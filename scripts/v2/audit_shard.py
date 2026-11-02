"""Audit one built shard of the whole collection: its SUPPORTS rate, measured by the judge panel.

    python scripts/v2/audit_shard.py estimate                 # the cost per shard and for every shard, before any spend
    python scripts/v2/audit_shard.py pending                  # JSON list: shards built on R2 with no audit result yet
    python scripts/v2/audit_shard.py run --shard federal-1899-1911
    python scripts/v2/audit_shard.py tiers [--apply]          # each audited shard's tier from its result
    python scripts/v2/audit_shard.py publish-calibration      # put the current calibration status on R2

run (resumable: a stopped run is started again with the same command and does only what is missing;
its state lives on R2 under audits/v1/<shard>/state/, so a fresh runner resumes it):
  1. downloads the shard's corpus database from R2 (shards/v1/<shard>/, checked against its manifest)
     and serves it in-process with the shards' engine config (config/shards/engine.toml), an empty
     vectors database beside it (BM25 alone, as the shard is served);
  2. drafts questions from a seeded random sample of the shard's pages with the existing question
     generator's "answerable" task (audit/generator.py, model-drafted, its quote and form gates), on
     gpt-oss-120b through the archive-argues-audit gateway: about a tenth of a cent a question, and a
     model that is neither the writer nor on the SUPPORTS panel;
  3. answers each through the real engine with the writer the shard serves with ([generate] in the
     engine config: today Claude Haiku 4.5, the v1 pipeline), until the answers hold the target number
     of cited sentences;
  4. turns the answers into sentence judge items (run_benchmark.py judge-items), runs the
     deterministic gates on the shard's own pages, and has the SUPPORTS panel judge every item (config/
     audit.toml [panel.checks.supports]: DeepSeek V4 Flash on Workers AI through the gateway, and
     Claude Sonnet 5.5 in Anthropic batches). Agreement decides; a disagreement or a missing verdict has
     no escalation judge on this route, so it goes to audits/v1/<shard>/undecided.jsonl for adjudication
     in a later session;
  5. writes audits/v1/<shard>/result.json: the strict SUPPORTS rate (pass among decided sentences) with
     its Wilson 95% interval and a question-clustered bootstrap interval, n, the undecided count, the
     spend, the models and prompt versions, and the tier the current calibration allows.

Budget: every paid call reserves its worst case first in one ledger shared by every audit run, kept on
R2 (audits/v1/ledger.jsonl) and written back after every entry, so a killed job leaves the ledger erring
high by at most the calls in flight. The hard cap for audits and drafting is $60 (TOTAL_CAP_USD); a call
that could cross it is not made. The target is about +-5 points per shard (140 judged sentences at a rate
near 0.9); when the money left cannot give every shard still to audit that many, each shard gets an equal
share and the interval widens (estimate prints the tradeoff).

Tier: a shard is AI-AUDITED only when the current calibration (reports/v2/audit/review/status.json from
scripts/v2/silver_labels.py recompute, copied to R2 by publish-calibration) says the SUPPORTS check meets
the bar and the silver error rule holds, and no check is left undecided. Otherwise it stays INDEXED and
the result says why. `tiers --apply` sets served shards' tiers through serve_shards.py.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_benchmark as rb  # noqa: E402
from archive_debugger import scopes  # noqa: E402
from archive_debugger.audit import calibration, gates, generator, judges, panel, prices, prompts  # noqa: E402
from archive_debugger.audit.budget import BudgetExceeded, Ledger  # noqa: E402
from archive_debugger.audit.records import append_jsonl, read_jsonl, write_jsonl  # noqa: E402

AUDIT_PREFIX = "audits/v1"
LEDGER_KEY = f"{AUDIT_PREFIX}/ledger.jsonl"
CALIBRATION_KEY = f"{AUDIT_PREFIX}/calibration_status.json"
SHARDS_PREFIX = "shards/v1"
PLAN = REPO / "config" / "shards" / "plan.json"
ENGINE_CONFIG = REPO / "config" / "shards" / "engine.toml"
CALIBRATION_FILE = REPO / "reports" / "v2" / "audit" / "review" / "status.json"
SCOPE = "audit-shard"                  # the in-process engine's scope name (never a served scope)
PHASE = "runB-shard-audits"            # the ledger phase every shard audit and its drafting share
TOTAL_CAP_USD = 60.00                  # Jake's ceiling for audits and drafting in this run
SAFETY_USD = 2.00                      # kept back for reservations still open when a job was killed
TARGET_SENTENCES = 140                 # about +-5 points at a SUPPORTS rate near 0.9
MIN_SENTENCES = 40                     # below this an audit says too little to be worth its cost
EXPECTED_RATE = 0.90                   # Phase 3's measured strict SUPPORTS on the frozen test, rounded down
SEED = 20261102
DRAFTER = "gpt-oss-120b"
CHECK = "supports"
# Costs before any shard has been audited (US dollars), at list price from audit/prices.py:
#   a draft on gpt-oss-120b, about 1,300 tokens in and 700 out;
#   an answer by Claude Haiku 4.5 (v1, 12 passages): about 7,000 in and 400 out;
#   one sentence judged by DeepSeek V4 Flash (3,500 in, 700 out) and Sonnet 5.5 in a batch (half price).
# The yield guesses (answered share, sentences an answer keeps, drafts that pass their gates) turn them
# into a cost per judged sentence. After the first audited shard the measured cost replaces all of it.
DEFAULT_UNITS = {"draft": 0.0010, "answer": 0.0090, "judge_sentence": 0.0094}
DEFAULT_YIELD = {"answered": 0.75, "sentences_per_answer": 3.0, "draft_pass": 0.85}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- the store and the ledger

def r2_store():
    from archive_debugger.jobs.store import R2Store
    from archive_debugger.local_env import load_local_env
    load_local_env(log=lambda m: None)
    return R2Store()


def download(store, key: str, dest: Path) -> None:
    """A large object straight to disk (R2), or through memory (a local store in tests)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    client = getattr(store, "client", None)
    if client is not None and hasattr(client, "download_file"):
        client.download_file(store.bucket, key, str(dest))
    else:
        dest.write_bytes(store.get(key))


