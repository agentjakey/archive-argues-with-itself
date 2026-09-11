"""Compose a cited answer or abstain. Two abstentions, both decided by code:
(1) thin evidence by QUESTION-TERM COVERAGE before any model call; (2) no sentence
survived the 3-check citation verifier. Failing or uncited sentences are dropped and
listed.

Thinness rule (fixed a priori, not tuned on eval labels): tokenize the question with
the same tokenizer as the FTS leg; a salient term is a non-stopword token of length
>= 3 or a 4-digit number; a term is covered if any retrieved passage contains an
equal token or (for terms of length >= 5) a token sharing its first 5 characters.
Thin if any salient term is uncovered, or fewer than min_passages were retrieved.

Amended once after sweep 1 (stoplist criteria a/b, plural stemming, year/decade
coverage); frozen thereafter."""
from __future__ import annotations

import hashlib
import inspect
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

from archive_debugger.generate.llm import LLM
from archive_debugger.generate.prompt import SYSTEM, build_user_prompt

ABSTAIN_THIN = (
    "the record here is thin: no retrieved passage mentions {uncovered} "
    "({n_undated} of {n_passages} retrieved passages are undated)"
)
ABSTAIN_UNVERIFIED = "no claim in the retrieved passages survived citation verification"
ABSTAIN_UNCITED = "the retrieved passages did not yield any cited claim"

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)   # same tokenizer as retrieve.search._fts_query
_YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
_PAGE = re.compile(r"\b(?:p\.|page)\s*(\d+)\b", re.IGNORECASE)
_DECADE = re.compile(r"^\d{3}0s$")            # e.g. 1980s
PREFIX = 5

# Fixed English stopwords: articles, conjunctions, prepositions, pronouns,
# auxiliaries, question words. Deliberately no domain words.
_STOP_FUNCTION = frozenset({
    "a", "an", "the",
    "and", "or", "but", "if", "so", "than", "as", "not", "no",
    "of", "to", "in", "on", "at", "by", "for", "from", "with", "about", "into",
    "over", "under", "between", "through", "during", "before", "after",
    "i", "me", "my", "we", "our", "you", "your", "he", "him", "his", "she", "her",
    "it", "its", "they", "them", "their", "this", "that", "these", "those",
    "is", "are", "was", "were", "be", "been", "being", "do", "does", "did",
    "have", "has", "had", "will", "would", "shall", "should", "can", "could",
    "may", "might", "must",
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
})
# Amendment, made once after sweep 1. Criterion (a): verbs and nouns that describe
# the act of asking or the form of the answer, not the subject matter.
_STOP_ASKING = frozenset({
    "describe", "explain", "discuss", "compare", "conclude", "conclusion", "conclusions",
    "recommend", "recommendation", "recommendations", "report", "reported", "state",
    "stated", "say", "said", "address", "addressed", "identify", "shift", "shifted",
    "change", "changed", "evolve", "evolved", "differ", "differed",
})
# Criterion (b): generic actor nouns that name who acted, not what was done.
_STOP_ACTORS = frozenset({
    "authorities", "authority", "officials", "government", "governments",
    "department", "departments", "ministry", "agency", "agencies",
})
STOPWORDS = _STOP_FUNCTION | _STOP_ASKING | _STOP_ACTORS


