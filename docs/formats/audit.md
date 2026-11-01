# Audit pipeline files

The audit pipeline (`src/archive_debugger/audit/`) hands each step's output to the next as a plain
file. All JSON Lines files are UTF-8, one JSON object per line, keys sorted. A change to any format
here changes every reader and writer in the same commit.

Run outputs live under `reports/v2/audit/runs/<run id>/`; the spend ledger is
`reports/v2/audit/ledger.jsonl`; the calibration kit and labels are under
`reports/v2/audit/calibration/`.

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
| `labels`, `labels_kind` | the v1 author decisions: `by_question` (`{qid: {sentence_no: label}}`) or `worksheet_field` (the worksheet's `judgment`) |
| `label_map` | raw label to `pass`, `partial` or `fail` |

## Audit config (`config/audit.toml`)

`[panel] judges` (two judges from two model families), `escalation`, `candidates` (run alongside to
choose the second judge by calibration; their verdicts never decide anything). Each
`[judges.<name>]` gives `provider` (`anthropic` or `workers-ai`), `model`, `family`, `max_tokens`,
and optionally `batch`, `effort` (Anthropic) or `reasoning_effort` (Workers AI). Every model must
have a price in `audit/prices.py`.

## Judge item (`items.jsonl`, `kit.jsonl`)

One kept answer sentence.

| Field | Meaning |
| --- | --- |
| `format` | 1 |
| `item_id` | `<collection>:<qid>:s<sentence number>` |
| `collection`, `qid`, `question`, `filters` | the question as asked |
| `sentence_no`, `sentence` | the sentence judged |
| `answer_text` | the whole answer, for context |
| `citations` | each cited passage: `passage_id`, `item_id`, `title`, `year`, `jurisdiction`, `leaf_index`, `printed_page`, `deep_link`, `text` (full passage text) |
| `retrieved_ids` | the passages the model was given for this answer, or null when not recorded |
| `source`, `generated_at` | where the answer came from and when it was written |

A kit item adds `kit_position`, `kit_batch` and `kit_version`. People's labels are never in an item.

## Gate result (`gates.jsonl`)

`item_id`, `gate_version`, `valid` (`pass`, `fail`, or `unrecorded` when the page resolves but the
answer's retrieved evidence was not recorded), `citations` (per passage: `exists`, `text` (`exact`,
`ascii_folded`, `differs`), `text_matches`, `page_link`, `in_retrieved`), `quotes` (each quoted span
of three words or more and whether it is on a cited page), `years` (each year in the sentence, on
the page or the page's own year), `flags` (`quote_not_on_page`, `year_not_on_page`).

## Judgment (`judgments.jsonl`)

One record per item per judge call: `item_id`, `judge`, `provider`, `model`, `family`,
`prompt_version`, `batch`, `verdicts` (null when the call failed or the reply could not be read),
`error`, `input_tokens`, `output_tokens`, `usd`, `at`.

`verdicts`: `supports` and `answers` each `{verdict: pass|partial|fail, reason}`; `in_scope`
`{verdict: pass|fail|unclear, period, jurisdiction, population, program, measure, reason}`, each
constraint `fits`, `differs`, `unclear` or `not_asked`. A judgment counts only under the current
`prompt_version`; the last record for an item and judge wins.

## Panel decision (`panel.jsonl`, `human_queue.jsonl`)

`item_id`, `panel_version`, `valid`, `flags`, `checks` (per check: `final` verdict or null, `route`
`agree`, `escalated` or `human`, `votes` by judge), `human_queue` (the checks left to a person).

## Spend ledger (`ledger.jsonl`)

`kind` `spend` (`run_id`, `provider`, `model`, `batch`, `input_tokens`, `output_tokens`, `usd`,
`what`), `reserve` (`reservation`, `usd`: the worst case of a call or batch in flight) or `release`.
Every entry has `at` and `price_version`. Committed spend is spend plus open reservations; no call
is made that could take either the run's cap or the phase cap ($25) past its limit.

## Calibration labels (`labels.jsonl`, `labels_relabel_<seed>.jsonl`)

One line per save, the last for an item wins: `item_id`, `supports`, `answers`, `in_scope` (same
classes as the verdicts), `note`, `labeler` (`author`), `review` (`author-reviewed`), `mode`
(`first` or `relabel`), `kit_version`, `labeled_at`. `kit.json` beside the kit records how it was
drawn: seed, size, strata, the items always included, and the strata of the first 150.

## Run report (`report.json`, `report.md`)

Items and answers by collection, VALID counts and gate flags, each judge's verdict counts, errors,
spend and tokens, the panel's final verdicts and routes per check, spend by provider for the run and
the phase, cost per judged item (panel and escalation; everything in the run), and agreement with
the v1 SUPPORTS decisions (`audit/calibration.py` `compare`).