class R2Ledger(Ledger):
    """The audit ledger, one file on R2 shared by every shard audit. Read from R2 when opened; every
    entry is appended locally and the whole file written back to R2 at once, with `after_write`
    (the run's judgment and batch files) so a resumed job finds what was paid for. One audit job runs
    at a time (the workflow's concurrency group), so there is one writer."""

    def __init__(self, store, path: Path, *, cap: float = TOTAL_CAP_USD, after_write: Optional[Callable] = None):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if store.head(LEDGER_KEY) is not None:
            path.write_bytes(store.get(LEDGER_KEY))
        elif path.exists():
            path.unlink()
        super().__init__(path, phase=PHASE, phase_cap=cap)
        self.store = store
        self.after_write = after_write

    def _write(self, entry: dict) -> None:
        with self._lock:
            super()._write(entry)
            self.store.put(LEDGER_KEY, self.path.read_bytes())
            if self.after_write is not None:
                self.after_write()


# ---------------------------------------------------------------- shards and sizing

def planned_shards() -> list:
    return [s["shard_id"] for s in json.loads(PLAN.read_text(encoding="utf-8"))["shards"]]


def built_shards(store) -> list:
    out = []
    for key in store.list(f"{SHARDS_PREFIX}/"):
        parts = key.split("/")
        if len(parts) == 4 and parts[3] == "manifest.json":
            manifest = json.loads(store.get(key))
            if not manifest.get("partial"):
                out.append(parts[2])
    return sorted(set(out))


def audited_shards(store) -> dict:
    out = {}
    for key in store.list(f"{AUDIT_PREFIX}/"):
        parts = key.split("/")
        if len(parts) == 4 and parts[3] == "result.json":
            out[parts[2]] = json.loads(store.get(key))
    return out


def cost_per_sentence(results: dict) -> tuple:
    """(US dollars per judged sentence, all stages, basis). Measured over audited shards when there are
    any; otherwise from DEFAULT_UNITS and DEFAULT_YIELD."""
    spent = sum(float((r.get("spend") or {}).get("usd") or 0) for r in results.values())
    judged = sum(int(r.get("sentences_judged") or 0) for r in results.values())
    if judged:
        return spent / judged, f"measured over {len(results)} audited shards ({judged} sentences, ${spent:.2f})"
    y = DEFAULT_YIELD
    per_answer = DEFAULT_UNITS["answer"] + DEFAULT_UNITS["draft"] / y["draft_pass"]
    per_sentence = DEFAULT_UNITS["judge_sentence"] + per_answer / (y["answered"] * y["sentences_per_answer"])
    return per_sentence, "estimated from list prices and assumed yields (no shard audited yet)"


def wilson_half_width(p: float, n: int) -> float:
    if n <= 0:
        return 1.0
    low, high = calibration.wilson(int(round(p * n)), n)
    return (high - low) / 2


