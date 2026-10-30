"""Generate and store the missing recorded answers for a scope's seed and story questions. PAID.

Runs the real engine in this process with the real model (the key from .env, never printed), asks
each curated question of the scope that has no stored answer, and lets the engine store the result
exactly as it stores any answer (a curated row in the local v2 cache). Nothing else is generated.

Spend is measured, not estimated: every model call's token usage is read from the API response and
priced at the published rate. Before each call the script refuses to proceed if the spend so far
plus the most one call can cost (max_tokens of output plus a generous input) would pass --cap-usd;
the refused question then gets the engine's limited-mode answer, which is never stored.

    python scripts/v2/record_curated_answers.py --scope microlog --cap-usd 1.00 --out reports/v2/raw/paid_microlog_run.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PRICE_PER_MTOK = {"claude-haiku-4-5-20251001": (1.00, 5.00)}
WORST_INPUT_TOKENS = 12_000          # the largest prompt measured on the seed questions was 6,652 tokens


class Ledger:
    def __init__(self, cap_usd: float, max_tokens: int, model: str):
        self.cap = cap_usd
        self.price_in, self.price_out = PRICE_PER_MTOK[model]
        self.worst_call = (WORST_INPUT_TOKENS * self.price_in + max_tokens * self.price_out) / 1e6
        self.calls: list[dict] = []
        self.lock = threading.Lock()

    @property
    def spent(self) -> float:
        return sum(c["usd"] for c in self.calls)

    def allow(self) -> bool:
        with self.lock:
            return self.spent + self.worst_call <= self.cap

    def record(self, usage) -> None:
        tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
        usd = (tokens_in * self.price_in + tokens_out * self.price_out) / 1e6
        with self.lock:
            self.calls.append({"input_tokens": tokens_in, "output_tokens": tokens_out, "usd": round(usd, 6)})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scope", required=True)
    parser.add_argument("--cap-usd", type=float, required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    from dotenv import dotenv_values
    key = dotenv_values(REPO / ".env").get("ANTHROPIC_API_KEY")
    if not key:
        print("no ANTHROPIC_API_KEY in .env", file=sys.stderr)
        return 2
    os.environ["ANTHROPIC_API_KEY"] = key               # the .env key; the shell's exported key is stale
    os.environ.pop("ANTHROPIC_BASE_URL", None)

    import anthropic
    from fastapi.testclient import TestClient

    from archive_debugger.api.app import create_app
    from archive_debugger.generate.cli import load_generate_config
    from archive_debugger import scopes

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from migrate_cache import curated_questions

    resolved = scopes.resolve_scope(args.scope)
    gcfg = load_generate_config(Path(resolved.config_path))
    ledger = Ledger(args.cap_usd, gcfg["max_tokens"], gcfg["model"])

    original_parse = anthropic.resources.messages.Messages.parse

    def metered_parse(self, *a, **kw):
        if not ledger.allow():
            raise RuntimeError("spend cap reached; no further model calls")
        resp = original_parse(self, *a, **kw)
        ledger.record(resp.usage)
        return resp

    anthropic.resources.messages.Messages.parse = metered_parse

    from archive_debugger import scopes as _scopes
    _default = _scopes.load_registry().get("default")
    _base_config = Path(_scopes.resolve_scope(_default).config_path)
    app = create_app(_base_config, load_env=False,
                     serve_scopes=[args.scope] if args.scope != _default else None)
    rows = []
    t0 = time.monotonic()
    with TestClient(app, raise_server_exceptions=False) as client:
        if not app.state.ready.wait(900):
            print(f"engine never became ready: {app.state.startup_error}", file=sys.stderr)
            return 1
        for q in curated_questions(args.scope):
            before = len(ledger.calls)
            body = client.post(f"/ask?scope={args.scope}", json={"question": q["question"], "filters": q["filters"]}).json()
            answer = body.get("answer") or {}
            if answer.get("cached"):
                outcome = "already_stored"
            elif body.get("degraded"):
                outcome = f"limited:{body['degraded'].get('reason')}"
            elif answer.get("abstained"):
                outcome = "stored_abstention"
            else:
                outcome = "stored_answer"
            rows.append({"label": q["label"], "outcome": outcome, "model_calls": len(ledger.calls) - before,
                         "verified_citations": len(answer.get("verified_citations") or [])})
            print(json.dumps(rows[-1]), flush=True)
    record = {"scope": args.scope, "model": gcfg["model"], "cap_usd": args.cap_usd,
              "spent_usd": round(ledger.spent, 6), "calls": ledger.calls, "questions": rows,
              "seconds": round(time.monotonic() - t0, 1),
              "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps({"spent_usd": record["spent_usd"], "model_calls": len(ledger.calls)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
