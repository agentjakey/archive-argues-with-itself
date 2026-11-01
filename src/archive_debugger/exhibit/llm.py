"""Model calls for offline drafting and checking of exhibit rounds. Nothing here runs on the exhibit
floor: the kiosk and the online exhibit only read finished decks.

Every call is metered in the exhibit's own ledger (config/exhibit.toml [budget]) with the audit's
Ledger: the worst case is reserved before a call and the actual cost recorded after, and a call
that could cross the run cap or the phase cap is not made. Anthropic calls run as Message Batches
(half price) and resume from their state file; Workers AI calls go through the audit's network
module and AI Gateway settings. Replies must match a JSON schema; one that does not is recorded as
an error, never as a result."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from archive_debugger.audit import judges, net
from archive_debugger.audit.budget import Ledger, worst_case
from archive_debugger.audit.prices import cost

BATCH_POLL_S = 20.0
BATCH_WAIT_LIMIT_S = 6 * 3600.0


def anthropic_request(model: str, system: str, user: str, schema: dict, *, max_tokens: int,
                      effort: Optional[str]) -> dict:
    params = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }
    if effort:
        params["output_config"]["effort"] = effort
    return params


def repair_text(text: str) -> str:
    """Undo UTF-8 read as a single-byte encoding. Batch results arrive as a JSON Lines stream whose
    encoding the HTTP client sometimes guesses wrong, so "h" + chr(0xF4) + "pital" comes back as its
    UTF-8 bytes read one by one. A correct string never round-trips this way, so it is returned
    unchanged."""
    for encoding in ("cp1252", "latin-1"):
        try:
            fixed = text.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        return fixed
    return text


def repair_value(value):
    if isinstance(value, str):
        return repair_text(value)
    if isinstance(value, list):
        return [repair_value(v) for v in value]
    if isinstance(value, dict):
        return {k: repair_value(v) for k, v in value.items()}
    return value


def _reply_json(text: Optional[str]) -> dict:
    if not text:
        raise ValueError("empty reply")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the reply")
    return repair_value(json.loads(text[start:end + 1]))


def run_anthropic_batch(requests: dict, ledger: Ledger, run_id: str, run_cap: float, state_path: Path, *,
                        what: str, client_factory: Callable = judges.anthropic_client,
                        sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> dict:
    """Send {key: params} as one Message Batch; return {key: {"reply", "error", "input_tokens",
    "output_tokens", "usd"}}. A stopped run resumes the submitted batch from state_path."""
    client = client_factory()
    store = judges.BatchState(state_path)
    state = store.load()
    by_cid = {judges.custom_id(key): key for key in requests}
    if not state.get("batch_id"):
        worst = 0.0
        for params in requests.values():
            chars = len(params["system"]) + sum(len(m["content"]) for m in params["messages"]) + 2000
            worst += worst_case(params["model"], chars, params["max_tokens"], batch=True)
        model = next(iter(requests.values()))["model"]
        reservation = f"{run_id}:{what}:batch:{len(requests)}:{int(time.time())}"
        ledger.reserve(run_id, run_cap, "anthropic", model, reservation, worst)
        try:
            batch = client.messages.batches.create(
                requests=[{"custom_id": cid, "params": requests[key]} for cid, key in by_cid.items()])
        except Exception:
            ledger.release(run_id, reservation)
            raise
        state = {"batch_id": batch.id, "reservation": reservation, "model": model, "keys": len(requests),
                 "worst_usd": round(worst, 6)}
        store.save(state)
        log(f"[{what}] batch {batch.id}: {len(requests)} requests, up to ${worst:.4f} reserved")
    waited = 0.0
    while True:
        batch = client.messages.batches.retrieve(state["batch_id"])
        if batch.processing_status == "ended":
            break
        if waited > BATCH_WAIT_LIMIT_S:
            raise TimeoutError(f"batch {state['batch_id']} still {batch.processing_status}; run again to resume")
        sleep(BATCH_POLL_S)
        waited += BATCH_POLL_S
    out = {}
    in_total = out_total = 0
    for result in client.messages.batches.results(state["batch_id"]):
        key = by_cid.get(result.custom_id)
        if key is None:
            continue
        reply, error, tin, tout = None, None, 0, 0
        if result.result.type == "succeeded":
            message = result.result.message
            usage = message.usage
            tin = int(usage.input_tokens or 0) + int(getattr(usage, "cache_read_input_tokens", 0) or 0) \
                + int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
            tout = int(usage.output_tokens or 0)
            if message.stop_reason == "refusal":
                error = "refusal"
            elif message.stop_reason == "max_tokens":
                error = "max_tokens"
            else:
                text = "".join(getattr(b, "text", "") for b in message.content if getattr(b, "type", "") == "text")
                try:
                    reply = _reply_json(text)
                except ValueError as exc:
                    error = f"unreadable: {exc}"
        else:
            error = f"batch {result.result.type}"
        in_total += tin
        out_total += tout
        out[key] = {"reply": reply, "error": error, "input_tokens": tin, "output_tokens": tout,
                    "usd": round(cost(state["model"], tin, tout, batch=True), 6), "model": state["model"]}
    ledger.spend(run_id, "anthropic", state["model"], in_total, out_total, batch=True,
                 what=f"{what} batch {state['batch_id']} ({len(out)} replies)")
    ledger.release(run_id, state["reservation"])
    store.save({})
    return out


def run_workers_ai(spec: judges.JudgeSpec, system: str, user: str, schema: dict, ledger: Ledger, run_id: str,
                   run_cap: float, *, gateway: Optional[str], what: str, post: Callable = None) -> dict:
    post = post or net.post_json
    account, token = judges.workers_ai_credentials()
    url = judges.WORKERS_AI_URL.format(account=account)
    headers = judges.workers_ai_headers(token, gateway)
    instruction = "Reply with one JSON object that matches this schema, and nothing else:\n" + json.dumps(schema)
    body = {"model": spec.model, "max_tokens": spec.max_tokens, "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user + "\n\n" + instruction}]}
    if spec.reasoning_effort:
        body["reasoning_effort"] = spec.reasoning_effort
    chars = len(system) + len(user) + len(instruction)
    reservation = f"{run_id}:{spec.name}:{what}:{time.time_ns()}"
    ledger.reserve(run_id, run_cap, spec.provider, spec.model, reservation, worst_case(spec.model, chars, spec.max_tokens))
    reply_headers: dict = {}
    try:
        try:
            raw = post(url, headers, body, response_headers=reply_headers)
        except net.HttpError as exc:
            return {"reply": None, "error": f"http {exc.status}", "input_tokens": 0, "output_tokens": 0, "usd": 0.0,
                    "model": spec.model}
        usage = raw.get("usage") or {}
        tin = int(usage.get("prompt_tokens") or 0) if usage else int(chars / 2.5)
        tout = int(usage.get("completion_tokens") or 0) if usage else spec.max_tokens
        cached = str(reply_headers.get("cf-aig-cache-status", "")).upper() == "HIT"
        usd = 0.0 if cached else ledger.spend(run_id, spec.provider, spec.model, tin, tout, what=f"{spec.name} {what}")
    finally:
        ledger.release(run_id, reservation)
    choice = (raw.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content")
    if isinstance(text, list):
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    reply, error = None, None
    if choice.get("finish_reason") == "length":
        error = "max_tokens"
    else:
        try:
            reply = _reply_json(text)
        except ValueError as exc:
            error = f"unreadable: {exc}"
    return {"reply": reply, "error": error, "input_tokens": tin, "output_tokens": tout, "usd": round(usd, 6),
            "model": spec.model, "cached": cached}


def run_workers_ai_many(spec: judges.JudgeSpec, prompts: dict, schema: dict, ledger: Ledger, run_id: str,
                        run_cap: float, *, gateway: Optional[str], workers: int = 3, post: Callable = None) -> dict:
    """{key: (system, user)} -> {key: result}, a few at a time."""
    def one(key):
        system, user = prompts[key]
        return key, run_workers_ai(spec, system, user, schema, ledger, run_id, run_cap, gateway=gateway,
                                   what=key, post=post)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(one, list(prompts)))
