"""Cold and warm latency of a question to one shard engine, through the engine Worker.

    python scripts/v2/shard_latency.py --api https://archive-argues-engine-staging.<account>.workers.dev \
        --scope british_columbia-1968-2001 --question "What did reports say about forest fire suppression?" [--live]

Cold: the shard's engine is asleep (checked on /health first; the script waits for it to sleep when it
is awake, up to --sleep-wait seconds), and the first question wakes it. Warm: --warm more questions
straight after. Every question asks for the record alone (evidence_only: no model call, never
stored); --live adds one answer through the scope's model on the warm engine, which spends one
model call. The operator token (ADMIN_WAKE_TOKEN) stands in for Turnstile, as in engine_ops.py smoke.
Writes one JSON line per measurement to reports/v2/scale/latency.jsonl and prints a summary.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import engine_ops  # noqa: E402

OUT = REPO / "reports" / "v2" / "scale" / "latency.jsonl"


def engine_state(api: str, scope: str) -> str:
    for engine in engine_ops.health(api).get("engines", []):
        if engine.get("name") == scope:
            return engine.get("status", "unknown")
    return "missing"


def ask(api: str, token: str, scope: str, question: str, evidence_only: bool, timeout: float) -> dict:
    body = {"question": question, "evidence_only": evidence_only, "nocache": True}
    started = time.time()
    status, headers, parsed = engine_ops.request("POST", f"{api}/ask?scope={scope}", body=body, token=token,
                                                 timeout=timeout)
    seconds = round(time.time() - started, 2)
    evidence = parsed.get("evidence") or []
    answer = parsed.get("answer") or {}
    return {"status": status, "seconds": seconds, "evidence": len(evidence),
            "abstained": answer.get("abstained") if not evidence_only else None,
            "source": headers.get("x-answer-source")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", required=True)
    ap.add_argument("--scope", required=True)
    ap.add_argument("--question", required=True)
    ap.add_argument("--warm", type=int, default=3)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--sleep-wait", type=float, default=1500.0, help="seconds to wait for the engine to fall asleep")
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args(argv)
    api = args.api.rstrip("/")
    token = engine_ops.read_token()
    waited = 0.0
    state = engine_state(api, args.scope)
    while state not in ("asleep", "missing") and waited < args.sleep_wait:
        time.sleep(30)
        waited += 30
        state = engine_state(api, args.scope)
    if state == "missing":
        print(f"{args.scope} is not an engine this deployment serves")
        return 1
    rows = []
    run = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "api": api, "scope": args.scope}
    first = ask(api, token, args.scope, args.question, True, args.timeout)
    rows.append({**run, "kind": "cold" if state == "asleep" else f"not cold ({state})", **first})
    for _ in range(args.warm):
        rows.append({**run, "kind": "warm", **ask(api, token, args.scope, args.question, True, args.timeout)})
    if args.live:
        rows.append({**run, "kind": "warm live answer", **ask(api, token, args.scope, args.question, False, args.timeout)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    for r in rows:
        print(f"{r['kind']:18} {r['status']} {r['seconds']:7.2f} s  evidence {r['evidence']}")
    return 0 if all(r["status"] == 200 for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
