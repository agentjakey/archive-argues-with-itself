"""The second benchmark generator's gates, fixtures and prompt (audit/generator_extra.py)."""
from __future__ import annotations

import json

import pytest

from archive_debugger.audit import generator_extra as gx
from archive_debugger.audit import prompts


def page(item="A", year=1985, jur="ontario", text="In 1985 there were 1,204 beds in 31 hospitals."):
    return {"passage_id": f"{item}#1:0", "item_id": item, "title": "Annual report", "year": year,
            "jurisdiction": jur, "leaf_index": 1, "deep_link": "", "text": text, "ocr_quality": 0.9}


def test_numbers_ignore_thousands_separators_and_single_digits():
    assert gx.numbers("1,204 beds in 31 hospitals, 5 wards, 1985") == {"1204", "31", "1985"}


def test_a_false_claim_whose_number_is_on_the_page_is_rejected():
    p = [page()]
    assert gx.claim_number_gate("There were 1,500 beds in 1985.", "There were 1,204 beds in 1985.", p)["passed"]
    assert not gx.claim_number_gate("There were 31 beds.", "There were 1,204 beds.", p)["passed"]


def test_a_conflict_needs_two_documents_one_place_close_years_and_different_values():
    a, b = page("A"), page("B", year=1987, text="Beds: 1,180 in 1985.")
    assert gx.conflict_gate(a, b, "1,204 beds", "1,180 in 1985")["passed"]
    assert not gx.conflict_gate(a, page("A"), "1,204 beds", "1,180")["passed"]                  # same document
    assert not gx.conflict_gate(a, page("B", jur="quebec"), "1,204 beds", "1,180")["passed"]    # another place
    assert not gx.conflict_gate(a, page("B", year=1990), "1,204 beds", "1,180")["passed"]       # too far apart
    assert not gx.conflict_gate(a, b, "1,204 beds", "1,204 beds")["passed"]                     # same value


def test_restricted_items_carry_a_fixture_that_names_no_real_authority():
    policy = gx.fixture_policy("c", 3, "A")
    assert policy["fixture"] is True and policy["targets"]["items"] == ["A"]
    assert policy["authority"] == gx.FIXTURE_AUTHORITY and "fixture" in policy["authority"]
    assert set(policy["restrict"]) == {"retrieve", "generate", "export"}
    item = gx.make_item("c", "restricted", 3, "What did it say?", [page()], [], "claude-sonnet-5-5",
                        [{"source": 1, "quote": "x"}], governance=[policy])
    assert item["kind"] == "benchmark2" and item["label"]["verdict"] == "RESTRICTED" and item["label"]["should_refuse"]
    message = prompts.user_message(item)
    assert "fixture-c-0003" in message and "<governance>" in message


def test_benchmark2_has_its_own_prompt_versions_and_leaves_the_others_alone():
    versions = {prompts.version_for("benchmark2"), prompts.version_for("benchmark2", "reference"),
                prompts.version_for("benchmark"), prompts.version_for("sentence"), prompts.version_for("sentence", "reference")}
    assert len(versions) == 5
    assert "RESTRICTED" in prompts.system("benchmark2") and "CONFLICTING" in prompts.system("benchmark2", "reference")


def test_drafts_parse_strictly():
    good = {"conflict": True, "question": "q?", "measure": "m", "quote_a": "a", "quote_b": "b", "why_comparable": "w"}
    assert gx.parse("ok " + json.dumps(good), "conflicting")["conflict"] is True
    with pytest.raises(ValueError):
        gx.parse(json.dumps({**good, "conflict": "yes"}), "conflicting")
