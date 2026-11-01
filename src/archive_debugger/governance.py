"""The governance register and the checks that enforce it (docs/formats/governance.md).

A policy record restricts how a legitimate authority's records may be used: `retrieve` (never returned
as evidence), `generate` (never given to a model or quoted in an answer), `export` (never in a stored
answer, an export or a static file). The engine checks the register at three points: before retrieval
(the restricted documents are excluded from the search itself), before generation (no restricted
passage reaches the model) and before export (no restricted passage is stored or shown).

The register is empty by default. Nothing here infers a restriction or a label from a record's text or
metadata, and a Local Contexts label is shown only when a policy record carries it. The production
loader refuses a register that holds a synthetic fixture; the fixture loader refuses a register that
holds anything else, so test restrictions can never reach readers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

USES = ("retrieve", "generate", "export")
FIXTURE_AUTHORITY = "Synthetic test authority (fixture, not a real restriction)"
DEFAULT_REGISTER = Path(__file__).resolve().parents[2] / "config" / "governance" / "policies.jsonl"
REQUIRED = ("format", "policy_id", "targets", "restrict", "authority", "basis", "display", "entered_by",
            "entered_at", "fixture")


class RegisterError(ValueError):
    pass


@dataclass(frozen=True)
class Policy:
    policy_id: str
    items: frozenset
    collections: frozenset
    restrict: frozenset
    authority: str
    basis: str
    contact: str
    label: str
    local_contexts: Optional[dict]
    fixture: bool

    def covers(self, item_id: str, collection: Optional[str]) -> bool:
        return item_id in self.items or (collection is not None and collection in self.collections)

    def notice(self) -> dict:
        """What a reader may see about the policy: never anything from the restricted records."""
        return {"policy_id": self.policy_id, "authority": self.authority, "basis": self.basis,
                "contact": self.contact, "label": self.label, "local_contexts": self.local_contexts,
                "fixture": self.fixture}


def _policy(row: dict, line: int) -> Policy:
    missing = [k for k in REQUIRED if k not in row]
    if missing:
        raise RegisterError(f"line {line}: missing {missing}")
    if row["format"] != 1:
        raise RegisterError(f"line {line}: unknown format {row['format']}")
    restrict = set(row["restrict"] or [])
    if not restrict or restrict - set(USES):
        raise RegisterError(f"line {line}: restrict must be a non-empty subset of {USES}")
    targets = row["targets"] or {}
    items, collections = targets.get("items") or [], targets.get("collections") or []
    if not items and not collections:
        raise RegisterError(f"line {line}: a policy must target items or collections")
    display = row["display"] or {}
    lc = display.get("local_contexts")
    if lc is not None and not (isinstance(lc, dict) and lc.get("project_id") and lc.get("label_ids")):
        raise RegisterError(f"line {line}: local_contexts must name the authority's project and labels, or be null")
    return Policy(policy_id=str(row["policy_id"]), items=frozenset(map(str, items)),
                  collections=frozenset(map(str, collections)), restrict=frozenset(restrict),
                  authority=str(row["authority"]), basis=str(row["basis"]), contact=str(row.get("contact") or ""),
                  label=str(display.get("label") or "Restricted"), local_contexts=lc, fixture=bool(row["fixture"]))


@dataclass
class Register:
    policies: list = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.policies

    @property
    def digest(self) -> str:
        """A hash of every policy, "" for an empty register: it joins the answer cache context, so a
        changed register never serves an answer stored under the old one."""
        if not self.policies:
            return ""
        import hashlib
        rows = sorted(json.dumps({"id": p.policy_id, "items": sorted(p.items), "collections": sorted(p.collections),
                                  "restrict": sorted(p.restrict), "authority": p.authority, "label": p.label,
                                  "lc": p.local_contexts}, sort_keys=True) for p in self.policies)
        return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()[:16]

    def restricted_items(self, use: str, collection: Optional[str] = None, candidates: Optional[Iterable] = None) -> set:
        """Item ids restricted for `use`. Collection-wide policies need the candidates to name items."""
        out = set()
        for p in self.policies:
            if use not in p.restrict:
                continue
            out |= set(p.items)
            if collection is not None and collection in p.collections and candidates is not None:
                out |= set(candidates)
        return out

    def collection_restricted(self, use: str, collection: str) -> list:
        return [p for p in self.policies if use in p.restrict and collection in p.collections]

    def policies_for(self, item_ids: Iterable, collection: Optional[str] = None) -> list:
        ids = set(item_ids)
        return [p for p in self.policies if any(p.covers(i, collection) for i in ids)]

    def split(self, rows: list, use: str, collection: Optional[str] = None, key: str = "item_id") -> tuple:
        """(allowed rows, restricted policies that removed any) for evidence or hit rows."""
        kept, hit = [], {}
        for row in rows:
            blocking = [p for p in self.policies if use in p.restrict and p.covers(str(row.get(key)), collection)]
            if blocking:
                for p in blocking:
                    hit[p.policy_id] = p
            else:
                kept.append(row)
        return kept, list(hit.values())


def load(path: Optional[Path] = None, *, fixtures: bool = False) -> Register:
    """Read a register. Production (fixtures False) refuses any fixture record; the fixture loader
    refuses any record that is not a fixture. A missing or empty file is an empty register."""
    path = Path(path) if path is not None else DEFAULT_REGISTER
    if not path.exists():
        return Register()
    policies, seen = [], set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise RegisterError(f"line {n}: not JSON ({exc})") from None
        p = _policy(row, n)
        if p.policy_id in seen:
            raise RegisterError(f"line {n}: duplicate policy_id {p.policy_id}")
        seen.add(p.policy_id)
        if p.fixture and not fixtures:
            raise RegisterError(f"line {n}: {p.policy_id} is a test fixture; the production register refuses it")
        if fixtures and not p.fixture:
            raise RegisterError(f"line {n}: {p.policy_id} is not a fixture; the fixture loader refuses it")
        policies.append(p)
    return Register(policies)


def from_records(records: list, *, fixtures: bool) -> Register:
    """A register from policy records held in memory (benchmark items carry their fixtures)."""
    policies = []
    for n, row in enumerate(records, 1):
        p = _policy(row, n)
        if p.fixture != fixtures:
            raise RegisterError(f"record {n}: fixture is {p.fixture}, expected {fixtures}")
        policies.append(p)
    return Register(policies)
