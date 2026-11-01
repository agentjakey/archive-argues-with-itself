"""Building the registry from files. Each step is idempotent (INSERT OR IGNORE / REPLACE keyed by the
stable ids) and writes one audit-trail event, so a rebuild from the same files gives the same rows.

  add_catalogue   every catalogue record: documents, collection membership, catalogue and derived
                  dates kept apart, licence as stated, locators, coverage "known"
  add_indexed     an indexed corpus: its documents, pages and passages (ids unchanged), a "corpus"
                  text version, coverage "indexed" with the engine scope
  add_text        a fetched full-text version (djvu_txt), coverage "text_fetched"
  add_governance  the governance register's policies, per document they target"""
from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from archive_debugger.ingest import normalize
from archive_debugger.registry.schema import REGISTRY_VERSION, SCHEMA

REPO = Path(__file__).resolve().parents[3]
ACTOR = f"registry.build v{REGISTRY_VERSION}"
IA = "ia"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def doc_id(identifier: str) -> str:
    return f"{IA}:{identifier}"


def page_id(identifier: str, leaf: int) -> str:
    return f"{IA}:{identifier}#{int(leaf)}"


def version_id(identifier: str, kind: str, sha256: str) -> str:
    return f"{IA}:{identifier}@{kind}:{sha256[:12]}"


def open_registry(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('registry_version', ?)", (str(REGISTRY_VERSION),))
    conn.execute("INSERT OR IGNORE INTO archives VALUES (?, ?, ?)", (IA, "Internet Archive", "https://archive.org"))
    return conn


def audit(conn: sqlite3.Connection, action: str, target: str, detail: dict) -> None:
    conn.execute("INSERT INTO audit_trail (at, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)",
                 (now(), ACTOR, action, target, json.dumps(detail, sort_keys=True)))


def _list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _text(value) -> Optional[str]:
    items = [str(v) for v in _list(value) if v not in (None, "")]
    return "; ".join(items) if items else None


class Rules:
    def __init__(self, config_dir: Path = REPO / "config"):
        # The shared rules plus the Microlog rules (provinces and territories beyond the pilot's three).
        from archive_debugger.ingest.microlog_jurisdiction import load_rules
        self.text_rules, self.coll_rules = load_rules([config_dir / "jurisdiction_rules.csv",
                                                       config_dir / "microlog_jurisdiction_rules.csv"])
        self.aliases = normalize.load_issuer_aliases(config_dir / "issuer_aliases.csv")


def add_catalogue(conn: sqlite3.Connection, records: Iterable[dict], *, source_collection: str,
                  rules: Optional[Rules] = None) -> dict:
    rules = rules or Rules()
    seen = now()
    conn.execute("INSERT OR IGNORE INTO collections VALUES (?, ?, ?, 'source')",
                 (f"{IA}:{source_collection}", IA, source_collection))
    counts = {"documents": 0, "dated": 0, "derived": 0}
    for rec in records:
        ident = rec["identifier"]
        did = doc_id(ident)
        raw = json.dumps(rec, sort_keys=True, ensure_ascii=True).encode("utf-8")
        creator, publisher = _text(rec.get("creator")), _text(rec.get("publisher"))
        title = _text(rec.get("title"))
        colls = [str(c) for c in _list(rec.get("collection"))]
        jur, jur_method = normalize.classify_jurisdiction(creator or "", publisher or "", colls, title or "",
                                                          rules.text_rules, rules.coll_rules)
        issuer, issuer_method, _ = normalize.normalize_issuer(creator, publisher, rules.aliases)
        conn.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                     "COALESCE((SELECT first_seen FROM documents WHERE doc_id = ?), ?))",
                     (did, IA, ident, title, creator, publisher, _text(rec.get("language")), _text(rec.get("mediatype")),
                      int(rec["imagecount"]) if str(rec.get("imagecount") or "").isdigit() else None,
                      issuer, issuer_method, jur, jur_method, hashlib.sha256(raw).hexdigest(), did, seen))
        for c in colls:
            conn.execute("INSERT OR IGNORE INTO collections VALUES (?, ?, ?, 'membership')", (f"{IA}:{c}", IA, c))
            conn.execute("INSERT OR IGNORE INTO document_collections VALUES (?, ?)", (did, f"{IA}:{c}"))
        conn.execute("INSERT OR REPLACE INTO licences VALUES (?, ?, ?, ?)",
                     (did, _text(rec.get("licenseurl")), _text(rec.get("rights")),
                      "catalogue terms only: not reviewed for reuse"))
        parsed = normalize.parse_date(_text(rec.get("date")))
        conn.execute("INSERT OR REPLACE INTO dates VALUES (?, 'catalogue', ?, ?, ?, ?)",
                     (did, _text(rec.get("date")), parsed["year"], parsed["date_method"], "catalogue field date"))
        counts["dated"] += 1 if parsed["dated"] else 0
        if not parsed["dated"]:
            derived = normalize.recover_title_year(title)
            if derived is not None:
                conn.execute("INSERT OR REPLACE INTO dates VALUES (?, 'derived', ?, ?, 'title_extracted', ?)",
                             (did, str(derived), derived, title))
                counts["derived"] += 1
        if rec.get("addeddate"):
            conn.execute("INSERT OR REPLACE INTO dates VALUES (?, 'added', ?, ?, 'catalogue field addeddate', NULL)",
                         (did, _text(rec.get("addeddate")), None))
        conn.execute("INSERT OR IGNORE INTO locators VALUES (?, NULL, 'details', ?)", (did, f"https://archive.org/details/{ident}"))
        conn.execute("INSERT OR IGNORE INTO locators VALUES (?, NULL, 'djvu_txt', ?)",
                     (did, f"https://archive.org/download/{ident}/{ident}_djvu.txt"))
        conn.execute("INSERT OR IGNORE INTO coverage VALUES (?, 'known', '', ?)", (did, seen))
        counts["documents"] += 1
    audit(conn, "add_catalogue", f"{IA}:{source_collection}", counts)
    conn.commit()
    return counts


