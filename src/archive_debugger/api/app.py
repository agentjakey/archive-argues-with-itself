"""Read-only serve layer (FastAPI). One Retriever opened at startup; every request
runs retrieve -> compose and returns the Answer plus an evidence timeline. Reuses
generate/cli.py's config loading and filter construction. Never writes civic.db.

CORS: ALLOWED_ORIGINS env (comma-separated); empty means same-origin only.
Static: serves web/dist when it exists, with index.html fallback for client routes."""
from __future__ import annotations

import functools
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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


def _allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app(config_path: Path = Path("config/pilot.toml"), *, retriever: Optional[Retriever] = None,
               provider: Optional[str] = None, llm: Optional[LLM] = None,
               seed_path: Path = DEFAULT_SEED, web_dist: Path = WEB_DIST) -> FastAPI:
    gcfg = load_generate_config(config_path)
    own_retriever = retriever is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.retriever = retriever or Retriever(config_path)
        try:
            yield
        finally:
            if own_retriever:
                app.state.retriever.close()

    app = FastAPI(title="archive-argues-with-itself", lifespan=lifespan)
    origins = _allowed_origins()
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "provider": provider or gcfg["provider"], "model": gcfg["model"]}

    @app.get("/examples")
    def examples() -> list[dict]:
        if not Path(seed_path).exists():
            return []
        conn = app.state.retriever.conn
        out = []
        for q in load_seed(seed_path):
            gold = store.gold_verdict(conn, q["qid"])
            out.append({"qid": q["qid"], "text": q["text"], "filters": q.get("filters") or {},
                        "gold": None if gold is None else ("answerable" if gold["answerable"] else "abstain")})
        return out

    @app.post("/ask")
    def ask(req: AskRequest) -> dict:
        r = app.state.retriever
        kind = req.provider or provider or gcfg["provider"]
        model_id = req.model or gcfg["model"]
        temp = sent_temperature(kind, gcfg)
        hits = r.search(req.question, filters=build_filters(req.filters), top_k=gcfg["top_k"])
        model = llm or make_llm(kind, model_id, gcfg["max_tokens"], temperature=temp)
        verify = functools.partial(citation.verify_citations, r.conn)
        gen = generation_meta(provider=kind, model=model_id, temperature=temp,
                              max_tokens=gcfg["max_tokens"], top_k=gcfg["top_k"])
        ans = compose(req.question, hits, model, verify, min_passages=gcfg["min_passages"], generation=gen)
        return {"answer": ans.to_dict(), "evidence": evidence_rows(hits, ans.verified_citations)}

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
