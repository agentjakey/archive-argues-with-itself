"""Turning a draft reply into a round in the deck format. Nothing here decides whether a round is
good: the builder's checks, the panel and the reviewer do. A reply that names a quote the page does
not carry still becomes a round, so the builder refuses it on the record."""
from __future__ import annotations

import hashlib
import re

from archive_debugger.exhibit import prompts

# Years and year ranges hidden on a When Was This? card: 1975, 1975-76, 1975/1976.
YEAR_SPAN = re.compile(r"(?<![0-9])(1[89][0-9]{2}|20[0-2][0-9])(?:\s?[-/]\s?[0-9]{2,4})?(?![0-9])")


def round_id(mode: str, refs: list) -> str:
    prefix = {"same_or_not": "son", "when_was_this": "wwt", "time_dial": "dial"}[mode]
    return f"{prefix}-" + hashlib.sha256("|".join(refs).encode("utf-8")).hexdigest()[:10]


def year_spans(text: str) -> list:
    return [[m.start(), m.end()] for m in YEAR_SPAN.finditer(text or "")]


def _provenance(model: str, prompt_version: str, drafted_at: str) -> dict:
    return {"drafted_by": model, "prompt_version": prompt_version, "drafted_at": drafted_at,
            "draft_kind": "model-drafted", "edits": []}


def when_round(page: dict, reply: dict, *, model: str, drafted_at: str, prompt_version: str = prompts.WHEN_VERSION) -> dict:
    quotes = [{"id": f"c{n}", "page_ref": page["ref"], "role": "clue", "text": text}
              for n, text in enumerate(reply.get("clues") or [], 1)]
    return {
        "id": round_id("when_was_this", [page["ref"]]),
        "mode": "when_was_this",
        "level": 1,
        "collection": page["collection"],
        "pages": [page],
        "quotes": quotes,
        "play": {"year": (page.get("catalogue_date") or {}).get("year"),
                 "label": {"en": reply.get("label_en", ""), "fr": reply.get("label_fr", "")},
                 "clues": [q["id"] for q in quotes],
                 "masked_text": year_spans(page.get("text")),
                 "masked_title": year_spans(page.get("title"))},
        "explanation": {"en": reply.get("explanation_en", ""), "fr": reply.get("explanation_fr", "")},
        "explanation_status": "model-drafted",
        "care_flags": [],
        "status": "draft",
        "review": {},
        "provenance": _provenance(model, prompt_version, drafted_at),
    }


def same_round(pair: dict, page_a: dict, page_b: dict, reply: dict, *, model: str, drafted_at: str,
               prompt_version: str = prompts.SAME_VERSION) -> dict:
    refs = {"A": page_a["ref"], "B": page_b["ref"]}
    quotes = [{"id": "a1", "page_ref": page_a["ref"], "role": "claim", "text": reply.get("quote_a", "")},
              {"id": "b1", "page_ref": page_b["ref"], "role": "claim", "text": reply.get("quote_b", "")}]
    decisive = []
    for n, d in enumerate(reply.get("decisive") or [], 1):
        qid = f"d{n}"
        quotes.append({"id": qid, "page_ref": refs.get(d.get("page"), page_a["ref"]), "role": "decisive",
                       "text": d.get("quote", "")})
        decisive.append(qid)
    return {
        "id": round_id("same_or_not", [page_a["ref"], page_b["ref"]]),
        "mode": "same_or_not",
        "level": 2,
        "collection": page_a["collection"],
        "pages": [page_a, page_b],
        "quotes": quotes,
        "play": {"claims": [{"page_ref": page_a["ref"], "quote": "a1",
                             "text": {"en": reply.get("claim_a_en", ""), "fr": reply.get("claim_a_fr", "")}},
                            {"page_ref": page_b["ref"], "quote": "b1",
                             "text": {"en": reply.get("claim_b_en", ""), "fr": reply.get("claim_b_fr", "")}}],
                 "answer": reply.get("answer"),
                 "decisive": decisive,
                 "constraints": reply.get("constraints") or {},
                 "mined_as": {"phrase": pair.get("phrase"), "kind": pair.get("kind")}},
        "explanation": {"en": reply.get("explanation_en", ""), "fr": reply.get("explanation_fr", "")},
        "explanation_status": "model-drafted",
        "care_flags": [],
        "status": "draft",
        "review": {},
        "provenance": _provenance(model, prompt_version, drafted_at),
    }


def dial_round(question: dict, pool: list, epochs: list, *, model: str, drafted_at: str, extra: dict,
               prompt_version: str = prompts.DIAL_VERSION) -> dict:
    """question: {"id", "en", "fr", "jurisdiction"}; pool: page records with their years; epochs:
    [{"year", "reply", "pages": [page records shown to the writer, in order]}]."""
    quotes, out_epochs = [], []
    for e in epochs:
        reply = e["reply"]
        qids = []
        for n, q in enumerate(reply.get("quotes") or [], 1):
            idx = int(q.get("page", 0)) - 1
            if not 0 <= idx < len(e["pages"]):
                continue
            qid = f"y{e['year']}q{n}"
            quotes.append({"id": qid, "page_ref": e["pages"][idx]["ref"], "role": "evidence", "text": q.get("quote", "")})
            qids.append(qid)
        out_epochs.append({"year": int(e["year"]), "state": reply.get("state", "insufficient"),
                           "answer": {"en": reply.get("answer_en", ""), "fr": reply.get("answer_fr", "")},
                           "quotes": qids, "pages_by_then": [p["ref"] for p in e["pages"]]})
    return {
        "id": "dial-" + question["id"],
        "mode": "time_dial",
        "level": 1,
        "collection": pool[0]["collection"] if pool else "",
        "pages": pool,
        "quotes": quotes,
        "play": {"question": {"en": question["en"], "fr": question["fr"]},
                 "question_id": question["id"],
                 "jurisdiction": question.get("jurisdiction"),
                 "epochs": out_epochs, **extra},
        "explanation": {"en": question.get("note_en", ""), "fr": question.get("note_fr", "")},
        "explanation_status": "author-reviewed" if question.get("note_en") else "model-drafted",
        "care_flags": [],
        "status": "draft",
        "review": {},
        "provenance": _provenance(model, prompt_version, drafted_at),
    }
