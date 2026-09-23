"""Read-only serve layer (FastAPI). One Retriever opened at startup; every request
runs retrieve -> compose and returns the Answer plus an evidence timeline. Reuses
generate/cli.py's config loading and filter construction. Never writes civic.db;
the only write is the separate answer cache file.

CORS: ALLOWED_ORIGINS env (comma-separated); empty means same-origin only.
Static: serves web/dist when it exists, with index.html fallback for client routes.
.env: loaded here (the API is outside generate/, so generate/ hermeticity is
unchanged); load_dotenv never overrides variables already set in the environment."""
from __future__ import annotations

import copy
import functools
import json
import os
import re
import sqlite3
import threading
import time
import tomllib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from archive_debugger import crisis, flags, scopes
from archive_debugger.scopes import parse_enabled_scopes
from archive_debugger.api.cache import AnswerCache, cache_key, retrieval_fingerprint
from archive_debugger.api.coverage import coverage as compute_coverage
from archive_debugger.eval import store
from archive_debugger.eval.questions import load_seed
from archive_debugger.generate.answer import Answer, compose, coverage_of, generation_meta
from archive_debugger.generate.cli import build_filters, load_generate_config, retrieve_pool, sent_temperature
from archive_debugger.generate.llm import LLM, AnthropicLLM, make_llm
from archive_debugger.ingest.db import ENV_CACHE_PATH, env_path
from archive_debugger.retrieve import citation
from archive_debugger.retrieve.search import Retriever

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_DIST = REPO_ROOT / "web" / "dist"
DEFAULT_SEED = Path("eval/seed_questions.jsonl")
DEFAULT_CACHE = Path("data/cache/answers.db")
DEFAULT_PAGES = Path("data/cache/pages")           # offline pack of page images (scripts/offline_pack.py)
DEFAULT_STORIES = Path("config/stories.json")
ENV_PAGES_DIR = "CIVIC_PAGES_DIR"
ENV_SERVE_SCOPES = "CIVIC_SERVE_SCOPES"   # local multi-scope opt-in: "pilot,microlog". Unset = single base scope.
ENV_ENABLED_SCOPES = "CIVIC_ENABLED_SCOPES"   # deploy gate: only these scopes are built/exposed. Unset = all.
ENV_DEFAULT_SCOPE = "CIVIC_DEFAULT_SCOPE"     # UI landing scope (GET /scopes 'default'); falls back if not built.
DEFAULT_LANDING = "microlog"                  # landing when CIVIC_DEFAULT_SCOPE is unset (falls back to the base scope)
SNIPPET = 300
_PAGE_FILE = re.compile(r"^n(\d+)_(thumb|medium)\.jpg$")
# Memory-map extra scopes' large databases. SQLite clamps to its own compiled max, so an
# oversized target is safe. The pilot connection is left exactly as before (no PRAGMA).
MMAP_BYTES = 1 << 33   # 8 GiB target

# Offline degradation + input hardening (R1). When the model cannot answer (no key,
# unreachable/timeout, or rate-limited), /ask returns 200 with a designed limited-mode
# state and the retrieved record, never a raw error (N6). The generation logic in
# generate/ is untouched (N5): the hard timeout lives here, on the client this layer
# builds.
GEN_TIMEOUT_S = 20.0                 # hard cap on one generation call; the kiosk must never hang
MAX_QUESTION_CHARS = 500             # server-side defense in depth; the web input caps lower
PUBLIC_URL = os.environ.get("PUBLIC_URL", "https://archive-argues-with-itself-production.up.railway.app")
RATE_BURST, RATE_REFILL = 5, 0.5     # token bucket on model-calling requests (this process)
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DEGRADE_MSG = {
    "no_key": "offline: showing the record, read the source yourself; the live version at {url} generates answers.",
    "model_unreachable": "offline: showing the record, read the source yourself; the live version at {url} generates answers.",
    "rate_limited": "one moment: showing the record below while the answer service catches up.",
    "empty": "type a question to search the record.",
}


def clean_question(q: str) -> str:
    """Strip control characters, collapse whitespace, and cap length. Sanitizes the text
    handed to retrieval and the model; the cache key still uses the original text, so a
    warmed answer keeps hitting."""
    return " ".join(_CTRL.sub(" ", q or "").split())[:MAX_QUESTION_CHARS]


class RateLimiter:
    """A tiny token bucket, shared by all requests in this process. Only the
    model-calling path consumes a token; a cached answer never does."""

    def __init__(self, capacity: int, refill_per_s: float):
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.refill = refill_per_s
        self.ts = time.monotonic()
        self.lock = threading.Lock()

    def allow(self) -> bool:
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.ts) * self.refill)
            self.ts = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


def local_page(pages_dir: Optional[Path], item_id: str, leaf: int, kind: str) -> Optional[str]:
    """API path of a page image held in the offline pack, or None when absent."""
    if pages_dir is None:
        return None
    name = f"n{leaf}_{kind}.jpg"
    return f"/pages/{item_id}/{name}" if (Path(pages_dir) / item_id / name).is_file() else None


