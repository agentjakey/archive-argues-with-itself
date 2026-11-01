"""The embedder ablation (scripts/v2/embedder_ablation.py) over a tiny SQLite corpus with stub
encoders in place of fastembed and Workers AI: the shared sub-corpus, filters on every system, RRF
order, chunk max-sim, pool items, scoring, the test-split refusal and the heavy-job lock. Every test
here fails if it opens a network connection."""
from __future__ import annotations

import importlib.util
import json
import socket
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

from archive_debugger.audit.records import read_jsonl, write_jsonl
from archive_debugger.retrieve.embed import StubEmbedder

REPO = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("embedder_ablation", REPO / "scripts" / "v2" / "embedder_ablation.py")
ea = importlib.util.module_from_spec(spec)
sys.modules["embedder_ablation"] = ea      # dataclasses look their module up by name
spec.loader.exec_module(ea)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


ITEMS = [
    # item_id, title, year, dated, jurisdiction
    ("itemA", "Alberta hospital report", 1985, 1, "alberta"),
    ("itemB", "Ontario fisheries review", 1975, 1, "ontario"),
    ("itemC", "Undated pamphlet", None, 0, "federal"),
    ("itemD", "Federal budget papers", 1988, 1, "federal"),
]
TOPICS = {
    "itemA": "hospital budget nurses beds alberta health",
    "itemB": "fisheries salmon quota boats ontario lakes",
    "itemC": "pamphlet notice library hours readers",
    "itemD": "budget deficit taxes federal spending hospital",
}
FILLER = ["river", "council", "survey", "winter", "office", "school", "road", "census", "mine", "forest"]


