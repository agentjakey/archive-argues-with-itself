"""Answer the frozen v2 benchmark through the real engine, turn the answers into judge items, and score them.

    python scripts/v2/run_benchmark.py run --split dev --pipeline v2 --run-id dev-v2-haiku45 --cap 3.00
    python scripts/v2/run_benchmark.py run --split dev --pipeline v1 --run-id dev-v1 --cap 3.00
    python scripts/v2/run_benchmark.py run --split dev --pipeline v2 --stub --limit 6 --collections pilot --run-id smoke --cap 0.01
    python scripts/v2/run_benchmark.py judge-items --run-id dev-v2-haiku45
    python scripts/v2/run_benchmark.py score --runs dev-v1 dev-v2-haiku45 --audit bench-audit-1 --name dev-v1-vs-v2

run: the split file must match its sha256 in config/benchmark_v2.lock.json, and items in the versioned
exclusion list are dropped. The test split needs --final and runs once per pipeline label (a marker
under test_runs/ is written after a complete run). Each collection gets one engine (api/app.py
create_app) built from a temporary copy of its config with [generate] answer_version, model and effort
set as asked; the config files themselves are never changed. A collection's restricted items are asked
of a second engine whose governance register holds exactly those items' fixtures. Every item is asked
with nocache true, and the engine's answer cache lives in a temporary folder that is thrown away.
Paid calls go through the audit ledger under the run id: the worst case is reserved before each ask,
the actual tokens (v2) or the worst case marked estimated (v1, which reports no usage) are recorded
after it, and the reservation is released. A call that could cross the run cap or the phase cap is not
made: the run stops there and keeps what it did, and the same command resumes it. --stub uses a stub
writer that cites the first passage it is given: no paid call, nothing written to the ledger.

judge-items: the answered (not refused) rows of a run as audit judge items (docs/formats/audit.md,
format 2): an answer item per answer and a sentence item per kept sentence, with the full text of its
cited passages read from the collection corpus (read-only). The qid is "<run id>/<benchmark item id>",
so item ids never collide across runs.

score: per run, the refusal rate on should-refuse items, the false refusal rate, state accuracy by
category, the expected x produced confusion table, the strict SUPPORTS rate and the ANSWERS failure rate
from the audit panel's final verdicts, the share left to a person, cost per answer and latency p50/p95.
Rates carry Wilson 95% intervals; two runs over the same items get paired bootstrap 95% intervals on
each difference (second minus first).

Outputs live under reports/v2/benchmark/ (or --out): runs/<run id>/{answers.jsonl, run.json,
judge_items.jsonl}, test_runs/<pipeline label>.json and scores/<name>/{scores.json, scores.md}."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger import governance, scopes  # noqa: E402
from archive_debugger.audit import calibration, prices  # noqa: E402
from archive_debugger.audit import items as audit_items  # noqa: E402
from archive_debugger.audit.budget import BudgetExceeded, Ledger  # noqa: E402
from archive_debugger.audit.records import append_jsonl, read_jsonl, write_jsonl  # noqa: E402
from archive_debugger.generate import answer_v2  # noqa: E402
from archive_debugger.generate.cli import load_generate_config, sent_temperature  # noqa: E402

NL = chr(10)
DEFAULT_OUT = REPO / "reports" / "v2" / "benchmark"
DEFAULT_LOCK = REPO / "config" / "benchmark_v2.lock.json"
DEFAULT_SPLITS = REPO / "reports" / "v2" / "benchmark" / "v2"
DEFAULT_LEDGER = REPO / "reports" / "v2" / "audit" / "ledger.jsonl"
DEFAULT_AUDIT_DIR = REPO / "reports" / "v2" / "audit"
SPLITS = ("dev", "validation", "test")
PIPELINES = ("v1", "v2")
EFFORT_MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
PASSAGE_CHARS = 2500             # the worst case assumes every passage given to the writer is this long
PASSAGE_HEADER_CHARS = 300       # and each carries a citation line about this long
STUB_SENTENCE = "Stub answer written without a model call, citing the first passage it was given."
LIMIT_SEED = 20261104
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20261105
RUN_ID = re.compile("^[A-Za-z0-9][A-Za-z0-9._-]*$")
RESUME_KEYS = ("split", "pipeline", "writer", "effort", "stub", "collections", "limit", "seed")


class Refused(Exception):
    """The run cannot go ahead as asked (a changed split, a second final run, a bad option)."""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit() -> dict:
    def git(*args):
        try:
            out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None
    status = git("status", "--porcelain", "--untracked-files=no")
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(status) if status is not None else None}


# ---------------------------------------------------------------- the frozen split

def load_split(split: str, lock_path: Path = DEFAULT_LOCK, splits_dir: Path = DEFAULT_SPLITS) -> tuple:
    """(items with exclusions dropped, facts about the split) after checking the file's sha256
    against the lock. A changed split file is refused, never answered."""
    if split not in SPLITS:
        raise Refused(f"unknown split {split!r}")
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    entry = (lock.get("splits") or {}).get(split)
    if not entry or not entry.get("sha256"):
        raise Refused(f"{lock_path} has no sha256 for the {split} split")
    path = Path(splits_dir) / f"{split}.jsonl"
    if not path.exists():
        raise Refused(f"split file {path} is missing")
    actual = sha256_file(path)
    if actual != entry["sha256"]:
        raise Refused(f"{path} has sha256 {actual}, the lock says {entry['sha256']}: the frozen split changed; refusing")
    exclusions_path = Path(lock.get("exclusions") or "config/benchmark_v2_exclusions.json")
    if not exclusions_path.is_absolute():
        exclusions_path = REPO / exclusions_path
    exclusions = json.loads(exclusions_path.read_text(encoding="utf-8")) if exclusions_path.exists() else {}
    if exclusions and lock.get("set_sha256") and exclusions.get("set_sha256") not in (None, lock["set_sha256"]):
        raise Refused(f"{exclusions_path} belongs to another benchmark set ({exclusions.get('set_sha256')})")
    excluded = {str(e["item_id"]) for e in exclusions.get("excluded") or []}
    rows = read_jsonl(path)
    if entry.get("items") is not None and len(rows) != int(entry["items"]):
        raise Refused(f"{path} holds {len(rows)} items, the lock says {entry['items']}")
    kept = [r for r in rows if r["item_id"] not in excluded]
    facts = {"split": split, "split_path": str(path), "split_sha256": actual, "lock_path": str(lock_path),
             "items_in_split": len(rows), "excluded": sorted(excluded & {r["item_id"] for r in rows}),
             "exclusions_version": exclusions.get("version")}
    return kept, facts


def pick_subset(items: list, limit: Optional[int], seed: int) -> list:
    """A seeded random `limit` of the items, kept in split order (all of them when limit is None)."""
    if limit is None or limit >= len(items):
        return list(items)
    if limit <= 0:
        raise Refused("--limit must be positive")
    chosen = set(random.Random(seed).sample([it["item_id"] for it in items], limit))
    return [it for it in items if it["item_id"] in chosen]


# ---------------------------------------------------------------- writers and prices

def price_model(writer: str) -> str:
    """The prices table's name for a writer model id: a dated id maps to its undated name."""
    return re.sub("-[0-9]{8}$", "", writer)


