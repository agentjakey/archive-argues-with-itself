# Discovery and sizing pass

Search surface: advancedsearch.php (scrape API was throttled to a canned baseline).
Base Canada-scoped clause: `collection:governmentpublications` = 104293 items.

## 1. Collections found in the housing sample
Sample size: 20 real topical items.

| collection | appears in N items |
| --- | ---: |
| governmentpublications | 20 |
| toronto | 20 |
| albertagovernmentpublications | 9 |
| university_of_alberta_libraries | 9 |
| robarts | 5 |
| university_of_toronto | 5 |
| uoftgovpubs | 4 |
| ministryoffinance_ontario | 3 |
| ocul_govinfocommunity | 3 |
| hpl-govdocs | 2 |
| hamiltonpubliclibrary | 2 |
| microlog | 1 |
| microfiche | 1 |
| taskforce_reports | 1 |
| canadianmunicipal | 1 |
| ontarioeconomiccouncil | 1 |

Scanning centers: alberta (9), uoft (8), hamilton (2), sanfrancisco (1)

## 2. Collection sizes

| collection | total items | texts items |
| --- | ---: | ---: |
| governmentpublications | 104293 | 104219 |
| toronto | 1001392 | 969916 |
| albertagovernmentpublications | 18150 | 18150 |
| university_of_alberta_libraries | 294989 | 271913 |
| robarts | 268077 | 268067 |
| university_of_toronto | 408143 | 408068 |
| uoftgovpubs | 52502 | 52502 |
| ministryoffinance_ontario | 801 | 798 |
| ocul_govinfocommunity | 1910 | 1898 |
| hpl-govdocs | 3077 | 3077 |
| hamiltonpubliclibrary | 3680 | 3672 |
| microlog | 207863 | 207863 |
| microfiche | 1056678 | 1056552 |
| taskforce_reports | 122 | 122 |
| canadianmunicipal | 762 | 761 |
| ontarioeconomiccouncil | 204 | 204 |

## 3. Topic sizing (can each clear 2500?)

| topic | count in base clause | reaches 2500 | count in union clause | reaches 2500 |
| --- | ---: | :---: | ---: | :---: |
| housing_affordability | 1737 | no | 18256 | yes |
| immigration | 1762 | no | 22111 | yes |
| public_health | 3413 | yes | 50805 | yes |

## 4. OCR-derivative spot check

| topic | sample | usable text % | any OCR % | undated | decade distribution |
| --- | ---: | ---: | ---: | ---: | --- |
| housing_affordability | 25 | 100.0 | 100.0 | 3 | 1960s:1, 1970s:4, 1980s:7, 1990s:4, 2000s:6 |
| immigration | 25 | 100.0 | 100.0 | 2 | 1950s:2, 1970s:1, 1980s:5, 1990s:4, 2000s:11 |
| public_health | 25 | 100.0 | 100.0 | 7 | 1950s:2, 1970s:6, 1980s:4, 1990s:6 |
