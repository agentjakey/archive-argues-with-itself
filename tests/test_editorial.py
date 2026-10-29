"""Curated comparisons and editorial notes: every story carries a comparability note, and no
caption, question or label claims more than that note supports. Runs over the real config files
and over small synthetic cases for the rules themselves."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from archive_debugger import editorial

REPO = Path(__file__).resolve().parents[1]
STORY_FILES = {"pilot": REPO / "config" / "stories.json", "microlog": REPO / "config" / "stories.microlog.json"}
NOTES = editorial.load_notes(REPO / "config" / "editorial_notes.json")
RETIRED = editorial.load_retired(REPO / "config" / "retired_stories.json")


@pytest.mark.parametrize("scope", sorted(STORY_FILES))
def test_every_story_has_a_comparability_note_and_no_overclaim(scope):
    stories = editorial.load_stories(STORY_FILES[scope])
    assert stories, f"{scope} has no stories"
    for s in stories:
        assert s["comparability"]["outcome"] in editorial.COMPARISON_OUTCOMES
        assert s["comparability"]["note"].strip()
    assert editorial.find_story_problems(stories, NOTES, scope) == []


@pytest.mark.parametrize("scope", sorted(STORY_FILES))
def test_hero_and_attract_never_carry_an_incompatible_pair(scope):
    stories = editorial.load_stories(STORY_FILES[scope])
    heroes = [s for s in stories if "hero" in s["surfaces"]]
    assert len(heroes) == 1, f"{scope} needs exactly one hero story"
    for s in stories:
        if {"hero", "attract"} & set(s["surfaces"]):
            assert s["comparability"]["outcome"] != "incompatible", s["id"]


def test_retired_stories_are_off_every_surface_and_noted():
    live = {(scope, s["id"]) for scope, path in STORY_FILES.items() for s in editorial.load_stories(path)}
    assert {s["id"] for s in RETIRED} == {"federal-aging-1995-2000", "microlog-immunization-1984-2016"}
    for s in RETIRED:
        assert (s["scope"], s["id"]) not in live
        assert editorial.notes_for_story(NOTES, s["scope"], s["id"]), f"{s['id']} retired without a dated note"


def test_every_note_targets_something_that_exists():
    stories = {(scope, s["id"]): s for scope, path in STORY_FILES.items() for s in editorial.load_stories(path)}
    stories.update({(s["scope"], s["id"]): s for s in RETIRED})
    asked = {(scope, editorial.asked_question(s)) for (scope, _), s in stories.items()}
    for n in NOTES["notes"]:
        t = n["target"]
        if t["kind"] == "story":
            assert (t["scope"], t["story_id"]) in stories, n["id"]
        else:
            assert (t["scope"], t["question"]) in asked, n["id"]


def test_alberta_answer_note_names_both_pages():
    notes = editorial.notes_for_answer(
        NOTES, "pilot", "How did Alberta health insurance coverage change between the 1970s and 1990s?", cached=True)
    assert len(notes) == 1
    text = notes[0]["text"]
    assert "page 116" in text and "page 117" in text
    assert "unedited" in text
    assert editorial.notes_for_answer(
        NOTES, "pilot", "How did Alberta health insurance coverage change between the 1970s and 1990s?", cached=False) == []


def test_config_text_is_ascii():
    for path in [*STORY_FILES.values(), REPO / "config" / "editorial_notes.json", REPO / "config" / "retired_stories.json"]:
        path.read_text(encoding="utf-8").encode("ascii")


# --- the rules themselves -------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Two pages, twenty-five years apart, from the same insurance plan.",
    "A provincial watch, then a national one.",
    "Writing the schedule, then chasing what slipped past it.",
    "The wording shifted between the two reports.",
    "Coverage changed between 1974 and 1999.",
    "What changed",
])
def test_overclaims_caught_on_a_pair_that_is_not_comparable(text):
    assert editorial.overclaims(text, "related_different")
    assert editorial.overclaims(text, "incompatible")


@pytest.mark.parametrize("text", [
    "They describe different things and cannot, on their own, show how coverage changed.",
    "Two provinces' registries, each in its own report; not one registry over time.",
])
def test_negated_or_neutral_wording_passes(text):
    assert editorial.overclaims(text, "incompatible") == []


def test_disagreement_language_needs_a_comparable_disagreeing_pair():
    assert editorial.overclaims("The record disagrees with itself.", "comparable_agreeing")
    assert editorial.overclaims("The record disagrees with itself.", "comparable_disagreeing") == []
    assert editorial.overclaims("Background, then decision.", "comparable_agreeing") == []


def test_change_question_needs_a_comparable_pair():
    s = {"id": "x", "question": "How did coverage change between the 1970s and 1990s?", "caption": "",
         "comparability": {"outcome": "related_different", "differs_on": ["measure"], "note": "Different measures."},
         "surfaces": ["gallery"], "pins": ["a#0:0", "b#0:0"]}
    assert any("presupposes a change" in p for p in editorial.find_story_problems([s], {"notes": []}, "pilot"))


def test_replaced_question_needs_dated_notes_on_story_and_answer():
    s = {"id": "x", "question": "What do two records say?", "answer_question": "Old wording?", "caption": "",
         "comparability": {"outcome": "incompatible", "differs_on": ["measure"], "note": "Different measures."},
         "surfaces": ["gallery"], "pins": ["a#0:0", "b#0:0"]}
    problems = editorial.find_story_problems([s], {"notes": []}, "pilot")
    assert len(problems) == 2


def test_structural_validation(tmp_path):
    base = {"id": "x", "question": "q", "pins": ["a#0:0", "b#0:0"], "caption": "",
            "comparability": {"outcome": "incompatible", "differs_on": [], "note": "n"}, "surfaces": ["gallery"]}
    with pytest.raises(editorial.StoryError, match="differs on"):
        editorial.validate_story(base)
    with pytest.raises(editorial.StoryError, match="comparability block"):
        editorial.validate_story({k: v for k, v in base.items() if k != "comparability"})
    two_heroes = [dict(base, id=i, comparability={"outcome": "comparable_agreeing", "differs_on": [], "note": "n"},
                       surfaces=["hero"]) for i in ("a", "b")]
    path = tmp_path / "s.json"
    path.write_text(json.dumps(two_heroes), encoding="utf-8")
    with pytest.raises(editorial.StoryError, match="hero"):
        editorial.load_stories(path)
    bad_notes = tmp_path / "n.json"
    bad_notes.write_text(json.dumps({"version": 1, "notes": [{"id": "n", "target": {"kind": "story", "scope": "pilot"},
                                                                "date": "2026-10-29", "text": "t", "reason": "r"}]}),
                         encoding="utf-8")
    with pytest.raises(editorial.StoryError, match="story_id"):
        editorial.load_notes(bad_notes)
