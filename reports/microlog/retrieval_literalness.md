# Microlog retrieval-literalness diagnostic (P-EXP-10 input, read-only)

Measurement only. No change to search.py, the gate, RRF weights, config, or any DB; no LLM call. For each decided-gold seed: FTS5-only top-k, vector-only top-k, and the production RRF-fused top-k side by side, plus the a-priori gate outcome. Gate-abstained seeds are flagged as possibly-correct thin coverage, not assumed retrieval failure.

- seeds: 47 (decided gold); k = 10
- gate: 41 answer, 6 abstain
- lexical-dominance (RRF overlaps FTS >= 0.8): 2/41 answered; mean RRF-vs-FTS overlap@10 = 0.473; top-1 agreement 10/41
- semantic-contribution (>=1 dense-only passage in RRF top-10): 34/41 answered; 106 dense-only slots total
- gate-abstained (possibly-correct thin coverage): mq28, mq41, mq42, mq45, mq46, mq48

High overlap + top-1 agreement + few dense-only slots => lexical-dominant retrieval; the vector arm mostly re-ranks the same lexical candidates. Dense-only slots are where the vector arm surfaced items FTS missed. This is a MEASUREMENT for the P-EXP-10 decision; no ranking or gate change is made here. Gate-abstained seeds are flagged as possibly-correct thin coverage, not assumed retrieval failure.

## mq01  [gate: answer]
What did FluWatch or influenza surveillance reports describe about seasonal influenza activity?
overlap RRF-vs-FTS@10 = 0.6; top-1 agree = False; dense-only in RRF top-10 = 1

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40242405_2170#5:0 | micro_IA40243316_0965#2:1 | micro_IA40243316_0965#2:1 (b47/d1) |
| 2 | micro_IA40242405_2175#7:0 | micro_IA40243315_2357#3:1 | micro_IA40243315_2432#4:0 (b18/d37) |
| 3 | micro_IA40242405_2174#7:0 | micro_IA40243315_2483#0:1 | micro_IA40243315_2408#4:0 (b64/d57) |
| 4 | micro_IA40242405_2180#8:0 | micro_IA40244215_3220#0:1 | micro_IA40242405_2170#5:0 (b1/d-) |
| 5 | micro_IA40242405_2171#5:0 | micro_IA40243315_2357#1:3 | micro_IA40242405_2175#7:0 (b2/d-) |
| 6 | micro_IA40242405_2181#8:0 | micro_IA40244215_3183#3:0 | micro_IA40243315_2357#3:1 (b-/d2) |
| 7 | micro_IA40242405_2173#6:0 | micro_IA40243315_2455#7:0 | micro_IA40242405_2174#7:0 (b3/d-) |
| 8 | micro_IA40243315_2428#0:0 | micro_IA40244206_2006#5:0 | micro_IA40242405_2180#8:0 (b4/d-) |
| 9 | micro_IA40244209_0284#1:0 | micro_IA40244205_3345#13:0 | micro_IA40242405_2171#5:0 (b5/d-) |
| 10 | micro_IA40244209_0282#0:0 | micro_IA40244209_0268#6:0 | micro_IA40242405_2181#8:0 (b6/d-) |

## mq02  [gate: answer]
What did the Canada Communicable Disease Report describe about notifiable disease trends?
overlap RRF-vs-FTS@10 = 0.8; top-1 agree = True; dense-only in RRF top-10 = 2

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243314_1437#10:0 | micro_IA40244214_1394#0:0 | micro_IA40243314_1437#10:0 (b1/d-) |
| 2 | micro_IA40243314_1437#11:0 | micro_IA40243311_1031#0:0 | micro_IA40243314_1437#11:0 (b2/d-) |
| 3 | micro_IA40243316_0978#0:0 | micro_IA40242803_1648#0:0 | micro_IA40244215_3225#23:0 (b4/d-) |
| 4 | micro_IA40244215_3225#23:0 | micro_IA40244213_0514#0:0 | micro_IA40243213_0884#13:0 (b5/d-) |
| 5 | micro_IA40243213_0884#13:0 | micro_IA40244213_0516#0:0 | micro_IA40243510_0597#42:1 (b6/d-) |
| 6 | micro_IA40243510_0597#42:1 | micro_IA40243311_1051#43:0 | micro_IA40243311_1051#43:0 (b-/d6) |
| 7 | micro_IA40243314_1437#57:0 | micro_IA40242803_0034#0:0 | micro_IA40243314_1437#57:0 (b7/d-) |
| 8 | micro_IA40244215_3271#11:1 | micro_IA40244205_3210#0:0 | micro_IA40244215_3271#11:1 (b8/d-) |
| 9 | micro_IA40243305_0416#21:0 | micro_IA40243311_1051#45:0 | micro_IA40243305_0416#21:0 (b9/d-) |
| 10 | micro_IA40244207_2850#0:1 | micro_IA40242401_0608#0:0 | micro_IA40243311_1051#45:0 (b-/d9) |

## mq03  [gate: answer]
How did provincial communicable-disease surveillance reports describe reportable disease case counts?
overlap RRF-vs-FTS@10 = 0.3; top-1 agree = False; dense-only in RRF top-10 = 3

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244208_2428#0:1 | micro_IA40244215_3271#2:0 | micro_IA40243315_0323#22:1 (b3/d7) |
| 2 | micro_IA40244208_2427#1:0 | micro_IA40244204_2374#12:0 | micro_IA40243316_2035#71:1 (b51/d6) |
| 3 | micro_IA40243315_0323#22:1 | micro_IA40244204_2381#6:0 | micro_IA40242404_2779#30:0 (b63/d5) |
| 4 | micro_IA40243316_2040#27:1 | micro_IA40244204_2376#17:0 | micro_IA40244215_3271#10:0 (b58/d15) |
| 5 | micro_IA40244208_2426#1:0 | micro_IA40242404_2779#30:0 | micro_IA40244204_2374#12:0 (b-/d2) |
| 6 | micro_IA40244215_3171#6:1 | micro_IA40243316_2035#71:1 | micro_IA40244204_2381#6:0 (b-/d3) |
| 7 | micro_IA40243305_0704#8:0 | micro_IA40243315_0323#22:1 | micro_IA40243305_0169#3:0 (b182/d27) |
| 8 | micro_IA40244207_2845#1:0 | micro_IA40244215_3271#11:0 | micro_IA40243316_2040#27:1 (b4/d-) |
| 9 | micro_IA40244208_2429#1:0 | micro_IA40243305_0704#15:1 | micro_IA40244204_2376#17:0 (b-/d4) |
| 10 | micro_IA40243312_2684#16:0 | micro_IA40243316_2037#52:0 | micro_IA40244215_3171#6:1 (b6/d-) |

## mq04  [gate: answer]
What did National Advisory Committee on Immunization statements recommend about immunization schedules?
overlap RRF-vs-FTS@10 = 0.4; top-1 agree = False; dense-only in RRF top-10 = 3

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40242405_0796#18:1 | micro_IA40242803_1226#48:0 | micro_IA40243513_0439#4:0 (b85/d20) |
| 2 | micro_IA40244215_3193#75:1 | micro_IA40244215_3182#12:1 | micro_IA40244215_1179#35:1 (b32/d91) |
| 3 | micro_IA40243316_0959#3:0 | micro_IA40244215_3247#12:1 | micro_IA40242402_2655#13:0 (b23/d165) |
| 4 | micro_IA40243315_2502#2:0 | micro_IA40244215_3765#3:1 | micro_IA40242405_0796#18:1 (b1/d-) |
| 5 | micro_IA40242402_2647#17:0 | micro_IA40243306_2473#73:0 | micro_IA40244215_3182#12:1 (b-/d2) |
| 6 | micro_IA40244215_3239#21:0 | micro_IA40243315_1852#101:0 | micro_IA40243316_0959#3:0 (b3/d-) |
| 7 | micro_IA40242403_0394#2:0 | micro_IA40244201_1890#2:0 | micro_IA40244215_3247#12:1 (b-/d3) |
| 8 | micro_IA40242407_0294#38:1 | micro_IA40243315_2304#0:2 | micro_IA40243315_2502#2:0 (b4/d-) |
| 9 | micro_IA40243316_1272#3:0 | micro_IA40243316_1272#60:0 | micro_IA40242402_2647#17:0 (b5/d-) |
| 10 | micro_IA40242405_0796#18:0 | micro_IA40243315_2391#5:2 | micro_IA40243306_2473#73:0 (b-/d5) |

## mq05  [gate: answer]
What did reports describe about vaccine coverage or immunization uptake?
overlap RRF-vs-FTS@10 = 0.3; top-1 agree = False; dense-only in RRF top-10 = 5

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244216_2194#21:0 | micro_IA40243314_2655#84:0 | micro_IA40242402_2647#5:1 (b45/d16) |
| 2 | micro_IA40243312_2683#31:0 | micro_IA40244215_3178#29:2 | micro_IA40242402_2647#5:0 (b11/d165) |
| 3 | micro_IA40244215_3167#18:0 | micro_IA40244215_3267#6:0 | micro_IA40244216_2194#21:0 (b1/d-) |
| 4 | micro_IA40243315_2387#0:0 | micro_IA40244215_3267#2:0 | micro_IA40243314_2655#84:0 (b-/d1) |
| 5 | micro_IA40244201_1890#0:0 | micro_IA40244214_3727#2:0 | micro_IA40243312_2683#31:0 (b2/d-) |
| 6 | micro_IA40243315_2387#1:0 | micro_IA40242405_0798#25:0 | micro_IA40244215_3178#29:2 (b-/d2) |
| 7 | micro_IA40243316_0969#4:0 | micro_IA40243306_2473#78:1 | micro_IA40244215_3167#18:0 (b3/d-) |
| 8 | micro_IA40244215_3167#4:1 | micro_IA40243315_2296#4:1 | micro_IA40244215_3267#6:0 (b-/d3) |
| 9 | micro_IA40244210_1442#1:0 | micro_IA40243315_1852#101:0 | micro_IA40242405_0798#25:0 (b-/d6) |
| 10 | micro_IA40242404_0134#6:1 | micro_IA40243305_0704#23:1 | micro_IA40243306_2473#78:1 (b-/d7) |