def pipeline_label(pipeline: str, writer: str, effort: Optional[str], stub: bool) -> str:
    label = f"{pipeline}-{price_model(writer)}"
    if effort:
        label += f"-{effort}"
    if stub:
        label += "-stub"
    return label


def _first_passage_id(user_prompt: str) -> Optional[str]:
    for line in user_prompt.splitlines():
        if line.startswith("[") and "]" in line:
            return line[1:line.index("]")]
    return None


class EchoStubWriter(answer_v2.StubWriter):
    """The v2 stub writer for --stub: one sentence citing the first passage it is given, proposed as
    an answer. No model is called; last_usage stays empty."""

    def __init__(self):
        super().__init__(answer_v2.Draft2(sentences=[], evidence_state="insufficient", state_reason="stub writer"))

    def draft(self, system: str, user: str) -> answer_v2.Draft2:
        self.calls += 1
        self.last_usage = {}
        pid = _first_passage_id(user)
        if pid is None:
            return answer_v2.Draft2(sentences=[], evidence_state="insufficient", state_reason="stub writer: no passages")
        return answer_v2.Draft2(sentences=[answer_v2.CitedSentence2(text=STUB_SENTENCE, cited_ids=[pid])],
                                evidence_state="answers", state_reason="stub writer: no model was called")


class EchoStubLLM:
    """The v1 stub for --stub: the same single sentence through the frozen v1 Draft shape."""

    def __init__(self):
        self.calls = 0

    def draft(self, system: str, user: str):
        from archive_debugger.generate.llm import CitedSentence, Draft
        self.calls += 1
        pid = _first_passage_id(user)
        return Draft(sentences=[CitedSentence(text=STUB_SENTENCE, cited_ids=[pid])] if pid else [])


class CountingLLM:
    """Wraps the frozen v1 AnthropicLLM to count calls (v1 reports no token usage)."""

    def __init__(self, inner):
        self.inner, self.calls = inner, 0

    def draft(self, system: str, user: str):
        self.calls += 1
        return self.inner.draft(system, user)


