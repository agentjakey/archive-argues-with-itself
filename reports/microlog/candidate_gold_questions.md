# Microlog candidate gold questions (candidate text only)

Author decides the gold. Per N4, these are candidate QUESTION TEXT ONLY. No relevance labels, no
gold passages, no expected period/jurisdiction/abstention status are assigned here. You validate and
edit each question against the real microlog corpus, hand-label relevance, and determine against the
corpus whether any question abstains. The suggested filters are candidates to edit, not labels.

Per Gate 2, none of these feature Indigenous-identifying health content, and all four flagged topics
(residential-school health, coerced sterilization, tainted blood, early HIV/AIDS) are deliberately
excluded from this candidate set so the gold can seed non-flagged golden questions and attract tiles.

Scope: microlog national public-health administration, dated span 1963-2018, all provinces and
territories present as an issuer proxy.

## Candidate answerable-leaning questions (validate against the corpus; do not pre-assign status)

1. How did provincial reports describe hospital funding or global budgeting arrangements? (suggested filter: none)
2. What did reports describe about public hospital insurance and medicare administration? (suggested: none)
3. How was communicable-disease surveillance organized in provincial public-health reports? (suggested: none)
4. What did reports say about drinking-water safety and municipal sanitation? (suggested: none)
5. What occupational health and workplace-safety priorities did reports describe? (suggested: none)
6. How did reports characterize childhood immunization programs? (suggested: none, and confirm this does not surface flagged content)
7. What did reports describe about tobacco control and smoking cessation? (suggested: none)
8. How did reports address nutrition, food safety, or food inspection? (suggested: none)
9. What did reports say about long-term care or care of the aged? (suggested: none)
10. How did provincial reports describe mental health service organization? (suggested: none; screen out any Indigenous-identifying content at labeling)
11. What did reports describe about health human resources or physician supply? (suggested: none)
12. How did reports address environmental health hazards such as air quality? (suggested: none)
13. What did reports say about prescription drug programs or pharmacare? (suggested: none)
14. How did reports describe maternal and child health services? (suggested: none; screen at labeling)
15. What did reports describe about health-system regionalization or reorganization? (suggested: none)

## Candidate out-of-scope / abstention probes (status determined against the corpus, not here)

16. What did reports say about COVID-19 pandemic response? (span note: microlog reaches 2018; the corpus likely predates this)
17. What did reports describe about telehealth or digital health apps in the 2020s? (out of the dated span)
18. What did reports say about cannabis legalization public-health guidance after 2018? (edge of the span)
19. What did United States federal agencies report about Medicaid? (out of jurisdiction/scope)

## Author steps (N4)

- Validate each question against microlog: does real evidence exist? Edit or drop as needed.
- Hand-label relevance for the answerable set (candidate labels may be model-proposed for adjudication,
  each reviewed and decided by you; the honesty disclosure noting the judge is not independent applies).
- Determine abstention status against the corpus; do not pre-assign it.
- Record the decided gold in its own microlog gold file; the pilot gold is untouched (N4).

## Validated candidate set (grounded in real retrieval and gate behavior)

Model-proposed, author-decided (N4). Each question below was run through the frozen retriever
and the a-priori thinness gate over the microlog scope; per-passage candidate relevance labels
with the retrieved excerpt, ids, and page/leaf are in reports/microlog/candidate_gold_labels.json
(the accept/edit/reject queue). Nothing here is decided gold; the eval_* tables stay empty and
the pilot gold is untouched until you decide.

Disclosure (verbatim): Candidate relevance labels and abstention statuses were proposed by an assistant model from real retrieval output and gate behavior; each is to be reviewed and decided by Jacob Ortiz. The same model family generates the tool's answers, so this judge is not independent of the system.

Summary: 48 candidate questions -- 41 proposed answerable, 7 proposed should-abstain; 4 gate-conflict cases (the frozen gate disagrees with the proposed status; noted, not fixed, P-EXP-10); 20 passages excluded per Gate 2 (flagged topics or Indigenous-identifying content).

- mq01 [answerable] gate: answers
    Q: What did FluWatch or influenza surveillance reports describe about seasonal influenza activity?
    note: FluWatch/CCDR influenza surveillance; uniformly on-topic.
- mq02 [answerable] gate: answers
    Q: What did the Canada Communicable Disease Report describe about notifiable disease trends?
    note: CCDR + provincial notifiable-disease; CIHR estimates off-topic.
- mq03 [answerable] gate: answers excluded=2
    Q: How did provincial communicable-disease surveillance reports describe reportable disease case counts?
    note: Strong provincial reportable-disease counts; 2 flagged passages excluded per Gate 2. rank3 mentions 2015 (item dated 2012).
- mq04 [answerable] gate: answers
    Q: What did National Advisory Committee on Immunization statements recommend about immunization schedules?
    note: NACI statements / Canadian Immunization Guide / CCDR ACS; strong.
- mq05 [answerable] gate: answers excluded=1
    Q: What did reports describe about vaccine coverage or immunization uptake?
    note: Vaccine uptake/hesitancy; exclude First Nations coverage report.