def make_corpus(path: Path) -> list:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE items (item_id TEXT PRIMARY KEY, title TEXT, year INTEGER, dated INTEGER, jurisdiction_norm TEXT);
        CREATE TABLE passages (passage_id TEXT PRIMARY KEY, item_id TEXT, leaf_index INTEGER, text TEXT,
                               token_count INTEGER, ocr_quality REAL);
        CREATE VIRTUAL TABLE passages_fts USING fts5(text);
    """)
    conn.executemany("INSERT INTO items VALUES (?, ?, ?, ?, ?)", ITEMS)
    ids = []
    for item_id, *_ in ITEMS:
        for leaf in range(10):
            pid = f"{item_id}#{leaf}:0"
            text = TOPICS[item_id] + " " + " ".join(FILLER[(leaf + k) % len(FILLER)] for k in range(leaf % 4 + 1))
            cur = conn.execute("INSERT INTO passages VALUES (?, ?, ?, ?, ?, ?)", (pid, item_id, leaf, text, 20, 0.95))
            conn.execute("INSERT INTO passages_fts (rowid, text) VALUES (?, ?)", (cur.lastrowid, text))
            ids.append(pid)
    conn.commit()
    conn.close()
    return ids


def question(n, text, filters=None, sources=(), refuse=False, collection="toy"):
    return {"item_id": f"{collection}:gen:q{n:02d}", "collection": collection, "category": "answerable",
            "question": text, "filters": filters or {}, "label": {"should_refuse": refuse},
            "sources": [{"passage_id": s} for s in sources]}


QUESTIONS = [
    question(1, "What did the hospital budget pay for?", sources=["itemA#9:0"]),
    question(2, "Hospital budget in the 1980s?", filters={"period": "1980s"}, sources=["itemD#3:0"]),
    question(3, "Salmon quota for boats", filters={"jurisdiction": "ontario"}, sources=["itemB#2:0"]),
    question(4, "Library hours of the pamphlet", filters={"period": "undated"}),
    question(5, "Should be refused", refuse=True),
]


class StubEncoder:
    def __init__(self, dim=64, window_words=None):
        self.inner = StubEmbedder(dim=dim)
        self.window_words = window_words
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return np.asarray(self.inner.embed_passages(list(texts)), dtype=np.float32)

    def windows(self, text):
        words = text.split()
        size = self.window_words
        return [" ".join(words[i:i + size]) for i in range(0, max(len(words), 1), size - 1)] or [text]


def stub_candidates(made=None):
    made = made if made is not None else []

    def maker(**kw):
        def make():
            enc = StubEncoder(**kw)
            made.append(enc)
            return enc
        return make
    return [
        ea.Candidate("stub-a", "stub/a", 64, "MIT", "local (stub)", make=maker(dim=64)),
        ea.Candidate("stub-b", "stub/b", 32, "MIT", "local (stub)", make=maker(dim=32), query_prefix="query: "),
        ea.Candidate("stub-chunks", "stub/a", 64, "MIT", "local (stub)", make=maker(dim=64, window_words=4),
                     chunked=True),
        ea.Candidate("stub-paid", "stub/paid", 16, "MIT", "remote (stub)", paid=True,
                     make=lambda: pytest.fail("a paid candidate ran under --skip-paid")),
        ea.Candidate("stub-blocked", "stub/blocked", 16, "MIT", "local (stub)", blocked="not supported here"),
    ]


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "corpus.db"
    corpus_ids = make_corpus(db)
    qfile = tmp_path / "dev.jsonl"
    write_jsonl(qfile, QUESTIONS)
    out = tmp_path / "out"
    lock = tmp_path / "heavy.lock"

    def open_corpus(collection):
        return sqlite3.connect(db), 60, True

    def args(*extra):
        return ea.parser().parse_args(["build", "--collections", "toy", "--questions", str(qfile), "--out", str(out),
                                       "--bm25-depth", "3", "--distractors", "5", "--seed", "7", "--skip-paid",
                                       "--ledger", str(tmp_path / "ledger.jsonl"), *extra])
    return {"db": db, "ids": corpus_ids, "qfile": qfile, "out": out, "lock": lock, "open_corpus": open_corpus,
            "args": args}


def run(env, made=None, *extra):
    return ea.run_build(env["args"](*extra), lock_path=env["lock"], candidates_factory=lambda: stub_candidates(made),
                        open_corpus=env["open_corpus"])


def test_subcorpus_holds_bm25_hits_distractors_and_sources_and_is_shared(env):
    assert run(env) == 0
    sub = json.loads((env["out"] / "toy" / "subcorpus.json").read_text(encoding="utf-8"))
    ids = set(sub["passage_ids"])
    conn = sqlite3.connect(env["db"])
    asked = [q for q in QUESTIONS if not q["label"]["should_refuse"]]
    for q in asked:
        hits = ea.bm25_ranking(conn, q["question"], ea.question_filters(q), 3)
        assert hits and set(hits) <= ids
        assert set(ea.source_ids(q)) <= ids
    assert sub["counts"]["distractors"] == 5
    assert sub["counts"]["total"] == len(ids)
    assert sub["sha256"] == ea.ids_digest(sorted(ids))
    # every non-chunked candidate embedded exactly the sub-corpus, in the same order
    emb = env["out"] / "toy" / "embeddings"
    rows_a = json.loads((emb / f"stub-a-{sub['sha256'][:16]}.ids.json").read_text(encoding="utf-8"))
    rows_b = json.loads((emb / f"stub-b-{sub['sha256'][:16]}.ids.json").read_text(encoding="utf-8"))
    assert rows_a["row_passage_ids"] == rows_b["row_passage_ids"] == sub["passage_ids"]
    chunks = json.loads((emb / f"stub-chunks-{sub['sha256'][:16]}.ids.json").read_text(encoding="utf-8"))
    assert set(chunks["row_passage_ids"]) == ids
    build = json.loads((env["out"] / "toy" / "build.json").read_text(encoding="utf-8"))
    assert build["candidates"]["stub-blocked"]["status"] == "BLOCKED"
    assert build["candidates"]["stub-paid"]["status"] == "SKIPPED"
    assert build["candidates"]["stub-a"]["status"] == "BUILT"
    assert build["candidates"]["stub-b"]["query_prefix"] == "query: "


def test_rerun_reuses_subcorpus_and_never_reembeds(env):
    assert run(env) == 0
    made = []
    assert run(env, made) == 0
    assert all(enc.calls == 0 for enc in made)


def test_filters_apply_to_every_system(env):
    assert run(env) == 0
    rankings = json.loads((env["out"] / "toy" / "rankings.json").read_text(encoding="utf-8"))["systems"]
    assert {"bm25", "dense stub-a", "hybrid stub-a", "dense stub-chunks", "hybrid stub-b"} <= set(rankings)
    allowed = {"toy:gen:q02": {"itemA", "itemD"}, "toy:gen:q03": {"itemB"}, "toy:gen:q04": {"itemC"}}
    for system, by_q in rankings.items():
        for qid, items in allowed.items():
            assert by_q[qid], (system, qid)
            assert {pid.split("#")[0] for pid in by_q[qid]} <= items, (system, qid)


def test_rrf_fusion_order_on_a_hand_made_example():
    # a: 1/61 + 1/62, c: 1/63 + 1/61, b: 1/62, d: 1/63
    assert ea.fuse([["a", "b", "c"], ["c", "a", "d"]], 60, 10) == ["a", "c", "b", "d"]
    assert ea.fuse([["a", "b", "c"], ["c", "a", "d"]], 60, 2) == ["a", "c"]
    # a tie is broken by passage id
    assert ea.fuse([["y"], ["x"]], 60, 10) == ["x", "y"]


def test_chunk_max_sim_scores_a_passage_by_its_best_window():
    ids = ["p0", "p1", "p2"]
    matrix = ea.unit_rows(np.array([[1, 0], [0, 1], [0.6, 0.8], [0.9, 0.1], [-1, 0]], dtype=np.float32))
    owners = np.array([0, 0, 1, 1, 2])
    query = np.array([0, 1], dtype=np.float32)
    everything = np.ones(3, dtype=bool)
    # p0's second window is the query itself; p1's best window is 0.8; p2's only window scores 0
    assert ea.dense_ranking(matrix, owners, query, ids, everything, 10) == ["p0", "p1", "p2"]
    no_p0 = np.array([False, True, True])
    assert ea.dense_ranking(matrix, owners, query, ids, no_p0, 10) == ["p1", "p2"]


def test_window_spans_overlap_and_cover():
    assert ea.window_spans(0, 126, 32) == [(0, 0)]
    assert ea.window_spans(100, 126, 32) == [(0, 100)]
    assert ea.window_spans(300, 126, 32) == [(0, 126), (94, 220), (188, 300)]
    with pytest.raises(ValueError):
        ea.window_spans(10, 4, 4)


def test_pool_items_have_the_documented_fields(env):
    assert run(env) == 0
    items = read_jsonl(env["out"] / "pool_items.jsonl")
    assert items and items == read_jsonl(env["out"] / "toy" / "pool_items.jsonl")
    for it in items:
        assert set(it) == {"format", "kind", "item_id", "collection", "qid", "question", "filters", "passage",
                           "writer_model"}
        assert it["kind"] == "relevance" and it["format"] == 1 and it["writer_model"] is None
        assert it["item_id"] == f"toy:{it['qid']}:{it['passage']['passage_id']}"
        p = it["passage"]
        assert set(p) == {"passage_id", "item_id", "title", "year", "jurisdiction", "leaf_index", "deep_link", "text"}
        assert p["deep_link"] == f"https://archive.org/details/{p['item_id']}/page/n{p['leaf_index']}"
    assert "toy:gen:q05" not in {it["qid"] for it in items}
    # keys sorted on disk, and every system's top 10 is in the pool
    first = (env["out"] / "pool_items.jsonl").read_text(encoding="utf-8").splitlines()[0]
    assert list(json.loads(first)) == sorted(json.loads(first))
    rankings = json.loads((env["out"] / "rankings.json").read_text(encoding="utf-8"))
    pooled = {(it["qid"], it["passage"]["passage_id"]) for it in items}
    for by_q in rankings.values():
        for qid, ranked in by_q.items():
            assert {(qid, pid) for pid in ranked[:10]} <= pooled
    from archive_debugger.audit import prompts
    assert "<question>" in prompts.user_message(items[0])


def test_question_scores_on_a_hand_made_judged_pool():
    judged = {"a": "pass", "b": "partial", "c": "fail", "d": "pass", "e": None}
    s = ea.question_scores(["a", "c", "x", "e"], judged)
    assert s["recall@10"] == pytest.approx(0.5)
    ideal = 2 + 2 / np.log2(3) + 1 / np.log2(4)
    assert s["ndcg@10"] == pytest.approx(2 / ideal)
    assert s["unjudged@10"] == pytest.approx(0.25)
    assert s["person@10"] == pytest.approx(0.25)
    none = ea.question_scores(["c"], {"c": "fail", "b": "partial"})
    assert none["recall@10"] is None and none["ndcg@10"] is None


def test_score_reads_panel_decisions_and_bootstraps(tmp_path):
    out = tmp_path / "out"
    coll = out / "toy"
    coll.mkdir(parents=True)

    def item(qid, pid):
        return {"format": 1, "kind": "relevance", "item_id": f"toy:{qid}:{pid}", "collection": "toy", "qid": qid,
                "question": "q", "filters": {}, "passage": {"passage_id": pid}, "writer_model": None}
    items = [item("q1", p) for p in ("a", "b", "c")] + [item("q2", p) for p in ("d", "e")] + [item("q3", "f")]
    write_jsonl(coll / "pool_items.jsonl", items)
    systems = {"hybrid minilm-128": {"q1": ["c", "a"], "q2": ["e", "d"], "q3": ["f"]},
               "dense other": {"q1": ["a", "b"], "q2": ["d"], "q3": ["f"]}}
    (coll / "rankings.json").write_text(json.dumps({"systems": systems}), encoding="utf-8")
    (coll / "build.json").write_text(json.dumps({"corpus_rows": 1000, "candidates": {
        "minilm-128": {"model": "m", "dim": 384, "status": "BUILT", "embedding": {"windows_per_passage": 1.0}},
        "minilm-chunks": {"model": "m", "dim": 384, "status": "BUILT", "chunked": True,
                          "embedding": {"windows_per_passage": 3.5}}}}), encoding="utf-8")
    runs = tmp_path / "runs"
    first = [{"item_id": "toy:q1:a", "checks": {"relevant": {"final": "fail"}}}]
    second = [{"item_id": "toy:q1:a", "checks": {"relevant": {"final": "pass"}}},
              {"item_id": "toy:q1:b", "checks": {"relevant": {"final": "partial"}}},
              {"item_id": "toy:q2:d", "checks": {"relevant": {"final": "pass"}}},
              {"item_id": "toy:q2:e", "checks": {"relevant": {"final": None}}},
              {"item_id": "toy:q3:f", "checks": {"relevant": {"final": "fail"}}}]
    write_jsonl(runs / "r1" / "panel.jsonl", first)
    write_jsonl(runs / "r2" / "panel.jsonl", second)
    result = ea.score(out, ["r1", "r2"], runs_dir=runs, seed=3, spot=2)
    toy = result["collections"]["toy"]
    assert toy["questions"] == 3 and toy["questions_scored"] == 2 and toy["questions_without_a_pass"] == 1
    ref, other = toy["systems"]["hybrid minilm-128"], toy["systems"]["dense other"]
    assert ref["recall@10"] == pytest.approx(1.0) and other["recall@10"] == pytest.approx(1.0)
    # q1: ref puts the pass second, other first; q2: ref puts the pass second, other first
    assert other["ndcg@10"] > ref["ndcg@10"]
    diff = other["ndcg@10 diff vs reference"]
    assert diff["n"] == 2 and diff["low"] <= diff["diff"] <= diff["high"] and diff["diff"] > 0
    assert ref["unjudged@10"] == pytest.approx((0.5 + 0 + 0) / 3, abs=1e-4)   # q1's c was never judged
    assert ref["person@10"] == pytest.approx((0 + 0.5 + 0) / 3, abs=1e-4)     # q2's e went to a person
    sizes = result["candidates"]["minilm-128"]["index_size_whole_collection"]["toy"]
    assert sizes == {"rows": 1000, "rows_estimated_from_subcorpus_windows": False, "float32_bytes": 1000 * 384 * 4,
                     "int8_bytes": 1000 * 384, "binary_bytes": 1000 * 48}
    assert result["candidates"]["minilm-chunks"]["index_size_whole_collection"]["toy"]["rows"] == 3500
    assert len(read_jsonl(out / "spot_items.jsonl")) == 2
    assert (out / "scores.md").exists() and json.loads((out / "scores.json").read_text(encoding="utf-8"))
    assert result["pooled"]["systems"]["dense other"]["ndcg@10 diff vs reference"]["n"] == 2


def test_paired_bootstrap_is_seeded_and_brackets_the_mean():
    a, b = [1.0, 0.5, 0.8, 0.2], [0.5, 0.5, 0.4, 0.4]
    one, two = ea.paired_bootstrap(a, b, seed=5), ea.paired_bootstrap(a, b, seed=5)
    assert one == two and one["low"] <= one["diff"] <= one["high"]
    assert ea.paired_bootstrap([], [])["diff"] is None


def test_a_test_split_is_refused(tmp_path):
    path = tmp_path / "test.jsonl"
    write_jsonl(path, QUESTIONS)
    with pytest.raises(ValueError, match="test split"):
        ea.load_questions([path], None, 1)
    with pytest.raises(ValueError, match="test split"):
        ea.main(["build", "--questions", str(path), "--out", str(tmp_path / "o")])


def test_questions_drop_refusals_and_cap_per_collection_with_a_seed(tmp_path):
    path = tmp_path / "dev.jsonl"
    write_jsonl(path, QUESTIONS + [question(9, "", collection="toy"), question(1, "other", collection="more")])
    got = ea.load_questions([path], None, 1)
    assert [q["item_id"] for q in got["toy"]] == [f"toy:gen:q0{n}" for n in (1, 2, 3, 4)]
    capped = ea.load_questions([path], 2, 1)
    assert len(capped["toy"]) == 2 and capped == ea.load_questions([path], 2, 1)


def test_lock_refuses_another_owner_and_is_removed_after_a_run(env, capsys):
    env["lock"].write_text("run-B something-else 2026-11-01T00:00:00+00:00", encoding="utf-8")
    assert run(env) == ea.LOCK_BUSY_STATUS
    assert "held by another job" in capsys.readouterr().out
    assert not (env["out"] / "toy").exists()
    assert env["lock"].read_text(encoding="utf-8").startswith("run-B")
    env["lock"].unlink()
    seen = []

    def open_corpus(collection):
        seen.append(env["lock"].read_text(encoding="utf-8"))
        return env["open_corpus"](collection)
    assert ea.run_build(env["args"](), lock_path=env["lock"], candidates_factory=stub_candidates,
                        open_corpus=open_corpus) == 0
    assert seen and seen[0].startswith("run-A embedder_ablation ")
    assert not env["lock"].exists()


def test_lock_is_removed_on_error(env):
    def broken(collection):
        raise RuntimeError("boom")
    with pytest.raises(RuntimeError):
        ea.run_build(env["args"](), lock_path=env["lock"], candidates_factory=stub_candidates, open_corpus=broken)
    assert not env["lock"].exists()