def size_for(store, ledger: Ledger, shard: Optional[str] = None) -> dict:
    """How many sentences each shard still to audit can have within the cap: TARGET_SENTENCES, or
    an equal share of what is left when that is less."""
    results = audited_shards(store)
    remaining = [s for s in planned_shards() if s not in results]
    if shard is not None and shard not in remaining:
        remaining.append(shard)
    per_sentence, basis = cost_per_sentence(results)
    committed = ledger.totals().committed
    left = TOTAL_CAP_USD - committed - SAFETY_USD
    per_shard = left / max(1, len(remaining))
    affordable = int(per_shard / per_sentence) if per_sentence > 0 else TARGET_SENTENCES
    n = max(0, min(TARGET_SENTENCES, affordable))
    return {"target": n, "ideal": TARGET_SENTENCES, "shards_left": len(remaining), "usd_left": round(left, 4),
            "usd_committed": round(committed, 4), "usd_per_shard": round(per_shard, 4),
            "usd_per_sentence": round(per_sentence, 5), "basis": basis,
            "cost_at_target_per_shard": round(TARGET_SENTENCES * per_sentence, 4),
            "cost_at_target_all_left": round(TARGET_SENTENCES * per_sentence * len(remaining), 2),
            "half_width_at_target": round(wilson_half_width(EXPECTED_RATE, n), 4),
            "half_width_at_ideal": round(wilson_half_width(EXPECTED_RATE, TARGET_SENTENCES), 4),
            "too_small": n < MIN_SENTENCES}


# ---------------------------------------------------------------- the shard and its engine

def shard_files(store, sid: str, work: Path) -> tuple:
    """(civic.db, vectors.db) for the shard under work/, the database checked against the build manifest."""
    from archive_debugger.jobs.store import sha256_file
    from archive_debugger.retrieve.index import VEC_SCHEMA
    manifest = json.loads(store.get(f"{SHARDS_PREFIX}/{sid}/manifest.json"))
    if manifest.get("partial"):
        raise SystemExit(f"{sid} is a partial (trial) build and is never audited")
    db = work / "data" / "civic.db"
    want = manifest["files"]["civic.db"]["sha256"]
    if not db.exists() or sha256_file(db) != want:
        download(store, f"{SHARDS_PREFIX}/{sid}/civic.db", db)
        if sha256_file(db) != want:
            raise SystemExit(f"{sid}: civic.db from R2 does not match its manifest")
    vec = work / "data" / "index" / "vectors.db"
    if not vec.exists():
        vec.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(vec))
        conn.executescript(VEC_SCHEMA)
        conn.commit()
        conn.close()
    return db, vec


@contextmanager
def shard_engine(work: Path, cfg_path: Path, db: Path, vec: Path, llm, provider: str):
    """The real app (api/app.py create_app) serving the shard, under a temporary scope registry: the
    project's registry plus one entry for the shard's files. The answer cache is a throwaway file."""
    from fastapi.testclient import TestClient
    from archive_debugger.api.app import create_app
    from archive_debugger.retrieve.search import Retriever
    from archive_debugger.jobs.store import sha256_file
    registry = work / "scopes.audit.toml"
    base = (REPO / "config" / "scopes.toml").read_text(encoding="utf-8")
    # The answer cache keys on the data's published sha256, so the entry carries the files' own hashes.
    registry.write_text(base + "\n" + "\n".join([
        f'[scopes."{SCOPE}"]', f'config = "{cfg_path.resolve().as_posix()}"',
        f'db_path = "{db.resolve().as_posix()}"', f'index_path = "{vec.resolve().as_posix()}"', "",
        f'[scopes."{SCOPE}".r2]', f'db_sha256 = "{sha256_file(db)}"', f'index_sha256 = "{sha256_file(vec)}"', ""]),
        encoding="utf-8")
    previous_registry, previous_active = scopes.REGISTRY_PATH, scopes.active_scope()
    scopes.REGISTRY_PATH = registry
    retriever = None
    try:
        resolved = scopes.resolve_scope(SCOPE)
        with scopes.activate(resolved):
            retriever = Retriever(resolved.config_path)
        app = create_app(cfg_path, scope=SCOPE, retriever=retriever, provider=provider, llm=llm, load_env=False,
                         governance_register=None, web_dist=work / "nodist", cache_path=work / "cache" / "answers.db")
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        scopes.REGISTRY_PATH = previous_registry
        scopes.set_active(previous_active)
        if retriever is not None:
            try:
                retriever.close()
            except Exception:  # noqa: BLE001 - closing a read-only connection never fails a run
                pass


