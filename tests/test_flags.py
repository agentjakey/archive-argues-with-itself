"""Harm-adjacent flagging: positives, mandatory benign negatives, per-topic crisis-line
mapping, and answer-basis narrowing. Precision on the care-critical topics is the point of
this suite: an equipment/food sterilization line or a "hearing aid" must never be mislabeled."""
from __future__ import annotations

from archive_debugger import crisis, flags


def row(text, title="", year=None, in_prompt=True, cited=False):
    """An /ask evidence row. Defaults to an answer-basis row (in_prompt) so a bare
    flagged_topics(text) call exercises matching; pass in_prompt=False for a pool-tail row."""
    return {"title": title, "snippet": text, "year": year, "in_prompt": in_prompt, "cited": cited}


def topics(text, title=""):
    return flags.flagged_topics([row(text, title=title)])


# --- positives: each topic must flag on genuine content ---

def test_positive_tainted_blood():
    assert "tainted-blood-krever" in topics("the Krever inquiry into the tainted blood system")
    assert "tainted-blood-krever" in topics("contaminated blood distributed through the blood system")


def test_positive_sterilization():
    # the base coerced-sterilization topic fires on coercion/eugenics phrasing with no Indigenous
    # context; it is upgraded to the Indigenous variant only when Indigenous context is present.
    assert "coerced-sterilization" in topics("cases under the Sexual Sterilization Act")
    assert "coerced-sterilization" in topics("the eugenics board authorized the procedure")
    assert "coerced-sterilization-indigenous" in topics("coerced sterilization of Indigenous women without consent")


def test_positive_residential_school():
    assert "residential-school-health" in topics("health conditions in Indian residential schools")
    assert "residential-school-health" in topics("the residential school health support program")


def test_positive_hiv_aids():
    assert "early-hiv-aids" in topics("provincial HIV/AIDS prevention program")
    assert "early-hiv-aids" in topics("human immunodeficiency virus transmission")
    assert "early-hiv-aids" in topics("acquired immune deficiency syndrome surveillance")


# --- mandatory negatives: benign confusables must NOT flag ---

def test_equipment_sterilization_never_flags():
    for t in [
        "sterilization of surgical instruments",
        "sterilized milk for infants",
        "water sterilization plant upgrade",
        "food sterilization by canning",
        "autoclave and instrument sterilization procedures",
        "chemical sterilization of laboratory glassware",
    ]:
        assert flags.flagged_topics([row(t)]) == [], t


def test_aid_confusables_never_flag_hiv():
    for t in [
        "hearing aid clinic",
        "hearing aids for seniors",
        "visual aids in classrooms",
        "teaching aids catalogue",
        "first aid training",
        "study aids for students",
        "mobility aids assessment",
    ]:
        assert "early-hiv-aids" not in flags.flagged_topics([row(t)]), t


def test_routine_blood_never_flags():
    for t in [
        "blood donation clinic schedule",
        "blood bank inventory report",
        "blood pressure screening campaign",
        "blood-borne pathogen infection control",
    ]:
        assert "tainted-blood-krever" not in flags.flagged_topics([row(t)]), t


def test_general_school_health_not_residential():
    for t in [
        "school health program for local children",
        "high school immunization clinic",
        "nursing in the public school system",
    ]:
        assert "residential-school-health" not in flags.flagged_topics([row(t)]), t


# --- per-topic crisis-line mapping, with de-duplication on multi-topic ---

def _keys(ev):
    return [r["key"] for r in flags.detect(ev)["crisis_lines"]]


