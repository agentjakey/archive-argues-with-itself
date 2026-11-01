"""Model judges (docs/formats/audit.md). Each judge reads one item and returns the verdicts for
the item's unit: SUPPORTS and IN SCOPE for a sentence item, ANSWERS for an answer item. Anthropic
judges run as Message Batches (half price) or direct calls, straight to Anthropic. Workers AI judges
run as direct calls, through the AI Gateway named in config/audit.toml when one is set. Every call
is checked against the budget first and its cost recorded after.

A judgment that could not be read (an error, a refusal, a reply that is not a valid verdict) is
recorded with its error and no verdicts, and counts as missing, never as a pass."""
from __future__ import annotations

import hashlib
import os
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from archive_debugger.audit import net, prompts
from archive_debugger.audit.budget import Ledger, worst_case

REPO = Path(__file__).resolve().parents[3]
AUDIT_CONFIG = REPO / "config" / "audit.toml"
WORKERS_AI_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions"
BATCH_POLL_S = 20.0
BATCH_WAIT_LIMIT_S = 3 * 3600.0


@dataclass(frozen=True)
class JudgeSpec:
    name: str
    provider: str
    model: str
    family: str
    max_tokens: int
    batch: bool = False
    effort: Optional[str] = None
    reasoning_effort: Optional[str] = None
    prompt: str = "panel"                 # "reference": the author's guide, full pages, reasoning allowed


@dataclass(frozen=True)
class PanelConfig:
    judges: tuple
    escalation: str
    candidates: tuple
    specs: dict
    workers_ai_gateway: Optional[str] = None
    review_share: float = 0.10            # share of agreed passes the escalation judge re-reads
    lenient_above: float = 0.10           # escalation disagreement on that sample that flags a check
    references: tuple = ()                # reference judges (silver labels); never panel, escalation or candidate
    check_panels: dict = None             # {check: (judges, escalation or None)} where a check has its own panel

    def route(self, check: str) -> tuple:
        """(the two judges, the escalation judge or None) that decide one check."""
        if self.check_panels and check in self.check_panels:
            return self.check_panels[check]
        return self.judges, self.escalation

    def deciding_judges(self) -> list:
        """Every judge whose verdict can decide a check: the default pair, the per-check pairs and
        every escalation judge in use, in a stable order."""
        names = list(self.judges) + [self.escalation]
        for judges_, esc in (self.check_panels or {}).values():
            names += list(judges_) + ([esc] if esc else [])
        return list(dict.fromkeys(names))


def load_panel(path: Path = AUDIT_CONFIG) -> PanelConfig:
    with Path(path).open("rb") as fh:
        raw = tomllib.load(fh)
    specs = {name: JudgeSpec(name=name, provider=j["provider"], model=j["model"], family=j["family"],
                             max_tokens=int(j["max_tokens"]), batch=bool(j.get("batch", False)),
                             effort=j.get("effort"), reasoning_effort=j.get("reasoning_effort"),
                             prompt=j.get("prompt", "panel"))
             for name, j in (raw.get("judges") or {}).items()}
    panel = raw["panel"]
    check_panels = {}
    for check, row in (panel.get("checks") or {}).items():
        pair = tuple(row["judges"])
        esc = row.get("escalation") or None
        if len(pair) != 2 or any(n not in specs for n in pair) or (esc and esc not in specs):
            raise ValueError(f"{path}: [panel.checks.{check}] needs two defined judges and a defined escalation or none")
        if specs[pair[0]].family == specs[pair[1]].family:
            raise ValueError(f"{path}: [panel.checks.{check}] needs two judges from two different model families")
        if esc in pair:
            raise ValueError(f"{path}: [panel.checks.{check}] escalation cannot be one of its own judges")
        check_panels[check] = (pair, esc)
    names = list(panel["judges"]) + [panel["escalation"]] + list(panel.get("candidates") or [])
    names += [n for pair, esc in check_panels.values() for n in list(pair) + ([esc] if esc else [])]
    missing = [n for n in names if n not in specs]
    if missing:
        raise ValueError(f"{path}: judges named in [panel] but not defined: {missing}")
    if len(panel["judges"]) != 2 or len({specs[n].family for n in panel["judges"]}) != 2:
        raise ValueError(f"{path}: the panel needs two judges from two different model families")
    gateway = (raw.get("gateway") or {}).get("workers_ai") or None
    references = tuple((raw.get("reference") or {}).get("judges") or ())
    unknown = [n for n in references if n not in specs]
    if unknown:
        raise ValueError(f"{path}: reference judges not defined: {unknown}")
    on_panel = [n for n in references if n in names]
    if on_panel:
        raise ValueError(f"{path}: a reference judge cannot also be a panel, escalation or candidate judge: {on_panel}")
    if len({specs[n].family for n in references}) != len(references):
        raise ValueError(f"{path}: the reference judges must come from different model families")
    return PanelConfig(check_panels=check_panels, references=references,judges=tuple(panel["judges"]), escalation=panel["escalation"],
                       candidates=tuple(panel.get("candidates") or ()), specs=specs, workers_ai_gateway=gateway,
                       review_share=float(panel.get("review_share", 0.10)),
                       lenient_above=float(panel.get("lenient_above", 0.10)))


