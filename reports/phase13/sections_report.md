# Phase 13 section classifier report

Deterministic front / body / back classification of every page with text, from leaf
position and text signals. Thresholds fixed a priori; no labels used. Samples are a
seeded reservoir sample (seed 13) so the same db reproduces the same rows.

## Counts

- pages walked: 468405 of 468405 (2990.6 pages/s, 156.6 s)
- pages classified: 448496
- pages with no text (left NULL): 19909 in this walk; 19909 NULL in the table
- front: 12680 pages, 15002 passages
- body: 433091 pages, 724323 passages
- back: 2725 pages, 6568 passages

## Deciding rule

| method | pages |
| --- | ---: |
| default | 433091 |
| cover | 5714 |
| title_page | 4943 |
| reference_list | 2666 |
| contents | 1749 |
| transmittal | 274 |
| back_zone_list | 49 |
| index | 10 |

## Sample: front (20 pages)

- `31761115565004#1` leaf 1/2 [cover] SOME SKILLS AND CONCEPTS - (FOOD FOR PRESCHOOLERS) - PAMPHLET
  > Effect of Heat on Objects. What changes occur in form, taste, volume, etc., when different foods are heated? What substances conduct heat? Does every- thing evaporate? Sets and Numbers. Dozen eggs, pound of butter, quart of milk. Sequence, 
- `31761115565053#0` leaf 0/2 [cover] You can prevent falls : the Falls Prevention Initiative
  > F You can prevent falls: we Sy CA | = iy 6 74.3 The Falls Prevention Initiative e What is the Falls Prevention Initiative? Health Canada and Veterans Affairs Canada have established a community-based health promotion initiative to help iden
- `31761115566069#7` leaf 7/184 [contents] NATIONAL HEALTH FILM LIBRARY CATALOGUE
  > DENTAL HEALTH About: Puce s c:....Acicndsusnee ee ] Something NorGnew meee... 116 COWIE CVO esnsscacssuxecgdedevvertous cavueccuecet aimee a eee 22 Swab Your Choppers= ee 12?T Dariny s Dental Dates ccc. oan ee 27 Target: Tooth Decayamer ee.
- `31761115568552#7` leaf 7/164 [title_page] Charting Canada's future : a report of the Demographic Review
  > Digitized by the Internet Archive in 2022 with funding from University of Toronto https://archive.org/details/31/61115568552
- `31761115569196#24` leaf 24/454 [title_page] 31761115569196
  > PROVINCIAL AND TERRITORIAL HEALTH CARE INSURANCE PLANS Canada Health Act Annual Report 1998-1999
- `31761115571309#7` leaf 7/224 [contents] Suicide in Canada : update of the Report of the Task Force on Suicide 
  > List of Tables and Figures (For a discussion of official suicide statistics and their interpretation, see Appendix 4 and the introductory note for Appendix 6) ‘Table: Tables le able: Table 3: davies: Table 4.1: Table 4.2: Table 4.3: ‘Table:
- `31761116496498#3` leaf 3/270 [title_page] Proceedings - Royal Commission on matters of health and safety arising
  > MY: i chad pid Sh F vine ty Pe) * \) y a) re, " Oe
- `31761118500032#3` leaf 3/364 [title_page] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > Digitized by the Internet Archive in 2023 with funding from University of Toronto https://archive.org/details/31/761118500032
- `31761118500693#0` leaf 0/536 [cover] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > Fd ad al MM DN 3 1761 11850069 3 UTM Ontario { USO B/C ROYAL COMMISSION OF ING IRY ID ) CERTAIN DEATHS AT THE HOSPITAL FOR SICK p RELATED MATTERS. 180 Dundas Street West Toronto, Ontario P.S.A. Lamex, Q.C. £.A. Cronk Thomas Millar Transcrip
- `31761118937606#2` leaf 2/92 [title_page] Designated substances in the workplace : a general guide to the regula
  > Covesesnes P Ublion ten Designated Substances in the Workplace: A General Guide to the Regulations July 1995
