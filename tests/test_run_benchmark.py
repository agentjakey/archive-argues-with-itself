"""scripts/v2/run_benchmark.py: the frozen split check, exclusions, the one final test run, restricted
items answered by an engine holding their fixtures, the v1 state mapping, ledger metering and the cap,
judge items, and the scores. Hermetic: a temp corpus, the stub writer, and every test fails if it
opens a network connection."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from archive_debugger.audit.budget import Ledger
from archive_debugger.audit.records import read_jsonl, write_jsonl

REPO = Path(__file__).resolve().parent.parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / "v2" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rb = load("run_benchmark")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every outbound connection is refused. On Windows the asyncio event loop behind TestClient makes
    its internal socket pair by connecting to 127.0.0.1, so only that loopback connect is let through."""
    real_connect = socket.socket.connect

    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")

    def loopback_only(sock, address, *args, **kwargs):
        if isinstance(address, tuple) and address and address[0] in ("127.0.0.1", "::1"):
            return real_connect(sock, address, *args, **kwargs)
        raise AssertionError(f"a test tried to open a network connection to {address!r}")
    monkeypatch.setattr(socket.socket, "connect", loopback_only)
    monkeypatch.setattr(socket, "create_connection", refuse)


FIXTURE = {
    "authority": "Synthetic test authority (fixture, not a real restriction)",
    "basis": "Synthetic restriction for testing (benchmark fixture).", "contact": "",
    "display": {"label": "Restricted (test fixture)", "local_contexts": None},
    "entered_at": "2026-11-01T00:00:00Z", "entered_by": "test", "fixture": True, "format": 1,
    "policy_id": "fixture-test-0001", "restrict": ["retrieve", "generate", "export"],
    "targets": {"collections": [], "items": ["a", "b"]},
}


def bench_item(n, category="answerable", verdict="SUPPORTED", refuse=False, governance=None):
    item = {"item_id": f"pilot:gen:{category}:{n:04d}", "kind": "benchmark2" if governance is not None else "benchmark",
            "collection": "pilot", "category": category, "question": "vaccination hospital", "filters": {},
            "label": {"verdict": verdict, "should_refuse": refuse, "behaviour": "b"}, "sources": []}
    if governance is not None:
        item["governance"] = governance
    return item


def items_default():
    return [bench_item(1), bench_item(2),
            bench_item(3, "false_premise", "INSUFFICIENT_EVIDENCE", True, governance=[]),
            bench_item(4, "restricted", "RESTRICTED", True, governance=[FIXTURE])]


def make_bench(tmp_path, items=None, split="dev", excluded=()):
    """A split file, its lock and an exclusion list, all under tmp_path."""
    items = items if items is not None else items_default()
    splits = tmp_path / "splits"
    splits.mkdir(exist_ok=True)
    path = splits / f"{split}.jsonl"
    write_jsonl(path, items)
    exclusions = tmp_path / "exclusions.json"
    exclusions.write_text(json.dumps({"version": 1, "set_sha256": "s", "excluded": [{"item_id": i, "reason": "t"}
                                                                                   for i in excluded]}), encoding="utf-8")
    lock = tmp_path / "lock.json"
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    lock.write_text(json.dumps({"set_sha256": "s", "exclusions": str(exclusions),
                                "splits": {split: {"items": len(items), "sha256": sha}}}), encoding="utf-8")
    return lock, splits


@pytest.fixture()
def corpus(tmp_path):
    from tests.test_api import _retriever
    r, _ = _retriever(tmp_path, [("a", 1990, "ontario"), ("b", 1991, "ontario")])
    return r, tmp_path / "civic.db"


def engine_factory(tmp_path, retriever, seen):
    from fastapi.testclient import TestClient
    from archive_debugger.api.app import create_app

    @contextmanager
    def factory(collection, cfg_path, register, llm, provider):
        seen.append({"collection": collection, "register": register, "cfg": Path(cfg_path).read_text(encoding="utf-8")})
        app = create_app(cfg_path, retriever=retriever, load_env=False, provider=provider, llm=llm,
                         governance_register=register if register is not None else rb.governance.Register(),
                         web_dist=tmp_path / "nodist", cache_path=tmp_path / "cache" / f"answers-{len(seen)}.db")
        with TestClient(app) as client:
            yield client
    return factory


