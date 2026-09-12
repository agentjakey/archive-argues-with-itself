# Audit report

Five headline numbers, measured on the audit run: every seed question once through /ask with the
configured model (claude-haiku-4-5-20251001), final retrieval configuration, 50 questions: 40 answered, 10 abstained; sentence judgments by the author.

| # | number | value | source |
| --- | --- | --- | --- |
| 1 | Citation support, strict (supported only), kept sentences on the 35 gold-answerable questions | **93.3%** (166 of 178) | eval/judgments_phase16.json over reports/phase16/judgment_worksheet.jsonl |
| 2 | Citation support, lenient (supported + partly) | **99.4%** (177 of 178) | same |
| 3 | Abstention | in-sample: **10/15** gold-abstain abstained (5 answered off target); false abstentions **0/35**. held-out: **9/10** probes abstained (answered: h009); **4/5** answerable answered (abstained: h015) | this run; holdout_run.md; retrieval_report.md (sweep) |
| 4 | Retrieval recall@10 on the final gold, before -> after the retrieval changes | **0.3470 -> 0.4581** (recall@20 0.5928 -> 0.7276; nDCG@10 0.4174 -> 0.5082) | retrieval_report.md, final section |
| 5 | Cited passages resolving to a recorded page | **119/119 = 1.00** | every kept citation in the run re-checked with retrieve.citation.verify_citation |

In-sample means the 50 seed questions, which were used to amend the abstention rule (once) and to
label the gold the retriever was chosen on. Held-out means `eval/holdout_questions.jsonl`: 15 questions
written after the abstention rule and retrieval configuration were frozen, never used in any sweep or
design decision, verdicts assigned by the author before the single run.

## Disclosure

All labels and judgments were decided by the author. To speed adjudication, candidate labels for the Phase 13 extension and the Phase 16 support judgments were first proposed by an assistant model and each was reviewed and decided by the author; the same model family generates the tool's answers, so this judge is not independent of the system.

Judgment rule (`eval/judgments_phase16.json`, `_meta`): s = every factual claim in the sentence appears in
the cited passage text; p = a claim, date, or attribution is added or shifted; n = the sentence misstates
the passage. Reasons for every p and n: `eval/judgments_phase16_notes.md`.

## 1-2. Support, per question (35 gold-answerable)

| qid | sentences | supported | partly | not |
| --- | ---: | ---: | ---: | ---: |
| q001 | 5 | 5 | 0 | 0 |
| q002 | 6 | 6 | 0 | 0 |
| q003 | 12 | 12 | 0 | 0 |
| q004 | 4 | 4 | 0 | 0 |
| q005 | 4 | 4 | 0 | 0 |
| q006 | 6 | 5 | 1 | 0 |
| q007 | 3 | 3 | 0 | 0 |
| q008 | 7 | 7 | 0 | 0 |
| q009 | 9 | 8 | 1 | 0 |
| q010 | 7 | 7 | 0 | 0 |
| q011 | 1 | 1 | 0 | 0 |
| q012 | 3 | 1 | 1 | 1 |
| q013 | 8 | 7 | 1 | 0 |
| q014 | 3 | 3 | 0 | 0 |
| q016 | 4 | 4 | 0 | 0 |
| q017 | 3 | 2 | 1 | 0 |
| q018 | 5 | 4 | 1 | 0 |
| q019 | 12 | 11 | 1 | 0 |
| q020 | 4 | 3 | 1 | 0 |
| q021 | 5 | 5 | 0 | 0 |
| q023 | 8 | 7 | 1 | 0 |
| q024 | 3 | 3 | 0 | 0 |
| q025 | 4 | 4 | 0 | 0 |
| q026 | 2 | 2 | 0 | 0 |
| q027 | 3 | 3 | 0 | 0 |
| q028 | 5 | 4 | 1 | 0 |
| q031 | 9 | 9 | 0 | 0 |
| q032 | 2 | 2 | 0 | 0 |
| q033 | 2 | 1 | 1 | 0 |
| q034 | 3 | 3 | 0 | 0 |
| q035 | 3 | 3 | 0 | 0 |
| q038 | 3 | 3 | 0 | 0 |
| q043 | 6 | 6 | 0 | 0 |
| q044 | 6 | 6 | 0 | 0 |
| q045 | 8 | 8 | 0 | 0 |
| **all** | **178** | **166** | **11** | **1** |

