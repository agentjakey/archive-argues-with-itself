# Derived dates

A date read from a document's own pages, for documents the catalogue leaves undated. It is stored
apart from the catalogue date and never replaces it; the catalogue date, the date read from the
document and the capture date are separate fields.

## File (`reports/v2/dates/<collection>/derived_dates.jsonl`)

One line per undated item the reader could date:

| Field | Meaning |
| --- | --- |
| `item_id` | the archive.org identifier |
| `year` | the year read from the document |
| `method` | `copyright`, `imprint`, `fiscal`, `dated_line`, `title` or `year_mode` (src/archive_debugger/dates.py) |
| `confidence` | the label fixed before measurement (`high`, `medium`, `low`); see accuracy below before relying on it |
| `evidence` | the words the year was read from (at most 120 characters), or the title |
| `leaf` | the page it was read from (null for the title) |
| `method_version` | `dates-1` |

## Accuracy (`reports/v2/dates/accuracy.json`, `accuracy.md`)

Measured on a seeded sample of dated items with the catalogue year hidden: exact and within one year,
per method and per confidence label, with Wilson 95% intervals, and coverage. A reader-facing derived
date is shown with its method and the measured accuracy of that method, never with the confidence
label alone: on the first measurement the labels did not track accuracy (imprint, labelled high, was
right about half the time).
