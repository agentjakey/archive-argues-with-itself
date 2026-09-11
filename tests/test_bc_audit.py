"""BC scope audit over a fake transport: counts flow into the table, the window clause
is used, the OCR share scales the estimate, the report is written. No network."""
from __future__ import annotations

import json
import random
import urllib.parse

from archive_debugger.harvest import bc_audit
from archive_debugger.harvest.explore import HttpResponse


def _fake_transport(url, headers, timeout):
    assert "contact:" in headers["User-Agent"]
    if url.startswith("https://archive.org/metadata/"):
        ident = url.rsplit("/", 1)[1]
        files = [{"format": "DjVuTXT"}] if ident != "bc2" else [{"format": "JPEG"}]   # one of the 3 sampled lacks OCR
        meta = {"metadata": {"collection": ["bcgovpubs", "texts"], "scanningcenter": "vancouver", "year": "1975"}, "files": files}
        return HttpResponse(200, {}, json.dumps(meta))
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
    rows = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["rows"][0]
    if "zzqxnonexistentterm42" in q:
        n = 0
    elif q == "collection:governmentpublications":
        n = 104219
    elif "year:[1960 TO 2009]" in q:
        n = 1200
    elif "year:[1990 TO 2009]" in q:
        n = 700
    elif "year:[2010" in q:
        n = 9
    elif "year:[1000" in q:
        n = 60
    elif "British Columbia" in q or "bcgovpubs" in q:
        n = 1900
    else:
        n = 3413
    docs = [{"identifier": f"bc{i}", "year": "1975"} for i in range(int(rows))] if rows != "0" else []
    return HttpResponse(200, {}, json.dumps({"response": {"numFound": n, "docs": docs}}))


def test_bc_audit_sizes_and_recommends(tmp_path):
    result = bc_audit.run_bc_audit("config/audit_candidates.toml", tmp_path / "out", tmp_path / "cache",
                                   contact="me@example.com", sample_size=3, ocr_sample_size=3,
                                   transport=_fake_transport, sleeper=lambda _s: None, rng=random.Random(0))
    names = [s["name"] for s in result["sizes"]]
    assert names[0] == "bc_issuer" and "bcgovpubs" in names and "bc_union" in names and names[-1] == "pilot_gov"
    bc = result["sizes"][0]
    assert bc["topic_1960_2009"] == 1200 and bc["topic_2010_plus"] == 9 and bc["topic_pre_1960"] == 60
    assert result["discovery"]["collections_kept"] == ["bcgovpubs"]                 # "texts" excluded
    rec = result["recommendation"]
    assert rec["ocr_usable_share"] == round(2 / 3, 3) and rec["estimated_usable_in_window"] == 800
    assert rec["clears_floor"] is False
    md = (tmp_path / "out" / "bc_sizing.md").read_text(encoding="utf-8")
    assert "## Sizing: BC-scoped clauses" in md and "does not clear" in md and "year:[1960 TO 2009]" in md
    assert rec["best_scope"] == "bc_issuer"                                        # never a whole library collection
