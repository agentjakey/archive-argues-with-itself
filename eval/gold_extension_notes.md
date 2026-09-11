# Phase 13 gold extension: decisions and notes

Jacob Ortiz's per-question decisions over `reports/phase13/extension_worksheet.jsonl`
(the candidate retriever's top-20, passages that carried no Phase 7 label).
Ranks are the candidate's ranks as printed in the worksheet. r = relevant,
n = not relevant, uncertain = no label written (the passage stays unjudged).
The machine-readable form is `eval/gold_extension_decisions.json`.

QID: q001 question: What did Ontario public health authorities recommend about controlling tobacco smoking?
r: 6 "tax increases as a major component ... large decreases in smoking" (Ontario doc, describes national strategy); 7 "eliminating tobacco use ... co-operating with the local Boards of Education"; 9 "Smoking cessation programs are encouraged"; 10 "achievable with sustained funding and comprehensive programming"; 13 "support smoke-free by-law development in local communities"; 20 "raised the legal age to purchase tobacco from 18 to 19"
uncertain: 12 (survey finding on public support for smoke-free places; r only if survey results count as a recommendation); 19 (paper summary cut off before any workplace-smoke recommendation)
n: 8, 11, 14, 15, 16, 17, 18

QID: q002 question: How did federal health authorities describe tuberculosis control programs?
r: 9 "organized in 1900 to stimulate interest in the control of tuberculosis"; 11 "co-ordinate the various agencies engaged in the prevention and treatment"; 14 "Tuberculosis Control Grant ... prevention and case finding ... free treatment"; 19 "responsible for the programme of tuberculosis control and treatment" (federal commission describing Saskatchewan)
uncertain: 20 (cut off before any program description; 2010 sits at the window edge)
n: 18

QID: q003 question: What did Alberta's provincial AIDS program report about HIV prevention?
r: 14 "limiting or eliminating the spread ... through direct and indirect educational activities"
uncertain: 17 (ministerial open letter, cut off; probably preface only, r if it states a prevention strategy)
n: 15, 18, 19

QID: q004 question: What did federal reports describe about the prevalence of venereal disease?
r: 18 "many diseases ... actual morbidity is higher than venereal disease"
uncertain: none
n: 17, 19

QID: q006 question: What did the Ontario SARS Commission conclude about hospital infection control?
r: 10 "failure of the Ministry of Labour to proactively inspect SARS hospitals" (regulatory oversight, not clinical practice); 18 "primary responsibility for managing outbreaks within an institution"; 19 "hierarchy of controls ... developed long before SARS"; 20 "direction ... came from infection control, administration or management"
uncertain: none
n: 17

QID: q007 question: What health and safety risks from asbestos did the Ontario royal commission identify?
r: none
uncertain: none
n: 11, 12, 13, 14, 15, 16, 17, 18, 19, 20

QID: q008 question: What workplace health and safety hazards did Alberta occupational health reports cover?
r: none
uncertain: none
n: 7

QID: q009 question: What did Alberta vital statistics report about mortality?
r: 16 "INFANT MORTALITY ... TOTAL 15,039 246 ... Mortality Rate 16.36"
uncertain: 20 (chapter introduction; r only if the passage continues into actual figures)
n: none

QID: q011 question: What did the Ontario Hospital Services Commission report about hospital funding?
r: none
uncertain: 18 (states Ontario global budgeting problems, but source is the 1989 Health Care System Committee, not OHSC; decide how strictly the named body applies)
n: 8, 9, 10, 11, 12, 13, 19, 20

QID: q012 question: What did the federal National Day Care Information Centre report about child care?
r: 20 "obtain information concerning the existing day care services and ... unmet need"
uncertain: 4, 8, 17, 18 (substantive Canadian National Child Care Study content; r if you treat CNCCS as an NDCIC report, otherwise n)
n: 9, 10, 12

QID: q013 question: What did the National Clearinghouse on Family Violence report?
r: 16 "series of directories prepared by the National Clearinghouse on Family Violence"
uncertain: none
n: 14, 15, 17, 19, 20

QID: q014 question: What did federal reports say about the health of aging seniors?
r: 10 "health needs of future seniors may not be the same"
uncertain: none
n: 16, 18

QID: q015 question: What did the royal commission on new reproductive technologies recommend?
r: none
uncertain: none
n: 18, 19, 20

QID: q016 question: What did the federal Food and Drug Directorate report about drug safety?
r: none
uncertain: 14 (witness paraphrase; "statements of the Food and Drug Directorate ... to the effect" cut off before content)
n: 17, 18

QID: q018 question: What vaccination programs did federal health authorities describe?
r: 4 "mass vaccination program ... influenza ... approximately ten million citizens"; 13 "Public Health Grant for B.C.G. vaccination programs" (federal report, provincial spending)
uncertain: none
n: 1, 2, 5, 9, 15, 18, 20
verdict note: gold says abstain, but ranks 4 and 13 both describe federally announced or federally funded vaccination programs.

QID: q020 question: How did Ontario describe communicable disease surveillance?
r: none
uncertain: 14 (new agency to support the CMOH; cut off before any mention of surveillance functions)
n: 15, 16, 18, 20

QID: q021 question: What environmental health concerns did Alberta report?
r: none
uncertain: 7, 8 (opens the environmental influences section; cut off before naming any concern); 14 (states emission impacts "not well understood. Some of the concerns" then cut off)
n: 6, 15, 17, 20

QID: q022 question: What did the inquiry into deaths at the Hospital for Sick Children find?
r: none
uncertain: 15 (report body referencing CDC/Ministry work and murder-charge evidence; cut off before any finding)
n: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20

QID: q023 question: What health promotion strategies did federal reports describe in the 1980s?
r: 17 "our proposal for a health promotion framework"
uncertain: none
n: 15

QID: q024 question: What did Alberta report about occupational cancer risk?
r: 4 "workplace exposure could have caused this cancer? Yes, it is possible"; 10 "8% Occupational Exposures"
uncertain: none
n: 6, 11, 14, 16, 19, 20

QID: q025 question: How did Ontario describe restructuring of mental health services?
r: none
uncertain: none
n: 17

QID: q026 question: What did the Alberta Alcohol and Drug Abuse Commission report?
r: none
uncertain: none
n: 9, 12, 16, 17, 18, 19, 20

QID: q027 question: What did the federal physical fitness division promote?
r: 13 "grants and support to national fitness and sport organizations" (1972 Fitness and Amateur Sport program, not literally a "division")
uncertain: none
n: none

QID: q028 question: What did federal reports say about women's health status?
r: none
uncertain: none
n: 2, 5, 6, 10, 12, 13, 14, 16, 18, 20

QID: q029 question: How did Ontario's approach to tobacco control change between 1975 and 1990?
r: none
uncertain: 14 (1990 shift to program approach following Ministry mandatory programs; tobacco link not in excerpt); 16 ("increasingly seen" implies change, but national and undated)
n: 6, 7, 8, 9, 10, 11, 12, 13, 15, 17, 18, 19, 20

QID: q030 question: How did hospital funding concerns differ between the 1970s and the 1990s?
r: none
uncertain: 1 (1984 evaluation states hospitals' budget responsibility; era not dated in excerpt); 10 (transfer history opens, cut off before any 1970s/1990s content)
n: 6, 8, 12, 14, 18, 20

QID: q031 question: How did Alberta's mental health policy change between 1980 and 2000?
r: 8 "In April 1992 Future Directions ... approved ... as the mental health policy"
uncertain: 9 (1997 AADAC/AMHB partnership; counts only if concurrent-disorders policy is in scope); 12 (1993 critique of uncoordinated system; motivation for change, not a change)
n: 10, 17, 20
verdict note: gold says abstain, but rank 8 states a dated policy adoption inside the window (single point, not a comparison).

QID: q032 question: How did reported mortality patterns change between 1975 and 2005?
r: none
uncertain: 5 (life expectancy chart 1975-2005; OCR garbles the values)
n: 7, 9, 10, 16, 19

QID: q033 question: How did occupational health and safety priorities shift between 1980 and 2000?
r: none
uncertain: 12 (1979 consolidation priorities; single pre-1980 point)
n: 3, 5, 9, 11, 13, 15, 16, 17, 18, 19, 20

QID: q034 question: How did Alberta health insurance coverage change between the 1970s and 1990s?
r: none
uncertain: 16, 17 (1987-88 coverage: premium-free Blue Cross and EHB for seniors; single period); 19 (1998-99 coverage components; single period, paired with 16/17 could support the comparison)
n: 18

QID: q035 question: How did federal communicable disease priorities change between 1975 and 2005?
r: none
uncertain: none
n: 6, 8, 11, 13, 17, 19

QID: q036 question: How did federal policy on aging change between the 1980s and 2000s?
r: 9 "shifting the emphasis from institutional to community-based"
uncertain: 6 (2000 Division stance, "population health approach"; single period)
n: 2, 3, 5, 10, 12, 15, 19, 20

QID: q037 question: How did Alberta environmental health concerns change between 1980 and 2005?
r: none
uncertain: 5 ("HISTORICAL CONTEXT" section may narrate evolution; cut off at organizational point)
n: 10, 16, 17, 20

QID: q038 question: How did federal child care policy change between the 1970s and 1990s?
r: none
uncertain: 4 (federal involvement via transfers; cut off before any change); 12 ("In the 1970s, access to..." cut off; context looks provincial)
n: 7, 14, 20

QID: q039 question: What did public health authorities report about the COVID-19 pandemic in 2020?
r: none
uncertain: none
n: 1, 12, 13, 14, 17, 19

QID: q040 question: What public health guidance followed cannabis legalization in 2018?
r: none
uncertain: none
n: 9, 16, 18, 20

QID: q041 question: What did health authorities report about vaping and e-cigarettes in 2019?
r: none
uncertain: none
n: 1, 3, 5, 7, 9, 10, 12, 15, 18, 19

QID: q042 question: What did reports say about the opioid overdose crisis around 2016?
r: none
uncertain: 4 (2019 Brant report, "Highest rates of opioid hospitalization in Ontario"; hinges on how wide "around 2016" is)
n: 1, 3, 6, 8, 14, 16, 17, 18, 20

QID: q043 question: How did British Columbia structure its health insurance plan?
r: 16 "commenced payments to hospitals for treatment provided to qualified residents"; 20 "administered ... by the Hospital Programs Division of the Ministry of Health"
uncertain: 13 (general system description; "insured services under the Canada Health Act" only loosely about plan structure)
n: none
verdict note: gold says abstain on jurisdiction, but ranks 16 and 20 (unknown-jurisdiction items, likely federal Canada Health Act reports) do describe BC's plan structure.

QID: q044 question: What did Quebec report about hospital funding?
r: none
uncertain: 4 (states Quebec uses a population-based method, but the reporter is a Senate committee, not Quebec)
n: 2, 3, 6, 7, 9, 11, 12, 14, 16, 18, 19

QID: q046 question: What did authorities report about tuberculosis sanatoria in 1905?
r: none
uncertain: 11 (history of sanatoria 1896-1912; r if the question means that era, n if it means reports dated 1905)
n: 9, 15, 16, 18, 20

QID: q047 question: What did Alberta report about public health nursing in the 1910s?
r: none
uncertain: none
n: 3, 4, 6, 10, 11, 12, 15, 16, 18, 19, 20

QID: q048 question: What did health authorities report about telehealth expansion around 2015?
r: none
uncertain: none
n: 6, 7, 11, 14, 15, 17, 18, 19

QID: q049 question: What did Canadian health authorities report about Ebola preparedness in 2014?
r: none
uncertain: none
n: 2, 3, 6, 8, 9, 11, 14, 15, 17, 18, 20

QID: q050 question: What did reports say about digital mental health apps around 2017?
r: none
uncertain: none
n: 8, 9, 10, 12, 14, 17, 19, 20

Note on the three verdict notes (q018, q031, q043): the Phase 7 gold for all three
is already answerable (see the x->a entries in eval/labeling_notes.md), so no
verdict was changed by this extension; the new r marks are consistent with it.

## Batch 2

The 35 passages left uncertain in batch 1, decided from the same worksheet
excerpts (`eval/gold_extension_decisions_2.json`; 6 r, 29 n; additive, no
earlier label changed). Rule decisions:

- single-period statements count as relevant for comparison questions,
  consistent with Phase 7 (q031 9, q034 16/17/19, q036 6 r);
- q032 5 r as a 1975-2005 life-expectancy series;
- named-body questions require the named body (q011 18, q012 4/8/17/18, q044 4 n);
- out-of-window probes stay n by design (q042 4, q046 11);
- cut-off or non-answering excerpts n (q001 12/19, q002 20, q003 17, q009 20,
  q016 14, q020 14, q021 7/8/14, q022 15, q029 14/16, q030 1/10, q031 12,
  q033 12, q037 5, q038 4/12, q043 13).
