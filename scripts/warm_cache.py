"""Warm a deployed API's answer cache: every seed question through POST /ask with the
server's configured (real) provider. Standard library only.

    python scripts/warm_cache.py https://archive-argues-with-itself.fly.dev [--yes] [--seed eval/seed_questions.jsonl]

Idempotent: /ask reads its cache first, so a question already answered under the
current model, prompt, retrieval config and index returns `answer.cached` and costs
no model call; re-running only pays for what is missing. Before starting it prints a
cost estimate and asks for confirmation (--yes skips the prompt for unattended runs).

The estimate is an upper bound from fixed assumptions printed alongside it; the
server does not report token counts. Check PRICE_* against current pricing."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TIMEOUT = 600
# Assumptions for the estimate (upper-bound-ish). The prompt is SYSTEM plus top_k
# tagged passages; passages are chunks of a few hundred words.
TOP_K = 12
TOKENS_PER_PASSAGE = 450
TOKENS_SYSTEM = 700
TOKENS_OUTPUT = 600
# USD per million tokens; verify against the provider's current price list.
PRICES = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}
DEFAULT_PRICE = (1.00, 5.00)


def post(base: str, body: dict) -> tuple[int, object]:
    req = urllib.request.Request(base + "/ask", data=json.dumps(body).encode("utf-8"),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def get_json(base: str, path: str):
    with urllib.request.urlopen(base + path, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_seed(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):        # same rule as eval.questions.load_seed
            rows.append(json.loads(line))
    return rows


def estimate(n: int, model: str) -> tuple[float, int, int]:
    price_in, price_out = PRICES.get(model, DEFAULT_PRICE)
    tokens_in = n * (TOKENS_SYSTEM + TOP_K * TOKENS_PER_PASSAGE)
    tokens_out = n * TOKENS_OUTPUT
    usd = tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out
    return usd, tokens_in, tokens_out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Warm the answer cache of a deployed API with every seed question.")
    p.add_argument("base_url")
    p.add_argument("--seed", default=Path("eval/seed_questions.jsonl"), type=Path)
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = p.parse_args(argv)
    base = args.base_url.rstrip("/")

    try:
        health = get_json(base, "/health")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"cannot reach {base}/health: {exc}. Nothing sent.")
        return 2
    if health.get("provider") != "anthropic":
        print(f"server provider is {health.get('provider')!r}; warming a stub server is pointless. Nothing sent.")
        return 2
    model = health.get("model", "")
    seed = load_seed(args.seed)
    usd, tokens_in, tokens_out = estimate(len(seed), model)
    print(f"server: {base}  model: {model}")
    print(f"questions: {len(seed)}  (cached ones cost nothing; thin abstentions call no model)")
    print(f"upper-bound estimate if every question calls the model: about ${usd:.2f} "
          f"({tokens_in:,} input + {tokens_out:,} output tokens at "
          f"${PRICES.get(model, DEFAULT_PRICE)[0]:.2f}/{PRICES.get(model, DEFAULT_PRICE)[1]:.2f} per million)")
    print(f"assumptions: top_k {TOP_K}, {TOKENS_PER_PASSAGE} tokens/passage, {TOKENS_SYSTEM} system, "
          f"{TOKENS_OUTPUT} output tokens/question")
    if not args.yes:
        if input("proceed? type yes: ").strip().lower() != "yes":
            print("aborted; nothing sent")
            return 1

    counts = {"cached": 0, "answered": 0, "abstained": 0, "failed": 0}
    t_all = time.perf_counter()
    for q in seed:
        t0 = time.perf_counter()
        status, body = post(base, {"question": q["text"], "filters": q.get("filters") or {}})
        dt = time.perf_counter() - t0
        if status != 200 or not isinstance(body, dict):
            counts["failed"] += 1
            print(f"{q['qid']}  FAIL {status} {str(body)[:120]}")
            continue
        ans = body["answer"]
        if ans.get("cached"):
            counts["cached"] += 1
            tag = f"cached ({ans['cached']['created_at'][:10]})"
        elif ans.get("abstained"):
            counts["abstained"] += 1
            tag = "abstained"
        else:
            counts["answered"] += 1
            tag = f"answered, {len(ans.get('verified_citations', []))} citations"
        print(f"{q['qid']}  {tag}  {dt:.1f}s")
    print(f"\n{counts}  in {time.perf_counter() - t_all:.0f}s")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