def test_crisis_lines_map_per_topic():
    # topic -> resource keys, in display order, from the single source of truth (archive_debugger.crisis)
    assert _keys([row("HIV/AIDS report", year=1990)]) == ["helpline_988"]
    assert _keys([row("Krever tainted blood", year=1997)]) == ["helpline_988"]
    # generic coerced-sterilization (no Indigenous context) -> 9-8-8 only
    assert _keys([row("Sexual Sterilization Act", year=1972)]) == ["helpline_988"]
    # the Indigenous variant (Indigenous context present) -> the Indigenous-specific lines
    assert _keys([row("Sexual Sterilization Act for Indigenous women", year=1972)]) == ["hope_for_wellness", "mmiwg_crisis_line", "helpline_988"]
    assert _keys([row("Indian residential schools", year=2004)]) == ["irs_crisis_line", "hope_for_wellness", "helpline_988"]
    # the served objects are the full resources from the single source of truth, not bare numbers
    line = flags.detect([row("HIV/AIDS report", year=1990)])["crisis_lines"][0]
    assert line == crisis.resource("helpline_988")
    assert set(line) >= {"key", "label", "contact", "hours", "for"}


def test_default_resources_for_gaps_care_note():
    # the Gaps care note is filled with default_indigenous_sensitive (helpline_988 then hope_for_wellness)
    assert [r["key"] for r in crisis.default_resources("indigenous_sensitive")] == ["helpline_988", "hope_for_wellness"]
    assert [r["key"] for r in crisis.default_resources("other_sensitive")] == ["helpline_988"]


def test_multi_topic_dedupes_crisis_lines():
    ev = [row("Indian residential school health"), row("coerced sterilization of Indigenous women")]
    d = flags.detect(ev)
    # Both Tier A topics fire; "Indigenous + sterilization" additionally fires the Tier B
    # sterilization-reproductive topic, which maps to no crisis line, so the dedup below is unaffected.
    assert {"residential-school-health", "coerced-sterilization-indigenous"} <= set(d["topics"])
    keys = [r["key"] for r in d["crisis_lines"]]
    assert keys.count("hope_for_wellness") == 1        # maps to both topics, deduped
    assert "irs_crisis_line" in keys and "mmiwg_crisis_line" in keys


# --- answer-basis narrowing (FIX 2) ---

def test_pool_tail_row_does_not_flag():
    ev = [row("HIV/AIDS clinic services", in_prompt=False, cited=False)]   # tangential pool-tail
    assert flags.flagged_topics(ev) == []
    assert flags.detect(ev) is None


def test_in_prompt_or_cited_row_flags():
    assert "early-hiv-aids" in flags.flagged_topics([row("HIV/AIDS clinic services", in_prompt=True, cited=False)])
    assert "early-hiv-aids" in flags.flagged_topics([row("HIV/AIDS clinic services", in_prompt=False, cited=True)])


def test_year_is_earliest_matching_row():
    ev = [row("HIV report", year=1995, in_prompt=True), row("HIV report", year=1988, in_prompt=True)]
    assert flags.detect(ev)["year"] == 1988


def test_clean_content_returns_none():
    assert flags.detect([row("tobacco taxation and smoking cessation", year=1999)]) is None


# --- widened scan surface (prompt 6): the SAME patterns also run over the question + answer ---

BENIGN = [row("tobacco taxation and smoking cessation", year=1999)]   # served rows that alone do NOT flag


def test_widened_scan_flags_from_question():
    # harm content the user explicitly asks about carries the care note even when the served snippets
    # alone did not trigger it (the p097 / p114 open-input breach).
    d = flags.detect(BENIGN, question="coerced sterilization of Indigenous women")
    assert d and "coerced-sterilization-indigenous" in d["topics"]
    d = flags.detect(BENIGN, question="Red Cross contaminated blood")
    assert d and "tainted-blood-krever" in d["topics"]


def test_widened_scan_flags_from_answer():
    # harm content the model composed carries the care note. Native communities -> Indigenous variant.
    d = flags.detect(BENIGN, answer_text="Forced sterilization programs were imposed on many Native communities.")
    assert d and "coerced-sterilization-indigenous" in d["topics"]
    # involuntary sterilization with no Indigenous context -> the generic coerced-sterilization topic
    d = flags.detect(BENIGN, answer_text="the right to be free from involuntary sterilization")
    assert d and "coerced-sterilization" in d["topics"]
    assert "coerced-sterilization-indigenous" not in d["topics"]


