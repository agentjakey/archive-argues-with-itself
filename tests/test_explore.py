"""Tests for the Week 1 coverage-audit harvester.

Pure functions (year, decade, jurisdiction, doc_type, tabulation) are tested
against a real captured scrape page in tests/fixtures. The paginated fetch loop
is tested with a fake transport whose pages are sliced from that same real data,
so no network is touched and the sleeper never actually waits.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from archive_debugger.harvest import explore

FIXTURE = Path(__file__).parent / "fixtures" / "scrape_governmentpublications_page.json"


@pytest.fixture
def real_page() -> dict:
    with FIXTURE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def real_items(real_page) -> list[dict]:
    return real_page["items"]


# --------------------------------------------------------------------------- #
# Query and URL construction
# --------------------------------------------------------------------------- #


def test_build_query_shape():
    q = explore.build_query("housing OR affordability", ["governmentpublications"], "texts")
    assert q == (
        "mediatype:texts AND collection:(governmentpublications) "
        "AND (housing OR affordability)"
    )


def test_build_url_includes_cursor_only_when_present():
    without = explore.build_url("q", "identifier", 100, None)
    assert "cursor=" not in without
    with_cursor = explore.build_url("q", "identifier", 100, "abc123")
    assert "cursor=abc123" in with_cursor


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #


def test_item_year_from_year_field(real_items):
    first = real_items[0]
    assert explore.item_year(first) == first["year"]


def test_item_year_falls_back_to_date():
    assert explore.item_year({"date": "1980-01-01T00:00:00Z"}) == 1980


def test_item_year_none_when_missing():
    assert explore.item_year({"title": "no date here"}) is None


def test_real_fixture_has_an_undated_item(real_items):
    # The captured page intentionally includes an item with no year, so the
    # undated path is exercised against real data, not a synthetic edge case.
    assert any(explore.item_year(it) is None for it in real_items)


def test_decade_label():
    assert explore.decade_label(1889) == "1880s"
    assert explore.decade_label(1980) == "1980s"
    assert explore.decade_label(None) == "undated"


def test_jurisdiction_detects_ontario_from_issuer(real_items):
    # The Ontario Ministry of the Environment items must map to Ontario.
    onta = [it for it in real_items if "Ontario" in explore._as_text(it.get("publisher"))]
    assert onta
    assert all(explore.jurisdiction(it) == "Ontario" for it in onta)


def test_jurisdiction_unknown_when_no_signal():
    assert explore.jurisdiction({"title": "A pamphlet", "publisher": "Some Press"}) == "Unknown"


def test_jurisdiction_does_not_use_scanner_collection():
    # 'toronto' is a digitizing library, not a jurisdiction signal.
    item = {"title": "x", "publisher": "y", "collection": ["toronto", "governmentpublications"]}
    assert explore.jurisdiction(item) == "Unknown"


def test_doc_type_examples():
    assert explore.doc_type({"title": "Annual report 1990"}) == "Annual report"
    assert explore.doc_type({"title": "General index to the journals"}) == "Index/catalogue"
    assert explore.doc_type({"title": "An analysis of smelter emissions"}) == "Study/survey"
    assert explore.doc_type({"title": "Something unclassifiable"}) == "Other/Unknown"


# --------------------------------------------------------------------------- #
# Tabulation
# --------------------------------------------------------------------------- #


def test_tabulate_counts_add_up(real_items):
    cov = explore.tabulate("t", real_items, reported_total=104298)
    assert cov.total_fetched == len(real_items)
    assert sum(cov.by_decade.values()) == len(real_items)
    assert sum(cov.by_jurisdiction.values()) == len(real_items)
    assert sum(cov.three_way.values()) == len(real_items)
    # undated + pre_recent + recent must partition every item.
    assert cov.undated + cov.pre_recent + cov.recent == len(real_items)


def test_summary_recency_fields(real_items):
    cov = explore.tabulate("t", real_items, reported_total=104298)
    s = explore.coverage_summary(cov)
    assert s["reaches_target_2500"] is True  # reported_total is large
    assert s["undated"] >= 1
    assert 0.0 <= s["pre_2000_pct"] <= 100.0


# --------------------------------------------------------------------------- #
# Retry-After parsing and backoff
# --------------------------------------------------------------------------- #


def test_parse_retry_after_seconds():
    assert explore.parse_retry_after("12") == 12.0


def test_parse_retry_after_none():
    assert explore.parse_retry_after(None) is None
    assert explore.parse_retry_after("not-a-date") is None


def test_fetch_retries_on_503_then_succeeds():
    calls = []
    slept = []

    def transport(url, headers, timeout):
        calls.append(url)
        if len(calls) == 1:
            return explore.HttpResponse(503, {"retry-after": "1"}, "")
        return explore.HttpResponse(200, {}, json.dumps({"items": [], "total": 0}))

    data = explore.fetch_with_retries(
        "http://x",
        {},
        transport=transport,
        sleeper=slept.append,
        rng=random.Random(0),
    )
    assert data == {"items": [], "total": 0}
    assert len(calls) == 2
    assert slept and slept[0] >= 1.0  # honored Retry-After


def test_fetch_raises_on_persistent_503():
    def transport(url, headers, timeout):
        return explore.HttpResponse(503, {}, "busy")

    with pytest.raises(explore.ScrapeError):
        explore.fetch_with_retries(
            "http://x",
            {},
            transport=transport,
            sleeper=lambda s: None,
            rng=random.Random(0),
            max_retries=2,
        )


def test_fetch_raises_on_json_error_payload():
    def transport(url, headers, timeout):
        return explore.HttpResponse(200, {}, json.dumps({"error": "boom"}))

    with pytest.raises(explore.ScrapeError):
        explore.fetch_with_retries(
            "http://x", {}, transport=transport, sleeper=lambda s: None, rng=random.Random(0)
        )


# --------------------------------------------------------------------------- #
# Pagination + cache
# --------------------------------------------------------------------------- #


def make_paged_transport(real_items):
    """A fake transport that returns real items across two cursor pages, then
    stops. Records how many network calls were made."""
    half = len(real_items) // 2 or 1
    pages = {
        None: {"items": real_items[:half], "cursor": "CUR1", "total": len(real_items)},
        "CUR1": {"items": real_items[half:], "cursor": "CUR2", "total": len(real_items)},
        "CUR2": {"items": [], "total": len(real_items)},  # empty page ends it
    }
    calls = {"n": 0}

    def transport(url, headers, timeout):
        calls["n"] += 1
        cursor = None
        if "cursor=" in url:
            cursor = url.split("cursor=")[1].split("&")[0]
        return explore.HttpResponse(200, {}, json.dumps(pages[cursor]))

    return transport, calls


def test_scrape_all_paginates_and_caches(tmp_path, real_items):
    transport, calls = make_paged_transport(real_items)
    cache_dir = tmp_path / "cache"

    items, meta = explore.scrape_all(
        "some query",
        fields="identifier",
        count=100,
        cache_dir=cache_dir,
        transport=transport,
        sleeper=lambda s: None,
        rng=random.Random(0),
        headers={},
        page_delay=0.0,
    )
    assert len(items) == len(real_items)
    assert meta["total"] == len(real_items)
    first_call_count = calls["n"]
    assert first_call_count >= 2  # at least two real pages fetched

    # Rerun: everything is cached, so the transport must not be called again.
    items2, _ = explore.scrape_all(
        "some query",
        fields="identifier",
        count=100,
        cache_dir=cache_dir,
        transport=transport,
        sleeper=lambda s: None,
        rng=random.Random(0),
        headers={},
        page_delay=0.0,
    )
    assert [i["identifier"] for i in items2] == [i["identifier"] for i in items]
    assert calls["n"] == first_call_count  # zero additional network calls


def test_scrape_all_respects_max_items(tmp_path, real_items):
    transport, _ = make_paged_transport(real_items)
    items, _ = explore.scrape_all(
        "q",
        fields="identifier",
        count=100,
        cache_dir=tmp_path / "c",
        transport=transport,
        sleeper=lambda s: None,
        rng=random.Random(0),
        headers={},
        page_delay=0.0,
        max_items=2,
    )
    assert len(items) == 2


def test_scrape_all_offline_cache_miss_raises(tmp_path):
    def transport(url, headers, timeout):
        raise AssertionError("offline mode must not call the transport")

    with pytest.raises(explore.ScrapeError):
        explore.scrape_all(
            "q",
            fields="identifier",
            count=100,
            cache_dir=tmp_path / "empty",
            transport=transport,
            sleeper=lambda s: None,
            rng=random.Random(0),
            headers={},
            offline=True,
        )


# --------------------------------------------------------------------------- #
# End-to-end orchestration against fixture data (no network)
# --------------------------------------------------------------------------- #


def test_run_audit_writes_tables(tmp_path, real_items):
    transport, _ = make_paged_transport(real_items)
    config = explore.AuditConfig(
        fields="identifier,title,creator,publisher,date,year,collection,language,mediatype",
        count=100,
        max_items=0,
        mediatype="texts",
        collections=["governmentpublications"],
        contact="test@example.com",
        candidates=[explore.Candidate(name="housing", query="housing")],
    )
    out_dir = tmp_path / "out"
    coverages = explore.run_audit(
        config,
        out_dir,
        tmp_path / "cache",
        contact="test@example.com",
        transport=transport,
        sleeper=lambda s: None,
        rng=random.Random(0),
        page_delay=0.0,
    )
    assert len(coverages) == 1
    assert (out_dir / "AUDIT_SUMMARY.md").exists()
    assert (out_dir / "housing__by_decade_jurisdiction_doctype.csv").exists()
    assert (out_dir / "housing__summary.json").exists()
    summary_text = (out_dir / "AUDIT_SUMMARY.md").read_text(encoding="utf-8")
    assert "housing" in summary_text