## mq06  [gate: answer]
What did Pest Management Regulatory Agency re-evaluation decisions conclude about pesticides?
overlap RRF-vs-FTS@10 = 0.6; top-1 agree = False; dense-only in RRF top-10 = 2

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40242405_0584#4:0 | micro_IA40243311_0927#71:0 | micro_IA40243302_0142#206:1 (b15/d3) |
| 2 | micro_IA40243302_0142#206:0 | micro_IA40244206_0471#4:1 | micro_IA40244215_0966#22:0 (b9/d24) |
| 3 | micro_IA40242405_0548#4:0 | micro_IA40243302_0142#206:1 | micro_IA40244215_0965#17:0 (b10/d48) |
| 4 | micro_IA40242405_0617#6:0 | micro_IA40244211_0830#5:1 | micro_IA40244215_0963#11:0 (b20/d96) |
| 5 | micro_IA40242402_1014#5:0 | micro_IA40242404_1132#25:0 | micro_IA40242405_0584#4:0 (b1/d-) |
| 6 | micro_IA40242402_3523#5:0 | micro_IA40244206_1026#3:1 | micro_IA40243311_0927#71:0 (b-/d1) |
| 7 | micro_IA40242405_0646#6:0 | micro_IA40244202_0303#4:1 | micro_IA40243302_0142#206:0 (b2/d-) |
| 8 | micro_IA40242405_0534#5:0 | micro_IA40244215_1053#33:1 | micro_IA40244206_0471#4:1 (b-/d2) |
| 9 | micro_IA40244215_0966#22:0 | micro_IA40242802_0577#0:0 | micro_IA40242405_0548#4:0 (b3/d-) |
| 10 | micro_IA40244215_0965#17:0 | micro_IA40244120_2944#4:1 | micro_IA40242405_0617#6:0 (b4/d-) |

## mq07  [gate: answer]
How did reports describe pesticide re-evaluation or registration review?
overlap RRF-vs-FTS@10 = 0.3; top-1 agree = False; dense-only in RRF top-10 = 0

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244215_0966#10:1 | micro_IA40244215_0966#22:0 | micro_IA40244215_0966#22:0 (b25/d1) |
| 2 | micro_IA40244211_0898#4:1 | micro_IA40244211_0898#6:0 | micro_IA40244215_0965#17:0 (b33/d3) |
| 3 | micro_IA40242403_1761#4:1 | micro_IA40244215_0965#17:0 | micro_IA40243306_1507#74:0 (b13/d27) |
| 4 | micro_IA40243302_0142#117:1 | micro_IA40243302_0142#114:0 | micro_IA40244211_0898#6:0 (b96/d2) |
| 5 | micro_IA40242403_1750#4:1 | micro_IA40242803_0876#17:1 | micro_IA40244211_0898#4:1 (b2/d108) |
| 6 | micro_IA40243302_0142#206:0 | micro_IA40243311_1188#88:0 | micro_IA40244211_0898#2:0 (b11/d97) |
| 7 | micro_IA40242403_2912#2:0 | micro_IA40242808_2131#181:0 | micro_IA40242403_1750#9:1 (b95/d13) |
| 8 | micro_IA40244211_0906#2:0 | micro_IA40244203_3329#13:1 | micro_IA40243306_1507#4:0 (b29/d125) |
| 9 | micro_IA40242404_1199#31:0 | micro_IA40243510_0258#242:1 | micro_IA40244215_0966#10:1 (b1/d-) |
| 10 | micro_IA40242405_0528#6:0 | micro_IA40244215_0966#10:0 | micro_IA40242403_1761#4:1 (b3/d-) |

## mq08  [gate: answer]
What did workers' compensation board reports describe about occupational injury claims?
overlap RRF-vs-FTS@10 = 0.5; top-1 agree = True; dense-only in RRF top-10 = 5

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244205_1719#8:0 | micro_IA40244208_0750#19:0 | micro_IA40244205_1719#8:0 (b1/d-) |
| 2 | micro_IA40244207_2483#8:0 | micro_IA40244205_2426#23:0 | micro_IA40244208_0750#19:0 (b-/d1) |
| 3 | micro_IA40243514_1608#36:0 | micro_IA40243509_0725#4:0 | micro_IA40244207_2483#8:0 (b2/d-) |
| 4 | micro_IA40242806_2129#23:0 | micro_IA40244213_1776#11:0 | micro_IA40244205_2426#23:0 (b-/d2) |
| 5 | micro_IA40242807_2202#18:0 | micro_IA40244205_1717#24:0 | micro_IA40243514_1608#36:0 (b3/d-) |
| 6 | micro_IA40243511_2347#134:0 | micro_IA40243222_0374#138:2 | micro_IA40242806_2129#23:0 (b4/d-) |
| 7 | micro_IA40242807_2202#8:0 | micro_IA40244207_2484#25:0 | micro_IA40244213_1776#11:0 (b-/d4) |
| 8 | micro_IA40243215_0308#267:0 | micro_IA40244213_1769#16:0 | micro_IA40244205_1717#24:0 (b-/d5) |
| 9 | micro_IA40243514_1608#216:0 | micro_IA40242808_0721#155:0 | micro_IA40243511_2347#134:0 (b6/d-) |
| 10 | micro_IA40243220_0500#19:0 | micro_IA40244207_2478#47:0 | micro_IA40243222_0374#138:2 (b-/d6) |

## mq09  [gate: answer]
What did reports describe about occupational disease or workplace hazard exposure?
overlap RRF-vs-FTS@10 = 0.7; top-1 agree = False; dense-only in RRF top-10 = 3

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244206_2109#18:0 | micro_IA40244206_0473#10:0 | micro_IA40244204_1021#21:0 (b4/d55) |
| 2 | micro_IA40244204_2590#17:0 | micro_IA40243510_0825#0:0 | micro_IA40244204_2590#2:1 (b9/d71) |
| 3 | micro_IA40243304_2304#15:0 | micro_IA40242806_1241#2:0 | micro_IA40244206_2109#18:0 (b1/d-) |
| 4 | micro_IA40244204_1021#21:0 | micro_IA40243312_0741#84:0 | micro_IA40244206_0473#10:0 (b-/d1) |
| 5 | micro_IA40244204_1021#7:0 | micro_IA40244202_1418#475:0 | micro_IA40244204_2590#17:0 (b2/d-) |
| 6 | micro_IA40244202_1597#39:1 | micro_IA40243313_0920#0:0 | micro_IA40243304_2304#15:0 (b3/d-) |
| 7 | micro_IA40243219_0439#141:0 | micro_IA40244206_2118#63:0 | micro_IA40243312_0741#84:0 (b-/d4) |
| 8 | micro_IA40242806_2095#73:0 | micro_IA40242803_0242#0:0 | micro_IA40244204_1021#7:0 (b5/d-) |
| 9 | micro_IA40244204_2590#2:1 | micro_IA40243510_0825#2:0 | micro_IA40244202_1418#475:0 (b-/d5) |
| 10 | micro_IA40243215_0308#131:0 | micro_IA40242806_0832#0:0 | micro_IA40244202_1597#39:1 (b6/d-) |

## mq10  [gate: answer]
What did drinking-water quality guidelines recommend about contaminants?
overlap RRF-vs-FTS@10 = 0.3; top-1 agree = False; dense-only in RRF top-10 = 0

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243308_0263#9:0 | micro_IA40243302_1985#0:0 | micro_IA40243308_3620#149:0 (b14/d24) |
| 2 | micro_IA40243305_0185#42:1 | micro_IA40243512_0687#113:1 | micro_IA40243305_2838#122:0 (b5/d85) |
| 3 | micro_IA40243512_0687#83:0 | micro_IA40243315_1681#83:0 | micro_IA40243316_0931#5:1 (b47/d47) |
| 4 | micro_IA40244212_3181#219:0 | micro_IA40243315_1681#8:0 | micro_IA40243305_2838#122:1 (b8/d197) |
| 5 | micro_IA40243305_2838#122:0 | micro_IA40243209_1157#161:0 | micro_IA40242803_0016#44:2 (b53/d50) |
| 6 | micro_IA40243305_2838#158:1 | micro_IA40243315_1385#24:0 | micro_IA40243308_3620#148:0 (b27/d98) |
| 7 | micro_IA40243224_1696#9:0 | micro_IA40243222_2011#89:0 | micro_IA40243512_0687#300:0 (b137/d19) |
| 8 | micro_IA40243305_2838#122:1 | micro_IA40244215_0615#4:0 | micro_IA24402414_0343#53:0 (b41/d88) |
| 9 | micro_IA40244214_2518#39:0 | micro_IA40243223_0779#0:0 | micro_IA40243305_0185#38:0 (b71/d51) |
| 10 | micro_IA40243512_0687#291:0 | micro_IA40243512_0687#2:0 | micro_IA40243308_0263#9:0 (b1/d-) |

## mq11  [gate: answer]
How did reports describe municipal water treatment or sanitation infrastructure?
overlap RRF-vs-FTS@10 = 0.5; top-1 agree = False; dense-only in RRF top-10 = 2

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40242808_0735#4:1 | micro_IA40244213_0962#0:0 | micro_IA40243511_1728#3:0 (b5/d21) |
| 2 | micro_IA40243307_1279#52:0 | micro_IA40243315_1385#37:0 | micro_IA40243511_1728#4:0 (b19/d11) |
| 3 | micro_IA40243307_0987#49:0 | micro_IA40243217_0812#0:0 | micro_IA40243303_2181#6:0 (b39/d65) |
| 4 | micro_IA40242808_0735#4:0 | micro_IA40244213_0964#0:0 | micro_IA40242808_0735#4:1 (b1/d-) |
| 5 | micro_IA40243511_1728#3:0 | micro_IA40244201_0543#64:0 | micro_IA40243307_1279#52:0 (b2/d-) |
| 6 | micro_IA40243510_2672#9:0 | micro_IA40244213_0963#0:0 | micro_IA40243315_1385#37:0 (b-/d2) |
| 7 | micro_IA40243307_1279#91:1 | micro_IA40244213_0965#0:0 | micro_IA40243307_0987#49:0 (b3/d-) |
| 8 | micro_IA40242808_0735#5:0 | micro_IA40243315_1681#25:0 | micro_IA40242808_0735#4:0 (b4/d-) |
| 9 | micro_IA40242402_2140#45:0 | micro_IA40243217_0812#72:0 | micro_IA40243306_0039#46:2 (b146/d34) |
| 10 | micro_IA40244206_0879#14:1 | micro_IA40244213_0966#0:0 | micro_IA40244201_0543#64:0 (b-/d5) |