Strict support rate (s only): 166 / 178 = 93.3%. Lenient (s + p): 177 / 178 = 99.4%. The 12 kept sentences on the five off-target answers (section 3) are excluded from these rates; 3 drafted sentences were dropped by the verifier or the fact-leak guard before anyone judged them.

### Every partly and not sentence, with the reason

- **q006 s3: partly** (cites 39260713100092#74:0)
  > The survey identified that 12% of acute care hospitals with more than 200 beds had no infection control program, and 40% of Canadian hospitals did not have physicians or doctoral professionals with infection control training who provided service to the infection control program.
  Reason: the 12% "no ICP" figure describes 1980s staffing levels, not the 2000 survey.

- **q009 s1: partly** (cites birthdeathstatistics1986#8:0)
  > Alberta Vital Statistics reported birth and death statistics disaggregated by health units in Alberta.
  Reason: the health-unit disaggregation is the report's work on Vital Statistics data, not Vital Statistics' own reporting.

- **q012 s2: not** (cites 31761115563926#4:0)
  > The National Day Care Information Centre was part of a series of resources available from the Day Care Information Centre under the Canada Assistance Plan.
  Reason: the passage says the booklet is part of a series from the Centre; the sentence says the Centre is part of a series.

- **q012 s3: partly** (cites 31761115564932#38:0)
  > The National Day Care Information Centre distributed publications designed to assist parent and community groups, as well as day care and pre-school staff, trainees and interested individuals in planning and design of child care centres.
  Reason: "Design for Child-Care" is a guidebook by the Urban Design Centre; the text does not say the Centre distributed it.

- **q013 s1: partly** (cites 31761115567265#28:0)
  > The National Clearinghouse on Family Violence distributed a catalogue of Canadian videos on family violence for the general public and for professionals working in the field.
  Reason: distributed by the National Film Board on the Clearinghouse's behalf.

- **q017 s2: partly** (cites annualreportofal00albe#60:0)
  > All new nursing homes being built in Alberta must comply with the Minimum Standards of Nursing Home Construction which prescribe essential services such as dining rooms, barber and beauty shops and areas for the provision of recreational, diversional and religious activities.
  Reason: dining rooms and shops are "extra facilities" beyond the essential services, not the essential services.

- **q018 s2: partly** (cites 39262009090110#18:1)
  > Federal health authorities coordinated vaccination programs with provincial and territorial partners, with the federal level well placed to coordinate activities such as the procurement of vaccines and antiviral drugs and the sharing of epidemiologic information on infectious diseases.
  Reason: the coordination claim rests on an Ontario official's testimony about federal capacity, not a federal description of coordinating programs.

- **q019 s2: partly** (cites 31761116324690#46:1)
  > Local health departments conducted routine tests on public water supplies, public sewage systems, and plumbing to assure that no health hazards exist.
  Reason: plumbing tests are not in the text; routine tests cover municipal water and sewage.

- **q020 s4: partly** (cites 31761118924935#90:0)
  > Ontario recognized that comparable surveillance data are essential to estimate the size of a health problem and to determine its economic burden on society, to characterize trends, and to evaluate intervention and prevention programs.
  Reason: the passage is the Ontario commission quoting the federal Auditor General; "Ontario recognized" shifts the speaker.

- **q023 s8: partly** (cites 39282716050165#462:1)
  > A 1984 federal report noted that while health promotion was practised by both governments and non-government organizations, their fragmentation had resulted in a poorly coordinated or integrated health promotion infrastructure, and no health goals had been set nationally for health promotion as there had been in the United States.
  Reason: content matches; "1984" is item metadata on a passage that cites 2002 sources.

- **q028 s3: partly** (cites 31761119706406#215:0)
  > Federal reports indicated that statistics on women's economic equality, adequate childcare, and equal access to training and post-secondary education remained unchanged despite twenty years of promised improvements.
  Reason: a witness brief in committee minutes, not a federal report's finding.

- **q033 s1: partly** (cites 4thannualinjuryi00inju#15:1)
  > Traditional approaches to occupational health and safety in the early 1990s included one-on-one inspections, enforcement, a focus on safety rather than health, reactive priorities, and a focus on fatalities.
  Reason: "in the early 1990s" is added; the passage lists past approaches as of 1992.

## 3. Abstention: verification guarantees support, not relevance

In-sample, on the 15 gold-abstain questions the tool abstained on 10: q022, q029, q039, q040, q041, q042, q046, q047, q048, q050. It answered 5: q015, q030, q036, q037, q049. The author's
judgment of the five: each is an all-supported answer to a different question than the one asked, on
the wrong period or the wrong object (marks on their sentences: {"q015": {"s": 3}, "q030": {"s": 3}, "q036": {"p": 1, "s": 1}, "q037": {"s": 2, "p": 1}, "q049": {"s": 1}}).
Every kept sentence cites a passage that exists, was in the retrieved evidence, resolves to a recorded
page, and says what the sentence says; the passages do not bear on the question's period or subject.
The three structural checks and the fact-leak guard guarantee support by the page; nothing in the
pipeline guarantees the page is about what was asked.

The frozen thinness sweep on this configuration (`retrieval_report.md`, final section)
predicted 9 of the 15 gold-abstain questions would pass the gate: 5 passed and answered off target, and
the rest abstained at the gate or downstream when no drafted sentence survived verification. False
abstentions on the 35 answerable questions: 0, as the sweep predicted.

### Held-out run

`eval/holdout_questions.jsonl`, one run on 2026-09-11T19:45:29+00:00 (UTC): 9/10 gold-abstain probes abstained, answered: h009; 4/5 gold-answerable questions answered, abstained: h015.
Per-question outcomes, uncovered terms and abstention texts: `holdout_run.md`. These
held-out numbers are the only abstention figures here that were not available while the rule and
the retrieval configuration were being designed.

- h001 gold abstain: abstained (gate: no passage mentions zika)
- h002 gold abstain: abstained (gate: no passage mentions mpox)
- h003 gold abstain: abstained (downstream: no drafted sentence survived verification)
- h004 gold abstain: abstained (gate: no passage mentions vaping)
- h005 gold abstain: abstained (gate: no passage mentions semaglutide)
- h006 gold abstain: abstained (gate: no passage mentions 2000, 2020)
- h007 gold abstain: abstained (gate: no passage mentions 2023)
- h008 gold abstain: abstained (gate: no passage mentions edibles)
- h009 gold abstain: answered
- h010 gold abstain: abstained (gate: no passage mentions 2024)
- h011 gold answerable: answered
- h012 gold answerable: answered
- h013 gold answerable: answered
- h014 gold answerable: answered
- h015 gold answerable: abstained (gate: no passage mentions federal)

The two held-out misses, recorded after this single run with no rule changed (mechanisms read
from the cached answers and the frozen stoplist in `src/archive_debugger/stopwords.py`):

- h009 (electric scooters) answered: "scooters" was covered by an undated child-safety pamphlet and a
  1988 occupational-health maintenance note; the lexical gate cannot separate electric scooters from
  toy or workplace scooters. Same class as the five in-sample off-target answers.
- h015 (1976 influenza program) abstained at the gate: "federal" is salient under the frozen rule and
  no retrieved passage contains the word; the stoplist's actor-noun criterion lacks "federal". First
  candidate for a v2 stoplist, if one is opened; v1 stands and this false abstention counts against it.

## 4. Retrieval, before and after (final gold, all top-20 judged)

recall@10 0.3470 -> 0.4581; recall@20 0.5928 -> 0.7276; nDCG@10 0.4174 -> 0.5082; unjudged@10 and @20 0.0 for both (`retrieval_report.md`, final section).

## 5. Citations resolving to a recorded page

119 kept citations across the 40 answered questions; 119 exist, 119 were in the retrieved evidence,
119 resolve to a recorded page: 1.00. This is 1.0 by construction: verifier check 3 (`resolves`) drops
any citation whose (item, leaf) has no page row before a sentence can be kept, so a kept citation
cannot fail to resolve. The number confirms the gate held on the live run; it is not evidence of
anything beyond that.

## Later-years cases the audit surfaced

- q023 s8 cites `39282716050165#462:1`: item metadata year 1984, passage text names 2002; judged p for
  that reason. The evidence card carries "mentions 2002 (item dated 1984)".
- q018 s2 cites `39262009090110#18:1`: item metadata year 1984; this passage's own text contains no
  year, so its card carries no mark. The 2010-10-22 date recorded in `eval/labeling_notes.md` sits in
  another passage of the same item. The annotation is passage-level; an item-level date conflict shows
  only on the chunks that name the later year.
- 34 further cited passages in the run carry a later-years mark, mostly annual reports whose item year
  predates the report year in the text (for example `birthdeathstatistics1986` items dated 1984 with
  1986-1989 text).

