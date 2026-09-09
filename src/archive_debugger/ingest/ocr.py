"""OCR parsing and page/passage construction (Phase 4).

Local only: reads cached derivatives under raw/ and writes pages/passages into
civic.db. No network, no re-fetch.

Parsers branch on items.ocr_format:
  - DjVuTXT  : split pages on form-feed (\\f); page ordinal (0-based) = leaf_index,
               aligned to IA /page/n{leaf}. NOTE: some IA djvu.txt carry NO
               form-feed; such an item yields a single page and MUST be flagged as
               a citation-alignment risk rather than silently accepted.
  - DjVuXML  : OBJECT-per-page -> page-bounded text (used only for that format).
  - hOCR     : implemented for the future on-demand word-level upgrade path, but
               NEVER invoked over the corpus (parse_item refuses it).

N3: no coordinates are stored. has_word_coords is untouched here.

Quality is a proxy in [0,1] from surface metrics only (dictionary-hit rate,
alnum ratio, garbage-line fraction, token-length sanity). There is no per-word
confidence in DjVuTXT/DjVu XML, so ocr_conf_mean stays NULL.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

# A small EN + FR frequent-word lexicon used as the dictionary-hit proxy. It is a
# proxy, not a full dictionary; it is deliberately small and inspectable.
EN_FR_COMMON = {
    # English function + frequent domain words
    "the", "and", "of", "to", "in", "a", "is", "for", "on", "with", "as", "by",
    "that", "this", "was", "were", "are", "be", "an", "or", "at", "from", "which",
    "report", "health", "public", "canada", "ontario", "alberta", "government",
    "department", "ministry", "hospital", "medical", "care", "disease", "board",
    "commission", "committee", "services", "annual", "provincial", "federal",
    "ottawa", "toronto", "edmonton", "statistics", "welfare", "national", "year",
    # French function + frequent domain words
    "de", "la", "le", "les", "et", "des", "du", "une", "un", "pour", "sur", "au",
    "aux", "dans", "par", "est", "sante", "publique", "rapport", "ministere",
    "gouvernement", "canada", "quebec", "ministere", "commission", "publie",
}

WORD_RE = re.compile(r"[A-Za-zÀ-ſ][A-Za-zÀ-ſ'\-]{1,}")


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #


def parse_djvutxt(text: str) -> list[str]:
    """Split DjVuTXT into pages on form-feed. Page ordinal is the 0-based
    leaf_index. An item with no form-feed yields exactly one page (caller must
    validate the count and flag misalignment)."""
    return text.split("\f")


def parse_djvu_xml(data: str) -> list[str]:
    """One page per <OBJECT>. Concatenate <WORD> text within each object."""
    pages: list[str] = []
    root = ET.fromstring(data)
    for obj in root.iter("OBJECT"):
        words = [w.text or "" for w in obj.iter("WORD")]
        pages.append(" ".join(w.strip() for w in words if w.strip()))
    return pages


def parse_djvu_xml_file(path: Path) -> list[str]:
    """Streaming variant: one page per <OBJECT>, freeing each object after use so
    a large DjVu XML file never sits fully in memory (the env kills memory-heavy
    runs)."""
    pages: list[str] = []
    for _event, elem in ET.iterparse(str(path), events=("end",)):
        if elem.tag == "OBJECT":
            words = [w.text or "" for w in elem.iter("WORD")]
            pages.append(" ".join(w.strip() for w in words if w.strip()))
            elem.clear()
    return pages


class _HocrPageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.pages: list[list[str]] = []
        self._depth_stack: list[bool] = []
        self._in_page = False

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class", "")
        if tag == "div" and "ocr_page" in cls:
            self._in_page = True
            self.pages.append([])

    def handle_endtag(self, tag):
        if tag == "div" and self._in_page:
            # A page closes at the next div end after it opened. Good enough for
            # the flat hOCR we emit; the corpus never uses this path.
            self._in_page = False

    def handle_data(self, data):
        if self._in_page and data.strip():
            self.pages[-1].append(data.strip())


def parse_hocr(html: str) -> list[str]:
    """Extract page text from hOCR (ocr_page divs). Implemented for the future
    word-level upgrade; NOT invoked over the corpus (see parse_item)."""
    p = _HocrPageText()
    p.feed(html)
    return [" ".join(words) for words in p.pages]


# --------------------------------------------------------------------------- #
# page_numbers.json
# --------------------------------------------------------------------------- #


def load_printed_pages(path: Path) -> list[Optional[str]]:
    """Return the printed page label per leaf (or None where empty), from
    page_numbers.json. Its length is the authoritative leaf count."""
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    labels: list[Optional[str]] = []
    for entry in data.get("pages", []):
        label = entry.get("pageNumber")
        labels.append(label if label else None)
    return labels


# --------------------------------------------------------------------------- #
# Quality proxy
# --------------------------------------------------------------------------- #


def ocr_quality(text: str) -> float:
    """Proxy quality in [0,1] from surface metrics only. Empty text scores 0."""
    stripped = text.strip()
    if not stripped:
        return 0.0
    tokens = stripped.split()
    if not tokens:
        return 0.0

    non_space = [c for c in text if not c.isspace()]
    alnum_ratio = (sum(c.isalnum() for c in non_space) / len(non_space)) if non_space else 0.0

    words = WORD_RE.findall(text)
    wordlike_ratio = len(words) / len(tokens)
    hits = sum(1 for w in words if w.lower() in EN_FR_COMMON)
    dict_hit = hits / len(words) if words else 0.0

    lines = [ln for ln in text.splitlines() if ln.strip()]
    def _garbage(ln: str) -> bool:
        chars = [c for c in ln if not c.isspace()]
        if not chars:
            return True
        alnum = sum(c.isalnum() for c in chars) / len(chars)
        return alnum < 0.5
    garbage_fraction = (sum(_garbage(ln) for ln in lines) / len(lines)) if lines else 1.0

    mean_len = sum(len(t) for t in tokens) / len(tokens)
    len_sanity = 1.0 if 2.5 <= mean_len <= 12.0 else max(0.0, 1.0 - abs(mean_len - 6.0) / 10.0)

    score = (
        0.15 * alnum_ratio
        + 0.25 * wordlike_ratio
        + 0.40 * min(1.0, dict_hit * 3.0)   # dictionary hits dominate; real prose ~0.3-0.5
        + 0.10 * (1.0 - garbage_fraction)
        + 0.10 * len_sanity
    )
    return round(max(0.0, min(1.0, score)), 4)


def quality_bucket(score: float) -> str:
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "medium"
    return "low"


# --------------------------------------------------------------------------- #
# Page + passage construction
# --------------------------------------------------------------------------- #


def page_id(item_id: str, leaf_index: int) -> str:
    return f"{item_id}#{leaf_index}"


def build_pages(item_id: str, page_texts: list[str], printed: Optional[list[Optional[str]]]) -> list[dict]:
    pages = []
    for leaf, text in enumerate(page_texts):
        printed_page = None
        if printed is not None and leaf < len(printed):
            printed_page = printed[leaf]
        pages.append({
            "page_id": page_id(item_id, leaf),
            "item_id": item_id,
            "leaf_index": leaf,
            "printed_page": printed_page,
            "char_count": len(text),
            "ocr_conf_mean": None,          # no reliable per-word confidence
            "has_text": 1 if text.strip() else 0,
            "_text": text,                   # transient, not a DB column
        })
    return pages


def chunk_within_page(text: str, *, target_tokens: int = 300, overlap_tokens: int = 40) -> list[dict]:
    """Chunk a single page into passages of ~target_tokens with small overlap.
    Never crosses a page boundary. Returns dicts with char offsets into `text`."""
    if not text.strip():
        return []
    # token index -> char span
    spans = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    if not spans:
        return []
    step = max(1, target_tokens - overlap_tokens)
    passages = []
    i = 0
    while i < len(spans):
        window = spans[i:i + target_tokens]
        char_start = window[0][0]
        char_end = window[-1][1]
        chunk_text = text[char_start:char_end]
        passages.append({
            "char_start": char_start,
            "char_end": char_end,
            "text": chunk_text,
            "token_count": len(window),
        })
        if i + target_tokens >= len(spans):
            break
        i += step
    return passages


def build_passages(item_id: str, page: dict, *, target_tokens: int = 300, overlap_tokens: int = 40) -> list[dict]:
    text = page["_text"]
    out = []
    for j, ch in enumerate(chunk_within_page(text, target_tokens=target_tokens, overlap_tokens=overlap_tokens)):
        score = ocr_quality(ch["text"])
        out.append({
            "passage_id": f"{page['page_id']}:{j}",
            "item_id": item_id,
            "page_id": page["page_id"],
            "leaf_index": page["leaf_index"],
            "char_start": ch["char_start"],
            "char_end": ch["char_end"],
            "text": ch["text"],
            "token_count": ch["token_count"],
            "ocr_conf_mean": None,
            "ocr_quality": score,
            "embedding_id": None,
        })
    return out


# --------------------------------------------------------------------------- #
# Per-item orchestration
# --------------------------------------------------------------------------- #

CORPUS_FORMATS = {"DjVuTXT", "DjVuXML"}


def parse_item(record: dict, raw_text: str, printed: Optional[list[Optional[str]]], *, expected_leaves: Optional[int] = None) -> dict:
    """Parse one item into pages + passages, branching on ocr_format. Returns
    {pages, passages, alignment_risk, reason}. hOCR is refused here: it is not a
    corpus parser.

    expected_leaves (from page_numbers.json length and/or metadata page_count) is
    used only to detect and FLAG a page-count mismatch. It is never used to
    fabricate page boundaries: when djvu.txt lacks form-feeds there is no text
    offset to split on, so the item is flagged, not silently re-segmented."""
    fmt = record.get("ocr_format")
    if fmt == "hOCR":
        raise ValueError("hOCR is not a corpus parser; use the on-demand upgrade path")
    if fmt not in CORPUS_FORMATS:
        raise ValueError(f"unsupported ocr_format for corpus parse: {fmt}")

    if fmt == "DjVuTXT":
        page_texts = parse_djvutxt(raw_text)
    else:  # DjVuXML
        page_texts = parse_djvu_xml(raw_text)

    parsed_count = len(page_texts)
    alignment_risk = False
    reason = None
    if expected_leaves is not None and parsed_count != expected_leaves:
        alignment_risk = True
        reason = f"parsed {parsed_count} pages but page map has {expected_leaves} leaves"

    item_id = record["identifier"]
    pages = build_pages(item_id, page_texts, printed)
    passages: list[dict] = []
    for page in pages:
        passages.extend(build_passages(item_id, page))
    return {
        "pages": pages,
        "passages": passages,
        "alignment_risk": alignment_risk,
        "reason": reason,
        "parsed_page_count": parsed_count,
        "expected_leaves": expected_leaves,
    }
