# Phase 13 section classifier report

Deterministic front / body / back classification of every page with text, from leaf
position and text signals. Thresholds fixed a priori; no labels used. Samples are a
seeded reservoir sample (seed 13) so the same db reproduces the same rows.

## Counts

- pages walked: 468405 of 468405 (1176.4 pages/s, 398.2 s)
- pages classified: 448496
- pages with no text (left NULL): 19909 in this walk; 19909 NULL in the table
- front: 12684 pages, 15016 passages
- body: 431989 pages, 723510 passages
- back: 3823 pages, 7367 passages

## Deciding rule

| method | pages |
| --- | ---: |
| default | 431989 |
| cover | 5714 |
| title_page | 4943 |
| reference_list | 3764 |
| contents | 1753 |
| transmittal | 274 |
| back_zone_list | 49 |
| index | 10 |

## Sample: front (20 pages)

- `31761115566655#0` leaf 0/84 [cover] Smoking by-laws in Canada, 1991
  > MO 31761 11556665 5 Health and Welfare Santé et Bien-étre social Canada Canada Smoking By-laws in Canada 1991
- `31761116510587#6` leaf 6/1196 [title_page] HEARINGS OF THE CANADA ROYAL COMMISSION ON HEALTH SERVICES, 1961-1962
  > Te | F268 ~~ ROYAL COMMISSION — ON HEALTH SERVICES HEARINGS HELD AT REGINA SASK. VOLUME NUMBER: DATE: 18 JANUARY 23 1962 Wa\e ries Veiaul § 2 se = OFFICIAL REPORTERS ANGUS, STONEHOUSE & CO. LTD. BOARD OF TRADE BLDG. 11 ADELAIDE ST. W. TORON
- `31761118499961#0` leaf 0/552 [cover] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > 1 DYNA IM IM Ontario ROYAL COMMISSION OF DEATHS AT THE HOSPITA RELATED MATTERS. 180 Dundas Street West Toronto, Ontario 4 Cnr! The Honourable Mr. Justice S.G.M. ange P.S.A. Lamek, Q.C. E.A. Cronk ' : é Associate Counsel Thomas Millar Admin 
- `31761118500867#8` leaf 8/278 [title_page] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > Xo? 24 25 ANGUS. STONEHOUSE & CO. LTD. (ii) TORONTO. ONTARIO INDEX OF EXHIBITS Description Page No. A Statement of Claim and a Statement of Defence submitted by Mr. Percival 2977
- `31761118500909#8` leaf 8/508 [title_page] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > ANGUS, STONEHOUSE & CO. LTO. 306 307 TORONTO, ONTARIO INDEX JE ie oaks Le oD Description (Cont'd) Summaries of Various Administra- tive Practices by Carol Browne. Photograph of IV System Document entitled: Care Plan". "Patient 353) Page No.
- `31761118944321#6` leaf 6/126 [contents] COTTAGE POLLUTION STUDY. PART 1- METHODOLOGY AND STUDY OF THREE LAKES
  > INDEX Contents oummary Part I — Introduction Part II - The Study of Jack Lake Part III -— The Study of Steenburg Lake Part IV - The Study of Six Mile Lake Part V -— Comparing the Lakes Part VI — Conclusions Notice to Cottage Owners Blank Da
- `31761118944388#12` leaf 12/338 [contents] PROFILES HEALTH OCCUPATIONS
  > TABLE OF CONTENTS NURSING Page Registered Nurse 1 Registered Nurse (Psychiatric) 6 Public Health Nurse 10 Registered Nursing Assistant 14 Hospital Orderly E7 Nursing Aide 19 GENERAL MEDICAL CARE Basic Physician 31 Clinical Psychologist 40 M
- `31761119720431#0` leaf 0/736 [cover] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > meat ott e ks ee — ‘ 5 > = ee wey ae vate eee
- `39091118030083#4` leaf 4/94 [contents] [Report]
  > Table of Contents PENAL AI LET OT Cit oe ls ill Sea Be ea Ri Re oe EE 5 ACEO. Vin ati Reale os it aire Peer vars Rad Oe eT ae ne 7 PEROOUCTION Dm rremn hmmm ee rte) DM ake Martaru rn Veta AES 9 Chapter 1 1 USS BIG Ce Qiao RS aR LLC naa aL n