def answer_cache_key(gcfg: dict, kind: str, model_id: str, question: str, filters: Optional[dict],
                     retrieval_sha256: str) -> str:
    """The exact key /ask uses, shared with scripts that need to know what is cached."""
    temp = sent_temperature(kind, gcfg)
    gen = generation_meta(provider=kind, model=model_id, temperature=temp,
                          max_tokens=gcfg["max_tokens"], top_k=gcfg["top_k"])
    return cache_key(question=question, filters=filters, provider=kind, model=model_id,
                     prompt_sha256=gen["prompt_sha256"], top_k=gcfg["top_k"], temperature=temp,
                     retrieval_sha256=retrieval_sha256)


class AskRequest(BaseModel):
    question: str
    filters: Optional[dict] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    nocache: bool = False


def evidence_rows(hits: list[dict], verified: list[dict], prompt_ids: Optional[set] = None,
                  pages_dir: Optional[Path] = None) -> list[dict]:
    """hits is the whole pool shown in the trail; prompt_ids marks the prefix the model saw.
    When the offline pack holds a page image, its API path replaces the archive.org URL
    and `offline` is true, so the exhibit shows real pages without a network."""
    cited_ids = {c["passage_id"] for c in verified}
    ordered = sorted(hits, key=lambda h: (h.get("year") is None, h.get("year") or 0))  # undated last
    rows = []
    for h in ordered:
        thumb = local_page(pages_dir, h["item_id"], h["leaf_index"], "thumb")
        image = local_page(pages_dir, h["item_id"], h["leaf_index"], "medium")
        rows.append({
            "in_prompt": True if prompt_ids is None else h["passage_id"] in prompt_ids,
            "section_class": h.get("section_class") or "body",
            "later_years": h.get("later_years"),
            "ocr_quality": h.get("ocr_quality"),   # 0..1 from _provenance; client flags a shaky line

            "passage_id": h["passage_id"], "item_id": h["item_id"], "title": h.get("title"),
            "year": h.get("year"), "decade": h.get("decade"), "jurisdiction": h.get("jurisdiction"),
            "doc_type": h.get("doc_type"), "leaf_index": h["leaf_index"], "printed_page": h.get("printed_page"),
            "deep_link": h["page_deep_link"],
            "page_thumb": thumb or citation.page_thumb(h["item_id"], h["leaf_index"]),
            "page_image": image or citation.page_image(h["item_id"], h["leaf_index"]),
            "embed_url": citation.embed_url(h["item_id"], h["leaf_index"]),
            "offline": bool(thumb or image),
            "snippet": " ".join((h.get("text") or "").split())[:SNIPPET],
            "bm25_rank": h.get("bm25_rank"), "dense_rank": h.get("dense_rank"),
            "cited": h["passage_id"] in cited_ids,
        })
    return rows


def load_stories(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    stories = json.loads(Path(path).read_text(encoding="utf-8"))
    for s in stories:
        if not (isinstance(s.get("pins"), list) and len(s["pins"]) == 2 and s.get("question") and s.get("id")):
            raise ValueError(f"story {s.get('id')!r} needs id, question, and exactly two pins")
    return stories


def corpus_facts(conn, pilot_window: dict) -> dict:
    """Whole-corpus figures for the header strip, computed once at startup."""
    items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    passages = conn.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
    undated = conn.execute(
        "SELECT COUNT(*) FROM passages p JOIN items i ON i.item_id = p.item_id "
        "WHERE i.dated = 0 OR i.dated IS NULL").fetchone()[0]
    undated_items = conn.execute(
        "SELECT COUNT(*) FROM items WHERE dated = 0 OR dated IS NULL").fetchone()[0]
    # Dated items whose metadata year falls outside the scope's nominal (config) window. The bounds
    # come from the scope's own config window (pilot_window), never a literal, so each scope measures
    # against its own window. Both scopes' config window is 1960-2009, matching
    # ingest.normalize.period_of and _PERIOD_CASE, so this still equals by_period['pre-1960'] +
    # by_period['post-2009'] on the same items table (one count across header, timeline, sources).
    w0 = (pilot_window or {}).get("min_year")
    w1 = (pilot_window or {}).get("max_year")
    out_of_window = conn.execute(
        "SELECT COUNT(*) FROM items WHERE dated = 1 AND "
        "((? IS NOT NULL AND year < ?) OR (? IS NOT NULL AND year > ?))",
        (w0, w0, w1, w1)).fetchone()[0]
    mn, mx = conn.execute("SELECT MIN(year), MAX(year) FROM items WHERE dated = 1").fetchone()
    return {
        "items": items,
        "passages": passages,
        "passages_undated": undated,
        "undated_share": round(undated / passages, 4) if passages else 0.0,   # passage-weighted (% of passages)
        "items_undated": undated_items,
        "undated_item_share": round(undated_items / items, 4) if items else 0.0,   # headline undated basis
        "items_out_of_window": out_of_window,
        "window": {"min_year": mn, "max_year": mx},          # true dated span
        "pilot_window": pilot_window,                         # config binning window
    }


def _pilot_window(config_path: Path) -> dict:
    with Path(config_path).open("rb") as fh:
        w = tomllib.load(fh).get("corpus", {}).get("window", {})
    return {"min_year": w.get("start_year"), "max_year": w.get("end_year")}


def _allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip()]


