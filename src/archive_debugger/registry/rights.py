"""Rights and care blocks per document, and the public-domain shelf manifest (dry run only).

Rights (rule RULE_VERSION). Canadian Crown copyright lasts 50 years after the year of first
publication (Copyright Act s. 12), so a work first published in year Y is in the public domain from
1 January of Y + 51. For each document:

  issuer_type      federal | provincial | territorial | municipal | other | unknown, read from the
                   registry's jurisdiction and, for municipal bodies, the issuer's or publisher's name
  publication_year the catalogue year, only when the catalogue date was read exactly; a derived date
                   (a year read from a title or a page) is never used here
  status           PD_CA_CROWN        issuer federal, provincial or territorial AND publication_year
                                      <= current year - 51
                   CROWN_IN_COPYRIGHT issuer federal, provincial or territorial and a later year
                   UNKNOWN            anything else: municipal, other or unknown issuers, no exact
                                      catalogue year
This is a rule applied to catalogue metadata, not legal advice and not a clearance: the catalogue's
issuer can be wrong, a Crown publication can reproduce third-party material, and nothing is
exported on the strength of it until IAC signs off in writing.

Care. Each document's catalogue title, creator and publisher are read with the site's care rules
(archive_debugger.flags: the care topics and the Indigenous-context terms, as decided at Gate 2).
A document with Indigenous-identifying metadata is excluded from any export until IAC answers the
CARE/OCAP question; one with a care topic is excluded too.

The shelf. pd_shelf_manifest counts what a public-domain text shelf would hold (PD_CA_CROWN, no care
exclusion) by decade, jurisdiction, language and OCR band, with estimated tokens. export_pd_shelf
refuses to run unless the switch in config/pd_shelf.toml is on, and it ships off."""
from __future__ import annotations

import json
import re
import sqlite3
import tomllib
from datetime import date
from pathlib import Path
from typing import Optional

from archive_debugger import flags

RULE_VERSION = "pd-ca-crown-1"
PROVINCES = {"alberta", "british_columbia", "manitoba", "new_brunswick", "newfoundland", "nova_scotia", "ontario",
             "prince_edward_island", "quebec", "saskatchewan"}
TERRITORIES = {"yukon", "northwest_territories", "nunavut"}
CROWN = {"federal", "provincial", "territorial"}
MUNICIPAL = re.compile(r"\b(city|town|village|township|municipalit\w*|county|regional municipality|metropolitan|"
                       r"metro toronto|district health council|ville de|cit[ey] de)\b", re.IGNORECASE)
TOKENS_PER_PAGE = 450              # until measured on fetched text; pd_shelf_manifest says which it used
OCR_BANDS = ((0.9, "high"), (0.75, "medium"), (0.0, "low"))

RIGHTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS rights (
  doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id),
  issuer_type TEXT NOT NULL,              -- federal | provincial | territorial | municipal | other | unknown
  issuer_type_method TEXT NOT NULL,       -- how it was read
  publication_year INTEGER,               -- the exact catalogue year, or NULL
  date_method TEXT NOT NULL,              -- the catalogue date's method (exact | unknown | ...)
  status TEXT NOT NULL,                   -- PD_CA_CROWN | CROWN_IN_COPYRIGHT | UNKNOWN
  rule_version TEXT NOT NULL,
  decided_on TEXT NOT NULL                -- the date the rule was applied (the cutoff moves each year)
);
CREATE TABLE IF NOT EXISTS care (
  doc_id TEXT PRIMARY KEY REFERENCES documents(doc_id),
  topics TEXT NOT NULL,                   -- JSON list of care topics from the metadata
  indigenous INTEGER NOT NULL,            -- 1 when the metadata identifies Indigenous content
  export_excluded INTEGER NOT NULL,       -- 1 while IAC has not answered (Indigenous) or a topic applies
  method TEXT NOT NULL,                   -- "metadata:flags.py"
  rule_version TEXT NOT NULL
);
"""


def issuer_type(jurisdiction: Optional[str], issuer: Optional[str], publisher: Optional[str],
                creator: Optional[str]) -> tuple:
    names = " ".join(x for x in (issuer, publisher, creator) if x and x != "unknown")
    if names and MUNICIPAL.search(names):
        return "municipal", "name:municipal_terms"
    if jurisdiction == "federal":
        return "federal", "jurisdiction"
    if jurisdiction in PROVINCES:
        return "provincial", "jurisdiction"
    if jurisdiction in TERRITORIES:
        return "territorial", "jurisdiction"
    if jurisdiction in (None, "", "unknown"):
        return "unknown", "jurisdiction_unknown"
    return "other", "jurisdiction"


def status(kind: str, year: Optional[int], date_method: str, today: date) -> str:
    if kind not in CROWN or year is None or date_method != "exact":
        return "UNKNOWN"
    return "PD_CA_CROWN" if year <= today.year - 51 else "CROWN_IN_COPYRIGHT"


def care_block(title: str, creator: str, publisher: str) -> tuple:
    text = " ".join(x for x in (title, creator, publisher) if x)
    topics = sorted(set(flags._row_topics({"title": text, "snippet": ""})))
    hay = flags._norm(text)
    indigenous = any(p.search(hay) for p in flags._INDIGENOUS_CONTEXT)
    return topics, indigenous


def apply(conn: sqlite3.Connection, today: Optional[date] = None) -> dict:
    """Write the rights and care blocks for every document (replacing earlier ones)."""
    today = today or date.today()
    conn.executescript(RIGHTS_SCHEMA)
    cat = {d: (y, m) for d, y, m in conn.execute("SELECT doc_id, year, method FROM dates WHERE kind = 'catalogue'")}
    counts: dict = {}
    rows_r, rows_c = [], []
    for doc_id, juris, issuer, publisher, creator, title in conn.execute(
            "SELECT doc_id, jurisdiction, issuer, publisher_raw, creator_raw, title FROM documents"):
        kind, how = issuer_type(juris, issuer, publisher, creator)
        year, method = cat.get(doc_id, (None, "unknown"))
        st = status(kind, year, method, today)
        rows_r.append((doc_id, kind, how, year if method == "exact" else None, method, st, RULE_VERSION, today.isoformat()))
        topics, indigenous = care_block(title or "", creator or "", publisher or "")
        rows_c.append((doc_id, json.dumps(topics), int(indigenous), int(indigenous or bool(topics)),
                       "metadata:flags.py", RULE_VERSION))
        counts[st] = counts.get(st, 0) + 1
        counts["indigenous"] = counts.get("indigenous", 0) + int(indigenous)
        counts["care_topic"] = counts.get("care_topic", 0) + int(bool(topics))
    conn.executemany("INSERT OR REPLACE INTO rights VALUES (?,?,?,?,?,?,?,?)", rows_r)
    conn.executemany("INSERT OR REPLACE INTO care VALUES (?,?,?,?,?,?)", rows_c)
    conn.execute("INSERT INTO audit_trail (at, actor, action, target, detail) VALUES (?,?,?,?,?)",
                 (today.isoformat(), f"registry.rights {RULE_VERSION}", "rights_and_care", "documents", json.dumps(counts)))
    conn.commit()
    return counts


def ocr_band(quality: Optional[float]) -> str:
    if quality is None:
        return "unknown"
    return next(name for floor, name in OCR_BANDS if quality >= floor)


def pd_shelf_manifest(conn: sqlite3.Connection, tokens_per_page: float = TOKENS_PER_PAGE,
                      tokens_source: str = "assumed") -> dict:
    """What a public-domain shelf would hold today. A dry run: it reads the registry and writes nothing."""
    quality = {d: q for d, q in conn.execute("SELECT doc_id, MAX(ocr_quality) FROM versions GROUP BY doc_id")}
    out = {"rule_version": RULE_VERSION, "dry_run": True, "export_enabled": False,
           "tokens_per_page": tokens_per_page, "tokens_per_page_source": tokens_source,
           "documents": 0, "pages": 0, "estimated_tokens": 0,
           "by_decade": {}, "by_jurisdiction": {}, "by_language": {}, "by_ocr_band": {},
           "excluded": {"indigenous_pending_iac": 0, "care_topic": 0}}
    for doc_id, year, juris, lang, pages, indigenous, topics in conn.execute(
            "SELECT r.doc_id, r.publication_year, d.jurisdiction, d.language, d.imagecount, c.indigenous, c.topics "
            "FROM rights r JOIN documents d ON d.doc_id = r.doc_id JOIN care c ON c.doc_id = r.doc_id "
            "WHERE r.status = 'PD_CA_CROWN'"):
        if indigenous:
            out["excluded"]["indigenous_pending_iac"] += 1
            continue
        if json.loads(topics):
            out["excluded"]["care_topic"] += 1
            continue
        n = int(pages or 0)
        out["documents"] += 1
        out["pages"] += n
        for key, value in (("by_decade", f"{year // 10 * 10}s"), ("by_jurisdiction", juris or "unknown"),
                           ("by_language", (lang or "unknown")[:12]), ("by_ocr_band", ocr_band(quality.get(doc_id)))):
            out[key][value] = out[key].get(value, 0) + 1
    out["estimated_tokens"] = int(out["pages"] * tokens_per_page)
    for key in ("by_decade", "by_jurisdiction", "by_language", "by_ocr_band"):
        out[key] = dict(sorted(out[key].items()))
    return out


def export_enabled(config: Path) -> bool:
    if not config.exists():
        return False
    return bool(tomllib.loads(config.read_text(encoding="utf-8")).get("export_enabled", False))


def export_pd_shelf(conn: sqlite3.Connection, config: Path, out: Path) -> int:
    """Write the shelf's document list. Refused while the switch is off (IAC has not signed off)."""
    if not export_enabled(config):
        raise PermissionError(f"the public-domain shelf export is off ({config}): it stays off until IAC signs off in writing")
    rows = conn.execute("SELECT r.doc_id FROM rights r JOIN care c ON c.doc_id = r.doc_id "
                        "WHERE r.status = 'PD_CA_CROWN' AND c.export_excluded = 0 ORDER BY r.doc_id").fetchall()
    out.write_text("".join(r[0] + "\n" for r in rows), encoding="utf-8")
    return len(rows)
