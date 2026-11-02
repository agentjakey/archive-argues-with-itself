"""The per-shard audit (scripts/v2/audit_shard.py) end to end with stubs: a shard built from compiled
units on a local store stands in for R2, a stub drafter, the stub writer and stub judges. No network,
no paid call. Covers the R2 ledger, sizing under the cap, the result file, the undecided queue, the
resume from R2 state and the tier rule."""
from __future__ import annotations

import gzip
import importlib.util
import json
import socket
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

PAGES = [
    "The hospital board reported that the number of beds in Ontario hospitals rose to 4,200 in 1965, "
    "with new wings opened at Kingston and London to serve patients admitted from rural districts. "
    "The board recorded the cost of construction and the staff required for each ward in the province.",
    "Annual report of the department of highways: the province paved 310 miles of road in 1965 and "
    "repaired eleven bridges damaged by spring floods along the river valleys of the northern districts. "
    "Expenditure on maintenance rose with the cost of materials and labour across the province.",
    "The fisheries branch counted salmon returning to the coastal streams and reported a decline in the "
    "catch of 1965 compared with the previous five seasons, recommending limits on commercial licences "
    "and new hatcheries for the rivers of the southern coast and the islands.",
]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    real_connect = socket.socket.connect

    def refuse(self, address, *args, **kwargs):
        # The in-process app's event loop opens a loopback socket pair on Windows; nothing else may connect.
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return real_connect(self, address, *args, **kwargs)
        raise AssertionError("a test tried to open a network connection")

    def refuse_create(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse_create)


