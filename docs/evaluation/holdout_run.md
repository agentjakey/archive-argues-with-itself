# Held-out run

2026-09-11T19:45:29+00:00 (UTC); provider anthropic, model claude-haiku-4-5-20251001; 15 questions from `eval/holdout_questions.jsonl`, one run, no sweep, no tuning.

- gold-abstain probes: 9/10 abstained; answered: h009
- gold-answerable: 4/5 answered; abstained: h015

| qid | gold | outcome | sentences | citations | uncovered terms | s |
| --- | --- | --- | ---: | ---: | --- | ---: |
| h001 | abstain | abstained | 0 | 0 | zika | 71.2 |
| h002 | abstain | abstained | 0 | 0 | mpox | 13.3 |
| h003 | abstain | abstained | 0 | 0 |  | 12.0 |
| h004 | abstain | abstained | 0 | 0 | vaping | 11.1 |
| h005 | abstain | abstained | 0 | 0 | semaglutide | 12.3 |
| h006 | abstain | abstained | 0 | 0 | 2000, 2020 | 9.3 |
| h007 | abstain | abstained | 0 | 0 | 2023 | 10.2 |
| h008 | abstain | abstained | 0 | 0 | edibles | 9.3 |
| h009 | abstain | answered | 2 | 2 |  | 12.4 |
| h010 | abstain | abstained | 0 | 0 | 2024 | 11.4 |
| h011 | answerable | answered | 2 | 3 |  | 12.5 |
| h012 | answerable | answered | 8 | 5 |  | 27.1 |
| h013 | answerable | answered | 4 | 1 |  | 18.1 |
| h014 | answerable | answered | 1 | 1 |  | 15.2 |
| h015 | answerable | abstained | 0 | 0 | federal | 10.0 |
