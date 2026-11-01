"""config/exhibit.toml, read once into plain values."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EXHIBIT_CONFIG = REPO / "config" / "exhibit.toml"


@dataclass(frozen=True)
class CareRules:
    excluded_tiers: tuple
    exclude_indigenous_context: bool
    excluded_terms: tuple
    period_terms: tuple


@dataclass(frozen=True)
class Settings:
    collections: tuple
    dial_first_year: int
    dial_last_year: int
    same_or_not_rounds: int
    when_was_this_cards: int
    time_dial_questions: tuple
    max_page_chars: int
    offline_image_cache: bool
    care: CareRules
    writer: str
    reviewers: tuple
    writer_effort: str
    reviewer_effort: str
    phase_cap_usd: float
    ledger: Path
    idle_reset_seconds: int
    counts_dir: str


def load(path: Path = EXHIBIT_CONFIG) -> Settings:
    with Path(path).open("rb") as fh:
        raw = tomllib.load(fh)
    deck, care, models, budget = raw["deck"], raw["care"], raw["models"], raw["budget"]
    if deck["dial_first_year"] > deck["dial_last_year"]:
        raise ValueError(f"{path}: dial_first_year is after dial_last_year")
    ledger = Path(budget["ledger"])
    return Settings(
        collections=tuple(deck["collections"]),
        dial_first_year=int(deck["dial_first_year"]),
        dial_last_year=int(deck["dial_last_year"]),
        same_or_not_rounds=int(deck["same_or_not_rounds"]),
        when_was_this_cards=int(deck["when_was_this_cards"]),
        time_dial_questions=tuple(int(n) for n in deck["time_dial_questions"]),
        max_page_chars=int(deck["max_page_chars"]),
        offline_image_cache=bool(raw.get("images", {}).get("offline_cache", False)),
        care=CareRules(excluded_tiers=tuple(care.get("excluded_tiers") or ()),
                       exclude_indigenous_context=bool(care.get("exclude_indigenous_context", True)),
                       excluded_terms=tuple(care.get("excluded_terms") or ()),
                       period_terms=tuple(care.get("period_terms") or ())),
        writer=models["writer"],
        reviewers=tuple(models["reviewer"]),
        writer_effort=models.get("writer_effort", "medium"),
        reviewer_effort=models.get("reviewer_effort", "medium"),
        phase_cap_usd=float(budget["phase_cap_usd"]),
        ledger=ledger if ledger.is_absolute() else REPO / ledger,
        idle_reset_seconds=int(raw.get("kiosk", {}).get("idle_reset_seconds", 60)),
        counts_dir=raw.get("kiosk", {}).get("counts_dir", "kiosk-counts"),
    )