def run(tmp_path, corpus, seen=None, **kw):
    seen = seen if seen is not None else []
    lock, splits = kw.pop("bench", None) or make_bench(tmp_path)
    kw.setdefault("split", "dev")
    kw.setdefault("pipeline", "v2")
    kw.setdefault("run_id", "t1")
    kw.setdefault("cap", 1.0)
    kw.setdefault("stub", True)
    return rb.run_benchmark(out_root=tmp_path / "out", lock_path=lock, splits_dir=splits,
                            engine_factory=engine_factory(tmp_path, corpus[0], seen), log=lambda *_: None, **kw)


def answers(tmp_path, run_id="t1"):
    return {r["item_id"]: r for r in read_jsonl(tmp_path / "out" / "runs" / run_id / "answers.jsonl")}


def test_a_changed_split_is_refused(tmp_path):
    lock, splits = make_bench(tmp_path)
    with (splits / "dev.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(bench_item(9)) + chr(10))
    with pytest.raises(rb.Refused, match="sha256"):
        rb.load_split("dev", lock, splits)


def test_exclusions_are_dropped(tmp_path, corpus):
    excluded = "pilot:gen:answerable:0002"
    lock, splits = make_bench(tmp_path, excluded=[excluded])
    items, facts = rb.load_split("dev", lock, splits)
    assert excluded not in {it["item_id"] for it in items} and facts["excluded"] == [excluded]
    assert run(tmp_path, corpus, bench=(lock, splits)) == 0
    assert excluded not in answers(tmp_path) and len(answers(tmp_path)) == 3


def test_the_test_split_needs_final_and_runs_once_per_pipeline(tmp_path, corpus):
    bench = make_bench(tmp_path, split="test")
    with pytest.raises(rb.Refused, match="--final"):
        run(tmp_path, corpus, bench=bench, split="test")
    assert run(tmp_path, corpus, bench=bench, split="test", final=True) == 0
    marker = tmp_path / "out" / "test_runs" / "v2-claude-haiku-4-5-stub.json"
    assert json.loads(marker.read_text(encoding="utf-8"))["run_id"] == "t1"
    with pytest.raises(rb.Refused, match="already answered"):
        run(tmp_path, corpus, bench=bench, split="test", final=True, run_id="t2")
    with pytest.raises(rb.Refused, match="--limit"):
        run(tmp_path, corpus, bench=bench, split="test", final=True, run_id="t3", pipeline="v1", limit=2)


def test_restricted_items_are_answered_by_an_engine_holding_their_fixtures(tmp_path, corpus):
    seen = []
    assert run(tmp_path, corpus, seen=seen) == 0
    rows = answers(tmp_path)
    assert rows["pilot:gen:restricted:0004"]["state"] == "RESTRICTED"
    assert rows["pilot:gen:restricted:0004"]["refused"] is True
    assert rows["pilot:gen:restricted:0004"]["governance_policies"] == ["fixture-test-0001"]
    assert rows["pilot:gen:answerable:0001"]["state"] == "SUPPORTED"
    assert rows["pilot:gen:answerable:0001"]["sentences"][0]["cited_ids"]
    # two engines: the main one with no fixtures, then one holding exactly the restricted item's fixture
    assert seen[0]["register"] is None
    assert [p.policy_id for p in seen[1]["register"].policies] == ["fixture-test-0001"]
    assert 'answer_version = "v2"' in seen[0]["cfg"] and 'model = "claude-haiku-4-5-20251001"' in seen[0]["cfg"]
    assert (REPO / "config" / "pilot.toml").read_text(encoding="utf-8").count("answer_version") == 0


def test_v1_state_mapping():
    def body(abstained, gov=None, degraded=None):
        b = {"answer": {"abstained": abstained, "text": "x"}, "evidence": []}
        if gov:
            b["governance"] = {"restricted": [{"policy_id": "p"}]}
        if degraded:
            b["degraded"] = {"reason": degraded}
        return b
    assert rb.state_of("v1", body(True, gov=True)) == ("RESTRICTED", None)
    assert rb.state_of("v1", body(True)) == ("INSUFFICIENT_EVIDENCE", None)
    assert rb.state_of("v1", body(False)) == ("SUPPORTED", None)
    assert rb.state_of("v1", body(False, gov=True)) == ("SUPPORTED", None)       # answered around a restriction
    assert rb.state_of("v1", body(True, degraded="budget")) == (None, "degraded:budget")
    assert rb.state_of("v2", {"answer": {"state": "CONFLICTING"}}) == ("CONFLICTING", None)


def test_a_v1_run_through_the_engine(tmp_path, corpus):
    assert run(tmp_path, corpus, pipeline="v1") == 0
    rows = answers(tmp_path)
    assert rows["pilot:gen:answerable:0001"]["state"] == "SUPPORTED"
    assert rows["pilot:gen:restricted:0004"]["state"] == "RESTRICTED"
    assert all(r["pipeline"] == "v1" and r["usd"] == 0.0 for r in rows.values())


class PaidWriter(rb.EchoStubWriter):
    """Stands in for a paid writer: reports token usage like the real one."""

    def draft(self, system, user):
        out = super().draft(system, user)
        self.last_usage = {"input_tokens": 1000, "output_tokens": 100}
        return out


def test_the_ledger_records_each_call_and_the_cap_stops_before_crossing(tmp_path, corpus):
    writers = []

    def factory(pipeline, writer, effort, stub, gcfg):
        w = PaidWriter()
        writers.append(w)
        return w
    ledger = Ledger(tmp_path / "ledger.jsonl", phase="test", phase_cap=100.0)
    gcfg = rb.load_generate_config(REPO / "config" / "pilot.toml")
    _, _, worst = rb.worst_case_usd("claude-haiku-4-5", "vaccination hospital", gcfg["top_k"], gcfg["max_tokens"])
    actual = rb.prices.cost("claude-haiku-4-5", 1000, 100)
    cap = worst + actual / 2           # room for one call, not for a second on top of the first's spend
    code = run(tmp_path, corpus, stub=False, ledger=ledger, writer_factory=factory, cap=cap)
    assert code == 2
    rows = answers(tmp_path)
    assert list(rows) == ["pilot:gen:answerable:0001"]
    assert rows["pilot:gen:answerable:0001"]["usage"] == {"input_tokens": 1000, "output_tokens": 100, "estimated": False}
    entries = read_jsonl(tmp_path / "ledger.jsonl")
    assert [e["kind"] for e in entries] == ["reserve", "spend", "release"]
    assert entries[1]["usd"] == round(actual, 6) and entries[1]["run_id"] == "t1"
    assert ledger.totals("t1").reserved == 0 and ledger.totals("t1").spent <= cap
    info = json.loads((tmp_path / "out" / "runs" / "t1" / "run.json").read_text(encoding="utf-8"))
    assert info["status"] == "stopped_at_cap"
    # a rerun with room resumes: the answered item is not asked again
    assert run(tmp_path, corpus, stub=False, ledger=ledger, writer_factory=factory, cap=1.0) == 0
    assert len(answers(tmp_path)) == 4
    calls_after_resume = sum(w.calls for w in writers[1:])
    assert calls_after_resume == 2     # the second answerable and the false premise; the restricted one never reaches it


def test_v1_spend_is_the_worst_case_marked_estimated(tmp_path, corpus):
    class PaidV1(rb.EchoStubLLM):
        pass
    ledger = Ledger(tmp_path / "ledger.jsonl", phase="test", phase_cap=100.0)
    lock, splits = make_bench(tmp_path, items=[bench_item(1)])
    assert run(tmp_path, corpus, bench=(lock, splits), pipeline="v1", stub=False, ledger=ledger,
               writer_factory=lambda *a: PaidV1()) == 0
    row = answers(tmp_path)["pilot:gen:answerable:0001"]
    assert row["usage"]["estimated"] is True and row["usd"] > 0
    spend = [e for e in read_jsonl(tmp_path / "ledger.jsonl") if e["kind"] == "spend"]
    assert len(spend) == 1 and "estimated" in spend[0]["what"]


def test_a_rerun_with_other_settings_is_refused(tmp_path, corpus):
    assert run(tmp_path, corpus) == 0
    with pytest.raises(rb.Refused, match="different"):
        run(tmp_path, corpus, pipeline="v1")


def test_judge_items_follow_the_audit_format_with_ids_unique_across_runs(tmp_path, corpus):
    assert run(tmp_path, corpus, run_id="r1") == 0
    assert run(tmp_path, corpus, run_id="r2") == 0

    def connect(collection):
        conn = sqlite3.connect(corpus[1])
        conn.row_factory = sqlite3.Row
        return conn
    one = rb.build_judge_items(tmp_path / "out" / "runs" / "r1", connect)
    two = rb.build_judge_items(tmp_path / "out" / "runs" / "r2", connect)
    sentences = [it for it in one if it["kind"] == "sentence"]
    answer_items = [it for it in one if it["kind"] == "answer"]
    # the stub answers the two answerable items and the false premise; the restricted item is refused
    assert len(answer_items) == 3 and len(sentences) == 3
    assert "pilot:gen:restricted:0004" not in {it["qid"].split("/", 1)[1] for it in one}
    s = sentences[0]
    assert s["format"] == 2 and s["item_id"] == "pilot:r1/pilot:gen:answerable:0001:s1"
    assert s["qid"] == "r1/pilot:gen:answerable:0001" and s["sentence_no"] == 1
    assert set(s["citations"][0]) == set(rb.audit_items.CITATION_FIELDS)
    assert s["citations"][0]["text"] == "vaccination hospital programme" and s["writer_model"] == "claude-haiku-4-5-20251001"
    assert s["retrieved_ids"] and s["citations"][0]["passage_id"] in s["retrieved_ids"]
    a = answer_items[0]
    assert a["item_id"] == "pilot:r1/pilot:gen:answerable:0001:answer" and a["sentences"] == [rb.STUB_SENTENCE]
    assert set(a) == {"format", "kind", "item_id", "collection", "qid", "question", "filters", "answer_text",
                      "sentences", "source", "writer_model", "generated_at"}
    ids_one, ids_two = {it["item_id"] for it in one}, {it["item_id"] for it in two}
    assert len(ids_one) == len(one) and not ids_one & ids_two


def row(item_id, category, expected, state, refuse, usd=0.0, latency=1.0, called=True, error=None):
    from archive_debugger.generate.answer_v2 import refused
    return {"item_id": item_id, "category": category, "expected_verdict": expected, "should_refuse": refuse,
            "state": None if error else state, "refused": None if error else refused(state), "usd": usd,
            "latency_s": latency, "model_called": called, "error": error}


def test_scores_on_hand_made_rows():
    rows = [row("i1", "answerable", "SUPPORTED", "SUPPORTED", False, usd=0.01, latency=1.0),
            row("i2", "answerable", "SUPPORTED", "INSUFFICIENT_EVIDENCE", False, usd=0.03, latency=3.0),
            row("i3", "false_premise", "INSUFFICIENT_EVIDENCE", "INSUFFICIENT_EVIDENCE", True, latency=2.0),
            row("i4", "restricted", "RESTRICTED", "RESTRICTED", True, called=False, latency=0.5),
            row("i5", "answerable", "SUPPORTED", "SUPPORTED", False, error="degraded:budget")]
    judge_items = [{"item_id": "c:r/i1:s1", "kind": "sentence", "qid": "r/i1"},
                   {"item_id": "c:r/i1:s2", "kind": "sentence", "qid": "r/i1"},
                   {"item_id": "c:r/i1:answer", "kind": "answer", "qid": "r/i1"}]
    decisions = {"c:r/i1:s1": {"checks": {"supports": {"final": "pass"}, "in_scope": {"final": "pass"}}, "human_queue": []},
                 "c:r/i1:s2": {"checks": {"supports": {"final": None}, "in_scope": {"final": "pass"}},
                               "human_queue": ["supports"]},
                 "c:r/i1:answer": {"checks": {"answers": {"final": "partial"}}, "human_queue": []}}
    s = rb.score_run(rows, judge_items, decisions)
    m = s["metrics"]
    assert s["answered"] == 4 and s["errors"] == 1
    assert m["refusal_rate_should_refuse"]["value"] == 1.0 and m["refusal_rate_should_refuse"]["den"] == 2
    assert m["false_refusal_rate"]["value"] == 0.5
    assert m["state_accuracy"]["value"] == 0.75
    lo, hi = m["state_accuracy"]["wilson95"]
    assert lo < 0.75 < hi
    assert m["supports_strict"]["num"] == 1 and m["supports_strict"]["den"] == 1
    assert m["answers_failure"]["value"] == 1.0
    assert s["left_to_person"]["value"] == pytest.approx(1 / 3)
    assert m["cost_per_answer"]["value"] == pytest.approx((0.01 + 0.03 + 0.0) / 3)
    assert s["latency_s"]["p50"] == pytest.approx(1.5) and s["latency_s"]["p95"] == pytest.approx(2.85)
    assert s["confusion"]["SUPPORTED"] == {"INSUFFICIENT_EVIDENCE": 1, "SUPPORTED": 1}
    assert s["state_accuracy_by_category"]["answerable"]["value"] == 0.5


def test_recall_at_10_counts_the_source_page_among_the_first_ten():
    found = {**row("i1", "answerable", "SUPPORTED", "SUPPORTED", False),
             "source_pages": ["x#4"], "top10": ["y#1:0", "x#4:2"]}
    missed = {**row("i2", "answerable", "SUPPORTED", "INSUFFICIENT_EVIDENCE", False),
              "source_pages": ["x#5"], "top10": ["x#4:0", "x#50:1"]}
    no_source = {**row("i3", "answerable", "SUPPORTED", "SUPPORTED", False), "source_pages": [], "top10": ["x#4:0"]}
    refuse = {**row("i4", "false_premise", "INSUFFICIENT_EVIDENCE", "INSUFFICIENT_EVIDENCE", True),
              "source_pages": ["x#4"], "top10": ["x#4:0"]}
    m = rb.score_run([found, missed, no_source, refuse], [], {})["metrics"]
    assert (m["recall_at_10"]["num"], m["recall_at_10"]["den"]) == (1, 2)
    assert rb.source_pages({"sources": [{"passage_id": "a#3:1"}, {"passage_id": "a#3:2"}, {"item_id": "b", "leaf_index": 0}]}) == ["a#3", "b#0"]


def test_score_fills_source_pages_from_the_split_for_older_rows(tmp_path, corpus):
    items = [dict(bench_item(1), sources=[{"passage_id": "a#0:0"}]), bench_item(2)]
    bench = make_bench(tmp_path, items=items)
    assert run(tmp_path, corpus, run_id="r1", bench=bench) == 0
    path = tmp_path / "out" / "runs" / "r1" / "answers.jsonl"
    rows = read_jsonl(path)
    assert rows[0]["source_pages"] == ["a#0"]
    for r in rows:
        r.pop("source_pages")
    write_jsonl(path, rows)
    write_jsonl(tmp_path / "out" / "runs" / "r1" / "judge_items.jsonl", [])
    lock, splits = bench
    result = rb.score(["r1"], [], "s", out_root=tmp_path / "out", audit_dir=tmp_path / "audit",
                      lock_path=lock, splits_dir=splits)
    assert result["runs"]["r1"]["metrics"]["recall_at_10"]["den"] == 1


def test_rank_weights_reach_the_engine_config_and_the_label(tmp_path, corpus):
    assert rb.parse_rank(None) is None and rb.parse_rank("year=0") is None
    weights = rb.parse_rank("year=0.3, place=0.2")
    assert weights == {"year": 0.3, "place": 0.2, "issuer": 0.0, "recency": 0.0}
    with pytest.raises(rb.Refused):
        rb.parse_rank("years=0.3")
    seen = []
    assert run(tmp_path, corpus, seen=seen, run_id="rk", rank=weights) == 0
    assert "[rank]" in seen[0]["cfg"] and "year = 0.3" in seen[0]["cfg"]
    info = json.loads((tmp_path / "out" / "runs" / "rk" / "run.json").read_text(encoding="utf-8"))
    assert info["config"]["rank"] == weights and "-rank" in info["pipeline_label"]
    # Resuming with other weights is refused.
    with pytest.raises(rb.Refused):
        run(tmp_path, corpus, run_id="rk", rank=rb.parse_rank("year=0.5"))


def test_paired_bootstrap():
    first = [row(f"i{n}", "answerable", "SUPPORTED", "SUPPORTED" if n % 2 else "INSUFFICIENT_EVIDENCE", False)
             for n in range(40)]
    second = [row(f"i{n}", "answerable", "SUPPORTED", "SUPPORTED", False) for n in range(40)]
    empty = ({}, {})
    same = rb.paired_bootstrap(first, first, empty, empty)
    assert same["differences"]["state_accuracy"]["difference"] == 0
    assert same["differences"]["state_accuracy"]["bootstrap95"] == [0, 0]
    diff = rb.paired_bootstrap(first, second, empty, empty)
    d = diff["differences"]["state_accuracy"]
    assert d["difference"] == pytest.approx(0.5) and d["resamples_used"] == 2000
    assert d["bootstrap95"][0] < 0.5 < d["bootstrap95"][1] and d["bootstrap95"][0] > 0
    assert diff["differences"]["false_refusal_rate"]["difference"] == pytest.approx(-0.5)
    assert rb.paired_bootstrap(first, second, empty, empty) == diff          # seeded
    assert rb.paired_bootstrap(first[:1], [row("x", "a", "S", "SUPPORTED", False)], empty, empty) is None


def test_score_writes_json_and_markdown(tmp_path, corpus):
    assert run(tmp_path, corpus, run_id="r1") == 0
    assert run(tmp_path, corpus, run_id="r2", pipeline="v1") == 0
    for r in ("r1", "r2"):
        write_jsonl(tmp_path / "out" / "runs" / r / "judge_items.jsonl", [])
    result = rb.score(["r1", "r2"], [], "cmp", out_root=tmp_path / "out", audit_dir=tmp_path / "audit")
    assert set(result["runs"]) == {"r1", "r2"} and result["comparisons"][0]["items"] == 4
    md = (tmp_path / "out" / "scores" / "cmp" / "scores.md").read_text(encoding="utf-8")
    assert "r2 minus r1" in md and md.isascii()


def test_the_script_is_ascii():
    assert (REPO / "scripts" / "v2" / "run_benchmark.py").read_bytes().isascii()


def test_an_open_writer_provider_is_v2_only_and_metered_under_its_own_provider(tmp_path, corpus):
    class PaidOpen(rb.EchoStubWriter):
        def draft(self, system, user):
            out = super().draft(system, user)
            self.last_usage = {"input_tokens": 1000, "output_tokens": 100}
            return out
    with pytest.raises(rb.Refused, match="v2 pipeline only"):
        run(tmp_path, corpus, pipeline="v1", stub=False, provider="workers_ai", writer="@cf/zai-org/glm-5.3")
    with pytest.raises(rb.Refused, match="--endpoint"):
        run(tmp_path, corpus, stub=False, endpoint="mistral")
    ledger = Ledger(tmp_path / "ledger.jsonl", phase="test", phase_cap=100.0)
    lock, splits = make_bench(tmp_path, items=[bench_item(1)])
    assert run(tmp_path, corpus, bench=(lock, splits), stub=False, ledger=ledger, provider="workers_ai",
               writer="@cf/zai-org/glm-5.3", writer_factory=lambda *a: PaidOpen()) == 0
    spend = [e for e in read_jsonl(tmp_path / "ledger.jsonl") if e["kind"] == "spend"]
    assert len(spend) == 1 and spend[0]["provider"] == "workers-ai"
    assert spend[0]["usd"] == round(rb.prices.cost("@cf/zai-org/glm-5.3", 1000, 100), 6)
    info = json.loads((tmp_path / "out" / "runs" / "t1" / "run.json").read_text(encoding="utf-8"))
    assert info["config"]["provider"] == "workers_ai" and info["pipeline_label"] == "v2-cf_zai-org_glm-5.3"