- `ableg_33398003121703#0` leaf 0/68 [cover] Preliminary Report to the Honourable Neil Crawford - Minister of Healt
  > CAaALHS8/O | oc. | CA2 ALHS 810 1974P66 Preliminary Report to the Honourable Nei | 1 Crawford - Minister of Health So 2 GT HAM 3 4 3 3398 00312 1703 , PRELIMINARY REPORT | to 4 THE HONOURABLE NEIL CRAWFORD a MINISTER OF HEALTH AND SOCIAL DE
- `ableg_33398004679394#0` leaf 0/240 [cover] Inventory : services for the individual and the community / 1968 Vol. 
  > VERT HIBU oee nrvenrvertt 2 INVENIUKY INVENTORY SERVICES FOR THE INDIVIDUAL AND THE pOMMUNITY VOLUME ONE
- `albertashealthya00albe#2` leaf 2/60 [contents] Alberta's healthy aging and seniors wellness strategic framework 2002-
  > Alberta's Healthy Aging and Seniors Wellness Strategic Framework Contents Executive Summary 1 I Introduction 8 II Background and Methodology 9 A. Background 9 B. Methodologies and approaches 13 III Components of Healthy Aging 15 A. Some hea
- `annualreportalbe1978albe#0` leaf 0/100 [cover] Annual Report : Alberta Hospitals & Medical Care
  > Annual Report 1978/79 Axxta HOSPITALS & MEDICAL CARE
- `delorovillageenv01ontauoft#1` leaf 1/206 [cover] Deloro Village Environmental Health Risk Study - Overall Technical Sum
  > U999 - Her Majesty the Queen in Right of Ontario as Represented by the Minister of the Environment
- `educationphysiqu00onta_0#0` leaf 0/32 [cover] Education physique et hygiène, cycle supérieur
  > Ontario Ministère de l’Éducation OfK;d 113- Vstoa,'t'^ "x / c - P'C fr^rscW Education physique et hygiène Autorisé par Cycle supérieur le ministre de l’Éducation 1975 l’hon. Thomas L. Wells DO NOT REMOVE
- `micro_IA40243301_0487#2` leaf 2/49 [contents] Abuse in lesbian relationships : information and resources
  > Our mission is to help the people of Canada maintain and improve their health. Health Canada Published by the authority of the Minister of Health Abuse in Lesbian Relationships: Information and Resources was prepared by Laurie Chesley, Donn
- `micro_IA40243301_2747#0` leaf 0/36 [cover] Rural and northern hospital networks : Network 17, Brant/Norfolk
  > M1 © THE QUEEN’S PRINTER FOR ONTARIO 1999 REPRODUCED WITH PERMISSION L’IMPRIMEUR DE LA REINE POUR L’ONTARIO REPRODUIT AVEC PERMISSION : dq R 20 Victoria Street rr se 1a Toronto, Ontario MSC 2N8 - nse _ Tel: (416) 362-5211 a division of 1HS 
- `occupationalinj001albe_12#0` leaf 0/26 [cover] Occupational injury and disease in Alberta
  > >fV> ; Jbetta HUMAN RESOURCES AND EMPLOYMENT the people & workplace department September 2001 Occupational Injuries and Diseases in Alberta Tar Sands 1996 to 2000 Upstream Oil and Gas Sub-Sector #6
- `reportofactiviti1997albe#1` leaf 1/24 [cover] Report of activities for ...
  > Digitized by the Internet Archive in 2016 https://archive.org/details/reportofactiviti1997albe
- `socresinvedm1983#12` leaf 12/786 [title_page] Social resources inventory. Edmonton region
  > MAP OF EDMONTON REGION

## Sample: body (20 pages)