- `31761119709236#0` leaf 0/700 [cover] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > Jatabiseoientens ite i wl heb aR 94d Wy alah <i ‘e pis Tht AA sy ie i a ity ee Ve! i Ms Ab “AR WAR IS U8 Wy bei aha ‘ His ny UE a Hd ry ue He Ata ay nian ioe a i Ui ae i wrviahe ene fot hdon a ne : Ce ay a rae prt ' h As 4) a i a Vn f a Pe 
- `31761120610522#4` leaf 4/182 [contents] Proposed revisions to the sections of the regulations for construction
  > TABLE OF CONTENTS PROPOSED REVISIONS TO THE SECTIONS OF THE REGULATIONS FOR CONSTRUCTION PROJECTS, INDUSTRIAL ESTABLISHMENTS, AND MINES AND MINING PLANTS, WHICH ADDRESS ELECTRICAL HAZARDS Purpose of these Notes Background EXPLANATORY NOTES 
- `39262609040028#1` leaf 1/310 [cover] Proceedings of the Standing Senate Committee on Social Affairs, Scienc
  > THE STANDING SENATE COMMITTEE ON SOCIAL AFFAIRS, SCIENCE AND TECHNOLOGY The Honourable Michael Kirby, Chair The Honourable Wilbert J. Keon, Deputy Chair and The Honourable Senators: * Austin, P.C. Gill (or Rompkey, P.C.) Johnson Callbeck Le
- `ableg_33398003988283#1` leaf 1/204 [cover] Annual report of the Alberta Hospitalization Benefits Plan / 1970
  > are SS: ae Fs a Se SSS 5
- `annualreport2000albe_4#1` leaf 1/20 [cover] Annual report
  > For additional copies of this report, contact the Public Health Appeal Board 24th Floor, 10025 JASPER AVENUE EDMONTON, ALBERTA T5J 2N3 (780) 427-2813 ISSN 0845 -6089
- `healthriskassess00flemuoft#4` leaf 4/202 [title_page] Health risk assessment of mercury contamination in the vicinity of ICI
  > HEALTH RISK ASSESSMENT OF MERCURY CONTAMINATION IN THE VICINITY OF ICI FOREST PRODUCTS CORNWALL, ONTARIO Report prepared by: S.W. Fleming, L.V. Radzius and F. Ursitti Standards Development Branch Report prepared for: Ontario Ministry of Env
- `premierscommiss1988#1` leaf 1/2 [cover] The Premier's Commission on Future Health Care for Albertans [newslett
  > Project Update On December 18, 1987 Premier Getty an- nounced the establishment of the seven-member Commission to recommend a course of action to ensure Alberta's health care system continues to be the best in Canada well into the next cent
- `science2408albe#4` leaf 4/92 [title_page] Science 24
  > We hope you'll enjoy your study of Energy in Action. To moke your learning a bit easier, a teacher will help guide you through the material. So whenever you see this icon. fT turn on your audiocassette and listen.
- `soilinvestigatio4255ontauoft#21` leaf 21/582 [contents] Soil Investigation and Human Health Risk Assessment for the Rodney Str
  > Soil Investigation and Human Health Risk Assessment for the Rodney Street Community; Port Colborne: March 2002 Algoma, which was located on the east side of the Welland canal bordering on the southwest comer of the Rodney Street community, 
- `utilizationofmed00albe#7` leaf 7/236 [title_page] Utilization of medical services
  > UTILIZATION OF MEDICAL SERVICES LEVEL 1: EXECUTIVE SUMMARY

## Sample: body (20 pages)

- `31761095474680#123` leaf 123/216 [default] European cooperation on environmental health aspects of the control of
  > Tetra eds i wit) ‘eo b VRltw rioqee . Sty Sa LITe3 Weeds vi cy Lore? "i Seat) a er alae Mi ie 7, a hei. dr ; mt Oak aah ' Oia AD fie Oy} ay 7 ; : One ak ae ee ; PAV ‘ ae a Ne i‘, varareey? Real fo’ Phe tr?) f Tad Mm anomyat Atleed ao eldili
