"""Operator steps after an engine deploy: make the wake token, wake each collection and wait until it
is ready, and run the smoke tests. Standard library only; the token is read from .env (or the
environment) and never printed.

    python scripts/v2/engine_ops.py token                         # writes a fresh ADMIN_WAKE_TOKEN to .env
    python scripts/v2/engine_ops.py wait-release --api URL --release 2026-11-01.1
    python scripts/v2/engine_ops.py wake --api URL [--scope pilot] [--timeout 300]
    python scripts/v2/engine_ops.py smoke --api URL [--site https://archiveargues.org] [--live]

`token` only writes .env; setting it on the Worker is `npx wrangler secret put ADMIN_WAKE_TOKEN
--env <env>` from worker/engine, with the value piped in, never on a command line. `wake` posts to
/admin/wake and polls /health until every woken engine is ready (or failed). `smoke` checks /health,
a stored seed answer, the record alone for one question (no model call, never stored), with
--live one new answer through the model, and with --site the site's headers. Exit status 1 when any
check fails, so a deploy script can roll back on it.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"
USER_AGENT = "archive-argues-operator/1.0 (+https://archiveargues.org; hello@archiveargues.org)"
TOKEN_NAME = "ADMIN_WAKE_TOKEN"

STORED_QUESTION = {"question": "What did Ontario public health authorities recommend about controlling tobacco smoking?",
                   "filters": {"jurisdiction": "ontario"}, "scope": "pilot"}
# Live smoke questions, tried in order until one is not already stored (production ignores nocache).
LIVE_QUESTIONS = [
    {"question": "What did Ontario reports say about road salt and the environment?", "scope": "pilot"},
    {"question": "What did federal reports say about fisheries inspection in the 1970s?", "scope": "pilot"},
    {"question": "What did provincial reports say about rural libraries?", "scope": "pilot"},
    {"question": "What did government reports say about forest fire prevention?", "scope": "pilot"},
    {"question": "What did government reports say about winter road maintenance?", "scope": "pilot"},
    {"question": "What did government reports say about apprenticeship programs?", "scope": "pilot"},
]


def read_token() -> str:
    value = os.environ.get(TOKEN_NAME, "")
    if not value and ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{TOKEN_NAME}="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not value:
        raise SystemExit(f"{TOKEN_NAME} is not set in the environment or .env (run: engine_ops.py token)")
    return value


def write_token() -> None:
    value = secrets.token_urlsafe(32)
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [line for line in lines if not line.startswith(f"{TOKEN_NAME}=")]
    lines.append(f"{TOKEN_NAME}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"{TOKEN_NAME} written to .env ({len(value)} characters); the value is not shown")


def request(method: str, url: str, *, body: dict | None = None, token: str | None = None,
            timeout: float = 60.0) -> tuple[int, dict, dict]:
    """One HTTP call. Returns (status, headers, json body or {})."""
    headers = {"user-agent": USER_AGENT}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"
    if token:
        headers["authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status, resp_headers = resp.status, {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status, resp_headers = exc.code, {k.lower(): v for k, v in exc.headers.items()}
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        parsed = {}
    return status, resp_headers, parsed


def health(api: str) -> dict:
    status, _, body = request("GET", f"{api.rstrip('/')}/health", timeout=30)
    if status != 200:
        raise RuntimeError(f"/health answered {status}")
    return body


def wait_release(api: str, release: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            body = health(api)
            if body.get("release") == release:
                print(f"/health names release {release} (status {body.get('status')})")
                return True
        except (RuntimeError, urllib.error.URLError, OSError):
            pass
        time.sleep(5)
    print(f"FAIL: /health did not name release {release} within {timeout:.0f} s")
    return False


def wake(api: str, scope: str | None, timeout: float) -> bool:
    url = f"{api.rstrip('/')}/admin/wake" + (f"?scope={scope}" if scope else "")
    t0 = time.monotonic()
    try:
        status, _, body = request("POST", url, token=read_token(), timeout=180)
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        # The first start of a new image can hold the reply; the wake has usually begun, so poll.
        print(f"/admin/wake gave no reply ({exc}); polling /health")
        status, body = 202, {"engines": [{"name": e.get("name"), "status": e.get("status")} for e in health(api).get("engines", [])
                                         if not scope or e.get("name") == scope]}
    if status != 202:
        print(f"FAIL: /admin/wake answered {status} {body.get('error', '')}")
        return False
    names = [e.get("name") for e in body.get("engines", [])]
    woken = ", ".join(f"{e.get('name')}:{e.get('status')}" for e in body.get("engines", []))
    print(f"woke {woken} (release {body.get('release')})")
    while time.monotonic() - t0 < timeout:
        engines = {e.get("name"): e for e in health(api).get("engines", [])}
        states = {name: (engines.get(name) or {}).get("status") for name in names}
        if any(s == "failed" for s in states.values()):
            print(f"FAIL: an engine failed while waking: {states}")
            return False
        if all(s == "ready" for s in states.values()):
            print(f"ready after {time.monotonic() - t0:.1f} s: {', '.join(names)}")
            return True
        time.sleep(3)
    print(f"FAIL: not ready within {timeout:.0f} s")
    return False


def smoke(api: str, site: str | None, live: bool) -> bool:
    api = api.rstrip("/")
    results: list[tuple[str, bool, str]] = []

    body = health(api)
    results.append(("health", body.get("status") in {"ready", "asleep", "waking"}, f"status {body.get('status')}, release {body.get('release')}"))

    status, headers, answer = request("POST", f"{api}/ask", body=STORED_QUESTION)
    results.append(("stored answer", status == 200 and headers.get("x-answer-source") == "stored" and bool((answer.get("answer") or {}).get("text")),
                    f"{status}, source {headers.get('x-answer-source')}"))

    token = read_token()
    record_q = {**LIVE_QUESTIONS[0], "evidence_only": True}
    status, headers, record = request("POST", f"{api}/ask", body=record_q, token=token, timeout=180)
    results.append(("record alone (no model call)", status == 200 and len(record.get("evidence") or []) > 0,
                    f"{status}, {len(record.get('evidence') or [])} passages"))

    if live:
        tried = 0
        for question in LIVE_QUESTIONS:
            tried += 1
            t0 = time.monotonic()
            status, headers, answer = request("POST", f"{api}/ask", body=question, token=token, timeout=180)
            source = headers.get("x-answer-source")
            if status == 200 and source == "stored":
                continue
            text = (answer.get("answer") or {}).get("text") or ""
            results.append(("live answer through the model", status == 200 and source == "engine" and bool(text),
                            f"{status}, source {source}, {time.monotonic() - t0:.1f} s, abstained {(answer.get('answer') or {}).get('abstained')}"))
            break
        else:
            results.append(("live answer through the model", False, f"all {tried} live questions are already stored"))

    if site:
        for path, expected in (("/", "no-cache"),):
            req = urllib.request.Request(site.rstrip("/") + path, method="HEAD", headers={"user-agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    cache_control = resp.headers.get("cache-control", "")
                    results.append((f"site {path}", resp.status == 200 and expected in cache_control, f"{resp.status}, cache-control {cache_control}"))
            except (urllib.error.URLError, OSError) as exc:
                results.append((f"site {path}", False, str(exc)))

    for name, ok, detail in results:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}: {detail}")
    return all(ok for _, ok, _ in results)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("token")
    p = sub.add_parser("wait-release")
    p.add_argument("--api", required=True)
    p.add_argument("--release", required=True)
    p.add_argument("--timeout", type=float, default=900)
    p = sub.add_parser("wake")
    p.add_argument("--api", required=True)
    p.add_argument("--scope", default=None)
    p.add_argument("--timeout", type=float, default=300)
    p = sub.add_parser("smoke")
    p.add_argument("--api", required=True)
    p.add_argument("--site", default=None)
    p.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "token":
        write_token()
        return 0
    if args.command == "wait-release":
        return 0 if wait_release(args.api, args.release, args.timeout) else 1
    if args.command == "wake":
        return 0 if wake(args.api, args.scope, args.timeout) else 1
    return 0 if smoke(args.api, args.site, args.live) else 1


if __name__ == "__main__":
    sys.exit(main())