- `31761095474680#69` leaf 69/216 [default] European cooperation on environmental health aspects of the control of
  > r i "ie oe she ais | qo migta ato; Moved Sout? vil g Seiapriont 3979 > 4S med 20d «ye ilrow aod kala etdns) is). | ag ohwnns aia wile a aed shdoie’ poh pnd SAiou" ‘md teeter nkie trams ed to aay ste tt ee ee Wen ome ‘ots at tie Et neequ ok 
- `31761115548711#355` leaf 355/418 [default] Speech / Discours
  > : - ae —— 7 ® Aa i) Tai) see oo. na r ep 6 ~~ eo chad - nS | “Awe ar 4 a tt I : - ih’ wn | oT? ehokt ally a a etnheiuth ca - ‘7 cre OF Se agen aa, Sate wwe ‘on Te tipeade bn Bt = ian ela a Te: om ook ert Ps ae anc ie > * dupe ON tis ¥. ¢ e 
- `31761115549123#23` leaf 23/46 [default] Progress report
  > ACTIVITIES The years 2001 through 2003 saw a number of important activities and initiatives undertaken at the community, regional and national levels. The national office advised and offered expertise on several projects over the reporting 
- `31761115549248#190` leaf 190/452 [default] 31761115549248
  > MEMBERS OF THE EXPERT COMMITTEE ON SACCHARIN IN DRUGS AND COSMETICS “OTe rhnchard Bann, University of Ottawa - Dr. Mimi Belmonte, McGill University - Dr. J.S. Bennett, Canadian Medical Association - Dr. John A. Hunt, Lion's Gate Hospital, N
- `31761115549412#180` leaf 180/946 [default] 31761115549412
  > a Poe TABLE"E PAYMENTS BY CANADA — JULY 1, 1958 TO MARCH 31, 1962 BY PROVINCE AND BY CALENDAR YEAR 1958 1959 1960 1961 96 PROVINCE Total Total Advances on Advances on Advances on Contributions Contributions Contributions Contributions Contr
- `31761116486184#48` leaf 48/164 [default] Canadian incidence study of reported child abuse and neglect : major f
  > TABLE 3-3 Primary Categories of Substantiated Child Maltreatment in Canada in 2003 Primary Category of Substantiated Maltreatment Physical — Sexual Emotional Exposure to Abuse Abuse Neglect Maltreatment Domestic Violence Total Substantiated
- `31761116497322#260` leaf 260/288 [default] Proceedings - Royal Commission on matters of health and safety arising
  > = —— _ = ES OE a = == —— — — —— = a iff av = 10 15 20 25 7 (6/76) = 150) = Enterline DR. DUPRE: This completes the cross-examination, I gather, counsel? MR. LASKIN: At last, time for the Commission. DRewUUPRE es Pare eront. “Stl bloeedmtOun
- `31761116510520#442` leaf 442/1416 [default] HEARINGS OF THE CANADA ROYAL COMMISSION ON HEALTH SERVICES, 1961-1962
  > ANGUS, STONEHOUSE & CO. LTD. Donahoe 452 TORONTO, ONTARIO COMMISSIONER BALTZAN: I would like to reserve questions I wish to put, they are very interesting ones and will probably come up a little later. COMMISSIONER STRACHAN: Mr, Chairman, t
- `31761117015610#227` leaf 227/688 [default] Proceedings of the Subcommittee on Population Health = Délibérations d
  > APPENDIX A Aboriginal health research environment, which demonstrated how the efforts of the Canadian government to oppress the cultures, traditions, and community structures of Aboriginal populations has caused collective trauma and grief 
