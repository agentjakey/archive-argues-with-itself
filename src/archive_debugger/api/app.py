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

from archive_debugger import flags
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
SNIPPET = 300
_PAGE_FILE = re.compile(r"^n(\d+)_(thumb|medium)\.jpg$")

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
    mn, mx = conn.execute("SELECT MIN(year), MAX(year) FROM items WHERE dated = 1").fetchone()
    return {
        "items": items,
        "passages": passages,
        "passages_undated": undated,
        "undated_share": round(undated / passages, 4) if passages else 0.0,
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


def create_app(config_path: Path = Path("config/pilot.toml"), *, retriever: Optional[Retriever] = None,
               provider: Optional[str] = None, llm: Optional[LLM] = None,
               seed_path: Path = DEFAULT_SEED, web_dist: Path = WEB_DIST, load_env: bool = True,
               cache_path: Optional[Path] = None, pages_dir: Optional[Path] = None,
               stories_path: Path = DEFAULT_STORIES) -> FastAPI:
    if load_env:
        from dotenv import load_dotenv
        load_dotenv()
    cache_path = cache_path or env_path(ENV_CACHE_PATH, DEFAULT_CACHE)
    pages_dir = pages_dir or env_path(ENV_PAGES_DIR, DEFAULT_PAGES)
    stories = load_stories(stories_path)
    gcfg = load_generate_config(config_path)
    pilot_window = _pilot_window(config_path)
    own_retriever = retriever is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.retriever = retriever or Retriever(config_path)
        app.state.lock = threading.Lock()   # one sqlite connection; sync endpoints run in a threadpool
        app.state.cache = AnswerCache(cache_path)
        app.state.coverage_cache = {}
        app.state.model_ratelimit = RateLimiter(RATE_BURST, RATE_REFILL)
        app.state.retrieval_sha256 = retrieval_fingerprint(app.state.retriever.cfg)
        with app.state.lock:
            app.state.corpus = corpus_facts(app.state.retriever.conn, pilot_window)
        try:
            yield
        finally:
            app.state.cache.close()
            if own_retriever:
                app.state.retriever.close()

    app = FastAPI(title="archive-argues-with-itself", lifespan=lifespan)
    origins = _allowed_origins()
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

    def answer(question: str, filters: Optional[dict], req_provider: Optional[str], req_model: Optional[str],
               nocache: bool):
        r = app.state.retriever
        kind = req_provider or provider or gcfg["provider"]
        model_id = req_model or gcfg["model"]
        temp = sent_temperature(kind, gcfg)
        gen = generation_meta(provider=kind, model=model_id, temperature=temp,
                              max_tokens=gcfg["max_tokens"], top_k=gcfg["top_k"])
        # Key on the ORIGINAL text so every warmed answer keeps hitting; sanitize only
        # the text handed to retrieval and the model.
        key = answer_cache_key(gcfg, kind, model_id, question, filters, app.state.retrieval_sha256)
        clean = clean_question(question)

        def degraded(reason: str, pool: list, hits: list) -> dict:
            """A 200 limited-mode response: the record, a designed message, no model
            paragraph, no raw error, and never cached (N6)."""
            msg = _DEGRADE_MSG[reason].format(url=PUBLIC_URL)
            cov = coverage_of(clean, hits)
            ans = Answer(text=msg, sentences=[], verified_citations=[], unsupported=[],
                         abstained=True, coverage=cov, abstention_text=msg, generation=gen)
            out = {"answer": ans.to_dict(),
                   "evidence": evidence_rows(pool, [], {h["passage_id"] for h in hits}, pages_dir),
                   "degraded": {"reason": reason, "live_url": PUBLIC_URL}}
            out["answer"]["cached"] = None
            out["flagged"] = flags.detect(out["evidence"])
            return out

        if not clean:
            return degraded("empty", [], [])
        if not nocache:
            hit = app.state.cache.get(key)
            if hit is not None:
                served = copy.deepcopy(hit["response"])
                served["answer"]["cached"] = {"created_at": hit["created_at"]}
                for row in served["evidence"]:   # the offline pack may have grown since the answer was cached
                    thumb = local_page(pages_dir, row["item_id"], row["leaf_index"], "thumb")
                    image = local_page(pages_dir, row["item_id"], row["leaf_index"], "medium")
                    if thumb:
                        row["page_thumb"] = thumb
                    if image:
                        row["page_image"] = image
                    row["offline"] = bool(thumb or image)
                served["flagged"] = flags.detect(served["evidence"])   # on serve, from stored evidence; not cached
                return served

        # Cache miss. Retrieve first, so the record can be shown even when the model cannot run.
        with app.state.lock:   # retrieval reads through r.conn
            pool, hits = retrieve_pool(r, clean, build_filters(filters), gcfg["top_k"])

        if kind == "anthropic" and llm is None and not _key_available():
            return degraded("no_key", pool, hits)
        if kind == "anthropic" and llm is None and not app.state.model_ratelimit.allow():
            return degraded("rate_limited", pool, hits)

        try:
            if llm is not None:
                model = llm
            elif kind == "stub":
                model = make_llm("stub", model_id, gcfg["max_tokens"])
            else:                                        # real provider: hard timeout, no retries (kiosk must never hang; N5: llm.py untouched)
                import anthropic
                client = anthropic.Anthropic(timeout=GEN_TIMEOUT_S, max_retries=0)
                model = AnthropicLLM(model_id, gcfg["max_tokens"], client=client, temperature=temp)
            verify = functools.partial(citation.verify_citations, r.conn)
            with app.state.lock:   # the LLM call and verification read through r.conn
                ans = compose(clean, hits, model, verify, min_passages=gcfg["min_passages"], generation=gen)
        except Exception:  # noqa: BLE001 - offline / timeout / provider error -> show the record, not a raw error (N6)
            return degraded("model_unreachable", pool, hits)

        result = {"answer": ans.to_dict(),
                  "evidence": evidence_rows(pool, ans.verified_citations, {h["passage_id"] for h in hits}, pages_dir)}
        app.state.cache.put(key, result)   # flagged is computed on serve below, never stored (like cached=)
        result["answer"]["cached"] = None
        result["flagged"] = flags.detect(result["evidence"])
        return result

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "provider": provider or gcfg["provider"], "model": gcfg["model"],
                "corpus": app.state.corpus}

    @app.get("/examples")
    def examples() -> list[dict]:
        if not Path(seed_path).exists():
            return []
        out = []
        with app.state.lock:
            conn = app.state.retriever.conn
            for q in load_seed(seed_path):
                gold = store.gold_verdict(conn, q["qid"])
                out.append({"qid": q["qid"], "text": q["text"], "filters": q.get("filters") or {},
                            "gold": None if gold is None else ("answerable" if gold["answerable"] else "abstain")})
        return out

    @app.get("/stories")
    def stories_view() -> list[dict]:
        """Curated question + two pinned passages + caption, pins expanded to evidence rows
        (in pin order) so the compare view can render them without a retrieval pool."""
        out = []
        with app.state.lock:
            r = app.state.retriever
            for s in stories:
                try:
                    rows = evidence_rows(r.lookup(s["pins"]), [], set(), pages_dir)
                except LookupError as exc:
                    raise HTTPException(status_code=500, detail=f"story {s['id']}: {exc}") from exc
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
    def flag_view(pins: str = Query("")):
        """Harm-adjacent flag for a user-pinned comparison: flags.detect over exactly the
        pinned passages, treated as the shown basis, returned in the same shape /ask and
        /stories use. Read-only, computed on serve, never stored; detection and the
        crisis-line mapping stay in flags.py. A malformed or unknown id yields a safe empty
        result, never a raw error (N6)."""
        ids = [p.strip() for p in pins.split(",") if p.strip()][:2]   # the compared pair
        if not ids:
            return {"flagged": None}
        try:
            with app.state.lock:
                rows = evidence_rows(app.state.retriever.lookup(ids), [], set(), pages_dir)
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
                      jurisdiction: Optional[str] = None, doc_type: Optional[str] = None) -> dict:
        filters = _clean_filters(period, jurisdiction, doc_type)
        ck = (q, tuple(sorted(filters.items())))
        cached = app.state.coverage_cache.get(ck)
        if cached is not None:
            return cached
        with app.state.lock:
            r = app.state.retriever
            result = compute_coverage(r.conn, q, build_filters(filters), doc_type_families=r.cfg.active_families())
        app.state.coverage_cache[ck] = result
        return result

    @app.post("/ask")
    def ask_post(req: AskRequest):
        return answer(req.question, req.filters, req.provider, req.model, req.nocache)

    @app.get("/ask")
    def ask_get(q: str = Query(..., min_length=1), period: Optional[str] = None,
                jurisdiction: Optional[str] = None, doc_type: Optional[str] = None, nocache: int = 0,
                provider: Optional[str] = None):
        """Permalink form: same handler as POST, filters from query params. `provider=stub`
        exercises retrieval and the response shape without a model call (smoke tests)."""
        if provider is not None and provider not in ("stub", "anthropic"):
            raise HTTPException(status_code=422, detail="provider must be 'stub' or 'anthropic'")
        return answer(q, _clean_filters(period, jurisdiction, doc_type), provider, None, bool(nocache))

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


app = create_app()
