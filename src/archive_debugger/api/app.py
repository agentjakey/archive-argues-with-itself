"""Read-only serve layer (FastAPI). One Retriever opened at startup; every request
runs retrieve -> compose and returns the Answer plus an evidence timeline. Reuses
generate/cli.py's config loading and filter construction. Never writes civic.db.

CORS: ALLOWED_ORIGINS env (comma-separated); empty means same-origin only.
Static: serves web/dist when it exists, with index.html fallback for client routes.
.env: loaded here (the API is outside generate/, so generate/ hermeticity is
unchanged); load_dotenv never overrides variables already set in the environment."""
from __future__ import annotations

import functools
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from archive_debugger.eval import store
from archive_debugger.eval.questions import load_seed
from archive_debugger.generate.answer import compose, generation_meta
from archive_debugger.generate.cli import build_filters, load_generate_config, sent_temperature
from archive_debugger.generate.llm import LLM, make_llm
from archive_debugger.retrieve import citation
from archive_debugger.retrieve.search import Retriever

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_DIST = REPO_ROOT / "web" / "dist"
DEFAULT_SEED = Path("eval/seed_questions.jsonl")
SNIPPET = 300
MISSING_KEY = "ANTHROPIC_API_KEY is not set on the server"


class AskRequest(BaseModel):
    question: str
    filters: Optional[dict] = None
    provider: Optional[str] = None
    model: Optional[str] = None


def evidence_rows(hits: list[dict], verified: list[dict]) -> list[dict]:
    cited_ids = {c["passage_id"] for c in verified}
    ordered = sorted(hits, key=lambda h: (h.get("year") is None, h.get("year") or 0))  # undated last
    return [{
        "passage_id": h["passage_id"], "item_id": h["item_id"], "title": h.get("title"),
        "year": h.get("year"), "decade": h.get("decade"), "jurisdiction": h.get("jurisdiction"),
        "doc_type": h.get("doc_type"), "leaf_index": h["leaf_index"], "printed_page": h.get("printed_page"),
        "deep_link": h["page_deep_link"],
        "page_thumb": citation.page_thumb(h["item_id"], h["leaf_index"]),
        "page_image": citation.page_image(h["item_id"], h["leaf_index"]),
        "embed_url": citation.embed_url(h["item_id"], h["leaf_index"]),
        "snippet": " ".join((h.get("text") or "").split())[:SNIPPET],
        "bm25_rank": h.get("bm25_rank"), "dense_rank": h.get("dense_rank"),
        "cited": h["passage_id"] in cited_ids,
    } for h in ordered]


def corpus_facts(conn) -> dict:
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
        "window": {"min_year": mn, "max_year": mx},
    }


def _allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip()]


def _key_available() -> bool:
    # The SDK also honors ANTHROPIC_AUTH_TOKEN; an `ant auth` profile on disk is not
    # detected here and would be reported as missing.
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def create_app(config_path: Path = Path("config/pilot.toml"), *, retriever: Optional[Retriever] = None,
               provider: Optional[str] = None, llm: Optional[LLM] = None,
               seed_path: Path = DEFAULT_SEED, web_dist: Path = WEB_DIST, load_env: bool = True) -> FastAPI:
    if load_env:
        from dotenv import load_dotenv
        load_dotenv()
    gcfg = load_generate_config(config_path)
    own_retriever = retriever is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.retriever = retriever or Retriever(config_path)
        app.state.lock = threading.Lock()   # one sqlite connection; sync endpoints run in a threadpool
        with app.state.lock:
            app.state.corpus = corpus_facts(app.state.retriever.conn)
        try:
            yield
        finally:
            if own_retriever:
                app.state.retriever.close()

    app = FastAPI(title="archive-argues-with-itself", lifespan=lifespan)
    origins = _allowed_origins()
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

    def answer(question: str, filters: Optional[dict], req_provider: Optional[str], req_model: Optional[str]):
        r = app.state.retriever
        kind = req_provider or provider or gcfg["provider"]
        model_id = req_model or gcfg["model"]
        temp = sent_temperature(kind, gcfg)
        if kind == "anthropic" and llm is None and not _key_available():
            return JSONResponse(status_code=503, content={"error": MISSING_KEY})
        model = llm or make_llm(kind, model_id, gcfg["max_tokens"], temperature=temp)
        gen = generation_meta(provider=kind, model=model_id, temperature=temp,
                              max_tokens=gcfg["max_tokens"], top_k=gcfg["top_k"])
        with app.state.lock:   # retrieval, the LLM call, and verification all read through r.conn
            hits = r.search(question, filters=build_filters(filters), top_k=gcfg["top_k"])
            verify = functools.partial(citation.verify_citations, r.conn)
            try:
                ans = compose(question, hits, model, verify, min_passages=gcfg["min_passages"], generation=gen)
            except Exception as exc:  # noqa: BLE001 - surfaced verbatim, never swallowed
                return JSONResponse(status_code=502, content={"error": f"{type(exc).__name__}: {exc}"})
        return {"answer": ans.to_dict(), "evidence": evidence_rows(hits, ans.verified_citations)}

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

    @app.post("/ask")
    def ask_post(req: AskRequest):
        return answer(req.question, req.filters, req.provider, req.model)

    @app.get("/ask")
    def ask_get(q: str = Query(..., min_length=1), period: Optional[str] = None,
                jurisdiction: Optional[str] = None, doc_type: Optional[str] = None):
        """Permalink form: same handler as POST, filters from query params."""
        filters = {k: v for k, v in (("period", period), ("jurisdiction", jurisdiction), ("doc_type", doc_type)) if v}
        return answer(q, filters, None, None)

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
