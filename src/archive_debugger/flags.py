"""Harm-adjacent topic flagging (additive, N5-safe), in three proportionate care tiers.

Reads only the served-evidence fields already on each /ask evidence row (title, snippet,
year, and the in_prompt / cited markers) plus, on the answer and limited-mode paths, the
user's question and the model's answer (the widened scan). It touches neither retrieval nor
the abstention gate. It is computed ON SERVE and never stored in the answer cache, so it fires
identically for a cached answer, a real abstention, and the offline limited-mode state.

Tiers (the client, web/src/lib/sensitivity.ts, holds the authoritative tier -> treatment render;
TIERS below mirrors the mapping for auditability and tests):

- Tier A, crisis care: residential-school health and coerced sterilization (contextual note,
  tap-through interstitial, and crisis lines; residential-school and the Indigenous variant of
  coerced sterilization also get the attribution-incomplete notice), and tainted-blood /
  early-HIV-AIDS (contextual note and a crisis line). Only Tier A topics map to crisis resources
  (archive_debugger.crisis).
- Tier B, a calm historical-content note, NO crisis line: human/reproductive sterilization and
  sexual content (especially involving children) that is sensitive but does not warrant crisis
  resources.
- Tier C, a "not current medical advice" note, NO crisis line: immunization/vaccination schedule
  and dose guidance, hepatitis disease-transmission guidance, and drug dosing / treatment
  instructions a visitor could mistake for current advice.

Coerced sterilization has two topic keys that differ only in treatment:
- `coerced-sterilization` (the base, pattern-detected): coercion/eugenics/consent-plus-procedure
  phrasing, including coerced tubal ligation / tubes tied without consent. Treatment: interstitial +
  contextual note + 9-8-8.
- `coerced-sterilization-indigenous` (derived): the base topic UPGRADED when Indigenous context
  appears in the user-facing text (question, answer, or shown evidence). It additionally carries the
  attribution-incomplete notice and the Indigenous-specific lines (Hope for Wellness, the MMIWG line).
  The attribution notice is a factual claim ("a government record about an Indigenous community"), so
  it is shown only when the record actually shows Indigenous context. Residential-school content is
  inherently about Indigenous communities and always carries the full treatment, never gated.

Two design rules keep it proportionate:

- Answer-basis, not the whole pool. A topic counts only when it appears in a row the visitor
  actually reads as the answer basis (in_prompt or cited), or in the question / answer text. A
  tangential retrieved-pool row the model never used does not trigger a flag.

- Precision over recall on the care-critical topics, because a false positive here is worse than a
  miss. In particular, "sterilization" in this corpus is overwhelmingly the benign
  equipment/water/food/milk sense (700+ passages), so bare "sterilization" is NOT matched by any
  tier: only unambiguous coercion/eugenics phrasing (Tier A) or human/reproductive phrasing such as
  tubal ligation / vasectomy / contraceptive sterilization (Tier B) counts.

Accent-insensitive matching: the patterns are ASCII (project rule), but the text being scanned is
normalized for matching only (diacritics stripped), so accented French (sterilisation forcee written
with its accents, Metis, Premieres Nations, sang contamine, and so on) matches the ASCII patterns.
The displayed record is never altered; normalization applies only to the copy being searched.

Tier-C hepatitis demotion: a routine hepatitis-transmission answer can pull in an incidental
early-HIV/AIDS or tainted-blood match from a SOURCE TITLE (for example a combined "HIV, hepatitis C
and STD" survey) that is not what the visitor is actually reading. When the user-facing text
(question + answer) is itself about hepatitis transmission and names neither HIV/AIDS nor the blood
scandal, those two Tier-A crisis topics are dropped so the result carries the calm Tier-C note
instead of a suicide crisis line. It is gated on user-facing text being present, so the snippet-only
paths (/stories, /flag, a pure abstention) stay byte-identical.

Tune the detection by editing TOPIC_SIGNALS (topic key -> regex patterns, matched
case-insensitively against accent-stripped text). The topic-to-resource mapping and the crisis
numbers live in archive_debugger.crisis, the single source of truth; nothing here holds a number.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from archive_debugger import crisis

TOPIC_SIGNALS: dict[str, list[str]] = {
    # --- Tier A: crisis care (maps to crisis.TOPIC_RESOURCES) ---
    # The 1997 Krever inquiry into the contaminated blood system. Kept to the scandal's own
    # vocabulary; routine "blood supply"/"blood-borne" phrasings are intentionally excluded
    # so a blood-donation or infection-control line does not flag. French: sang contamine.
    "tainted-blood-krever": [
        r"\bkrever\b",
        r"\btainted blood\b",
        r"\bcontaminated blood\b",
        r"\bblood system\b",
        r"\bsang contamine\b",
        r"\bsang souille\b",
        r"\bscandale du sang\b",
    ],
    # Coerced human sterilization / the eugenics era (the BASE topic; upgraded to
    # coerced-sterilization-indigenous when Indigenous context is present, see detect). ONLY
    # unambiguous phrasing: bare "sterilization" is not matched (it is almost always
    # milk/food/water/instrument sterilization in this corpus). Coerced tubal ligation / tubes tied
    # without consent are included here (Tier A), while plain voluntary/contraceptive tubal ligation
    # stays Tier B (sterilization-reproductive).
    "coerced-sterilization": [
        # steril(iz|is) covers both the American and British spellings; the sexual/act/coercion/
        # eugenic qualifiers still gate every pattern, so bare "sterilization" is still not matched.
        r"\bsexual steril(?:iz|is)\w*",
        r"\bsteril(?:iz|is)ation act\b",
        r"\b(?:forced|coerced|involuntary|compulsory)\s+steril(?:iz|is)\w*",
        r"\beugenic\w*",
        # Coerced tubal ligation / tubes tied: coercion or consent language plus the procedure.
        r"\b(?:forced|coerced|involuntary|compulsory|non-?consensual)\s+tubal ligation\b",
        r"\btubal ligation\b.{0,40}\bwithout consent\b",
        r"\bwithout consent\b.{0,40}\btubal ligation\b",
        r"\b(?:forced|coerced|involuntary|compulsory|non-?consensual)\s+(?:tubal ligation|tying of (?:the )?(?:fallopian )?tubes)\b",
        r"\btubes\b.{0,12}\btied\b.{0,30}\bwithout consent\b",
        r"\bwithout consent\b.{0,30}\btubes\b.{0,12}\btied\b",
        # Sterilization WITHOUT consent (any form, generalizing the tubal case per Fix 1's principle:
        # coercion or consent language plus the procedure is Tier A). Gated on "without ... consent",
        # so a voluntary "with informed consent" discussion stays out of Tier A.
        r"\bsteril(?:iz|is)\w*.{0,40}\bwithout (?:their |her |his |informed |any |proper )?consent\b",
        r"\bwithout (?:their |her |his |informed |any |proper )?consent\b.{0,40}\bsteril(?:iz|is)\w*",
        r"\bnon-?consensual steril(?:iz|is)\w*",
        r"\bsteril(?:iz|is)ation\b.{0,40}sans (?:leur |son )?consentement",   # French
        r"\bsans (?:leur |son )?consentement\b.{0,40}steril(?:iz|is)ation",   # French
        # French alternates (ASCII; the scanned text is accent-stripped before matching).
        r"\bsteril(?:iz|is)ation\s+(?:forcee|forcees|contrainte|imposee|sexuelle)\b",
        r"\beugenisme\w*",
        r"\bligature des trompes\b.{0,40}(?:forcee|forcees|contrainte|imposee|sans consentement|sans le consentement)",
        r"\b(?:forcee|forcees|sans consentement|sans le consentement)\b.{0,40}\bligature des trompes\b",
    ],
    "residential-school-health": [
        r"\bresidential school\w*",
        r"\bindian residential\b",
        # French: pensionnat(s) (indiens / autochtones).
        r"\bpensionnat\w*",
    ],
    # Keyed on "hiv" and the spelled-out forms, which appear in essentially every genuine
    # HIV/AIDS document in this corpus. Bare "aids" is intentionally NOT matched: it collides
    # with hearing/visual/teaching/mobility/band aids in a health corpus. French: SIDA / VIH
    # (explicitly requested; less confusable than bare "aids").
    "early-hiv-aids": [
        r"\bhiv\b",
        r"\bhiv/aids\b",
        r"\bacquired immune deficiency\b",
        r"\bacquired immunodeficiency\b",
        r"\bhuman immunodeficiency\b",
        r"\bsida\b",
        r"\bvih\b",
    ],
    # --- Tier B: calm historical-content note, NO crisis line ---
    # Human / reproductive sterilization that is sensitive but not the Tier-A coercion/eugenics case.
    # Only unambiguous human/reproductive phrasing, so equipment/food/water/instrument sterilization
    # (the dominant benign sense) never matches. Content with explicit coercion/eugenics language also
    # hits Tier A, which outranks this; that overlap is intentional and harmless.
    "sterilization-reproductive": [
        r"\btubal ligation\b",
        r"\btubal steril(?:iz|is)\w*",
        r"\bvasectom\w*",
        r"\bligature des trompes\b",                               # French tubal ligation
        r"\bconsent\w*.{0,40}steril(?:iz|is)\w*",                  # consent + sterilization
        r"\bsteril(?:iz|is)\w*.{0,40}consent\w*",
        r"\bsteril(?:iz|is)\w*.{0,60}should not have been\b",      # "sterilizations performed when they should not have been"
        r"\bshould not have been.{0,60}steril(?:iz|is)\w*",
        r"\b(?:indigenous|aboriginal|first nations|inuit|metis)\b.{0,40}steril(?:iz|is)\w*",
        r"\bsteril(?:iz|is)\w*.{0,40}(?:indigenous|aboriginal|first nations|inuit|metis)\b",
        r"\bcontracept\w*.{0,30}steril(?:iz|is)\w*",               # contraceptive + sterilization
        r"\bsteril(?:iz|is)\w*.{0,30}contracept\w*",
        r"\breproductive steril(?:iz|is)\w*",
        r"\bsteril(?:iz|is)ation (?:de|des) (?:femmes|hommes|personnes)\b",   # French
    ],
    # Sexual content, especially anything involving children. Gated to attitudes/counselling, "act
    # out sexually", and child-sexual phrasing so routine "sexually transmitted" / "sexual health"
    # public-health content (ubiquitous here) does not flag.
    "sexual-content-minors": [
        r"\bsexual attitudes?\b",
        r"\bsexual counsell?ing\b",
        r"\bact(?:ing|ed|s)? out sexually\b",
        r"\bchild(?:ren|hood)?\W+(?:\w+\W+){0,3}sexual",
        r"\bsexual\w*\W+(?:\w+\W+){0,2}child(?:ren)?\b",
        r"\bchild sexual (?:abuse|exploitation)\b",
        r"\bsexual (?:abuse|assault|exploitation) of (?:a )?(?:child|children|minors?|young)",
        r"\bagression sexuelle\b",                                 # French sexual assault
        r"\bexploitation sexuelle\b",                              # French sexual exploitation
    ],
    # --- Tier C: "not current medical advice" note, NO crisis line ---
    # Immunization / vaccination schedule and dose guidance (not administrative health-records content).
    "immunization-guidance": [
        r"\bimmuni[sz]ation schedule",
        r"\bvaccination schedule",
        r"\brecommended immuni[sz]ation",
        r"\bprimary series\b",
        r"\bfully immuni[sz]ed\b",
        r"\bimmuni[sz]ation[^.]{0,20}\bdoses?\b",
        r"\bvaccine[^.]{0,15}\bdoses?\b",
        r"\bcalendrier (?:de |d'|des )?(?:vaccination|immunisation)",   # French
    ],
    # Hepatitis disease-transmission guidance. Scoped to hepatitis (the observed case) rather than all
    # disease transmission, which would blanket-fire in a public-health corpus. Drives the Tier-C
    # demotion of an incidental HIV/blood title match on a routine hepatitis-transmission answer.
    "hepatitis-transmission": [
        r"\bhepatitis\s*[abc]\b",
        r"\bhepatitis [abc] virus\b",
        r"\bcontracted hepatitis\b",
        r"\binfected with hepatitis\b",
        r"\bhepatite\s*[abc]\b",                                   # French
    ],
    # Drug dosing and treatment instructions a visitor could mistake for current medical advice (for
    # example "the standard dose ... is 80 mg", "give your child 5 mL every 6 hours"). Gated to drug
    # dosing (a number plus a dose unit, a qualified "dose", "dosage", explicit intervals, or a
    # take/give/administer instruction with a dose) so administrative or epidemiological health content
    # (coverage rates, registries, program descriptions, disease rates) does not fire.
    "dosing-treatment-guidance": [
        r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|ml|microgram|milligram|millilit|millilitre|milliliter)s?\b",
        r"\bdosage\b",
        r"\b(?:standard|recommended|maximum|minimum|usual|single|daily|correct|appropriate|safe|therapeutic|starting|total|divided|per kilogram|per-kilogram) dose\b",
        r"\bdose (?:of|for|form)\b",
        r"\b(?:every \d+(?:\s?(?:to|-)\s?\d+)? hours?|\d+ times (?:a day|daily|per day|each day)|twice (?:a day|daily)|once (?:a day|daily))\b",
        r"\b(?:take|give|administer|apply)\b.{0,25}\b(?:\d+\s?(?:mg|mcg|ml|tablet|teaspoon|drop|dose|pill)|every \d+ hours?)\b",
        r"\bgive (?:your|the|a|my|her|his) child(?:ren)?\b.{0,40}(?:dose|mg|ml|medicine|medication|drug|tablet|teaspoon|fever|every \d)",
    ],
}

# Tier of each topic, for the client's proportionate treatment. crisis.py maps ONLY Tier A topics to
# crisis resources; Tier B and Tier C deliberately map to none. The frontend holds the authoritative
# tier -> treatment rendering; this mirror exists for auditability and tests. coerced-sterilization-
# indigenous is derived in detect() (not a TOPIC_SIGNALS key), so it is listed here explicitly.
TIERS: dict[str, str] = {
    "residential-school-health": "A",
    "coerced-sterilization": "A",
    "coerced-sterilization-indigenous": "A",
    "tainted-blood-krever": "A",
    "early-hiv-aids": "A",
    "sterilization-reproductive": "B",
    "sexual-content-minors": "B",
    "immunization-guidance": "C",
    "hepatitis-transmission": "C",
    "dosing-treatment-guidance": "C",
}

_COMPILED = {t: [re.compile(p, re.IGNORECASE) for p in pats] for t, pats in TOPIC_SIGNALS.items()}

# Indigenous context, in English and French and including the historical terms the record itself
# uses. Matched (accent-insensitively) only when coerced-sterilization has fired, to decide the
# Indigenous upgrade. Word-bounded and precision-first: bare "band"/"reserve" are skipped unless in
# an Indigenous phrase ("band council", "on reserve"); bare "native" is skipped too, because it is
# ambiguous ("native-born", "native population" = a demographic sense). "native" counts only inside an
# Indigenous phrase (native people(s), native community/communities, native woman/women, native
# band(s), native nation(s)); "Native communities" still counts, "native-born" never does.
_INDIGENOUS_CONTEXT = [re.compile(p, re.IGNORECASE) for p in (
    r"\bindigenous\b",
    r"\bfirst nations?\b",
    r"\bmetis\b",
    r"\binuit\b",
    r"\baboriginal\b",
    r"\bnative (?:people|peoples|community|communities|woman|women|band|bands|nation|nations)\b",
    r"\bindian\b",
    r"\bindien\w*",
    r"\bamerindien\w*",
    r"\bautochtone\w*",
    r"\bpremieres? nations?\b",
    r"\btreaty\b",
    r"\btreaties\b",
    r"\beskimo\w*",
    r"\bband council\b",
    r"\bon reserve\b",
)]

# Unambiguous scandal/epidemic names that PROTECT a Tier-A tainted-blood/HIV flag from the Tier-C
# hepatitis demotion: when any of these is in the user-facing text, the content is about the scandal
# or the epidemic (not routine transmission), so the crisis topics are kept.
_SCANDAL_NAMES = re.compile(
    r"\bkrever\b|\btainted[- ]blood\b|\bblood scandal\b|\bblood tragedy\b|"
    r"\bcontaminated blood (?:scandal|tragedy|disaster)\b|"
    r"\bcommission of inquiry on the blood system\b|\bsang contamine\b|\bscandale du sang\b",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    """Accent-stripped copy of text, for MATCHING ONLY. Never alters the displayed record. Lets the
    ASCII patterns match accented French (an accented 'sterilisation forcee', 'Metis', 'Premieres
    Nations', 'sang contamine', and so on). ASCII text is unchanged."""
    if not text:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _haystack(row: dict) -> str:
    return f"{row.get('title') or ''} {row.get('snippet') or ''}"


def _row_topics(row: dict) -> list[str]:
    hay = _norm(_haystack(row))
    return [t for t, pats in _COMPILED.items() if any(p.search(hay) for p in pats)]


# The two lighter crisis topics require a CITED basis on the row scan: a match from a passage that was
# sent to the model (in_prompt) but never cited by the kept answer is incidental and must NOT fire their
# note + 9-8-8 line. The question and the answer text still fire them (see _text_topics), and the
# heavier topics (residential-school, coerced sterilization) are unaffected and fire from any
# answer-basis row.
_CITED_BASIS_ONLY = frozenset({"early-hiv-aids", "tainted-blood-krever"})


def _basis_row_topics(row: dict) -> list[str]:
    """Row topics for the answer-basis scan, applying the cited-basis rule: the two lighter crisis
    topics count only from a cited row; every other topic counts from any answer-basis row."""
    matched = _row_topics(row)
    if row.get("cited"):
        return matched
    return [t for t in matched if t not in _CITED_BASIS_ONLY]


def _answer_basis(evidence: list[dict]) -> list[dict]:
    """The rows that are the basis of what the visitor reads: sent to the model (in_prompt)
    or cited. Excludes tangential retrieved-pool rows. Still non-empty on the abstention and
    offline limited-mode paths, where in_prompt marks the top_k shown record."""
    return [r for r in evidence if r.get("in_prompt") or r.get("cited")]


def _crisis_lines(topics: list[str]) -> list[dict]:
    """Resolve the matched topics to their crisis resources from the single source of truth
    (archive_debugger.crisis): ordered by topic, then each topic's display order, de-duplicated.
    Tier B and Tier C topics map to no resource, so they contribute no crisis line."""
    return crisis.resources_for_topics(topics)


def _indigenous_context(evidence: list[dict], question: Optional[str], answer_text: Optional[str]) -> bool:
    """Whether Indigenous context appears in the user-facing text for this result: the question, the
    answer, or the shown evidence (answer-basis rows). Matched accent-insensitively. Used only to
    upgrade coerced-sterilization to its Indigenous variant, so the attribution-incomplete notice and
    the Indigenous-specific crisis lines are shown only when the record actually shows that context."""
    parts = [question or "", answer_text or ""]
    for row in _answer_basis(evidence):
        parts.append(_haystack(row))
    hay = _norm(" ".join(parts))
    return any(p.search(hay) for p in _INDIGENOUS_CONTEXT)


def _finalize_coerced(topics: set[str], evidence: list[dict],
                      question: Optional[str], answer_text: Optional[str]) -> None:
    """Upgrade the base coerced-sterilization topic to its Indigenous variant in place when Indigenous
    context is present. Residential-school is inherently Indigenous and is handled by its own topic,
    never gated here."""
    if "coerced-sterilization" in topics and _indigenous_context(evidence, question, answer_text):
        topics.discard("coerced-sterilization")
        topics.add("coerced-sterilization-indigenous")


def flagged_topics(evidence: list[dict]) -> list[str]:
    """Topic keys whose signal appears in an answer-basis row's title or snippet (snippet-only path:
    the Indigenous upgrade uses the evidence rows as its context)."""
    found: set[str] = set()
    for row in _answer_basis(evidence):
        found.update(_basis_row_topics(row))
    _finalize_coerced(found, evidence, None, None)
    return sorted(found)


def _text_topics(text: str) -> list[str]:
    """Topics whose signal appears anywhere in a free-text string (the user's question or the model's
    answer). Uses the SAME compiled patterns as the row scan on accent-stripped text; only the scanned
    surface differs, so precision-first is preserved (no pattern or term-list change)."""
    if not text:
        return []
    nt = _norm(text)
    return [t for t, pats in _COMPILED.items() if any(p.search(nt) for p in pats)]


def detect(evidence: list[dict], *, question: Optional[str] = None,
           answer_text: Optional[str] = None) -> Optional[dict]:
    """The `flagged` field for the /ask response, or None. `year` is the earliest year among
    the answer-basis rows that matched a topic, for the client's year-aware contextual note.
    `crisis_lines` is the de-duplicated union of the matched Tier-A topics' mapped lines (Tier B
    and C map to none). The visitor-facing note text and tier are rendered client-side from topics
    + year (not baked here).

    When `question` and/or `answer_text` are supplied (the answer and limited-mode paths, never a
    pure abstention), the SAME care patterns also run over the user's question and the model's
    written answer. coerced-sterilization is upgraded to its Indigenous variant when Indigenous
    context appears in the question, answer, or shown evidence. A Tier-C hepatitis-transmission
    result that would otherwise carry an incidental early-HIV/AIDS or tainted-blood crisis line
    (from a source title, not the visitor's reading) is demoted when the user-facing text is about
    hepatitis transmission and names neither HIV/AIDS nor the blood scandal.

    early-hiv-aids and tainted-blood-krever require a cited basis on the row scan (see
    _basis_row_topics): a match from a passage that was sent to the model but never cited by the kept
    answer does not fire them; the question and answer text still do. The heavier topics are
    unaffected."""
    topics: set[str] = set()
    years: list[int] = []
    for row in _answer_basis(evidence):
        matched = _basis_row_topics(row)
        if matched:
            topics.update(matched)
            if row.get("year") is not None:
                years.append(int(row["year"]))
    for extra in (question, answer_text):
        topics.update(_text_topics(extra or ""))
    # Indigenous upgrade (attribution notice + Indigenous lines only when the record shows it).
    _finalize_coerced(topics, evidence, question, answer_text)
    # Tier-C hepatitis demotion (see the module and function docstrings). Only on the answer /
    # limited-mode paths, where the user-facing text is present.
    user_text = _norm(f"{question or ''} {answer_text or ''}".strip())
    if user_text and "hepatitis-transmission" in topics:
        hiv_in_user = any(p.search(user_text) for p in _COMPILED["early-hiv-aids"])
        scandal_in_user = bool(_SCANDAL_NAMES.search(user_text))
        if not hiv_in_user and not scandal_in_user:
            topics.discard("early-hiv-aids")
            topics.discard("tainted-blood-krever")
    if not topics:
        return None
    ordered = sorted(topics)
    return {"topics": ordered, "year": min(years) if years else None, "crisis_lines": _crisis_lines(ordered)}