class MeteredWriter(answer_v2.AnthropicWriter):
    """The real v2 writer, counting calls and clearing the usage before each one, so a failed call
    never reports the tokens of the call before it."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = 0

    def draft(self, system: str, user: str):
        self.calls += 1
        self.last_usage = {}
        return super().draft(system, user)


def real_writer(pipeline: str, writer: str, effort: Optional[str], stub: bool, gcfg: dict):
    """The writer handed to the engine: a stub for --stub, else the real Anthropic writer (v2) or
    the frozen v1 model through a client with a 60 s timeout and no SDK retries."""
    if stub:
        return EchoStubWriter() if pipeline == "v2" else EchoStubLLM()
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise Refused("no Anthropic key in the environment or .env; use --stub for a run without paid calls")
    if pipeline == "v2":
        return MeteredWriter(writer, gcfg["max_tokens"], effort=effort, timeout=60.0)
    import anthropic
    from archive_debugger.generate.llm import AnthropicLLM
    client = anthropic.Anthropic(timeout=60.0, max_retries=0)
    return CountingLLM(AnthropicLLM(writer, gcfg["max_tokens"], client=client,
                                    temperature=sent_temperature("anthropic", gcfg)))


def worst_case_usd(model: str, question: str, top_k: int, max_tokens: int) -> tuple:
    """(input tokens, output tokens, usd) of the most an ask can cost: the system prompt, the
    question and top_k passages of PASSAGE_CHARS with their citation lines in, max_tokens out."""
    chars = len(answer_v2.SYSTEM) + len(question) + top_k * (PASSAGE_CHARS + PASSAGE_HEADER_CHARS)
    input_tokens = prices.estimate_input_tokens("x" * chars)
    return input_tokens, max_tokens, prices.cost(model, input_tokens, max_tokens)


# ---------------------------------------------------------------- the engine

def collection_config(collection: str) -> Path:
    entry = (scopes.load_registry().get("scopes") or {}).get(collection)
    if not entry:
        raise Refused(f"collection {collection!r} is not a scope in config/scopes.toml")
    return REPO / entry["config"]


def write_engine_config(source: Path, dest: Path, *, answer_version: str, model: str, effort: Optional[str]) -> Path:
    """A copy of a collection config with [generate] answer_version, model and effort set. Every
    other line is kept as it is."""
    out, section, placed = [], None, False
    for line in Path(source).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped
            out.append(line)
            if section == "[generate]":
                out.append(f'answer_version = "{answer_version}"')
                out.append(f'model = "{model}"')
                if effort:
                    out.append(f'effort = "{effort}"')
                placed = True
            continue
        if section == "[generate]":
            key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
            if key in ("answer_version", "model", "effort"):
                continue
        out.append(line)
    if not placed:
        raise Refused(f"{source} has no [generate] section")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline=NL) as fh:
        fh.write(NL.join(out) + NL)
    return dest


def _registry_pointing_at(collection: str, config_path: Path, dest: Path) -> Path:
    """A copy of config/scopes.toml whose entry for the collection names the temporary config."""
    lines, inside, done = [], False, False
    source = Path(scopes.REGISTRY_PATH)
    if not source.is_absolute():
        source = REPO / source
    for line in source.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            inside = stripped == f"[scopes.{collection}]"
        if inside and not done and stripped.startswith("config") and stripped.split("=", 1)[0].strip() == "config":
            line = f'config = "{Path(config_path).resolve().as_posix()}"'
            done = True
        lines.append(line)
    if not done:
        raise Refused(f"config/scopes.toml has no config line for {collection}")
    with Path(dest).open("w", encoding="utf-8", newline=NL) as fh:
        fh.write(NL.join(lines) + NL)
    return Path(dest)


class RealEngines:
    """Opens the engine for each collection: one Retriever per collection, shared by the main and the
    restricted app, under a temporary scope registry that points the collection at its temporary
    config. The answer cache lives in the work folder and is discarded with it."""

    def __init__(self, work_dir: Path):
        self.work_dir = Path(work_dir)
        self.retrievers: dict = {}
        self.count = 0

    @contextmanager
    def __call__(self, collection: str, cfg_path: Path, register, llm, provider: str):
        from fastapi.testclient import TestClient
        from archive_debugger.api.app import create_app
        from archive_debugger.retrieve.search import Retriever
        self.count += 1
        registry = _registry_pointing_at(collection, cfg_path, self.work_dir / f"scopes.{collection}.toml")
        previous_registry, previous_active = scopes.REGISTRY_PATH, scopes.active_scope()
        scopes.REGISTRY_PATH = registry
        try:
            resolved = scopes.resolve_scope(collection)
            if collection not in self.retrievers:
                if not Path(resolved.db_path).exists() or not Path(resolved.index_path).exists():
                    raise Refused(f"the {collection} corpus is missing ({resolved.db_path}, {resolved.index_path})")
                with scopes.activate(None if resolved.inherit else resolved):
                    self.retrievers[collection] = Retriever(resolved.config_path)
            app = create_app(cfg_path, scope=collection, retriever=self.retrievers[collection], provider=provider,
                             llm=llm, load_env=False, governance_register=register,
                             web_dist=self.work_dir / "nodist",
                             cache_path=self.work_dir / "cache" / f"{collection}-{self.count}.db")
            with TestClient(app, raise_server_exceptions=False) as client:
                yield client
        finally:
            scopes.REGISTRY_PATH = previous_registry
            scopes.set_active(previous_active)

    def close(self) -> None:
        for r in self.retrievers.values():
            try:
                r.close()
            except Exception:  # noqa: BLE001 - closing a read-only connection never fails a run
                pass
        self.retrievers = {}


# ---------------------------------------------------------------- answers

def state_of(pipeline: str, body: dict) -> tuple:
    """(state, error) for one engine response. A limited-mode response is an error, not a state. v1
    has no states: RESTRICTED when a governance block came back with no answer, INSUFFICIENT_EVIDENCE
    when it abstained, SUPPORTED otherwise."""
    if not isinstance(body, dict) or not isinstance(body.get("answer"), dict):
        return None, "no answer in the response"
    if body.get("degraded"):
        return None, f"degraded:{body['degraded'].get('reason')}"
    answer = body["answer"]
    if pipeline == "v2":
        state = answer.get("state")
        if state not in answer_v2.STATES:
            return None, f"unknown state {state!r}"
        return state, None
    if body.get("governance") and answer.get("abstained"):
        return "RESTRICTED", None
    if answer.get("abstained"):
        return "INSUFFICIENT_EVIDENCE", None
    return "SUPPORTED", None


def restricted_items(items: list) -> list:
    return [it for it in items if it.get("governance")]


def fixture_register(items: list):
    """A register holding exactly these items' fixture policies (one copy of each policy id)."""
    records: dict = {}
    for it in items:
        for record in it.get("governance") or []:
            records.setdefault(record["policy_id"], record)
    return governance.from_records(list(records.values()), fixtures=True)


def answer_row(item: dict, body: Optional[dict], error: Optional[str], *, pipeline: str, writer: str,
               effort: Optional[str], latency: float, usage: dict, usd: float, model_called: bool) -> dict:
    state, state_error = (None, error) if error else state_of(pipeline, body)
    answer = (body or {}).get("answer") or {}
    evidence = (body or {}).get("evidence") or []
    retrieved = [e["passage_id"] for e in evidence if e.get("in_prompt")]
    return {
        "item_id": item["item_id"], "collection": item["collection"], "category": item["category"],
        "question": item["question"], "filters": item.get("filters") or {},
        "expected_verdict": item["label"]["verdict"], "should_refuse": bool(item["label"]["should_refuse"]),
        "pipeline": pipeline, "writer": writer, "effort": effort,
        "state": state, "refused": None if state is None else answer_v2.refused(state),
        "proposed_state": answer.get("proposed_state"), "state_reason": answer.get("state_reason"),
        "coverage_state": answer.get("coverage_state"), "gate_notes": answer.get("gate_notes"),
        "abstained": answer.get("abstained"),
        "governance_policies": [n.get("policy_id") for n in ((body or {}).get("governance") or {}).get("restricted") or []],
        "answer": answer.get("text"), "sentences": answer.get("sentences") or [],
        "verified_citations": answer.get("verified_citations") or [],
        "retrieved_ids": retrieved, "top10": retrieved[:10],
        "latency_s": round(latency, 3), "usage": usage, "usd": round(usd, 6), "model_called": model_called,
        "error": state_error, "answered_at": now_iso(),
    }


