"""The judge job: an open-weight judge reads audit items in bulk, through any OpenAI-compatible chat
endpoint. The prompts, schemas and reply parsing are the audit pipeline's own
(archive_debugger.audit.prompts), so a bulk run's judgments are the same records an audit run
writes and can be calibrated the same way.

Endpoints: a local Ollama server on this machine (CPU), Workers AI (gpt-oss-120b, metered by its
own account), or a vLLM server the cluster runs as a Deployment (k8s/judge-server). The endpoint
and model come from the job spec's executor section.

Input unit: <input_prefix>/items/<id>.jsonl, audit items. Output: <id>.jsonl, one judgment per item:
{item_id, kind, verdicts, error, model, endpoint, prompt_version}. A reply that is not a valid
verdict is recorded with its error and no verdicts, never as a pass."""
from __future__ import annotations

import json
import os
from typing import Callable

from archive_debugger.audit import prompts
from archive_debugger.audit.budget import Ledger, worst_case
from archive_debugger.jobs import net
from archive_debugger.jobs.spec import REPO, JobSpec, executor_settings

# Paid endpoints are metered in Phase G and 4 prep's own ledger (Jake, 2026-11-01: $40 hard cap).
LEDGER = REPO / "reports" / "v2" / "scale" / "ledger.jsonl"
PHASE_CAP_USD = 40.00

WORKERS_AI_CHAT = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions"


def endpoint_for(spec: JobSpec, executor: str) -> tuple:
    s = executor_settings(spec, executor)
    if executor == "workers_ai":
        account, token = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_AI_TOKEN")
        if not account or not token:
            raise RuntimeError("the Workers AI executor needs CF_ACCOUNT_ID and CF_AI_TOKEN")
        return WORKERS_AI_CHAT.format(account=account), {"authorization": f"Bearer {token}"}, s["model"]
    url = s.get("endpoint") or os.environ.get("JUDGE_ENDPOINT")
    if not url:
        raise RuntimeError(f"[executor.{executor}] needs an endpoint (or JUDGE_ENDPOINT)")
    headers = {}
    if os.environ.get("JUDGE_API_KEY"):
        headers["authorization"] = f"Bearer {os.environ['JUDGE_API_KEY']}"
    return url.rstrip("/") + "/chat/completions", headers, s["model"]


def judge_one(item: dict, url: str, headers: dict, model: str, max_tokens: int, post: Callable,
              meter: tuple = None) -> dict:
    kind = prompts.kind_of(item)
    body = {"model": model, "max_tokens": max_tokens, "temperature": 0,
            "messages": [{"role": "system", "content": prompts.system(kind)},
                         {"role": "user", "content": prompts.user_message(item) + "\n\n" + prompts.json_instruction(kind)}]}
    verdicts, error = None, None
    reservation = None
    if meter is not None:
        ledger, run_id, run_cap, price_model = meter
        reservation = f"{run_id}:{item['item_id']}"
        chars = sum(len(m["content"]) for m in body["messages"])
        ledger.reserve(run_id, run_cap, "workers-ai", price_model, reservation, worst_case(price_model, chars, max_tokens))
    try:
        reply = post(url, headers, body)
        if meter is not None:
            usage = reply.get("usage") or {}
            ledger.spend(run_id, "workers-ai", price_model, int(usage.get("prompt_tokens") or 0),
                         int(usage.get("completion_tokens") or max_tokens), what=f"judge {item['item_id']}")
        choice = (reply.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        if choice.get("finish_reason") == "length":
            error = "max_tokens"
        else:
            verdicts = prompts.parse_verdicts(text, kind)
    except net.HttpError as exc:
        error = f"http {exc.status}"
    except ValueError as exc:
        error = f"unreadable: {exc}"
    finally:
        if reservation is not None:
            ledger.release(run_id, reservation)
    return {"item_id": item["item_id"], "kind": kind, "verdicts": verdicts, "error": error, "model": model,
            "prompt_version": prompts.version_for(kind)}


def make_process(spec: JobSpec, executor: str, *, post: Callable = None) -> Callable:
    url, headers, model = endpoint_for(spec, executor)
    post = post or net.post_json
    max_tokens = int(spec.params.get("max_tokens", 1500))
    meter = None
    if executor == "workers_ai":
        settings = executor_settings(spec, executor)
        if "run_cap_usd" not in settings or "price_model" not in settings:
            raise RuntimeError("a paid endpoint needs run_cap_usd and price_model in [executor.workers_ai]")
        meter = (Ledger(LEDGER, phase_cap=PHASE_CAP_USD), f"{spec.name}:{settings.get('run', 'run-1')}",
                 float(settings["run_cap_usd"]), settings["price_model"])

    def process(unit: dict, store, _spec: JobSpec) -> tuple:
        raw = store.get(f"{spec.input_prefix.rstrip('/')}/items/{unit['id']}.jsonl").decode("utf-8")
        items = [json.loads(line) for line in raw.splitlines() if line.strip()]
        rows = [judge_one(it, url, headers, model, max_tokens, post, meter) for it in items]
        body = "".join(json.dumps({**r, "endpoint": executor}, ensure_ascii=True) + "\n" for r in rows)
        errors = sum(1 for r in rows if r["error"])
        return body.encode("utf-8"), "jsonl", {"model": model, "backend": executor, "items": len(rows), "errors": errors}
    return process
