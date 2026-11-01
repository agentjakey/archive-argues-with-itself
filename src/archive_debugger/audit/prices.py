"""Prices per million tokens, in US dollars, with where each came from. A run's spend is computed
from these and the token counts each provider reports, and the price version is stamped on every
ledger entry. Update a price only from the provider's own page, with the date checked."""
from __future__ import annotations

from dataclasses import dataclass

PRICE_VERSION = "2026-10-31"


@dataclass(frozen=True)
class Price:
    provider: str
    model: str
    input_per_m: float
    output_per_m: float
    batch_discount: float     # fraction of the list price paid in a batch (1.0 when there is no batch)
    source: str


PRICES = {
    # Anthropic list prices (Claude API skill model table, cached 2026-10-06); batches are half price.
    "claude-haiku-4-5": Price("anthropic", "claude-haiku-4-5", 1.00, 5.00, 0.5, "anthropic models table 2026-10-06"),
    # Haiku 5.5: the rate for prompts of 100K tokens or fewer (judge prompts are far under that).
    "claude-haiku-5-5": Price("anthropic", "claude-haiku-5-5", 0.10, 0.50, 0.5, "anthropic pricing page 2026-10-31"),
    "claude-sonnet-5-5": Price("anthropic", "claude-sonnet-5-5", 2.00, 10.00, 0.5, "anthropic models table 2026-10-06"),
    # Workers AI catalogue prices, read from the account's model search on 2026-10-31.
    "@cf/openai/gpt-oss-120b": Price("workers-ai", "@cf/openai/gpt-oss-120b", 0.35, 0.75, 1.0, "workers ai catalogue 2026-10-31"),
    "@cf/deepseek-ai/deepseek-v4-flash-0731": Price("workers-ai", "@cf/deepseek-ai/deepseek-v4-flash-0731", 0.44, 1.32, 1.0,
                                                    "workers ai catalogue 2026-10-31"),
    "@cf/moonshotai/kimi-k2.6": Price("workers-ai", "@cf/moonshotai/kimi-k2.6", 0.95, 4.00, 1.0, "workers ai catalogue 2026-10-31"),
}


def price(model: str) -> Price:
    if model not in PRICES:
        raise KeyError(f"no price for {model}: add it to audit/prices.py from the provider's page before using it")
    return PRICES[model]


def cost(model: str, input_tokens: int, output_tokens: int, *, batch: bool = False) -> float:
    p = price(model)
    factor = p.batch_discount if batch else 1.0
    return (input_tokens * p.input_per_m + output_tokens * p.output_per_m) / 1_000_000 * factor


def estimate_input_tokens(text: str) -> int:
    """An upper estimate of a prompt's tokens from its length: 2.5 characters per token, below the
    3.5 to 4 characters an English or French prompt usually takes, so budgets err high."""
    return int(len(text) / 2.5) + 50
