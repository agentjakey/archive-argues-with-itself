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
# Source selection (DjVuTXT preferred) and capability flag
# --------------------------------------------------------------------------- #


def test_select_source_prefers_djvutxt(real_meta):
    # The fixture has hOCR, DjVu XML AND DjVuTXT; the parsed source is DjVuTXT.
    fmt, entry = fetch.select_source(real_meta)
    assert fmt == "DjVuTXT"
    assert entry["name"].endswith("_djvu.txt")
    assert entry["md5"]


def test_select_source_falls_back_to_djvuxml():
    meta = {"files": [
        {"format": "hOCR", "name": "x_hocr.html", "md5": "h"},
        {"format": "Djvu XML", "name": "x_djvu.xml", "md5": "x"},
    ]}
    fmt, entry = fetch.select_source(meta)
    assert fmt == "DjVuXML"
    assert entry["md5"] == "x"


def test_select_source_falls_back_to_hocr_only():
    meta = {"files": [{"format": "hOCR", "name": "x_hocr.html", "md5": "h"}]}
    assert fetch.select_source(meta)[0] == "hOCR"


def test_select_source_none_when_no_derivative():
    meta = {"files": [{"format": "JPEG"}, {"format": "Metadata"}]}
    assert fetch.select_source(meta) == (None, None)


def test_word_coords_capability_independent_of_source(real_meta):
    # Source is DjVuTXT, but the item is still word-coord capable (hOCR present).
    assert fetch.word_coords_capable(real_meta) is True
    txt_only = {"files": [{"format": "DjVuTXT", "name": "t_djvu.txt", "md5": "m"}]}
    assert fetch.word_coords_capable(txt_only) is False


# --------------------------------------------------------------------------- #
# Record building
# --------------------------------------------------------------------------- #


def test_record_from_real_fixture(real_meta):
    doc = {"identifier": "01ambientairsurvey00onta", "title": "Ambient air survey",
           "year": 1980, "collection": ["omote", "governmentpublications"]}
    rec = fetch.build_record(doc, real_meta)
    assert rec["ocr_format"] == "DjVuTXT"                 # parsed source is text
    assert rec["ocr_file"]["name"].endswith("_djvu.txt")
    assert rec["ocr_file_ref"].startswith("ocr/")
    assert rec["has_word_coords"] is True                 # capability preserved (hOCR present)
    assert rec["has_printed_page_map"] is True            # Page Numbers JSON present
    assert rec["page_count"] == 524
    assert rec["ocr_engine"] == "ABBYY FineReader 8.0"
    assert rec["dated"] is True


def test_record_txt_only_no_page_map():
    doc = {"identifier": "txtonly", "title": "t", "year": 1975}
    meta = {"metadata": {}, "files": [{"format": "DjVuTXT", "name": "t_djvu.txt", "md5": "m"}]}
    rec = fetch.build_record(doc, meta)
    assert rec["ocr_format"] == "DjVuTXT"
    assert rec["has_word_coords"] is False
    assert rec["has_printed_page_map"] is False


def test_record_djvuxml_fallback():
    # No DjVuTXT: fall back to DjVu XML and mark ocr_format='DjVuXML'.
    doc = {"identifier": "xmlonly", "title": "t", "year": 1980}
    meta = {"metadata": {}, "files": [{"format": "Djvu XML", "name": "x_djvu.xml", "md5": "x"}]}
    rec = fetch.build_record(doc, meta)
    assert rec["ocr_format"] == "DjVuXML"
    assert rec["has_word_coords"] is True                 # DjVu XML is positional OCR
    assert rec["ocr_file"]["md5"] == "x"


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
        # manifest page: parse 1-indexed page
        page = int(url.split("page=")[1].split("&")[0])
        start = (page - 1) * 100
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


def test_harvest_manifest_dedupes_repeated_pages(tmp_path):
    # Regression: if the search ignores paging and returns the same first page
    # forever (the `start`-vs-`page` bug), the loop must terminate via the seen
    # guard and return only the unique items, not spin or inflate the count.
    first_page = [{"identifier": f"id{i}", "title": "t", "year": 1980} for i in range(100)]

    def responder(url):
        if discover.CANARY_TERM in url:
            return {"response": {"numFound": 0, "docs": []}}
        if "rows=0" in url:
            return {"response": {"numFound": 105289, "docs": []}}
        return {"response": {"numFound": 3500, "docs": first_page}}  # same page every time

    ctx, _ = make_ctx(tmp_path, responder)
    cfg = fetch.PilotConfig(
        topic="t", query="health", mediatype="texts", collections=["governmentpublications"],
        fields="identifier,title,year", manifest_rows=100, request_delay=0.0, cache_dir=tmp_path,
        contact="x@example.com", usable_floor=2500,
    )
    docs = fetch.harvest_manifest(cfg, tmp_path / "m.jsonl", ctx=ctx)
    assert len(docs) == 100  # unique only, not 3500


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