def load_module():
    spec = importlib.util.spec_from_file_location("audit_shard", REPO / "scripts" / "v2" / "audit_shard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_shard(tmp_path: Path, store, sid: str) -> None:
    from archive_debugger.ingest import db as ingest_db
    from archive_debugger.jobs import compile as comp
    from archive_debugger.jobs.store import sha256_file
    lines = []
    for n in range(12):
        text = PAGES[n % 3] + " " + PAGES[n % 3] + f" Item {n}."      # over the sampler's 80 words
        files = {"searchtext": gzip.compress(text.encode()),
                 "pageindex": gzip.compress(json.dumps([[0, len(text), 0, 0]]).encode()),
                 "page_numbers": gzip.compress(json.dumps({"pages": [{"leafNum": 0, "pageNumber": "1"}]}).encode())}
        lines += comp.compile_item(f"item{n:02d}", files, {"title": f"Report {n}", "date": "1965"},
                                   target_tokens=300, overlap_tokens=40)
    unit = gzip.compress("".join(json.dumps(l) + "\n" for l in lines).encode())
    db = tmp_path / "built" / "civic.db"
    db.parent.mkdir(parents=True)

    def normalize(conn):
        conn.execute("UPDATE items SET year = 1965, dated = 1, jurisdiction_norm = 'ontario'")
        conn.execute("UPDATE passages SET ocr_quality = 0.9")
        conn.commit()
    comp.pack_shard([unit], db, init_db=ingest_db.init_db, normalize=normalize)
    store.put(f"shards/v1/{sid}/civic.db", db.read_bytes())
    store.put(f"shards/v1/{sid}/manifest.json", json.dumps(
        {"shard_id": sid, "partial": False, "files": {"civic.db": {"sha256": sha256_file(db)}}}).encode())


class StubDrafter:
    model = "stub-drafter"

    def __init__(self):
        self.calls = 0

    def draft(self, task, sources):
        self.calls += 1
        words = sources[0]["text"].split()
        return {"question": f"What did the {words[1]} {words[2]} report about the {words[5]} {words[6]}?",
                "answer_quote": " ".join(words[:6]), "topic": "provincial reports"}


def stub_judge(verdict_for):
    def judge(spec, pending, run_dir, ledger, run_id, cap):
        from archive_debugger.audit import judges
        from archive_debugger.audit.records import append_jsonl
        for it in pending:
            v = verdict_for(spec.name, it)
            verdicts = {"supports": {"verdict": v}, "in_scope": {"verdict": "pass"}}
            append_jsonl(Path(run_dir) / "judgments.jsonl",
                         judges._record(spec, it, verdicts, None, 10, 10, 0.0, False))
    return judge


def test_a_shard_audit_writes_its_result_queues_undecided_checks_and_stays_indexed(tmp_path, monkeypatch):
    from archive_debugger.jobs.store import LocalStore
    mod = load_module()
    monkeypatch.setenv("CIVIC_EMBEDDER", "stub")
    monkeypatch.setenv("CIVIC_DENSE_BACKEND", "numpy")
    monkeypatch.delenv("WRITER_CANDIDATE", raising=False)
    monkeypatch.setattr(mod, "TARGET_SENTENCES", 6)
    monkeypatch.setattr(mod, "MIN_SENTENCES", 2)
    store = LocalStore(tmp_path / "r2")
    sid = "ontario-1960-1970"
    build_shard(tmp_path, store, sid)
    # The calibration on R2 says what run A's latest recompute says: SUPPORTS is not AI-AUDITED.
    store.put(mod.CALIBRATION_KEY, json.dumps({
        "checks": {"supports": {"status": {"check": "supports", "ai_audited": False, "status": "NOT-AI-AUDITED",
                                           "why": "panel misses the bar: silver error upper bound 0.122 over 0.1"}}},
        "silver_error_random_agreed": {"meets": False, "wilson": [0.02, 0.122]}}).encode())
    seen = {"n": 0}

    def verdict_for(judge, item):
        # The two judges disagree on the first sentence each judges: that check is left undecided.
        seen["n"] += 1
        return "fail" if (judge == "deepseek-v4-flash" and item["sentence_no"] == 1
                          and item["qid"].endswith("q0001")) else "pass"
    audit = mod.ShardAudit(sid, store, tmp_path / "work", drafter=StubDrafter(), judge=stub_judge(verdict_for),
                           stub=True, log=lambda m: None)
    assert audit.run() == 0
    result = json.loads(store.get(f"audits/v1/{sid}/result.json"))
    assert result["sentences_judged"] >= 6 and result["undecided"] == 1
    assert result["decided"] == result["sentences_judged"] - 1 and result["pass"] == result["decided"]
    assert result["supports_strict"]["value"] == 1.0 and result["supports_strict"]["wilson95"][0] < 1.0
    assert result["tier"] == "INDEXED" and "silver error" in result["tier_reason"]
    assert result["panel"]["judges"] == ["deepseek-v4-flash", "claude-sonnet-5-5"]
    undecided = store.get(f"audits/v1/{sid}/undecided.jsonl").decode().splitlines()
    assert len(undecided) == 1 and json.loads(undecided[0])["item"]["sentence_no"] == 1
    # State is on R2: a fresh machine resumes without asking or judging again.
    assert store.head(f"audits/v1/{sid}/state/answers.jsonl") is not None
    store.root.joinpath(f"audits/v1/{sid}/result.json").unlink()
    before = seen["n"]
    again = mod.ShardAudit(sid, store, tmp_path / "work2", drafter=StubDrafter(), judge=stub_judge(verdict_for),
                           stub=True, log=lambda m: None)
    assert again.run() == 0 and seen["n"] == before
    assert again.drafter.calls == 0


def test_tiers_need_the_bar_the_silver_rule_and_every_check_decided():
    mod = load_module()
    ok = {"checks": {"supports": {"status": {"ai_audited": True, "why": ""}}}, "silver_error_random_agreed": {"meets": True}}
    assert mod.tier_for({"decided": 100, "undecided": 0}, ok)[0] == "AI-AUDITED"
    assert mod.tier_for({"decided": 100, "undecided": 3}, ok)[0] == "INDEXED"
    assert mod.tier_for({"decided": 100, "undecided": 0}, None)[0] == "INDEXED"
    bad_silver = {**ok, "silver_error_random_agreed": {"meets": False}}
    assert mod.tier_for({"decided": 100, "undecided": 0}, bad_silver)[0] == "INDEXED"
    not_audited = {"checks": {"supports": {"status": {"ai_audited": False, "why": "x"}}},
                   "silver_error_random_agreed": {"meets": True}}
    assert mod.tier_for({"decided": 100, "undecided": 0}, not_audited)[0] == "INDEXED"


def test_the_r2_ledger_is_shared_capped_and_written_back_after_every_entry(tmp_path):
    from archive_debugger.audit.budget import BudgetExceeded
    from archive_debugger.jobs.store import LocalStore
    mod = load_module()
    store = LocalStore(tmp_path / "r2")
    first = mod.R2Ledger(store, tmp_path / "a" / "ledger.jsonl", cap=1.00)
    first.reserve("audit-x", 5.0, "anthropic", "claude-sonnet-5-5", "r1", 0.60)
    # A second job (a fresh runner) reads the ledger from R2 and sees the open reservation.
    second = mod.R2Ledger(store, tmp_path / "b" / "ledger.jsonl", cap=1.00)
    assert abs(second.totals().committed - 0.60) < 1e-9
    with pytest.raises(BudgetExceeded):
        second.reserve("audit-y", 5.0, "anthropic", "claude-sonnet-5-5", "r2", 0.50)


def test_sizing_shares_what_is_left_equally_and_says_when_it_cannot_reach_the_target(tmp_path, monkeypatch):
    from archive_debugger.jobs.store import LocalStore
    mod = load_module()
    store = LocalStore(tmp_path / "r2")
    ledger = mod.R2Ledger(store, tmp_path / "ledger.jsonl")
    s = mod.size_for(store, ledger)
    per_sentence, _ = mod.cost_per_sentence({})
    assert s["shards_left"] == len(mod.planned_shards())
    expected = min(mod.TARGET_SENTENCES, int((mod.TOTAL_CAP_USD - mod.SAFETY_USD) / s["shards_left"] / per_sentence))
    assert s["target"] == expected and s["target"] <= mod.TARGET_SENTENCES
    # After an audited shard, the measured cost per sentence replaces the estimate.
    store.put("audits/v1/some-shard/result.json", json.dumps({"spend": {"usd": 1.0}, "sentences_judged": 200}).encode())
    assert mod.cost_per_sentence(mod.audited_shards(store))[0] == pytest.approx(0.005)
