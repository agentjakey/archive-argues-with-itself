"""Invariant tests over the composition (/scopes) and corpus facts (/health): the auditability
numbers the sources view, explorer, and timeline display must be internally consistent and share
one undated basis. Hermetic and read-only: a tiny temp civic.db, no index, no network, no pilot DB.
These guard the numbers, so a future ingest or serve change that broke a sum fails here."""

from __future__ import annotations

import sqlite3

from archive_debugger.api.app import corpus_facts, scope_composition
from archive_debugger.ingest import db

PILOT_WINDOW = {"min_year": 1960, "max_year": 2009}
TEXT = "vaccination hospital programme"


def _facts_and_comp(tmp_path, items):
    """items: [(item_id, year|None, jurisdiction_norm, date_method|None, jurisdiction_method|None,
    ocr_quality)]. Two passages per item, each with the given OCR quality. Returns
    (corpus_facts, scope_composition) computed exactly as the server does."""
    civ = tmp_path / "civic.db"
    conn = db.init_db(str(civ))
    for item, year, jur, dm, jm, ocr in items:
        dated = 0 if year is None else 1
        decade = None if year is None else f"{(year // 10) * 10}s"
        conn.execute(
            "INSERT INTO items (item_id, title, dated, year, decade, date_method, jurisdiction_norm, "
            "jurisdiction_method, doc_type_norm, details_url) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (item, item, dated, year, decade, dm, jur, jm, "other", "u"))
        for leaf in (0, 1):
            conn.execute(
                "INSERT INTO pages (page_id, item_id, leaf_index, printed_page, has_text) VALUES (?,?,?,?,1)",
                (f"{item}#{leaf}", item, leaf, str(leaf + 1)))
            conn.execute(
                "INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, "
                "text, token_count, ocr_quality) VALUES (?,?,?,?,0,30,?,3,?)",
                (f"{item}#{leaf}:0", item, f"{item}#{leaf}", leaf, TEXT, ocr))
    conn.commit()
    facts = corpus_facts(conn, PILOT_WINDOW)
    comp = scope_composition(conn, facts)
    conn.close()
    return facts, comp


# item, year, jurisdiction, date_method, jurisdiction_method, ocr_quality
ITEMS = [
    ("pre",  1955, "federal",      "exact",            None,                     "0.95"),  # pre-1960, high
    ("mid",  1985, "ontario",      "exact",            None,                     "0.50"),  # 1980s, medium
    ("late", 2015, "alberta",      "title_extracted",  None,                     "0.20"),  # post-2009, low
    ("nd",   None, "federal",      None,               None,                     "0.95"),  # undated, high
    ("prox", 1990, "saskatchewan", "exact",            "microlog_map:publisher", "0.95"),  # proxy, 1990s, high
]


def test_composition_and_corpus_facts_invariants(tmp_path):
    facts, comp = _facts_and_comp(tmp_path, ITEMS)
    items = facts["items"]
    passages = facts["passages"]
    assert items == 5 and passages == 10

    # OCR buckets sum to the passage total
    assert comp["ocr"]["high"] + comp["ocr"]["medium"] + comp["ocr"]["low"] == passages
    # date-method counts sum to the item total
    assert sum(comp["date_method"].values()) == items
    # by_period sums to the item total
    assert sum(comp["by_period"].values()) == items
    # undated share is item-weighted and self-consistent on both surfaces
    assert comp["undated"]["item_share"] == round(comp["undated"]["items"] / items, 4)
    assert facts["undated_item_share"] == round(facts["items_undated"] / items, 4)
    # ONE undated count across the three surfaces (composition, timeline by_period, header facts)
    assert comp["undated"]["items"] == comp["by_period"]["undated"] == facts["items_undated"] == 1
    # ONE out-of-window count: corpus_facts equals by_period pre/post, same basis
    oow = comp["by_period"].get("pre-1960", 0) + comp["by_period"].get("post-2009", 0)
    assert oow == 2 and facts["items_out_of_window"] == oow
    # the passage-weighted figure is kept but computed on its own (passage) basis, not the headline
    # (it can coincide with the item basis when every item has the same passage count, as here)
    assert facts["undated_share"] == round(facts["passages_undated"] / passages, 4)


def test_is_floor_set_when_a_proxy_map_jurisdiction_is_present(tmp_path):
    # Unknown share is 0 (every item has a real jurisdiction), so is_floor is driven purely by the
    # proxy-map row: it must still be set wherever a proxy jurisdiction is shown.
    _, comp = _facts_and_comp(tmp_path, ITEMS)
    assert comp["jurisdiction_unknown_share"] == 0.0
    assert comp["jurisdiction_is_floor"] is True


def test_is_floor_clear_without_proxy_and_low_unknown(tmp_path):
    items = [
        ("a", 1985, "ontario", "exact", None, "0.95"),
        ("b", 1990, "federal", "exact", None, "0.95"),
    ]
    _, comp = _facts_and_comp(tmp_path, items)
    assert comp["jurisdiction_unknown_share"] == 0.0
    assert comp["jurisdiction_is_floor"] is False


def test_is_floor_set_on_high_unknown_share_without_proxy(tmp_path):
    # The other path into the floor: a high unknown share alone (no proxy map) still marks it.
    items = [
        ("a", 1985, "ontario", "exact", None, "0.95"),
        ("u", 1990, "unknown", "exact", None, "0.95"),
    ]
    _, comp = _facts_and_comp(tmp_path, items)
    assert comp["jurisdiction_unknown_share"] == 0.5
    assert comp["jurisdiction_is_floor"] is True