def sample_pages(conn, count: int, rng: random.Random, *, quality: float, exclude: set) -> list:
    """Passages chosen at random by rowid, one per item, with at least 80 words and OCR quality at or
    above `quality`. Unlike the benchmark's sampler it keeps undated items and unknown places, since
    some shards hold nothing else."""
    previous_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    top = conn.execute("SELECT max(rowid) FROM passages").fetchone()[0] or 0
    out, seen = [], set(exclude)
    for _ in range(40):
        if len(out) >= count or not top:
            break
        rowids = rng.sample(range(1, top + 1), min(top, 400))
        marks = ",".join("?" * len(rowids))
        rows = conn.execute(
            "SELECT p.passage_id, p.item_id, p.leaf_index, p.text, p.token_count, p.ocr_quality, i.title, i.year, "
            f"i.jurisdiction_norm FROM passages p JOIN items i ON i.item_id = p.item_id WHERE p.rowid IN ({marks})",
            rowids).fetchall()
        for row in rows:
            if row["item_id"] in seen or float(row["ocr_quality"] or 0) < quality or (row["token_count"] or 0) < 80:
                continue
            seen.add(row["item_id"])
            out.append(generator._source(row))
            if len(out) >= count:
                break
    conn.row_factory = previous_factory
    return out


# ---------------------------------------------------------------- the run

