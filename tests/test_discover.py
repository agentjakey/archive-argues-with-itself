"""Tests for the discovery + sizing pass.

The OCR-derivative and collection helpers are tested against a real captured
metadata response in tests/fixtures. The cached-GET path is tested with a fake
transport, so no network is touched and reruns are proven zero-network.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from archive_debugger.harvest import discover

META_FIXTURE = Path(__file__).parent / "fixtures" / "metadata_01ambientairsurvey00onta.json"


@pytest.fixture
def real_meta() -> dict:
    with META_FIXTURE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# Pure helpers over real metadata
# --------------------------------------------------------------------------- #


def test_collections_of_real(real_meta):
    cols = discover.collections_of(real_meta)
    assert "governmentpublications" in cols
    assert "omote" in cols  # Ontario Ministry of the Environment issuer sub-collection


def test_collections_of_handles_string():
    assert discover.collections_of({"metadata": {"collection": "solo"}}) == ["solo"]


def test_collections_of_missing():
    assert discover.collections_of({"metadata": {}}) == []


def test_scanningcenter_of_real(real_meta):
    assert discover.scanningcenter_of(real_meta) == "uoft"


def test_meta_year_real(real_meta):
    assert discover.meta_year(real_meta) == 1980


def test_ocr_flags_real_item_has_usable_text(real_meta):
    flags = discover.ocr_flags(real_meta)
    assert flags["has_usable_text"] is True
    assert flags["DjVuTXT"] is True
    assert flags["hOCR"] is True
    assert flags["has_any_ocr"] is True


def test_ocr_flags_no_ocr():
    meta = {"files": [{"format": "JPEG"}, {"format": "Metadata"}]}
    flags = discover.ocr_flags(meta)
    assert flags["has_usable_text"] is False
    assert flags["has_any_ocr"] is False


# --------------------------------------------------------------------------- #
# URL builders
# --------------------------------------------------------------------------- #


def test_advancedsearch_url_count():
    url = discover.advancedsearch_url("collection:governmentpublications", rows=0)
    assert "advancedsearch.php" in url
    assert "rows=0" in url
    assert "output=json" in url


def test_advancedsearch_url_fields():
    url = discover.advancedsearch_url("q", rows=5, fields=("identifier", "year"))
    assert "fl%5B%5D=identifier" in url
    assert "fl%5B%5D=year" in url


def test_metadata_url():
    assert discover.metadata_url("abc").endswith("/metadata/abc")


# --------------------------------------------------------------------------- #
# Cached GET with a fake transport
# --------------------------------------------------------------------------- #


def make_ctx(tmp_path, responses):
    """responses: dict mapping a URL substring -> json dict to return."""
    calls = {"n": 0}

    def transport(url, headers, timeout):
        calls["n"] += 1
        for needle, payload in responses.items():
            if needle in url:
                return discover.explore.HttpResponse(200, {}, json.dumps(payload))
        raise AssertionError(f"unexpected url: {url}")

    ctx = {
        "cache_dir": tmp_path / "cache",
        "transport": transport,
        "sleeper": lambda s: None,
        "rng": random.Random(0),
        "headers": {},
        "page_delay": 0.0,
        "offline": False,
    }
    return ctx, calls


def test_cached_get_is_zero_network_on_rerun(tmp_path):
    ctx, calls = make_ctx(tmp_path, {"advancedsearch": {"response": {"numFound": 42, "docs": []}}})
    url = discover.advancedsearch_url("collection:x", rows=0)
    first = discover.cached_get_json(url, **ctx)
    assert first["response"]["numFound"] == 42
    n_after_first = calls["n"]
    second = discover.cached_get_json(url, **ctx)
    assert second["response"]["numFound"] == 42
    assert calls["n"] == n_after_first  # served from cache, no new call


def test_size_collection_uses_two_counts(tmp_path):
    ctx, calls = make_ctx(
        tmp_path,
        {
            # texts needle checked first; it is the more specific of the two.
            "mediatype%3Atexts": {"response": {"numFound": 103000, "docs": []}},
            "q=collection%3Agovernmentpublications": {"response": {"numFound": 104000, "docs": []}},
        },
    )
    sizes = discover.size_collection("governmentpublications", ctx=ctx)
    assert sizes["total_items"] == 104000
    assert sizes["texts_items"] == 103000


def test_assert_healthy_passes_on_good_baseline(tmp_path):
    ctx, _ = make_ctx(
        tmp_path,
        {
            discover.CANARY_TERM: {"response": {"numFound": 0, "docs": []}},
            "q=collection%3Agovernmentpublications&rows=0": {
                "response": {"numFound": 104293, "docs": []}
            },
        },
    )
    assert discover.assert_healthy("collection:governmentpublications", ctx=ctx) == 104293


def test_assert_healthy_aborts_on_canned_canary(tmp_path):
    # Canned/throttled: the nonsense canary returns a huge count.
    ctx, _ = make_ctx(tmp_path, {discover.CANARY_TERM: {"response": {"numFound": 5533263, "docs": []}}})
    with pytest.raises(discover.ThrottleError):
        discover.assert_healthy("collection:governmentpublications", ctx=ctx)


def test_assert_healthy_aborts_on_implausible_baseline(tmp_path):
    ctx, _ = make_ctx(
        tmp_path,
        {
            discover.CANARY_TERM: {"response": {"numFound": 0, "docs": []}},
            "q=collection%3Agovernmentpublications&rows=0": {
                "response": {"numFound": 5533263, "docs": []}
            },
        },
    )
    with pytest.raises(discover.ThrottleError):
        discover.assert_healthy("collection:governmentpublications", ctx=ctx)


def test_sample_identifiers_reads_docs(tmp_path):
    ctx, _ = make_ctx(
        tmp_path,
        {"advancedsearch": {"response": {"numFound": 2, "docs": [{"identifier": "a"}, {"identifier": "b"}]}}},
    )
    assert discover.sample_identifiers("q", 5, ctx=ctx) == ["a", "b"]


def test_ocr_spotcheck_aggregates(tmp_path, real_meta):
    # Two ids, both resolve to the same real metadata (has usable text, year 1980).
    ctx, _ = make_ctx(tmp_path, {"/metadata/": real_meta})
    result = discover.ocr_spotcheck(["id1", "id2"], ctx=ctx)
    assert result["sample_size"] == 2
    assert result["with_usable_text"] == 2
    assert result["with_usable_text_pct"] == 100.0
    assert result["decade_counts"] == {"1980s": 2}
    assert result["format_counts"]["DjVuTXT"] == 2


def test_offline_cache_miss_raises(tmp_path):
    ctx, _ = make_ctx(tmp_path, {})
    ctx["offline"] = True
    with pytest.raises(discover.ScrapeError):
        discover.cached_get_json(discover.advancedsearch_url("collection:x", rows=0), **ctx)
