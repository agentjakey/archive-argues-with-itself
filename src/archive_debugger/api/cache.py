"""Answer cache, content-addressed (cache format v2).

An answer is stored under a key that depends only on what produced it, never on where or when
the data files were copied:

  context = sha256 of the scope name, the canonical sha256 of the scope's two data files (from
            config/scopes.toml, the hashes the boot verifies), the retrieve config without host
            paths, and the generation settings (provider, model, prompt hash, top_k, temperature).
  key     = sha256 of {"v": 2, "context": context, "question": normalized question,
            "filters": canonical filters}.

The engine Worker computes the same key in TypeScript from the question, the filters and the
context string published with each release, so it can serve a stored answer without waking the
engine. Both sides are tested against the shared vectors in config/cache_key_vectors.json.

Privacy rule (docs/PRIVACY.md): a row keeps its question text only when the question is a
curated one (a seed question or a story's asked question). Any other row stores the key hash,
the answer and its metadata, no question, and expires RETENTION_DAYS after it was written.

Two stores share one interface: LocalCache (a SQLite file, for development, tests and the
offline exhibit) and RemoteCache (the engine Worker's internal cache route, backed by D1).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Protocol

from archive_debugger.retrieve.config import RetrieveConfig

KEY_VERSION = 2
RETENTION_DAYS = 180
_PATH_FIELDS = ("db_path", "index_path")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPACES = re.compile(r" {2,}")
_FILTER_TEXT = ("period", "jurisdiction", "doc_type")

SCHEMA = """
CREATE TABLE IF NOT EXISTS answers_v2 (
    key           TEXT PRIMARY KEY,
    scope         TEXT NOT NULL,
    curated       INTEGER NOT NULL,
    question      TEXT,
    response_json TEXT NOT NULL,
    extras_version TEXT NOT NULL,
    model         TEXT NOT NULL,
    prompt_sha256 TEXT NOT NULL,
    context       TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    expires_at    TEXT
);
CREATE INDEX IF NOT EXISTS answers_v2_expires ON answers_v2 (expires_at);
"""


# --- the key -------------------------------------------------------------------------------------

def canonical_json(value) -> str:
    """Sorted keys, no spaces, non-ASCII kept as is. Matches canonicalJson() in the Worker for the
    values the key uses (strings and string-keyed objects)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_question(text: Optional[str]) -> str:
    """The question as the key sees it: lone surrogates become U+FFFD, then Unicode NFC, then every
    control character (U+0000 to U+001F and U+007F) becomes a space, then runs of spaces collapse to
    one and the ends are trimmed. Nothing else changes: case, punctuation and other Unicode spaces
    stay, so two different questions never share an answer by accident."""
    text = text or ""
    text = "".join("\ufffd" if 0xD800 <= ord(ch) <= 0xDFFF else ch for ch in text)
    text = unicodedata.normalize("NFC", text)
    text = _CONTROL.sub(" ", text)
    return _SPACES.sub(" ", text).strip(" ")


def canonical_filters(filters: Optional[dict]) -> dict:
    """The filters as the key sees them: the three text filters as trimmed strings when non-empty,
    and min_ocr as a fixed four-decimal string when it is set and not zero. Unknown keys are
    ignored, as build_filters ignores them."""
    filters = filters or {}
    out = {}
    for name in _FILTER_TEXT:
        value = filters.get(name)
        if value is None:
            continue
        text = normalize_question(str(value))
        if text:
            out[name] = text
    min_ocr = filters.get("min_ocr")
    if min_ocr not in (None, "", 0):
        number = float(min_ocr)
        if number != 0.0:
            out["min_ocr"] = f"{number:.4f}"
    return out


def retrieve_settings(cfg: RetrieveConfig) -> dict:
    """The retrieve config with the host paths removed, so moving the data never moves the key."""
    out = {}
    for name, value in asdict(cfg).items():
        if name in _PATH_FIELDS:
            continue
        out[name] = str(value) if isinstance(value, Path) else value
    return out


