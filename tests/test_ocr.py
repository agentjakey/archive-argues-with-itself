"""OCR parser, quality, and page/passage construction tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from archive_debugger.ingest import ocr

FX = Path(__file__).parent / "fixtures" / "ocr"


def read(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# DjVuTXT form-feed splitting and leaf alignment
# --------------------------------------------------------------------------- #


def test_djvutxt_formfeed_split_and_leaf_alignment():
    pages = ocr.parse_djvutxt(read("clean_ff_djvutxt.txt"))
    assert len(pages) == 3
    assert "National Health" in pages[0]
    assert "Ontario and Alberta" in pages[1]
    assert "Statistics Canada" in pages[2]


def test_real_djvutxt_without_formfeed_yields_single_page():
    # Codifies the corpus finding: real IA djvu.txt for microfilm items carries
    # NO form-feed, so it collapses to one page and must be flagged upstream.
    text = read("real_noff_djvutxt.txt")
    assert text.count("\f") == 0
    assert len(ocr.parse_djvutxt(text)) == 1


# --------------------------------------------------------------------------- #
# DjVu XML (fallback) and hOCR (future-only)
# --------------------------------------------------------------------------- #


def test_djvu_xml_object_per_page():
    pages = ocr.parse_djvu_xml(read("sample_djvu.xml"))
    assert len(pages) == 2
    assert "Public health in Canada" in pages[0]
    assert "Ontario hospital funding" in pages[1]


def test_hocr_parser_works_but_is_not_a_corpus_parser():
    pages = ocr.parse_hocr(read("sample_hocr.html"))
    assert len(pages) == 2
    assert "Health Canada" in pages[0]
    # And the corpus path refuses it.
    with pytest.raises(ValueError):
        ocr.parse_item({"identifier": "x", "ocr_format": "hOCR"}, "irrelevant", None)


# --------------------------------------------------------------------------- #
# Quality proxy
# --------------------------------------------------------------------------- #


def test_quality_clean_beats_garbage():
    clean = ocr.parse_djvutxt(read("clean_ff_djvutxt.txt"))[0]
    garbage = read("garbage_djvutxt.txt")
    q_clean = ocr.ocr_quality(clean)
    q_garbage = ocr.ocr_quality(garbage)
    assert q_clean > 0.6
    assert q_garbage < 0.4
    assert q_clean > q_garbage


def test_quality_empty_is_zero():
    assert ocr.ocr_quality("   \n  ") == 0.0


# --------------------------------------------------------------------------- #
# page_numbers.json
# --------------------------------------------------------------------------- #


def test_load_printed_pages_real_fixture():
    labels = ocr.load_printed_pages(FX / "real_page_numbers.json")
    assert isinstance(labels, list)
    assert len(labels) == 2  # leaf count = authoritative


# --------------------------------------------------------------------------- #
# Page + passage construction
# --------------------------------------------------------------------------- #


def test_chunking_stays_within_page_and_has_one_leaf():
    record = {"identifier": "itemX", "ocr_format": "DjVuTXT"}
    result = ocr.parse_item(record, read("clean_ff_djvutxt.txt"), printed=None, expected_leaves=3)
    assert result["parsed_page_count"] == 3
    assert result["alignment_risk"] is False
    # every passage carries exactly one leaf_index and offsets within its page
    for p in result["passages"]:
        assert isinstance(p["leaf_index"], int)
        assert p["char_start"] < p["char_end"]
        assert "embedding_id" in p and p["embedding_id"] is None
        assert p["ocr_conf_mean"] is None
        assert 0.0 <= p["ocr_quality"] <= 1.0
    # passage ids are unique
    ids = [p["passage_id"] for p in result["passages"]]
    assert len(ids) == len(set(ids))


def test_page_count_mismatch_is_flagged_not_hidden():
    record = {"identifier": "mm", "ocr_format": "DjVuTXT"}
    # No form-feed -> parses to 1 page, but the page map says 22 leaves.
    result = ocr.parse_item(record, read("real_noff_djvutxt.txt"), printed=None, expected_leaves=22)
    assert result["parsed_page_count"] == 1
    assert result["alignment_risk"] is True
    assert "22 leaves" in result["reason"]


def test_empty_page_kept_with_has_text_zero():
    record = {"identifier": "ee", "ocr_format": "DjVuTXT"}
    # Two pages: one real, one empty (form-feed then whitespace).
    text = "real health report text about Canada\f   \n  "
    result = ocr.parse_item(record, text, printed=None)
    assert len(result["pages"]) == 2
    assert result["pages"][1]["has_text"] == 0
    # empty page yields no passages but the page row is retained
    assert all(p["leaf_index"] == 0 for p in result["passages"])


def test_printed_page_from_page_numbers_when_available():
    record = {"identifier": "pp", "ocr_format": "DjVuTXT"}
    result = ocr.parse_item(record, "page one text\fpage two text", printed=["i", "1"])
    assert result["pages"][0]["printed_page"] == "i"
    assert result["pages"][1]["printed_page"] == "1"