## mq12  [gate: answer]
What did chronic-disease surveillance reports describe about diabetes prevalence?
overlap RRF-vs-FTS@10 = 0.4; top-1 agree = False; dense-only in RRF top-10 = 3

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40242401_0609#35:1 | micro_IA40244211_2774#7:0 | micro_IA40243310_2721#33:0 (b5/d31) |
| 2 | micro_IA40244215_3064#35:1 | micro_IA40244205_1474#19:0 | micro_IA40244201_0515#32:0 (b63/d32) |
| 3 | micro_IA40243310_1232#30:1 | micro_IA40243313_3390#169:0 | micro_IA40244213_3183#23:1 (b56/d56) |
| 4 | micro_IA40242405_3345#11:0 | micro_IA40243315_1947#75:0 | micro_IA40242401_0609#35:1 (b1/d-) |
| 5 | micro_IA40243310_2721#33:0 | micro_IA40244204_3181#163:0 | micro_IA40244211_2774#7:0 (b-/d1) |
| 6 | micro_IA40244215_0913#24:1 | micro_IA40244209_2582#84:0 | micro_IA40243313_3390#50:0 (b34/d114) |
| 7 | micro_IA40242406_0347#41:0 | micro_IA40243312_1807#53:0 | micro_IA40244215_3064#35:1 (b2/d-) |
| 8 | micro_IA40244215_0913#24:2 | micro_IA40243308_0860#44:0 | micro_IA40243313_3390#169:0 (b-/d3) |
| 9 | micro_IA40242406_0347#24:0 | micro_IA40242802_0061#34:1 | micro_IA40242405_3345#11:0 (b4/d-) |
| 10 | micro_IA40243311_2729#65:0 | micro_IA40244213_3208#19:0 | micro_IA40244204_3181#163:0 (b-/d5) |

## mq13  [gate: answer]
What did reports describe about cancer incidence or cancer registry data?
overlap RRF-vs-FTS@10 = 0.4; top-1 agree = False; dense-only in RRF top-10 = 2

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244216_0406#47:0 | micro_IA40242808_0716#50:0 | micro_IA40243316_1325#12:0 (b21/d3) |
| 2 | micro_IA40243316_0548#40:0 | micro_IA40244211_2335#9:0 | micro_IA40244216_0409#41:0 (b14/d29) |
| 3 | micro_IA40243314_1726#32:0 | micro_IA40243316_1325#12:0 | micro_IA40242801_1553#66:0 (b40/d18) |
| 4 | micro_IA40244209_1543#28:0 | micro_IA40244211_2335#68:0 | micro_IA40243304_3168#7:0 (b71/d7) |
| 5 | micro_IA40244209_1543#29:0 | micro_IA40244206_2185#1:0 | micro_IA40242803_0845#48:0 (b9/d77) |
| 6 | micro_IA40244211_2696#2:0 | micro_IA40244211_2335#10:0 | micro_IA40244216_0406#47:0 (b1/d-) |
| 7 | micro_IA40244210_1093#41:1 | micro_IA40243304_3168#7:0 | micro_IA40242808_0716#50:0 (b-/d1) |
| 8 | micro_IA40242801_1553#70:0 | micro_IA40243313_0755#0:0 | micro_IA40243316_0548#40:0 (b2/d-) |
| 9 | micro_IA40242803_0845#48:0 | micro_IA40243212_0285#197:0 | micro_IA40244211_2335#9:0 (b-/d2) |
| 10 | micro_IA04243301_1823#55:0 | micro_IA40243306_3486#0:0 | micro_IA40243314_1726#32:0 (b3/d-) |

## mq14  [gate: answer]
How did reports describe cardiovascular disease surveillance?
overlap RRF-vs-FTS@10 = 0.6; top-1 agree = False; dense-only in RRF top-10 = 2

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243302_2545#147:1 | micro_IA40243315_1386#73:0 | micro_IA40242401_0607#11:3 (b5/d183) |
| 2 | micro_IA40244208_1663#35:0 | micro_IA40244210_0059#1:1 | micro_IA40244208_0136#24:1 (b28/d97) |
| 3 | micro_IA40243310_1232#11:1 | micro_IA40242803_1844#0:0 | micro_IA40244208_0138#22:2 (b21/d176) |
| 4 | micro_IA40242405_2178#7:1 | micro_IA40243515_0430#100:0 | micro_IA40243302_2545#147:1 (b1/d-) |
| 5 | micro_IA40242401_0607#11:3 | micro_IA40244210_0057#3:1 | micro_IA40243315_1386#73:0 (b-/d1) |
| 6 | micro_IA40243307_2074#49:0 | micro_IA40243212_2017#22:0 | micro_IA40244208_1663#35:0 (b2/d-) |
| 7 | micro_IA40244208_0138#22:1 | micro_IA40242405_0173#88:0 | micro_IA40243310_1232#11:1 (b3/d-) |
| 8 | micro_IA40244201_1558#2:1 | micro_IA40242803_1844#2:0 | micro_IA40242405_2178#7:1 (b4/d-) |
| 9 | micro_IA40244208_1665#15:1 | micro_IA40243304_2923#16:0 | micro_IA40244210_0057#3:1 (b-/d5) |
| 10 | micro_IA40242405_2177#7:1 | micro_IA40243315_0416#90:1 | micro_IA40243307_2074#49:0 (b6/d-) |

## mq15  [gate: answer]
What did provincial drug benefit formularies describe about covered medications?
overlap RRF-vs-FTS@10 = 0.5; top-1 agree = False; dense-only in RRF top-10 = 2

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244204_0077#32:1 | micro_IA40242801_1101#820:0 | micro_IA40243512_0127#34:0 (b28/d11) |
| 2 | micro_IA40244204_0077#37:1 | micro_IA40243302_2382#0:0 | micro_IA40242801_1101#819:0 (b21/d92) |
| 3 | micro_IA40242406_1041#5:0 | micro_IA40242406_1041#15:0 | micro_IA40242801_1101#67:0 (b22/d124) |
| 4 | micro_IA40242801_1101#87:1 | micro_IA40242406_3084#15:0 | micro_IA40244204_0077#32:1 (b1/d-) |
| 5 | micro_IA40243305_1227#38:0 | micro_IA40243302_2382#178:0 | micro_IA40242801_1101#820:0 (b-/d1) |
| 6 | micro_IA40243311_0888#17:1 | micro_IA40243302_2382#6:0 | micro_IA40244204_0077#37:1 (b2/d-) |
| 7 | micro_IA40243221_1410#17:0 | micro_IA40244205_1751#0:0 | micro_IA40242406_1041#5:0 (b3/d-) |
| 8 | micro_IA40242801_1101#508:0 | micro_IA40242807_0522#2:0 | micro_IA40242801_1101#87:1 (b4/d-) |
| 9 | micro_IA40242406_3084#6:1 | micro_IA40243302_2382#16:0 | micro_IA40243305_1227#38:0 (b5/d-) |
| 10 | micro_IA40244208_1724#22:0 | micro_IA40242807_0522#0:0 | micro_IA40243302_2382#178:0 (b-/d5) |

## mq16  [gate: answer]
How did reports describe pharmacare or drug program administration?
overlap RRF-vs-FTS@10 = 0.7; top-1 agree = False; dense-only in RRF top-10 = 2

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243314_1023#32:0 | micro_IA40242801_1101#820:0 | micro_IA40243314_1023#33:0 (b18/d136) |
| 2 | micro_IA40243314_1023#73:0 | micro_IA40244203_1774#3:0 | micro_IA40243314_1023#32:0 (b1/d-) |
| 3 | micro_IA40243311_1345#73:1 | micro_IA40244203_1787#1:0 | micro_IA40242801_1101#820:0 (b-/d1) |
| 4 | micro_IA40244203_1808#4:1 | micro_IA40244203_1797#3:0 | micro_IA40243314_1023#73:0 (b2/d-) |
| 5 | micro_IA40242808_1859#24:0 | micro_IA40244208_2017#24:0 | micro_IA40243311_1345#73:1 (b3/d-) |
| 6 | micro_IA40243314_1023#16:0 | micro_IA40244203_1781#3:0 | micro_IA40244203_1808#4:1 (b4/d-) |
| 7 | micro_IA40243221_1410#21:0 | micro_IA40244206_1648#58:0 | micro_IA40242808_1859#24:0 (b5/d-) |
| 8 | micro_IA40242801_0010#58:0 | micro_IA40244203_1797#5:0 | micro_IA40243314_1023#16:0 (b6/d-) |
| 9 | micro_IA40243314_1023#75:0 | micro_IA40244208_2017#82:0 | micro_IA40243221_1410#21:0 (b7/d-) |
| 10 | micro_IA40243314_1726#26:0 | micro_IA40243308_1673#116:0 | micro_IA40244206_1648#58:0 (b-/d7) |

## mq17  [gate: answer]
What did reports describe about long-term care standards or nursing home inspection?
overlap RRF-vs-FTS@10 = 0.5; top-1 agree = False; dense-only in RRF top-10 = 3

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243315_2537#36:0 | micro_IA40244210_2138#46:0 | micro_IA40244206_0068#6:0 (b7/d75) |
| 2 | micro_IA40242403_0974#65:0 | micro_IA40244210_2135#6:0 | micro_IA40243315_2537#36:0 (b1/d134) |
| 3 | micro_IA40243308_0861#15:0 | micro_IA40244210_2137#6:0 | micro_IA40244210_2135#5:0 (b14/d155) |
| 4 | micro_IA40244206_3032#217:0 | micro_IA40244210_2137#42:0 | micro_IA40244210_2136#5:0 (b12/d180) |
| 5 | micro_IA40244206_3360#104:0 | micro_IA40244210_2135#45:0 | micro_IA40244210_2138#46:0 (b-/d1) |
| 6 | micro_IA40244209_0419#9:2 | micro_IA40244210_2136#50:0 | micro_IA40242403_0974#65:0 (b2/d-) |
| 7 | micro_IA40244206_0068#6:0 | micro_IA40244210_2135#18:0 | micro_IA40244210_2135#6:0 (b-/d2) |
| 8 | micro_IA40243303_2037#58:0 | micro_IA40244210_2137#18:0 | micro_IA40243308_0861#15:0 (b3/d-) |
| 9 | micro_IA40243216_1924#23:0 | micro_IA40244210_2138#18:0 | micro_IA40244210_2137#6:0 (b-/d3) |
| 10 | micro_IA40244207_2693#47:3 | micro_IA40243223_1300#48:0 | micro_IA40244206_3032#217:0 (b4/d-) |

