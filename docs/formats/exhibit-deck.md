# Exhibit deck format (`exhibit-deck/1`)

A deck is the set of rounds the library exhibit plays: Same or Not?, When Was This?, the Time Dial,
and the Gap Hunt grid. It is one JSON file, built offline by `scripts/v2/exhibit_deck.py` and
published inside a site release by `scripts/v2/build_release.py`. The exhibit app only reads decks.
It never calls a model and never changes a round.

## Where it lives in a release

| Path | What | Caching |
|---|---|---|
| `exhibit/index.html`, `exhibit/assets/*` | the static app | page revalidated, assets for a year |
| `exhibit/decks/<deck_id>-<sha12>.json` | the deck, named by its content | for a year |
| `exhibit/current-deck.json` | `{"deck": "<file>", "deck_id", "sha256"}`: the deck the app plays | revalidated |

A new deck goes live by moving the pointer in a new release. Rolling back the release rolls back
the deck. The source of the published deck is `site/exhibit/deck.json`.

## Top level

| Field | Meaning |
|---|---|
| `format` | `"exhibit-deck/1"` |
| `deck_id` | the deck's name, such as `starter-1` |
| `built_at` | UTC time the deck was built |
| `builder_version` | the version of the builder's refusal checks |
| `settings` | `collections`, `dial` (`[first_year, last_year]`), `idle_reset_seconds`, `offline_image_cache`, `panel_calibrated`, `review_label` (`{en, fr}`: how the deck's rounds were checked, shown with each round until a person has reviewed them) |
| `counts` | rounds per mode |
| `rounds` | the rounds, described below |
| `gap_hunt` | the Gap Hunt grid, or `null` |

## A round

Every round has these fields:

| Field | Meaning |
|---|---|
| `id` | `son-...`, `wwt-...` or `dial-...`. For Same or Not? and When Was This? it is a hash of the page references |
| `mode` | `same_or_not`, `when_was_this` or `time_dial` |
| `level` | 1 for the first round of a mode's lesson, otherwise 2 |
| `collection` | the collection config (`config/collections/<name>.toml`) the pages come from |
| `pages` | the pages the round shows (below) |
| `quotes` | `{id, page_ref, role, text}`. The role is `claim`, `decisive`, `clue` or `evidence` |
| `play` | what the visitor plays (below, by mode) |
| `explanation` | `{en, fr}` |
| `explanation_status` | `model-drafted`, `author-reviewed` or `author-edited` |
| `care_flags` | always empty in a published deck. A round with a care flag is refused |
| `status` | `model-reviewed`, `ai-adjudicated` or `author-reviewed` in a published deck. The builder also uses `draft`, `refused`, `flagged`, `ai-rejected` and `author-rejected` |
| `checks` | `{builder_version, refusals, checked_at, fingerprint}`. `refusals` is empty in a published deck |
| `review` | `{panel, panel_calibrated, panel_prompt_version, reviewer, flags, author, adjudication}` (below) |
| `provenance` | `{drafted_by, prompt_version, drafted_at, draft_kind, edits}` |

### A page

| Field | Meaning |
|---|---|
| `ref` | `item_id#leaf`: the Internet Archive item and the page's leaf number. Passage citations elsewhere use `item_id#leaf:n` |
| `item_id`, `leaf`, `collection` | where the page is |
| `title`, `issuer`, `jurisdiction`, `language` | from the catalogue record, normalized by the collection's build |
| `catalogue_date` | `{year, raw, method}`: the catalogue's date, never overwritten |
| `page_date` | `{year, method, page_ref, line}`: a year read from the document itself. `method` is `read_from_page`, `read_from_front_matter` (the item's leaves 0 to 5) or `not_found`. `line` is the text around the year, exactly as on `page_ref` |
| `date_verified` | `true` when the catalogue year (normalized `exact`) equals the year read from the document and `line` is on `page_ref`. A published round carries only verified pages |
| `date_verification` | `catalogue_and_page_agree` or `unverified` |
| `text` | the page's own text, as the scanner read it. A long page is cut at line breaks around the quoted lines |
| `text_cut` | whether `text` is part of a longer page |
| `text_sha256` | sha256 of the full page text folded to ASCII words: the builder's check that the page has not changed |
| `passage_ids` | the page's passages in the corpus |
| `details_url` | `https://archive.org/details/<item>/page/n<leaf>`: the original page |
| `image_url`, `thumb_url` | archive.org's image service for that page. Images are never re-hosted |
| `qr` | `{size, path}`: a QR code for `details_url` as one SVG path, for the evidence card |

### `play` by mode

**Same or Not?**

- `claims`: two entries, each `{page_ref, quote, text: {en, fr}}`, one claim from each page, backed by a `claim` quote.
- `answer`: one of `same_thing_changed`, `real_disagreement`, `not_comparable` or `not_enough_evidence`.
- `decisive`: the ids of the quotes that settle the answer. The reveal marks them on the pages.
- `constraints`: for each of `period`, `jurisdiction`, `population`, `program` and `measure`, one of `same`, `differs` or `unclear`.
- `mined_as`: how the pair was found (the shared phrase, and whether it was a `change` or `compare` pair).

**When Was This?**

- `year`: the scored year. It must equal the page's verified catalogue year.
- `label`: `{en, fr}`, a neutral name for the kind of document that does not give the year away.
- `clues`: ids of `clue` quotes. No clue contains a year.
- `masked_text`, `masked_title`: character spans in `text` and `title` hidden until the guess. These are every year and year range.

Points go by closeness: 100 for the exact year, 10 fewer for each year off. Only cards with a verified date are scored.

**Time Dial**

- `question`: `{en, fr}`.
- `question_id`, `jurisdiction`: as written in `exhibit/decks/starter/time_dial.toml`.
- `epochs`: `{year, state, answer: {en, fr}, quotes, pages_by_then}`, one for every year in which a page of the round was published. Each was drafted from the pages in `pages_by_then` and no others: the round's pages published by that year. `state` is `answer` or `insufficient`.
- `years`: `{year, state, items}` for every dial year. `state` is `recorded` (`items` indexed items mention the question's terms), `quiet` (indexed, and none mention them) or `not_indexed` (outside the collection's period, so nothing can be said).
- `collection_period`: the collection's first and last year.

### `review`

- `panel`: each audit panel judge's verdicts on `supports`, `answer_correct` and `fair_to_visitor` (`pass`, `partial`, `unsure` or `fail`), plus `needs_person` and `notes`.
- `panel_calibrated`: `false`. No calibration covers exhibit rounds yet. The exhibit says on screen that the AI judges' accuracy has not been measured.
- `reviewer`: `{model, verdicts, prompt_version, date}`. This is the strongest Claude model the account could call, reading the whole round. It also gives `french_ok` and `year_is_publication`.
- `flags`: why a person must look at the round. A flagged round is not published until a person approves it or an adjudication approves or fixes it.
- `adjudication`: `{decision, reason, reviewer, date, label}` when a flagged round was decided by the strongest model reading it against its page text, before any person did. `decision` is `approve`, `fix` or `drop`, and `reason` is written out. A fixed round lists each change in `provenance.edits`, passes the builder's checks again and gets a new `checks.fingerprint` (the one it was read at is `checks.adjudicated_from`). Its status is `ai-adjudicated`; a dropped round is `ai-rejected`. A person's decision always replaces an adjudication.
- `author`: `{decision, date, notes, reviewer}` when a person reviewed the round. The decision was recorded against the round's `checks.fingerprint`, so a round that changed afterwards needs reading again.

The panel never includes the model that drafted the round. While Sonnet 5.5 drafts, the reviewer model takes the place of the escalation judge.

## Gap Hunt

- `decades`, `jurisdictions`: the grid's columns and rows.
- `cells`: `{place, iso, decade, catalogue_items, indexed_items, state}`.
  - `catalogue_items` counts items in Internet Archive Canada's government publications collection whose publisher or creator names the place. These come from count-only searches of the public search API on the date in `catalogue.fetched_at`.
  - `indexed_items` counts the items this project has indexed with that jurisdiction and a catalogue year in the decade.
  - `state` is `recorded`, `not_indexed` (the catalogue has items, none are indexed), `quiet_examined` (both counts are zero) or `unknown`.
- `catalogue`: `{api, base, fetched_at, method, total}`.
- `indexed_collections`: each indexed collection's period.
- `unknown_place_indexed`: indexed items with no readable place. They are not on the grid.

The place count is lexical. It misses issuers that do not name the place and counts some items that name it in passing. Not indexed is never shown as missing, and a quiet cell never claims that nothing was published.

## What refuses a round

The builder (`src/archive_debugger/exhibit/deck.py`) checks every round against the collection's
corpus. The release gate (`src/archive_debugger/exhibit/release.py`) checks it again against the
published text. A round is refused when any of these holds:

- a page does not resolve to text in the collection, or its text changed;
- a quote is not on its page, or not in the text the round shows;
- a page's date is not verified, or a When Was This? year is not the page's verified year;
- the round touches an excluded care topic (`config/exhibit.toml [care]`). That covers every care tier the reading room flags, Indigenous context until Internet Archive Canada answers the care question, a list of harm-related terms, and period terms that are now offensive;
- the round is not in this format.

Refused rounds go to the builder's rejected file with their reasons. They never reach a visitor.
