"""Second sources: the host allowlist and SSRF refusals, redirects checked hop by hop, the adapter
contract (publication and capture dates kept apart), and the Wayback adapter with the network replaced."""
from __future__ import annotations

import io
import json
import socket
import urllib.error
import urllib.parse

import pytest

from archive_debugger.sources import adapter, fetch, wayback


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


PUBLIC = lambda host: ["207.241.237.3"]          # noqa: E731  (a public address)


@pytest.mark.parametrize("url, reason", [
    ("ftp://web.archive.org/x", "scheme"),
    ("file:///etc/passwd", "scheme"),
    ("https://user:pw@web.archive.org/x", "credentials"),
    ("https://web.archive.org@evil.example/x", "credentials"),
    ("https://web.archive.org:8443/x", "port"),
    ("https://127.0.0.1/x", "IP address"),
    ("https://[::1]/x", "IP address"),
    ("https://169.254.169.254/latest/meta-data/", "IP address"),
    ("https://evil.example/x", "allowlist"),
    ("https://web.archive.org.evil.example/x", "allowlist"),
    ("https://archive.org.evil.example/x", "allowlist"),
])
def test_refused_urls(url, reason):
    with pytest.raises(fetch.Refused, match=reason):
        fetch.check_url(url, resolver=PUBLIC)


def test_an_allowed_name_that_resolves_privately_is_refused():
    with pytest.raises(fetch.Refused, match="non-public"):
        fetch.check_url("https://web.archive.org/x", resolver=lambda h: ["10.0.0.5"])
    with pytest.raises(fetch.Refused, match="non-public"):
        fetch.check_url("https://web.archive.org/x", resolver=lambda h: ["127.0.0.1"])


def test_http_is_upgraded_and_fragments_dropped():
    assert fetch.check_url("http://web.archive.org/web/1/x#frag", resolver=PUBLIC) == "https://web.archive.org/web/1/x"


class FakeOpener:
    def __init__(self, routes):
        self.routes, self.seen = routes, []

    def open(self, req, timeout):
        url = req.full_url
        self.seen.append(url)
        kind, value = self.routes[url]
        if kind == "redirect":
            raise urllib.error.HTTPError(url, 302, "Found", {"location": value}, io.BytesIO(b""))
        return io.BytesIO(value)


def test_redirects_are_checked_hop_by_hop():
    ok = FakeOpener({"https://web.archive.org/a": ("redirect", "/b"), "https://web.archive.org/b": ("body", b"done")})
    assert fetch.get("https://web.archive.org/a", resolver=PUBLIC, opener=ok, sleep=lambda s: None) == \
        ("https://web.archive.org/b", b"done")
    bad = FakeOpener({"https://web.archive.org/a": ("redirect", "https://internal.example/admin")})
    with pytest.raises(fetch.Refused, match="allowlist"):
        fetch.get("https://web.archive.org/a", resolver=PUBLIC, opener=bad, sleep=lambda s: None)
    assert bad.seen == ["https://web.archive.org/a"]       # the internal host was never requested


def test_a_redirect_loop_stops():
    loop = FakeOpener({"https://web.archive.org/a": ("redirect", "/a")})
    with pytest.raises(fetch.Refused, match="redirects"):
        fetch.get("https://web.archive.org/a", resolver=PUBLIC, opener=loop, sleep=lambda s: None)


PAGE = b"""<html><head><title>Tobacco - Health Canada</title>
<meta name="dcterms.modified" content="2008-03-14"><script>var x = "Date modified: 1999-01-01";</script></head>
<body><h1>Tobacco</h1><p>Smoking is the leading preventable cause of death.</p>
<p>Date modified: 2008-03-14</p><a href="http://10.0.0.1/admin">ignore me</a></body></html>"""