def test_widened_scan_preserves_precision():
    # a genuinely benign question + answer must NOT start firing (no pattern or term-list change).
    assert flags.detect(BENIGN, question="how do I fix a flat bike tire",
                        answer_text="Loosen the valve and patch the tube.") is None
    # confusables stay benign through the widened surface too
    assert flags.detect(BENIGN, question="sterilization of surgical instruments",
                        answer_text="Autoclave the instruments before each use.") is None


def test_widened_scan_backward_compatible():
    # detect(evidence) with no question/answer is byte-identical to before (snippet-only).
    assert flags.detect(BENIGN) is None
    d = flags.detect([row("HIV/AIDS report", year=1990)], question="unrelated tobacco question")
    assert d["topics"] == ["early-hiv-aids"]   # still flags from the row; the question adds nothing here


def test_widened_scan_year_from_rows_only():
    # a topic that fires only from the question/answer has no row-year, so year is None (graceful).
    d = flags.detect(BENIGN, question="coerced sterilization of Indigenous women")
    assert d["year"] is None


# --- care tiers (pre-festival): Tier B calm note, Tier C medical-advice note, both with NO crisis line ---

def _lines(d):
    return [r["key"] for r in (d or {}).get("crisis_lines", [])]


def test_tier_b_sterilization_reproductive():
    # human/reproductive sterilization fires Tier B, which maps to no crisis line.
    for t in ["tubal ligation is a form of sterilization", "a vasectomy or tubal sterilization",
              "sterilization for contraceptive reasons", "sterilizations were performed when they should not have been"]:
        d = flags.detect([row(t)])
        assert d and "sterilization-reproductive" in d["topics"], t
        assert _lines(d) == [], t   # Tier B: no crisis line
    # bare equipment/food/water sterilization still never flags any tier
    for t in ["sterilization of surgical instruments", "sterilized milk for infants",
              "water sterilization plant", "autoclave sterilization procedures"]:
        assert flags.flagged_topics([row(t)]) == [], t


def test_tier_b_sexual_content_minors():
    for t in ["disrespectful sexual attitudes", "when children act out sexually",
              "sexual counselling in this area", "child sexual abuse reporting"]:
        d = flags.detect([row(t)])
        assert d and "sexual-content-minors" in d["topics"], t
        assert _lines(d) == [], t
    # routine sexual-health public-health content must NOT flag
    for t in ["sexually transmitted disease prevention", "sexual health clinic hours",
              "family planning and birth control"]:
        assert "sexual-content-minors" not in flags.flagged_topics([row(t)]), t


def test_tier_c_immunization_guidance():
    for t in ["the recommended immunization schedule", "a vaccination schedule with four doses",
              "fully immunized children at age two", "completed the primary series"]:
        d = flags.detect([row(t)])
        assert d and "immunization-guidance" in d["topics"], t
        assert _lines(d) == [], t
    # administrative / clinic content is not guidance a visitor mistakes for current advice
    assert "immunization-guidance" not in flags.flagged_topics([row("the department maintains immunization records")])
    assert "immunization-guidance" not in flags.flagged_topics([row("high school immunization clinic")])


def test_tier_c_hepatitis_transmission():
    d = flags.detect([row("a person can become infected with Hepatitis C through blood transfusions")])
    assert d and "hepatitis-transmission" in d["topics"]
    assert _lines(d) == []   # Tier C: no crisis line


def test_tiers_map_and_crisis_mapping_consistent():
    # every detection topic has a tier; TIERS also carries the derived coerced-sterilization-indigenous
    # key (upgraded in detect, not a TOPIC_SIGNALS pattern). Only Tier A topics map to crisis resources.
    assert set(flags.TOPIC_SIGNALS) <= set(flags.TIERS)
    assert set(flags.TIERS) - set(flags.TOPIC_SIGNALS) == {"coerced-sterilization-indigenous"}
    for topic, tier in flags.TIERS.items():
        mapped = bool(crisis.TOPIC_RESOURCES.get(topic))
        assert mapped == (tier == "A"), (topic, tier, mapped)