- `31761115548711#339` leaf 339/418 [default] Speech / Discours
  > Poe Get et Cees ae be Dh nieey wl i VEPs, | - c 24 Si Ge (ey ~*~ +394 (ae ),) - i A 7 7 Ptr te Wel iste age , ma i 5 psy 0 gs ne A | ns ial) 2 91°? . =)! \ ‘ . a 7 at ce * 7 a My ’ f é iyi Ds Bilvs ) } ie if @ . ' Trane. uieae pein tt wnt t
- `31761115549248#212` leaf 212/452 [default] 31761115549248
  > Rosanne Laflamme, Quebec City, Quebec - Teacher Aftéralosane both legsvand an “armeasathe result ofa childhood accident, Miss Laflamme has become a paramount example to all handicapped people. In 1975 she won gold, silver and bronze medals 
- `31761115549412#220` leaf 220/946 [default] 31761115549412
  > TABLE A TABLE B TABLE C TABLE D TABLE E TABLE F TABLE G TABLE H TABLE J TABLE K INDEX OF TABLES Number of Insured Persons on March 3l, 1963 by Province as Reported for Purposes Rey Cee ey Tet Lee, oo aie sera Lek wie eraie ae Net Population
- `31761116486184#19` leaf 19/164 [default] Canadian incidence study of reported child abuse and neglect : major f
  > FIGURE 10 Age and Sex of Victims, by Primary Category of Substantiated Child Maltreatment in Canada, Excluding Quebec, in 2003 For sample size, see Table 6-3. 10,000 8,000 6,000 4,000 2,000 100% (‘0-3 Years [ 4-7 Years 80% & 8-11 Years (J 1
- `31761116497322#261` leaf 261/288 [default] Proceedings - Royal Commission on matters of health and safety arising
  > : tents 123 jets efquod » eved T - fata bent oo mata ofc Siode edtvp ots Yoda anida 3 -Ysb o47 jelteh feds evade « daub Socie: sav feds onc oF dned smo9 7 Sivcsd sicasons ofiuQ Sescanliisaes tgaeb ety Jeods ops elit atseri (sag sit Yo jasty
- `31761117015610#314` leaf 314/688 [default] Proceedings of the Subcommittee on Population Health = Délibérations d
  > APPENDIX A Woolcock, A. J., & Peat, J. K. (1997). Evidence for the increase in asthma worldwide. Ciba Found Symp, 206, 122-134; discussion 134-129, 157-129. World Health Organization. (1994). Assessment of fracture risk and its application 
- `31761118498526#320` leaf 320/410 [default] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > 24 25 ANGUS, STONEHOUSE & CO. LTD. TORONTO, ONTARIO MacLeod, dr.ex. 4182 (Lamek) something like the converse of the distribution CULVe.. »O that 1f it disappears from serum with a heliglatesof 20 minutes: then 1b probably appears in myocard
- `31761118499870#271` leaf 271/506 [default] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > ake & Be cnaatecee B, Sit no eanivevibam cr sosqeeee aad hei poe serene wi sud sess ns ay tae Bf fesse Ss lw ,sorin , to pram 2” Poe hKawarideen es 2c tone bie ' Mir at @ gual om aqothod ott Taw | wre ne Citi ‘679 MOLI! OM . at @ualds 4668 
- `31761118500669#207` leaf 207/536 [default] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > aR O noy 31 sud: ybadysave o¢ dpeosds 21 dep of opnacm Pienbgden sow xo molly [asd Gay ib 36 eee Soateslaunne>. new 2610 rd=ORTIW She a Gol, Stele Gwav oh? of Adigeinsiz9, No\20 Sree = aneiienibon «Gt esiGidienodesr sine y ‘tee Ym mi dau SA
- `31761118500891#77` leaf 77/480 [default] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > “vi naib kite epi sii \omtSont eegBbO: 33. iG (gait tn ints ae tea rico | sas tedmeitet ¥3 Fug? S335 avec TL . ar AG ¢ 5 > acl ious wre ya vey of .aiag 30 on haved eds | Ssfebwis ] 4 , ’ C) i” { } Y nilsseh 120en- Fi sor > eb, 3esbEons jot 
- `31761118501584#339` leaf 339/476 [default] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > nina een ae nee axedg pihyin thaeds por 68 OMA a) | wt sos eat oy 2 ea at eer ee | + i pay: ar Jan gay emia Laviv kes aaa So0t Bad ode: yesngt @ vos Sea at 9 eds betelqees Gad ads .i ian if min 262 Goeie ladty Weota’s cally s6¢ sostg excten
- `31761119702942#436` leaf 436/612 [default] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > 16 April, 1993 Mr. Brian Tobin John Drneman Member of Parliament 89 Windsor Street B22 Confederation Building Corer Brook, NF House of Commons A2H 685 Ottawa, Ontario KIA 0A6 ear Mr. Tobin: recently read in The Globe and Mail that the Liber
- `31761119709343#379` leaf 379/518 [default] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > HEALmn2(7658)-E Pace: Z.0n being considered. It was agreed, -- That the Chair present the First Report of the Sub-Committee on Agenda and Procedure to the main committee. At 11:52 a.m., the Committee adjourned to the call of the Chair. It w
- `31761119709350#139` leaf 139/408 [default] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > di) sreenlt planet en 2¢ ad gaitea Co ire AE satin ite — Lend a -_ Soa as a a ~) a ‘VAG 34T4O Wat aorta be, 08 cusragae Bataan 2 Ona testes! teak 0 pe Oy De | | ea Date ruler’ *yetaowrssh clad A Tervaiuys’ elec ip sonal, _ oT 3 an duvet? vr
- `31761119720282#89` leaf 89/896 [default] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > Le ‘AOU THOUVN ‘uopisoid a] ‘sIuNos JUaUIASNeN}oOdsay ‘gsodap 3sa (140ddpu aj puasdwoo inb ‘p¢ ja ‘Og ‘62 ‘82 ‘LZ ‘92 ‘CZ ‘be ‘EZ SOU Sajnoi2sv{) yues10dde, A.S saseusIoUlD} 39 XNVq19A-Sed01d Sap s1TejduWIax9 U_ [B1QU9Z INS}OI[[OS Np o19}SI
- `39102516100111#432` leaf 432/438 [default] Report of the Task Force on the implementation of midwifery in Ontario
  > APPENDIX 10 Biographies of the Task Force Members and Staff
- `39262609080081#25` leaf 25/28 [default] Proceedings of the Standing Senate Committee on Social Affairs, Scienc
  > ear RENE “ho SA ONL i AE AUS Og D a “3 j —s oe em ; fy . < } et ÿ . à 4 Ps eet «4 ete? bse Toes jz | | fa oh, F *) wy lg 11 = à ‘ 4 ' ad al fx vr re ' ’ J i ive , +; LT (M r da ‘ ‘ i! és re (] URL é vt i cé à : Faite # 4, ~ "+ try À 1 € ; à
- `39291103070074#89` leaf 89/106 [default] REPORT OF THE ROYAL COMMISSION ON ELECTRIC POWER PLANNING: VOL.9 - A B
  > Great Lakes Basin Commission. Great Lakes Basin Framework Study. A reference study which de- scribes each volume in the 27-volume set. Ann Arbor, Michigan, 1975. Great Lakes Basin Commission. Public Priorities for Great Lakes Research. Ann 
- `decisionsaboutto00albe#24` leaf 24/32 [default] Decisions about tomorrow : directives for your health care
  > YOUR VIEWS ARE IMPORTANT! These pages have been prepared to assist you in providing feedback to the Honourable Shirley McClellan. Please take a few moments of your time to fill out this survey on the issues raised in Decisions about Tomorro

## Sample: back (20 pages)

- `31761056886120#125` leaf 125/218 [reference_list] Report of proceedings of a study on animal health emergencies. 11-15 M
  > Pao 14. i353 16. Leyes 18. 19% 20. Delve bial Animal,.disease: fA.CeTRassegnandr4s N.S.WaeSadsGN ste tb SS- > ok 6; Qld s.3 and Exotic Diseases in Animals Act 1981-1982 s.5? S.A. ss.5(1) and 8a and Foot and Mouth Disease Eradication. Fund A
- `31761112244587#536` leaf 536/588 [reference_list] PROCEEDINGS OF CANADA PARLIAMENT SENATE STANDING COMMITTEE ON HEALTH, 
  > INDEX 4) Manpower—Cont'd Training—Cont’d Handicapped persons, 16: 7, 20 Health sciences programs, 16: 22-3 Institutes and courses sponsored by non-profit groups, 17: 11 Federal government assistance, 15: 13, 17; 16: 25-6 Licensing procedure