def context_hash(*, scope: str, data_sha256: dict, retrieve: dict, provider: str, model: str,
                 prompt_sha256: str, top_k: int, temperature: Optional[float]) -> str:
    """Everything except the question and filters that decides an answer, as one hash."""
    if set(data_sha256) != {"db", "index"} or not all(len(v) == 64 for v in data_sha256.values()):
        raise ValueError(f"scope {scope!r}: data_sha256 needs a 64-hex 'db' and 'index' hash")
    material = {
        "scope": scope,
        "data_sha256": {k: v.lower() for k, v in data_sha256.items()},
        "retrieve": retrieve,
        "provider": provider,
        "model": model,
        "prompt_sha256": prompt_sha256,
        "top_k": top_k,
        "temperature": temperature,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def content_key(context: str, question: str, filters: Optional[dict]) -> str:
    """The cache key of one question under one context."""
    return sha256_hex(canonical_json({
        "v": str(KEY_VERSION),
        "context": context,
        "question": normalize_question(question),
        "filters": canonical_filters(filters),
    }))


def canonical_data_sha256(scope: str, registry: Optional[dict] = None) -> dict:
    """The published sha256 of a scope's two data files, from config/scopes.toml. These are the
    hashes the boot verifies every file against, so a served answer is keyed on the exact bytes."""
    from archive_debugger import scopes
    reg = registry if registry is not None else scopes.load_registry()
    r2 = ((reg.get("scopes") or {}).get(scope) or {}).get("r2") or {}
    out = {"db": str(r2.get("db_sha256") or "").lower(), "index": str(r2.get("index_sha256") or "").lower()}
    if not all(len(v) == 64 for v in out.values()):
        raise ValueError(f"scope {scope!r} has no published data sha256 in config/scopes.toml")
    return out


# --- question terms in a stored answer -----------------------------------------------------------

def withhold_terms(response: dict) -> dict:
    """A copy of a response whose coverage block no longer holds words of the question. The salient
    terms (the question's content words) become their count, and the uncovered terms become their
    positions in that list. Whoever serves the row again has the question in the request and puts
    the words back with restore_terms(). Used for every row that is not a curated question."""
    out = dict(response)
    answer = dict(out.get("answer") or {})
    coverage = dict(answer.get("coverage") or {})
    salient = list(coverage.pop("salient_terms", None) or [])
    uncovered = list(coverage.pop("uncovered_terms", None) or [])
    coverage["terms_withheld"] = {"salient_count": len(salient),
                                  "uncovered_index": [salient.index(t) for t in uncovered if t in salient]}
    answer["coverage"] = coverage
    out["answer"] = answer
    return out


def restore_terms(response: dict, salient: list[str]) -> bool:
    """Put the question's terms back into a withheld coverage block, in place. salient is
    salient_terms() of the asker's (cleaned) question. Returns False, changing nothing, when the
    count does not match, so the caller can recompute instead of showing wrong terms."""
    coverage = (response.get("answer") or {}).get("coverage") or {}
    withheld = coverage.get("terms_withheld")
    if withheld is None:
        return True
    if withheld.get("salient_count") != len(salient):
        return False
    coverage["salient_terms"] = list(salient)
    coverage["uncovered_terms"] = [salient[i] for i in withheld.get("uncovered_index") or [] if 0 <= i < len(salient)]
    del coverage["terms_withheld"]
    return True


# --- records -------------------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def make_record(*, key: str, scope: str, context: str, response: dict, extras_version: str,
                curated_question: Optional[str], now: Optional[datetime] = None) -> dict:
    """One stored row. curated_question is the question text for a curated question and None for
    any other: a visitor's question is never stored, its words are withheld from the coverage
    block, and the row expires after RETENTION_DAYS. Only curated rows never expire."""
    created = now or _now()
    generation = (response.get("answer") or {}).get("generation") or {}
    curated = curated_question is not None
    if not curated:
        response = withhold_terms(response)
    return {
        "key": key,
        "scope": scope,
        "curated": 1 if curated else 0,
        "question": curated_question if curated else None,
        "response_json": json.dumps(response, ensure_ascii=False),
        "extras_version": extras_version,
        "model": str(generation.get("model") or ""),
        "prompt_sha256": str(generation.get("prompt_sha256") or ""),
        "context": context,
        "created_at": created.isoformat(),
        "expires_at": None if curated else (created + timedelta(days=RETENTION_DAYS)).isoformat(),
    }


