"""Phase 7 labeling assist. Pre-analyzes the corpus and writes an ADVISORY
worksheet of proposed labels for Jacob Ortiz to review. Proposals are a deterministic,
transparent triage heuristic -- never an LLM, never a retrieval score -- and are
CANDIDATE VALUES ONLY. This command never writes to eval_labels or
eval_question_gold; only Jacob Ortiz's keypresses (eval.label --from-worksheet) become
gold (N2, N4)."""
from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path

from archive_debugger.eval import store
from archive_debugger.ingest import db
from archive_debugger.ingest.ocr import quality_bucket

OUT_DEFAULT = Path("reports/phase7/label_worksheet.jsonl")
COVERED = {"ontario", "alberta", "federal"}

# Dropped from salient-term overlap: question scaffolding plus corpus-ubiquitous
# topic/jurisdiction words that match almost everything (so are non-discriminative).
_STOP = {
    "what", "which", "how", "why", "did", "do", "does", "was", "were", "the", "and",
    "for", "about", "with", "from", "that", "this", "into", "over", "report", "reports",
    "reporting", "describe", "described", "say", "said", "authorities", "authority",
    "health", "public", "healthcare", "program", "programs", "policy", "policies",
    "between", "change", "changed", "differ", "shift", "shifted", "provincial",
    "federal", "canada", "canadian", "ontario", "alberta", "toronto", "edmonton",
    "calgary", "ottawa", "quebec", "british", "columbia", "nunavut", "structure",
    "recommend", "recommended", "concern", "concerns", "issues",
}
_JUR_WORDS = {
    "british columbia": "bc", "nunavut": "nunavut", "quebec": "quebec",
    "ontario": "ontario", "toronto": "ontario", "hamilton": "ontario",
    "alberta": "alberta", "edmonton": "alberta", "calgary": "alberta",
    "federal": "federal", "ottawa": "federal", "canada": "federal",
}
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_YEAR = re.compile(r"\b(1[89]\d\d|20[0-2]\d)\b")


def salient_terms(text: str) -> list[str]:
    return [t for t in _WORD.findall(text.lower())
            if len(t) >= 4 and not t.isdigit() and t not in _STOP]


def question_jurisdiction(q: dict):
    f = json.loads(q.get("filters_json") or "{}")
    if f.get("jurisdiction"):
        return f["jurisdiction"]
    tl = q.get("text", "").lower()
    for w, j in _JUR_WORDS.items():
        if w in tl:
            return j
    return None


def period_problem(text: str, end_year: int):
    years = [int(y) for y in _YEAR.findall(text)]
    if years and all(y > end_year for y in years):
        return "period after archive window; not covered"
    if years and all(y < 1930 for y in years):
        return "very early period; archive is thin here"
    return None


def _cap(reason: str, n: int = 15) -> str:
    return " ".join(reason.split()[:n])


def propose_candidate(hit, q_terms, q_jur, period_prob) -> tuple[int, str]:
    """Conservative: topic match alone is not relevant; wrong jurisdiction/period
    or OCR garbage is not relevant; when the excerpt does not clearly answer,
    propose 0."""
    if quality_bucket(float(hit.get("ocr_quality") or 0.0)) == "low":
        return 0, "low OCR quality, likely garbage"
    if period_prob:
        return 0, period_prob
    if q_jur:
        if q_jur not in COVERED:
            return 0, _cap(f"jurisdiction {q_jur} not covered by the archive")
        cj = hit.get("jurisdiction")
        if cj and cj != q_jur:
            return 0, _cap(f"candidate is {cj}, question scoped to {q_jur}")
    ex = (hit.get("text") or "").lower()
    found = sorted(t for t in q_terms if t in ex)
    if len(found) >= 2:
        return 1, _cap("excerpt mentions " + ", ".join(found[:4]) + "; on topic and in scope")
    return 0, "excerpt does not clearly address the question"


def _excerpt(text: str) -> str:
    return " ".join((text or "").split())[:280]


def build_records(q: dict, hits: list[dict], end_year: int) -> list[dict]:
    q_terms = set(salient_terms(q.get("text", "")))
    q_jur = question_jurisdiction(q)
    period_prob = period_problem(q.get("text", ""), end_year)
    candidates = []
    any_relevant = False
    for rank, h in enumerate(hits, start=1):
        rel, reason = propose_candidate(h, q_terms, q_jur, period_prob)
        any_relevant = any_relevant or bool(rel)
        candidates.append({
            "kind": "candidate", "qid": q["qid"], "passage_id": h["passage_id"], "rank": rank,
            "year": h.get("year"), "jurisdiction": h.get("jurisdiction"), "doc_type": h.get("doc_type"),
            "ocr_quality": h.get("ocr_quality"), "title": h.get("title"),
            "leaf_index": h.get("leaf_index"), "printed_page": h.get("printed_page"),
            "deep_link": h.get("page_deep_link"), "excerpt": _excerpt(h.get("text")),
            "proposed_relevance": rel, "reason": reason,
        })
    summary = {
        "kind": "summary", "qid": q["qid"], "text": q.get("text"), "qtype": q.get("qtype"),
        "filters": json.loads(q.get("filters_json") or "{}"),
        "proposed_answerable": 1 if any_relevant else 0,
        "reason": ("at least one candidate appears on-topic and in-scope" if any_relevant
                   else "no candidate clearly answers; propose should-abstain"),
    }
    return [summary] + candidates


def _eval_cfg(config_path):
    with Path(config_path).open("rb") as fh:
        raw = tomllib.load(fh)
    return (int(raw.get("eval", {}).get("label_top_n", 30)),
            int(raw.get("corpus", {}).get("window", {}).get("end_year", 2009)))


def run(config_path=None, *, conn=None, retriever=None, top_n=None, end_year=2009, out_path=None) -> Path:
    own_conn = conn is None
    if own_conn:
        conn = db.init_db(db.resolve_db_path(config_path))
    if config_path is not None:
        cfg_top_n, end_year = _eval_cfg(config_path)
        top_n = top_n or cfg_top_n
    top_n = top_n or 30
    own_retriever = retriever is None
    if own_retriever:
        from archive_debugger.retrieve.search import Retriever  # lazy: no fastembed at import
        retriever = Retriever(config_path)
    from archive_debugger.eval.label import filters_from  # reuse the same Filters mapping
    out_path = Path(out_path) if out_path else OUT_DEFAULT
    try:
        records = []
        for q in store.list_questions(conn):
            hits = retriever.search(q["text"], filters=filters_from(q), top_k=top_n)
            records.extend(build_records(q, hits, end_year))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    finally:
        if own_retriever:
            retriever.close()
        if own_conn:
            conn.close()
    return out_path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Pre-analyze the corpus into an advisory label worksheet.")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--out", default=None, type=Path)
    args = p.parse_args(argv)
    out = run(args.config, out_path=args.out)
    print(f"wrote advisory worksheet -> {out} "
          f"(proposals are candidate-only; review with eval.label --from-worksheet)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
