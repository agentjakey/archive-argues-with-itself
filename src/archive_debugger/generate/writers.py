"""Writer providers for the v2 answer: one interface, three kinds of endpoint.

    anthropic      the Anthropic Messages API (answer_v2.AnthropicWriter)
    workers_ai     Workers AI through its OpenAI-compatible chat completions route
    openai_compat  any OpenAI-compatible chat completions endpoint (a hosted API, a vLLM server, a
                   llama.cpp server behind a tunnel)

Every writer has draft(system, user) -> Draft2 and last_usage. Base URLs, the environment variables
that hold keys, and any extra headers come from config/writers.toml and the environment; no vendor
endpoint or model name is written here. Keys are read from the environment only and never logged.

The writer makes one try per draft, no retries, like the Anthropic writer (max_retries=0), and the
whole draft must finish within its timeout (a total deadline, fallback included): the engine gives
the model a time budget, and a retry or a slow trickle of bytes would overrun it. The OpenAI-compatible writer sends the same system prompt and user prompt as the Anthropic writer,
temperature 0, and asks for the Draft2 JSON schema as a structured response. An endpoint that refuses
a JSON schema (HTTP 400) gets the same request with the schema stated in the prompt instead and
response_format json_object; the reply is validated against Draft2 either way. Plain HTTP goes through
audit/net.py, the one module that reaches the network outside the Anthropic SDK (one retry rule)."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from archive_debugger.generate import answer_v2

PROVIDERS = ("anthropic", "workers_ai", "openai_compat")
REPO = Path(__file__).resolve().parents[3]
WRITERS_CONFIG = REPO / "config" / "writers.toml"
# Fields of the request the writer always sets itself; a candidate's extra_body may add others (a
# model's reasoning setting, for example) but never these.
OWNED_FIELDS = frozenset({"model", "messages", "max_tokens", "temperature", "response_format", "stream"})
_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="writer")
SCHEMA_NOTE = ("Reply with one JSON object and nothing else, matching this JSON schema exactly:\n")


@dataclass(frozen=True)
class Endpoint:
    """Where an OpenAI-compatible writer sends its requests. base_url may hold {NAME} placeholders,
    filled from environment variables of that name (an account id, for example)."""
    provider: str
    base_url: str
    key_env: str
    header_envs: dict = field(default_factory=dict)   # header name -> environment variable
    temperature: Optional[float] = 0.0
    json_schema: bool = True


def load_endpoints(path: Path = WRITERS_CONFIG) -> dict:
    """{provider or endpoint name: Endpoint} from [endpoints.<name>] in config/writers.toml."""
    if not Path(path).exists():
        return {}
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for name, e in (raw.get("endpoints") or {}).items():
        provider = e.get("provider", name)
        if provider not in PROVIDERS or provider == "anthropic":
            raise ValueError(f"endpoint {name}: provider must be workers_ai or openai_compat, not {provider!r}")
        temp = e.get("temperature", 0.0)
        out[name] = Endpoint(provider=provider, base_url=str(e["base_url"]), key_env=str(e["key_env"]),
                             header_envs=dict(e.get("header_envs") or {}),
                             temperature=None if temp == "omit" else float(temp),
                             json_schema=bool(e.get("json_schema", True)))
    return out


def load_candidates(path: Path = WRITERS_CONFIG) -> dict:
    """{candidate name: dict} from [candidates.<name>]: provider or endpoint, model, price model,
    licence and where it can run, for the writer comparison."""
    if not Path(path).exists():
        return {}
    return dict(tomllib.loads(Path(path).read_text(encoding="utf-8")).get("candidates") or {})


def _fill(template: str, env: dict) -> str:
    out = template
    while "{" in out:
        start = out.index("{")
        end = out.index("}", start)
        name = out[start + 1:end]
        value = env.get(name)
        if not value:
            raise RuntimeError(f"the writer endpoint needs {name} in the environment or .env")
        out = out[:start] + value + out[end + 1:]
    return out


def resolve(endpoint: Endpoint, env: Optional[dict] = None) -> tuple:
    """(chat completions URL, headers) with the key and extra headers from the environment."""
    env = dict(os.environ) if env is None else env
    key = env.get(endpoint.key_env)
    if not key:
        raise RuntimeError(f"the {endpoint.provider} writer needs {endpoint.key_env} in the environment or .env")
    url = _fill(endpoint.base_url, env).rstrip("/") + "/chat/completions"
    headers = {"authorization": f"Bearer {key}"}
    for header, var in endpoint.header_envs.items():
        value = env.get(var)
        if not value:
            raise RuntimeError(f"the writer endpoint needs {var} in the environment or .env (header {header})")
        headers[header.lower()] = value
    return url, headers


class OpenAICompatWriter:
    """The v2 writer over an OpenAI-compatible chat completions endpoint. post is injectable for
    tests (audit.net.post_json by default)."""

    def __init__(self, endpoint: Endpoint, model: str, max_tokens: int, *, timeout: float = 60.0,
                 env: Optional[dict] = None, post: Optional[Callable] = None, extra_body: Optional[dict] = None):
        self.endpoint, self.model, self.max_tokens, self.timeout = endpoint, model, max_tokens, timeout
        clash = sorted(set(extra_body or {}) & OWNED_FIELDS)
        if clash:
            raise ValueError(f"extra_body may not set {clash}: the writer sets those itself")
        self.extra_body = dict(extra_body or {})
        self.url, self._headers = resolve(endpoint, env)
        if post is None:
            from archive_debugger.audit import net
            post = net.post_json
        self._post = post
        self.effort = None
        self.last_usage: dict = {}
        self.last_meta: dict = {}

    def body(self, system: str, user: str, structured: bool) -> dict:
        schema = answer_v2.Draft2.model_json_schema()
        if not structured:
            user = user + "\n\n" + SCHEMA_NOTE + json.dumps(schema)
        body = {"model": self.model, "max_tokens": self.max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.endpoint.temperature is not None:
            body["temperature"] = self.endpoint.temperature
        body["response_format"] = ({"type": "json_schema", "json_schema": {"name": "draft", "schema": schema}}
                                   if structured else {"type": "json_object"})
        body.update(self.extra_body)
        return body

    def _post_by(self, deadline: float, body: dict) -> dict:
        """One request that must finish by the deadline (time.monotonic()). A socket timeout bounds
        each read, not the whole reply, so the request runs on a worker thread and is abandoned,
        not waited for, once the deadline passes."""
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("writer deadline passed")
        future = _POOL.submit(self._post, self.url, self._headers, body, timeout_s=left, attempts=1)
        try:
            return future.result(timeout=left)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"writer reply not finished within {self.timeout:.0f} s") from None

    def draft(self, system: str, user: str) -> answer_v2.Draft2:
        from archive_debugger.audit import net
        self.last_usage, self.last_meta = {}, {}
        structured = self.endpoint.json_schema
        deadline = time.monotonic() + self.timeout        # the whole draft, fallback included
        try:
            reply = self._post_by(deadline, self.body(system, user, structured))
        except net.HttpError as exc:
            if exc.status != 400 or not structured:
                raise
            structured = False
            reply = self._post_by(deadline, self.body(system, user, False))
        usage = reply.get("usage") or {}
        self.last_usage = {"input_tokens": int(usage.get("prompt_tokens") or 0),
                           "output_tokens": int(usage.get("completion_tokens") or 0)}
        if not usage:
            self.last_usage["reported"] = False
        choice = (reply.get("choices") or [{}])[0]
        self.last_meta = {"structured": structured, "finish_reason": choice.get("finish_reason"),
                          "served_model": reply.get("model")}
        if choice.get("finish_reason") == "length":
            raise ValueError("writer reply cut off at max_tokens")
        text = (choice.get("message") or {}).get("content")
        if isinstance(text, list):
            text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
        if not text:
            raise ValueError("empty writer reply")
        return answer_v2.Draft2.model_validate(json.loads(_strip_fence(text)))


def _strip_fence(text: str) -> str:
    """The JSON object in a reply, without a Markdown code fence or text around it."""
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the writer reply")
    return text[start:end + 1]


V2_WRITERS = (answer_v2.AnthropicWriter, answer_v2.StubWriter, OpenAICompatWriter)


def extra_digest(extra_body: Optional[dict]) -> str:
    """16 hex characters naming a writer's extra request fields; empty when there are none."""
    if not extra_body:
        return ""
    return hashlib.sha256(json.dumps(extra_body, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def make_writer(provider: str, model: str, max_tokens: int, *, effort: Optional[str] = None,
                endpoint: Optional[str] = None, timeout: float = 60.0, client=None,
                endpoints: Optional[dict] = None, env: Optional[dict] = None, post: Optional[Callable] = None,
                extra_body: Optional[dict] = None):
    """The v2 writer for a provider. endpoint names an [endpoints.<name>] entry (default: the
    provider's own name)."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown writer provider {provider!r} (known: {', '.join(PROVIDERS)})")
    if provider == "anthropic":
        if extra_body:
            raise ValueError("extra_body is for OpenAI-compatible writers")
        return answer_v2.AnthropicWriter(model, max_tokens, effort=effort, client=client, timeout=timeout)
    endpoints = load_endpoints() if endpoints is None else endpoints
    name = endpoint or provider
    if name not in endpoints:
        raise RuntimeError(f"no [endpoints.{name}] in config/writers.toml for the {provider} writer")
    ep = endpoints[name]
    if ep.provider != provider:
        raise ValueError(f"endpoint {name} is a {ep.provider} endpoint, not {provider}")
    return OpenAICompatWriter(ep, model, max_tokens, timeout=timeout, env=env, post=post, extra_body=extra_body)
