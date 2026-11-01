"""Gap Hunt: where the record goes quiet, by province or territory and decade, and why.

Each cell keeps the coverage states apart:
  known to the catalogue  items in the Internet Archive collection whose publisher or creator names
                          the place, from count-only searches of its public API (a lexical proxy:
                          it misses issuers that do not name the place and counts some that name it
                          in passing; the counts are dated);
  indexed                 items in this project's indexed collections with that jurisdiction and a
                          catalogue year in the decade.
A cell with indexed items is "recorded"; one whose catalogue count is above zero and has nothing
indexed is "not_indexed" (the archive holds items we have not indexed); one where both are zero is
"quiet_examined" (absent from the examined holdings, which is not the same as nothing published).
The explanations are templates over those numbers: no model writes them."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from archive_debugger.exhibit import net

API = "https://archive.org/advancedsearch.php"
BASE = "mediatype:texts AND collection:governmentpublications"
DECADES = (1960, 1970, 1980, 1990, 2000, 2010)
QC = "Qu" + chr(233) + "bec"      # the accented spelling, kept ASCII in this file

# Jurisdiction key (the collections' jurisdiction_norm) -> the catalogue proxy clause.
PLACES = {
    "british_columbia": 'publisher:("British Columbia") OR creator:("British Columbia")',
    "alberta": 'publisher:("Alberta") OR creator:("Alberta")',
    "saskatchewan": 'publisher:("Saskatchewan") OR creator:("Saskatchewan")',
    "manitoba": 'publisher:("Manitoba") OR creator:("Manitoba")',
    "ontario": 'publisher:("Ontario") OR creator:("Ontario")',
    "quebec": f'publisher:("Quebec" OR "{QC}") OR creator:("Quebec" OR "{QC}")',
    "new_brunswick": 'publisher:("New Brunswick") OR creator:("New Brunswick")',
    "nova_scotia": 'publisher:("Nova Scotia") OR creator:("Nova Scotia")',
    "prince_edward_island": 'publisher:("Prince Edward Island") OR creator:("Prince Edward Island")',
    "newfoundland": 'publisher:("Newfoundland" OR "Labrador") OR creator:("Newfoundland" OR "Labrador")',
    "yukon": 'publisher:("Yukon") OR creator:("Yukon")',
    "northwest_territories": 'publisher:("Northwest Territories") OR creator:("Northwest Territories")',
    "nunavut": 'publisher:("Nunavut") OR creator:("Nunavut")',
    "federal": 'publisher:("Canada") OR creator:("Canada")',
}
ISO = {"british_columbia": "CA-BC", "alberta": "CA-AB", "saskatchewan": "CA-SK", "manitoba": "CA-MB",
       "ontario": "CA-ON", "quebec": "CA-QC", "new_brunswick": "CA-NB", "nova_scotia": "CA-NS",
       "prince_edward_island": "CA-PE", "newfoundland": "CA-NL", "yukon": "CA-YT",
       "northwest_territories": "CA-NT", "nunavut": "CA-NU", "federal": None}


def numfound(query: str, get: Callable = None) -> int:
    get = get or net.get_json
    body = get(API, {"q": query, "rows": 0, "output": "json"})
    return int(body["response"]["numFound"])


def fetch_catalogue_counts(get: Callable = None, log: Callable[[str], None] = print) -> dict:
    """Count-only searches: the collection total and every place by decade (85 requests)."""
    out = {"api": API, "base": BASE, "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "method": "advancedsearch numFound, rows=0; place = publisher or creator names it (lexical proxy)",
           "total": numfound(BASE, get), "cells": {}}
    for place, clause in PLACES.items():
        for decade in DECADES:
            q = f"{BASE} AND ({clause}) AND year:[{decade} TO {decade + 9}]"
            out["cells"][f"{place}:{decade}"] = numfound(q, get)
        log(f"  {place}: " + ", ".join(str(out["cells"][f"{place}:{d}"]) for d in DECADES))
    return out


def indexed_counts(corpora, names: tuple) -> dict:
    """{(jurisdiction, decade): set of item ids} over every indexed collection (an item held in two
    collections counts once), plus each collection's period."""
    cells: dict = {}
    periods = {}
    for name in names:
        conn = corpora(name)
        periods[name] = list(corpora.configs[name].period)
        for r in conn.execute("SELECT item_id, jurisdiction_norm, year FROM items WHERE dated = 1 AND year BETWEEN ? AND ?",
                              (DECADES[0], DECADES[-1] + 9)):
            key = (r["jurisdiction_norm"] or "unknown", int(r["year"]) // 10 * 10)
            cells.setdefault(key, set()).add(r["item_id"])
    return {"cells": cells, "periods": periods}


def cell_state(catalogue: Optional[int], indexed: int) -> str:
    if indexed > 0:
        return "recorded"
    if catalogue is None:
        return "unknown"
    return "not_indexed" if catalogue > 0 else "quiet_examined"


def build_grid(corpora, s, catalogue: Optional[dict]) -> dict:
    idx = indexed_counts(corpora, s.collections)
    cells = []
    for place in PLACES:
        for decade in DECADES:
            n_idx = len(idx["cells"].get((place, decade), ()))
            n_cat = None
            if catalogue:
                value = catalogue["cells"].get(f"{place}:{decade}")
                n_cat = None if value is None or value < 0 else int(value)
            cells.append({"place": place, "iso": ISO[place], "decade": decade, "catalogue_items": n_cat,
                          "indexed_items": n_idx, "state": cell_state(n_cat, n_idx)})
    return {
        "decades": list(DECADES),
        "jurisdictions": list(PLACES),
        "cells": cells,
        "indexed_collections": idx["periods"],
        "catalogue": None if not catalogue else {k: catalogue[k] for k in ("api", "base", "fetched_at", "method", "total")},
        "unknown_place_indexed": sum(len(v) for (j, _), v in idx["cells"].items() if j in ("unknown", "international")),
    }