- mq06 [answerable] gate: answers
    Q: What did Pest Management Regulatory Agency re-evaluation decisions conclude about pesticides?
    note: PMRA re-evaluation decisions; strong. rank7 mentions 2006 (item dated 2000).
- mq07 [answerable] gate: answers
    Q: How did reports describe pesticide re-evaluation or registration review?
    note: PMRA re-evaluation program; strong.
- mq08 [answerable] gate: answers
    Q: What did workers' compensation board reports describe about occupational injury claims?
    note: WCB occupational-injury claims; strong.
- mq09 [answerable] gate: answers
    Q: What did reports describe about occupational disease or workplace hazard exposure?
    note: Workplace injury/occupational disease statistics; strong.
- mq10 [answerable] gate: answers
    Q: What did drinking-water quality guidelines recommend about contaminants?
    note: Drinking-water quality/contaminants; strong.
- mq11 [answerable] gate: answers excluded=3
    Q: How did reports describe municipal water treatment or sanitation infrastructure?
    note: Water/sanitation; Baffin community-water passages are Indigenous-adjacent (author decides); Brazil-market passages off-topic.
- mq12 [answerable] gate: answers excluded=2
    Q: What did chronic-disease surveillance reports describe about diabetes prevalence?
    note: Diabetes prevalence surveillance; strong. rank6 mentions 2009/2010/2015/2016 (item dated 2004).
- mq13 [answerable] gate: answers
    Q: What did reports describe about cancer incidence or cancer registry data?
    note: Cancer registry/incidence; strong (provincial registries). rank2 is NWT-wide cancer data (territorial, kept).
- mq14 [answerable] gate: answers
    Q: How did reports describe cardiovascular disease surveillance?
    note: Cardiovascular surveillance; strong; rank8 FluWatch off-topic.
- mq15 [answerable] gate: answers excluded=1
    Q: What did provincial drug benefit formularies describe about covered medications?
    note: Provincial drug formularies; exclude NIHB passage.
- mq16 [answerable] gate: answers
    Q: How did reports describe pharmacare or drug program administration?
    note: Pharmacare administration (Manitoba audit, DPIN); strong.
- mq17 [answerable] gate: answers
    Q: What did reports describe about long-term care standards or nursing home inspection?
    note: LTC standards / nursing-home inspection; strong.
- mq18 [answerable] gate: answers excluded=2
    Q: How did reports describe community mental health service organization?
    note: Community mental-health organization; exclude Native-populations + flagged.
- mq19 [answerable] gate: answers
    Q: What did reports describe about mental health service delivery models?
    note: Mental-health service-delivery models; strong.
- mq20 [answerable] gate: answers
    Q: What did reports describe about physician or nurse supply and health human resources?
    note: Health human resources / nurse-physician supply; strong (Achieving the Vision).
- mq21 [answerable] gate: answers
    Q: How did reports describe food safety inspection or foodborne illness investigation?
    note: Food-safety inspection / CFIA; strong.
- mq22 [answerable] gate: answers
    Q: What did reports describe about tobacco control or smoking reduction programs?
    note: Tobacco control / smoking reduction; strong.
- mq23 [answerable] gate: answers
    Q: How did reports describe maternal or prenatal health programs?
    note: Maternal/prenatal health; strong. ranks1,5 are NWT territorial maternal-health (kept).
- mq24 [answerable] gate: answers
    Q: What did reports describe about child health programs?
    note: EDIT/DROP CANDIDATE: 'child health' pulls mostly child-WELFARE/protection, not child health. Weaker; consider reframing to 'childhood immunization or child health surveillance'.
- mq25 [answerable] gate: answers
    Q: What did reports describe about Ontario Local Health Integration Networks?
    note: Ontario LHINs; strong. ranks1,8 mention later years (2013; 2011/2012).
- mq26 [answerable] gate: answers excluded=1
    Q: How did reports describe regional health authority organization?
    note: Regional health authorities; strong (Saskatchewan RHAs).
- mq27 [answerable] gate: answers
    Q: What did reports describe about health-system restructuring or regionalization?
    note: Health-system restructuring/regionalization; strong.
- mq28 [answerable] gate: ABSTAINS (uncovered: reports) [GATE-CONFLICT]
    Q: What did reports describe about hospital funding or global budgets?
    note: GATE QUIRK (note, do not fix): evidence for hospital funding/global budgets is strong, but the frozen gate ABSTAINS because the salient word 'reports' is uncovered by retrieved pages -- same class as the pilot's 'federal'/'risks'. Suggested reworded variant that avoids the trigger: 'How were public hospitals funded, through global budgets or other mechanisms?'
- mq29 [answerable] gate: answers excluded=2
    Q: What did reports describe about public hospital insurance administration?
    note: Public hospital-insurance administration (Canada Health Act annual reports) + hospital-statistics tables; exclude Nunavut/traditional-foods passages.
- mq30 [answerable] gate: answers
    Q: What did reports describe about home care or continuing care programs?
    note: Home/continuing care; strong.
- mq31 [answerable] gate: answers
    Q: What did reports describe about air quality or environmental health hazards?
    note: Air quality / environmental-health hazards; strong (ambient air-quality objectives).