def _key_available() -> bool:
    # The SDK also honors ANTHROPIC_AUTH_TOKEN; an `ant auth` profile on disk is not
    # detected here and would be reported as missing.
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _clean_filters(period: Optional[str], jurisdiction: Optional[str], doc_type: Optional[str]) -> dict:
    return {k: v for k, v in (("period", period), ("jurisdiction", jurisdiction), ("doc_type", doc_type)) if v}


def parse_serve_scopes(raw: Optional[str]) -> Optional[list[str]]:
    """CIVIC_SERVE_SCOPES -> the list of scopes to serve from one process, or None (the
    single-scope default, byte-identical to the deploy)."""
    if not raw:
        return None
    names = [s.strip() for s in raw.split(",") if s.strip()]
    return names or None


def scopes_to_build(base_name: str, serve_scopes: Optional[list], enabled: Optional[set]) -> list:
    """Non-base scope names to attempt to build. serve_scopes are honored (the local multi-scope
    opt-in); when an ENABLED set is given, every enabled scope is also built, so a deploy that sets
    only CIVIC_ENABLED_SCOPES=pilot,microlog serves both. ENABLED always gates: a scope not in it is
    dropped. The base is never returned (it is always built)."""
    out: list = []
    for name in (serve_scopes or []):
        if name != base_name and name not in out:
            out.append(name)
    if enabled is not None:
        for name in sorted(enabled):
            if name != base_name and name not in out:
                out.append(name)
        out = [n for n in out if n in enabled]
    return out


def resolve_landing_scope(requested: Optional[str], built: list, base_name: str) -> str:
    """The scope the UI lands on first (GET /scopes 'default'): the requested scope when it is
    actually built/served here, else the base (always-served) scope. Never errors on an unavailable
    default -- a pilot-only box asked to land on microlog simply lands on the pilot. This is a UI
    concern only; no-scope request routing stays on the base scope, so the pilot path is unchanged."""
    if requested and requested in built:
        return requested
    return base_name


def offline_scopes() -> list[dict]:
    """Every scope this box can serve offline, for the page-pack tooling (scan_coverage, offline_pack).
    The base pilot (via config + CIVIC_* env, exactly like the deploy) plus any registered non-inherit
    scope whose built database is present. Each entry names the paths the shared, item-id-keyed page
    pack (data/cache/pages) must cover for that scope: its answer cache, its civic.db, and its optional
    stories file. A scope whose database is absent (e.g. microlog on the pilot-only festival volume) is
    skipped, so the pilot box is unaffected."""
    from archive_debugger.ingest.db import resolve_db_path
    out: list[dict] = [{
        "name": "pilot",
        "config": Path("config/pilot.toml"),
        "cache_db": env_path(ENV_CACHE_PATH, DEFAULT_CACHE),
        "civic_db": Path(resolve_db_path("config/pilot.toml")),
        "stories": DEFAULT_STORIES,
    }]
    try:
        reg = scopes.load_registry()
    except scopes.ScopeError:
        return out
    default = reg.get("default", "pilot")
    for name in reg.get("scopes", {}):
        if name == default:
            continue
        try:
            rs = scopes.resolve_scope(name)
        except scopes.ScopeError:
            continue
        if rs.inherit or not Path(rs.db_path).exists():
            continue
        root = Path(rs.db_path).parent
        out.append({
            "name": name,
            "config": rs.config_path,
            "cache_db": root / "cache" / "answers.db",
            "civic_db": Path(rs.db_path),
            "stories": root / "stories.json",
        })
    return out


def _enable_mmap(conn: sqlite3.Connection) -> None:
    """Memory-map the connection's main and attached (vec) databases. Read-only I/O tuning
    only; query results are unchanged. Applied to extra scopes, never the pilot."""
    for target in (f"PRAGMA mmap_size = {MMAP_BYTES}", f"PRAGMA vec.mmap_size = {MMAP_BYTES}"):
        try:
            conn.execute(target)
        except sqlite3.Error:
            pass


def _registry_entry(name: str) -> dict:
    try:
        return scopes.load_registry().get("scopes", {}).get(name, {}) or {}
    except scopes.ScopeError:
        return {}


def _config_collections(config_path) -> list[str]:
    try:
        with Path(config_path).open("rb") as fh:
            raw = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    cols = raw.get("corpus", {}).get("collections", {}).get("clean", []) or []
    return [str(c) for c in cols]


def _coverage_window(nominal: dict, span: dict, unclamped: bool) -> dict:
    """The window a scope should DISPLAY as its coverage, derived from its own data + config: the
    start is clamped past pre-window outliers to the nominal start, and the end is the true dated-span
    max when the scope reaches materially past its window (unclamped, e.g. microlog into the 2010s) or
    the nominal end otherwise (the pilot, which never frames itself as reaching the present). No literal
    years; both bounds resolve from the scope's config window and its own dated span."""
    ns = (nominal or {}).get("min_year")
    ne = (nominal or {}).get("max_year")
    ss = (span or {}).get("min_year")
    se = (span or {}).get("max_year")
    starts = [y for y in (ns, ss) if y is not None]
    start = max(starts) if starts else None
    if unclamped:
        end = se if se is not None else ne
    else:
        ends = [y for y in (ne, se) if y is not None]
        end = min(ends) if ends else None
    return {"min_year": start, "max_year": end}


