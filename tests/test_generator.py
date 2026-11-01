"""The question generator (audit/generator.py): sampling, corpus checks, gates, labels and the
metered drafter, on a small test corpus with the network replaced."""
from __future__ import annotations

import json
import random
import socket
import sqlite3

import pytest

from archive_debugger.audit import budget, generator, judges, prompts
from archive_debugger.ingest import db


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture
def corpus(tmp_path):
    path = tmp_path / "civic.db"
    conn = db.init_db(str(path))
    pages = [("a", 1975, "ontario", "Tuberculosis sanatorium admissions fell sharply across the province during 1975 "
                                    "as streptomycin treatment spread to every regional hospital. " * 3),
             ("b", 1995, "alberta", "Influenza vaccination clinics opened in every school district in 1995 and "
                                    "reached 41,000 children. " * 4),
             ("c", 1977, "ontario", "Sanatorium beds were converted for chronic care as tuberculosis cases declined. " * 4)]
    for item, year, jur, text in pages:
        conn.execute("INSERT INTO items (item_id, title, dated, year, decade, jurisdiction_norm, doc_type_norm, details_url) "
                     "VALUES (?,?,?,?,?,?,?,?)", (item, f"Report {item}", 1, year, f"{year // 10 * 10}s", jur, "report", "u"))
        conn.execute("INSERT INTO pages (page_id, item_id, leaf_index, printed_page, has_text) VALUES (?,?,?,?,1)",
                     (f"{item}#0", item, 0, "1"))
        conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, text, "
                     "token_count, ocr_quality) VALUES (?,?,?,?,0,?,?,?,?)",
                     (f"{item}#0:0", item, f"{item}#0", 0, len(text), text, len(text.split()), 0.9))
    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


def test_pages_are_sampled_from_dated_items_with_a_place(corpus):
    pages = generator.sample_pages(corpus, 3, random.Random(1), quality=(0.66, 1.01), min_words=10)
    assert sorted(p["item_id"] for p in pages) == ["a", "b", "c"]
    assert all(p["deep_link"].endswith("/page/n0") and p["year"] for p in pages)


def test_corpus_checks_count_passages_by_period_place_and_year(corpus):
    terms = generator.key_terms("tuberculosis sanatorium admissions")
    assert terms == ["tuberculosis", "admissions", "sanatorium"]
    assert generator.fts_count(corpus, ["tuberculosis", "sanatorium"]) == 2
    assert generator.fts_count(corpus, ["tuberculosis", "sanatorium"], period="1990s") == 0
    assert generator.fts_count(corpus, ["tuberculosis", "sanatorium"], jurisdiction="alberta") == 0
    assert generator.fts_count(corpus, ["influenza"], after_year=1995) == 0
    assert generator.newest_year(corpus) == 1995


def test_gates_and_labels():
    page = {"text": "Influenza vaccination clinics opened in every school district in 1995."}
    assert generator.quote_gate("clinics opened in every\nschool district", [page])["passed"]
    assert not generator.quote_gate("clinics closed in every school district", [page])["passed"]
    assert generator.question_gate("What did Alberta report about influenza clinics in 1995?")["passed"]
    assert not generator.question_gate("What does this document say about clinics?")["passed"]
    assert generator.other_decade(1975, random.Random(0), (1960, 2009)) in {"1960s"} | {f"{d}s" for d in range(2000, 2010, 10)}
    item = generator.make_item("c", "wrong_period", 3, "q?", {"period": "1990s"}, [page], [], "m")
    assert item["item_id"] == "c:gen:wrong_period:0003" and item["label"]["should_refuse"]
    assert item["status"] == "model-drafted" and item["kind"] == "benchmark"
    assert generator.templated("wrong_jurisdiction", "School Clinics.", place="Manitoba") == \
        "What did Manitoba government publications report about school clinics?"


def test_a_benchmark_item_is_judged_on_its_own_checks_and_prompt_version():
    item = generator.make_item("c", "answerable", 1, "What opened?", {}, [{"passage_id": "a#0:0", "text": "t"}], [], "m")
    assert set(prompts.verdict_schema("benchmark")["properties"]) == {"well_formed", "label_correct"}
    assert prompts.version_for("benchmark") != prompts.version_for("sentence")
    assert "<label verdict=\"SUPPORTED\">" in prompts.user_message(item)


def test_the_drafter_is_metered_and_skips_what_it_cannot_read(tmp_path, monkeypatch):
    monkeypatch.setenv("CF_AIG_TOKEN", "g")
    ledger = budget.Ledger(tmp_path / "l.jsonl")
    replies = [{"choices": [{"message": {"content": json.dumps({"question": "Q?", "answer_quote": "x y", "topic": "t"})}}],
                "usage": {"prompt_tokens": 900, "completion_tokens": 100}},
               {"choices": [{"message": {"content": "no json"}}], "usage": {"prompt_tokens": 900, "completion_tokens": 5}}]

    def post(url, headers, body, response_headers=None):
        assert headers["cf-aig-gateway-id"] == "gw"
        return replies.pop(0)

    d = generator.Drafter("@cf/deepseek-ai/deepseek-v4-flash-0731", ledger, "g1", 1.0, gateway="gw", post=post,
                          credentials=lambda: ("acct", "tok"))
    page = {"passage_id": "a#0:0", "text": "text", "title": "T", "year": 1990, "jurisdiction": "ontario", "leaf_index": 0}
    assert d.draft("answerable", [page]) == {"question": "Q?", "answer_quote": "x y", "topic": "t"}
    assert d.draft("answerable", [page]) is None
    assert ledger.totals("g1").spent > 0 and ledger.open_reservations() == []


def test_the_generator_names_no_collection():
    from archive_debugger.audit import collections
    from pathlib import Path
    text = Path(generator.__file__).read_text(encoding="utf-8")
    for name in collections.all_names():
        assert f'"{name}"' not in text