# --- Tier C hepatitis demotion: an incidental HIV/blood TITLE match on a routine hepatitis answer ---

def _hep_rows():
    # the shown record: a combined "HIV, hepatitis C and STD" survey title (so early-hiv-aids fires
    # from the title) plus a hepatitis-transmission snippet. This mirrors the real pilot record.
    return [row("blood transfusion with infected blood", title="HIV, hepatitis C and STD issues in Alberta")]


def test_hepatitis_demotion_drops_incidental_hiv_on_answer():
    # answered path: a hepatitis-transmission answer with no HIV/scandal in the user text -> the
    # incidental early-hiv-aids / tainted-blood title match is dropped, so NO crisis line (Tier C).
    d = flags.detect(_hep_rows(), question="contaminated blood and hepatitis C",
                     answer_text="A person can become infected with Hepatitis C through blood transfusions with infected blood.")
    assert d and "hepatitis-transmission" in d["topics"]
    assert "early-hiv-aids" not in d["topics"]
    assert "tainted-blood-krever" not in d["topics"]
    assert _lines(d) == []   # the whole point: no suicide line on a disease-transmission answer


def test_hepatitis_demotion_preserved_when_answer_is_about_hiv():
    # a genuine HIV/AIDS epidemic answer that also mentions hepatitis KEEPS its crisis line.
    d = flags.detect(_hep_rows(), question="HIV AIDS and hepatitis C co-infection",
                     answer_text="HIV and hepatitis C co-infection was common among people with AIDS in the 1980s.")
    assert d and "early-hiv-aids" in d["topics"]
    assert "helpline_988" in _lines(d)


def test_hepatitis_demotion_preserved_when_scandal_named():
    # when the user text names the scandal, the tainted-blood crisis line is kept.
    d = flags.detect(_hep_rows(), question="the Krever tainted blood scandal",
                     answer_text="The tainted blood scandal infected people with hepatitis C.")
    assert d and "tainted-blood-krever" in d["topics"]
    assert "helpline_988" in _lines(d)


def test_hepatitis_demotion_gated_to_user_text():
    # snippet-only (no question/answer): byte-identical to before, so an HIV title still flags with
    # its crisis line. The demotion is an answer/limited-mode refinement only.
    d = flags.detect(_hep_rows())
    assert "early-hiv-aids" in d["topics"]
    assert "helpline_988" in _lines(d)


# --- French / bilingual alternates (ASCII forms; the scanned text is accent-stripped for matching) ---

def test_french_alternates_fire_tier_a():
    assert "residential-school-health" in topics("au sujet des pensionnats indiens et la sante")
    # "autochtones" is Indigenous context, so the forced-sterilization French phrase upgrades
    assert "coerced-sterilization-indigenous" in topics("la sterilisation forcee des femmes autochtones")
    # eugenics with no Indigenous context -> the generic coerced-sterilization topic
    assert "coerced-sterilization" in topics("l'eugenisme au Canada")
    assert "tainted-blood-krever" in topics("le scandale du sang contamine")
    assert "early-hiv-aids" in topics("prevention du VIH et du SIDA")


# --- Fix 1: coerced tubal ligation / tubes tied without consent are Tier A (coerced-sterilization) ---

def test_coerced_tubal_ligation_is_tier_a():
    for t in ["coerced tubal ligation", "forced tubal ligation", "non-consensual tubal ligation",
              "tubal ligation without consent", "her tubes were tied without consent",
              "ligature des trompes forcee"]:
        tp = topics(t)
        assert ("coerced-sterilization" in tp or "coerced-sterilization-indigenous" in tp), t
        # it carries a crisis line (Tier A), unlike plain voluntary tubal ligation (Tier B only)
        d = flags.detect([row(t)])
        assert "helpline_988" in _lines(d), t