def _harvested_count(entry: dict) -> Optional[int]:
    """The scope's harvested item total, read from its committed harvest manifest (data, not a code
    literal): the recorded `count`, or the authoritative numFound the harvest targeted. None when no
    manifest is configured or it cannot be read, so the explorer simply omits the reconciliation."""
    path = entry.get("manifest")
    if not path:
        return None
    try:
        m = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    c = m.get("count")
    if c is None:
        c = m.get("authoritative_numfound_expected")
    return int(c) if isinstance(c, (int, float)) else None


def scope_facts(name: str, config_path, corpus: dict) -> dict:
    """The active scope's identity for the switcher: label, source collection with its archive.org
    link, item count, the config binning window, the DISPLAYED coverage window (per-scope, from data
    + config), and the harvested item total (from the scope's manifest) so the explorer can reconcile
    harvested vs live. Labels come from the registry (config/scopes.toml); the collection falls back
    to the scope config; the counts come from the built corpus."""
    entry = _registry_entry(name)
    cols = _config_collections(config_path)
    collection = entry.get("collection") or (cols[0] if cols else None)
    return {
        "name": name,
        "label": entry.get("label") or name,
        "blurb": entry.get("blurb") or "",
        "collection": collection,
        "collection_url": f"https://archive.org/details/{collection}" if collection else None,
        "collections": cols,
        "item_count": corpus["items"],
        "window": corpus["pilot_window"],
        "coverage_window": _coverage_window(corpus["pilot_window"], corpus["window"],
                                            bool(entry.get("coverage_unclamped"))),
        "harvested_count": _harvested_count(entry),
    }


_OCR_BUCKET = ("CASE WHEN CAST(p.ocr_quality AS REAL) >= 0.66 THEN 'high' "
               "WHEN CAST(p.ocr_quality AS REAL) >= 0.33 THEN 'medium' ELSE 'low' END")


def _ocr_distribution(conn) -> dict:
    """Passage-weighted OCR-quality buckets (high >= 0.66 / medium >= 0.33 / low), the same
    proxy the retriever down-weights by. Read-only aggregate over the scope's own passages."""
    out = {"high": 0, "medium": 0, "low": 0}
    for bucket, n in conn.execute(f"SELECT {_OCR_BUCKET} b, COUNT(*) FROM passages p GROUP BY b"):
        out[bucket] = n
    return out


def _jurisdiction_distribution(conn, items_total: int) -> tuple[list, float]:
    """Items per normalized jurisdiction, and the unknown share. The jurisdiction is an
    issuer-derived PROXY (a floor), not full provincial coverage; the caller flags it so."""
    rows, unknown = [], 0
    for j, n in conn.execute(
        "SELECT COALESCE(jurisdiction_norm, 'unknown') j, COUNT(*) c FROM items GROUP BY j ORDER BY c DESC"):
        rows.append({"name": j, "items": n, "share": round(n / items_total, 4) if items_total else 0.0})
        if j == "unknown":
            unknown = n
    return rows, (round(unknown / items_total, 4) if items_total else 0.0)


def _date_method_distribution(conn) -> dict:
    """Item counts by date_method: exact (catalog metadata), title_extracted (from the
    document's own title), unknown (undated). Nothing here is inferred/estimated."""
    return {m: n for m, n in conn.execute(
        "SELECT COALESCE(date_method, 'unknown') m, COUNT(*) c FROM items GROUP BY m")}


# Same period buckets as ingest.normalize.period_of: undated, pre-1960, each decade, post-2009.
# 'undated' here is exactly the undated-items set the sources view reports (dated != 1), so the
# timeline's undated bucket and the sources view's undated share share one basis.
_PERIOD_CASE = (
    "CASE WHEN i.dated = 1 AND i.year IS NOT NULL AND i.year < 1960 THEN 'pre-1960' "
    "WHEN i.dated = 1 AND i.year IS NOT NULL AND i.year > 2009 THEN 'post-2009' "
    "WHEN i.dated = 1 AND i.year IS NOT NULL THEN CAST((i.year / 10) * 10 AS TEXT) || 's' "
    "ELSE 'undated' END"
)


def _period_distribution(conn) -> dict:
    """Item counts per period for the thematic timeline. Real per-decade document counts;
    undated is its own bucket, never distributed onto a decade; out-of-window periods
    (pre-1960, post-2009) appear only when items actually fall there (honest window)."""
    return {p: n for p, n in conn.execute(
        f"SELECT {_PERIOD_CASE} AS period, COUNT(*) FROM items i GROUP BY period")}