## mq18  [gate: answer]
How did reports describe community mental health service organization?
overlap RRF-vs-FTS@10 = 0.6; top-1 agree = False; dense-only in RRF top-10 = 3

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40242805_1353#4:1 | micro_IA40243223_0344#12:0 | micro_IA40244205_0089#62:0 (b20/d154) |
| 2 | micro_IA40243312_0317#162:0 | micro_IA40242807_1437#0:0 | micro_IA40242805_1353#4:1 (b1/d-) |
| 3 | micro_IA40244211_0652#27:0 | micro_IA40244214_1685#77:0 | micro_IA40243223_0344#12:0 (b-/d1) |
| 4 | micro_IA40244210_0016#183:0 | micro_IA40242808_1657#0:0 | micro_IA40243312_0317#162:0 (b2/d-) |
| 5 | micro_IA40243308_0451#75:0 | micro_IA40243509_2378#49:0 | micro_IA40244211_0652#27:0 (b3/d-) |
| 6 | micro_IA40244206_3244#13:0 | micro_IA40243303_3038#0:0 | micro_IA40244214_1685#77:0 (b-/d3) |
| 7 | micro_IA40244208_2492#27:2 | micro_IA40244204_3037#21:0 | micro_IA40244210_0016#183:0 (b4/d-) |
| 8 | micro_IA40243313_2126#7:0 | micro_IA40242808_1657#20:0 | micro_IA40243308_0451#75:0 (b5/d-) |
| 9 | micro_IA40242805_1647#32:0 | micro_IA40243313_0307#162:0 | micro_IA40243509_2378#49:0 (b-/d5) |
| 10 | micro_IA40243305_2229#18:0 | micro_IA40243312_3235#190:0 | micro_IA40244206_3244#13:0 (b6/d-) |

## mq19  [gate: answer]
What did reports describe about mental health service delivery models?
overlap RRF-vs-FTS@10 = 0.5; top-1 agree = False; dense-only in RRF top-10 = 3

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243307_0467#73:1 | micro_IA40243223_0344#12:0 | micro_IA40242808_1657#24:0 (b37/d3) |
| 2 | micro_IA40244213_0344#21:1 | micro_IA40244214_1685#77:0 | micro_IA40243302_0186#134:0 (b5/d122) |
| 3 | micro_IA40244215_3165#22:1 | micro_IA40242808_1657#24:0 | micro_IA40243313_2126#76:0 (b61/d35) |
| 4 | micro_IA40243219_1161#8:0 | micro_IA40243312_3235#190:0 | micro_IA40243307_0467#73:1 (b1/d-) |
| 5 | micro_IA40243302_0186#134:0 | micro_IA40243312_0317#142:0 | micro_IA40243223_0344#12:0 (b-/d1) |
| 6 | micro_IA40243301_0937#11:0 | micro_IA40243219_1161#21:0 | micro_IA40244213_0344#21:1 (b2/d-) |
| 7 | micro_IA40242802_1081#24:1 | micro_IA40243313_0307#102:0 | micro_IA40244214_1685#77:0 (b-/d2) |
| 8 | micro_IA40244211_2470#22:1 | micro_IA40243312_0318#85:0 | micro_IA40244215_3165#22:1 (b3/d-) |
| 9 | micro_IA40242802_1081#26:0 | micro_IA40242405_3449#21:0 | micro_IA40243219_1161#8:0 (b4/d-) |
| 10 | micro_IA40242802_1081#27:0 | micro_IA40243313_0307#162:0 | micro_IA40243312_3235#190:0 (b-/d4) |

## mq20  [gate: answer]
What did reports describe about physician or nurse supply and health human resources?
overlap RRF-vs-FTS@10 = 0.8; top-1 agree = True; dense-only in RRF top-10 = 2

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243301_2600#24:0 | micro_IA40243510_1810#8:0 | micro_IA40243301_2600#24:0 (b1/d-) |
| 2 | micro_IA40242803_1400#41:0 | micro_IA40244203_2004#23:0 | micro_IA40242803_1400#41:0 (b2/d-) |
| 3 | micro_IA40242803_1400#40:0 | micro_IA40243509_1532#0:0 | micro_IA40242803_1400#40:0 (b3/d-) |
| 4 | micro_IA40243301_0169#18:0 | micro_IA40243217_1858#3:0 | micro_IA40243301_0169#18:0 (b4/d-) |
| 5 | micro_IA40243313_3495#60:0 | micro_IA40243221_2523#4:0 | micro_IA40243313_3495#60:0 (b5/d-) |
| 6 | micro_IA40242803_1400#39:0 | micro_IA40243511_2198#0:0 | micro_IA40242803_1400#39:0 (b6/d-) |
| 7 | micro_IA40243314_1727#63:1 | micro_IA40244203_2017#15:0 | micro_IA40243314_1727#63:1 (b7/d-) |
| 8 | micro_IA40243312_2777#45:1 | micro_IA40244215_0079#39:0 | micro_IA40243312_2777#45:1 (b8/d-) |
| 9 | micro_IA40243309_0344#138:0 | micro_IA40243310_2698#52:0 | micro_IA40244215_0079#39:0 (b-/d8) |
| 10 | micro_IA40243222_0288#28:0 | micro_IA40243223_1300#48:0 | micro_IA40244203_2004#23:0 (b-/d2) |

## mq21  [gate: answer]
How did reports describe food safety inspection or foodborne illness investigation?
overlap RRF-vs-FTS@10 = 0.7; top-1 agree = False; dense-only in RRF top-10 = 1

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244211_1710#29:0 | micro_IA40244208_2616#5:0 | micro_IA40244207_1979#33:2 (b6/d23) |
| 2 | micro_IA40243315_1929#148:2 | micro_IA40243218_0443#2:0 | micro_IA40243304_1129#37:1 (b25/d89) |
| 3 | micro_IA40244206_0402#26:1 | micro_IA40244213_1543#2:0 | micro_IA40244211_1710#29:0 (b1/d-) |
| 4 | micro_IA40244207_1977#6:1 | micro_IA40244207_1977#2:0 | micro_IA40244208_2616#5:0 (b-/d1) |
| 5 | micro_IA40243312_2683#39:0 | micro_IA40244211_1712#2:0 | micro_IA40244206_0402#26:1 (b3/d-) |
| 6 | micro_IA40244207_1979#33:2 | micro_IA40244207_1975#2:0 | micro_IA40244207_1977#6:1 (b4/d-) |
| 7 | micro_IA40243312_2682#84:0 | micro_IA40244211_1710#2:0 | micro_IA40244207_1977#27:0 (b61/d77) |
| 8 | micro_IA40243224_0279#65:0 | micro_IA40244207_1979#2:0 | micro_IA40243312_2683#39:0 (b5/d-) |
| 9 | micro_IA40243315_1929#148:1 | micro_IA40244216_1161#0:0 | micro_IA40243312_2682#84:0 (b7/d-) |
| 10 | micro_IA40244211_1712#40:1 | micro_IA40243312_1312#34:0 | micro_IA40243224_0279#65:0 (b8/d-) |

## mq22  [gate: answer]
What did reports describe about tobacco control or smoking reduction programs?
overlap RRF-vs-FTS@10 = 0.3; top-1 agree = False; dense-only in RRF top-10 = 0

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244205_0170#202:0 | micro_IA40243313_1139#93:0 | micro_IA40243308_1213#20:0 (b6/d32) |
| 2 | micro_IA40244205_0170#71:0 | micro_IA40242808_0037#0:0 | micro_IA40243217_1390#5:0 (b65/d11) |
| 3 | micro_IA40243217_1390#5:1 | micro_IA40243311_1188#71:0 | micro_IA40244205_0170#202:0 (b1/d184) |
| 4 | micro_IA40243301_2373#141:1 | micro_IA40243315_1762#0:0 | micro_IA40244205_0170#66:0 (b12/d105) |
| 5 | micro_IA40243314_2434#15:0 | micro_IA40244205_0170#99:0 | micro_IA40243312_1807#48:0 (b92/d17) |
| 6 | micro_IA40243308_1213#20:0 | micro_IA40244203_3265#0:0 | micro_IA40244216_3432#19:1 (b107/d22) |
| 7 | micro_IA40243315_1762#10:0 | micro_IA40243306_2969#2:1 | micro_IA40243308_1035#15:0 (b24/d103) |
| 8 | micro_IA40244209_2051#119:1 | micro_IA40243308_1035#0:0 | micro_IA40243315_1762#4:0 (b73/d42) |
| 9 | micro_IA40244210_3033#19:1 | micro_IA40244212_1246#26:1 | micro_IA40242806_1299#15:0 (b28/d132) |
| 10 | micro_IA40243314_2436#9:1 | micro_IA40243217_1390#2:0 | micro_IA40244205_0170#71:0 (b2/d-) |

## mq23  [gate: answer]
How did reports describe maternal or prenatal health programs?
overlap RRF-vs-FTS@10 = 0.4; top-1 agree = False; dense-only in RRF top-10 = 1

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244206_2613#114:0 | micro_IA40243515_0430#4:0 | micro_IA40243513_0390#64:0 (b10/d46) |
| 2 | micro_IA40243313_0041#24:0 | micro_IA40243310_1342#43:0 | micro_IA40243313_0041#65:0 (b52/d9) |
| 3 | micro_IA40244206_2613#113:0 | micro_IA40244206_0111#323:0 | micro_IA40243313_0041#68:0 (b33/d38) |
| 4 | micro_IA40244206_2613#86:0 | micro_IA40243301_2373#116:1 | micro_IA40243313_0041#66:0 (b48/d14) |
| 5 | micro_IA40244201_2639#5:0 | micro_IA40243303_2485#57:0 | micro_IA40243215_1676#73:0 (b141/d7) |
| 6 | micro_IA40244206_2613#109:0 | micro_IA40243511_1288#81:2 | micro_IA40243301_2373#40:0 (b17/d153) |
| 7 | micro_IA40244206_2613#108:0 | micro_IA40243215_1676#73:0 | micro_IA40244206_2613#114:0 (b1/d-) |
| 8 | micro_IA40244209_2051#103:0 | micro_IA40243301_2373#112:0 | micro_IA40243313_0041#24:0 (b2/d-) |
| 9 | micro_IA40244216_2885#36:0 | micro_IA40243313_0041#65:0 | micro_IA40243310_1342#43:0 (b-/d2) |
| 10 | micro_IA40243513_0390#64:0 | micro_IA40243308_1613#54:0 | micro_IA40244206_2613#113:0 (b3/d-) |