class AnswerStore(Protocol):
    def get(self, key: str) -> Optional[dict]: ...
    def put(self, record: dict) -> str: ...
    def close(self) -> None: ...


def _hit(record: dict) -> dict:
    return {"response": json.loads(record["response_json"]), "created_at": record["created_at"],
            "extras_version": record["extras_version"], "curated": bool(record["curated"])}


class LocalCache:
    """One SQLite file behind a lock. Every access is a keyed read or one write, so the lock never
    holds across a model call. Expired rows are removed when the file is opened and never served."""

    COLUMNS = ("key", "scope", "curated", "question", "response_json", "extras_version", "model",
               "prompt_sha256", "context", "created_at", "expires_at")

    def __init__(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = Path(path)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self._lock = threading.Lock()
        self.purge_expired()

    def purge_expired(self, now: Optional[datetime] = None) -> int:
        stamp = (now or _now()).isoformat()
        with self._lock:
            cur = self.conn.execute("DELETE FROM answers_v2 WHERE expires_at IS NOT NULL AND expires_at < ?", (stamp,))
            self.conn.commit()
        return cur.rowcount

    def get(self, key: str) -> Optional[dict]:
        stamp = _now().isoformat()
        with self._lock:
            row = self.conn.execute(
                f"SELECT {', '.join(self.COLUMNS)} FROM answers_v2 WHERE key = ? "
                "AND (expires_at IS NULL OR expires_at >= ?)", (key, stamp)).fetchone()
        return None if row is None else _hit(dict(zip(self.COLUMNS, row)))

    def put(self, record: dict) -> str:
        with self._lock:
            self.conn.execute(
                f"INSERT OR REPLACE INTO answers_v2 ({', '.join(self.COLUMNS)}) "
                f"VALUES ({', '.join('?' * len(self.COLUMNS))})",
                tuple(record[c] for c in self.COLUMNS))
            self.conn.commit()
        return record["created_at"]

    def count(self) -> dict:
        """Totals only: rows, curated rows, bytes of stored answers."""
        with self._lock:
            n, curated, size = self.conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(curated), 0), COALESCE(SUM(LENGTH(response_json)), 0) FROM answers_v2").fetchone()
        return {"rows": n, "curated": curated, "response_bytes": size}

    def close(self) -> None:
        with self._lock:
            self.conn.close()


class RemoteCache:
    """The engine Worker's internal cache route (D1 behind it). GET /cache/<key> returns the row or
    404; PUT /cache/<key> stores one. The route accepts only requests carrying the shared token
    (CIVIC_CACHE_TOKEN, a wrangler secret). A failed read is a miss and a failed write is logged and
    dropped: the cache can never turn a served answer into an error."""

    def __init__(self, base_url: str, token: str, *, timeout_s: float = 3.0):
        if not base_url or not token:
            raise ValueError("RemoteCache needs a base URL and a token")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_s = timeout_s

    def _request(self, method: str, key: str, body: Optional[bytes] = None):
        req = urllib.request.Request(f"{self.base_url}/cache/{key}", data=body, method=method,
                                     headers={"authorization": f"Bearer {self.token}",
                                              "content-type": "application/json"})
        return urllib.request.urlopen(req, timeout=self.timeout_s)

    def get(self, key: str) -> Optional[dict]:
        try:
            with self._request("GET", key) as resp:
                record = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                print(f"[cache] remote read failed: status {exc.code}", flush=True)
            return None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"[cache] remote read failed: {type(exc).__name__}", flush=True)
            return None
        return _hit(record)

    def put(self, record: dict) -> str:
        try:
            with self._request("PUT", record["key"], json.dumps(record, ensure_ascii=False).encode("utf-8")):
                pass
        except (urllib.error.URLError, OSError) as exc:
            print(f"[cache] remote write failed: {type(exc).__name__}", flush=True)
        return record["created_at"]

    def close(self) -> None:
        return None


def open_store(local_path: Path, *, remote_url: Optional[str] = None, remote_token: Optional[str] = None) -> AnswerStore:
    """The remote store when both its URL and token are set, else the local file."""
    if remote_url and remote_token:
        return RemoteCache(remote_url, remote_token)
    return LocalCache(local_path)
