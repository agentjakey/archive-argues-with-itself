"""Year, place and issuer ranking features (retrieve/meta_rank.py) and their place in the engine."""
from __future__ import annotations

from pathlib import Path

import pytest

from archive_debugger.retrieve import meta_rank
from archive_debugger.retrieve.filters import Filters

ON = {"year": 0.5, "place": 0.5, "issuer": 0.5, "recency": 0.5}


def hit(pid, score, year=None, jur=None, issuer=None):
    return {"passage_id": pid, "score": score, "year": year, "jurisdiction": jur, "issuer": issuer}


def test_question_constraints():
    c = meta_rank.question_constraints("What did Alberta report between 1974 and 1999?")
    assert c.years == [(1974, 1999)] and c.places == {"alberta"} and c.as_of is None
    c = meta_rank.question_constraints("Hospital insurance in the 1980s in Nova Scotia and Quebec")
    assert c.years == [(1980, 1989)] and c.places == {"nova_scotia", "quebec"}
    c = meta_rank.question_constraints("Tobacco rules as of 1990, compared with 1975")
    assert c.as_of == 1990 and c.years == [(1975, 1975)]
    c = meta_rank.question_constraints("Sant" + chr(233) + " publique au Qu" + chr(233) + "bec, 1974-1999")
    assert c.places == {"quebec"} and c.years == [(1974, 1999)]
    c = meta_rank.question_constraints("How many hospitals were there?")
    assert c.years == [] and c.places == set() and c.as_of is None
    # "Canada" and numbers that are not years name nothing.
    c = meta_rank.question_constraints("In Canada 300 beds and 12000 nurses")
    assert c.years == [] and c.places == set()


def test_issuer_words():
    assert meta_rank.issuer_words("Ontario Ministry of Health") == frozenset()
    assert meta_rank.issuer_words("Royal Commission on Asbestos (Ontario)") == {"asbestos"}
    assert meta_rank.issuer_words("Statistics Canada") == {"statistics"}
    assert meta_rank.issuer_words(None) == frozenset()


def test_zero_weights_leave_the_ranking_untouched():
    hits = [hit("a", 0.3, 1950, "ontario"), hit("b", 0.2, 1985, "alberta")]
    for weights in (None, {}, {"year": 0.0, "place": 0.0, "issuer": 0.0, "recency": 0.0}):
        assert meta_rank.rerank(hits, "Alberta in 1985", weights) is hits
    assert meta_rank.digest({"year": 0.0}) == "" and meta_rank.digest(None) == ""
    assert meta_rank.digest(ON) and meta_rank.digest(ON) != meta_rank.digest({**ON, "year": 0.4})


def test_each_feature_moves_a_matching_hit_up():
    base = [hit("a", 0.30, 1950, "ontario", "Health Canada"), hit("b", 0.25, 1985, "alberta", "Statistics Canada")]
    assert [h["passage_id"] for h in meta_rank.rerank(base, "hospital beds", ON)] == ["a", "b"]
    for question in ("hospital beds in 1985", "hospital beds in Alberta", "what Statistics Canada said on beds"):
        out = meta_rank.rerank(base, question, ON)
        assert [h["passage_id"] for h in out] == ["b", "a"], question
        assert out[0]["rank_features"]
    # A weight of zero switches its feature off.
    assert [h["passage_id"] for h in meta_rank.rerank(base, "hospital beds in 1985", {"place": 0.5})] == ["a", "b"]


def test_recency_prefers_the_latest_record_up_to_the_as_of_year():
    hits = [hit("old", 0.30, 1971), hit("near", 0.26, 1989), hit("after", 0.29, 1995)]
    out = meta_rank.rerank(hits, "hospital beds as of 1990", {"recency": 0.5})
    assert [h["passage_id"] for h in out] == ["near", "old", "after"]
    # The as_of_year filter counts as well; the earlier of two as of years wins.
    out = meta_rank.rerank(hits, "hospital beds", {"recency": 0.5}, Filters(as_of_year=1990))
    assert out[0]["passage_id"] == "near"
    # Year filters count as a named range.
    out = meta_rank.rerank(hits, "hospital beds", {"year": 0.5}, Filters(year_from=1985, year_to=1990))
    assert out[0]["passage_id"] == "near"


def test_ties_keep_the_original_order_and_input_is_not_changed():
    hits = [hit("a", 0.2, 1985), hit("b", 0.2, 1985), hit("c", 0.2, 1985)]
    out = meta_rank.rerank(hits, "in 1985", ON)
    assert [h["passage_id"] for h in out] == ["a", "b", "c"]
    assert "rank_features" not in hits[0]


def test_load_weights(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text("[generate]\nmodel = 'x'\n", encoding="utf-8")
    assert meta_rank.load_weights(cfg) == {"year": 0.0, "place": 0.0, "issuer": 0.0, "recency": 0.0}
    cfg.write_text("[rank]\nyear = 0.3\nplace = 0.2\n", encoding="utf-8")
    assert meta_rank.load_weights(cfg) == {"year": 0.3, "place": 0.2, "issuer": 0.0, "recency": 0.0}
    cfg.write_text("[rank]\nyears = 0.3\n", encoding="utf-8")
    with pytest.raises(ValueError):
        meta_rank.load_weights(cfg)


def test_cache_context_moves_only_when_weights_are_set():
    from archive_debugger.api.app import cache_context
    from archive_debugger.generate.cli import load_generate_config
    repo = Path(__file__).resolve().parent.parent
    gcfg = load_generate_config(repo / "config" / "pilot.toml")
    assert not meta_rank.active(gcfg["rank"])     # the shipped configs leave ranking as it was
    args = ("pilot", {"db": "a" * 64, "index": "b" * 64}, {"k": 1})
    plain = cache_context(*args, gcfg, "anthropic", "m")
    without = cache_context(*args, {k: v for k, v in gcfg.items() if k != "rank"}, "anthropic", "m")
    weighted = cache_context(*args, {**gcfg, "rank": ON}, "anthropic", "m")
    assert plain == without and weighted != plain


def test_retrieve_pool_reorders_within_the_pool():
    from archive_debugger.generate.cli import retrieve_pool

    class FakeRetriever:
        class cfg:
            pool_size = 3

        def search(self, question, filters=None, top_k=10):
            return [hit("a", 0.30, 1950), hit("b", 0.28, 1985), hit("c", 0.10, 1985)]

    pool, top = retrieve_pool(FakeRetriever(), "beds in 1985", Filters(), 2, ON)
    assert [h["passage_id"] for h in pool] == ["b", "a", "c"] and [h["passage_id"] for h in top] == ["b", "a"]
    pool, top = retrieve_pool(FakeRetriever(), "beds in 1985", Filters(), 2)
    assert [h["passage_id"] for h in top] == ["a", "b"]
