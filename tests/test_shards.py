"""The shard planner and the router, on small hand-made inputs."""
from __future__ import annotations

import pytest

from archive_debugger.shards import plan, router


def docs():
    out = []
    for n in range(30):
        out.append((f"ia:on{n}", "ontario", 1970 + n, 100))           # 159 passages each
    for n in range(5):
        out.append((f"ia:und{n}", "ontario", None, 100))
    out.append(("ia:yk0", "yukon", 1990, 10))
    out.append(("ia:big", "alberta", 1980, 5000))
    out.append(("ia:big2", "alberta", 1980, 5000))
    return out


def test_every_document_in_exactly_one_shard_and_undated_kept_apart():
    shards = plan.plan(docs(), target=1000, pool_below=500)
    members = plan.membership(shards)
    assert set(members) == {d[0] for d in docs()}
    undated = [s for s in shards if s.undated]
    assert {d for s in undated for d in s.documents} == {f"ia:und{n}" for n in range(5)}
    for s in shards:
        if not s.undated:
            assert s.first_year <= s.last_year
            assert s.est_passages <= 1000 or len(s.documents) == 1


def test_small_places_are_pooled_and_listed():
    shards = plan.plan(docs(), target=1000, pool_below=500)
    pooled = [s for s in shards if s.jurisdiction == "other"]
    assert pooled and pooled[0].jurisdictions == ["yukon"]


def test_a_year_bigger_than_a_shard_is_split_and_says_so():
    shards = [s for s in plan.plan(docs(), target=1000, pool_below=500) if s.jurisdiction == "alberta"]
    assert len(shards) == 2 and all(s.split_year for s in shards)
    assert len({s.shard_id for s in shards}) == 2


def cov(shard_id, place, years, df, passages=100, tokens=10000):
    return {"shard_id": shard_id, "jurisdictions": [place], "years": years, "df": df, "passages": passages, "tokens": tokens}


COVS = [
    cov("on-1970", "ontario", {"ontario|1975": 10}, {"tobacco": 40, "smoking": 30}),
    cov("on-1990", "ontario", {"ontario|1995": 10}, {"tobacco": 5}),
    cov("ab-1980", "alberta", {"alberta|1985": 10}, {"tobacco": 50}),
    cov("on-undated", "ontario", {"ontario|undated": 10}, {"tobacco": 9}),
    cov("on-fish", "ontario", {"ontario|1975": 10}, {"fish": 9}),
]


def test_choose_reads_only_coverage_and_says_why_others_were_left():
    chosen, left = router.choose("tobacco and smoking in Ontario", COVS, jurisdiction="ontario", first_year=1970,
                                 last_year=1980, max_engines=3)
    assert [c.shard_id for c in chosen] == ["on-1970"]
    reasons = {c.shard_id: c.reason for c in left}
    assert reasons["ab-1980"] == "other jurisdictions"
    assert reasons["on-1990"] == "no documents in the period"
    assert reasons["on-undated"] == "no documents in the period"
    assert reasons["on-fish"] == "none of the question's words occur in it"


def test_undated_shards_are_searched_when_no_period_is_asked():
    chosen, _ = router.choose("tobacco", COVS, jurisdiction="ontario", max_engines=5)
    assert "on-undated" in {c.shard_id for c in chosen}


def test_merge_uses_collection_wide_bm25_not_each_shards_own():
    # The same raw counts score the same wherever they come from: idf is the collection's.
    hits = {"on-1970": [{"passage_id": "a#1:0", "tf": {"tobacco": 2}, "dl": 100, "dense": 0.5}],
            "ab-1980": [{"passage_id": "b#1:0", "tf": {"tobacco": 2}, "dl": 100, "dense": 0.4}]}
    merged = router.merge("tobacco", hits, COVS, top_k=5)
    scores = {m["passage_id"]: m["bm25"] for m in merged}
    assert scores["a#1:0"] == pytest.approx(scores["b#1:0"])
    assert merged[0]["passage_id"] == "a#1:0"              # the dense score breaks the tie
    assert {m["shard_id"] for m in merged} == {"on-1970", "ab-1980"}
