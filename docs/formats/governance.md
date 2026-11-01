# Governance policy records

A policy record says that a legitimate authority restricts how some records may be used. The engine
reads the register before retrieval, before generation and before export, and a restricted record is
never retrieved, quoted, summarized or exported against its policy. The register is empty by default:
nothing in this project infers a restriction or a cultural label from a record's text or metadata, and
a Local Contexts label is shown only when a policy record carries it.

## Register (`config/governance/policies.jsonl`)

JSON Lines, UTF-8, one record per line. Empty file or no file: no restrictions.

| Field | Meaning |
| --- | --- |
| `format` | 1 |
| `policy_id` | stable id, unique in the register |
| `targets` | what it applies to: `{"items": [archive.org identifiers], "collections": [collection names]}` (either may be empty) |
| `restrict` | the uses refused: any of `retrieve` (never returned as evidence), `generate` (never given to a model or quoted in an answer), `export` (never in an export, a static file or a stored answer) |
| `authority` | who set it, in their own words, as recorded by the person who entered it |
| `basis` | why, in a sentence: the agreement, protocol or request it comes from |
| `contact` | where a reader can ask about it (may be empty) |
| `display` | what a reader sees: `label` (short text), `local_contexts` (`null` or `{project_id, label_ids, label_names}` copied from the authority's Local Contexts project; never made up) |
| `entered_by`, `entered_at` | the person who entered the record and when (ISO 8601) |
| `fixture` | `true` only for synthetic test records; a fixture is never loaded by a production engine |

## Fixtures (`tests/fixtures/governance/`, benchmark items)

Synthetic records used by tests and by the benchmark's `restricted` category. Their authority is
always "Synthetic test authority (fixture, not a real restriction)", their `fixture` is true, and they
name no real community, nation or organization. The production loader refuses a register that holds
a fixture, and the fixture loader refuses one that does not.

## What a reader sees

An answer whose question reaches restricted records gets the verdict RESTRICTED: it says that some
records matching the question are restricted, by whom (`authority`) and why (`basis`), shows the
`display.label` and, when present, the Local Contexts labels, and links nothing from the restricted
records' text. Records outside the policy are answered as usual.
