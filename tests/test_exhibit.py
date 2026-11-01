"""The exhibit deck builder: its refusal checks (each seeded bad round is refused for its own reason),
the care rules, the When Was This? masking, the deck's choice of rounds, Gap Hunt's coverage states
and the network module's retry rule. No test reaches a real host or a model."""
from __future__ import annotations

import copy
import socket
import sqlite3

import pytest

from archive_debugger.exhibit import care, deck, gaphunt, net, pages, rounds, settings, timedial


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


BODY = ("The Board accepted 4,210 claims for compensation this year, an increase over the previous year.\n"
        "Most claims came from the construction and logging industries.\n"
        "A new safety program for sawmill workers began in the spring.")
TITLE_PAGE = "WORKERS' COMPENSATION BOARD\nANNUAL REPORT\n1978\nFredericton"


@pytest.fixture
def corpus():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE items (item_id TEXT PRIMARY KEY, title TEXT, issuer_norm TEXT, publisher_raw TEXT, creator_raw TEXT,
            jurisdiction_norm TEXT, date_raw TEXT, date_method TEXT, year INTEGER, dated INTEGER, language TEXT,
            page_count INTEGER);
        CREATE TABLE passages (passage_id TEXT, item_id TEXT, leaf_index INTEGER, char_start INTEGER, text TEXT);
    """)
    conn.execute("INSERT INTO items VALUES ('wcb1978', 'Annual report', 'wcb', 'WCB', NULL, 'new_brunswick', "
                 "'1978-01-01', 'exact', 1978, 1, 'eng', 40)")
    conn.execute("INSERT INTO items VALUES ('undated1', 'A pamphlet', 'x', 'X', NULL, 'ontario', NULL, 'unknown', NULL, 0, "
                 "'eng', 10)")
    conn.execute("INSERT INTO passages VALUES ('wcb1978#1:0', 'wcb1978', 1, 0, ?)", (TITLE_PAGE,))
    conn.execute("INSERT INTO passages VALUES ('wcb1978#12:0', 'wcb1978', 12, 0, ?)", (BODY,))
    conn.execute("INSERT INTO passages VALUES ('undated1#5:0', 'undated1', 5, 0, ?)", (BODY,))
    return conn


@pytest.fixture
def rules():
    return settings.load().care


def when_round(corpus):
    page = pages.page_record(corpus, "c", "wcb1978", 12, keep_quotes=[], max_chars=2400)
    reply = {"label_en": "An annual report", "label_fr": "Un rapport annuel",
             "clues": ["A new safety program for sawmill workers began in the spring."],
             "explanation_en": "The page talks about a new safety program.", "explanation_fr": "La page parle d'un programme."}
    return rounds.when_round(page, reply, model="m", drafted_at="2026-11-01T00:00:00Z")


def check(rnd, corpus, rules):
    return deck.check_round(rnd, lambda name: corpus, rules)


def test_page_record_reads_and_verifies_the_date(corpus):
    page = pages.page_record(corpus, "c", "wcb1978", 12, keep_quotes=[], max_chars=2400)
    assert page["catalogue_date"] == {"year": 1978, "raw": "1978-01-01", "method": "exact"}
    assert page["page_date"]["method"] == "read_from_front_matter"
    assert page["page_date"]["page_ref"] == "wcb1978#1"
    assert "1978" in page["page_date"]["line"]
    assert page["date_verified"] is True
    assert page["details_url"] == "https://archive.org/details/wcb1978/page/n12"


def test_a_good_round_passes(corpus, rules):
    assert check(when_round(corpus), corpus, rules) == []


def test_seeded_bad_round_page_does_not_resolve(corpus, rules):
    rnd = when_round(corpus)
    rnd["pages"][0]["ref"] = "wcb1978#99"
    rnd["quotes"][0]["page_ref"] = "wcb1978#99"
    assert any(r.startswith("page_unresolved:") for r in check(rnd, corpus, rules))


def test_seeded_bad_round_quote_not_on_page(corpus, rules):
    rnd = when_round(corpus)
    rnd["quotes"][0]["text"] = "A new safety program for miners began in the autumn."
    assert "quote_not_on_page:c1" in check(rnd, corpus, rules)


def test_seeded_bad_round_date_not_verified(corpus, rules):
    page = pages.page_record(corpus, "c", "undated1", 5, keep_quotes=[], max_chars=2400)
    assert page["date_verified"] is False
    rnd = rounds.when_round(page, {"clues": ["Most claims came from the construction and logging industries."]},
                            model="m", drafted_at="x")
    reasons = check(rnd, corpus, rules)
    assert "date_unverified:undated1#5" in reasons
    assert "answer_year_unverified" in reasons


def test_seeded_bad_round_claims_a_date_it_cannot_show(corpus, rules):
    rnd = when_round(corpus)
    rnd["pages"][0]["page_date"]["line"] = "ANNUAL REPORT 1979"
    assert any(r.startswith("date_unverified:") for r in check(rnd, corpus, rules))


def test_seeded_bad_round_touches_a_care_topic(corpus, rules):
    rnd = when_round(corpus)
    rnd["explanation"]["en"] = "The page mentions the residential school health program."
    reasons = check(rnd, corpus, rules)
    assert any(r.startswith("care:") for r in reasons)


def test_changed_page_text_is_refused(corpus, rules):
    rnd = when_round(corpus)
    corpus.execute("UPDATE passages SET text = ? WHERE passage_id = 'wcb1978#12:0'", (BODY + "\nAn added line.",))
    assert any(r.startswith("page_text_changed:") for r in check(rnd, corpus, rules))


def test_when_year_must_be_the_verified_year(corpus, rules):
    rnd = when_round(corpus)
    rnd["play"]["year"] = 1980
    assert "answer_year_unverified" in check(rnd, corpus, rules)


def test_malformed_rounds_are_refused(corpus, rules):
    rnd = when_round(corpus)
    del rnd["play"]
    assert check(rnd, corpus, rules) == ["malformed:missing play"]
    rnd = when_round(corpus)
    rnd["mode"] = "trivia"
    assert any(r.startswith("malformed:mode") for r in check(rnd, corpus, rules))


def test_care_rules(rules):
    assert care.care_flags(["Hospital beds per 1,000 population rose."], rules) == []
    assert "indigenous-context" in care.care_flags(["Services for First Nations communities"], rules)
    assert "period-term:feeble-minded" in care.care_flags(["a home for the feeble-minded"], rules)
    assert "term:suicide" in care.care_flags(["Suicide prevention"], rules)
    assert any(r.startswith("tier-") for r in care.care_flags(["the tainted blood inquiry"], rules))
    # Accents and case do not hide a term.
    assert "term:abortion" in care.care_flags(["ABORTION"], rules)


def test_on_page_ignores_accents_and_line_breaks():
    text = "Le programme de sant\u00e9\npublique a commenc\u00e9 au printemps."
    assert pages.on_page("programme de sante publique a commence", text)
    assert not pages.on_page("programme de sante publique a fini", text)
    assert not pages.on_page("", text)


def test_year_spans_hide_years_and_ranges():
    text = "Report for 1975-76, compared with 1974 and the 2001/2002 plan; page 19 of 250."
    spans = rounds.year_spans(text)
    hidden = [text[a:b] for a, b in spans]
    assert hidden == ["1975-76", "1974", "2001/2002"]


def test_cut_text_keeps_the_quote():
    lines = [f"line {n} of filler text" for n in range(200)]
    lines[150] = "The decisive line about hospital beds."
    text, cut = pages.cut_text("\n".join(lines), ["The decisive line about hospital beds."], 600)
    assert cut and "The decisive line about hospital beds." in text and len(text) <= 700


def same_round(answer, n):
    return {"id": f"son-{answer}-{n}", "mode": "same_or_not", "status": "model-reviewed", "level": 2,
            "play": {"answer": answer}}


def test_choose_balances_same_or_not_and_sets_level_one():
    s = settings.load()
    decided = [same_round(a, n) for a in deck.SAME_OR_NOT_CHOICES for n in range(8)]
    decided.append({**same_round("not_comparable", 99), "status": "flagged"})
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("exhibit_deck", Path(__file__).resolve().parents[1] / "scripts" / "v2" / "exhibit_deck.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    chosen = mod.choose(decided, s)
    same = [r for r in chosen if r["mode"] == "same_or_not"]
    assert len(same) == s.same_or_not_rounds
    assert {a: sum(r["play"]["answer"] == a for r in same) for a in deck.SAME_OR_NOT_CHOICES} == \
        {a: s.same_or_not_rounds // 4 for a in deck.SAME_OR_NOT_CHOICES}
    assert same[0]["level"] == 1 and same[0]["play"]["answer"] == "not_comparable"
    assert all(r["status"] != "flagged" for r in chosen)


def test_gap_hunt_states():
    assert gaphunt.cell_state(120, 5) == "recorded"
    assert gaphunt.cell_state(120, 0) == "not_indexed"
    assert gaphunt.cell_state(0, 0) == "quiet_examined"
    assert gaphunt.cell_state(None, 0) == "unknown"


def test_dial_years_mark_not_indexed_and_quiet():
    extra = timedial.dial_extra({1963: 0, 1964: 3}, (1963, 2018), 1960, 1965)
    states = {y["year"]: y["state"] for y in extra["years"]}
    assert states == {1960: "not_indexed", 1961: "not_indexed", 1962: "not_indexed", 1963: "quiet",
                      1964: "recorded", 1965: "quiet"}


def test_step_pages_only_use_pages_published_by_then():
    def p(ref, year, decade, rank):
        return {"ref": ref, "catalogue_date": {"year": year}, "retrieval": {"decade": decade, "rank": rank}}
    pool = [p("a#1", 1965, 1960, 1), p("b#1", 1972, 1970, 2), p("c#1", 1981, 1980, 1)]
    assert [x["ref"] for x in timedial.step_pages(pool, 1975)] == ["a#1", "b#1"]
    assert timedial.step_years(pool) == [1965, 1972, 1981]


def test_net_retries_then_raises_on_client_error(monkeypatch):
    import urllib.error
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 404, "not found", {}, None)
    monkeypatch.setattr(net.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(net.HttpError):
        net.get_json("https://example.test/api", {"q": "x"}, sleep=lambda s: None)
    assert len(calls) == 1


def test_net_retries_server_errors(monkeypatch):
    import io
    import urllib.error
    calls = []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"response": {"numFound": 7}}'

    def fake_urlopen(req, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, io.BytesIO(b""))
        return Reply()
    monkeypatch.setattr(net.urllib.request, "urlopen", fake_urlopen)
    assert gaphunt.numfound("q", get=lambda url, params: net.get_json(url, params, sleep=lambda s: None)) == 7
    assert len(calls) == 3


def test_round_fingerprint_ignores_review_fields(corpus):
    rnd = when_round(corpus)
    other = copy.deepcopy(rnd)
    other["status"] = "flagged"
    other["review"] = {"flags": ["x"]}
    assert deck.round_fingerprint(rnd) == deck.round_fingerprint(other)
    other["explanation"]["en"] = "changed"
    assert deck.round_fingerprint(rnd) != deck.round_fingerprint(other)