def test_enrich_is_resumable(tmp_path, real_meta):
    metas = {"a": real_meta, "b": real_meta}

    def responder(url):
        for ident, meta in metas.items():
            if f"/metadata/{ident}" in url:
                return meta
        raise AssertionError(url)

    ctx, calls = make_ctx(tmp_path, responder)
    docs = [{"identifier": "a", "title": "a", "year": 1980},
            {"identifier": "b", "title": "b", "year": 1981}]
    items = tmp_path / "items.jsonl"
    fetch.enrich(docs, items, ctx=ctx)
    calls_after_first = calls["n"]
    # Second call: both already done, so no new metadata fetches happen.
    records, _ = fetch.enrich(docs, items, ctx=ctx)
    assert len(records) == 2
    assert calls["n"] == calls_after_first  # resumed, nothing re-fetched
    assert items.read_text(encoding="utf-8").strip().count("\n") == 1  # 2 lines, no dupes


def test_enrich_limit_caps_new_items(tmp_path, real_meta):
    def responder(url):
        return real_meta  # any id resolves to a real OCR-bearing item

    ctx, _ = make_ctx(tmp_path, responder)
    docs = [{"identifier": f"id{i}", "title": "t", "year": 1980} for i in range(3)]
    items = tmp_path / "items.jsonl"
    r1, _ = fetch.enrich(docs, items, ctx=ctx, limit=2)
    assert len(r1) == 2
    r2, _ = fetch.enrich(docs, items, ctx=ctx, limit=2)
    assert len(r2) == 3  # remaining one processed on the next chunk


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


def _dl_record(ident, md5):
    return {
        "identifier": ident,
        "ocr_file": {"name": f"{ident}_djvu.txt", "md5": md5, "size": "100"},
        "page_numbers_file": {"name": f"{ident}_page_numbers.json", "md5": md5 + "p", "size": "10"},
        "scandata_file": None,
    }


def test_download_corpus_downloads_then_resumes(tmp_path):
    calls = {"n": 0}

    def downloader(identifier, filename, dest_path):
        calls["n"] += 1
        Path(dest_path).write_text("real ocr text", encoding="utf-8")

    records = [_dl_record("a", "111"), _dl_record("b", "222")]
    r1 = fetch.download_corpus(records, tmp_path, downloader=downloader, sleeper=lambda s: None,
                               checkpoint_path=tmp_path / "ck.json")
    assert r1["downloaded"] == 4 and r1["failed"] == 0 and r1["complete"] is True
    n_after = calls["n"]
    # Rerun: all cached, nothing re-downloaded.
    r2 = fetch.download_corpus(records, tmp_path, downloader=downloader, sleeper=lambda s: None)
    assert r2["downloaded"] == 0 and r2["already_cached"] == 4 and calls["n"] == n_after
    assert (tmp_path / "ck.json").exists()  # checkpoint written


def test_download_corpus_new_limit_and_faults(tmp_path):
    def downloader(identifier, filename, dest_path):
        if identifier == "bad":
            raise RuntimeError("404 not found")
        Path(dest_path).write_text("x", encoding="utf-8")

    records = [_dl_record("good", "1"), _dl_record("bad", "2")]
    # new_limit stops after 1 new download.
    r = fetch.download_corpus(records, tmp_path, downloader=downloader, sleeper=lambda s: None, new_limit=1)
    assert r["downloaded"] == 1 and r["complete"] is False
    # Finish: the bad item's files fail but do not abort the run.
    r2 = fetch.download_corpus(records, tmp_path, downloader=downloader, sleeper=lambda s: None)
    assert r2["failed"] >= 1
    assert any(f["identifier"] == "bad" for f in r2["failures"])


def test_integrity_check_flags_missing_and_empty(tmp_path):
    records = [_dl_record("present", "aaa"), _dl_record("gone", "bbb"), _dl_record("blank", "ccc")]
    # 'present' source file exists with content.
    p = fetch.content_path(tmp_path, "aaa", "present_djvu.txt")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("has text", encoding="utf-8")
    # 'blank' source file exists but is empty.
    b = fetch.content_path(tmp_path, "ccc", "blank_djvu.txt")
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text("   \n", encoding="utf-8")
    # 'gone' has no file on disk.
    rep = fetch.integrity_check(records, tmp_path)
    assert rep["source_present"] == 1
    assert any(m["identifier"] == "gone" for m in rep["missing"])
    assert any(e["identifier"] == "blank" for e in rep["empty"])
    assert rep["total_source_bytes"] == p.stat().st_size


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