def with_routes(cfg: PanelConfig, overrides: list) -> PanelConfig:
    """The panel with some checks decided by another pair for one run (for example a panel without
    the writer's model or family). Each override is check=judge_a,judge_b[,escalation]; "all" sets
    every check. The two judges must come from two families."""
    if not overrides:
        return cfg
    from dataclasses import replace
    routes = dict(cfg.check_panels or {})
    for spec in overrides:
        check, _, names = spec.partition("=")
        parts = [n.strip() for n in names.split(",") if n.strip()]
        if len(parts) not in (2, 3) or any(n not in cfg.specs for n in parts):
            raise ValueError(f"bad route {spec!r}: check=judge_a,judge_b[,escalation] with defined judges")
        if cfg.specs[parts[0]].family == cfg.specs[parts[1]].family:
            raise ValueError(f"bad route {spec!r}: the two judges must come from two families")
        pair, esc = (parts[0], parts[1]), (parts[2] if len(parts) == 3 else None)
        checks = prompts.ALL_CHECKS if check == "all" else (check,)
        for c in checks:
            routes[c] = (pair, esc)
    return replace(cfg, check_panels=routes)


def same_model(a: str, b: str) -> bool:
    """claude-haiku-4-5 and claude-haiku-4-5-20251001 name the same model."""
    a, b = (a or "").lower(), (b or "").lower()
    return bool(a and b) and (a == b or a.startswith(b + "-") or b.startswith(a + "-"))


def writer_conflicts(cfg: PanelConfig, items: list, *, include_escalation: bool = True) -> list:
    """Panel and escalation judges whose model wrote some of these answers. The panel never includes
    the model that wrote the answers it judges; candidates may, since they decide nothing. A run
    that never calls the escalation judge (no escalation, no leniency review) does not check it."""
    out = set()
    for it in items:
        writer = it.get("writer_model")
        if not writer:
            continue
        for check in prompts.KIND_CHECKS[prompts.kind_of(it)]:
            pair, esc = cfg.route(check)
            deciding = list(pair) + ([esc] if esc and include_escalation else [])
            out |= {name for name in deciding if same_model(cfg.specs[name].model, writer)}
    return sorted(out)


def custom_id(item_id: str) -> str:
    """A batch request id (letters, digits, - and _, at most 64) that names one item."""
    return "i" + hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:40]


def _record(spec: JudgeSpec, item: dict, verdicts: Optional[dict], error: Optional[str], input_tokens: int,
            output_tokens: int, usd: float, batch: bool, cached: bool = False) -> dict:
    return {"item_id": item["item_id"], "kind": prompts.kind_of(item), "judge": spec.name, "provider": spec.provider,
            "model": spec.model, "family": spec.family, "prompt_style": spec.prompt,
            "prompt_version": prompts.version_for(prompts.kind_of(item), spec.prompt), "batch": batch,
            "verdicts": verdicts, "error": error, "input_tokens": input_tokens, "output_tokens": output_tokens,
            "usd": round(usd, 6), "cached": cached, "at": round(time.time(), 3)}


# --- Anthropic ---------------------------------------------------------------------------------

def anthropic_client():
    """The SDK client. Tests replace this function."""
    import anthropic
    return anthropic.Anthropic(max_retries=3)


def anthropic_params(spec: JudgeSpec, item: dict) -> dict:
    kind = prompts.kind_of(item)
    params = {
        "model": spec.model,
        "max_tokens": spec.max_tokens,
        "system": prompts.system(kind, spec.prompt),
        "messages": [{"role": "user", "content": prompts.user_message(item, spec.prompt)}],
        "output_config": {"format": {"type": "json_schema", "schema": prompts.verdict_schema(kind)}},
    }
    if spec.effort:
        # Models with effort levels take no sampling parameters; the schema constrains the reply.
        params["output_config"]["effort"] = spec.effort
    else:
        params["temperature"] = 0.0
    return params


def _message_text(message) -> tuple:
    if getattr(message, "stop_reason", None) == "refusal":
        return None, "refusal"
    text = "".join(getattr(b, "text", "") for b in message.content if getattr(b, "type", "") == "text")
    if getattr(message, "stop_reason", None) == "max_tokens":
        return None, "max_tokens"
    return text, None


