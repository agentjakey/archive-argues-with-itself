"""LLM boundary. The configured provider is the ONLY network call generation may
make (N1); IA re-fetch stays in harvest. Tests/CI use StubLLM; the anthropic SDK is
imported lazily so importing this package never touches it."""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class CitedSentence(BaseModel):
    text: str
    cited_ids: list[str]


class Draft(BaseModel):
    sentences: list[CitedSentence]


TEMPERATURE = 0.0   # deterministic-as-possible drafting; reported in Answer.generation


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
    def __init__(self, model: str, max_tokens: int):
        import anthropic  # noqa: lazy on purpose (CI hermetic)
        self._client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env; never in repo
        self.model = model
        self.max_tokens = max_tokens

    def draft(self, system: str, user: str) -> Draft:
        resp = self._client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=TEMPERATURE,
            output_format=Draft,
        )
        return resp.parsed_output


def make_llm(kind: str, model: str, max_tokens: int, stub_draft: Draft | None = None) -> LLM:
    if kind == "stub":
        return StubLLM(stub_draft or Draft(sentences=[]))
    if kind == "anthropic":
        return AnthropicLLM(model, max_tokens)
    raise ValueError(f"unknown generate provider: {kind}")