class ShardAudit:
    """One shard's audit. `store` is R2 (or a local store in tests); `drafter`, `writer_factory`
    and `judge` can be replaced by stubs."""

    def __init__(self, sid: str, store, work: Path, *, ledger: Optional[Ledger] = None, drafter=None,
                 writer_factory: Callable = rb.real_writer, judge: Optional[Callable] = None, stub: bool = False,
                 log: Callable = print):
        self.sid, self.store, self.work, self.log, self.stub = sid, store, Path(work), log, stub
        self.run_id = f"audit-{sid}"
        self.run_dir = self.work / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state_prefix = f"{AUDIT_PREFIX}/{sid}/state"
        self._sync_lock = threading.Lock()
        self.restore_state()
        self.ledger = ledger if ledger is not None else R2Ledger(store, self.work / "ledger.jsonl",
                                                                   after_write=self.sync_state)
        self.cfg = judges.load_panel()
        self.drafter = drafter
        self.writer_factory = writer_factory
        self.judge = judge

    # state on R2 -----------------------------------------------------------------------------
    STATE_FILES = ("questions.jsonl", "answers.jsonl", "judge_items.jsonl", "gates.jsonl", "judgments.jsonl",
                   "run.json")

    def restore_state(self) -> None:
        for key in self.store.list(self.state_prefix + "/"):
            name = key.rsplit("/", 1)[-1]
            path = self.run_dir / name
            if not path.exists():
                path.write_bytes(self.store.get(key))

    def sync_state(self) -> None:
        with self._sync_lock:
            for path in sorted(self.run_dir.iterdir()):
                if path.name in self.STATE_FILES or (path.name.startswith("batch_") and path.suffix == ".json"):
                    self.store.put(f"{self.state_prefix}/{path.name}", path.read_bytes())
            have = {p.name for p in self.run_dir.iterdir()}
            for key in list(self.store.list(self.state_prefix + "/")):
                name = key.rsplit("/", 1)[-1]
                if name.startswith("batch_") and name not in have and hasattr(self.store, "client"):
                    self.store.client.delete_object(Bucket=self.store.bucket, Key=key)

    # stages -----------------------------------------------------------------------------------
    def engine_config(self) -> tuple:
        from archive_debugger.generate.cli import load_generate_config
        gcfg = load_generate_config(ENGINE_CONFIG)
        writer = gcfg["model"]
        cfg_path = rb.write_engine_config(ENGINE_CONFIG, self.work / "engine.toml", answer_version="v1",
                                          model=writer, effort=None)
        return cfg_path, load_generate_config(cfg_path), writer, gcfg.get("provider") or "anthropic"

    def sentences_so_far(self) -> int:
        rows = rb.latest_rows(self.run_dir / "answers.jsonl")
        return sum(len(r.get("sentences") or []) for r in rows.values()
                   if r.get("error") is None and r.get("refused") is False)

    def questions(self, conn, target_questions: int) -> list:
        """Drafted questions, in order, read from questions.jsonl and drafted further as needed."""
        path = self.run_dir / "questions.jsonl"
        have = read_jsonl(path) if path.exists() else []
        if len(have) >= target_questions:
            return have
        rng = random.Random(f"{SEED}:{self.sid}:{len(have)}")
        used = {q["sources"][0]["item_id"] for q in have}
        for quality in (0.66, 0.5, 0.0):
            pages = sample_pages(conn, (target_questions - len(have)) * 2, rng, quality=quality, exclude=used)
            for page in pages:
                if len(have) >= target_questions:
                    break
                d = self.drafter.draft("answerable", [page])
                if d is None:
                    continue
                checks = [generator.quote_gate(d["answer_quote"], [page]), generator.question_gate(d["question"])]
                if not all(c["passed"] for c in checks):
                    continue
                n = len(have) + 1
                q = {"item_id": f"{self.sid}:q{n:04d}", "collection": self.sid, "category": "answerable",
                     "question": d["question"], "filters": {}, "sources": [page], "corpus_checks": checks,
                     "label": {"verdict": "SUPPORTED", "should_refuse": False}, "status": "model-drafted",
                     "drafter": self.drafter.model, "draft_prompt_version": generator.DRAFT_PROMPT_VERSION}
                append_jsonl(path, q)
                have.append(q)
                used.add(page["item_id"])
            if len(have) >= target_questions:
                break
        return have

    def answer(self, target: int, cap: float) -> Optional[str]:
        """Draft and answer until the answers hold `target` cited sentences (or the question budget is
        spent). Returns why it stopped early at the cap, else None."""
        from archive_debugger.eval.rundb import open_corpus_read_only
        cfg_path, gcfg, writer, provider = self.engine_config()
        self.writer = writer
        db, vec = shard_files(self.store, self.sid, self.work)
        conn = open_corpus_read_only(str(db))
        y = DEFAULT_YIELD
        max_questions = max(10, int(math.ceil(target / (y["answered"] * y["sentences_per_answer"]) * 2)))
        answers_path = self.run_dir / "answers.jsonl"
        model = rb.price_model(writer)
        llm = self.writer_factory("v1", writer, None, self.stub, gcfg)
        try:
            with shard_engine(self.work, cfg_path, db, vec, llm, "stub" if self.stub else provider) as client:
                batch = 0
                while self.sentences_so_far() < target:
                    done = rb.latest_rows(answers_path)
                    asked = len(done)
                    if asked >= max_questions:
                        self.log(f"{self.sid}: {asked} questions asked, {self.sentences_so_far()} sentences; stopping")
                        break
                    batch = min(max_questions, asked + 10)
                    qs = self.questions(conn, batch)
                    todo = [q for q in qs if q["item_id"] not in done]
                    if not todo:
                        self.log(f"{self.sid}: no more questions could be drafted")
                        break
                    for q in todo:
                        if self.sentences_so_far() >= target:
                            break
                        try:
                            row = rb.ask(client, q, SCOPE, llm, pipeline="v1", writer=writer, effort=None, model=model,
                                         gcfg=gcfg, stub=self.stub, ledger=self.ledger, run_id=self.run_id, cap=cap)
                        except BudgetExceeded as exc:
                            return str(exc)
                        append_jsonl(answers_path, row)
                        self.sync_state()
                        self.log(f"  {q['item_id']}: {row['state'] or row['error']} "
                                 f"({len(row.get('sentences') or [])} sentences, ${row['usd']:.4f})")
        finally:
            conn.close()
        return None

    def judge_items(self) -> list:
        from archive_debugger.eval.rundb import open_corpus_read_only
        path = self.run_dir / "judge_items.jsonl"
        if path.exists():
            return read_jsonl(path)
        db = self.work / "data" / "civic.db"
        items = [it for it in rb.build_judge_items(self.run_dir, connect=lambda _c: open_corpus_read_only(str(db)))
                 if it["kind"] == "sentence"]
        write_jsonl(path, items)
        self.sync_state()
        return items

    def gate_rows(self, items: list) -> dict:
        from archive_debugger.eval.rundb import open_corpus_read_only
        path = self.run_dir / "gates.jsonl"
        rows = {g["item_id"]: g for g in read_jsonl(path)} if path.exists() else {}
        if set(rows) != {it["item_id"] for it in items}:
            conn = open_corpus_read_only(str(self.work / "data" / "civic.db"))
            try:
                rows = {it["item_id"]: gates.run_gates(conn, it) for it in items}
            finally:
                conn.close()
            write_jsonl(path, rows.values())
            self.sync_state()
        return rows

    def run_judges(self, items: list, cap: float) -> Optional[str]:
        from archive_debugger.audit.run import good_judgments, run_judge
        (a, b), esc = self.cfg.route(CHECK)
        conflicts = judges.writer_conflicts(self.cfg, items, include_escalation=False)
        if conflicts:
            raise SystemExit(f"refused: {conflicts} wrote these answers and may not judge them")
        judgments = self.run_dir / "judgments.jsonl"
        try:
            for name in (a, b):
                done = good_judgments(judgments)
                pending = [it for it in items if (it["item_id"], name) not in done]
                if not pending:
                    continue
                self.log(f"{self.sid}: {name} judges {len(pending)} sentences")
                if self.judge is not None:
                    self.judge(self.cfg.specs[name], pending, self.run_dir, self.ledger, self.run_id, cap)
                else:
                    run_judge(self.cfg.specs[name], pending, self.run_dir, self.ledger, self.run_id, cap,
                              log=self.log, gateway=self.cfg.workers_ai_gateway)
                self.sync_state()
        except BudgetExceeded as exc:
            self.sync_state()
            return str(exc)
        return None

    def decisions(self, items: list, gate_rows: dict) -> list:
        from archive_debugger.audit.run import good_judgments
        done = good_judgments(self.run_dir / "judgments.jsonl")
        route = self.cfg.route(CHECK)
        routes = {c: route for c in prompts.KIND_CHECKS["sentence"]}
        names = list(route[0]) + ([route[1]] if route[1] else [])
        return [panel.decide_routes(it, gate_rows[it["item_id"]], routes, {n: done.get((it["item_id"], n)) for n in names})
                for it in items]

    def result(self, items: list, decisions: list, sizing: dict, calibration_status: Optional[dict]) -> dict:
        finals = {d["item_id"]: d["checks"][CHECK]["final"] for d in decisions}
        decided = [f for f in finals.values() if f is not None]
        passes = sum(1 for f in decided if f == "pass")
        low, high = calibration.wilson(passes, len(decided)) if decided else (None, None)
        by_q: dict = {}
        for it in items:
            f = finals.get(it["item_id"])
            if f is not None:
                by_q.setdefault(it["qid"], []).append(1 if f == "pass" else 0)
        clusters = list(by_q.values())
        boot = cluster_bootstrap(clusters, seed=SEED)
        totals = self.ledger.totals(self.run_id)
        rows = rb.latest_rows(self.run_dir / "answers.jsonl")
        valid = {}
        gate_path = self.run_dir / "gates.jsonl"
        for g in (read_jsonl(gate_path) if gate_path.exists() else []):
            valid[g["valid"]] = valid.get(g["valid"], 0) + 1
        (a, b), _ = self.cfg.route(CHECK)
        out = {
            "format": 1, "shard_id": self.sid, "run_id": self.run_id, "check": CHECK, "finished_at": now_iso(),
            "sentences_judged": len(items), "decided": len(decided), "undecided": len(items) - len(decided),
            "pass": passes, "partial": sum(1 for f in decided if f == "partial"),
            "fail": sum(1 for f in decided if f == "fail"),
            "supports_strict": {"value": round(passes / len(decided), 4) if decided else None,
                                "wilson95": [round(low, 4), round(high, 4)] if decided else None,
                                "question_clustered_bootstrap95": boot, "questions": len(clusters),
                                "note": "pass among decided sentences; undecided sentences wait for adjudication and "
                                        "are not counted"},
            "valid_gate": valid,
            "questions_asked": len(rows),
            "answered": sum(1 for r in rows.values() if r.get("error") is None and r.get("refused") is False),
            "refused": sum(1 for r in rows.values() if r.get("refused") is True),
            "errors": sum(1 for r in rows.values() if r.get("error")),
            "spend": {"usd": round(totals.spent, 6), "by_provider": {k: round(v, 6) for k, v in totals.by_provider.items()},
                      "open_reservations_usd": round(totals.reserved, 6), "ledger": LEDGER_KEY, "phase": PHASE,
                      "phase_cap_usd": TOTAL_CAP_USD},
            "sizing": sizing,
            "writer": {"model": getattr(self, "writer", None), "pipeline": "v1", "engine_config": "config/shards/engine.toml"},
            "drafter": {"model": getattr(self.drafter, "model", None), "task": "answerable",
                        "draft_prompt_version": generator.DRAFT_PROMPT_VERSION, "generator_version": generator.GENERATOR_VERSION},
            "panel": {"judges": [a, b], "models": [self.cfg.specs[a].model, self.cfg.specs[b].model],
                      "escalation": None, "panel_version": panel.PANEL_VERSION,
                      "judge_prompt_version": prompts.version_for("sentence"), "gate_version": gates.GATE_VERSION},
            "price_version": prices.PRICE_VERSION, "seed": SEED, "stub": self.stub,
        }
        out["tier"], out["tier_reason"] = tier_for(out, calibration_status)
        out["calibration"] = calibration_summary(calibration_status)
        return out

    def run(self) -> int:
        result_key = f"{AUDIT_PREFIX}/{self.sid}/result.json"
        if self.store.head(result_key) is not None:
            self.log(f"{self.sid}: already audited ({result_key})")
            return 0
        sizing = size_for(self.store, self.ledger, self.sid)
        self.log(f"{self.sid}: target {sizing['target']} sentences (ideal {sizing['ideal']}); "
                 f"${sizing['usd_left']:.2f} left for {sizing['shards_left']} shards; {sizing['basis']}")
        if sizing["target"] <= 0 or sizing["too_small"]:
            self.log(f"{self.sid}: refused: the money left gives {sizing['target']} sentences, under {MIN_SENTENCES}")
            return 2
        target = sizing["target"]
        # The shard's share is set by the sentence target; the run cap only has to leave room for a whole
        # Anthropic batch's worst case (60 items at full max_tokens, far above what they spend), so it is
        # what is left under the total cap, which the ledger's phase cap enforces in any case.
        run_cap = sizing["usd_left"]
        if self.drafter is None:
            spec = self.cfg.specs[DRAFTER]
            self.drafter = generator.Drafter(spec.model, self.ledger, self.run_id, run_cap,
                                             gateway=self.cfg.workers_ai_gateway, max_tokens=1500,
                                             cache_path=self.run_dir / "drafts_cache.jsonl")
        stopped = self.answer(target, run_cap)
        if stopped:
            self.log(f"STOPPED before a call that could cross a cap: {stopped}. Rerun to resume.")
            return 2
        items = self.judge_items()
        if not items:
            self.log(f"{self.sid}: no answer kept a cited sentence; nothing to judge")
        gate_rows = self.gate_rows(items)
        stopped = self.run_judges(items, run_cap)
        if stopped:
            self.log(f"STOPPED before a call that could cross a cap: {stopped}. Rerun to resume.")
            return 2
        decisions = self.decisions(items, gate_rows)
        undecided = [{"item": it, "decision": d} for it, d in zip(items, decisions) if d["checks"][CHECK]["final"] is None]
        self.store.put(f"{AUDIT_PREFIX}/{self.sid}/undecided.jsonl",
                       "".join(json.dumps(u, sort_keys=True) + "\n" for u in undecided).encode("utf-8"))
        self.store.put(f"{AUDIT_PREFIX}/{self.sid}/decisions.jsonl",
                       "".join(json.dumps(d, sort_keys=True) + "\n" for d in decisions).encode("utf-8"))
        result = self.result(items, decisions, sizing, load_calibration(self.store))
        self.store.put(result_key, json.dumps(result, indent=1, sort_keys=True).encode("utf-8"))
        s = result["supports_strict"]
        self.log(f"{self.sid}: SUPPORTS {s['value']} {s['wilson95']} over {result['decided']} decided sentences, "
                 f"{result['undecided']} undecided; spend ${result['spend']['usd']:.4f}; tier {result['tier']} "
                 f"({result['tier_reason']})")
        return 0


