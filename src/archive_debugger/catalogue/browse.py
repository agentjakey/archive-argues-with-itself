"""Catalogue browsing, compiled (docs/formats/catalogue_browse.md): the registry exported as static
files for the site's /catalogue/ page, so every document is findable by year, place, issuer and
sub-collection with its coverage state, and nothing needs an engine.

  summary.json             counts by decade and place, by coverage state, the sub-collections and
                           issuers with the most documents, and how the files were made
  decades/<key>.json       one file per decade ("1970s") plus "undated": every document in it

A document row: id (the archive.org identifier), t (title), y (catalogue year or null), d (a derived
year and how it was found, or null: never presented as the catalogue's), p (place), i (issuer), c
(sub-collections), s (coverage states: known, text_fetched, indexed:<scope>)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SOURCE_COLLECTION = "governmentpublications"


def decade_key(year) -> str:
    return "undated" if year is None else f"{int(year) // 10 * 10}s"


def rows(conn: sqlite3.Connection) -> list:
    states: dict = {}
    for doc_id, state, scope in conn.execute("SELECT doc_id, state, scope FROM coverage"):
        states.setdefault(doc_id, []).append(f"{state}:{scope}" if scope else state)
    colls: dict = {}
    for doc_id, cid in conn.execute("SELECT doc_id, collection_id FROM document_collections"):
        name = cid.split(":", 1)[1]
        if name != SOURCE_COLLECTION:
            colls.setdefault(doc_id, []).append(name)
    cat, der = {}, {}
    for doc_id, kind, year, method in conn.execute("SELECT doc_id, kind, year, method FROM dates WHERE kind IN ('catalogue', 'derived')"):
        if kind == "catalogue":
            cat[doc_id] = year
        elif year is not None:
            der[doc_id] = {"year": year, "method": method}
    out = []
    # Internet Archive items only: a second source's records (docs/INTEROP.md) are never published
    # as part of the catalogue, and their links would not be archive.org item pages.
    for doc_id, ident, title, place, issuer in conn.execute(
            "SELECT doc_id, identifier, title, jurisdiction, issuer FROM documents WHERE doc_id LIKE 'ia:%' "
            "ORDER BY identifier"):
        out.append({"id": ident, "t": (title or "")[:240], "y": cat.get(doc_id), "d": der.get(doc_id),
                    "p": place or "unknown", "i": None if issuer in (None, "unknown") else issuer,
                    "c": sorted(colls.get(doc_id, []))[:8], "s": sorted(states.get(doc_id, ["known"]))})
    return out


def export(conn: sqlite3.Connection, out: Path, *, source_note: dict) -> dict:
    docs = rows(conn)
    out.mkdir(parents=True, exist_ok=True)
    (out / "decades").mkdir(exist_ok=True)
    by_decade: dict = {}
    for r in docs:
        by_decade.setdefault(decade_key(r["y"]), []).append(r)
    files = {}
    for key, items in sorted(by_decade.items()):
        body = json.dumps(items, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        (out / "decades" / f"{key}.json").write_bytes(body)
        files[key] = {"documents": len(items), "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    grid = Counter((decade_key(r["y"]), r["p"]) for r in docs)
    state_counts = Counter(s.split(":")[0] for r in docs for s in set(x.split(":")[0] for x in r["s"]))
    summary = {
        "format": 1,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "documents": len(docs),
        "decades": files,
        "grid": [{"decade": d, "place": p, "documents": n} for (d, p), n in sorted(grid.items())],
        "coverage": dict(state_counts),
        "places": dict(Counter(r["p"] for r in docs).most_common()),
        "collections": dict(Counter(c for r in docs for c in r["c"]).most_common(150)),
        "issuers": dict(Counter(r["i"] for r in docs if r["i"]).most_common(300)),
        "source": source_note,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=True, indent=1), encoding="utf-8")
    return {"documents": len(docs), "files": len(files) + 1,
            "largest_bytes": max(f["bytes"] for f in files.values())}
