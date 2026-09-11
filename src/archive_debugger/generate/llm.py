"""LLM boundary. The configured provider is the ONLY network call generation may
make (N1); IA re-fetch stays in harvest. Tests/CI use StubLLM; the anthropic SDK is
imported lazily so importing this package never touches it."""
from __future__ import annotations

from typing import Optional, Protocol

from pydantic import BaseModel


class CitedSentence(BaseModel):
    text: str
    cited_ids: list[str]


class Draft(BaseModel):
    sentences: list[CitedSentence]


class LLM(Protocol):
    def draft(self, system: str, user: str) -> Draft: ...


class StubLLM:
    """Deterministic canned draft for tests; counts calls so abstention tests can
    assert the model was never invoked."""

    def __init__(self, draft: Draft):
        self._draft = draft
        self.calls = 0

    def draft(self, system: str, user: str) -> Draft:
        self.calls += 1
        return self._draft


class AnthropicLLM:
    """Real provider. In anthropic==1.5.0 neither Messages.parse nor Messages.create
    accepts a `temperature` kwarg (sampling params are gone from the SDK surface), so
    the temperature, when configured, is sent in the request body via extra_body.
    parse() is kept because it applies the SDK's own schema transform for
    output_format and returns typed parsed_output on each text block. The client is
    injectable so tests never construct a real one."""

    def __init__(self, model: str, max_tokens: int, client=None, temperature: Optional[float] = None):
        if client is None:
            import anthropic  # noqa: lazy on purpose (CI hermetic)
            client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env; never in repo
        self._client = client
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def draft(self, system: str, user: str) -> Draft:
        kwargs = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=Draft,
        )
        if self.temperature is not None:
            kwargs["extra_body"] = {"temperature": self.temperature}
        resp = self._client.messages.parse(**kwargs)
        # parsed_output lives on each ParsedTextBlock in resp.content, not on the message.
        for block in resp.content:
            parsed = getattr(block, "parsed_output", None)
            if getattr(block, "type", None) == "text" and parsed is not None:
                return parsed
        raise ValueError(f"no parsed text block in response (stop_reason={getattr(resp, 'stop_reason', None)!r})")


def make_llm(kind: str, model: str, max_tokens: int, stub_draft: Draft | None = None,
             temperature: Optional[float] = None) -> LLM:
    if kind == "stub":
        return StubLLM(stub_draft or Draft(sentences=[]))
    if kind == "anthropic":
        return AnthropicLLM(model, max_tokens, temperature=temperature)
    raise ValueError(f"unknown generate provider: {kind}")