def add_indexed(conn: sqlite3.Connection, corpus: sqlite3.Connection, scope: str, *, with_passages: bool = True) -> dict:
    """An indexed corpus. Its passage ids are kept exactly; a document the catalogue fetch did not
    list (it may live in another collection) is added from the corpus's own catalogue columns."""
    seen = now()
    counts = {"documents": 0, "pages": 0, "passages": 0, "new_documents": 0}
    items = corpus.execute("SELECT item_id, title, creator_raw, publisher_raw, date_raw, collection_raw, language, "
                           "page_count, issuer_norm, issuer_method, jurisdiction_norm, jurisdiction_method, year, "
                           "date_method, dated FROM items").fetchall()
    for it in items:
        did = doc_id(it["item_id"])
        if conn.execute("SELECT 1 FROM documents WHERE doc_id = ?", (did,)).fetchone() is None:
            raw = json.dumps(dict(it), sort_keys=True, default=str).encode("utf-8")
            conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (did, IA, it["item_id"], it["title"], it["creator_raw"], it["publisher_raw"], it["language"],
                          "texts", it["page_count"], it["issuer_norm"], it["issuer_method"], it["jurisdiction_norm"],
                          it["jurisdiction_method"], hashlib.sha256(raw).hexdigest(), seen))
            conn.execute("INSERT OR REPLACE INTO dates VALUES (?, 'catalogue', ?, ?, ?, 'corpus items.date_raw')",
                         (did, it["date_raw"], it["year"] if it["dated"] else None, it["date_method"]))
            for c in json.loads(it["collection_raw"] or "[]") if (it["collection_raw"] or "").startswith("[") else []:
                conn.execute("INSERT OR IGNORE INTO collections VALUES (?, ?, ?, 'membership')", (f"{IA}:{c}", IA, c))
                conn.execute("INSERT OR IGNORE INTO document_collections VALUES (?, ?)", (did, f"{IA}:{c}"))
            conn.execute("INSERT OR IGNORE INTO locators VALUES (?, NULL, 'details', ?)",
                         (did, f"https://archive.org/details/{it['item_id']}"))
            conn.execute("INSERT OR IGNORE INTO coverage VALUES (?, 'known', '', ?)", (did, seen))
            conn.execute("INSERT OR REPLACE INTO licences VALUES (?, NULL, NULL, 'catalogue terms only: not reviewed for reuse')", (did,))
            counts["new_documents"] += 1
        conn.execute("INSERT OR IGNORE INTO coverage VALUES (?, 'indexed', ?, ?)", (did, scope, seen))
        counts["documents"] += 1
    if not with_passages:
        audit(conn, "add_indexed", f"scope:{scope}", {**counts, "documents_only": True})
        conn.commit()
        return counts
    vids = {}
    for p in corpus.execute("SELECT item_id, leaf_index, printed_page, ocr_conf_mean FROM pages"):
        pid = page_id(p["item_id"], p["leaf_index"])
        conn.execute("INSERT OR IGNORE INTO pages VALUES (?, ?, ?, ?, ?)",
                     (pid, doc_id(p["item_id"]), int(p["leaf_index"]), p["printed_page"], p["ocr_conf_mean"]))
        conn.execute("INSERT OR IGNORE INTO locators VALUES (?, ?, 'page', ?)",
                     (doc_id(p["item_id"]), pid, f"https://archive.org/details/{p['item_id']}/page/n{int(p['leaf_index'])}"))
        counts["pages"] += 1
    for row in corpus.execute("SELECT passage_id, item_id, leaf_index, char_start, char_end, text FROM passages"):
        ident = row["item_id"]
        if ident not in vids:
            vid = version_id(ident, "corpus", hashlib.sha256(f"{scope}:{ident}".encode()).hexdigest())
            conn.execute("INSERT OR IGNORE INTO versions VALUES (?, ?, 'corpus', NULL, ?, NULL, NULL, 1, NULL, NULL)",
                         (vid, doc_id(ident), f"scope:{scope}"))
            vids[ident] = vid
        conn.execute("INSERT OR IGNORE INTO passages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (row["passage_id"], doc_id(ident), page_id(ident, row["leaf_index"]) if row["leaf_index"] is not None else None,
                      vids[ident], row["char_start"], row["char_end"],
                      hashlib.sha256((row["text"] or "").encode("utf-8")).hexdigest(), scope))
        counts["passages"] += 1
    audit(conn, "add_indexed", f"scope:{scope}", counts)
    conn.commit()
    return counts


