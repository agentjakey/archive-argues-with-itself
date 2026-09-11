# British Columbia scope: sizing and window analysis

All counts are real `advancedsearch.php` `numFound` results (same surface and throttle canary as the
Week 1 audit; the scrape API is not used). Query shape: `mediatype:texts AND <clause> AND (<topic
term-set>)`, topic term-set `public_health` from config/audit_candidates.toml. Window clause:
`year:[1960 TO 2009]`. Items with no `year` field fall outside every year clause.
No item was downloaded; OCR presence is read from item metadata.

Search health: baseline `collection:governmentpublications` = 104,302 (canary passed).

## Where BC health texts live

Sample: 30 real texts matching `(publisher:("British Columbia") OR creator:("British Columbia"))` and the topic term-set.

| collection | appears in N sampled items |
| --- | ---: |
| medicalheritagelibrary | 16 |
| medicallibrary | 15 |
| toronto | 12 |
| microlog | 12 |
| microfiche | 12 |
| mcgilluniversity | 11 |
| mcgilluniversityosler | 11 |
| medicalofficerofhealthreports | 5 |
| wellcomelibrary | 5 |
| ukmhl | 5 |
| europeanlibraries | 5 |
| internetarchivebooks | 2 |
| inlibrary | 2 |
| printdisabled | 2 |
| governmentpublications | 1 |

Scanning centers: sanfrancisco (12), euston (5), cebu (2)

## Sizing: BC-scoped clauses and the collections the sample lives in

`bc_issuer*` rows are BC scopes (the issuer names British Columbia). The collection rows size the
whole collections the sampled items belong to; they are context for where BC material sits, not BC
scopes, and `bc_union` is their union. `pilot_gov` is the public-health pilot's own clean clause.

| scope | clause | texts items | public_health | in 1960-2009 | 1990-2009 | 2010+ | pre-1960 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| bc_issuer | `(publisher:("British Columbia") OR creator:("British Columbia"))` | 15,816 | 590 | 278 | 209 | 199 | 109 |
| medicalheritagelibrary | `collection:medicalheritagelibrary` | 370,214 | 111,052 | 26,865 | 4,576 | 2,481 | 81,080 |
| medicallibrary | `collection:medicallibrary` | 376,919 | 111,680 | 26,939 | 4,580 | 2,496 | 81,619 |
| microlog | `collection:microlog` | 207,863 | 13,544 | 8,726 | 6,598 | 4,379 | 0 |
| mcgilluniversity | `collection:mcgilluniversity` | 28,270 | 417 | 12 | 3 | 1 | 401 |
| mcgilluniversityosler | `collection:mcgilluniversityosler` | 1,691 | 316 | 0 | 0 | 1 | 314 |
| medicalofficerofhealthreports | `collection:medicalofficerofhealthreports` | 68,430 | 65,698 | 17,410 | 20 | 0 | 48,287 |
| wellcomelibrary | `collection:wellcomelibrary` | 190,702 | 76,476 | 18,219 | 419 | 31 | 58,219 |
| ukmhl | `collection:ukmhl` | 240,056 | 83,111 | 18,140 | 417 | 35 | 64,927 |
| bc_union | `collection:(medicalheritagelibrary OR medicallibrary OR microlog OR mcgilluniversity OR mcgilluniversityosler OR medicalofficerofhealthreports OR wellcomelibrary OR ukmhl)` | 612,220 | 125,483 | 35,687 | 11,183 | 6,876 | 81,853 |
| bc_issuer_in_union | `(publisher:("British Columbia") OR creator:("British Columbia")) AND collection:(medicalheritagelibrary OR medicallibrary OR microlog OR mcgilluniversity OR mcgilluniversityosler OR medicalofficerofhealthreports OR wellcomelibrary OR ukmhl)` | 5,409 | 502 | 236 | 193 | 162 | 101 |
| pilot_gov | `collection:governmentpublications` | 104,228 | 3,413 | 2,224 | 1,352 | 44 | 151 |

Topic items outside every year column carry no `year` field (undated), which the pilot corpus
showed to be a large share.

## BC scopes against the 2,500 floor

- bc_issuer: 590 public_health texts (no on raw count); 278 dated 1960-2009 (no).
- bc_issuer_in_union: 502 public_health texts (no on raw count); 236 dated 1960-2009 (no).
- pilot_gov: 3,413 public_health texts (yes on raw count); 2,224 dated 1960-2009 (no).

## OCR presence (metadata spot check, BC topical sample)

Sample 25 items: 25 with usable OCR text (100.0%), 25 with any OCR derivative (100.0%), 0 undated.
Formats: DjVuTXT 25, OCR Search Text 25, hOCR 25, chOCR 25, Djvu XML 25, Abbyy GZ 5
Decades: 1910s:2, 1920s:10, 1930s:4, 1990s:1, 2000s:3, 2010s:5

## Recommendation

Of the 30 sampled BC health texts, 1 sit in `collection:governmentpublications`, the clean Canadian-government portal the pilot uses (3,413 public-health texts there in total); the rest sit in medical-library and microfiche collections. BC government health publications are not,
on the Internet Archive, a government-portal corpus the way the federal, Ontario and Alberta material is.

Best BC scope by in-window count: `bc_issuer` (`(publisher:("British Columbia") OR creator:("British Columbia"))`): 590 public_health texts, 278 dated 1960-2009. With the spot-check OCR share of 100%, the estimated usable in-window count is 278 against the 2,500 floor: **does not clear**.

BC does not clear the 2,500 floor in the 1960-2009 window; a BC scope would need a lower floor, a wider window, or a broader topic term-set.

Method caveats: `year:[a TO b]` excludes items with no year field, so undated items (which the pilot could
partly recover from titles) are not in the window counts; the publisher/creator clause depends on IA
metadata naming the province and misses items whose issuer is a BC ministry named without the province;
OCR share is from a 25-item metadata sample. The code path is the same as the pilot's: a BC scope is a new
`config/pilot.toml` (query, collections, window) and a new manifest, not a code change.