def latest_rows(path: Path) -> dict:
    """{item_id: the last row written for it}."""
    out: dict = {}
    for row in read_jsonl(path):
        out[row["item_id"]] = row
    return out


def run_benchmark(*, split: str, pipeline: str, run_id: str, cap: float, writer: Optional[str] = None,
                  effort: Optional[str] = None, limit: Optional[int] = None, seed: int = LIMIT_SEED,
                  collections: Optional[list] = None, stub: bool = False, final: bool = False,
                  out_root: Path = DEFAULT_OUT, lock_path: Path = DEFAULT_LOCK, splits_dir: Path = DEFAULT_SPLITS,
                  ledger: Optional[Ledger] = None, engine_factory: Optional[Callable] = None,
                  writer_factory: Callable = real_writer, log: Callable = print) -> int:
    """Answer the split's items; 0 when every item was answered, 1 when some came back with an
    error (a rerun asks them again), 2 when the run stopped before a call that could cross a cap."""
    if not RUN_ID.match(run_id or ""):
        raise Refused(f"run id {run_id!r}: use letters, digits, dot, dash and underscore")
    if pipeline not in PIPELINES:
        raise Refused(f"unknown pipeline {pipeline!r}")
    if effort and pipeline != "v2":
        raise Refused("--effort is for the v2 pipeline only")
    items, facts = load_split(split, lock_path, splits_dir)
    if collections:
        unknown = set(collections) - {it["collection"] for it in items}
        if unknown:
            raise Refused(f"no items in the {split} split for {sorted(unknown)}")
        items = [it for it in items if it["collection"] in collections]
    names = sorted({it["collection"] for it in items})
    configs = {c: collection_config(c) for c in names}
    gcfgs = {c: load_generate_config(configs[c]) for c in names}
    default_writers = {gcfgs[c]["model"] for c in names}
    if writer is None:
        if len(default_writers) != 1:
            raise Refused(f"the collections name different writers {sorted(default_writers)}; pass --writer")
        writer = default_writers.pop()
    model = price_model(writer)
    if effort and model not in EFFORT_MODELS:
        raise Refused(f"--effort applies to {EFFORT_MODELS}, not {writer}")
    if not stub:
        prices.price(model)       # an unpriced writer is refused before anything is asked
    label = pipeline_label(pipeline, writer, effort, stub)
    out_root = Path(out_root)
    marker = out_root / "test_runs" / f"{label}.json"
    if split == "test":
        if not final:
            raise Refused("the test split is answered once per pipeline; pass --final to mean it")
        if limit is not None:
            raise Refused("the final test run answers the whole split; --limit is for dev and validation")
        if marker.exists():
            raise Refused(f"{marker} exists: the test split was already answered for {label}")
    elif final:
        raise Refused("--final is only for the test split")
    items = pick_subset(items, limit, seed)

    run_dir = out_root / "runs" / run_id
    run_json = run_dir / "run.json"
    answers_path = run_dir / "answers.jsonl"
    config = {"split": split, "pipeline": pipeline, "writer": writer, "effort": effort, "stub": stub,
              "collections": names, "limit": limit, "seed": seed}
    if run_json.exists():
        before = json.loads(run_json.read_text(encoding="utf-8"))
        changed = [k for k in RESUME_KEYS if before.get("config", {}).get(k) != config[k]]
        if changed:
            raise Refused(f"run {run_id} exists with different {changed}; use a new run id")
    run_dir.mkdir(parents=True, exist_ok=True)
    own_engines = engine_factory is None
    if own_engines:
        os.environ.setdefault("CIVIC_DENSE_BACKEND", "numpy")     # the deploy's dense backend
        os.environ.pop("CIVIC_CACHE_URL", None)                   # the engine cache stays a local temp file
    if ledger is None and not stub:
        ledger = Ledger(DEFAULT_LEDGER)
    info = {"format": 1, "run_id": run_id, "pipeline_label": label, "config": config,
            "price_model": None if stub else model, "cap_usd": cap, **facts,
            "items": len(items), "answer_version": answer_v2.ANSWER_VERSION if pipeline == "v2" else "v1",
            "engine": {c: {"config": str(configs[c]), "max_tokens": gcfgs[c]["max_tokens"],
                           "top_k": gcfgs[c]["top_k"], "min_passages": gcfgs[c]["min_passages"]} for c in names},
            "dense_backend": os.environ.get("CIVIC_DENSE_BACKEND", "sqlite"),
            "ledger": None if stub else str(ledger.path), "metered": not stub, "git": git_commit(),
            "started_at": json.loads(run_json.read_text(encoding="utf-8")).get("started_at") if run_json.exists() else now_iso()}
    info["status"] = "running"
    run_json.write_text(json.dumps(info, indent=1, sort_keys=True), encoding="utf-8")

    done = {i for i, r in latest_rows(answers_path).items() if r.get("error") is None}
    todo = [it for it in items if it["item_id"] not in done]
    log(f"{run_id}: {len(items)} items ({len(done & {it['item_id'] for it in items})} already answered), "
        f"pipeline {label}, collections {names}")
    stopped = None
    with tempfile.TemporaryDirectory(prefix="bench-engine-") as work:
        if own_engines:
            engine_factory = RealEngines(Path(work))
        try:
            for collection in names:
                if stopped:
                    break
                pending = [it for it in todo if it["collection"] == collection]
                if not pending:
                    continue
                cfg_path = write_engine_config(configs[collection], Path(work) / f"{collection}.toml",
                                               answer_version=pipeline, model=writer, effort=effort)
                gcfg = load_generate_config(cfg_path)
                restricted = restricted_items(pending)
                groups = [(None, [it for it in pending if not it.get("governance")])]
                if restricted:
                    groups.append((fixture_register(restricted), restricted))
                for register, group in groups:
                    if stopped or not group:
                        continue
                    llm = writer_factory(pipeline, writer, effort, stub, gcfg)
                    with engine_factory(collection, cfg_path, register, llm, "stub" if stub else "anthropic") as client:
                        for it in group:
                            try:
                                row = ask(client, it, collection, llm, pipeline=pipeline, writer=writer, effort=effort,
                                          model=model, gcfg=gcfg, stub=stub, ledger=ledger, run_id=run_id, cap=cap)
                            except BudgetExceeded as exc:
                                stopped = str(exc)
                                break
                            append_jsonl(answers_path, row)
                            log(f"  {it['item_id']}: {row['state'] or row['error']} ({row['latency_s']:.1f} s, ${row['usd']:.4f})")
                        if stopped:
                            break
        finally:
            if own_engines:
                engine_factory.close()

    rows = latest_rows(answers_path)
    order = {it["item_id"]: n for n, it in enumerate(items)}
    kept = sorted((r for i, r in rows.items() if i in order), key=lambda r: order[r["item_id"]])
    write_jsonl(answers_path, kept)
    errors = [r["item_id"] for r in kept if r.get("error")]
    missing = [it["item_id"] for it in items if it["item_id"] not in rows]
    info["status"] = "stopped_at_cap" if stopped else ("errors" if errors or missing else "complete")
    info["stopped"] = stopped
    info["answered"] = len(kept) - len(errors)
    info["errors"] = errors
    info["unanswered"] = missing
    info["finished_at"] = now_iso()
    if ledger is not None:
        totals = ledger.totals(run_id)
        info["spend_usd"] = round(totals.spent, 6)
        info["open_reservations_usd"] = round(totals.reserved, 6)
    run_json.write_text(json.dumps(info, indent=1, sort_keys=True), encoding="utf-8")
    if stopped:
        log(f"STOPPED before a call that could cross a cap: {stopped}. Rerun the same command to resume.")
        return 2
    if errors or missing:
        log(f"{len(errors)} items came back with an error and {len(missing)} were not asked; rerun to ask them again.")
        return 1
    if split == "test":
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"run_id": run_id, "pipeline_label": label, "items": len(kept),
                                      "split_sha256": facts["split_sha256"], "finished_at": info["finished_at"],
                                      "git": info["git"]}, indent=1, sort_keys=True), encoding="utf-8")
    log(f"{run_id}: complete, {len(kept)} answers in {answers_path}")
    return 0


