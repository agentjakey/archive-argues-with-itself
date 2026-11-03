# Changelog

What changed for readers, newest first. Measurements behind each change are in
[docs/ACCURACY.md](docs/ACCURACY.md). Corrections and privacy-page changes are kept below, dated.

## 2.2.0 (2026-11-03): one question box for the whole collection

- The Ask page searches every part of the archive that has searchable text: the two collections that
  came first and every newly built part. The engine picks the parts that hold the question's words.
  Under the box, one line says how many documents answers can draw on, out of how many catalogued,
  read from the release's own data.
- The waiting screen names the parts of the archive that are waking for a question and waits for
  those alone. Before, a question could wait on parts it never needed until the site said the engine
  was down.
- The example questions are still the checked, recorded ones and answer instantly.
- The exhibit has the same light and dark switch as the site; kiosks stay dark and store nothing. On
  a kiosk, a screen taller than its frame now scrolls inside it, so Gap Hunt's last rows are never under
  the footer (found by the 5.5-hour soak test).
- A reranker can be switched on in the engine. Whether it ships was decided by a test written down in
  advance; see [ACCURACY.md](docs/ACCURACY.md).
- Docs: one index by reader ([docs/README.md](docs/README.md)); older documents moved to
  [docs/archive](docs/archive/).

## 2.1.0 (2026-11-03): the reading room, redesigned around search

- The opening screen is one heading and one search box, with example topics under it. Every example is
  a recorded answer that cites at least two scanned pages.
- One header on every page (Ask, Explore, Exhibit, How it works) and a light theme beside the dark
  one. The site follows your device until you pick; that one choice stays in your browser.
- Results keep the question box at the top, with Copy link, Print and Copy citations.
- The catalogue's title search comes first, takes words from the home page, can search every decade,
  and keeps its filters in the link.
- Correction: the site said answers are written by Anthropic's Claude. Since 2026-11-02 they are written
  by GLM-5.3 on Cloudflare Workers AI. The privacy page now says so.

## 2.0.0 (2026-11-02)

- Answers carry one of six evidence states (supported, partly supported, conflicting, not comparable,
  not enough evidence, restricted) and are written by GLM-5.3, an open-weight model, from keyword
  search. It shipped only after passing a rule fixed in advance on 839 fresh questions: the right page
  in the first ten 12.9 points more often, answerable questions refused 9.1 points less often.
- The whole collection: a catalogue of every record at /catalogue/, a full-text fetch, and parts built
  and audited one by one before they serve.
- The exhibit at /exhibit/ and /kiosk: date a page, compare two records, the Time Dial, group play.

## 2026-10-31: on Cloudflare

- The site became a static release that works while the engine sleeps; the engine wakes on a question
  and the site shows how far it has got. Every release is checked before it goes live; rollback is one
  command. The old Railway address redirects here.
- Public pages for About, Privacy, Terms of use, Accessibility, and Corrections and care.
- Visitors' questions are not stored as text; their answers expire after 90 days. A question with an
  email address or phone number in it is never stored.

## October 2026: the first version (tag v1.0.1-festival)

- A federal public-health pilot (3,477 documents, 1960 to 2009) and a national collection (13,539
  documents, 1963 to 2018), each audited by hand: 93.3% and 98.0% of sentences fully supported by the
  page they cite.
- Page-level citations, a refusal when the record is thin, a coverage view by decade, and featured
  pairs of pages years apart.
- A care layer for records that describe harm, and an offline exhibit for the October 2026 festival.

## Corrections

Stored model answers are never edited; a correction to an answer is a dated note shown beside it.
The notes the site shows live in `config/editorial_notes.json`.

### 2026-11-03: who writes the answers

The privacy page, the About page, the footer and the line beside every answer said answers are written
by Anthropic's Claude. Since 2026-11-02 live answers are written by GLM-5.3 on Cloudflare Workers AI;
the recorded example answers were written earlier by Claude Haiku 4.5, and each names its model.

### 2026-10-29: story questions, captions and placement

- The Alberta story asked how health insurance coverage changed between the 1970s and 1990s. Its two
  pages describe different programs and cannot show a change. It now asks what the two records say,
  with dated notes on the story and its answer, and is no longer featured on the landing or the kiosk.
- The federal aging story and the microlog immunization story are no longer featured: one was an
  evaluation question the audit counted off-target, and the other's pages are not what its question
  asked about.
- Three captions read pages from different provinces as one sequence. They now say what each page is.
- Every story carries a comparability block, and a test fails if a caption claims more than it allows.

### 2026-10-27: Alberta story caption

The caption called the 1974 and 1998-99 pages records "from the same insurance plan". They describe
different programs. The caption, the README image description and the landing label were corrected.

## Privacy page changes

- 2026-11-03: answers are written by GLM-5.3 on Workers AI (was: Anthropic). A light or dark choice,
  made only if you pick one, is kept in your own browser.
- 2026-11-01: the Turnstile row says what the engine sends to verify a check: the one-time token and
  your IP address, to Cloudflare. This was already the behaviour; the page did not say it.
- 2026-10-31: answers to visitors' questions kept 90 days instead of 180.