def _read(text: Optional[str], error: Optional[str], kind: str) -> tuple:
    if error:
        return None, error
    try:
        return prompts.parse_verdicts(text, kind), None
    except ValueError as exc:
        return None, f"unreadable: {exc}"


def prompt_chars(item: dict, style: str = "panel") -> int:
    kind = prompts.kind_of(item)
    return len(prompts.system(kind, style)) + len(prompts.user_message(item, style)) + 2000   # schema and framing


class BatchState:
    """Where an Anthropic batch stands, so a stopped run picks its batch up again."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict:
        import json
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def save(self, state: dict) -> None:
        import json
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")


def run_anthropic_batch(spec: JudgeSpec, items: list, ledger: Ledger, run_id: str, run_cap: float,
                        state_path: Path, *, client_factory: Callable = anthropic_client,
                        sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> list:
    """Judge `items` in one Message Batch and return their judgment records. Reserves the batch's worst
    case before submitting; resumes an already submitted batch from state_path."""
    client = client_factory()
    state_store = BatchState(state_path)
    state = state_store.load()
    by_cid = {custom_id(it["item_id"]): it for it in items}
    if not state.get("batch_id"):
        worst = sum(worst_case(spec.model, prompt_chars(it, spec.prompt), spec.max_tokens, batch=True) for it in items)
        reservation = f"{run_id}:{spec.name}:batch:{len(items)}:{int(time.time())}"
        ledger.reserve(run_id, run_cap, spec.provider, spec.model, reservation, worst)
        # Plain dicts in the SDK's request shape, so importing this module never loads the SDK.
        requests = [{"custom_id": cid, "params": anthropic_params(spec, it)} for cid, it in by_cid.items()]
        try:
            batch = client.messages.batches.create(requests=requests)
        except Exception:
            ledger.release(run_id, reservation)       # nothing was submitted, so nothing can be billed
            raise
        state = {"batch_id": batch.id, "reservation": reservation, "items": len(items), "worst_usd": round(worst, 6)}
        state_store.save(state)
        log(f"[{spec.name}] batch {batch.id}: {len(items)} items, up to ${worst:.4f} reserved")
    waited = 0.0
    while True:
        batch = client.messages.batches.retrieve(state["batch_id"])
        if batch.processing_status == "ended":
            break
        if waited > BATCH_WAIT_LIMIT_S:
            raise TimeoutError(f"batch {state['batch_id']} still {batch.processing_status}; run again to resume")
        sleep(BATCH_POLL_S)
        waited += BATCH_POLL_S
    records = []
    input_total = output_total = 0
    for result in client.messages.batches.results(state["batch_id"]):
        item = by_cid.get(result.custom_id)
        if item is None:
            continue
        if result.result.type == "succeeded":
            message = result.result.message
            usage = message.usage
            input_tokens = int(usage.input_tokens or 0) + int(getattr(usage, "cache_read_input_tokens", 0) or 0) \
                + int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
            output_tokens = int(usage.output_tokens or 0)
            verdicts, error = _read(*_message_text(message), prompts.kind_of(item))
        else:
            input_tokens = output_tokens = 0
            verdicts, error = None, f"batch {result.result.type}"
        input_total += input_tokens
        output_total += output_tokens
        from archive_debugger.audit.prices import cost
        records.append(_record(spec, item, verdicts, error, input_tokens, output_tokens,
                               cost(spec.model, input_tokens, output_tokens, batch=True), True))
    ledger.spend(run_id, spec.provider, spec.model, input_total, output_total, batch=True,
                 what=f"{spec.name} batch {state['batch_id']} ({len(records)} items)")
    ledger.release(run_id, state["reservation"])
    state_store.save({})
    return records


def run_anthropic_direct(spec: JudgeSpec, item: dict, ledger: Ledger, run_id: str, run_cap: float, *,
                         client_factory: Callable = anthropic_client) -> dict:
    reservation = f"{run_id}:{spec.name}:{item['item_id']}:{time.time_ns()}"
    ledger.reserve(run_id, run_cap, spec.provider, spec.model, reservation,
                   worst_case(spec.model, prompt_chars(item, spec.prompt), spec.max_tokens))
    try:
        message = client_factory().messages.create(**anthropic_params(spec, item))
        input_tokens, output_tokens = int(message.usage.input_tokens or 0), int(message.usage.output_tokens or 0)
        usd = ledger.spend(run_id, spec.provider, spec.model, input_tokens, output_tokens, what=f"{spec.name} {item['item_id']}")
    finally:
        ledger.release(run_id, reservation)
    verdicts, error = _read(*_message_text(message), prompts.kind_of(item))
    return _record(spec, item, verdicts, error, input_tokens, output_tokens, usd, False)


# --- Workers AI --------------------------------------------------------------------------------

def workers_ai_credentials() -> tuple:
    """CF_ACCOUNT_ID and CF_AI_TOKEN (never CLOUDFLARE_API_TOKEN, which would override the account
    owner's wrangler login)."""
    account, token = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_AI_TOKEN")
    if not account or not token:
        raise RuntimeError("Workers AI judges need CF_ACCOUNT_ID and CF_AI_TOKEN in the environment or .env")
    return account, token


def workers_ai_headers(token: str, gateway: Optional[str]) -> dict:
    """Request headers. With a gateway, the request names it (cf-aig-gateway-id) and carries the
    gateway's own token, CF_AIG_TOKEN (cf-aig-authorization). Audit traffic only: no visitor data
    passes through the gateway."""
    headers = {"authorization": f"Bearer {token}"}
    if gateway:
        aig = os.environ.get("CF_AIG_TOKEN")
        if not aig:
            raise RuntimeError(f"the AI Gateway {gateway} needs CF_AIG_TOKEN in the environment or .env")
        headers["cf-aig-gateway-id"] = gateway
        headers["cf-aig-authorization"] = f"Bearer {aig}"
    return headers


def workers_ai_body(spec: JudgeSpec, item: dict, structured: bool) -> dict:
    kind = prompts.kind_of(item)
    body = {
        "model": spec.model,
        "max_tokens": spec.max_tokens,
        "temperature": 0,
        "messages": [{"role": "system", "content": prompts.system(kind, spec.prompt)},
                     {"role": "user", "content": prompts.user_message(item, spec.prompt) +"\n\n" + prompts.json_instruction(kind)}],
    }
    if spec.reasoning_effort:
        body["reasoning_effort"] = spec.reasoning_effort
    if structured:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "verdicts", "schema": prompts.verdict_schema(kind), "strict": True}}
    return body


