# Batch job format

A batch job (embed, ocr, judge or compile) is described once in `config/jobs/<name>.toml`. The same
spec runs on any of three executors: this machine's CPU, Workers AI (where the model exists there),
or Kubernetes. Code: `src/archive_debugger/jobs/`, CLI: `scripts/v2/jobs.py`. Running it on a
cluster is described in [CLUSTER.md](../CLUSTER.md).

## Spec

| Section | Fields |
|---|---|
| `[job]` | `name`, `kind` (`embed`, `ocr`, `judge` or `compile`), `code_version`. Bump `code_version` whenever the job's code changes its output |
| `[input]` | `prefix`: where the prepared units live in the store |
| `[output]` | `prefix`: outputs go to `<prefix>/<name>/<build_key>/` |
| `[model]` | `name` and `licence`. A spec without a licence is refused. No non-commercial or no-redistribution model is used |
| `[params]` | the job's settings, for example `index_spec`, `batch`, `engine` or `max_tokens` |
| `[executor.local]`, `[executor.workers_ai]`, `[executor.k8s]` | which executors the job runs on, and their settings (backend, model id, endpoint, `gpu`). A paid endpoint must also give `run_cap_usd` and `price_model` |

The **build key** is a hash of the kind, the code version, the model, the parameters and the input
fingerprint (the sha256 of the input's `units.jsonl`). Changing any of these writes to a new folder,
so a run never mixes with an earlier one.

## Store layout

```
<input prefix>/units.jsonl                one unit per line: {"id", ...}
<input prefix>/shards|pages|items|units/  each unit's input files
<output prefix>/<name>/<build key>/units/<id>.<ext>        a unit's output
<output prefix>/<name>/<build key>/units/<id>.done.json    {unit, key, sha256, bytes, executor, model, backend, seconds, finished_at}
<output prefix>/<name>/<build key>/manifest.json           every unit's output, written once all are done
```

A unit counts as done only when its `done.json` exists and the output it names still has that
sha256. If a job crashes between writing the output and writing `done.json`, the unit is run again,
and running it again writes the same key. Worker `i` of `n` takes every unit whose position modulo
`n` is `i`, which is how a Kubernetes Indexed Job shares the units out.

`manifest.json` holds `job`, `kind`, `code_version`, `build_key`, `input_fingerprint`, `model`,
`params`, `units` (`{id: {key, sha256, bytes, executor, model, backend}}`), `complete`, `missing`,
`written_at` and `store`. `scripts/v2/jobs.py verify` reads every output back and checks its sha256.

## Outputs by kind

| Kind | Output per unit |
|---|---|
| `embed` | `<id>.npz` with `matrix` (rows in input order, in the index spec's dtype, unit length when the spec normalizes) and `ids` (the passage ids). The index spec is `config/jobs/index_spec.toml` |
| `ocr` | `<id>.jsonl`, one page per line: `page_ref`, `old_text`, `new_text`, `engine`, `engine_version`, `seconds`, `proxy` (`{old, new}`). The old text is always kept |
| `judge` | `<id>.jsonl`, one judgment per audit item: `item_id`, `kind`, `verdicts` (or `null`), `error`, `model`, `endpoint`, `prompt_version`. A reply that cannot be read is an error, never a pass |
| `compile` | `<id>.jsonl.gz`: an `item` line per document, then its `page` and `passage` lines in the corpus's own format, or a `skipped` line with the reason |