- mq32 [answerable] gate: answers excluded=1
    Q: What did reports describe about lead exposure or environmental contaminants?
    note: Lead exposure / environmental contaminants; strong (Health effects of lead).
- mq33 [answerable] gate: answers excluded=1
    Q: What did reports describe about nutrition or dietary guidance?
    note: Nutrition / dietary guidance (Canada's Food Guide consultation); exclude country-foods passage.
- mq34 [answerable] gate: answers
    Q: What did reports describe about health promotion or disease prevention campaigns?
    note: Health promotion / disease prevention; strong.
- mq35 [answerable] gate: answers
    Q: What did reports describe about emergency preparedness or pandemic planning?
    note: Emergency preparedness / pandemic planning (pre-COVID: H1N1, pandemic-influenza plans); strong.
- mq36 [answerable] gate: answers
    Q: What did reports describe about antimicrobial resistance or antibiotic use?
    note: Antimicrobial resistance / antibiotic use; strong (CCDR AMR supplements).
- mq37 [answerable] gate: answers
    Q: What did reports describe about West Nile virus or vector-borne disease surveillance?
    note: West Nile / vector-borne surveillance; strong (national WNV surveillance reports).
- mq38 [answerable] gate: answers
    Q: What did reports describe about measles or mumps outbreak response?
    note: Measles/mumps outbreak response; strong (CCDR mumps-outbreak guidelines). rank8 'related communities' is ambiguous (author screen).
- mq39 [answerable] gate: answers excluded=1
    Q: What did reports describe about health surveillance data systems or reporting?
    note: Health surveillance data systems/reporting; mixed (surveillance frameworks + Alberta HIA duplicates).
- mq40 [answerable] gate: answers
    Q: What did reports describe about the SARS outbreak of 2003?
    note: SARS 2003; strong (SARS Commission, Ontario Expert Panel). Good in-window boundary (2003).
- mq41 [should-abstain] gate: ABSTAINS (uncovered: covid) excluded=1
    Q: What did reports describe about the COVID-19 pandemic response in 2020?
    note: Gate correctly ABSTAINS on 'covid'. No COVID-19 content (post-2018); retrieval surfaces pre-COVID pandemic-influenza/H1N1 planning, none about COVID-2020.
- mq42 [should-abstain] gate: ABSTAINS (uncovered: apps, 2020s)
    Q: What did reports describe about telehealth or virtual-care apps in the 2020s?
    note: Gate ABSTAINS on 'apps','2020s'. Telehealth content EXISTS (2000-2001 evaluations) but nothing about 2020s or apps; a reframed 'What did reports describe about telehealth?' (drop 2020s/apps) would likely be answerable -- author decides.
- mq43 [should-abstain] gate: answers [GATE-CONFLICT]
    Q: What did United States Medicaid reports describe about eligibility rules?
    note: GATE ANSWERS despite out-of-jurisdiction (US). NOTE: microlog holds Canadian comparative-policy reports that describe US Medicaid/Medicare eligibility (ranks1,6 genuine). Author decides: rule should-abstain (out of the Canadian scope) or answerable-with-caveat.
- mq44 [should-abstain] gate: answers [GATE-CONFLICT]
    Q: What did reports describe about public health in the 1950s?
    note: GATE ANSWERS. NOTE: the scope has 0 pre-1960 DATED items, but later documents MENTION the 1950s (rank1: 1959 psychiatric units; rank7: Salk vaccine early 1950s). Author decides: should-abstain (no primary 1950s coverage) vs answerable-from-mentions.
- mq45 [should-abstain] gate: ABSTAINS (uncovered: mrna) excluded=1
    Q: What did reports describe about mRNA vaccine platform development?
    note: Gate correctly ABSTAINS on 'mrna'. No mRNA content (pre-2018 platform tech: VSV/VIDO); correct abstain.
- mq46 [should-abstain] gate: ABSTAINS (uncovered: guidance) [GATE-CONFLICT]
    Q: What did reports describe about cannabis legalization public-health guidance after 2018?
    note: Gate ABSTAINS on 'guidance' (quirk), though 2018 cannabis-legalization/regulation content IS present (ranks2,4,5: Task Force, proposed regulation). Boundary (2018 edge). A reframe dropping 'guidance' would answer -- author decides.
- mq47 [answerable] gate: answers
    Q: What did reports describe about vaping or electronic-cigarette regulation?
    note: RECLASSIFIED answerable (my should-abstain hypothesis was WRONG): vaping/e-cigarette regulation is genuinely in scope (2015-2018: Health Canada vaping consultation 2018, e-cigarette regulation 2016). Gate answers.
- mq48 [should-abstain] gate: ABSTAINS (uncovered: mpox) excluded=1
    Q: What did reports describe about monkeypox or mpox outbreak response?
    note: Gate correctly ABSTAINS on 'mpox'. No mpox content (post-2018); retrieval surfaces off-topic 'monkey' matches (lead study on monkeys; film-industry apes) + one incidental 'monkey-pox' mention -- good precision-first abstain.
