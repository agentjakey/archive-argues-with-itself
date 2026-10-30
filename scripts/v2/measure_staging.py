"""Measure a cold wake of the engine on Cloudflare staging, step by step, and load-test it once awake.

Run against the staging engine Worker (workers.dev), with staging's Turnstile set to Cloudflare's
always-pass test secret, so the script can send the documented dummy token. Standard library only.

  1. Waits until the engine is asleep (staging should run with a short SLEEP_AFTER_MINUTES).
  2. POST /wake, then polls GET /health once a second, recording every stage change with the
     engine's own byte counts, until the engine is ready or fails.
  3. Times the first live answer: a question that is not stored, with the stub provider, so the
     full retrieval path runs and no model is billed.
  4. Times a stored answer served by the Worker from D1 (no engine).
  5. Optionally (--load N) sends N concurrent uncached questions and checks every one was served
     without limited mode and without the container restarting (an out-of-memory kill shows as an
     exit in the wake log).
  6. Saves the Durable Object's wake record (port open and ready times, the provisioning summary).

    python scripts/v2/measure_staging.py --api https://archive-argues-engine-staging.<sub>.workers.dev \
        --label r2-binding-standard-3 --out reports/v2/raw/staging_wake_r2_binding.json --load 8
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DUMMY_TOKEN = "XXXX.DUMMY.TOKEN.XXXX"     # accepted only by Turnstile's test secrets
USER_AGENT = "archive-argues-measure/1.0 (staging measurement)"
LIVE_QUESTION = "What did annual reports say about rural nursing stations and outpost care?"
REPO = Path(__file__).resolve().parent.parent.parent
LOAD_QUESTIONS = [
    "What did reports say about immunization clinics in schools?",
    "How were tuberculosis sanatoriums described in provincial reports?",
    "What did health departments report about water fluoridation?",
    "What did reports say about mental health services in the community?",
    "How did reports describe maternal and infant health programs?",
    "What did reports say about occupational health in mines?",
    "How were nursing homes for seniors described?",
    "What did reports say about smoking in public places?",
    "How did health units describe food inspection?",
    "What did reports say about ambulance services?",
    "How was home care for the elderly described?",
    "What did reports say about dental health for children?",
]


def call(api: str, method: str, path: str, body: dict | None = None, timeout: float = 60.0,
         headers: dict | None = None) -> tuple[int, dict, float]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{api}{path}", data=data, method=method,
                                 headers={"content-type": "application/json", "user-agent": USER_AGENT,
                                          "x-turnstile-token": DUMMY_TOKEN})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8") or "{}")
            if headers is not None:
                headers.update({k.lower(): v for k, v in resp.headers.items()})
            return resp.status, payload, time.monotonic() - t0
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8") or "{}")
        except ValueError:
            payload = {}
        return exc.code, payload, time.monotonic() - t0


def engine_stage(health: dict) -> tuple[str, dict | None]:
    engines = health.get("engines") or []
    stages = [e.get("stage") for e in engines if e.get("stage")]
    return health.get("status", "unknown"), (stages[0] if stages else None)


def wait_asleep(api: str, limit_s: float) -> bool:
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        status, health, _ = call(api, "GET", "/health")
        if status == 200 and health.get("status") == "asleep":
            return True
        print(f"engine is {health.get('status')}; waiting for it to sleep", flush=True)
        time.sleep(30)
    return False


def ask(api: str, question: str, *, stub: bool, scope: str | None = None, filters: dict | None = None,
        headers: dict | None = None) -> tuple[int, dict, float]:
    body: dict = {"question": question}
    if filters:
        body["filters"] = filters
    if stub:
        body.update({"provider": "stub", "nocache": True})
    path = "/ask?" + urllib.parse.urlencode({"scope": scope}) if scope else "/ask"   # the scope is a query parameter
    return call(api, "POST", path, body, timeout=120, headers=headers)


def stored_question(data: Path) -> tuple[str, str, dict]:
    """A seed or story question with a recorded answer in the committed site data: the Worker
    serves it from D1 without waking the engine."""
    for index in sorted(data.glob("*/answers/index.json")):
        payload = json.loads(index.read_text(encoding="utf-8"))
        for entry in payload["answers"]:
            if entry.get("file"):
                return payload["scope"], entry["question"], entry.get("filters") or {}
    raise SystemExit(f"no recorded answer under {data}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", required=True)
    parser.add_argument("--label", required=True, help="what is being measured, e.g. r2-binding-standard-3")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--load", type=int, default=0, help="concurrent uncached questions once awake")
    parser.add_argument("--wait-asleep", type=float, default=1800.0)
    parser.add_argument("--timeout", type=float, default=1200.0, help="give up on the wake after this many seconds")
    parser.add_argument("--data", type=Path, default=REPO / "site" / "data", help="committed site data (for a stored question)")
    args = parser.parse_args(argv)
    api = args.api.rstrip("/")

    if not wait_asleep(api, args.wait_asleep):
        print("the engine did not fall asleep; set a short SLEEP_AFTER_MINUTES on staging", file=sys.stderr)
        return 2
    record: dict = {"label": args.label, "api": api, "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    t0 = time.monotonic()
    status, body, _ = call(api, "POST", "/wake")
    record["wake_request"] = {"status": status}
    transitions = []
    last = None
    final = "timeout"
    while time.monotonic() - t0 < args.timeout:
        _, health, _ = call(api, "GET", "/health")
        state, stage = engine_stage(health)
        key = (state, (stage or {}).get("stage"))
        if key != last:
            row = {"seconds": round(time.monotonic() - t0, 1), "status": state, "stage": stage}
            transitions.append(row)
            print(json.dumps(row), flush=True)
            last = key
        if state in ("ready", "failed"):
            final = state
            break
        time.sleep(1.0)
    record["transitions"] = transitions
    record["outcome"] = final
    record["wake_to_ready_seconds"] = round(time.monotonic() - t0, 1) if final == "ready" else None

    if final == "ready":
        code, answer, seconds = ask(api, LIVE_QUESTION, stub=True)
        record["first_live_answer"] = {"status": code, "seconds": round(seconds, 2),
                                       "degraded": (answer.get("degraded") or {}).get("reason"),
                                       "since_wake_seconds": round(time.monotonic() - t0, 1)}
        scope, question, filters = stored_question(args.data)
        seen: dict = {}
        code, answer, seconds = ask(api, question, stub=False, scope=scope, filters=filters, headers=seen)
        record["stored_answer"] = {"status": code, "seconds": round(seconds, 2),
                                   "source": seen.get("x-answer-source")}
        if args.load:
            results: list = []

            def one(question: str) -> None:
                results.append(ask(api, question, stub=True))

            threads = [threading.Thread(target=one, args=(LOAD_QUESTIONS[i % len(LOAD_QUESTIONS)],))
                       for i in range(args.load)]
            t_load = time.monotonic()
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            record["load"] = {
                "concurrent": args.load, "seconds": round(time.monotonic() - t_load, 2),
                "ok": sum(1 for code, body, _ in results if code == 200 and not body.get("degraded")),
                "degraded": sorted({(body.get("degraded") or {}).get("reason") for code, body, _ in results
                                    if body.get("degraded")} - {None}),
                "statuses": sorted({code for code, _, _ in results}),
                "slowest_seconds": round(max(s for _, _, s in results), 2),
            }
    _, health, _ = call(api, "GET", "/health?wakes=1")
    record["wake_log"] = (health.get("wakes") or [])[-3:]
    record["exits_during_run"] = [w for w in record["wake_log"]
                                  if w.get("exit") and w.get("started_at", "") >= record["measured_utc"]]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps({k: record.get(k) for k in ("label", "outcome", "wake_to_ready_seconds", "first_live_answer",
                                                  "stored_answer", "load")}, indent=1))
    return 0 if final == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