- `31761115561961#274` leaf 274/488 [reference_list] Health expenditures in Canada by age and sex, 1980-81 to 2000-01. Stat
  > Table 67A Total Health Expenditures by Age Group and Sex Tableau 67A Dépenses totales de santé selon le groupe d'âge et le sexe New Brunswick / Nouveau-Brunswick, 1980-81 to/à 2000-2001 0 Year Age Groups / Groupes d'âge Année 0-14 15-24 25-
- `31761119709210#701` leaf 701/716 [reference_list] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > 20 HEALTH, WELFARE AND SOCIAL AFFAIRS Ogle, Mr. Bob (NDP—Saskatoon East) Canada Health Act (Bill C-3), 10:83-4 Old Age Security Payments abroad, 31:14- 5 Provincial welfare payments, reimbursing provinces, 33:20-1 Recipients, numbers receiv
- `31761119715381#51` leaf 51/130 [reference_list] Deaths / Décès / Statistique Canada, Centre canadien d'information sur
  > Deaths, 1991 Décés, 1991 ee ee eee TABLE 15. Infant Deaths and Infant Death Rates, Canada and Provinces, Selected Years, 1931-1991 - Concluded TABLEAU 15. Mortalité infantile et taux de mortalité infantile, Canada et provinces, années chois
