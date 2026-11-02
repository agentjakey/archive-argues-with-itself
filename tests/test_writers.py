"""Writer providers (generate/writers.py): endpoint config, the OpenAI-compatible writer, the factory."""
from __future__ import annotations

import json

import pytest

from archive_debugger.audit import net
from archive_debugger.generate import answer_v2, writers

ENV = {"ACCT": "a1", "KEY": "k-secret", "HID": "id-1", "HSEC": "sec-1"}
GOOD = {"sentences": [{"text": "There were 112 hospitals.", "cited_ids": ["x#1:0"]}],
        "evidence_state": "answers", "state_reason": "the passage says so"}


def reply(content, usage=True, finish="stop"):
    out = {"model": "m", "choices": [{"message": {"content": content}, "finish_reason": finish}]}
    if usage:
        out["usage"] = {"prompt_tokens": 400, "completion_tokens": 90}
    return out


class FakePost:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, url, headers, body, timeout_s=None, attempts=None):
        assert attempts == 1          # the writer never retries inside the engine's time budget
        self.calls.append((url, headers, body))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def endpoint(**kw):
    base = dict(provider="openai_compat", base_url="https://host.example/{ACCT}/v1/", key_env="KEY")
    base.update(kw)
    return writers.Endpoint(**base)


def test_load_endpoints_and_candidates(tmp_path):
    cfg = tmp_path / "w.toml"
    cfg.write_text('[endpoints.x]\nprovider = "openai_compat"\nbase_url = "https://h/v1"\nkey_env = "K"\n'
                   'temperature = "omit"\nheader_envs = { "X-Id" = "HID" }\n'
                   '[candidates.c]\nprovider = "workers_ai"\nmodel = "m"\n', encoding="utf-8")
    ep = writers.load_endpoints(cfg)["x"]
    assert ep.temperature is None and ep.header_envs == {"X-Id": "HID"} and ep.json_schema
    assert writers.load_candidates(cfg)["c"]["model"] == "m"
    cfg.write_text('[endpoints.x]\nprovider = "anthropic"\nbase_url = "u"\nkey_env = "K"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        writers.load_endpoints(cfg)
    # The shipped config parses and names no key value.
    shipped = writers.load_endpoints()
    assert {"workers_ai", "openai_compat"} <= set(shipped)
    assert all(e.key_env.isupper() for e in shipped.values())


def test_resolve_fills_the_url_and_headers_from_the_environment():
    url, headers = writers.resolve(endpoint(header_envs={"CF-Access-Client-Id": "HID"}), ENV)
    assert url == "https://host.example/a1/v1/chat/completions"
    assert headers == {"authorization": "Bearer k-secret", "cf-access-client-id": "id-1"}
    with pytest.raises(RuntimeError, match="KEY"):
        writers.resolve(endpoint(), {"ACCT": "a1"})
    with pytest.raises(RuntimeError, match="ACCT"):
        writers.resolve(endpoint(), {"KEY": "k"})


def test_draft_sends_the_v2_prompt_at_temperature_zero_with_the_schema():
    post = FakePost(reply(json.dumps(GOOD)))
    w = writers.OpenAICompatWriter(endpoint(), "open-model", 2048, env=ENV, post=post)
    d = w.draft("SYS", "USER")
    assert d.evidence_state == "answers" and d.sentences[0].cited_ids == ["x#1:0"]
    assert w.last_usage == {"input_tokens": 400, "output_tokens": 90}
    _url, _headers, body = post.calls[0]
    assert body["model"] == "open-model" and body["temperature"] == 0.0 and body["max_tokens"] == 2048
    assert body["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
    assert body["response_format"]["json_schema"]["schema"] == answer_v2.Draft2.model_json_schema()


def test_a_400_on_the_schema_falls_back_to_json_object_with_the_schema_in_the_prompt():
    fenced = "Here it is:\n```json\n" + json.dumps(GOOD) + "\n```"
    post = FakePost(net.HttpError(400, "response_format not supported"), reply(fenced, usage=False))
    w = writers.OpenAICompatWriter(endpoint(temperature=None), "m", 512, env=ENV, post=post)
    assert w.draft("S", "U").state_reason == "the passage says so"
    body = post.calls[1][2]
    assert body["response_format"] == {"type": "json_object"} and "temperature" not in body
    assert writers.SCHEMA_NOTE in body["messages"][1]["content"]
    assert w.last_usage["reported"] is False and w.last_meta["structured"] is False


def test_other_errors_are_raised():
    w = writers.OpenAICompatWriter(endpoint(), "m", 512, env=ENV, post=FakePost(net.HttpError(401, "no")))
    with pytest.raises(net.HttpError):
        w.draft("S", "U")
    w = writers.OpenAICompatWriter(endpoint(), "m", 512, env=ENV, post=FakePost(reply("{}", finish="length")))
    with pytest.raises(ValueError, match="max_tokens"):
        w.draft("S", "U")
    w = writers.OpenAICompatWriter(endpoint(), "m", 512, env=ENV,
                                   post=FakePost(reply(json.dumps({**GOOD, "evidence_state": "sure"}))))
    with pytest.raises(ValueError):
        w.draft("S", "U")


def test_make_writer():
    eps = {"workers_ai": endpoint(provider="workers_ai"), "tunnel": endpoint()}
    assert isinstance(writers.make_writer("anthropic", "m", 10, client=object()), answer_v2.AnthropicWriter)
    w = writers.make_writer("workers_ai", "m", 10, endpoints=eps, env=ENV, post=FakePost())
    assert isinstance(w, writers.OpenAICompatWriter) and w.url.startswith("https://host.example/a1/")
    assert writers.make_writer("openai_compat", "m", 10, endpoint="tunnel", endpoints=eps, env=ENV, post=FakePost())
    with pytest.raises(ValueError):
        writers.make_writer("openai_compat", "m", 10, endpoint="workers_ai", endpoints=eps, env=ENV)
    with pytest.raises(RuntimeError):
        writers.make_writer("openai_compat", "m", 10, endpoints=eps, env=ENV)
    with pytest.raises(ValueError):
        writers.make_writer("someone", "m", 10)


def test_the_engine_answers_through_an_open_writer(tmp_path):
    """An OpenAI-compatible writer handed to the engine writes the v2 answer, and the provider is
    stamped in the generation metadata."""
    from fastapi.testclient import TestClient
    from archive_debugger.api.app import create_app
    from tests.test_api import _retriever
    cfg = tmp_path / "pilot_v2.toml"
    text = open("config/pilot.toml", encoding="utf-8").read()
    lines = [ln + (chr(10) + 'answer_version = "v2"' if ln.strip() == "[generate]" else "") for ln in text.splitlines()]
    cfg.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    r, _ = _retriever(tmp_path, [("a", 1990, "ontario"), ("b", 1991, "ontario")])
    content = {"sentences": [{"text": "A count.", "cited_ids": ["a#0:0"]}, {"text": "Another count.", "cited_ids": ["b#0:0"]}],
               "evidence_state": "conflicting", "state_reason": "they disagree"}
    post = FakePost(reply(json.dumps(content)))
    writer = writers.OpenAICompatWriter(endpoint(provider="workers_ai"), "open-model", 512, env=ENV, post=post)
    app = create_app(cfg, retriever=r, load_env=False, provider="workers_ai", llm=writer, web_dist=tmp_path / "nodist",
                     cache_path=tmp_path / "cache" / "answers.db")
    with TestClient(app) as c:
        body = c.post("/ask", json={"question": "vaccination hospital"}).json()
    assert body["answer"]["state"] == "CONFLICTING" and len(post.calls) == 1
    assert body["answer"]["generation"]["provider"] == "workers_ai"


def test_the_writer_candidate_flag_replaces_the_configured_writer():
    from archive_debugger.generate.cli import apply_writer_candidate
    g = {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "answer_version": "v1", "top_k": 12}
    assert apply_writer_candidate(g, {}) is g
    cand = next(n for n, c in writers.load_candidates().items() if c["provider"] != "anthropic")
    out = apply_writer_candidate(g, {"CIVIC_WRITER_CANDIDATE": cand, "CIVIC_WRITER_ENDPOINT": "workers_ai_proxy"})
    c = writers.load_candidates()[cand]
    assert out["provider"] == c["provider"] and out["model"] == c["model"] and out["answer_version"] == "v2"
    assert out["endpoint"] == "workers_ai_proxy" and out["top_k"] == 12 and g["provider"] == "anthropic"
    with pytest.raises(ValueError):
        apply_writer_candidate(g, {"CIVIC_WRITER_CANDIDATE": "nobody"})
    # Inside the container the proxy endpoint takes the per-start token and the proxy URL.
    ep = writers.load_endpoints()["workers_ai_proxy"]
    url, headers = writers.resolve(ep, {"CIVIC_AI_PROXY_URL": "http://ai.internal", "CIVIC_CACHE_TOKEN": "t"})
    assert url == "http://ai.internal/v1/chat/completions" and headers == {"authorization": "Bearer t"}


def test_the_whole_draft_must_finish_within_the_timeout():
    import time as _time

    def slow(url, headers, body, timeout_s=None, attempts=None):
        _time.sleep(0.5)
        return reply(json.dumps(GOOD))
    w = writers.OpenAICompatWriter(endpoint(), "m", 512, timeout=0.1, env=ENV, post=slow)
    t0 = _time.monotonic()
    with pytest.raises(TimeoutError):
        w.draft("S", "U")
    assert _time.monotonic() - t0 < 0.4


def test_extra_body_reaches_the_request_but_never_the_owned_fields():
    post = FakePost(reply(json.dumps(GOOD)))
    w = writers.OpenAICompatWriter(endpoint(), "m", 512, env=ENV, post=post, extra_body={"reasoning_effort": "low"})
    w.draft("S", "U")
    assert post.calls[0][2]["reasoning_effort"] == "low" and post.calls[0][2]["max_tokens"] == 512
    with pytest.raises(ValueError, match="max_tokens"):
        writers.OpenAICompatWriter(endpoint(), "m", 512, env=ENV, post=post, extra_body={"max_tokens": 9})
    with pytest.raises(ValueError):
        writers.make_writer("anthropic", "m", 10, client=object(), extra_body={"x": 1})
    assert writers.extra_digest(None) == "" and len(writers.extra_digest({"a": 1})) == 16


def test_extra_body_joins_the_v2_cache_context_only_when_set():
    from archive_debugger.api.app import cache_context
    gcfg = {"answer_version": "v2", "max_tokens": 10, "top_k": 3, "effort": None, "temperature": None}
    args = ("pilot", {"db": "a" * 64, "index": "b" * 64}, {"k": 1})
    plain = cache_context(*args, gcfg, "workers_ai", "m")
    assert cache_context(*args, {**gcfg, "extra_body": None}, "workers_ai", "m") == plain
    assert cache_context(*args, {**gcfg, "extra_body": {"reasoning_effort": "low"}}, "workers_ai", "m") != plain
