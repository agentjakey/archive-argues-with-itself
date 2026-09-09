"""Tests for the Phase 2 harvest.

The metadata-shaped logic (OCR selection priority, flags, record building, skip
path) is tested against the real committed metadata fixture plus small
constructed edge cases. The manifest paging loop, metadata reads, and the
content-addressed download are tested with fakes, so no network is touched.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from archive_debugger.harvest import discover, fetch

META_FIXTURE = Path(__file__).parent / "fixtures" / "metadata_01ambientairsurvey00onta.json"


@pytest.fixture
def real_meta() -> dict:
    with META_FIXTURE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# OCR selection priority
# --------------------------------------------------------------------------- #


def test_select_ocr_prefers_hocr(real_meta):
    ocr = fetch.select_ocr(real_meta)
    assert ocr["ocr_format"] == "hOCR"
    assert ocr["md5"]  # a real file entry with a checksum


def test_select_ocr_priority_djvu_xml_over_txt():
    meta = {"files": [
        {"format": "DjVuTXT", "name": "x_djvu.txt", "md5": "t"},
        {"format": "Djvu XML", "name": "x_djvu.xml", "md5": "x"},
    ]}
    assert fetch.select_ocr(meta)["ocr_format"] == "Djvu XML"


def test_select_ocr_txt_only():
    meta = {"files": [
        {"format": "DjVu", "name": "x.djvu"},
        {"format": "DjVuTXT", "name": "x_djvu.txt", "md5": "t"},
    ]}
    assert fetch.select_ocr(meta)["ocr_format"] == "DjVuTXT"


def test_select_ocr_none_when_no_derivative():
    meta = {"files": [{"format": "JPEG"}, {"format": "Metadata"}]}
    assert fetch.select_ocr(meta) is None


# --------------------------------------------------------------------------- #
# Flags and record building
# --------------------------------------------------------------------------- #


def test_has_word_coords():
    assert fetch.has_word_coords("hOCR") is True
    assert fetch.has_word_coords("Djvu XML") is True
    assert fetch.has_word_coords("DjVuTXT") is False


def test_record_from_real_fixture(real_meta):
    doc = {"identifier": "01ambientairsurvey00onta", "title": "Ambient air survey",
           "year": 1980, "collection": ["omote", "governmentpublications"]}
    rec = fetch.build_record(doc, real_meta)
    assert rec["ocr_format"] == "hOCR"
    assert rec["has_word_coords"] is True
    assert rec["has_printed_page_map"] is True       # Page Numbers JSON present
    assert rec["page_count"] == 524
    assert rec["ocr_engine"] == "ABBYY FineReader 8.0"
    assert rec["dated"] is True
    assert rec["ocr_file"]["md5"]


def test_record_txt_only_no_page_map():
    doc = {"identifier": "txtonly", "title": "t", "year": 1975}
    meta = {"metadata": {}, "files": [{"format": "DjVuTXT", "name": "t_djvu.txt", "md5": "m"}]}
    rec = fetch.build_record(doc, meta)
    assert rec["ocr_format"] == "DjVuTXT"
    assert rec["has_word_coords"] is False
    assert rec["has_printed_page_map"] is False


def test_record_undated_is_kept():
    doc = {"identifier": "u", "title": "t"}
    meta = {"metadata": {}, "files": [{"format": "hOCR", "name": "u_hocr.html", "md5": "m"}]}
    rec = fetch.build_record(doc, meta)
    assert rec is not None
    assert rec["dated"] is False
    assert rec["year"] is None


def test_record_none_when_no_ocr():
    doc = {"identifier": "n", "title": "t", "year": 1980}
    meta = {"metadata": {}, "files": [{"format": "JPEG"}]}
    assert fetch.build_record(doc, meta) is None


# --------------------------------------------------------------------------- #
# Fake-context helper
# --------------------------------------------------------------------------- #


def make_ctx(tmp_path, responder):
    calls = {"n": 0}

    def transport(url, headers, timeout):
        calls["n"] += 1
        return discover.explore.HttpResponse(200, {}, json.dumps(responder(url)))

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


# --------------------------------------------------------------------------- #
# Manifest paging loop
# --------------------------------------------------------------------------- #


def test_harvest_manifest_pages_all(tmp_path):
    num_found = 250
    all_docs = [{"identifier": f"id{i}", "title": f"t{i}", "year": 1970 + (i % 40)} for i in range(num_found)]

    def responder(url):
        if discover.CANARY_TERM in url:
            return {"response": {"numFound": 0, "docs": []}}
        if "rows=0" in url:
            return {"response": {"numFound": 105289, "docs": []}}  # assert_healthy baseline
        # manifest page: parse start
        start = int(url.split("start=")[1].split("&")[0])
        return {"response": {"numFound": num_found, "docs": all_docs[start:start + 100]}}

    ctx, _ = make_ctx(tmp_path, responder)
    cfg = fetch.PilotConfig(
        topic="public_health", query="health", mediatype="texts",
        collections=["governmentpublications", "uoftgovpubs"],
        fields="identifier,title,year", manifest_rows=100, request_delay=0.0,
        cache_dir=tmp_path, contact="x@example.com", usable_floor=2500,
    )
    out = tmp_path / "manifest.jsonl"
    docs = fetch.harvest_manifest(cfg, out, ctx=ctx)
    assert len(docs) == num_found
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == num_found
    assert json.loads(lines[0])["identifier"] == "id0"


def test_harvest_manifest_aborts_on_throttle(tmp_path):
    def responder(url):
        # Canary returns a huge count => throttled/canned.
        if discover.CANARY_TERM in url:
            return {"response": {"numFound": 999999, "docs": []}}
        return {"response": {"numFound": 0, "docs": []}}

    ctx, _ = make_ctx(tmp_path, responder)
    cfg = fetch.PilotConfig(
        topic="t", query="health", mediatype="texts", collections=["governmentpublications"],
        fields="identifier", manifest_rows=100, request_delay=0.0, cache_dir=tmp_path,
        contact="x@example.com", usable_floor=2500,
    )
    with pytest.raises(discover.ThrottleError):
        fetch.harvest_manifest(cfg, tmp_path / "m.jsonl", ctx=ctx)


# --------------------------------------------------------------------------- #
# enrich + skip path (fake metadata transport)
# --------------------------------------------------------------------------- #


def test_enrich_skips_items_without_ocr(tmp_path, real_meta):
    metas = {
        "withocr": real_meta,
        "noocr": {"metadata": {}, "files": [{"format": "JPEG"}]},
    }

    def responder(url):
        for ident, meta in metas.items():
            if f"/metadata/{ident}" in url:
                return meta
        raise AssertionError(url)

    ctx, _ = make_ctx(tmp_path, responder)
    docs = [{"identifier": "withocr", "title": "a", "year": 1980},
            {"identifier": "noocr", "title": "b", "year": 1990}]
    records, skipped = fetch.enrich(docs, tmp_path / "items.jsonl", ctx=ctx)
    assert [r["identifier"] for r in records] == ["withocr"]
    assert skipped == ["noocr"]


# --------------------------------------------------------------------------- #
# Content-addressed download
# --------------------------------------------------------------------------- #


def test_content_path_shape(tmp_path):
    p = fetch.content_path(tmp_path, "abcdef123", "ITEM_hocr.html")
    assert p.parent.name == "ab"
    assert p.name == "abcdef123__ITEM_hocr.html"


def test_download_file_skips_when_cached(tmp_path):
    calls = {"n": 0}

    def downloader(identifier, filename, dest_path):
        calls["n"] += 1
        Path(dest_path).write_text("data", encoding="utf-8")

    entry = {"name": "ITEM_hocr.html", "md5": "deadbeef", "size": "10"}
    dest1, did1 = fetch.download_file("id", entry, tmp_path, downloader=downloader, sleeper=lambda s: None)
    assert did1 is True and dest1.exists() and calls["n"] == 1
    # Second call: already cached, downloader must not be invoked again.
    dest2, did2 = fetch.download_file("id", entry, tmp_path, downloader=downloader, sleeper=lambda s: None)
    assert did2 is False and dest2 == dest1 and calls["n"] == 1


def test_summarize_counts(real_meta):
    records = [
        {"identifier": "a", "ocr_format": "hOCR", "has_word_coords": True,
         "has_printed_page_map": True, "dated": True, "year": 1980},
        {"identifier": "b", "ocr_format": "DjVuTXT", "has_word_coords": False,
         "has_printed_page_map": False, "dated": False, "year": None},
    ]
    s = fetch.summarize(records, skipped=["c"], manifest_count=3, floor=2500)
    assert s["usable_count"] == 2
    assert s["skipped_no_ocr"] == 1
    assert s["ocr_format_breakdown"] == {"hOCR": 1, "DjVuTXT": 1}
    assert s["has_word_coords"] == 1
    assert s["undated"] == 1
    assert s["clears_floor"] is False
