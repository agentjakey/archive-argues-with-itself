"""Harm-adjacent flagging: positives, mandatory benign negatives, per-topic crisis-line
mapping, and answer-basis narrowing. Precision on the care-critical topics is the point of
this suite: an equipment/food sterilization line or a "hearing aid" must never be mislabeled."""
from __future__ import annotations

from archive_debugger import flags


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
    assert "coerced-sterilization-indigenous" in topics("cases under the Sexual Sterilization Act")
    assert "coerced-sterilization-indigenous" in topics("coerced sterilization of Indigenous women without consent")
    assert "coerced-sterilization-indigenous" in topics("the eugenics board authorized the procedure")


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

def test_crisis_lines_map_per_topic():
    assert flags.detect([row("HIV/AIDS report", year=1990)])["crisis_lines"] == [flags._988]
    assert flags.detect([row("Krever tainted blood", year=1997)])["crisis_lines"] == [flags._988]
    assert flags.detect([row("Sexual Sterilization Act", year=1972)])["crisis_lines"] == [flags._HOPE]
    assert flags.detect([row("Indian residential schools", year=2004)])["crisis_lines"] == [flags._IRS, flags._HOPE]


def test_multi_topic_dedupes_crisis_lines():
    ev = [row("Indian residential school health"), row("coerced sterilization of Indigenous women")]
    d = flags.detect(ev)
    assert set(d["topics"]) == {"residential-school-health", "coerced-sterilization-indigenous"}
    lines = d["crisis_lines"]
    assert lines.count(flags._HOPE) == 1               # HOPE maps to both topics, deduped
    assert flags._IRS in lines


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