def ask(client, item: dict, collection: str, llm, *, pipeline: str, writer: str, effort: Optional[str], model: str,
        gcfg: dict, stub: bool, ledger: Optional[Ledger], run_id: str, cap: float) -> dict:
    """One item through the engine, metered: reserve the worst case, ask, record the spend, release."""
    reservation = None
    worst_in, worst_out, worst_usd = worst_case_usd(model, item["question"], gcfg["top_k"], gcfg["max_tokens"]) \
        if not stub else (0, 0, 0.0)
    if not stub:
        reservation = f"{run_id}:{item['item_id']}:{time.time():.3f}"
        ledger.reserve(run_id, cap, "anthropic", model, reservation, worst_usd)    # raises BudgetExceeded
    calls_before = getattr(llm, "calls", 0)
    body, error = None, None
    t0 = time.monotonic()
    try:
        resp = client.post("/ask", params={"scope": collection},
                           json={"question": item["question"], "filters": item.get("filters") or {}, "nocache": True})
        if resp.status_code == 200:
            body = resp.json()
        else:
            error = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001 - one failed ask is an error row, never the end of the run
        error = f"{type(exc).__name__}: {exc}"
    latency = time.monotonic() - t0
    model_called = getattr(llm, "calls", 0) > calls_before
    usage, usd = {}, 0.0
    try:
        if model_called and not stub:
            tokens = dict(getattr(llm, "last_usage", None) or {}) if pipeline == "v2" else {}
            if tokens.get("input_tokens") or tokens.get("output_tokens"):
                usage = {"input_tokens": int(tokens.get("input_tokens") or 0),
                         "output_tokens": int(tokens.get("output_tokens") or 0), "estimated": False}
                usd = ledger.spend(run_id, "anthropic", model, usage["input_tokens"], usage["output_tokens"],
                                   what=f"benchmark {pipeline} answer {item['item_id']}")
            else:
                usage = {"input_tokens": worst_in, "output_tokens": worst_out, "estimated": True}
                usd = ledger.spend(run_id, "anthropic", model, worst_in, worst_out,
                                   what=f"benchmark {pipeline} answer {item['item_id']} (estimated: worst case, "
                                        "no usage reported)")
    finally:
        if reservation is not None:
            ledger.release(run_id, reservation)
    return answer_row(item, body, error, pipeline=pipeline, writer=writer, effort=effort, latency=latency,
                      usage=usage, usd=usd, model_called=model_called)


# ---------------------------------------------------------------- judge items

CITATION_SQL = ("SELECT p.passage_id, p.item_id, p.leaf_index, p.text, i.title, i.year, i.jurisdiction_norm, "
                "pg.printed_page FROM passages p JOIN items i ON i.item_id = p.item_id "
                "LEFT JOIN pages pg ON pg.page_id = p.page_id WHERE p.passage_id = ?")


def corpus_connection(collection: str):
    from archive_debugger.audit import collections as audit_collections
    from archive_debugger.eval.rundb import open_corpus_read_only
    c = audit_collections.load(collection)
    return open_corpus_read_only(scopes.resolve_scope(c.scope).db_path)