def cluster_bootstrap(clusters: list, *, seed: int, resamples: int = 2000) -> Optional[list]:
    """A 95% interval on the pass rate resampling whole questions (sentences of one answer are not
    independent)."""
    if len(clusters) < 2:
        return None
    rng = random.Random(seed)
    rates = []
    for _ in range(resamples):
        pick = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        den = sum(len(c) for c in pick)
        rates.append(sum(sum(c) for c in pick) / den if den else 0.0)
    rates.sort()
    return [round(rates[int(0.025 * resamples)], 4), round(rates[int(0.975 * resamples) - 1], 4)]


# ---------------------------------------------------------------- tiers

def load_calibration(store) -> Optional[dict]:
    if store.head(CALIBRATION_KEY) is None:
        return None
    return json.loads(store.get(CALIBRATION_KEY))


def calibration_summary(status: Optional[dict]) -> Optional[dict]:
    if not status:
        return None
    check = ((status.get("checks") or {}).get(CHECK) or {}).get("status") or {}
    silver = status.get("silver_error_random_agreed") or {}
    return {"supports_status": check.get("status"), "supports_ai_audited": check.get("ai_audited"),
            "why": check.get("why"), "silver_error_meets": silver.get("meets"), "silver_error_wilson": silver.get("wilson"),
            "queue_version": status.get("queue_version"), "published_at": status.get("published_at")}