- `31761119715381#95` leaf 95/130 [reference_list] Deaths / Décès / Statistique Canada, Centre canadien d'information sur
  > Deaths 1992 “le Décès 1992 D eo 6 Table 6. Age-Sex-Specific Death Rates, Canada, Provinces and Territories, 1991 and 1992 Tableau 6. Taux de mortalité selon l'âge et le sexe, Canada, provinces et territoires, 1991 et 1992 Nfld. P.E.I. N.S. 
- `31761119717247#388` leaf 388/400 [reference_list] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > 30-5— 1995 Santé 3079 Members of the Committee present: Margaret Bridgman, Harold Culbert, Grant Hill, Ovid L. Jackson, Bernard Patry, Pauline Picard, Roger Simmons, Paul Szabo, Rose—Marie Ur. In attendance: From the Research Branch of the 
- `39040222040140#55` leaf 55/524 [reference_list] SELECTED ECONOMIC ASPECTS OF THE HEALTH CARE SECTOR IN ONTARIO - A STU
  > 18 Health Care Resources for the census years 1941, 1951 and 1961. In 1961, with 84.38 health profes- sionals per 10,000 persons, Ontario occupied third rank in Canada behind British Columbia (90.83) and Saskatchewan (85.58). TABLE 2.8 Heal
- `39040423030148#557` leaf 557/1190 [reference_list] FINAL REPORT OF THE CANADA COMMISSION OF INQUIRY INTO THE NON-MEDICAL 
  > 118. Lo: 120. ALS 122; 123: 124. $25: 126. 1273 128. 129: 130. 131. 132. 133. 134. 135: 136. H37 138. 139. The Drugs and Their Effects — References Hughes, F. W., & Forney, R. B. Delayed audiofeedback (DAF) for induction of anxiety. Effect 
- `39092409090067#153` leaf 153/208 [reference_list] Health status of Canadians : report of the 1991 General Social Survey
  > Kaiserman MJ, Collishaw NE. Trends in Canadian tobacco consumption, 1980-1990. Chronic Diseases in Canada. 1991;12(4):50-52. Pipe A. Tobacco control in Canada: the signs of success. Chronic Diseases in Canada. 1991; 12(4):44- 45. National C