def _citation(conn, passage_id: str, verified: dict) -> dict:
    row = conn.execute(CITATION_SQL, (passage_id,)).fetchone()
    if row is None:
        raise ValueError(f"cited passage {passage_id} is not in the corpus")
    row = dict(zip(("passage_id", "item_id", "leaf_index", "text", "title", "year", "jurisdiction",
                    "printed_page"), tuple(row)))
    from archive_debugger.retrieve import citation as citation_links
    link = (verified.get(passage_id) or {}).get("deep_link") or citation_links.deep_link(row["item_id"], row["leaf_index"])
    out = {k: row.get(k) for k in audit_items.CITATION_FIELDS if k != "deep_link"}
    out["deep_link"] = link
    out["year"] = audit_items._year(out["year"])
    out["leaf_index"] = int(out["leaf_index"])
    return out


def build_judge_items(run_dir: Path, connect: Callable = corpus_connection) -> list:
    """Sentence items then answer items, answer by answer, for every answered row of the run."""
    run_dir = Path(run_dir)
    run_id = run_dir.name
    conns: dict = {}
    out = []
    try:
        for row in read_jsonl(run_dir / "answers.jsonl"):
            if row.get("error") or row.get("refused") is not False or not row.get("sentences"):
                continue
            collection = row["collection"]
            conn = conns.get(collection) or conns.setdefault(collection, connect(collection))
            qid = f"{run_id}/{row['item_id']}"
            verified = {c["passage_id"]: c for c in row.get("verified_citations") or []}
            texts = [s["text"] for s in row["sentences"]]
            source = f"benchmark:{run_id}"
            for n, sentence in enumerate(row["sentences"], 1):
                out.append({
                    "format": audit_items.ITEM_FORMAT, "kind": "sentence",
                    "item_id": audit_items.item_id(collection, qid, n), "collection": collection, "qid": qid,
                    "question": row["question"], "filters": row.get("filters") or {},
                    "sentence_no": n, "sentence": sentence["text"], "answer_text": row["answer"],
                    "citations": [_citation(conn, pid, verified) for pid in sentence.get("cited_ids") or []],
                    "retrieved_ids": row.get("retrieved_ids"), "source": source,
                    "writer_model": row["writer"], "generated_at": row.get("answered_at"),
                })
            out.append({
                "format": audit_items.ITEM_FORMAT, "kind": "answer",
                "item_id": audit_items.answer_item_id(collection, qid), "collection": collection, "qid": qid,
                "question": row["question"], "filters": row.get("filters") or {}, "answer_text": row["answer"],
                "sentences": texts, "source": source, "writer_model": row["writer"],
                "generated_at": row.get("answered_at"),
            })
    finally:
        for conn in conns.values():
            conn.close()
    ids = [it["item_id"] for it in out]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate judge item ids")
    return out


# ---------------------------------------------------------------- scores

def bench_id_of(judge_item: dict) -> str:
    return judge_item["qid"].split("/", 1)[1]


def panel_finals(judge_items: list, decisions: dict) -> tuple:
    """({bench item: [SUPPORTS finals]}, {bench item: [ANSWERS finals]}, judged, left to a person,
    not judged) for one run's judge items, from the panel decisions by judge item id."""
    supports: dict = {}
    answers: dict = {}
    judged = human = unjudged = 0
    for it in judge_items:
        d = decisions.get(it["item_id"])
        if d is None:
            unjudged += 1
            continue
        judged += 1
        if d.get("human_queue"):
            human += 1
        check = "supports" if it.get("kind", "sentence") == "sentence" else "answers"
        final = ((d.get("checks") or {}).get(check) or {}).get("final")
        if final is not None:
            (supports if check == "supports" else answers).setdefault(bench_id_of(it), []).append(final)
    return supports, answers, judged, human, unjudged


def contributions(row: dict, supports: dict, answers: dict) -> dict:
    """Each metric as a (numerator, denominator) pair for one benchmark item, so every rate is a
    ratio of sums and a resample over items is a resample of these pairs."""
    ok = row.get("error") is None and row.get("state") is not None
    refused = 1 if ok and row.get("refused") else 0
    s = supports.get(row["item_id"], [])
    a = answers.get(row["item_id"], [])
    return {
        "refusal_rate_should_refuse": (refused, 1) if ok and row["should_refuse"] else (0, 0),
        "false_refusal_rate": (refused, 1) if ok and not row["should_refuse"] else (0, 0),
        "state_accuracy": (1 if ok and row["state"] == row["expected_verdict"] else 0, 1 if ok else 0),
        "supports_strict": (sum(1 for f in s if f == "pass"), len(s)),
        "answers_failure": (sum(1 for f in a if f != "pass"), len(a)),
        "cost_per_answer": (float(row.get("usd") or 0.0), 1) if ok and row.get("model_called") else (0.0, 0),
    }


RATES = ("refusal_rate_should_refuse", "false_refusal_rate", "state_accuracy", "supports_strict", "answers_failure")
METRICS = RATES + ("cost_per_answer",)