def tier_for(result: dict, status: Optional[dict]) -> tuple:
    """(tier, why). AI-AUDITED needs the current calibration to say the SUPPORTS check meets the bar
    and the silver error rule holds, and every judged sentence decided; anything less is INDEXED."""
    if not status:
        return "INDEXED", "no calibration status on R2 (publish-calibration): no accuracy claim"
    summary = calibration_summary(status)
    if not summary["supports_ai_audited"]:
        return "INDEXED", f"the current calibration does not let SUPPORTS claim AI-AUDITED: {summary['why']}"
    if summary["silver_error_meets"] is not True:
        return "INDEXED", "the silver error rule does not hold in the current calibration"
    if result.get("undecided"):
        return "INDEXED", f"{result['undecided']} judged sentences are undecided and wait for adjudication"
    if not result.get("decided"):
        return "INDEXED", "no sentence was judged"
    return "AI-AUDITED", "the SUPPORTS panel meets the bar in the current calibration and every sentence is decided"


# ---------------------------------------------------------------- commands

def cmd_estimate(args) -> int:
    store = r2_store()
    ledger = R2Ledger(store, Path(tempfile.mkdtemp(prefix="audit-ledger-")) / "ledger.jsonl")
    s = size_for(store, ledger)
    planned = len(planned_shards())
    print(json.dumps({**s, "shards_planned": planned, "cap_usd": TOTAL_CAP_USD,
                      "over_cap_at_target": s["cost_at_target_all_left"] > TOTAL_CAP_USD - s["usd_committed"] - SAFETY_USD},
                     indent=1))
    if s["target"] < TARGET_SENTENCES:
        print(f"At {TARGET_SENTENCES} sentences every shard left would cost about ${s['cost_at_target_all_left']:.2f}, "
              f"over the ${s['usd_left']:.2f} left under the cap; each shard gets {s['target']} sentences instead, "
              f"about +-{100 * s['half_width_at_target']:.1f} points at a rate of {EXPECTED_RATE} "
              f"(+-{100 * s['half_width_at_ideal']:.1f} at the ideal).")
    return 0