def run_workers_ai(spec: JudgeSpec, item: dict, ledger: Ledger, run_id: str, run_cap: float, *,
                   post: Callable = None, credentials: Callable = workers_ai_credentials,
                   gateway: Optional[str] = None) -> dict:
    post = post or net.post_json
    account, token = credentials()
    url = WORKERS_AI_URL.format(account=account)
    headers = workers_ai_headers(token, gateway)
    reply_headers: dict = {}
    chars = prompt_chars(item, spec.prompt) +len(prompts.json_instruction(prompts.kind_of(item)))
    worst = worst_case(spec.model, chars, spec.max_tokens)
    reservation = f"{run_id}:{spec.name}:{item['item_id']}:{time.time_ns()}"
    ledger.reserve(run_id, run_cap, spec.provider, spec.model, reservation, worst)
    try:
        try:
            reply = post(url, headers, workers_ai_body(spec, item, structured=True), response_headers=reply_headers)
        except net.HttpError as exc:
            if exc.status != 400:
                raise
            # A model that does not take a JSON schema gets the same prompt, which states the schema.
            reply_headers.clear()
            reply = post(url, headers, workers_ai_body(spec, item, structured=False), response_headers=reply_headers)
        usage = reply.get("usage") or {}
        estimated = not usage
        input_tokens = int(usage.get("prompt_tokens") or 0) if usage else int(chars / 2.5)
        output_tokens = int(usage.get("completion_tokens") or 0) if usage else spec.max_tokens
        # A reply the gateway served from its cache never reached the model and is not billed.
        cached = str(reply_headers.get("cf-aig-cache-status", "")).upper() == "HIT"
        if cached:
            usd = 0.0
        else:
            usd = ledger.spend(run_id, spec.provider, spec.model, input_tokens, output_tokens,
                               what=f"{spec.name} {item['item_id']}" + (" (usage not reported: worst case)" if estimated else ""))
    finally:
        ledger.release(run_id, reservation)
    choice = (reply.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    text = message.get("content")
    if isinstance(text, list):
        text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
    error = None
    if choice.get("finish_reason") == "length":
        error = "max_tokens"
    elif not text:
        error = "empty reply"
    verdicts, error = _read(text, error, prompts.kind_of(item))
    return _record(spec, item, verdicts, error, input_tokens, output_tokens, usd, False, cached)


def run_workers_ai_many(spec: JudgeSpec, items: list, ledger: Ledger, run_id: str, run_cap: float, *,
                        workers: int = 3, post: Callable = None, on_record: Callable[[dict], None] = None,
                        gateway: Optional[str] = None) -> list:
    """Judge several items, a few at a time (polite to the API); each record is handed to on_record
    as soon as it exists, so a stopped run keeps what it finished."""
    records = []

    def one(it):
        try:
            rec = run_workers_ai(spec, it, ledger, run_id, run_cap, post=post, gateway=gateway)
        except net.HttpError as exc:
            rec = _record(spec, it, None, f"http {exc.status}", 0, 0, 0.0, False)
        if on_record:
            on_record(rec)
        return rec

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for rec in pool.map(one, items):
            records.append(rec)
    return records
