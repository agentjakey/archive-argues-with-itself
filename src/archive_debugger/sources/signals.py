"""AI and text-and-data-mining preference signals in effect at each web capture (Phase 5 prep).

For every host in a bounded web-archive set and every capture of a page on it, this records what the
site said, at that time, about automated reading and AI use, from the archive's own captures:

  robots.txt      the rules for AI crawlers (AI_AGENTS) and for every agent ("*"), whether the captured
                  path is disallowed for each, and any aipref Content-Usage line
  TDMRep          /.well-known/tdmrep.json (W3C TDMRep), and the tdm-reservation response header
  X-Robots-Tag    the captured response's header (the Wayback Machine replays an original header as
                  x-archive-orig-<name>), and robots/tdm meta tags in the captured page

Each signal names the capture it was read from (timestamp and digest). A robots.txt or TDMRep file is
"in effect" at a page capture only when the archive holds a capture of it at or before the page's
capture and one at or after it with the same digest: the file did not change in between. Otherwise
the state is "unknown" with the nearest captures named. Unknown between captures stays unknown; a
missing capture is never read as "no restriction".

Signals are evidence for a person, not policy: a restriction found here becomes a candidate policy
record (docs/formats/governance.md) for Jake to enter, never an entry in the register by itself.
Every request goes through sources.fetch and its allowlist."""
from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

from archive_debugger.sources import fetch

CDX = "https://web.archive.org/cdx/search/cdx"
RAW = "https://web.archive.org/web/{ts}id_/{url}"
AI_AGENTS = ("GPTBot", "ChatGPT-User", "OAI-SearchBot", "CCBot", "Google-Extended", "anthropic-ai", "ClaudeBot",
             "Claude-Web", "PerplexityBot", "Bytespider", "Applebot-Extended", "Amazonbot", "meta-externalagent",
             "FacebookBot", "cohere-ai", "Diffbot", "Omgilibot", "ImagesiftBot")
META = re.compile(r"<meta\s+[^>]*name\s*=\s*[\"'](robots|tdm-reservation|tdm-policy)[\"'][^>]*>", re.IGNORECASE)
CONTENT = re.compile(r"content\s*=\s*[\"']([^\"']*)[\"']", re.IGNORECASE)


@dataclass
class FileState:
    state: str                         # in_effect | absent_in_effect | unknown
    before: Optional[dict] = None      # {timestamp, digest, status} of the capture at or before
    after: Optional[dict] = None       # {timestamp, digest, status} of the capture at or after
    parsed: Optional[dict] = None      # what the file said, when in effect


@dataclass
class CaptureSignals:
    host: str
    page_url: str
    page_timestamp: str
    robots: FileState
    tdmrep: FileState
    headers: dict = field(default_factory=dict)     # x-robots-tag, tdm-reservation as captured
    meta: list = field(default_factory=list)        # robots / tdm meta tags in the captured page
    restricts_ai: Optional[bool] = None             # True / False when known, None when unknown