def cmd_pending(args) -> int:
    store = r2_store()
    done = audited_shards(store)
    print(json.dumps([s for s in built_shards(store) if s not in done][: args.max]))
    return 0


def cmd_run(args) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    store = r2_store()
    work = Path(args.work or tempfile.mkdtemp(prefix=f"audit-{args.shard}-"))
    os.environ.setdefault("CIVIC_DENSE_BACKEND", "numpy")
    os.environ.pop("CIVIC_CACHE_URL", None)
    return ShardAudit(args.shard, store, work).run()


def cmd_tiers(args) -> int:
    store = r2_store()
    status = load_calibration(store)
    served = {}
    served_path = REPO / "config" / "shards" / "served.toml"
    if served_path.exists():
        import tomllib
        with served_path.open("rb") as fh:
            served = tomllib.load(fh).get("scopes") or {}
    for sid, result in sorted(audited_shards(store).items()):
        tier, why = tier_for(result, status)
        current = (served.get(sid) or {}).get("tier")
        line = f"{sid:32s} {tier:12s} served as {current or '-':12s} {why}"
        print(line)
        if args.apply and sid in served and current != tier:
            cmd = [sys.executable, str(REPO / "scripts" / "v2" / "serve_shards.py"), "tier", "--shard", sid, "--tier", tier]
            if tier == "AI-AUDITED":
                cmd += ["--audit", f"{AUDIT_PREFIX}/{sid}/result.json"]
            subprocess.run(cmd, check=True)
    return 0


def cmd_publish_calibration(args) -> int:
    store = r2_store()
    path = Path(args.status or CALIBRATION_FILE)
    status = json.loads(path.read_text(encoding="utf-8"))
    status["published_at"] = now_iso()
    store.put(CALIBRATION_KEY, json.dumps(status, indent=1, sort_keys=True).encode("utf-8"))
    print(json.dumps(calibration_summary(status), indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("estimate")
    p.set_defaults(fn=cmd_estimate)
    p = sub.add_parser("pending")
    p.add_argument("--max", type=int, default=41)
    p.set_defaults(fn=cmd_pending)
    p = sub.add_parser("run")
    p.add_argument("--shard", required=True)
    p.add_argument("--work", default=None, help="a working folder (default: a new temporary one)")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("tiers")
    p.add_argument("--apply", action="store_true", help="set served shards' tiers with serve_shards.py")
    p.set_defaults(fn=cmd_tiers)
    p = sub.add_parser("publish-calibration")
    p.add_argument("--status", default=None)
    p.set_defaults(fn=cmd_publish_calibration)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