def scope_composition(conn, corpus: dict) -> dict:
    """Real per-scope composition for the sources view, computed live from the scope's own
    databases (never hardcoded): passage count, true dated span, undated share, OCR-quality
    distribution, the jurisdiction proxy (a floor), and how dates were resolved."""
    items = corpus["items"]
    undated_items = conn.execute("SELECT COUNT(*) FROM items WHERE dated = 0 OR dated IS NULL").fetchone()[0]
    juris, unknown_share = _jurisdiction_distribution(conn, items)
    # A scope whose jurisdiction was resolved by the scope-local proxy map (microlog) stays a
    # floor: per-province counts are not verified per item, so the flag holds even after the
    # unknown share drops below the numeric threshold. The pilot has no such rows, so its
    # is_floor is unchanged.
    proxy_resolved = conn.execute(
        "SELECT COUNT(*) FROM items WHERE jurisdiction_method LIKE 'microlog_map:%'").fetchone()[0] > 0
    return {
        "passages": corpus["passages"],
        "dated_span": corpus["window"],       # true MIN/MAX year of dated items
        "window": corpus["pilot_window"],     # config binning window
        "undated": {
            "items": undated_items,
            "item_share": round(undated_items / items, 4) if items else 0.0,
            "passages": corpus["passages_undated"],
            "passage_share": corpus["undated_share"],
        },
        "ocr": _ocr_distribution(conn),
        "jurisdictions": juris,
        "jurisdiction_unknown_share": unknown_share,
        "jurisdiction_is_floor": bool(unknown_share >= 0.20 or proxy_resolved),
        "date_method": _date_method_distribution(conn),
        # Real per-period document counts for the thematic timeline. normalize sets dated=1 only
        # with a year, so by_period['undated'] equals undated['items'] above for any real corpus:
        # the timeline's undated bar and this view's undated count come from one basis.
        "by_period": _period_distribution(conn),
    }


def _attach_date_method(conn, rows) -> None:
    """Serve-time provenance: label each evidence row's date source from items.date_method
    (exact = catalog metadata, title_extracted = the document's own title, unknown = undated).
    Computed on serve and never stored, so it covers cached answers too, exactly like the
    offline-pack image paths and the flag. Retrieval (search.py) is untouched."""
    ids = {r["item_id"] for r in rows if r.get("item_id")}
    if not ids:
        return
    marks = ",".join("?" * len(ids))
    dm = {i: m for i, m in conn.execute(
        f"SELECT item_id, date_method FROM items WHERE item_id IN ({marks})", list(ids))}
    for r in rows:
        r["date_method"] = dm.get(r.get("item_id"))


class Bundle:
    """Everything one served scope needs, isolated per scope: its own Retriever (read-only
    connections to only its own databases), lock, answer cache, coverage cache, generation
    config, corpus facts, and display facts. Built with that scope active, so the connection
    is fenced to its corpus at open time; at request time no scope is active and a bundle can
    only ever read its own DBs. The base (default) scope's fields are aliased onto app.state
    so the pilot request path and offline_walkthrough see it exactly as before."""

    def __init__(self, *, name, retriever, gcfg, pilot_window, cache, retrieval_sha256,
                 corpus, facts, stories, seed_path, pages_dir, provider, llm, own_retriever):
        self.name = name
        self.retriever = retriever
        self.gcfg = gcfg
        self.pilot_window = pilot_window
        self.cache = cache
        self.coverage_cache: dict = {}
        self.retrieval_sha256 = retrieval_sha256
        self.corpus = corpus
        self.facts = facts
        self.stories = stories
        self.seed_path = seed_path
        self.pages_dir = pages_dir
        self.provider = provider
        self.llm = llm
        self.own_retriever = own_retriever
        self.lock = threading.Lock()   # one sqlite connection per bundle; sync endpoints run in a threadpool


