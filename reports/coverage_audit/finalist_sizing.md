# Finalist sizing and window analysis

All counts are real `advancedsearch.php` `numFound` results (the scrape API was
throttled to a canned baseline and was not used). Query shape:
`mediatype:texts AND <clause> AND (<topic term-set>)`. Topic term-sets are in
config/audit_candidates.toml.

## Candidate Canada-scoped clauses

| clause | texts items |
| --- | ---: |
| `collection:governmentpublications` (base, clean gov portal) | 104,219 |
| curated Canadian-government union (9 gov collections) | 105,289 |
| base + `microlog` (Cdn gov/institutional, microfiche-sourced) | 309,555 |

The curated-gov union barely exceeds the base: the other government collections
overlap `governmentpublications` almost entirely. `microlog` is the only lever
that materially grows the corpus, and its OCR quality is unverified here.

## Topic sizing across clauses (2500 floor)

| topic | base gov | curated gov | base + microlog |
| --- | ---: | ---: | ---: |
| housing_affordability | 1,737 (no) | 1,747 (no) | 13,796 (yes) |
| immigration | 1,762 (no) | 1,762 (no) | 5,174 (yes) |
| public_health | 3,413 (yes) | 3,477 (yes) | 16,857 (yes) |

Only public_health clears 2,500 within a clean Canadian-government scope. Housing
and immigration require `microlog` to qualify.

## Recency (within `collection:governmentpublications`)

| topic | 1990-2009 | 2010+ | 2015+ |
| --- | ---: | ---: | ---: |
| housing_affordability | 719 | 4 | 1 |
| immigration | 666 | 23 | 2 |
| public_health | 1,352 | 44 | 18 |

Post-2010 scanned-OCR government publications are nearly absent across all topics.
The proposal's example comparison year of 2025 is not supportable from this
archive. The realistic window is roughly the 1950s/1960s through about 2009, with
the dense band in the 1970s-2000s.

## OCR presence (25-item samples, base gov clause)

All three topics: 100% of sampled items carry usable OCR text (DjVuTXT etc.), from
uoft/alberta scanning centers. Undated fraction: housing 3/25, immigration 2/25,
public_health 7/25. Sample decade spread confirms the pre-2000 skew and the
absence of 2010s+ items. NOTE: this OCR figure is for governmentpublications, not
microlog.
