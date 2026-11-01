"""Collection configs (docs/formats/audit.md): what the audit needs to know about one
sub-collection, read from config/collections/<name>.toml."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO / "config" / "collections"
LABEL_CLASSES = ("pass", "partial", "fail")


class CollectionError(Exception):
    pass


@dataclass(frozen=True)
class V1Sources:
    worksheet: Path
    answers_index: Optional[Path]
    labels: Optional[Path]
    labels_kind: str                      # "by_question" or "worksheet_field"
    writer_model: str                     # the model that wrote these answers: never on their panel
    label_map: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Collection:
    name: str
    scope: str
    label: str
    languages: tuple
    period: tuple
    jurisdictions: tuple
    v1: Optional[V1Sources]
    path: Path


def _repo_path(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    p = Path(value)
    return p if p.is_absolute() else REPO / p


def load(name_or_path: str, config_dir: Path = CONFIG_DIR) -> Collection:
    """A collection by name (config/collections/<name>.toml) or by the path of its file."""
    path = Path(name_or_path)
    if not path.suffix:
        path = Path(config_dir) / f"{name_or_path}.toml"
    if not path.exists():
        raise CollectionError(f"no collection config at {path}")
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    c = raw.get("collection") or {}
    for key in ("name", "scope", "period", "jurisdictions"):
        if key not in c:
            raise CollectionError(f"{path}: [collection] needs {key}")
    period = tuple(int(y) for y in c["period"])
    if len(period) != 2 or period[0] > period[1]:
        raise CollectionError(f"{path}: period must be [first_year, last_year]")
    v1 = None
    if "v1" in raw:
        v = raw["v1"]
        label_map = dict(v.get("label_map") or {})
        bad = sorted(set(label_map.values()) - set(LABEL_CLASSES))
        if bad:
            raise CollectionError(f"{path}: label_map values must be {LABEL_CLASSES}, got {bad}")
        if not v.get("writer_model"):
            raise CollectionError(f"{path}: [v1] needs writer_model, the model that wrote the answers")
        if v.get("labels_kind", "by_question") not in ("by_question", "worksheet_field"):
            raise CollectionError(f"{path}: labels_kind must be by_question or worksheet_field")
        v1 = V1Sources(worksheet=_repo_path(v["worksheet"]), answers_index=_repo_path(v.get("answers_index")),
                       labels=_repo_path(v.get("labels")), labels_kind=v.get("labels_kind", "by_question"),
                       writer_model=v["writer_model"], label_map=label_map)
    return Collection(name=c["name"], scope=c["scope"], label=c.get("label", c["name"]),
                      languages=tuple(c.get("languages") or ()), period=period,
                      jurisdictions=tuple(c["jurisdictions"]), v1=v1, path=path)


def all_names(config_dir: Path = CONFIG_DIR) -> list[str]:
    return sorted(p.stem for p in Path(config_dir).glob("*.toml"))