- `31761118498526#360` leaf 360/410 [default] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > coiy 2 24 25 4202 ANGUS, STONEHOUSE & CO. LTD. MacLeod TORONTO, ONTARIO drvex, (Lamek) AG Pech ink that iS <within’the boa lmeol possibility! (Wi tfind PEsditftadpectco assess the likelihood of that happening. CepeaLmivy ert it has happened
- `31761118499870#321` leaf 321/506 [default] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > lewionss: ae PSP Tent ya GAT. Ay foetaviae . Le VA t gens ] aS Ane r 7 aes hg Antiict onl Line Pies Hatdd I. hac hens ipa dud, Sot Sag stom 1@. bs BAO AL aw mod ais asd f if ae , iM A Lc i bisd Lio Shady fei i, rm) mary ae ois sorsonw yeoma
- `31761118500669#221` leaf 221/536 [default] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > vast, - Guta tue SHaHOTERT IMD aire . Sees ioe aay, gos ie 26 pat VP ae | wth os satan tT -neD sect a a7 i: ro | Modi. fosgnbeg & ona! 36058: lorie wwd sb ee vitae a a | Aobtond). athe oa aso tee a g4ijin LiA 0) O21°02, GD asop oro aang is,
- `31761118500891#71` leaf 71/480 [default] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > we ; 1 . i. Site eWwNe AMOE 5 eew da.“ i | | iL y ; a 7 > “— a Swicutlw Pee sot me Se a > = 2 wit Jag gt. necwse es" Ye LoyiioS > * Li ee oe otjne> yraraaedsd, BsaG4 aoe rites i> csyonas peda iaw: yas me a ee A f o. part? ae Ew vow, Deitegs
- `31761118501584#339` leaf 339/476 [default] Hearings - Ontario Royal Commission of inquiry into certain deaths at 
  > nina een ae nee axedg pihyin thaeds por 68 OMA a) | wt sos eat oy 2 ea at eer ee | + i pay: ar Jan gay emia Laviv kes aaa So0t Bad ode: yesngt @ vos Sea at 9 eds betelqees Gad ads .i ian if min 262 Goeie ladty Weota’s cally s6¢ sostg excten
- `31761119702942#449` leaf 449/612 [default] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > 26 PAoN-bHedtuutm ep eyjndaep —- ueyyeqbegq Aay HuTSsoio s,AAePTD - uoojzeyses ep eyqndep - AyAAOMXW sSTayD :°d°d 3309URA0N pTaAed suTeyund stosuelzg ‘soeiaTequoutTT—e ‘gqezAned-Tjue eTeUuoT zeU senbueq sep suueTpeueRd uoTzestTuebhjgo,T ep 
- `31761119709343#435` leaf 435/518 [default] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > Minutes of Meeting / Procés-verbal | Page 4 of 7 Réal Ménard Marcel Proulx Karen Redman Paul Szabo Judy Wasylycia-Leis — (9) NAYS: -- (0) ABSTAINED: Yvon Bernier — (1) After further debate, the question being put on Clause 7, it carried on 
- `31761119709350#189` leaf 189/408 [default] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > 608 soi” >-<al¥ wy srs tt woh ms et conch jysaderani gee sibel nei) sonst gi soma a" sat ioral 7 untaynqaW elit seaatieT shnaloy ge SO Atal sii das cereal wean? stl Ineslt ouilye® (dA so yeh pont nasi sail cpesecnnhl nese 38 Smear, WO gail 
- `31761119720282#168` leaf 168/896 [default] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > 11-5-1982 Santé, bien-étre social et affaires sociales APPENDICE "SNTE-14"' ACTUALITE SUR LA CONVERSION AU SYSTEME METRIQUE AU CANADA FONDEMENT LEGISLATIF DE LA CONVERSION AU_SYSTEME METRIQUE AU CANADA La conversion au systeme métrique est 
- `39112721070207#180` leaf 180/298 [default] Report of Ontario Task Force on Health and Safety in Agriculture.
  > REFERENCES Chapter One ifs Statistics Canada, 1981 Census of Canada - Agriculture. Cat. No. 96-907 and No. 96.920. Zs Earl Haslett, A Structure of Ontario Agriculture as Related to Health and Safety. Task Force on Health and Safety in Agric
- `39262609080115#76` leaf 76/94 [default] Proceedings of the Standing Senate Committee on Social Affairs, Scienc
  > 5-7-2005 Affaires sociales, sciences et technologie DST short-term disability programs do not cover most mental illnesses; and to how long-term disability programs do not seem to be covered. We also heard that the CPP disability program put