def test_wayback_records_keep_publication_and_capture_dates_apart():
    calls = []

    def get(url):
        calls.append(url)
        if url.startswith(wayback.CDX):
            return url, json.dumps([["timestamp", "original"], ["20090215120000", "http://www.hc-sc.gc.ca/hc-ps/tobac-tabac/index-eng.php"]]).encode()
        return url, PAGE
    recs = list(wayback.WaybackPrefix("www.hc-sc.gc.ca/hc-ps/tobac-tabac/", 2005, 2010, 5, get=get).records())
    assert len(recs) == 1
    r = recs[0]
    assert r.title == "Tobacco - Health Canada"
    assert "Smoking is the leading preventable cause of death." in r.text and "var x" not in r.text
    assert (r.publication.year, r.publication.method) == (2008, "read_from_page_meta")
    assert (r.capture.year, r.capture.value, r.capture.method) == (2009, "2009-02-15", "archive_capture_timestamp")
    assert r.problems() == []
    assert r.locator == "https://web.archive.org/web/20090215120000/http://www.hc-sc.gc.ca/hc-ps/tobac-tabac/index-eng.php"
    # The link inside the page is content, never a destination: only the CDX and the capture were requested.
    assert len(calls) == 2 and all(c.startswith("https://web.archive.org/") for c in calls)


def test_the_contract_refuses_a_capture_date_passed_off_as_publication():
    cap = wayback.capture_date("20090215120000")
    r = adapter.SourceRecord("wayback", "x", "https://web.archive.org/web/x", None, None, "t", publication=cap, capture=cap)
    assert "a capture date was given as the publication date" in r.problems()


def test_no_date_on_the_page_means_no_publication_date():
    page = wayback.parse_page(b"<html><body><p>No dates here.</p></body></html>")
    assert wayback.publication_date(page).method == "not_found"

def test_robots_rules_for_ai_agents_and_content_usage():
    from archive_debugger.sources import signals
    text = "User-agent: *\nDisallow: /private/\n\nUser-agent: GPTBot\nUser-agent: CCBot\nDisallow: /\n\nContent-Usage: train-ai=n\n"
    got = signals.parse_robots(text, "/hc-ps/tobac-tabac/index-eng.php")
    assert got["agents"]["*"]["disallowed"] is False
    assert got["agents"]["GPTBot"]["disallowed"] is True and got["agents"]["CCBot"]["disallowed"] is True
    assert got["content_usage"] == ["train-ai=n"]


def test_a_file_is_in_effect_only_when_the_captures_around_the_page_agree():
    from archive_debugger.sources import signals
    cdx = {"www.x.gc.ca/robots.txt": [["timestamp", "digest", "statuscode"], ["20080101000000", "AAA", "200"],
                                      ["20100101000000", "BBB", "200"]],
           "www.x.gc.ca/.well-known/tdmrep.json": [["timestamp", "digest", "statuscode"]]}
    calls = []

    def get(url):
        calls.append(url)
        if url.startswith(signals.CDX):
            key = next(k for k in cdx if urllib.parse.quote(k, safe="") in url)
            return url, json.dumps(cdx[key]).encode()
        return url, b"User-agent: *\nDisallow:\n"

    def get_response(url):
        return url, {"x-archive-orig-x-robots-tag": "noindex"}, b"<html><meta name='robots' content='noai'></html>"
    reader = signals.SignalReader(get=get, get_response=get_response)
    between = reader.for_capture("http://www.x.gc.ca/a.html", "20090101000000")
    assert between.robots.state == "unknown"            # it changed between the captures around the page
    assert between.tdmrep.state == "unknown"            # never captured: unknown, not "none"
    assert between.headers == {"x-robots-tag": "noindex"} and between.meta[0]["content"] == "noai"
    assert between.restricts_ai is True                 # the page's own meta tag restricts it
    on = reader.for_capture("http://www.x.gc.ca/a.html", "20080101000000")
    assert on.robots.state == "in_effect" and on.robots.before["digest"] == "AAA"
    assert all(c.startswith("https://web.archive.org/") for c in calls)