def parse_robots(text: str, path: str) -> dict:
    """{agent: {"disallowed": bool for this path, "rules": [...]}} for the AI agents and "*", plus
    content_usage lines. Longest match wins between Allow and Disallow, as RFC 9309 says."""
    groups: list = []
    agents: list = []
    content_usage = []
    last_was_agent = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (s.strip() for s in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not last_was_agent:
                agents = []
                groups.append((agents, []))
            agents.append(value)
            last_was_agent = True
            continue
        last_was_agent = False
        if key == "content-usage":
            content_usage.append(value)
        elif key in ("allow", "disallow") and groups:
            groups[-1][1].append((key, value))

    def rules_for(agent: str) -> Optional[list]:
        for names, rules in groups:
            if any(n.lower() == agent.lower() for n in names):
                return rules
        return None

    def disallowed(rules: list) -> bool:
        best = None
        for kind, pattern in rules:
            if not pattern:
                continue
            regex = "^" + re.escape(pattern).replace(r"\*", ".*").replace(r"\$", "$")
            if re.match(regex, path) and (best is None or len(pattern) > len(best[1])):
                best = (kind, pattern)
        return bool(best and best[0] == "disallow")
    star = rules_for("*") or []
    out = {"*": {"disallowed": disallowed(star), "rules": star}}
    for agent in AI_AGENTS:
        rules = rules_for(agent)
        if rules is not None:
            out[agent] = {"disallowed": disallowed(rules), "rules": rules}
    return {"agents": out, "content_usage": content_usage}


def page_meta(html: bytes) -> list:
    out = []
    for m in META.finditer(html.decode("utf-8", errors="replace")):
        c = CONTENT.search(m.group(0))
        out.append({"name": m.group(1).lower(), "content": c.group(1) if c else ""})
    return out


class SignalReader:
    def __init__(self, get: Callable = fetch.get, get_response: Callable = fetch.get_response):
        self.get, self.get_response = get, get_response
        self._captures: dict = {}
        self._bodies: dict = {}

    def captures(self, url: str) -> list:
        """Every capture of a URL the archive holds: [{timestamp, digest, status}], oldest first."""
        if url not in self._captures:
            params = urllib.parse.urlencode({"url": url, "output": "json", "fl": "timestamp,digest,statuscode"})
            _, body = self.get(f"{CDX}?{params}")
            rows = json.loads(body.decode("utf-8") or "[]")
            self._captures[url] = [{"timestamp": r[0], "digest": r[1], "status": r[2]} for r in rows[1:]] if rows else []
        return self._captures[url]

    def body(self, url: str, ts: str) -> bytes:
        if (url, ts) not in self._bodies:
            _, data = self.get(RAW.format(ts=ts, url=url))
            self._bodies[(url, ts)] = data
        return self._bodies[(url, ts)]

    def file_state(self, url: str, ts: str, parse: Callable[[bytes], dict]) -> FileState:
        caps = self.captures(url)
        before = next((c for c in reversed(caps) if c["timestamp"] <= ts), None)
        after = next((c for c in caps if c["timestamp"] >= ts), None)
        if before is None or after is None or before["digest"] != after["digest"] or before["status"] != after["status"]:
            return FileState("unknown", before, after)
        if before["status"] != "200":
            return FileState("absent_in_effect", before, after)
        return FileState("in_effect", before, after, parse(self.body(url, before["timestamp"])))

    def for_capture(self, page_url: str, ts: str) -> CaptureSignals:
        parts = urllib.parse.urlsplit(page_url if "://" in page_url else "http://" + page_url)
        host = parts.hostname or ""
        path = parts.path or "/"
        robots = self.file_state(f"{host}/robots.txt", ts, lambda b: parse_robots(b.decode("utf-8", "replace"), path))
        tdmrep = self.file_state(f"{host}/.well-known/tdmrep.json", ts, lambda b: {"tdmrep": _json_or_text(b)})
        _, headers, html = self.get_response(RAW.format(ts=ts, url=page_url))
        captured = {k.replace("x-archive-orig-", ""): v for k, v in headers.items()
                    if k in ("x-archive-orig-x-robots-tag", "x-archive-orig-tdm-reservation", "x-archive-orig-tdm-policy")}
        meta = page_meta(html)
        sig = CaptureSignals(host, page_url, ts, robots, tdmrep, captured, meta)
        sig.restricts_ai = restricts_ai(sig)
        return sig


def _json_or_text(data: bytes):
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError:
        return data.decode("utf-8", "replace")[:2000]


def restricts_ai(sig: CaptureSignals) -> Optional[bool]:
    """True when any signal in effect restricts AI or TDM use of this page; False when every source
    is known and none does; None when any of robots.txt or TDMRep is unknown and nothing restricts."""
    found = False
    if sig.robots.state == "in_effect":
        agents = sig.robots.parsed["agents"]
        found |= any(a != "*" and v["disallowed"] for a, v in agents.items())
        # aipref: a usage category set to "n" (for example "train-ai=n") refuses it.
        found |= any(re.search(r"=\s*n\b", cu.lower()) for cu in sig.robots.parsed["content_usage"])
    if sig.tdmrep.state == "in_effect":
        entries = sig.tdmrep.parsed.get("tdmrep")
        found |= isinstance(entries, list) and any(isinstance(e, dict) and str(e.get("tdm-reservation")) == "1"
                                                   for e in entries)
    found |= any(h and ("noai" in h.lower() or h.strip() == "1") for h in sig.headers.values())
    found |= any(("noai" in m["content"].lower()) or (m["name"] == "tdm-reservation" and m["content"].strip() == "1")
                 for m in sig.meta)
    if found:
        return True
    if sig.robots.state == "unknown" or sig.tdmrep.state == "unknown":
        return None
    return False


def as_dict(sig: CaptureSignals) -> dict:
    return asdict(sig)