## Sample: back (20 pages)

- `31761095474805#35` leaf 35/120 [reference_list] Water resources development and health : a selected bibliography.
  > PDP/82.2 page 34 G27 Farvar, M.T. & Milton, J.F.*Cediters) : Careless Technology. Conference on ecological aspects of international development. Garden City, Natural History Press, 1972 428. Feachem, R.G. Infectious diseases related to wate
- `31761115567364#33` leaf 33/52 [reference_list] An intervention program for women who were sexually victimized in chil
  > a2 REFERENCES Baker, A.W., & DUNCAN, S.P. (1985). “Child sexual =saduUusc mae study of prevalence in Great Britain. Child Abuse and Neglect, 9, 457-467. Finkelhor, D. (1984). Child sexual abuse: New theory and research. New York: Free Press
- `31761115571218#35` leaf 35/76 [reference_list] Aging and the health care system : am I in the right queue?
  > BSasess FORUM ss REFERENCES Amoko, D.H.A., Modrow, R.E., Tan, J.K.H. (1992). Surgical waiting lists I: Definition, desired characteristics and uses. Healthcare Management FORUM, 5(2), 17-22. Anderson, G., Black, C., Dunn, E., Alonso, J., Ch
- `31761116496704#179` leaf 179/340 [reference_list] REPORT OF THE ROYAL COMMISSION ON MATTERS OF HEALTH AND SAFETY ARISING
  > 158 Chapter 4 asbestos-cement workers, where the trace rate is only 75% .8° (However, Dr. Hans Weill is in the course of updating this study and has achieved a much higher ascertainment rate.)*! End-Point Ascertainment — This criterion refe
- `31761117128629#477` leaf 477/496 [reference_list] Psychiatric care in Canada: extent and results
  > 446 ROYAL COMMISSION ON HEALTH SERVICES CuuTE, K. F., The General Practitioner, Toronto: University of Toronto Press, 1963 College of General Practice of Canada, brief submitted to the Royal Commission on Health Services, Toronto, May 1962 
- `31761118498492#148` leaf 148/372 [reference_list] ASBESTOS IN BUILDINGS
  > ee ae. REFERENCES Wright, S.; Schoepke, S.; and Mathias, P. Economic Impact Analysis of Proposed Identification and Notification Rule on Friable Asbestos- Containing Materials in Schools. EPA 560/12-80-004. Washington, D.C. : U.S. Governmen
- `31761118945252#232` leaf 232/240 [reference_list] Report to the Workers' Compensation Board on cardiovascular disease an
  > CARDIOVASCULAR DISEASE AND CANCER AMONG FIREFIGHTERS 209 17: 178. 1/9; 180. LSL. 182. 183. 184. 185. 186. 187. Silverman, D.T.; Hoover, R.N.; et al. Motor exhaust-related occupations and bladder cancer. Cancer Research. Vol. 46(1986). p.211
- `31761119716892#708` leaf 708/996 [reference_list] Minutes of proceedings and evidence of the Sub-Committee on Health iss
  > 11-2-1993 Questions de santé 20A : 45 43. Wainberg MA, Kendall O, Gilmore NJ: Vaccine and antiviral strategies against infections caused by human immunodeficiency virus. Can Med Assoc J 1988; 138: 797-807 44. Govig B, Jackson WB, Gilmore NJ
- `31761119720399#39` leaf 39/1254 [reference_list] MINUTES OF PROCEEDINGS AND EVIDENCE OF CANADA PARLIAMENT HOUSE OF COMM
  > 946 References 1. Wahi, P.N. Epidemiology of cancer: oropharyngeal tum- ours. WHO Chronicle 22: 539, 1968. 2. Orlovsky, L. V. Theory and method of health education on the prevention of cancer in the U.S.S.R. in Public Education about Cancer
- `31761119734424#242` leaf 242/852 [reference_list] New reproductive technologies and the health care system : the case fo
  > The Epidemiology of Randomized Controlled Trials 209 Bellinge, B.S., et al. 1986. “The Influence of Patient Insemination on the Implantation Rate in an In Vitro Fertilization and Embryo Transfer Program.” Fertility and Sterility 46: 252-56.
