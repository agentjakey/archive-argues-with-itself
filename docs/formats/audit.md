# Audit pipeline files

The audit pipeline (`src/archive_debugger/audit/`) hands each step's output to the next as a plain
file. All JSON Lines files are UTF-8, one JSON object per line, keys sorted. A change to any format
here changes every reader and writer in the same commit.

Run outputs live under `reports/v2/audit/runs/<run id>/`; the spend ledger is
`reports/v2/audit/ledger.jsonl`; the calibration kit and labels are under
`reports/v2/audit/calibration/`.

## Units of judgment

VALID, SUPPORTS and IN SCOPE are judged per sentence: a sentence item. ANSWERS is judged once per
answer: an answer item.

## Collection config (`config/collections/<name>.toml`)

One per sub-collection. Every audit module reads its collection from here and none names one in
code (a test checks).

| Key | Meaning |
| --- | --- |
| `[collection] name` | the collection's name, used in item ids |
| `scope` | the scope in `config/scopes.toml` whose corpus database the gates read (read-only) |
| `label`, `languages` | for reports |
| `period` | `[first_year, last_year]` of the dated window |
| `jurisdictions` | the jurisdiction vocabulary |
| `[v1] worksheet` | the v1 audit worksheet: kept sentences with the full text of their cited passages |
| `answers_index` | recorded v1 answers (site data format); they give each answer's retrieved evidence |
| `writer_model` | the model that wrote the answers; the panel never includes it for them |
| `labels`, `labels_kind` | the v1 author decisions: `by_question` (`{qid: {sentence_no: label}}`) or `worksheet_field` (the worksheet's `judgment`) |
| `label_map` | raw label to `pass`, `partial` or `fail` |

## Audit config (`config/audit.toml`)

`[panel] judges` (two judges from two model families), `escalation`, `candidates` (run alongside to
choose the panel by calibration; their verdicts never decide anything), `review_share` (the share of
agreed passes the escalation judge re-reads in every run) and `lenient_above` (the disagreement on
that sample that flags a check). A run is refused when a panel or escalation judge uses the model
that wrote the answers. `[gateway] workers_ai` names the AI Gateway that Workers AI calls go
through (empty: direct). Each `[judges.<name>]` gives `provider` (`anthropic` or `workers-ai`),
`model`, `family`, `max_tokens`, and optionally `batch`, `effort` (Anthropic) or
`reasoning_effort` (Workers AI), and `prompt` (`panel`, the default, or `reference`). Every model
must have a price in `audit/prices.py`.

`[reference] judges` names the reference judges: two models from two families, none of them a panel,
escalation or candidate judge. They read the author's labelling guide and worked examples, the full
page text (no cap) and may reason before answering, under their own prompt version
(`REFERENCE_PROMPT_VERSION`). Where both agree, that is the silver label (see Silver labels below).

`[budget] phase` names the current phase and `[budget.caps]` its hard cap in US dollars.

## Judge item (`items.jsonl`, `kit.jsonl`)

| Field | Meaning |
| --- | --- |
| `format` | 2 |
| `kind` | `sentence` or `answer` (an item without `kind` is a sentence item) |
| `item_id` | `<collection>:<qid>:s<sentence number>` for a sentence, `<collection>:<qid>:answer` for an answer |
| `collection`, `qid`, `question`, `filters` | the question as asked |
| `answer_text` | the whole answer |
| `writer_model` | the model that wrote the answer |
| `source`, `generated_at` | where the answer came from and when it was written |

A sentence item adds `sentence_no`, `sentence`, `citations` (each cited passage: `passage_id`,
`item_id`, `title`, `year`, `jurisdiction`, `leaf_index`, `printed_page`, `deep_link`, `text`, the
full passage text) and `retrieved_ids` (the passages the model was given for this answer, or null
when not recorded). An answer item adds `sentences`, the answer's sentences in order.

A kit item adds `kit_position`, `kit_batch`, `kit_version` and `kit_format` (2). The kit is ordered
answer by answer: the answer item, then that answer's sampled sentences; a batch never splits an
answer. People's labels are never in an item.

## Gate result (`gates.jsonl`)

`item_id`, `gate_version`, `valid` (`pass`, `fail`, `unrecorded` when the page resolves but the
answer's retrieved evidence was not recorded, or `not_applicable` for an answer item), `citations`
(per passage: `exists`, `text` (`exact`, `ascii_folded`, `differs`), `text_matches`, `page_link`,
`in_retrieved`), `quotes` (each quoted span of three words or more and whether it is on a cited
page), `years` (each year in the sentence, on the page or the page's own year), `flags`
(`quote_not_on_page`, `year_not_on_page`).

## Judgment (`judgments.jsonl`)

One record per item per judge call: `item_id`, `kind`, `judge`, `provider`, `model`, `family`,
`prompt_style` (`panel` or `reference`; absent means `panel`), `prompt_version`, `batch`, `verdicts` (null when the call failed or the reply could not be read),
`error`, `input_tokens`, `output_tokens`, `usd`, `cached` (true when the AI Gateway answered from
its cache: not billed, `usd` 0), `at`.

`verdicts` for a sentence item: `supports` `{verdict: pass|partial|fail, reason}` and `in_scope`
`{verdict: pass|fail|unclear, period, jurisdiction, population, program, measure, reason}`, each
constraint `fits`, `differs`, `unclear` or `not_asked`. For an answer item: `answers` `{verdict:
pass|partial|fail, reason}`. A judgment counts only under the current `prompt_version`; the last
record for an item and judge wins.

## Panel decision (`panel.jsonl`, `human_queue.jsonl`)

`item_id`, `kind`, `panel_version`, `valid`, `flags`, `checks` (the item's checks, each with the
`final` verdict or null, `route` `agree`, `escalated` or `human`, `votes` by judge), `human_queue`
(the checks left to a person).

## Spend ledger (`ledger.jsonl`)

`kind` `spend` (`run_id`, `provider`, `model`, `batch`, `input_tokens`, `output_tokens`, `usd`,
`what`), `reserve` (`reservation`, `usd`: the worst case of a call or batch in flight) or `release`.
Every entry has `at`, `price_version` and `phase` (entries written before the field existed are
`phase2`). Committed spend is spend plus open reservations; no call is made that could take either
the run's cap or the current phase's cap (`[budget.caps]`) past its limit.

## Calibration labels (`labels.jsonl`, `labels_relabel_<seed>.jsonl`)

One line per save, the last for an item wins: `item_id`, `kind`, the item's checks (`supports` and
`in_scope` for a sentence, `answers` for an answer, same classes as the verdicts), `note`, `labeler`
(`author`), `review` (`author-reviewed`), `mode` (`first` or `relabel`), `kit_version`,
`labeled_at`. `kit.json` beside the kit records how it was drawn: seed, sentence and answer counts,
batch sizes, strata, the sentences always included, and the strata of the first 150 sentences.

## Run report (`report.json`, `report.md`)

Sentence and answer items by collection, VALID counts and gate flags, each judge's verdict counts,
errors, gateway cache hits, spend and tokens, the panel's final verdicts and routes per check, the
leniency review (per check: agreed passes re-read, how many the escalation judge did not pass, the
rate with its 95% interval, and the flag), spend by provider for the run and the phase, cost per
judged sentence (panel and escalation; everything in the run), and agreement with the v1 SUPPORTS
decisions (`audit/calibration.py` `compare`).

## Silver labels (`reports/v2/audit/reference/silver_kit.jsonl`, `silver_approval.jsonl`)

One row per item (`audit/silver.py`, `scripts/v2/silver_labels.py build`): `format` (1), `item_id`,
`kind`, `collection`, `category` (benchmark items), `references` (the reference judges), `checks`
(per check: `silver`, the class both references gave, or null when they disagree or one gave no
verdict, and `votes` by judge), `agreed` (every check has a silver label), `labeler` (`silver`),
`review` (`reference-judges`). `silver_labels.jsonl` holds the same labels in the calibration labels
format, for the calibration report. `silver_summary.json` counts agreement per check.

## Author review queue (`reports/v2/audit/review/queue.jsonl`, `queue.json`, `labels.jsonl`)

`queue.jsonl` is in the kit format the calibration form opens (kit items and benchmark approval
items, renumbered `kit_position`, `kit_batch` = section number, `kit_version` = queue version,
`queue_format` 1). At most 80 items: every reference disagreement on the kit, then a seeded random 40
of the agreed kit items, then up to 20 benchmark approval items, flagged ones first. `queue.json`
records the seed, the counts and each item's section; the form never shows the section. The author's
labels go to `labels.jsonl` beside it in the calibration labels format. `status.json` and
`status.md` (`silver_labels.py recompute`) hold the panel's agreement with reference labels, against
the best labels (the author's where present, silver elsewhere), against the author on the random 40,
the silver labels' per-item error on the random 40 with its Wilson interval, and each check's status
(`AGREEMENT-WITH-REFERENCE-ONLY` until the random 40 are labelled; then `AI-AUDITED` only when the
panel meets the bar and the silver error's upper 95% bound is at most 10%, else `HUMAN-REVIEWED`).