def create_app(config_path: Path = Path("config/pilot.toml"), *, retriever: Optional[Retriever] = None,
               provider: Optional[str] = None, llm: Optional[LLM] = None,
               seed_path: Path = DEFAULT_SEED, web_dist: Path = WEB_DIST, load_env: bool = True,
               cache_path: Optional[Path] = None, pages_dir: Optional[Path] = None,
               stories_path: Path = DEFAULT_STORIES, scope: Optional[str] = None,
               serve_scopes: Optional[list[str]] = None,
               enabled_scopes: Optional[list[str]] = None,
               default_scope: Optional[str] = None) -> FastAPI:
    if load_env:
        from dotenv import load_dotenv
        load_dotenv()
    # Scope layer (additive): with no scope and no serve_scopes this serves the pilot exactly
    # as before. A named scope serves that scope's config + registry databases. serve_scopes
    # serves several scopes from one process, routed per request by a `scope` parameter, with
    # the pilot the default; it NEVER pins the process (that would break the pilot and the
    # fence). Each scope's retriever is opened with only that scope active, so every
    # connection is fenced to its own databases at open time; at request time no scope is
    # active and a bundle can read only its own corpus.
    base_config = config_path
    if scope is not None:
        resolved = scopes.resolve_scope(scope)
        base_config = resolved.config_path
        base_name = resolved.name
        # Single-scope legacy path only: pin the process so the CIVIC_SCOPE=<name> deploy is
        # byte-identical to before. In multi-scope we never pin.
        if not resolved.inherit and not serve_scopes:
            scopes.set_active(resolved)
    else:
        try:
            base_name = scopes.load_registry().get("default", "pilot")
        except scopes.ScopeError:
            base_name = "pilot"
    base_cache_path = cache_path or env_path(ENV_CACHE_PATH, DEFAULT_CACHE)
    pages_dir = pages_dir or env_path(ENV_PAGES_DIR, DEFAULT_PAGES)
    base_stories = load_stories(stories_path)

    def _build_bundle(name, *, cfg_path, retr, cache_p, seed_p, stories_list, llm_obj, mmap) -> Bundle:
        """Open one scope's databases and generation config with only that scope active, so
        the connection is fenced to its own corpus. The base scope may pass an injected
        retriever (tests) and is never memory-mapped (the pilot stays exactly as before)."""
        resolved_b = scopes.resolve_scope(name)
        active = None if resolved_b.inherit else resolved_b
        with scopes.activate(active):
            r = retr or Retriever(cfg_path)
            if mmap and retr is None:
                _enable_mmap(r.conn)
            gcfg = load_generate_config(cfg_path)
            pilot_window = _pilot_window(cfg_path)
            sha = retrieval_fingerprint(r.cfg)
            corpus = corpus_facts(r.conn, pilot_window)
            facts = scope_facts(name, cfg_path, corpus)
            facts["composition"] = scope_composition(r.conn, corpus)   # real numbers for the sources view
        return Bundle(name=name, retriever=r, gcfg=gcfg, pilot_window=pilot_window,
                      cache=AnswerCache(cache_p), retrieval_sha256=sha, corpus=corpus,
                      facts=facts, stories=stories_list,
                      seed_path=seed_p, pages_dir=pages_dir, provider=provider, llm=llm_obj,
                      own_retriever=retr is None)

    def _extra_bundle(name) -> Optional[Bundle]:
        """Build one additional scope, or None if it cannot be served here because its
        databases are not present (e.g. the festival volume holds only the pilot). A missing
        or broken extra scope never breaks serving the base, so the deploy is unaffected."""
        try:
            rs = scopes.resolve_scope(name)
            if not (Path(rs.db_path).exists() and Path(rs.index_path).exists()):
                return None
            cache_p = Path(rs.db_path).parent / "cache" / "answers.db"     # isolated, never the pilot's cache
            story_file = Path(rs.db_path).parent / "stories.json"          # optional; absent -> no stories
            return _build_bundle(name, cfg_path=rs.config_path, retr=None, cache_p=cache_p,
                                 seed_p=None, stories_list=load_stories(story_file), llm_obj=None, mmap=True)
        except Exception:  # noqa: BLE001 - a bad extra scope is skipped, never fatal to the base serve
            return None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        base = _build_bundle(base_name, cfg_path=base_config, retr=retriever, cache_p=base_cache_path,
                             seed_p=seed_path, stories_list=base_stories, llm_obj=llm, mmap=False)
        bundles = {base.name: base}
        # ENABLED_SCOPES gate: only build/serve/expose the enabled scopes (None = all). The base is
        # always served; extra scopes not enabled are never built, so /scopes and the switcher never
        # advertise a scope this deployment has no data for.
        enabled = (set(enabled_scopes) if enabled_scopes is not None
                   else parse_enabled_scopes(os.environ.get(ENV_ENABLED_SCOPES)))
        for name in scopes_to_build(base.name, serve_scopes, enabled):
            if name in bundles:
                continue
            extra = _extra_bundle(name)
            if extra is not None:
                bundles[extra.name] = extra
        app.state.bundles = bundles
        # Routing default (no-scope requests + the back-compat aliases below): always the base, so
        # the pilot request path stays byte-identical.
        app.state.default_scope = base.name
        # UI landing scope (GET /scopes 'default'): CIVIC_DEFAULT_SCOPE when that scope is actually
        # built here, else the base. Lets the deploy land on microlog while a pilot-only box lands on
        # the pilot, both scopes in the switcher. Separate from routing so no-scope calls stay on the base.
        requested_landing = default_scope or os.environ.get(ENV_DEFAULT_SCOPE) or DEFAULT_LANDING
        app.state.landing_scope = resolve_landing_scope(requested_landing, list(bundles), base.name)
        app.state.model_ratelimit = RateLimiter(RATE_BURST, RATE_REFILL)   # one process-wide model budget
        # Back-compat aliases: the pilot request path and offline_walkthrough (which patches
        # app.state.cache.put) see the default bundle exactly as the single-scope app did.
        app.state.retriever = base.retriever
        app.state.lock = base.lock
        app.state.cache = base.cache
        app.state.coverage_cache = base.coverage_cache
        app.state.retrieval_sha256 = base.retrieval_sha256
        app.state.corpus = base.corpus
        try:
            yield
        finally:
            for b in bundles.values():
                b.cache.close()
                if b.own_retriever:
                    b.retriever.close()

    app = FastAPI(title="archive-argues-with-itself", lifespan=lifespan)
    origins = _allowed_origins()
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

    def _bundle(scope_param: Optional[str]) -> Bundle:
        """The bundle for a request. No scope (or the default name) returns the base bundle,
        so the no-scope path is byte-identical to the single-scope app. An unserved scope 404s."""
        name = scope_param or app.state.default_scope
        b = app.state.bundles.get(name)
        if b is None:
            raise HTTPException(status_code=404, detail=f"scope {name!r} is not served here")
        return b

    def answer(b: Bundle, question: str, filters: Optional[dict], req_provider: Optional[str],
               req_model: Optional[str], nocache: bool):
        r = b.retriever
        gcfg = b.gcfg
        kind = req_provider or b.provider or gcfg["provider"]
        model_id = req_model or gcfg["model"]
        temp = sent_temperature(kind, gcfg)
        gen = generation_meta(provider=kind, model=model_id, temperature=temp,
                              max_tokens=gcfg["max_tokens"], top_k=gcfg["top_k"])
        # Key on the ORIGINAL text so every warmed answer keeps hitting; sanitize only
        # the text handed to retrieval and the model. The retrieval fingerprint is the
        # scope's own (its db/index paths + size/mtime), so no answer crosses scopes.
        key = answer_cache_key(gcfg, kind, model_id, question, filters, b.retrieval_sha256)
        clean = clean_question(question)

        def degraded(reason: str, pool: list, hits: list) -> dict:
            """A 200 limited-mode response: the record, a designed message, no model
            paragraph, no raw error, and never cached (N6)."""
            msg = _DEGRADE_MSG[reason].format(url=PUBLIC_URL)
            cov = coverage_of(clean, hits)
            ans = Answer(text=msg, sentences=[], verified_citations=[], unsupported=[],
                         abstained=True, coverage=cov, abstention_text=msg, generation=gen)
            out = {"answer": ans.to_dict(),
                   "evidence": evidence_rows(pool, [], {h["passage_id"] for h in hits}, b.pages_dir),
                   "degraded": {"reason": reason, "live_url": PUBLIC_URL}}
            out["answer"]["cached"] = None
            with b.lock:
                _attach_date_method(r.conn, out["evidence"])
            out["flagged"] = flags.detect(out["evidence"])
            return out

        if not clean:
            return degraded("empty", [], [])
        if not nocache:
            hit = b.cache.get(key)
            if hit is not None:
                served = copy.deepcopy(hit["response"])
                served["answer"]["cached"] = {"created_at": hit["created_at"]}
                for row in served["evidence"]:   # the offline pack may have grown since the answer was cached
                    thumb = local_page(b.pages_dir, row["item_id"], row["leaf_index"], "thumb")
                    image = local_page(b.pages_dir, row["item_id"], row["leaf_index"], "medium")
                    if thumb:
                        row["page_thumb"] = thumb
                    if image:
                        row["page_image"] = image
                    row["offline"] = bool(thumb or image)
                with b.lock:
                    _attach_date_method(r.conn, served["evidence"])
                served["flagged"] = flags.detect(served["evidence"])   # on serve, from stored evidence; not cached
                return served

        # Cache miss. Retrieve first, so the record can be shown even when the model cannot run.
        with b.lock:   # retrieval reads through r.conn
            pool, hits = retrieve_pool(r, clean, build_filters(filters), gcfg["top_k"])

        if kind == "anthropic" and b.llm is None and not _key_available():
            return degraded("no_key", pool, hits)
        if kind == "anthropic" and b.llm is None and not app.state.model_ratelimit.allow():
            return degraded("rate_limited", pool, hits)

        try:
            if b.llm is not None:
                model = b.llm
            elif kind == "stub":
                model = make_llm("stub", model_id, gcfg["max_tokens"])
            else:                                        # real provider: hard timeout, no retries (kiosk must never hang; N5: llm.py untouched)
                import anthropic
                client = anthropic.Anthropic(timeout=GEN_TIMEOUT_S, max_retries=0)
                model = AnthropicLLM(model_id, gcfg["max_tokens"], client=client, temperature=temp)
            verify = functools.partial(citation.verify_citations, r.conn)
            with b.lock:   # the LLM call and verification read through r.conn
                ans = compose(clean, hits, model, verify, min_passages=gcfg["min_passages"], generation=gen)
        except Exception:  # noqa: BLE001 - offline / timeout / provider error -> show the record, not a raw error (N6)
            return degraded("model_unreachable", pool, hits)

        result = {"answer": ans.to_dict(),
                  "evidence": evidence_rows(pool, ans.verified_citations, {h["passage_id"] for h in hits}, b.pages_dir)}
        b.cache.put(key, result)   # flagged + date_method are computed on serve below, never stored (like cached=)
        result["answer"]["cached"] = None
        with b.lock:
            _attach_date_method(r.conn, result["evidence"])
        result["flagged"] = flags.detect(result["evidence"])
        return result

    @app.get("/health")
    def health(scope: Optional[str] = None) -> dict:
        b = _bundle(scope)
        return {"status": "ok", "provider": b.provider or b.gcfg["provider"], "model": b.gcfg["model"],
                "corpus": b.corpus}

    @app.get("/scopes")
    def scopes_view() -> dict:
        """The scopes this process serves, each with its identity for the switcher: label, source
        collection with an archive.org link, and item count. 'default' is the UI landing scope
        (CIVIC_DEFAULT_SCOPE, default microlog when served, else the base)."""
        default = app.state.landing_scope   # UI landing; no-scope request routing stays on the base
        order = [default] + [n for n in app.state.bundles if n != default]
        return {"default": default, "scopes": [app.state.bundles[n].facts for n in order],
                "crisis": crisis.serialized()}

    @app.get("/examples")
    def examples(scope: Optional[str] = None) -> list[dict]:
        b = _bundle(scope)
        if not b.seed_path or not Path(b.seed_path).exists():
            return []
        out = []
        with b.lock:
            conn = b.retriever.conn
            for q in load_seed(b.seed_path):
                gold = store.gold_verdict(conn, q["qid"])
                out.append({"qid": q["qid"], "text": q["text"], "filters": q.get("filters") or {},
                            "gold": None if gold is None else ("answerable" if gold["answerable"] else "abstain")})
        return out

    @app.get("/stories")
    def stories_view(scope: Optional[str] = None) -> list[dict]:
        """Curated question + two pinned passages + caption, pins expanded to evidence rows
        (in pin order) so the compare view can render them without a retrieval pool. A scope
        with no stories file returns an empty list."""
        b = _bundle(scope)
        out = []
        with b.lock:
            r = b.retriever
            for s in b.stories:
                try:
                    rows = evidence_rows(r.lookup(s["pins"]), [], set(), b.pages_dir)
                except LookupError as exc:
                    raise HTTPException(status_code=500, detail=f"story {s['id']}: {exc}") from exc
                _attach_date_method(r.conn, rows)
                by_id = {row["passage_id"]: row for row in rows}
                # The two pins are the shown record for this story, so they are the flagging
                # basis; mark copies in_prompt for detection only, leaving the returned rows
                # unchanged. Computed on serve, never stored, exactly like the /ask flagged.
                flagged = flags.detect([{**row, "in_prompt": True} for row in rows])
                out.append({"id": s["id"], "question": s["question"], "filters": s.get("filters") or {},
                            "caption": s.get("caption", ""), "pins": [by_id[p] for p in s["pins"]],
                            "flagged": flagged})
        return out

    @app.get("/flag")
    def flag_view(pins: str = Query(""), scope: Optional[str] = None):
        """Harm-adjacent flag for a user-pinned comparison: flags.detect over exactly the
        pinned passages, treated as the shown basis, returned in the same shape /ask and
        /stories use. Read-only, computed on serve, never stored; detection and the
        crisis-line mapping stay in flags.py. A malformed or unknown id yields a safe empty
        result, never a raw error (N6)."""
        b = _bundle(scope)
        ids = [p.strip() for p in pins.split(",") if p.strip()][:2]   # the compared pair
        if not ids:
            return {"flagged": None}
        try:
            with b.lock:
                rows = evidence_rows(b.retriever.lookup(ids), [], set(), b.pages_dir)
                _attach_date_method(b.retriever.conn, rows)
        except LookupError:
            return {"flagged": None}   # unknown id -> safe empty, never a raw error
        return {"flagged": flags.detect([{**row, "in_prompt": True} for row in rows])}

    @app.get("/pages/{item_id}/{name}")
    def page_image(item_id: str, name: str):
        """A page image from the offline pack (data/cache/pages), else 404 so the client
        falls back to archive.org. Names are n<leaf>_thumb.jpg / n<leaf>_medium.jpg."""
        if "/" in item_id or "\\" in item_id or item_id in (".", "..") or not _PAGE_FILE.match(name):
            raise HTTPException(status_code=404)
        target = Path(pages_dir) / item_id / name
        if not target.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(target, media_type="image/jpeg")

    @app.get("/coverage")
    def coverage_view(q: str = Query(..., min_length=1), period: Optional[str] = None,
                      jurisdiction: Optional[str] = None, doc_type: Optional[str] = None,
                      scope: Optional[str] = None) -> dict:
        b = _bundle(scope)
        filters = _clean_filters(period, jurisdiction, doc_type)
        ck = (q, tuple(sorted(filters.items())))
        cached = b.coverage_cache.get(ck)
        if cached is not None:
            return cached
        with b.lock:
            r = b.retriever
            result = compute_coverage(r.conn, q, build_filters(filters), doc_type_families=r.cfg.active_families())
        b.coverage_cache[ck] = result
        return result

    @app.post("/ask")
    def ask_post(req: AskRequest, scope: Optional[str] = None):
        return answer(_bundle(scope), req.question, req.filters, req.provider, req.model, req.nocache)

    @app.get("/ask")
    def ask_get(q: str = Query(..., min_length=1), period: Optional[str] = None,
                jurisdiction: Optional[str] = None, doc_type: Optional[str] = None, nocache: int = 0,
                provider: Optional[str] = None, scope: Optional[str] = None):
        """Permalink form: same handler as POST, filters from query params. `provider=stub`
        exercises retrieval and the response shape without a model call (smoke tests)."""
        if provider is not None and provider not in ("stub", "anthropic"):
            raise HTTPException(status_code=422, detail="provider must be 'stub' or 'anthropic'")
        return answer(_bundle(scope), q, _clean_filters(period, jurisdiction, doc_type), provider, None, bool(nocache))

    if Path(web_dist).is_dir():
        dist = Path(web_dist)

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            # Registered after the API routes. Real files are served; anything else
            # falls back to index.html so client-side routes resolve.
            target = (dist / path).resolve() if path else dist / "index.html"
            if path and target.is_file() and dist.resolve() in target.parents:
                return FileResponse(target)
            index = dist / "index.html"
            if index.is_file():
                return FileResponse(index)
            raise HTTPException(status_code=404)

    return app


# The uvicorn entrypoint. With no CIVIC_SCOPE and no CIVIC_SERVE_SCOPES this is byte-identical
# to the pilot deploy; CIVIC_SCOPE=<name> serves one registered scope; CIVIC_SERVE_SCOPES=
# pilot,microlog serves several from one process, routed per request, the pilot default.
app = create_app(scope=os.environ.get("CIVIC_SCOPE") or None,
                 serve_scopes=parse_serve_scopes(os.environ.get(ENV_SERVE_SCOPES)))
