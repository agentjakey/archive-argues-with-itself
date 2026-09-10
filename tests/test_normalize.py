"""Phase 5 normalization tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from archive_debugger.ingest import db, normalize

CONFIG_DIR = Path(__file__).parent.parent / "config"


@pytest.fixture(scope="module")
def rules():
    tr, cr = normalize.load_jurisdiction_rules(CONFIG_DIR / "jurisdiction_rules.csv")
    al = normalize.load_issuer_aliases(CONFIG_DIR / "issuer_aliases.csv")
    dt = normalize.load_doctype_rules(CONFIG_DIR / "doctype_rules.csv")
    return tr, cr, al, dt


# ---- date -----------------------------------------------------------------


def test_date_iso_datetime_exact():
    d = normalize.parse_date("1986-01-01T00:00:00Z")
    assert (d["year"], d["dated"], d["date_method"], d["decade"]) == (1986, 1, "exact", "1980s")


def test_date_plain_year_and_full_date():
    assert normalize.parse_date("1975")["year"] == 1975
    assert normalize.parse_date("1975-06-30")["year"] == 1975


def test_date_range_takes_earliest():
    d = normalize.parse_date("1998-1999")
    assert d["year"] == 1998 and d["date_method"] == "range"


def test_date_partial_is_undated():
    d = normalize.parse_date("197-")
    assert d["dated"] == 0 and d["date_method"] == "partial" and d["year"] is None


def test_date_year_zero_and_out_of_range_undated():
    assert normalize.parse_date("0000-01-01T00:00:00Z")["dated"] == 0
    assert normalize.parse_date("1700")["dated"] == 0
    assert normalize.parse_date("2100")["dated"] == 0


def test_date_none_is_unknown():
    d = normalize.parse_date(None)
    assert d["dated"] == 0 and d["date_method"] == "unknown"


# ---- title recovery -------------------------------------------------------


def test_title_recovery_explicit_year():
    assert normalize.recover_title_year("Annual report 1997") == 1997


def test_title_recovery_year_ending():
    assert normalize.recover_title_year("Report for the year ending March 31, 1999") == 1999


def test_title_recovery_fiscal():
    assert normalize.recover_title_year("Annual report 1998-99") == 1998


def test_title_recovery_multiple_years_refuses():
    assert normalize.recover_title_year("Comparison of 1995 and 1997 data") is None


def test_title_recovery_no_year():
    assert normalize.recover_title_year("Public health in the province") is None


# ---- jurisdiction ---------------------------------------------------------


def test_jurisdiction_federal_from_creator(rules):
    tr, cr, *_ = rules
    j, m = normalize.classify_jurisdiction("CANADA. DEPT. OF NATIONAL HEALTH AND WELFARE", "", [], "", tr, cr)
    assert (j, m) == ("federal", "creator")


def test_jurisdiction_ontario_from_publisher(rules):
    tr, cr, *_ = rules
    j, m = normalize.classify_jurisdiction("", "Toronto : Queen's Printer for Ontario", [], "", tr, cr)
    assert (j, m) == ("ontario", "publisher")


def test_jurisdiction_collection_fallback(rules):
    tr, cr, *_ = rules
    j, m = normalize.classify_jurisdiction("", "", ["governmentpublications", "albertagovernmentpublications"], "", tr, cr)
    assert (j, m) == ("alberta", "collection")


def test_jurisdiction_international_who(rules):
    tr, cr, *_ = rules
    j, _ = normalize.classify_jurisdiction("World Health Organization", "", [], "", tr, cr)
    assert j == "international"


def test_jurisdiction_conflict_is_unknown(rules):
    tr, cr, *_ = rules
    j, m = normalize.classify_jurisdiction("Government of Alberta", "Queen's Printer for Ontario", [], "", tr, cr)
    assert (j, m) == ("unknown", "unknown")


def test_jurisdiction_absent_is_unknown(rules):
    tr, cr, *_ = rules
    assert normalize.classify_jurisdiction("McMaster University", "", [], "", tr, cr) == ("unknown", "unknown")


def test_jurisdiction_department_name_beats_city(rules):
    tr, cr, *_ = rules
    j, _ = normalize.classify_jurisdiction("", "[Ottawa] : Health Canada", [], "", tr, cr)
    assert j == "federal"


def test_jurisdiction_alberta_legislative_assembly(rules):
    tr, cr, *_ = rules
    assert normalize.classify_jurisdiction("Alberta. Legislative Assembly", "", [], "", tr, cr) == ("alberta", "creator")


def test_jurisdiction_bare_ministry_of_health_is_unknown(rules):
    tr, cr, *_ = rules
    assert normalize.classify_jurisdiction("Ministry of Health", "", [], "", tr, cr) == ("unknown", "unknown")


def test_jurisdiction_ontario_backstop_still_fires(rules):
    tr, cr, *_ = rules
    assert normalize.classify_jurisdiction("Ontario. Ministry of Health", "", [], "", tr, cr)[0] == "ontario"


# ---- issuer ---------------------------------------------------------------


def test_issuer_alias_collapses_era_names(rules):
    *_, al, _ = rules
    a, m, _ = normalize.normalize_issuer("Canada. Department of National Health and Welfare", "", al)
    b, _, _ = normalize.normalize_issuer("", "Ottawa : Health and Welfare Canada", al)
    assert m == "alias" and a == b == "Health Canada (federal health portfolio)"


def test_issuer_semicolon_split_first_body(rules):
    *_, al, _ = rules
    a, _, _ = normalize.normalize_issuer(
        "Alberta. Alberta Health; Alberta. Alberta Health and Wellness", "", al)
    assert a == "Alberta Health"


def test_issuer_allcaps_cleaned(rules):
    *_, al, _ = rules
    a, m, key = normalize.normalize_issuer("ONTARIO COUNCIL OF HEALTH", "", al)
    assert a == "Ontario Council of Health"  # mapped


def test_issuer_bracket_place_prefix_stripped(rules):
    *_, al, _ = rules
    a, m, _ = normalize.normalize_issuer("", "[Ottawa] : Health Canada", al)
    assert a == "Health Canada (federal health portfolio)"


def test_issuer_anaphora_resolves_to_creator(rules):
    *_, al, _ = rules
    a, m, _ = normalize.normalize_issuer("Ontario. Ministry of Health", "[Toronto] : The Dept.", al)
    assert a == "Ontario Ministry of Health"


def test_issuer_anaphora_without_creator_is_unknown(rules):
    *_, al, _ = rules
    a, m, _ = normalize.normalize_issuer("", "[Toronto] : The Dept.", al)
    assert (a, m) == ("unknown", "unknown")


def test_issuer_unmapped_keeps_cleaned_raw(rules):
    *_, al, _ = rules
    a, m, key = normalize.normalize_issuer("Some Obscure Local Board of Widgets", "", al)
    assert m == "unmapped" and a == "Some Obscure Local Board of Widgets" and key == a


def test_issuer_bare_ministry_of_health_is_unmapped(rules):
    *_, al, _ = rules
    assert normalize.normalize_issuer("Ministry of Health", "", al) == ("Ministry of Health", "unmapped", "Ministry of Health")


# ---- doc type -------------------------------------------------------------


def test_doctype_royal_commission_beats_commission(rules):
    *_, dt = rules
    assert normalize.classify_doctype("Royal Commission on Health Services", "", dt)[0] == "royal_commission"


def test_doctype_standing_committee(rules):
    *_, dt = rules
    assert normalize.classify_doctype("Standing Committee on Health report", "", dt)[0] == "standing_committee"


def test_doctype_annual_report(rules):
    *_, dt = rules
    assert normalize.classify_doctype("Annual report 1990", "", dt)[0] == "annual_report"


def test_doctype_statistical(rules):
    *_, dt = rules
    assert normalize.classify_doctype("Vital statistics review", "", dt)[0] == "statistical_report"


def test_doctype_board_or_appeal(rules):
    *_, dt = rules
    assert normalize.classify_doctype("Public Health Appeal Board decision", "", dt)[0] == "board_or_appeal"


def test_doctype_other_when_present_but_uncategorized(rules):
    *_, dt = rules
    assert normalize.classify_doctype("A general policy paper", "", dt) == ("other", "default")


def test_doctype_unknown_when_no_text(rules):
    *_, dt = rules
    assert normalize.classify_doctype("", "", dt) == ("unknown", "unknown")


# ---- no-imputation guard + end-to-end -------------------------------------


def test_no_imputation_undated_stays_undated():
    conn = db.init_db(":memory:")
    conn.execute("INSERT INTO items (item_id, title, date_raw) VALUES ('u', 'Public health study', NULL)")
    conn.commit()
    normalize.normalize_items(conn, CONFIG_DIR)
    row = conn.execute("SELECT year, dated, date_method FROM items WHERE item_id='u'").fetchone()
    assert row["year"] is None and row["dated"] == 0
    conn.close()


def test_end_to_end_coverage_periods():
    conn = db.init_db(":memory:")
    conn.executemany(
        "INSERT INTO items (item_id, title, creator_raw, date_raw) VALUES (?,?,?,?)",
        [
            ("a", "Annual report", "Ontario. Ministry of Health", "1955-01-01T00:00:00Z"),
            ("b", "Annual report", "Government of Alberta", "1985-01-01T00:00:00Z"),
            ("c", "Annual report", "Canada. Health Canada", "2015-01-01T00:00:00Z"),
            ("d", "Report for the year ending 1990", "Canada. Health Canada", None),
            ("e", "Undated study", "McMaster University", None),
        ],
    )
    conn.commit()
    stats = normalize.normalize_items(conn, CONFIG_DIR)
    cells = normalize.compute_coverage(conn)
    periods = {r["period"] for r in conn.execute("SELECT period FROM coverage_cells")}
    assert {"pre-1960", "1980s", "post-2009", "undated"} <= periods
    assert stats["recovered_items"] == 1  # item d recovered from title
    assert conn.execute("SELECT dated FROM items WHERE item_id='e'").fetchone()["dated"] == 0
    conn.close()