## mq25  [gate: answer]
What did reports describe about Ontario Local Health Integration Networks?
overlap RRF-vs-FTS@10 = 0.2; top-1 agree = False; dense-only in RRF top-10 = 1

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA04243301_1611#211:1 | micro_IA40244212_0308#8:0 | micro_IA40244214_1723#3:0 (b21/d11) |
| 2 | micro_IA40244212_0308#8:0 | micro_IA40242402_1675#47:0 | micro_IA40244214_1724#3:0 (b17/d16) |
| 3 | micro_IA40244206_3362#93:0 | micro_IA40242402_3359#0:0 | micro_IA40244215_2892#5:2 (b20/d39) |
| 4 | micro_IA40244216_3022#3:2 | micro_IA40242402_1678#0:0 | micro_IA40244214_1602#49:1 (b33/d33) |
| 5 | micro_IA40244212_0325#28:0 | micro_IA40244202_1394#0:0 | micro_IA40244208_2990#135:0 (b24/d64) |
| 6 | micro_IA40244212_0325#28:1 | micro_IA40242403_2665#0:0 | micro_IA40244212_0315#10:0 (b13/d127) |
| 7 | micro_IA40244214_1602#47:0 | micro_IA40242405_3457#61:0 | micro_IA04243301_1611#211:1 (b1/d-) |
| 8 | micro_IA40244212_0315#57:0 | micro_IA40242403_2663#39:0 | micro_IA40244212_0330#8:0 (b52/d74) |
| 9 | micro_IA04244212_1865#19:0 | micro_IA40242405_3450#0:0 | micro_IA40244212_0308#8:0 (b2/d1) |
| 10 | micro_IA40244212_0315#2:0 | micro_IA40244214_1722#1:0 | micro_IA40242402_1675#47:0 (b-/d2) |

## mq26  [gate: answer]
How did reports describe regional health authority organization?
overlap RRF-vs-FTS@10 = 0.4; top-1 agree = False; dense-only in RRF top-10 = 5

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244215_0015#21:0 | micro_IA40242405_0121#38:0 | micro_IA40243310_2700#10:1 (b19/d183) |
| 2 | micro_IA40242805_1353#4:1 | micro_IA40242401_0551#52:0 | micro_IA40244215_0015#21:0 (b1/d-) |
| 3 | micro_IA40244213_0210#22:0 | micro_IA40244213_0231#17:0 | micro_IA40242405_0121#38:0 (b-/d1) |
| 4 | micro_IA44420209_2953#25:1 | micro_IA40242403_0297#48:0 | micro_IA40242805_1353#4:1 (b2/d-) |
| 5 | micro_IA40242808_0969#152:0 | micro_IA40244212_3181#298:0 | micro_IA40242401_0551#52:0 (b-/d2) |
| 6 | micro_IA40243217_0556#298:0 | micro_IA40243214_1318#26:0 | micro_IA40244213_0210#22:0 (b3/d-) |
| 7 | micro_IA40244210_3444#11:0 | micro_IA40243309_1880#267:0 | micro_IA40244213_0231#17:0 (b-/d3) |
| 8 | micro_IA40243509_1805#133:0 | micro_IA40243313_2302#22:0 | micro_IA44420209_2953#25:1 (b4/d-) |
| 9 | micro_IA40244210_1389#16:1 | micro_IA40243315_0456#183:0 | micro_IA40242403_0297#48:0 (b-/d4) |
| 10 | micro_IA40244214_2768#6:1 | micro_IA40243310_2698#52:0 | micro_IA40244212_3181#298:0 (b-/d5) |

## mq27  [gate: answer]
What did reports describe about health-system restructuring or regionalization?
overlap RRF-vs-FTS@10 = 0.5; top-1 agree = False; dense-only in RRF top-10 = 5

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243315_2537#36:1 | micro_IA40242401_0551#52:0 | micro_IA40243305_0633#28:0 (b2/d108) |
| 2 | micro_IA40243305_0633#28:0 | micro_IA40242403_0297#48:0 | micro_IA40243315_2537#36:1 (b1/d-) |
| 3 | micro_IA40243306_2345#118:0 | micro_IA40242405_0121#38:0 | micro_IA40242401_0551#52:0 (b-/d1) |
| 4 | micro_IA40243302_0055#29:1 | micro_IA40243313_2302#22:0 | micro_IA40242403_0297#48:0 (b-/d2) |
| 5 | micro_IA40243301_2964#29:1 | micro_IA40243315_0456#183:0 | micro_IA40243306_2345#118:0 (b3/d-) |
| 6 | micro_IA40243306_3359#36:1 | micro_IA40242805_0909#8:0 | micro_IA40242405_0121#38:0 (b-/d3) |
| 7 | micro_IA40243310_2844#3:0 | micro_IA40244213_0231#17:0 | micro_IA40243302_0055#29:1 (b4/d-) |
| 8 | micro_IA40243310_2844#2:0 | micro_IA40243302_2047#0:0 | micro_IA40243313_2302#22:0 (b-/d4) |
| 9 | micro_IA40243301_1052#3:1 | micro_IA40244212_0317#0:0 | micro_IA40243301_2964#29:1 (b5/d-) |
| 10 | micro_IA40243302_0055#57:0 | micro_IA40243310_2698#52:0 | micro_IA40243315_0456#183:0 (b-/d5) |

## mq28  [gate: abstain, uncovered: reports]
What did reports describe about hospital funding or global budgets?
overlap RRF-vs-FTS@10 = 0.5; top-1 agree = False; dense-only in RRF top-10 = 3

(gate abstained: possibly-correct thin coverage, not assumed retrieval failure)

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243306_3426#50:0 | micro_IA40243220_0426#86:0 | micro_IA40243221_1213#3:1 (b18/d156) |
| 2 | micro_IA40243306_3426#49:1 | micro_IA40244203_2535#14:0 | micro_IA40243306_3426#50:0 (b1/d-) |
| 3 | micro_IA40242807_0528#80:1 | micro_IA40243209_1157#96:0 | micro_IA40243220_0426#86:0 (b-/d1) |
| 4 | micro_IA40243221_1213#36:0 | micro_IA40244203_2535#8:0 | micro_IA40243306_3426#49:1 (b2/d-) |
| 5 | micro_IA40242807_1283#47:1 | micro_IA40243215_0266#195:0 | micro_IA40242807_0528#80:1 (b3/d-) |
| 6 | micro_IA40243306_3426#49:0 | micro_IA40244204_1385#12:0 | micro_IA40243209_1157#96:0 (b-/d3) |
| 7 | micro_IA40242807_0528#80:0 | micro_IA40244204_1385#18:0 | micro_IA40242807_1283#55:0 (b54/d83) |
| 8 | micro_IA40242804_0524#9:1 | micro_IA40244206_0050#16:0 | micro_IA40243221_1213#36:0 (b4/d-) |
| 9 | micro_IA40242806_2128#29:1 | micro_IA40243220_0426#379:0 | micro_IA40242807_1283#47:1 (b5/d-) |
| 10 | micro_IA40242807_1283#47:0 | micro_IA40243218_0384#158:0 | micro_IA40243215_0266#195:0 (b-/d5) |

## mq29  [gate: answer]
What did reports describe about public hospital insurance administration?
overlap RRF-vs-FTS@10 = 0.6; top-1 agree = True; dense-only in RRF top-10 = 4

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244206_3360#208:1 | micro_IA40243218_0384#21:0 | micro_IA40244206_3360#208:1 (b1/d-) |
| 2 | micro_IA40244206_3362#210:1 | micro_IA40243223_0598#21:0 | micro_IA40243218_0384#21:0 (b-/d1) |
| 3 | micro_IA40244206_3360#220:0 | micro_IA40243218_0384#158:0 | micro_IA40244206_3362#210:1 (b2/d-) |
| 4 | micro_IA40243312_0821#229:1 | micro_IA40243223_0598#158:0 | micro_IA40243223_0598#21:0 (b-/d2) |
| 5 | micro_IA40243303_0820#173:0 | micro_IA40243509_1532#0:0 | micro_IA40244206_3360#220:0 (b3/d-) |
| 6 | micro_IA40244214_3053#62:0 | micro_IA40243223_0598#142:0 | micro_IA40243218_0384#158:0 (b-/d3) |
| 7 | micro_IA40244214_3051#62:0 | micro_IA40244203_2535#14:0 | micro_IA40243312_0821#229:1 (b4/d-) |
| 8 | micro_IA40244206_3362#222:0 | micro_IA40243215_0266#195:0 | micro_IA40243223_0598#158:0 (b-/d4) |
| 9 | micro_IA40244214_3053#128:1 | micro_IA40243209_1157#96:0 | micro_IA40243303_0820#173:0 (b5/d-) |
| 10 | micro_IA40244206_3360#86:0 | micro_IA40244204_1385#12:0 | micro_IA40244214_3053#62:0 (b6/d-) |

## mq30  [gate: answer]
What did reports describe about home care or continuing care programs?
overlap RRF-vs-FTS@10 = 0.5; top-1 agree = True; dense-only in RRF top-10 = 5

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA04243301_2053#52:0 | micro_IA40243509_0235#50:0 | micro_IA04243301_2053#52:0 (b1/d-) |
| 2 | micro_IA40243309_1637#25:0 | micro_IA40244205_1012#50:0 | micro_IA40243509_0235#50:0 (b-/d1) |
| 3 | micro_IA04243301_2053#58:0 | micro_IA40243314_3603#29:0 | micro_IA40243309_1637#25:0 (b2/d-) |
| 4 | micro_IA40243301_2107#16:0 | micro_IA40243314_3605#24:0 | micro_IA40244205_1012#50:0 (b-/d2) |
| 5 | micro_IA04243301_2053#60:1 | micro_IA40242405_3449#18:0 | micro_IA04243301_2053#58:0 (b3/d-) |
| 6 | micro_IA40243224_0257#29:1 | micro_IA40244213_0360#6:0 | micro_IA40243314_3603#29:0 (b-/d3) |
| 7 | micro_IA40243513_2603#84:0 | micro_IA40243509_0102#62:0 | micro_IA40243301_2107#16:0 (b4/d-) |
| 8 | micro_IA40243311_3293#16:0 | micro_IA40244215_0681#54:0 | micro_IA40243314_3605#24:0 (b-/d4) |
| 9 | micro_IA40243219_1332#2:0 | micro_IA40243514_2596#144:0 | micro_IA04243301_2053#60:1 (b5/d-) |
| 10 | micro_IA04243301_2053#51:0 | micro_IA40242807_2120#0:0 | micro_IA40242405_3449#18:0 (b-/d5) |