def add_text(conn: sqlite3.Connection, identifier: str, *, store_key: str, sha256: str, size: int,
             source_url: str, page_breaks: bool, fetched_at: str) -> str:
    vid = version_id(identifier, "djvu_txt", sha256)
    conn.execute("INSERT OR REPLACE INTO versions VALUES (?, ?, 'djvu_txt', ?, ?, ?, ?, ?, NULL, ?)",
                 (vid, doc_id(identifier), source_url, store_key, sha256, size, 1 if page_breaks else 0, fetched_at))
    conn.execute("INSERT OR IGNORE INTO coverage VALUES (?, 'text_fetched', '', ?)", (doc_id(identifier), fetched_at))
    return vid


def add_governance(conn: sqlite3.Connection, register: Path) -> dict:
    """Production policies only: a fixture record is refused, as the engine's loader refuses it."""
    counts = {"policies": 0, "documents": 0}
    if not register.exists():
        audit(conn, "add_governance", str(register), {"policies": 0, "note": "no register: no restrictions"})
        conn.commit()
        return counts
    for line in register.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        policy = json.loads(line)
        if policy.get("fixture"):
            raise ValueError(f"{register} holds a fixture policy ({policy.get('policy_id')}): refused")
        counts["policies"] += 1
        targets = policy.get("targets") or {}
        docs = {doc_id(i) for i in targets.get("items") or []}
        for c in targets.get("collections") or []:
            docs |= {r[0] for r in conn.execute("SELECT doc_id FROM document_collections WHERE collection_id = ?", (f"{IA}:{c}",))}
        for d in docs:
            conn.execute("INSERT OR REPLACE INTO governance VALUES (?, ?, ?, ?)",
                         (d, policy["policy_id"], json.dumps(policy.get("restrict") or []), policy.get("authority", "")))
            counts["documents"] += 1
    audit(conn, "add_governance", str(register), counts)
    conn.commit()
    return counts


def read_catalogue(path: Path) -> Iterable[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)