def tokens(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def salient_terms(question: str) -> list[str]:
    out = []
    for t in tokens(question):
        if t in STOPWORDS:
            continue
        if len(t) >= 3 or (t.isdigit() and len(t) == 4):
            if t not in out:
                out.append(t)
    return out


def _stem(t: str) -> str:
    """Crude plural stemming: strip one trailing 's' when the token is longer than 3."""
    return t[:-1] if len(t) > 3 and t.endswith("s") else t


def allowed_years(hits: list[dict]) -> set[str]:
    """Same allowed-year set the fact-leak guard uses: years in any hit's text UNION
    any hit's metadata year."""
    years = {str(h["year"]) for h in hits if h.get("year") is not None}
    for h in hits:
        years.update(_YEAR.findall(h.get("text") or ""))
    return years


def uncovered_terms(question: str, hits: list[dict]) -> list[str]:
    raw: set[str] = set()
    for h in hits:
        raw.update(tokens(h.get("text")))
    stemmed = {_stem(t) for t in raw}
    prefixes = {p[:PREFIX] for p in stemmed if len(p) >= PREFIX}
    years = allowed_years(hits)
    missing = []
    for term in salient_terms(question):
        if _DECADE.match(term):                          # decade: verbatim token, or any allowed year in it
            if term in raw or any(y[:3] == term[:3] for y in years):
                continue
        elif term.isdigit() and len(term) == 4:          # year: in text or metadata
            if term in years:
                continue
        else:                                            # word: stem, then equality or prefix
            s = _stem(term)
            if s in stemmed or (len(s) >= PREFIX and s[:PREFIX] in prefixes):
                continue
        missing.append(term)
    return missing


@dataclass
class Coverage:
    n_items: int
    n_passages: int
    n_undated: int
    periods: dict
    jurisdictions: dict
    salient_terms: list = field(default_factory=list)
    uncovered_terms: list = field(default_factory=list)
    single_source: bool = False      # UI flag only; never an abstention


@dataclass
class Answer:
    text: str
    sentences: list[dict]
    verified_citations: list[dict]
    unsupported: list[dict]
    abstained: bool
    coverage: Coverage
    abstention_text: Optional[str] = None
    generation: dict = field(default_factory=dict)   # provider/model/temperature/prompt_sha256/max_tokens/top_k

    def to_dict(self) -> dict:
        return asdict(self)


def prompt_material() -> str:
    """Everything that shapes the prompt: the SYSTEM text plus the source of the
    user-prompt template, so a template change alters prompt_sha256."""
    return SYSTEM + inspect.getsource(build_user_prompt)


def generation_meta(*, provider: str, model: str, temperature: float, max_tokens: int, top_k: int) -> dict:
    """Run metadata attached to every Answer (abstentions included)."""
    return {"provider": provider, "model": model, "temperature": temperature,
            "prompt_sha256": hashlib.sha256(prompt_material().encode("utf-8")).hexdigest(),
            "max_tokens": max_tokens, "top_k": top_k}


def coverage_of(question: str, hits: list[dict]) -> Coverage:
    items = {h["item_id"] for h in hits}
    return Coverage(
        n_items=len(items),
        n_passages=len(hits),
        n_undated=sum(1 for h in hits if not h.get("dated")),
        periods=dict(Counter(str(h.get("decade") or "undated") for h in hits)),
        jurisdictions=dict(Counter(str(h.get("jurisdiction") or "unknown") for h in hits)),
        salient_terms=salient_terms(question),
        uncovered_terms=uncovered_terms(question, hits),
        single_source=(len(items) == 1),
    )


def is_thin(cov: Coverage, *, min_passages: int) -> bool:
    return bool(cov.uncovered_terms) or cov.n_passages < min_passages


def _citation_dict(h: dict) -> dict:
    return {"passage_id": h["passage_id"], "item_id": h["item_id"], "leaf_index": h["leaf_index"],
            "printed_page": h.get("printed_page"), "deep_link": h["page_deep_link"]}


def _leaks_facts(text: str, cited: list[dict]) -> bool:
    # Allowed years: cited items' metadata years UNION years occurring in the cited
    # passages' own text. Allowed pages: cited printed labels and leaf indexes.
    years = {str(h["year"]) for h in cited if h.get("year") is not None}
    for h in cited:
        years.update(_YEAR.findall(h.get("text") or ""))
    pages = {str(h["printed_page"]) for h in cited if h.get("printed_page")} | {str(h["leaf_index"]) for h in cited}
    if any(y not in years for y in _YEAR.findall(text)):
        return True
    return any(p not in pages for p in _PAGE.findall(text))


def _abstain(msg: str, cov: Coverage, unsupported: list[dict], generation: Optional[dict]) -> "Answer":
    return Answer(text=msg, sentences=[], verified_citations=[], unsupported=unsupported,
                  abstained=True, coverage=cov, abstention_text=msg, generation=generation or {})


def compose(question: str, hits: list[dict], llm: LLM, verify: Callable, *,
            min_passages: int, generation: Optional[dict] = None) -> Answer:
    cov = coverage_of(question, hits)
    if is_thin(cov, min_passages=min_passages):
        uncovered = ", ".join(cov.uncovered_terms) if cov.uncovered_terms else "the question's terms"
        return _abstain(ABSTAIN_THIN.format(uncovered=uncovered, n_undated=cov.n_undated,
                                            n_passages=cov.n_passages), cov, [], generation)

    retrieved_ids = [h["passage_id"] for h in hits]
    by_id = {h["passage_id"]: h for h in hits}
    draft = llm.draft(SYSTEM, build_user_prompt(question, hits))

    kept, unsupported, verified = [], [], {}
    reached_verifier = False   # did any cited sentence reach the 3-check verifier?
    for s in draft.sentences:
        cited = list(dict.fromkeys(s.cited_ids))  # dedupe, order-preserving
        row = {"text": s.text, "cited_ids": cited}
        if not cited:
            unsupported.append({**row, "reason": "no citation"})
            continue
        reached_verifier = True
        failed = sorted({c.passage_id for c in verify(cited, retrieved_ids) if not c.ok})
        if failed:
            unsupported.append({**row, "reason": f"citation failed verification: {failed}"})
            continue
        cited_hits = [by_id[i] for i in cited]
        if _leaks_facts(s.text, cited_hits):
            unsupported.append({**row, "reason": "mentions a year or page not in the cited passages"})
            continue
        kept.append(row)
        for h in cited_hits:
            verified[h["passage_id"]] = _citation_dict(h)

    if not kept:
        # UNVERIFIED: cited sentences reached the verifier and none survived.
        # UNCITED: nothing reached the verifier (all sentences uncited, or a zero-sentence draft).
        return _abstain(ABSTAIN_UNVERIFIED if reached_verifier else ABSTAIN_UNCITED, cov, unsupported, generation)
    return Answer(text=" ".join(r["text"] for r in kept), sentences=kept,
                  verified_citations=list(verified.values()), unsupported=unsupported,
                  abstained=False, coverage=cov, generation=generation or {})