## mq31  [gate: answer]
What did reports describe about air quality or environmental health hazards?
overlap RRF-vs-FTS@10 = 0.6; top-1 agree = True; dense-only in RRF top-10 = 4

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40242801_0933#44:1 | micro_IA40242802_0088#90:0 | micro_IA40242801_0933#44:1 (b1/d-) |
| 2 | micro_IA40243302_3338#4:0 | micro_IA40242404_3619#108:0 | micro_IA40243302_3338#4:0 (b2/d-) |
| 3 | micro_IA40243209_1069#128:0 | micro_IA40242404_3619#27:0 | micro_IA40242404_3619#108:0 (b-/d2) |
| 4 | micro_IA40243302_1376#6:0 | micro_IA40243221_1392#132:0 | micro_IA40243209_1069#128:0 (b3/d-) |
| 5 | micro_IA40243209_1157#190:0 | micro_IA40243217_1858#23:0 | micro_IA40242404_3619#27:0 (b-/d3) |
| 6 | micro_IA40243222_1316#346:0 | micro_IA40243221_2523#27:0 | micro_IA40243302_1376#6:0 (b4/d-) |
| 7 | micro_IA40244203_0222#11:0 | micro_IA40243511_2204#12:0 | micro_IA40243221_1392#132:0 (b-/d4) |
| 8 | micro_IA40243214_1609#24:0 | micro_IA40243219_1297#61:0 | micro_IA40243209_1157#190:0 (b5/d-) |
| 9 | micro_IA40242807_1071#36:1 | micro_IA40243308_0748#14:0 | micro_IA40243217_1858#23:0 (b-/d5) |
| 10 | micro_IA40244203_1411#47:0 | micro_IA40243310_1941#14:0 | micro_IA40243222_1316#346:0 (b6/d-) |

## mq32  [gate: answer]
What did reports describe about lead exposure or environmental contaminants?
overlap RRF-vs-FTS@10 = 0.5; top-1 agree = False; dense-only in RRF top-10 = 4

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243306_3414#27:0 | micro_IA40243221_1588#15:1 | micro_IA40243213_0141#360:0 (b29/d48) |
| 2 | micro_IA40243217_0228#14:0 | micro_IA40243213_0141#153:1 | micro_IA40243306_3414#27:0 (b1/d-) |
| 3 | micro_IA40242806_2171#36:0 | micro_IA40243213_0141#152:1 | micro_IA40243221_1588#15:1 (b-/d1) |
| 4 | micro_IA40244214_1056#297:1 | micro_IA40243213_0141#225:1 | micro_IA40243217_0228#14:0 (b2/d-) |
| 5 | micro_IA40242403_0516#98:0 | micro_IA40244206_1112#0:0 | micro_IA40243213_0141#153:1 (b-/d2) |
| 6 | micro_IA40242405_0584#40:0 | micro_IA40243221_1588#69:1 | micro_IA40242806_2171#36:0 (b3/d-) |
| 7 | micro_IA40244216_0324#15:0 | micro_IA40243221_1588#149:0 | micro_IA40243213_0141#152:1 (b-/d3) |
| 8 | micro_IA40243215_1677#102:0 | micro_IA40243221_1588#37:1 | micro_IA40244214_1056#297:1 (b4/d-) |
| 9 | micro_IA40243308_0253#269:1 | micro_IA40242805_2049#59:0 | micro_IA40243213_0141#225:1 (b-/d4) |
| 10 | micro_IA40244208_1243#28:0 | micro_IA40243213_0141#153:0 | micro_IA40242403_0516#98:0 (b5/d-) |

## mq33  [gate: answer]
What did reports describe about nutrition or dietary guidance?
overlap RRF-vs-FTS@10 = 0.6; top-1 agree = True; dense-only in RRF top-10 = 3

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40242406_0339#53:0 | micro_IA40243307_0887#192:0 | micro_IA40242406_0339#53:0 (b1/d-) |
| 2 | micro_IA40243303_0600#43:0 | micro_IA40243307_0887#132:0 | micro_IA40243303_0600#43:0 (b2/d-) |
| 3 | micro_IA40243310_2369#58:1 | micro_IA40243307_0887#190:0 | micro_IA40243310_2369#58:1 (b3/d-) |
| 4 | micro_IA40242406_2505#8:1 | micro_IA40243307_0887#176:0 | micro_IA40243307_0887#190:0 (b-/d3) |
| 5 | micro_IA40244213_0514#33:1 | micro_IA40243307_0887#7:0 | micro_IA40242406_2505#8:1 (b4/d-) |
| 6 | micro_IA40244213_0517#55:1 | micro_IA40243307_0887#150:0 | micro_IA40243307_0887#192:0 (b-/d1) |
| 7 | micro_IA40243211_0746#29:0 | micro_IA40243223_0777#2:0 | micro_IA40243513_1483#66:0 (b8/d-) |
| 8 | micro_IA40243513_1483#66:0 | micro_IA40243223_1196#2:0 | micro_IA40243307_0887#132:0 (b-/d2) |
| 9 | micro_IA40243315_1929#34:2 | micro_IA40243315_1386#43:0 | micro_IA40243315_1929#34:2 (b9/d-) |
| 10 | micro_IA40244213_0517#45:2 | micro_IA40243307_0887#120:0 | micro_IA40242406_0339#32:0 (b11/d-) |

## mq34  [gate: answer]
What did reports describe about health promotion or disease prevention campaigns?
overlap RRF-vs-FTS@10 = 0.5; top-1 agree = True; dense-only in RRF top-10 = 5

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243311_2678#4:0 | micro_IA40243222_1411#25:0 | micro_IA40243311_2678#4:0 (b1/d-) |
| 2 | micro_IA40243310_0630#26:1 | micro_IA40244215_0079#39:0 | micro_IA40243222_1411#25:0 (b-/d1) |
| 3 | micro_IA40243308_0381#31:1 | micro_IA40243306_3426#256:0 | micro_IA40243310_0630#26:1 (b2/d-) |
| 4 | micro_IA40243306_3486#17:0 | micro_IA40244215_0079#9:0 | micro_IA40244215_0079#39:0 (b-/d2) |
| 5 | micro_IA40243310_0630#26:0 | micro_IA40243224_0247#28:0 | micro_IA40243308_0381#31:1 (b3/d-) |
| 6 | micro_IA40243308_0381#28:0 | micro_IA40243220_0426#14:0 | micro_IA40243306_3426#256:0 (b-/d3) |
| 7 | micro_IA40242801_0010#39:1 | micro_IA40244212_0321#31:0 | micro_IA40243306_3486#17:0 (b4/d-) |
| 8 | micro_IA40242402_0620#10:0 | micro_IA40243223_1862#35:0 | micro_IA40244215_0079#9:0 (b-/d4) |
| 9 | micro_IA40243314_2435#10:0 | micro_IA40244214_1594#31:0 | micro_IA40243310_0630#26:0 (b5/d-) |
| 10 | micro_IA40243314_2434#22:0 | micro_IA40244215_0079#8:0 | micro_IA40243224_0247#28:0 (b-/d5) |

## mq35  [gate: answer]
What did reports describe about emergency preparedness or pandemic planning?
overlap RRF-vs-FTS@10 = 0.3; top-1 agree = False; dense-only in RRF top-10 = 0

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244204_1315#82:0 | micro_IA40244210_1412#23:0 | micro_IA40244208_1667#17:1 (b9/d34) |
| 2 | micro_IA40244206_0014#82:0 | micro_IA40243310_2269#122:0 | micro_IA40243313_3110#20:0 (b40/d9) |
| 3 | micro_IA40424201_0676#45:1 | micro_IA40243215_1384#233:0 | micro_IA40424201_0676#45:1 (b3/d77) |
| 4 | micro_IA40244205_2447#57:2 | micro_IA40243310_1720#106:0 | micro_IA40243315_0383#24:0 (b63/d8) |
| 5 | micro_IA40244203_2479#79:0 | micro_IA40244203_2445#68:0 | micro_IA40244204_1886#22:0 (b64/d10) |
| 6 | micro_IA40242405_0802#23:0 | micro_IA40243312_1599#405:0 | micro_IA40242406_2170#33:0 (b70/d12) |
| 7 | micro_IA40244208_0142#34:0 | micro_IA40244215_3752#310:0 | micro_IA40244208_0142#34:0 (b7/d92) |
| 8 | micro_IA40424201_0676#45:2 | micro_IA40243315_0383#24:0 | micro_IA40243315_0373#16:1 (b23/d55) |
| 9 | micro_IA40244208_1667#17:1 | micro_IA40243313_3110#20:0 | micro_IA40244203_0442#167:0 (b14/d115) |
| 10 | micro_IA40243314_1727#29:1 | micro_IA40244204_1886#22:0 | micro_IA40244208_1663#54:1 (b83/d23) |

## mq36  [gate: answer]
What did reports describe about antimicrobial resistance or antibiotic use?
overlap RRF-vs-FTS@10 = 0.3; top-1 agree = False; dense-only in RRF top-10 = 0

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244215_3283#22:1 | micro_IA40242406_1672#12:0 | micro_IA40242402_2648#6:1 (b3/d3) |
| 2 | micro_IA40243303_1290#9:1 | micro_IA40242406_0714#2:0 | micro_IA40244215_3283#6:0 (b21/d6) |
| 3 | micro_IA40242402_2648#6:1 | micro_IA40242402_2648#6:1 | micro_IA40244215_3283#41:0 (b14/d18) |
| 4 | micro_IA40244203_0224#29:0 | micro_IA40244203_0228#34:1 | micro_IA40242402_2648#2:0 (b18/d15) |
| 5 | micro_IA40244215_3283#0:0 | micro_IA40242402_2648#22:0 | micro_IA40244215_3283#43:0 (b8/d35) |
| 6 | micro_IA40244215_3283#42:0 | micro_IA40244215_3283#6:0 | micro_IA40244215_3283#42:0 (b6/d51) |
| 7 | micro_IA40244203_0224#77:2 | micro_IA40242406_0714#6:0 | micro_IA40242402_2648#22:0 (b92/d5) |
| 8 | micro_IA40244215_3283#43:0 | micro_IA40242406_0714#0:0 | micro_IA40244203_0224#22:1 (b69/d17) |
| 9 | micro_IA40244203_0224#38:2 | micro_IA40244203_0224#78:0 | micro_IA40244204_2960#9:0 (b56/d26) |
| 10 | micro_IA40242402_2648#7:0 | micro_IA40242405_0795#12:0 | micro_IA40243303_1290#13:0 (b31/d48) |

