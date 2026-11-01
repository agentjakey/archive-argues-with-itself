# Adding a second source

The project's first source is Internet Archive Canada's government publications collection. Any
other source comes in through one adapter contract and one network module. This page says what an
adapter must provide and what the project checks.

## The contract

An adapter (`src/archive_debugger/sources/adapter.py`) yields records. Each record has:

| Field | Meaning |
|---|---|
| `archive` | the source, for example `wayback`. The registry stores its records as documents of that archive, never as part of the government publications collection |
| `identifier` | stable within the archive. For a web capture: `<timestamp>/<original URL>` |
| `locator` | where a reader opens it: the archived capture, never only the live URL |
| `original_url` | the address the page was captured from, when there is one |
| `title`, `text` | the visible title and text. Scripts, styles and markup are dropped. The text is evidence only: no link or instruction inside it is ever followed or obeyed |
| `publication` | a date the document states: `{year, value, method, evidence}`. The method is `read_from_page_meta` (a dcterms or dc.date field) or `read_from_page_text` (for example the federal web standard's "Date modified:" line), and the evidence is the field or line. When the page states none, the method is `not_found` |
| `capture` | when the archive captured the page, from the archive's own record (`archive_capture_timestamp`) |
| `licence` | as the source states it, or "unknown: the source states none" |

A record is refused, and not stored, when:

- it has no identifier or locator;
- its capture date is given as its publication date;
- its capture date did not come from the archive's record;
- it gives a publication year without the line it was read from.

In the registry, the publication date is a `derived` date with its evidence, and the capture date
is a `capture` date. The two are separate rows and neither overwrites the other
([formats/registry.md](formats/registry.md)).

## Fetching

`src/archive_debugger/sources/fetch.py` is the only code that fetches for a second source. A URL is
requested only when all of these hold:

- the scheme is https (http is upgraded);
- the host is on the allowlist exactly. Today the allowlist is `web.archive.org` and `archive.org`;
- the URL carries no credentials and no explicit port;
- the host is a name, not an IP address;
- the name does not resolve to a private, loopback, link-local or reserved address.

Redirects are not followed blindly. Each `Location` passes the same checks before it is requested,
at most five times. Bodies over 8 MB are refused. Requests are polite: an identified user agent, one
at a time, a pause, and backoff on 408, 429 and 5xx.

Tests (`tests/test_sources.py`) refuse, among others:

- `file:` and `ftp:` URLs;
- `user@host` tricks;
- explicit ports;
- `127.0.0.1`, `[::1]` and the cloud metadata address;
- look-alike hosts such as `web.archive.org.evil.example`;
- an allowed name that resolves to a private address;
- a redirect to a host off the allowlist. That host is never requested.

## The first second source (bounded)

`scripts/v2/second_source.py` takes Wayback captures of Health Canada's tobacco pages:

- the prefix `www.hc-sc.gc.ca/hc-ps/tobac-tabac/`;
- 2005 to 2010;
- successful HTML captures only, one per URL;
- at most 30.

They come from the Wayback CDX API and are stored in the registry as the archive `wayback`. On
2026-11-01, all 30 captures stated a modification date, and the capture came 0 to 3 years after it.

This is on staging only. Nothing from a second source is published, searched by the engine or cited
in an answer yet.

## Federated Internet Archive search

Searching the wider Internet Archive at question time is not built. Its full-text search endpoint
is undocumented and could change without notice. Its Terms of Use page could not be read by our
tools. A person must read the terms before any use.