- `39040218110154#41` leaf 41/76 [reference_list] REPORT OF THE ONTARIO COUNCIL OF HEALTH - SUPPLEMENT NO. - 3 HEALTH MA
  > 18 10. LAs Section A RECOMMENDATION 6 THAT the number of full-time general practitioners or family physicians required be in the ratio of 1 family physician for each 1,500 of population: range 1/1,000 to 1/2,000. This may be modified by cha
- `39171007050127#415` leaf 415/716 [reference_list] Overview of legal issues in new reproductive technologies.
  > 394 Overview of Legal Issues in NRTs Baechtold, R.L., et al. “Property Rights in Living Matter: Is New Law Required?” Denver University Law Review 68 (1991): 141-72. Beier, D., and R.H. Benson. “Biotechnology Patent Protection Act.” Denver 
- `39291103070074#29` leaf 29/106 [reference_list] REPORT OF THE ROYAL COMMISSION ON ELECTRIC POWER PLANNING: VOL.9 - A B
  > Chilenskas, A.A., et al. Lithium Requirements for High-Energy Lithium-Aluminum/Iron Sulfide Batter- ies for Load-Levelling and Electric-Vehicle Applications. A report prepared for the U.S. Energy Re- search and Development Administration fo
- `albertapatientcl00semr#230` leaf 230/232 [back_zone_list] Alberta patient classification system for long term care facilities : 
  > 1
- `micro_IA40243301_2768#43` leaf 43/47 [reference_list] Standards of evidence for evaluating foods with health claims : a prop
  > 16. 17. 19, 20. 21. 22. 23. 24. 25. 26. 27. 28. 29. Therapeutic Products Directorate. General considerations for clinical trials. ICH Harmonized tripartite guideline. Ottawa (ON): Minister of Public Works and Government Services Canada, 199
- `micro_IA40243301_3116#74` leaf 74/84 [reference_list] Acrylonitrile
  > Mohamadin, A.M., M.H. El-zahaby and A.E. Ahmed. 1996. Acrylonitrile oxidation and cyanide release in cell free system catalyzed by Fenton-like reaction. Toxicologist 30 (1 part 2): 238 (Abstract No. 1220). Morita, T., N. Asano, T. Awogi, Y.
- `occupationalheal00inte#124` leaf 124/524 [reference_list] Occupational health in the chemical industry : proceedings of the Elev
  > 117 3. Chalabreysse, J.; Archimbaud, M. , and Bourgineau, G. 1980. Etude globale des nuisances mutagenes en Hygiene Industrielle: Proposition d'une methodologie . Rapport EUR 7549:433-442. 4. Penalva, J.M.; Chalabreysse, J.; Archimbaud, M. 
- `ontla_354377#140` leaf 140/146 [reference_list] Recommendations for the Prevention, Detection and Management of Occupa
  > 137. Wilke A, Gediga G, Schlesinger T, John SM, Wulfhorst B. Sustainability of interdisciplinary secondary prevention in patients with occupational hand eczema: a 5-year follow-up survey. Contact Dermatitis. 2012;67(4):208-16. 138. Wulfhors
- `reportondesignat01unse#296` leaf 296/424 [reference_list] The report on the designation of noise in Ontario
  > ch REFERENCES Burns, William, Noise and Man. Second Edition 1973, John Murray Co. London. Jonsson, A., and Hansson, L., "Prolonged Exposure to a Stressful Stimulus (Noise) as a Cause of Raised Blood Pressure in Man". Lancet, Pg. 86, January
- `soilinvestcolbor00onta#276` leaf 276/321 [reference_list] Soil investigation and human health risk assessment for the Rodney str
  > Soil Investigation and Human Health Risk Assessment for the Rodney Street Communrty: Port Colbome (2001) Dabeka, R. W and AD. McKensie 1995. Survey of lead, cadmium, fluoride, nickel and cobalt in food composites and estimation of dietary i