## mq37  [gate: answer]
What did reports describe about West Nile virus or vector-borne disease surveillance?
overlap RRF-vs-FTS@10 = 0.2; top-1 agree = False; dense-only in RRF top-10 = 0

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40242401_0631#0:0 | micro_IA40244204_3181#222:0 | micro_IA40242405_2113#7:0 (b7/d10) |
| 2 | micro_IA40242401_0632#26:1 | micro_IA40244204_3181#224:0 | micro_IA40242405_2113#8:0 (b8/d14) |
| 3 | micro_IA40242405_0794#19:0 | micro_IA40243312_2850#22:0 | micro_IA40243315_1441#24:0 (b33/d18) |
| 4 | micro_IA40243307_0508#48:1 | micro_IA40243308_2950#0:0 | micro_IA40244204_1315#20:0 (b41/d24) |
| 5 | micro_IA40242402_3364#34:1 | micro_IA40244206_0014#21:1 | micro_IA40242405_0794#8:2 (b37/d27) |
| 6 | micro_IA40242405_0794#25:0 | micro_IA40243305_0421#0:0 | micro_IA40242405_2113#11:0 (b13/d70) |
| 7 | micro_IA40242405_2113#7:0 | micro_IA40243312_2922#26:1 | micro_IA40244206_0014#21:1 (b109/d5) |
| 8 | micro_IA40242405_2113#8:0 | micro_IA40244206_1193#28:1 | micro_IA40244214_1887#29:0 (b53/d21) |
| 9 | micro_IA40242405_2113#1:0 | micro_IA40244206_1192#28:0 | micro_IA40243305_0421#4:0 (b24/d48) |
| 10 | micro_IA40244214_3726#15:0 | micro_IA40242405_2113#7:0 | micro_IA40244205_1538#23:1 (b31/d41) |

## mq38  [gate: answer]
What did reports describe about measles or mumps outbreak response?
overlap RRF-vs-FTS@10 = 0.3; top-1 agree = False; dense-only in RRF top-10 = 0

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244216_2194#18:2 | micro_IA40244215_3275#41:0 | micro_IA40243306_2473#195:1 (b13/d17) |
| 2 | micro_IA40243306_2473#178:1 | micro_IA40243315_2333#2:2 | micro_IA40244215_3275#22:0 (b18/d14) |
| 3 | micro_IA40244215_3275#27:0 | micro_IA40243315_2410#6:0 | micro_IA40242402_2632#11:2 (b16/d38) |
| 4 | micro_IA40243306_2473#197:0 | micro_IA40244215_3275#43:0 | micro_IA40244215_3275#9:1 (b45/d13) |
| 5 | micro_IA40242402_2632#10:0 | micro_IA40244215_3275#34:0 | micro_IA40244214_2620#11:1 (b8/d60) |
| 6 | micro_IA40243315_2310#3:0 | micro_IA40243307_1232#71:1 | micro_IA40243306_2473#196:1 (b7/d98) |
| 7 | micro_IA40243306_2473#196:1 | micro_IA40242805_1852#5:1 | micro_IA40244215_3275#9:0 (b108/d9) |
| 8 | micro_IA40244214_2620#11:1 | micro_IA40243303_0763#114:0 | micro_IA40244216_2194#18:2 (b1/d191) |
| 9 | micro_IA40243315_2520#7:0 | micro_IA40244215_3275#9:0 | micro_IA40243513_0439#13:1 (b34/d43) |
| 10 | micro_IA40243306_2473#178:0 | micro_IA40244215_3275#39:0 | micro_IA40244215_3275#46:0 (b49/d30) |

## mq39  [gate: answer]
What did reports describe about health surveillance data systems or reporting?
overlap RRF-vs-FTS@10 = 0.5; top-1 agree = True; dense-only in RRF top-10 = 5

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243305_0612#67:0 | micro_IA40244215_0079#39:0 | micro_IA40243305_0612#67:0 (b1/d-) |
| 2 | micro_IA40244207_1249#60:1 | micro_IA40243301_1288#209:0 | micro_IA40244215_0079#39:0 (b-/d1) |
| 3 | micro_IA40242401_0633#8:0 | micro_IA40243304_2923#118:0 | micro_IA40244207_1249#60:1 (b2/d-) |
| 4 | micro_IA40242402_2623#26:0 | micro_IA40243304_2923#120:0 | micro_IA40243301_1288#209:0 (b-/d2) |
| 5 | micro_IA40243316_2036#14:0 | micro_IA40243304_2923#134:0 | micro_IA40242401_0633#8:0 (b3/d-) |
| 6 | micro_IA40243305_0612#69:0 | micro_IA40243304_2923#136:0 | micro_IA40243304_2923#118:0 (b-/d3) |
| 7 | micro_IA40243316_2036#59:1 | micro_IA40243304_2923#182:0 | micro_IA40242402_2623#26:0 (b4/d-) |
| 8 | micro_IA40244207_1249#31:0 | micro_IA40243304_2923#184:0 | micro_IA40243304_2923#120:0 (b-/d4) |
| 9 | micro_IA40242407_0294#19:0 | micro_IA40243304_2923#186:0 | micro_IA40243316_2036#14:0 (b5/d-) |
| 10 | micro_IA40242405_2175#7:0 | micro_IA40243304_2923#188:0 | micro_IA40243304_2923#134:0 (b-/d5) |

## mq40  [gate: answer]
What did reports describe about the SARS outbreak of 2003?
overlap RRF-vs-FTS@10 = 0.3; top-1 agree = False; dense-only in RRF top-10 = 4

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243310_1720#32:0 | micro_IA40243310_1139#161:0 | micro_IA40243310_1720#38:1 (b4/d104) |
| 2 | micro_IA40244215_3226#9:2 | micro_IA40243315_1149#101:0 | micro_IA40243315_1149#143:0 (b81/d30) |
| 3 | micro_IA40244215_3226#9:0 | micro_IA40243310_1139#32:0 | micro_IA40243315_1149#330:0 (b40/d62) |
| 4 | micro_IA40243310_1720#38:1 | micro_IA40243315_1149#84:0 | micro_IA40243309_0344#43:2 (b13/d198) |
| 5 | micro_IA40243315_1149#854:1 | micro_IA40243315_1149#475:1 | micro_IA40243310_1720#32:0 (b1/d-) |
| 6 | micro_IA40243313_2517#205:0 | micro_IA40243315_1149#974:0 | micro_IA40243315_1149#84:0 (b-/d4) |
| 7 | micro_IA40243315_2520#2:0 | micro_IA40243310_1141#4:1 | micro_IA40243315_1149#854:1 (b5/d-) |
| 8 | micro_IA40243310_1141#222:0 | micro_IA40243312_1599#0:0 | micro_IA40243315_1149#475:1 (b-/d5) |
| 9 | micro_IA40243315_1149#1153:1 | micro_IA40244202_2322#12:1 | micro_IA40243310_1141#4:1 (b-/d7) |
| 10 | micro_IA40242401_0621#10:0 | micro_IA40243310_1720#198:0 | micro_IA40243310_1139#161:0 (b-/d1) |

## mq41  [gate: abstain, uncovered: covid]
What did reports describe about the COVID-19 pandemic response in 2020?
overlap RRF-vs-FTS@10 = 0.3; top-1 agree = False; dense-only in RRF top-10 = 0

(gate abstained: possibly-correct thin coverage, not assumed retrieval failure)

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243313_3110#18:0 | micro_IA40244215_1796#8:0 | micro_IA40243313_3230#25:1 (b23/d18) |
| 2 | micro_IA40242406_2170#9:1 | micro_IA40243313_3110#20:0 | micro_IA40244210_1687#12:2 (b74/d6) |
| 3 | micro_IA40244207_2060#8:0 | micro_IA40243315_2692#3:0 | micro_IA24402414_0252#48:1 (b13/d54) |
| 4 | micro_IA40244207_2060#6:0 | micro_IA40244204_3129#46:0 | micro_IA40244207_2060#2:1 (b5/d88) |
| 5 | micro_IA40244207_2060#2:1 | micro_IA40243316_0945#14:1 | micro_IA40243313_3110#20:0 (b120/d2) |
| 6 | micro_IA40244209_2276#26:1 | micro_IA40244210_1687#12:2 | micro_IA40243313_3110#18:0 (b1/d138) |
| 7 | micro_IA40244207_2060#11:0 | micro_IA40244201_1888#17:0 | micro_IA40243313_3110#28:0 (b57/d24) |
| 8 | micro_IA40243313_3110#22:0 | micro_IA40243313_1221#168:0 | micro_IA40244209_0787#106:1 (b71/d40) |
| 9 | micro_IA40243313_3110#5:0 | micro_IA40243315_2377#3:3 | micro_IA40244209_1585#81:0 (b20/d190) |
| 10 | micro_IA40243313_3110#8:0 | micro_IA40244203_3130#28:0 | micro_IA40242406_2170#9:1 (b2/d-) |

## mq42  [gate: abstain, uncovered: apps, 2020s]
What did reports describe about telehealth or virtual-care apps in the 2020s?
overlap RRF-vs-FTS@10 = 0.2; top-1 agree = False; dense-only in RRF top-10 = 0

(gate abstained: possibly-correct thin coverage, not assumed retrieval failure)

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40242405_0255#21:0 | micro_IA40242403_2762#24:0 | micro_IA40243311_2159#124:1 (b10/d28) |
| 2 | micro_IA40242402_3421#3:2 | micro_IA40242405_0173#43:0 | micro_IA40243305_3113#10:0 (b49/d9) |
| 3 | micro_IA40242405_0255#3:1 | micro_IA40243305_3113#7:1 | micro_IA40243308_0569#20:0 (b6/d70) |
| 4 | micro_IA40244203_2447#14:1 | micro_IA40242403_3121#50:0 | micro_IA40243305_3113#34:1 (b121/d6) |
| 5 | micro_IA40242405_0255#23:1 | micro_IA40243305_3113#21:0 | micro_IA40243311_2159#45:0 (b55/d25) |
| 6 | micro_IA40243308_0569#20:0 | micro_IA40243305_3113#34:1 | micro_IA40243305_3113#7:1 (b158/d3) |
| 7 | micro_IA40242405_0255#23:0 | micro_IA40243314_1068#1:1 | micro_IA40243311_2159#204:0 (b20/d78) |
| 8 | micro_IA40243311_2159#216:0 | micro_IA40243311_2159#101:1 | micro_IA40243311_2159#204:1 (b11/d125) |
| 9 | micro_IA40244215_2708#45:1 | micro_IA40243305_3113#10:0 | micro_IA40243305_3113#36:0 (b73/d33) |
| 10 | micro_IA40243311_2159#124:1 | micro_IA40244202_1503#14:1 | micro_IA40243305_3113#37:0 (b56/d51) |