- `39171007050085#332` leaf 332/436 [reference_list] New reproductive technologies : ethical aspects.
  > Prenatal Diagnosis and Society 313 Holmes, H.B., B.B. Hoskins, and M. Gross, eds. 1980. Birth Control and Controlling Birth: Women-Centered Perspectives. Clifton: Humana Press. —. rats: 1. The Custom-Made Child? Women-Centered Perspectives.
- `fieldmeasurement03albe_0#266` leaf 266/614 [reference_list] Field measurement program : atmospheric dispersion tracer study under 
  > METEOROLOGY (T13B21) Date : 11-20- ■1988 Time: 21:52: : 24 to 22: 1: : 5 4 Flow: 0. 8 Fan: 2.4 C/Q: : 2996 TiMet V4 VI 0 D4 D10 SiqU SiqV StoW SiqTh SiqPh Hflux T2 Tqrad Nrad Ustar Z/L Travel Time Averages (# 3 minute observations = 2 ) 21:
- `fieldmeasurement03albe_0#405` leaf 405/614 [reference_list] Field measurement program : atmospheric dispersion tracer study under 
  > TRAVERSE STATISTICS (T18B03) File scans: data ( 150 to 370 ), moment ( 170 to 358 ) Date : 12-07-1988 Time : 17:46:36 to 17:50:16 Start location: P7 on 1400 m E arc. Source : E Elevated Power Law Cal. : ppt = 545.6 * (voltage) A 1.071 Metho
- `fieldmeasurement03albe_0#411` leaf 411/614 [reference_list] Field measurement program : atmospheric dispersion tracer study under 
  > TRAVERSE STATISTICS (T18C03) File scans: data ( 10 to 650 ) , moment ( 481 to 615 ) Date : 12 -07-1988 Time : 17:50:47 to 18: 1:27 Start location: 13 on 700 m E arc. Source : E Elevated Power Law Cal. : ppt = 854.8 * (voltage) A .944 Method
- `micro_IA40243301_2134#218` leaf 218/306 [reference_list] Quest for quality in Canadian health care : continuous quality improve
  > 205 Harrigan ML (Ed.). The Pacific Health Care Society: responding to customer needs in a long-term care setting. Can | Qual Health Care. June 1995; 12(2): 23-26. Harrigan ML. Quality of care: issues and challenges in the 90's: a literature
- `micro_IA40243301_2135#265` leaf 265/337 [reference_list] En quête de qualité dans les soins de santé canadiens : amélioration c
  > 257 Goldsmith, J.C. « The illusive logic of integration », Healthc. Forum J, septembre 1994 : 26-31. Gordon, P.R., Carlson, L., et coll. «A multisite collaborative for the development of interdisciplinary education in continuous improvement
- `micro_IA40243301_3139#64` leaf 64/70 [reference_list] Acetaldehyde
  > Silverman, L., H. Schulte and M. First. 1946. Further studies on sensory response to certain industrial solvent vapours. J. Ind. Hyg. Toxicol. 28: 262-266. Sim, V. and R. Pattle. 1957. Effects of possible smog irritants on human subjects. J
- `ontla_354368#214` leaf 214/223 [reference_list] Cervical Artificial Disc Replacement Versus Fusion for Cervical Degene
  > References February 2019 (81) (82) (83) (84) Schrot RJ, Mathew JS, Li Y, Beckett L, Bae HW, Kim KD. Headache relief after anterior cervical discectomy: post hoc analysis of a randomized investigational device exemption trial. Clinical artic
- `ontla_354377#141` leaf 141/146 [reference_list] Recommendations for the Prevention, Detection and Management of Occupa
  > healthcare workers in comparison with a control group: the Hands4U study. Acta Derm Venereol. 2016;96(4):499-504. Available from: https://www.medicaljournals.se/acta/content/html/10.2340/00015555-2287 149. Ontario Agency for Health Protecti
- `soilinvestigatio00ontauoft#356` leaf 356/496 [reference_list] Soil Investigation and Human Health Risk Assessment - Report for Rodne
  > Soil Investigation and Human Health Risk Assessment for the Rodney Street Community, Port Colborne. October 2001 Gerhardsson, L., Borjesson, J., Mattsson, S., Schiitz, A., and Skerfving, S. 1999. Chelated lead in relation to lead in bone an
