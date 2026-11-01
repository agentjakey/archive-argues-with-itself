"""A bounded Wayback source: captures of Canadian government health pages.

The Wayback Machine's CDX API (documented: github.com/internetarchive/wayback/tree/master/wayback-cdx-server)
lists captures of a URL prefix; this adapter asks for successful HTML captures in a year range,
one per URL (collapse=urlkey), at most `limit`, and fetches each capture's original bytes
(the id_ form, without the archive's banner). From each page it keeps the visible text and title,
the capture date from the CDX timestamp, and a publication or modification date only when the page
states one (a dcterms meta field, or the federal web standard's "Date modified:" line), with the
field or line it came from. Every request goes through sources.fetch and its allowlist."""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from typing import Callable, Iterable

from archive_debugger.sources import fetch
from archive_debugger.sources.adapter import DateEvidence, SourceRecord

CDX = "https://web.archive.org/cdx/search/cdx"
CAPTURE = "https://web.archive.org/web/{ts}id_/{url}"
VIEW = "https://web.archive.org/web/{ts}/{url}"
DATE_META = ("dcterms.modified", "dcterms.issued", "dcterms.created", "dc.date.modified", "dc.date.created", "date")
DATE_MODIFIED = re.compile(r"Date (?:modified|Modified)\s*:?\s*(\d{4})-(\d{2})-(\d{2})")
SKIP = {"script", "style", "noscript", "template", "svg"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title, self.meta, self._skip, self._in_title = [], [], {}, 0, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta" and a.get("name") and a.get("content"):
            self.meta[a["name"].lower()] = a["content"]
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr", "section"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)
        elif not self._skip:
            self.parts.append(data)


def parse_page(raw: bytes) -> dict:
    p = _Text()
    p.feed(raw.decode("utf-8", errors="replace"))
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.parts))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return {"title": html.unescape(" ".join("".join(p.title).split())) or None, "text": text, "meta": p.meta}


def publication_date(page: dict) -> DateEvidence:
    for name in DATE_META:
        value = page["meta"].get(name)
        if value and re.match(r"\d{4}", value):
            return DateEvidence(int(value[:4]), value[:10], "read_from_page_meta", f'meta name="{name}" content="{value}"')
    m = DATE_MODIFIED.search(page["text"])
    if m:
        return DateEvidence(int(m.group(1)), "-".join(m.groups()), "read_from_page_text", m.group(0))
    return DateEvidence(None, None, "not_found", None)


def capture_date(ts: str) -> DateEvidence:
    return DateEvidence(int(ts[:4]), f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", "archive_capture_timestamp", f"CDX timestamp {ts}")


class WaybackPrefix:
    archive = "wayback"

    def __init__(self, prefix: str, first_year: int, last_year: int, limit: int, *, get: Callable = fetch.get):
        self.prefix, self.first_year, self.last_year, self.limit, self.get = prefix, first_year, last_year, limit, get

    def captures(self) -> list:
        params = (f"url={self.prefix}&matchType=prefix&from={self.first_year}&to={self.last_year}"
                  f"&filter=statuscode:200&filter=mimetype:text/html&collapse=urlkey&output=json&limit={self.limit}"
                  "&fl=timestamp,original")
        _, body = self.get(f"{CDX}?{params}")
        rows = json.loads(body.decode("utf-8") or "[]")
        return [(r[0], r[1]) for r in rows[1:]] if rows else []

    def records(self) -> Iterable[SourceRecord]:
        for ts, url in self.captures():
            _, raw = self.get(CAPTURE.format(ts=ts, url=url))
            page = parse_page(raw)
            yield SourceRecord(archive=self.archive, identifier=f"{ts}/{url}", locator=VIEW.format(ts=ts, url=url),
                               original_url=url, title=page["title"], text=page["text"],
                               publication=publication_date(page), capture=capture_date(ts),
                               meta={"cdx_prefix": self.prefix})
