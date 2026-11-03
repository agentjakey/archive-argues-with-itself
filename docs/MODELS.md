# Models

Every model the project uses or has considered, one card per role. Each card gives the model's
licence, the hardware it needs, what was measured on this project's own checks, and its cost per
1,000 answers. A number with no measurement behind it is marked as an assumption or left out.
Licences must be compatible with this MIT repository. Non-commercial terms, no-redistribution terms
and revenue caps are flagged, and a model under such terms is not used. Checked on 2026-11-01.

## Writer: drafts the answer from retrieved passages

| Model | Licence | Hardware | Measured on our checks | Cost per 1,000 answers |
|---|---|---|---|---|
| Claude Haiku 4.5 (in production) | Anthropic API terms (not open weights) | API | Strict support on the frozen benchmark (see [ACCURACY.md](ACCURACY.md)) | $7.20, measured: 10 answers in the bounded run averaged 5,088 input and 421 output tokens |
| Mistral Small 4 (119B, 2603) | Apache-2.0 (model card) | One 96 GB GPU in NVFP4, or two 80 GB GPUs with tensor parallelism | Not measured: no GPU yet | Marginal on a donated GPU; not stated for a rented one |
| gpt-oss-120b | Apache-2.0 | One 80 GB GPU (model card) | Not measured as a writer here | As above |
| Ministral 3 14B Instruct (2512) | Apache-2.0 | One 24 GB GPU in FP8 (model card) | Not measured | As above |

The three open-weight writers run from presets in `k8s/values.example.toml`. Each preset uses its
model card's own vLLM flags, plus our request limits. The engine calls a served model as an
OpenAI-compatible provider through an outbound Cloudflare Tunnel ([CLUSTER.md](CLUSTER.md)).

None is used until it is measured on the benchmark's checks: VALID, SUPPORTS, ANSWERS and IN SCOPE,
plus abstention.

## Judge: checks each cited sentence (the audit panel)

| Model | Licence | Hardware | Measured on our checks | Cost per 1,000 answers |
|---|---|---|---|---|
| Claude Haiku 5.5 | Anthropic API terms | API | Calibrated against people's labels per model and prompt version; the current figures and whether each judge meets the bar are in [ACCURACY.md](ACCURACY.md) | About $5.20 for the whole panel, measured: the bounded run's audit of 10 answers (53 items) cost $0.052 |
| gpt-oss-120b on Workers AI | Apache-2.0 | Workers AI (or one 80 GB GPU) | As above | Included in the panel cost above |
| Claude Fable 5.1 (reviewer, exhibit rounds) | Anthropic API terms | API | Not calibrated; exhibit decks say so | Not used on answers |

The panel never has the answer's writer as its only judge. Disagreements go to a stronger model,
then to a person. A judge is used only when it meets the bar set from the calibration set.

## Embedder: turns passages and questions into vectors for search

| Model | Licence | Hardware | Measured | Cost |
|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 (the first version's index) | Apache-2.0 | CPU | Embeds 29 to 33 passages a second on this laptop (bounded run). Passages longer than 128 tokens are cut | Free on CPU: about 323 hours for the whole collection's estimated 36 million passages |
| bge-m3 on Workers AI | MIT | Workers AI | Retrieval comparison (2026-11-02): the source page in the first ten for 97 of 160 questions, within noise of BM25 alone (93 of 160); BM25 alone measured best on the frozen test | $7.25 per million passages, measured on 2026-11-02 (inputs cut to 2,000 characters; noisy OCR runs about 1,300 tokens a passage): about $261 for the plan's 36 million passages, over the $150 embedding ceiling, so the whole collection is indexed BM25-only |

The index model is chosen by measurement (`config/jobs/index_spec.toml`); today the site searches by keywords alone. An embedding job may only use
the model the index names. A question's embedding costs a fraction of a cent.

## OCR: reads page images again where the old text is poor

| Engine | Licence | Hardware | Measured | Speed |
|---|---|---|---|---|
| The archive's existing text | as published | none | Lexicon proxy 0.676 on 24 of our worst pages | none |
| Tesseract | Apache-2.0 | CPU | Lexicon proxy 0.694 on the same pages | 2.7 s a page on CPU |
| docTR | Apache-2.0 | CPU or GPU | Lexicon proxy 0.806 (difference from the old text +0.061, 95% interval -0.012 to +0.127, 21 pages) | 16 s a page on CPU |
| PaddleOCR-VL-1.6 | Apache-2.0 | GPU | Not measured | none |
| olmOCR 2 (7B) | Apache-2.0 | GPU | Not measured | none |
| Chandra OCR 2 | **Not used.** Its weights are under a modified OpenRAIL-M licence that is free only below $2M in funding or revenue, and they may not be used to compete with the vendor's API | | | |

The lexicon proxy is the share of a page's words found in the collection's cleanest text. It is not
an error rate.

The choice will be made on 100 of our worst pages that a person has transcribed
(`scripts/v2/ocr_eval.py`):

- the character error rate, with a 95% interval;
- a hallucination check: an engine that adds three or more words the page does not have fails,
  whatever its error rate.

The old text is always kept beside the new.

## Reranker

None is used. No reranker has a measured case on this project's checks, and a new model needs one
before it is added.