def percentile(values: list, q: float) -> Optional[float]:
    if not values:
        return None
    vals = sorted(values)
    pos = (len(vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def rate(num, den, *, interval: bool = True) -> dict:
    out = {"num": num, "den": den, "value": (num / den) if den else None}
    if interval:
        low, high = calibration.wilson(int(num), int(den))
        out["wilson95"] = [round(low, 4), round(high, 4)] if den else None
    return out


def score_run(rows: list, judge_items: list, decisions: dict) -> dict:
    supports, answers, judged, human, unjudged = panel_finals(judge_items, decisions)
    per_item = [contributions(r, supports, answers) for r in rows]
    metrics = {}
    for name in METRICS:
        num = sum(c[name][0] for c in per_item)
        den = sum(c[name][1] for c in per_item)
        metrics[name] = rate(num, den, interval=name in RATES)
    ok = [r for r in rows if r.get("error") is None and r.get("state") is not None]
    by_category: dict = {}
    confusion: dict = {}
    for r in ok:
        cat = by_category.setdefault(r["category"], [0, 0])
        cat[0] += 1 if r["state"] == r["expected_verdict"] else 0
        cat[1] += 1
        row = confusion.setdefault(r["expected_verdict"], {})
        row[r["state"]] = row.get(r["state"], 0) + 1
    latencies = [float(r["latency_s"]) for r in ok if r.get("latency_s") is not None]
    return {
        "items": len(rows), "answered": len(ok), "errors": len(rows) - len(ok),
        "metrics": metrics,
        "state_accuracy_by_category": {k: rate(v[0], v[1]) for k, v in sorted(by_category.items())},
        "confusion": {k: dict(sorted(v.items())) for k, v in sorted(confusion.items())},
        "judge_items": len(judge_items), "judged": judged, "unjudged": unjudged,
        "left_to_person": rate(human, judged),
        "latency_s": {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95)},
        "spend_usd": round(sum(float(r.get("usd") or 0.0) for r in rows), 6),
    }


def paired_bootstrap(rows_a: list, rows_b: list, extra_a: tuple, extra_b: tuple, *,
                     resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED) -> Optional[dict]:
    """Second minus first for every metric over the items both runs answered, with a percentile 95%
    interval from a paired bootstrap over items. extra_x is (supports finals, answers finals)."""
    a = {r["item_id"]: r for r in rows_a if r.get("error") is None and r.get("state") is not None}
    b = {r["item_id"]: r for r in rows_b if r.get("error") is None and r.get("state") is not None}
    common = sorted(set(a) & set(b))
    if not common:
        return None
    pairs = [(contributions(a[i], *extra_a), contributions(b[i], *extra_b)) for i in common]

    def ratio(sample, side, name):
        num = sum(p[side][name][0] for p in sample)
        den = sum(p[side][name][1] for p in sample)
        return (num / den) if den else None

    rng = random.Random(seed)
    draws = {name: [] for name in METRICS}
    n = len(pairs)
    for _ in range(resamples):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        for name in METRICS:
            first, second = ratio(sample, 0, name), ratio(sample, 1, name)
            if first is not None and second is not None:
                draws[name].append(second - first)
    out = {"items": n, "resamples": resamples, "seed": seed, "differences": {}}
    for name in METRICS:
        first, second = ratio(pairs, 0, name), ratio(pairs, 1, name)
        point = (second - first) if first is not None and second is not None else None
        ds = draws[name]
        out["differences"][name] = {
            "first": first, "second": second, "difference": point, "resamples_used": len(ds),
            "bootstrap95": [round(percentile(ds, 0.025), 6), round(percentile(ds, 0.975), 6)] if ds else None,
        }
    return out


def load_decisions(audit_runs: list, audit_dir: Path) -> dict:
    decisions: dict = {}
    for name in audit_runs or []:
        path = Path(audit_dir) / "runs" / name / "panel.jsonl"
        if not path.exists():
            raise Refused(f"{path} is missing")
        for d in read_jsonl(path):
            decisions[d["item_id"]] = d
    return decisions


def score(runs: list, audit_runs: list, name: str, *, out_root: Path = DEFAULT_OUT,
          audit_dir: Path = DEFAULT_AUDIT_DIR) -> dict:
    decisions = load_decisions(audit_runs, audit_dir)
    loaded = {}
    for run_id in runs:
        run_dir = Path(out_root) / "runs" / run_id
        if not (run_dir / "answers.jsonl").exists():
            raise Refused(f"{run_dir / 'answers.jsonl'} is missing")
        rows = read_jsonl(run_dir / "answers.jsonl")
        judge_items = read_jsonl(run_dir / "judge_items.jsonl")
        info = json.loads((run_dir / "run.json").read_text(encoding="utf-8")) if (run_dir / "run.json").exists() else {}
        loaded[run_id] = (rows, judge_items, info)
    result = {"format": 1, "name": name, "runs": {}, "comparisons": [], "audit_runs": list(audit_runs or []),
              "scored_at": now_iso(),
              "notes": ["Rates are over items answered without an error; Wilson 95% intervals.",
                        "SUPPORTS and ANSWERS come from the audit panel's final verdicts; a check left to a "
                        "person has no final verdict and is counted in left_to_person, not in the rate.",
                        "Cost per answer is the mean ledger cost over items whose ask reached the writer; v1 "
                        "costs are worst-case estimates (v1 reports no token usage)."]}
    extras = {}
    for run_id, (rows, judge_items, info) in loaded.items():
        summary = score_run(rows, judge_items, decisions)
        summary["pipeline_label"] = info.get("pipeline_label")
        summary["split"] = (info.get("config") or {}).get("split")
        result["runs"][run_id] = summary
        supports, answers, _, _, _ = panel_finals(judge_items, decisions)
        extras[run_id] = (supports, answers)
    for i, first in enumerate(runs):
        for second in runs[i + 1:]:
            boot = paired_bootstrap(loaded[first][0], loaded[second][0], extras[first], extras[second])
            if boot is not None:
                result["comparisons"].append({"first": first, "second": second, **boot})
    out_dir = Path(out_root) / "scores" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scores.json").write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    with (out_dir / "scores.md").open("w", encoding="utf-8", newline=NL) as fh:
        fh.write(scores_markdown(result))
    return result


def _fmt(r: dict) -> str:
    if r.get("value") is None:
        return "n/a (0 items)"
    text = f"{r['value']:.3f} ({r['num']}/{r['den']})"
    if r.get("wilson95"):
        text += f" [{r['wilson95'][0]:.3f}, {r['wilson95'][1]:.3f}]"
    return text


def scores_markdown(result: dict) -> str:
    lines = [f"# Benchmark scores: {result['name']}", "",
             f"Scored {result['scored_at']}. Audit runs: {', '.join(result['audit_runs']) or 'none'}.", ""]
    for note in result["notes"]:
        lines.append(f"- {note}")
    for run_id, s in result["runs"].items():
        m = s["metrics"]
        lines += ["", f"## {run_id} ({s.get('pipeline_label')}, {s.get('split')} split)", "",
                  f"{s['items']} items, {s['answered']} answered, {s['errors']} errors; spend ${s['spend_usd']:.4f}.", "",
                  "| Measure | Value [Wilson 95%] |", "| --- | --- |",
                  f"| Should-refuse items refused | {_fmt(m['refusal_rate_should_refuse'])} |",
                  f"| Answerable items refused (false refusal) | {_fmt(m['false_refusal_rate'])} |",
                  f"| State accuracy | {_fmt(m['state_accuracy'])} |",
                  f"| Strict SUPPORTS (sentence items passing) | {_fmt(m['supports_strict'])} |",
                  f"| ANSWERS failure (answer items not passing) | {_fmt(m['answers_failure'])} |",
                  f"| Judge items left to a person | {_fmt(s['left_to_person'])} |",
                  f"| Cost per answer (USD) | {m['cost_per_answer']['value'] if m['cost_per_answer']['value'] is not None else 'n/a'} |",
                  f"| Latency p50 / p95 (s) | {s['latency_s']['p50']} / {s['latency_s']['p95']} |",
                  "", f"Judge items: {s['judge_items']}, judged {s['judged']}, not judged {s['unjudged']}.", "",
                  "| Category | State accuracy |", "| --- | --- |"]
        for cat, r in s["state_accuracy_by_category"].items():
            lines.append(f"| {cat} | {_fmt(r)} |")
        produced = sorted({p for row in s["confusion"].values() for p in row})
        lines += ["", "Expected (rows) x produced (columns):", "",
                  "| expected | " + " | ".join(produced) + " |", "| --- |" + " --- |" * len(produced)]
        for expected, row in s["confusion"].items():
            lines.append(f"| {expected} | " + " | ".join(str(row.get(p, 0)) for p in produced) + " |")
    for comp in result["comparisons"]:
        lines += ["", f"## {comp['second']} minus {comp['first']}", "",
                  f"Paired bootstrap over {comp['items']} items both runs answered ({comp['resamples']} resamples, "
                  f"seed {comp['seed']}).", "", "| Measure | Difference | Bootstrap 95% |", "| --- | --- | --- |"]
        for name, d in comp["differences"].items():
            diff = "n/a" if d["difference"] is None else f"{d['difference']:+.4f}"
            ci = "n/a" if not d["bootstrap95"] else f"[{d['bootstrap95'][0]:+.4f}, {d['bootstrap95'][1]:+.4f}]"
            lines.append(f"| {name} | {diff} | {ci} |")
    return NL.join(lines) + NL


# ---------------------------------------------------------------- command line

def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output root (default reports/v2/benchmark)")
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="answer a split through the engine")
    p_run.add_argument("--split", choices=SPLITS, required=True)
    p_run.add_argument("--pipeline", choices=PIPELINES, required=True)
    p_run.add_argument("--writer", default=None, help="writer model id (default: the collection config's model)")
    p_run.add_argument("--effort", choices=EFFORTS, default=None, help="v2 only, for claude-haiku-5-5 and claude-sonnet-5-5")
    p_run.add_argument("--run-id", required=True)
    p_run.add_argument("--cap", type=float, required=True, help="this run's spending cap in US dollars")
    p_run.add_argument("--limit", type=int, default=None, help="a seeded random subset of this many items")
    p_run.add_argument("--seed", type=int, default=LIMIT_SEED, help="seed for --limit")
    p_run.add_argument("--collections", nargs="*", default=None)
    p_run.add_argument("--stub", action="store_true", help="stub writer: no paid calls, no ledger entries")
    p_run.add_argument("--final", action="store_true", help="required for the test split (once per pipeline label)")
    p_run.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    p_run.add_argument("--splits-dir", type=Path, default=DEFAULT_SPLITS)
    p_run.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    p_items = sub.add_parser("judge-items", help="write a run's judge items")
    p_items.add_argument("--run-id", required=True)
    p_score = sub.add_parser("score", help="score benchmark runs against audit panel decisions")
    p_score.add_argument("--runs", nargs="+", required=True)
    p_score.add_argument("--audit", nargs="*", default=[])
    p_score.add_argument("--name", required=True)
    p_score.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    args = parser.parse_args(argv)
    out_root = args.out.resolve()
    os.chdir(REPO)      # configs and scope paths are relative to the repo root
    try:
        if args.command == "run":
            from archive_debugger.local_env import load_local_env
            load_local_env()
            ledger = None if args.stub else Ledger(args.ledger)
            return run_benchmark(split=args.split, pipeline=args.pipeline, run_id=args.run_id, cap=args.cap,
                                 writer=args.writer, effort=args.effort, limit=args.limit, seed=args.seed,
                                 collections=args.collections, stub=args.stub, final=args.final, out_root=out_root,
                                 lock_path=args.lock, splits_dir=args.splits_dir, ledger=ledger)
        if args.command == "judge-items":
            from archive_debugger.local_env import load_local_env
            load_local_env()
            run_dir = out_root / "runs" / args.run_id
            if not (run_dir / "answers.jsonl").exists():
                raise Refused(f"{run_dir / 'answers.jsonl'} is missing")
            items = build_judge_items(run_dir)
            n = write_jsonl(run_dir / "judge_items.jsonl", items)
            kinds = sum(1 for it in items if it["kind"] == "answer")
            print(f"{n} judge items ({kinds} answer items, {n - kinds} sentence items) in {run_dir / 'judge_items.jsonl'}")
            return 0
        result = score(args.runs, args.audit, args.name, out_root=out_root, audit_dir=args.audit_dir)
        print(f"scores: {out_root / 'scores' / args.name / 'scores.md'} ({len(result['runs'])} runs, "
              f"{len(result['comparisons'])} comparisons)")
        return 0
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