## mq43  [gate: answer]
What did United States Medicaid reports describe about eligibility rules?
overlap RRF-vs-FTS@10 = 0.6; top-1 agree = False; dense-only in RRF top-10 = 4

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243312_0318#60:0 | micro_IA40243222_1279#1:0 | micro_IA40243219_1267#33:2 (b2/d-) |
| 2 | micro_IA40243219_1267#33:2 | micro_IA40243220_0426#86:0 | micro_IA40243220_0426#86:0 (b-/d2) |
| 3 | micro_IA40243215_0530#62:0 | micro_IA40243209_1157#96:0 | micro_IA40243215_0530#62:0 (b3/d-) |
| 4 | micro_IA40243212_0688#17:0 | micro_IA40243515_0619#0:0 | micro_IA40243209_1157#96:0 (b-/d3) |
| 5 | micro_IA40243305_1229#55:0 | micro_IA40243306_3426#116:0 | micro_IA40243212_0688#17:0 (b4/d-) |
| 6 | micro_IA40243217_0556#43:0 | micro_IA40243220_0426#128:0 | micro_IA40243305_1229#55:0 (b5/d-) |
| 7 | micro_IA40243216_1959#52:0 | micro_IA40242805_2175#16:0 | micro_IA40243306_3426#116:0 (b-/d5) |
| 8 | micro_IA40242405_0528#144:0 | micro_IA40243220_0426#379:0 | micro_IA40243217_0556#43:0 (b6/d-) |
| 9 | micro_IA40243305_1229#60:1 | micro_IA40243303_2317#26:0 | micro_IA40243220_0426#128:0 (b-/d6) |
| 10 | micro_IA40242807_0522#173:1 | micro_IA40243513_0392#2:0 | micro_IA40243216_1959#52:0 (b7/d-) |

## mq44  [gate: answer]
What did reports describe about public health in the 1950s?
overlap RRF-vs-FTS@10 = 0.6; top-1 agree = True; dense-only in RRF top-10 = 4

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243513_1013#55:0 | micro_IA40243223_1862#35:0 | micro_IA40243513_1013#55:0 (b1/d-) |
| 2 | micro_IA40242801_1198#16:1 | micro_IA40243223_1862#41:0 | micro_IA40243223_1862#35:0 (b-/d1) |
| 3 | micro_IA40242806_0512#71:1 | micro_IA40243310_1720#46:0 | micro_IA40242801_1198#16:1 (b2/d-) |
| 4 | micro_IA40243315_1386#168:1 | micro_IA40244215_0079#8:0 | micro_IA40243223_1862#41:0 (b-/d2) |
| 5 | micro_IA40243313_0996#4:0 | micro_IA40243510_1399#0:0 | micro_IA40242806_0512#71:1 (b3/d-) |
| 6 | micro_IA40243307_0382#125:1 | micro_IA40242802_1401#34:0 | micro_IA40243310_1720#46:0 (b-/d3) |
| 7 | micro_IA40242803_0911#94:0 | micro_IA40243312_1599#435:0 | micro_IA40243315_1386#168:1 (b4/d-) |
| 8 | micro_IA40242803_0911#75:0 | micro_IA40243510_0390#15:0 | micro_IA40244215_0079#8:0 (b-/d4) |
| 9 | micro_IA40243309_2798#6:1 | micro_IA40243315_1872#51:0 | micro_IA40243313_0996#4:0 (b5/d-) |
| 10 | micro_IA40243313_0126#7:1 | micro_IA40244215_0079#9:0 | micro_IA40243307_0382#125:1 (b6/d-) |

## mq45  [gate: abstain, uncovered: mrna]
What did reports describe about mRNA vaccine platform development?
overlap RRF-vs-FTS@10 = 0.5; top-1 agree = False; dense-only in RRF top-10 = 4

(gate abstained: possibly-correct thin coverage, not assumed retrieval failure)

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40243304_0965#2:1 | micro_IA40243314_2655#84:0 | micro_IA40242405_0800#10:0 (b114/d25) |
| 2 | micro_IA40242406_1747#20:1 | micro_IA40244215_3267#6:0 | micro_IA40243304_0965#2:1 (b1/d-) |
| 3 | micro_IA40242406_1747#21:3 | micro_IA40242405_0798#25:0 | micro_IA40243314_2655#84:0 (b-/d1) |
| 4 | micro_IA40244204_1846#5:0 | micro_IA40244215_3267#18:0 | micro_IA40242406_1747#20:1 (b2/d-) |
| 5 | micro_IA40242406_1747#20:0 | micro_IA40244215_3183#15:0 | micro_IA40244215_3267#6:0 (b-/d2) |
| 6 | micro_IA40244204_1846#4:0 | micro_IA40244215_3178#29:2 | micro_IA40242406_1747#21:3 (b3/d-) |
| 7 | micro_IA40242406_1747#23:1 | micro_IA40244209_0079#49:1 | micro_IA40242405_0798#25:0 (b-/d3) |
| 8 | micro_IA40242406_1747#22:0 | micro_IA40242406_0351#13:2 | micro_IA40244204_1846#5:0 (b4/d-) |
| 9 | micro_IA40242402_2645#21:1 | micro_IA40244215_3267#2:0 | micro_IA40244215_3267#18:0 (b-/d4) |
| 10 | micro_IA40244213_0139#50:0 | micro_IA40244214_3727#2:0 | micro_IA40242406_1747#20:0 (b5/d-) |

## mq46  [gate: abstain, uncovered: guidance]
What did reports describe about cannabis legalization public-health guidance after 2018?
overlap RRF-vs-FTS@10 = 0.3; top-1 agree = False; dense-only in RRF top-10 = 0

(gate abstained: possibly-correct thin coverage, not assumed retrieval failure)

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40242406_2349#20:0 | micro_IA40242406_0223#0:0 | micro_IA40242406_0223#3:0 (b3/d4) |
| 2 | micro_IA40242406_0325#6:0 | micro_IA40244206_0082#246:0 | micro_IA40242406_0325#23:0 (b12/d6) |
| 3 | micro_IA40242406_0223#3:0 | micro_IA40244204_2320#6:0 | micro_IA40242406_0223#16:1 (b47/d5) |
| 4 | micro_IA40242406_0325#24:0 | micro_IA40242406_0223#3:0 | micro_IA40242406_0325#5:0 (b6/d63) |
| 5 | micro_IA40242406_2349#6:0 | micro_IA40242406_0223#16:1 | micro_IA40242406_1672#3:0 (b15/d74) |
| 6 | micro_IA40242406_0325#5:0 | micro_IA40242406_0325#23:0 | micro_IA40242406_0223#5:2 (b26/d51) |
| 7 | micro_IA40242406_0592#22:1 | micro_IA40242406_0325#6:1 | micro_IA40242406_0223#6:0 (b72/d19) |
| 8 | micro_IA40242406_2349#9:0 | micro_IA40242406_0223#5:1 | micro_IA40242406_2349#9:0 (b8/d172) |
| 9 | micro_IA40242404_0104#13:0 | micro_IA40244206_0082#108:0 | micro_IA40243223_2064#35:1 (b24/d92) |
| 10 | micro_IA40242406_2349#14:0 | micro_IA40244216_3028#0:0 | micro_IA40242406_0223#3:2 (b53/d59) |

## mq47  [gate: answer]
What did reports describe about vaping or electronic-cigarette regulation?
overlap RRF-vs-FTS@10 = 0.2; top-1 agree = False; dense-only in RRF top-10 = 3

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40242402_3429#17:3 | micro_IA40243222_1060#8:0 | micro_IA40242402_3429#15:1 (b21/d4) |
| 2 | micro_IA40242406_0337#10:1 | micro_IA40243303_1018#48:0 | micro_IA40242406_0337#4:0 (b9/d24) |
| 3 | micro_IA40242406_0337#4:1 | micro_IA40243210_0343#33:0 | micro_IA40242406_0337#7:1 (b19/d13) |
| 4 | micro_IA40242402_3429#17:2 | micro_IA40242402_3429#15:1 | micro_IA40242406_0337#6:0 (b17/d16) |
| 5 | micro_IA40242406_0337#13:0 | micro_IA40244209_2049#14:1 | micro_IA40242406_0337#13:0 (b5/d35) |
| 6 | micro_IA40242406_0337#0:0 | micro_IA40242808_0037#0:0 | micro_IA40242808_0037#3:1 (b32/d19) |
| 7 | micro_IA40242402_3429#17:1 | micro_IA40243313_1139#93:0 | micro_IA40242406_0337#2:0 (b12/d109) |
| 8 | micro_IA40242406_0337#7:0 | micro_IA40243308_1213#25:0 | micro_IA40243222_1060#8:0 (b-/d1) |
| 9 | micro_IA40242406_0337#4:0 | micro_IA40242806_1018#0:0 | micro_IA40243303_1018#48:0 (b-/d2) |
| 10 | micro_IA40242406_0337#10:0 | micro_IA40242806_1018#2:0 | micro_IA40243210_0343#33:0 (b-/d3) |

## mq48  [gate: abstain, uncovered: mpox]
What did reports describe about monkeypox or mpox outbreak response?
overlap RRF-vs-FTS@10 = 0.6; top-1 agree = True; dense-only in RRF top-10 = 4

(gate abstained: possibly-correct thin coverage, not assumed retrieval failure)

| # | FTS5-only | vector-only | production RRF (arms) |
| - | --- | --- | --- |
| 1 | micro_IA40244210_1302#12:1 | micro_IA40243312_1599#296:1 | micro_IA40244210_1302#12:1 (b1/d-) |
| 2 | micro_IA40244210_1301#12:1 | micro_IA40243213_0141#258:0 | micro_IA40243312_1599#296:1 (b-/d1) |
| 3 | micro_IA40244213_1878#78:1 | micro_IA40244215_3752#69:0 | micro_IA40244210_1301#12:1 (b2/d-) |
| 4 | micro_IA40244210_1302#12:0 | micro_IA40244210_2386#155:0 | micro_IA40243213_0141#258:0 (b-/d2) |
| 5 | micro_IA40242402_2632#10:0 | micro_IA40242801_0907#543:4 | micro_IA40244213_1878#78:1 (b3/d-) |
| 6 | micro_IA40243309_0344#101:0 | micro_IA40243221_0033#12:0 | micro_IA40244210_1302#12:0 (b4/d-) |
| 7 | micro_IA40244210_1301#12:0 | micro_IA40242801_0907#537:5 | micro_IA40244210_2386#155:0 (b-/d4) |
| 8 | micro_IA40244215_1531#24:0 | micro_IA40243303_0763#86:0 | micro_IA40242402_2632#10:0 (b5/d-) |
| 9 | micro_IA40242402_2632#11:2 | micro_IA40242803_0967#87:0 | micro_IA40242801_0907#543:4 (b-/d5) |
| 10 | micro_IA40242401_0632#23:1 | micro_IA40243213_0141#258:1 | micro_IA40243309_0344#101:0 (b6/d-) |

