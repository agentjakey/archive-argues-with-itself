"""The date reader: fixed rules, latest year within a rule, nothing outside the document."""
from __future__ import annotations

from archive_debugger import dates


def test_copyright_beats_every_other_rule():
    d = dates.read_date("Annual report", [(0, "Annual report 1984-85. March 1985."), (1, "(c) Minister of Supply 1986")])
    assert (d.year, d.method, d.confidence) == (1986, "copyright", "high")


def test_the_copyright_sign_and_accents_are_folded():
    d = dates.read_date("Rapport", [(0, "Publi" + chr(233) + " en 1990"), (1, chr(169) + " 1991")])
    assert d.year == 1991 and d.method == "copyright"


def test_fiscal_years_close_on_their_second_year():
    assert dates.read_date("x", [(0, "Report for 1986-87")]).year == 1987
    assert dates.read_date("x", [(0, "Report for 1999-00")]).year == 2000
    assert dates.read_date("x", [(0, "for the year ended March 31, 1994")]).year == 1994


def test_month_lines_title_and_mode():
    assert dates.read_date("x", [(0, "Ottawa, mars 1978")]).method == "dated_line"
    assert dates.read_date("Census 1971 results", [(0, "no years here")]).method == "title"
    d = dates.read_date("x", [(0, "in 1950 and 1960 and 1960")])
    assert (d.year, d.method) == (1960, "year_mode")


def test_implausible_years_and_empty_pages_give_nothing():
    assert dates.read_date("x", [(0, "code 3021 and 1200")]) is None
    assert dates.read_date("", []) is None


def test_only_the_first_pages_are_read():
    pages = [(i, "") for i in range(dates.FIRST_LEAVES)] + [(dates.FIRST_LEAVES, "(c) 1999")]
    assert dates.read_date("x", pages) is None
