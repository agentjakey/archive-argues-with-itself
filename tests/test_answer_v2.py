"""The v2 answer's evidence states and the gates that can only move a proposal toward caution."""
from __future__ import annotations

from types import SimpleNamespace

from archive_debugger.generate import answer_v2 as v2


def hit(pid, item, text="vaccination clinics opened in ontario", year=1990):
    return {"passage_id": pid, "item_id": item, "leaf_index": 1, "printed_page": "1", "page_deep_link": "u",
            "title": "t", "year": year, "jurisdiction": "ontario", "decade": "1990s", "dated": 1, "text": text}


HITS = [hit("a#1:0", "a"), hit("b#1:0", "b"), hit("c#1:0", "c")]


def ok_verify(cited, retrieved):
    return [SimpleNamespace(passage_id=c, ok=c in retrieved) for c in cited]


def draft(state, sentences):
    return v2.Draft2(sentences=[v2.CitedSentence2(text=t, cited_ids=ids) for t, ids in sentences],
                     evidence_state=state, state_reason="r")


def run(state, sentences, question="vaccination clinics ontario", hits=HITS, **kw):
    w = v2.StubWriter(draft(state, sentences))
    return v2.compose_v2(question, hits, w, ok_verify, min_passages=3, **kw), w


def test_supported_answer():
    a, _ = run("answers", [("Clinics opened.", ["a#1:0"])])
    assert a.state == "SUPPORTED" and not a.abstained and a.verified_citations


def test_a_conflict_needs_two_documents_or_it_is_shown_as_partial():
    a, _ = run("conflicting", [("One count.", ["a#1:0"]), ("Another count.", ["b#1:0"])])
    assert a.state == "CONFLICTING"
    a, _ = run("conflicting", [("One count.", ["a#1:0"])])
    assert a.state == "PARTIALLY_SUPPORTED" and a.gate_notes


def test_incomparable_needs_two_documents_too():
    a, _ = run("incomparable", [("A.", ["a#1:0"]), ("B.", ["c#1:0"])])
    assert a.state == "INCOMPARABLE" and v2.refused(a.state)
    a, _ = run("incomparable", [("A.", ["a#1:0"])])
    assert a.state == "PARTIALLY_SUPPORTED"


def test_dropped_sentences_turn_supported_into_partial():
    a, _ = run("answers", [("Clinics opened.", ["a#1:0"]), ("Uncited claim.", [])])
    assert a.state == "PARTIALLY_SUPPORTED" and a.unsupported


def test_a_false_premise_is_insufficient_but_shows_what_the_record_says():
    a, _ = run("insufficient", [("The record says 31 clinics, not 50.", ["a#1:0"])])
    assert a.state == "INSUFFICIENT_EVIDENCE" and not a.abstained and v2.refused(a.state)


def test_thin_coverage_abstains_before_any_model_call_and_says_which_kind_of_missing():
    a, w = run("answers", [("x", ["a#1:0"])], question="vaccination zeppelins",
               filters={"period": "1930s"}, window=(1960, 2009), jurisdictions=("ontario",))
    assert w.calls == 0 and a.state == "INSUFFICIENT_EVIDENCE" and a.coverage_state == "not_indexed"
    a, _ = run("answers", [("x", ["a#1:0"])], question="vaccination zeppelins", window=(1960, 2009))
    assert a.coverage_state == "absent_from_examined_holdings"
    assert "archive" not in (a.text or "")


def test_nothing_verified_is_insufficient():
    a, _ = run("answers", [("Bad.", ["zzz#1:0"])])
    assert a.state == "INSUFFICIENT_EVIDENCE" and a.abstained


def test_the_v2_prompt_has_its_own_version():
    from archive_debugger.generate.answer import prompt_material as v1
    assert v2.prompt_material() != v1()
    meta = v2.generation_meta(provider="anthropic", model="m", effort="low", max_tokens=10, top_k=5)
    assert meta["answer_version"] == v2.ANSWER_VERSION and len(meta["prompt_sha256"]) == 64


def test_the_engine_serves_v2_states_under_its_own_cache_key(tmp_path):
    from fastapi.testclient import TestClient
    from archive_debugger.api.app import create_app
    from tests.test_api import _retriever
    cfg = tmp_path / "pilot_v2.toml"
    text = open("config/pilot.toml", encoding="utf-8").read()
    lines = [ln + (chr(10) + 'answer_version = "v2"' if ln.strip() == "[generate]" else "") for ln in text.splitlines()]
    cfg.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    r, _ = _retriever(tmp_path, [("a", 1990, "ontario"), ("b", 1991, "ontario")])
    writer = v2.StubWriter(draft("conflicting", [("A count.", ["a#0:0"]), ("Another count.", ["b#0:0"])]))
    app = create_app(cfg, retriever=r, load_env=False, provider="stub", llm=writer, web_dist=tmp_path / "nodist",
                     cache_path=tmp_path / "cache" / "answers.db")
    with TestClient(app) as c:
        body = c.post("/ask", json={"question": "vaccination hospital"}).json()
    assert body["answer"]["state"] == "CONFLICTING" and writer.calls == 1
    assert body["answer"]["generation"]["answer_version"] == v2.ANSWER_VERSION
