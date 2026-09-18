"""Scope-local microlog jurisdiction remap: the resolver maps known issuers correctly,
precision-first, and sends ambiguous ones to unknown. Hermetic: uses the real rule files
and a temp civic.db; touches no scope databases."""
from __future__ import annotations

from pathlib import Path

import pytest

from archive_debugger.ingest import db
from archive_debugger.ingest.microlog_jurisdiction import (
    MICROLOG_RULES,
    SHARED_RULES,
    apply_resolver,
    load_rules,
    resolve,
)


@pytest.fixture(scope="module")
def rules():
    return load_rules([SHARED_RULES, MICROLOG_RULES])


@pytest.mark.parametrize("creator,expected", [
    ("British Columbia. Ministry of Health", "british_columbia"),
    ("BC Stats", "british_columbia"),
    ("Communications Services Dept. of WorkSafeBC", "british_columbia"),
    ("Manitoba Health", "manitoba"),
    ("Manitoba. Manitoba Health", "manitoba"),
    ("Saskatchewan Health", "saskatchewan"),
    ("Saskatchewan. Ministry of Health", "saskatchewan"),
    ("Prince Albert Parkland Regional Health Authority (Sask.)", "saskatchewan"),
    ("Nova Scotia. Dept. of Health", "nova_scotia"),
    ("Yukon Health and Social Services", "yukon"),
    ("Government of Prince Edward Island", "prince_edward_island"),
    ("Northwest Territories Bureau of Statistics", "northwest_territories"),
    ("Workplace Health, Safety and Compensation Commission of New Brunswick", "new_brunswick"),
    ("Ministere de la Sante et des Services sociaux, Quebec", "quebec"),
    ("Mississauga Halton Local Health Integration Network (Ont.)", "ontario"),
    ("Natural Resources Canada, Canadian Forest Service", "federal"),
    ("Canadian Institutes of Health Research", "federal"),
    ("Pest Management Regulatory Agency", "federal"),
    ("Patented Medicine Prices Review Board", "federal"),
])
def test_known_issuers_resolve(rules, creator, expected):
    text_rules, coll_rules = rules
    jur, method, pattern = resolve(creator, "", [], text_rules, coll_rules)
    assert jur == expected, f"{creator!r} -> {jur} (pattern {pattern!r}), expected {expected}"
    assert method in ("creator", "publisher", "collection")


def test_accent_insensitive(rules):
    # An accented Quebec issuer must resolve even though the rule pattern is ASCII. Build the
    # accented string from code points so this source file stays ASCII-only.
    e = chr(0xe9)  # e-acute
    text_rules, coll_rules = rules
    jur, _, _ = resolve(f"Qu{e}bec, Sant{e} et Services sociaux", "", [], text_rules, coll_rules)
    assert jur == "quebec"


@pytest.mark.parametrize("creator,publisher", [
    ("Ministry of Health", ""),               # bare, deliberately not mapped -> unknown
    ("Department of Health", ""),
    ("Ministry of Health Services", ""),      # BC-ish but no province named -> unknown (precision)
    ("The Region", ""),
    ("The Hospital", ""),
    ("", ""),
    ("Pharmacare", ""),
    ("Social Planning Council of Winnipeg", ""),   # a city, not a named province -> unknown (cities dropped)
    ("City of Saskatoon", ""),                     # a city, not a named province -> unknown
])
def test_ambiguous_or_unmatched_go_unknown(rules, creator, publisher):
    text_rules, coll_rules = rules
    jur, _, _ = resolve(creator, publisher, [], text_rules, coll_rules)
    assert jur == "unknown"


def test_creator_publisher_conflict_is_unknown(rules):
    text_rules, coll_rules = rules
    # Saskatchewan (creator) vs Alberta (publisher, from the shared rules) -> conflict -> unknown.
    jur, method, _ = resolve("Saskatchewan Health", "Government of Alberta", [], text_rules, coll_rules)
    assert jur == "unknown" and method == "conflict"


def test_province_plus_canada_is_ambiguous(rules):
    text_rules, coll_rules = rules
    # A field naming both a province and Canada is ambiguous -> unknown (precision-first):
    # it may be a federal body named for its provincial region.
    for issuer in (
        "Forestry Canada, Newfoundland and Labrador Region",
        "Canada. Medical Services Branch. Northwest Territories Region.",
        "Canada-Nova Scotia Offshore Petroleum Board",
        "British Columbia, Canada",
    ):
        jur, _, _ = resolve(issuer, "", [], text_rules, coll_rules)
        assert jur == "unknown", f"{issuer!r} should be ambiguous -> unknown, got {jur}"


def test_cataloguer_tag_is_authoritative_over_canada(rules):
    text_rules, coll_rules = rules
    # A deliberate "(prov.)" jurisdiction tag is trusted even when the field also says Canada.
    jur, _, _ = resolve("Some Health Authority (Sask.), funded by Canada", "", [], text_rules, coll_rules)
    assert jur == "saskatchewan"


def test_canada_catchall_resolves_federal(rules):
    text_rules, coll_rules = rules
    jur, _, pattern = resolve("Correctional Service Canada", "", [], text_rules, coll_rules)
    assert jur == "federal" and pattern == "canada"


def test_canada_vs_province_across_fields_is_conflict(rules):
    text_rules, coll_rules = rules
    jur, method, _ = resolve("Widgets of Canada", "Manitoba Health", [], text_rules, coll_rules)
    assert jur == "unknown" and method == "conflict"


def _seed(conn, rows):
    for item_id, creator in rows:
        conn.execute(
            "INSERT INTO items (item_id, creator_raw, publisher_raw, jurisdiction_norm, jurisdiction_method) "
            "VALUES (?,?,?,'unknown','unknown')", (item_id, creator, ""))
    conn.commit()


def test_apply_resolver_updates_only_matches(tmp_path, rules):
    text_rules, coll_rules = rules
    conn = db.init_db(str(tmp_path / "civic.db"))
    try:
        _seed(conn, [
            ("a", "Manitoba Health"),
            ("b", "Saskatchewan Health"),
            ("c", "Pest Management Regulatory Agency"),
            ("d", "Ministry of Health"),          # ambiguous -> stays unknown
            ("e", "British Columbia. Office of the Provincial Health Officer"),
        ])
        report = apply_resolver(conn, text_rules, coll_rules, dry_run=False)
        got = dict(conn.execute("SELECT item_id, jurisdiction_norm FROM items").fetchall())
        methods = dict(conn.execute("SELECT item_id, jurisdiction_method FROM items").fetchall())
        assert got == {"a": "manitoba", "b": "saskatchewan", "c": "federal",
                       "d": "unknown", "e": "british_columbia"}
        assert methods["a"].startswith("microlog_map:") and methods["d"] == "unknown"
        assert report["resolved"] == 4
        assert report["baseline_unknown"] == 5 and report["after_unknown"] == 1

        # Idempotent: a second run reverts then re-resolves to the same state.
        report2 = apply_resolver(conn, text_rules, coll_rules, dry_run=False)
        assert report2["baseline_unknown"] == 5 and report2["after_unknown"] == 1
    finally:
        conn.close()
