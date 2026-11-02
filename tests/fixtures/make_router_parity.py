"""Writes tests/fixtures/router_parity.json: the Python router's results on fixed inputs, which the
engine Worker's port (worker/engine/test/router.test.ts) must reproduce, and tests/test_router_index.py
checks are still current.

    python tests/fixtures/make_router_parity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.shards import router  # noqa: E402
from archive_debugger.shards.coverage import terms  # noqa: E402

OUT = REPO / "tests" / "fixtures" / "router_parity.json"
TEXTS = [
    "Sant\u00e9 publique: H\u00f4pital-Dieu, 1975 report_x the vaccination 12abc O\u2019Brien",
    "The HOSPITAL beds of the Province of Alberta, 1980-81; patients admitted: 4,512",
    "\u00c9COLES et h\u00f4pitaux du Qu\u00e9bec \u2014 rapport annuel \u00bd \u00b2 \u0130stanbul",
    "under_score snake_case and   tabs\tand\nnewlines",
]
COVERAGES = [
    {"shard_id": "s-alberta", "jurisdictions": ["alberta"], "years": {"alberta|1980": 4, "alberta|undated": 1},
     "passages": 400, "tokens": 40000, "df": {"hospital": 30, "beds": 12, "vaccination": 2}},
    {"shard_id": "s-ontario", "jurisdictions": ["ontario"], "years": {"ontario|1975": 7},
     "passages": 900, "tokens": 81000, "df": {"hospital": 50, "vaccination": 40}},
    {"shard_id": "s-federal", "jurisdictions": ["federal"], "years": {"federal|1990": 3},
     "passages": 100, "tokens": 9000, "df": {"tariff": 9}},
]
CHOICES = [
    {"question": "hospital beds vaccination", "filters": {}, "max_engines": 2},
    {"question": "hospital beds", "filters": {"jurisdiction": "alberta"}, "max_engines": 3},
    {"question": "vaccination", "filters": {"first_year": 1970, "last_year": 1979}, "max_engines": 3},
]
HITS = {
    "s-alberta": [{"passage_id": "a#1:0", "tf": {"hospital": 2, "beds": 1}, "dl": 80},
                  {"passage_id": "a#2:0", "tf": {"beds": 1}, "dl": 120}],
    "s-ontario": [{"passage_id": "o#5:0", "tf": {"hospital": 1, "vaccination": 3}, "dl": 95},
                  {"passage_id": "o#6:1", "tf": {}, "dl": 50}],
}


def main() -> int:
    out = {"terms": [{"text": t, "terms": terms(t)} for t in TEXTS], "coverages": COVERAGES, "choices": [], "merge": None}
    for c in CHOICES:
        f = c["filters"]
        chosen, left = router.choose(c["question"], COVERAGES, jurisdiction=f.get("jurisdiction"),
                                     first_year=f.get("first_year"), last_year=f.get("last_year"),
                                     max_engines=c["max_engines"])
        out["choices"].append({**c, "chosen": [[x.shard_id, round(x.score, 9), x.reason] for x in chosen],
                               "left": sorted([[x.shard_id, x.reason] for x in left])})
    merged = router.merge("hospital beds vaccination", HITS, COVERAGES, top_k=10)
    out["merge"] = {"question": "hospital beds vaccination", "hits": HITS,
                    "result": [[m["passage_id"], m["shard_id"], round(m["bm25"], 9), m["rrf"], m["bm25_rank"]] for m in merged]}
    text = json.dumps(out, indent=1, ensure_ascii=True, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        return 0 if OUT.read_text(encoding="ascii") == text else 1
    OUT.write_text(text, encoding="ascii", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
