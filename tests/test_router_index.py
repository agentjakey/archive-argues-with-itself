"""The router index (scripts/v2/router_index.py): term buckets the engine Worker can read for just the
question's terms, a stable hash the Worker computes the same way, and collection-wide BM25 figures."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def router_index():
    spec = importlib.util.spec_from_file_location("router_index", REPO / "scripts" / "v2" / "router_index.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The same values are asserted in worker/engine/test/router.test.ts, so the two hashes stay one.
HASH_FIXTURES = {"hospital": 1335678899, "vaccination": 2013792114, "sant\u00e9": 994107771, "": 2166136261}


def test_the_bucket_hash_is_fnv1a_and_matches_the_worker():
    ri = router_index()
    for term, h in HASH_FIXTURES.items():
        assert ri.fnv1a(term) == h
    assert ri.bucket_of("hospital") == HASH_FIXTURES["hospital"] % ri.BUCKETS


def test_buckets_hold_every_term_once_with_each_shards_df():
    ri = router_index()
    cov = {
        "s1": {"df": {"hospital": 3, "beds": 2}, "passages": 10, "tokens": 100, "jurisdictions": ["alberta"],
               "years": {"alberta|1980": 2}},
        "s2": {"df": {"hospital": 5}, "passages": 30, "tokens": 500, "jurisdictions": ["ontario"],
               "years": {"ontario|undated": 4}},
    }
    files, pointer = ri.build(cov, {"s1": "INDEXED", "s2": "AI-AUDITED"}, buckets=16)
    lines = [l for body in files.values() for l in body.decode().splitlines()]
    assert sorted(lines) == ["beds\ts1:2", "hospital\ts1:3,s2:5"]
    assert "hospital\t" in files[ri.bucket_name(ri.bucket_of("hospital", 16))].decode()
    assert pointer["N"] == 40 and pointer["avgdl"] == 15.0 and pointer["buckets"] == 16
    assert pointer["shards"]["s2"]["tier"] == "AI-AUDITED"
    again, pointer2 = ri.build(cov, {}, buckets=16)
    assert pointer2["digest"] == pointer["digest"]                     # content-addressed
    json.dumps(pointer)


def test_the_workers_parity_fixture_is_current():
    """tests/fixtures/router_parity.json holds the Python router's results that the engine Worker's
    port must reproduce (worker/engine/test/router.test.ts); regenerate it when the router changes."""
    import os
    import subprocess
    import sys
    done = subprocess.run([sys.executable, str(REPO / "tests" / "fixtures" / "make_router_parity.py"), "--check"],
                          cwd=REPO, env={**os.environ, "PYTHONPATH": str(REPO / "src")})
    assert done.returncode == 0, "run python tests/fixtures/make_router_parity.py"


def test_the_collections_served_first_are_parts_of_the_whole_collection(monkeypatch):
    ri = router_index()
    monkeypatch.setattr(ri, "local_db", lambda name, entry: None)
    parts = ri.parts()
    assert sorted(parts) == ["microlog", "pilot"]
    assert ri.coverage_key(parts["pilot"]) == "pilot/coverage.json"
    assert ri.coverage_key(parts["microlog"]) == "microlog/coverage.json"
    # The Worker's generated config lists the same parts, so it searches what the index holds.
    config = json.loads((REPO / "worker" / "engine" / "src" / "generated" / "engine_config.json").read_text(encoding="utf-8"))
    assert config["collection"]["parts"] == ["pilot", "microlog"]