def test_sterilization_without_consent_is_tier_a():
    # general "sterilization without consent" is coerced sterilization (Tier A), not the calm Tier B
    # note (generalized from the tubal case per Fix 1's principle).
    for t in ["sterilization without consent", "women sterilized without their consent",
              "non-consensual sterilization of patients"]:
        d = flags.detect([row(t)])
        tp = d["topics"]
        assert ("coerced-sterilization" in tp or "coerced-sterilization-indigenous" in tp), t
        assert "helpline_988" in _lines(d), t
    # a voluntary "with informed consent" discussion does NOT escalate to Tier A
    d = flags.detect([row("sterilization performed only with informed consent of the patient")])
    tp = (d or {}).get("topics", [])
    assert "coerced-sterilization" not in tp and "coerced-sterilization-indigenous" not in tp


def test_plain_tubal_ligation_stays_tier_b():
    # voluntary / contraceptive tubal ligation with no coercion keeps its Tier B mapping (no crisis).
    for t in ["tubal ligation is a form of contraception", "tubal ligation and vasectomy options"]:
        tp = topics(t)
        assert "sterilization-reproductive" in tp, t
        assert "coerced-sterilization" not in tp and "coerced-sterilization-indigenous" not in tp, t
        assert _lines(flags.detect([row(t)])) == [], t


# --- Fix 2: the Indigenous attribution/lines fire only when the record shows Indigenous context ---

def test_coerced_sterilization_without_indigenous_context_is_generic():
    # the BC Sexual Sterilization Act / institution-patients case: coerced-sterilization fires, but with
    # no Indigenous context it stays generic -> 9-8-8 only, NOT the Indigenous-specific lines.
    d = flags.detect([row("the Sexual Sterilization Act and institution patients", title="forced sterilisation in British Columbia")],
                     question="forced sterilisation",
                     answer_text="British Columbia's Sexual Sterilization Act authorized sterilization of institution patients.")
    assert d and "coerced-sterilization" in d["topics"]
    assert "coerced-sterilization-indigenous" not in d["topics"]
    assert _lines(d) == ["helpline_988"]   # 9-8-8 only; no Hope for Wellness / MMIWG line


def test_coerced_sterilization_with_indigenous_context_upgrades():
    # the same coercion, but the answer/evidence shows Indigenous context -> the Indigenous variant,
    # which carries the Indigenous-specific lines (and, on the client, the attribution notice).
    d = flags.detect([row("sterilization of patients")],
                     question="forced sterilisation",
                     answer_text="Forced sterilization was performed on First Nations women without consent.")
    assert d and "coerced-sterilization-indigenous" in d["topics"]
    assert [k for k in _lines(d)] == ["hope_for_wellness", "mmiwg_crisis_line", "helpline_988"]


def test_indigenous_context_terms_including_historical_and_phrases():
    for ctx in ["Indigenous", "First Nations", "Metis", "Inuit", "Aboriginal", "Native women",
                "Indian Act", "treaty rights", "Eskimo", "the band council", "women on reserve"]:
        d = flags.detect([row("sterilization")], answer_text=f"forced sterilization and {ctx}")
        assert d and "coerced-sterilization-indigenous" in d["topics"], ctx
    # "native-born" is NOT Indigenous context (precision): stays generic
    d = flags.detect([row("sterilization")], answer_text="forced sterilization of native-born women")
    assert d and "coerced-sterilization" in d["topics"] and "coerced-sterilization-indigenous" not in d["topics"]


# --- Fix 3: accented French matches (the scanned text is accent-stripped for matching only) ---

def test_accented_french_matches():
    # stripped accents are only for matching; the displayed record is never altered.
    assert "coerced-sterilization-indigenous" in topics("stérilisation forcée des Métis")
    assert "tainted-blood-krever" in topics("le scandale du sang contaminé")
    assert "residential-school-health" in topics("les pensionnats indiens")
    # Indigenous context via an accented historical/French term upgrades coerced-sterilization
    d = flags.detect([row("sterilization")], answer_text="stérilisation forcée des Premières Nations")
    assert d and "coerced-sterilization-indigenous" in d["topics"]
