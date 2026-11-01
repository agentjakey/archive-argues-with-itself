"""The shard planner: cut the whole collection into engines of about a million passages, each holding
one jurisdiction and a run of years, so a question about a place and a period wakes few engines.

Passages per document are estimated from the catalogue's scanned-page count and the built corpora's
measured passages per page (docs/v2/SCALING.md: 1.47 to 1.59; the planner uses the upper value, so
shards err small). Documents of one jurisdiction are sorted by year and cut into consecutive year
ranges that fit the target; a single year bigger than the target is split by identifier order and
says so. Undated documents of a jurisdiction form their own shards: an undated record is never put
in a dated range. Every document lands in exactly one shard."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field

PASSAGES_PER_PAGE = 1.59
DEFAULT_TARGET = 1_000_000
POOL_BELOW = 200_000                # a jurisdiction smaller than this shares "other" shards
WAKE_KB_PER_PASSAGE = 4.14          # docs/v2/SCALING.md: databases plus dense artifacts, upper fit
MISSING_PAGES = 72                  # the sample's median scanned pages, for a record with no count


@dataclass
class Shard:
    shard_id: str
    jurisdiction: str
    first_year: int | None
    last_year: int | None
    undated: bool
    documents: list = field(default_factory=list)
    est_passages: float = 0.0
    split_year: bool = False
    jurisdictions: list = field(default_factory=list)   # every jurisdiction its documents carry

    def summary(self) -> dict:
        d = asdict(self)
        d["documents"] = len(self.documents)
        d["est_passages"] = int(round(self.est_passages))
        d["est_wake_gb"] = round(self.est_passages * WAKE_KB_PER_PASSAGE / 1024 / 1024, 2)
        d["documents_sha256"] = hashlib.sha256("\n".join(sorted(self.documents)).encode()).hexdigest()[:16]
        return d


def documents(registry: sqlite3.Connection) -> list:
    """(doc_id, jurisdiction, year or None, scanned pages) for every text document. The year is the
    catalogue year, or a derived year when the catalogue has none (marked, never overwriting)."""
    rows = registry.execute(
        "SELECT d.doc_id, COALESCE(d.jurisdiction, 'unknown'), d.imagecount, "
        "(SELECT year FROM dates WHERE doc_id = d.doc_id AND kind = 'catalogue'), "
        "(SELECT year FROM dates WHERE doc_id = d.doc_id AND kind = 'derived') "
        "FROM documents d WHERE COALESCE(d.mediatype, 'texts') = 'texts'").fetchall()
    return [(r[0], r[1], r[3] if r[3] is not None else r[4], r[2] if r[2] else MISSING_PAGES) for r in rows]


def plan(docs: list, target: int = DEFAULT_TARGET, pool_below: int = POOL_BELOW) -> list:
    totals: dict = {}
    for _, place, _, pages in docs:
        totals[place] = totals.get(place, 0.0) + pages * PASSAGES_PER_PAGE
    pooled = {p for p, n in totals.items() if n < pool_below}
    place_of = {}
    by_place: dict = {}
    for doc_id, place, year, pages in docs:
        key = "other" if place in pooled else place
        place_of[doc_id] = place
        by_place.setdefault(key, []).append((year, doc_id, pages * PASSAGES_PER_PAGE))
    shards = []
    for place in sorted(by_place):
        rows = by_place[place]
        dated = sorted((r for r in rows if r[0] is not None), key=lambda r: (r[0], r[1]))
        undated = sorted((r for r in rows if r[0] is None), key=lambda r: r[1])
        current = None
        for year, doc_id, est in dated:
            if current is None or (current.documents and current.est_passages + est > target):
                fresh = Shard("", place, year, year, False)
                if current is not None and current.last_year == year:
                    current.split_year = fresh.split_year = True     # one year bigger than a shard
                current = fresh
                shards.append(current)
            current.documents.append(doc_id)
            current.est_passages += est
            current.last_year = year
        current = None
        for _, doc_id, est in undated:
            if current is None or (current.documents and current.est_passages + est > target):
                current = Shard("", place, None, None, True)
                shards.append(current)
            current.documents.append(doc_id)
            current.est_passages += est
    seen: dict = {}
    for s in shards:
        s.jurisdictions = sorted({place_of[d] for d in s.documents})
        base = f"{s.jurisdiction}-undated" if s.undated else f"{s.jurisdiction}-{s.first_year}-{s.last_year}"
        seen[base] = seen.get(base, 0) + 1
        s.shard_id = base if seen[base] == 1 else f"{base}-{seen[base]}"
    ids = [s.shard_id for s in shards]
    if len(set(ids)) != len(ids):
        raise ValueError("shard ids are not unique")
    return shards


def plan_document(shards: list, target: int) -> dict:
    total = sum(s.est_passages for s in shards)
    return {"format": 1, "target_passages": target, "passages_per_page": PASSAGES_PER_PAGE,
            "shards": [s.summary() for s in shards],
            "totals": {"shards": len(shards), "documents": sum(len(s.documents) for s in shards),
                       "est_passages": int(round(total)),
                       "est_wake_gb": round(total * WAKE_KB_PER_PASSAGE / 1024 / 1024, 1)}}


def membership(shards: list) -> dict:
    """{doc_id: shard_id}: exactly one shard per document."""
    out = {}
    for s in shards:
        for d in s.documents:
            if d in out:
                raise ValueError(f"{d} is in two shards")
            out[d] = s.shard_id
    return out


def write_plan(shards: list, target: int, path, members_path) -> dict:
    doc = plan_document(shards, target)
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    members_path.write_text("".join(f"{d}\t{s}\n" for d, s in sorted(membership(shards).items())), encoding="utf-8")
    return doc
