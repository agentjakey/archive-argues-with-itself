"""Phase 11 coverage view tests. Hermetic: temp civic.db with FTS via the schema triggers."""
from __future__ import annotations

import sqlite3

from archive_debugger.api.coverage import FIXED_LANES, coverage, fts_expression
from archive_debugger.ingest import db
from archive_debugger.retrieve.filters import Filters


def _corpus(tmp_path):
    civ = tmp_path / "civic.db"
    conn = db.init_db(str(civ))
    rows = [  # item, year, jurisdiction, texts per leaf
        ("a", 1985, "alberta", ["vaccination programme for children", "hospital admissions rose"]),
        ("b", 1990, "ontario", ["vaccination clinic hours", "sanatorium beds were closed"]),
        ("c", None, "federal", ["undated vaccination pamphlet", "hospital funding"]),
    ]
    for item, year, jur, texts in rows:
        dated = 0 if year is None else 1
        conn.execute("INSERT INTO items (item_id, title, dated, year, decade, jurisdiction_norm, doc_type_norm) VALUES (?,?,?,?,?,?,?)",
                     (item, item, dated, year, None if year is None else f"{(year // 10) * 10}s", jur, "other"))
        for leaf, text in enumerate(texts):
            conn.execute("INSERT INTO pages (page_id, item_id, leaf_index, has_text) VALUES (?,?,?,1)", (f"{item}#{leaf}", item, leaf))
            conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, text, ocr_quality) VALUES (?,?,?,?,?,'0.9')",
                         (f"{item}#{leaf}:0", item, f"{item}#{leaf}", leaf, text))
    conn.commit()
    conn.close()
    ro = sqlite3.connect(f"file:{civ}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    return ro


def _lane(cov, decade):
    return next(r for r in cov["by_decade"] if r["decade"] == decade)


def test_fts_expressions_mirror_the_rule():
    assert fts_expression("sanatoria") == '"sanat"*'
    assert fts_expression("risks") == '"risk" OR "risks"'
    assert fts_expression("2020") == '"2020"'
    assert fts_expression("1980s").startswith('"1980" OR "1981"') and fts_expression("1980s").endswith('"1980s"')


def test_out_of_window_decades_fold_into_edge_lanes(tmp_path):
    conn = _corpus(tmp_path)
    conn.close()
    civ = tmp_path / "civic.db"
    rw = sqlite3.connect(str(civ))
    for item, year in (("old", 1923), ("older", 1888), ("new", 2014)):
        rw.execute("INSERT INTO items (item_id, title, dated, year, decade, jurisdiction_norm, doc_type_norm) VALUES (?,?,1,?,?,?,?)",
                   (item, item, year, f"{(year // 10) * 10}s", "federal", "other"))
        rw.execute("INSERT INTO pages (page_id, item_id, leaf_index, has_text) VALUES (?,?,0,1)", (f"{item}#0", item))
        rw.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, text, ocr_quality) VALUES (?,?,?,0,'vaccination notice','0.9')",
                   (f"{item}#0:0", item, f"{item}#0"))
    rw.commit()
    rw.close()
    ro = sqlite3.connect(f"file:{civ}?mode=ro", uri=True)
    cov = coverage(ro, "vaccination", Filters())
    assert [r["decade"] for r in cov["by_decade"]] == ["pre-1960", *FIXED_LANES[:-1], "post-2009", "undated"]
    assert _lane(cov, "pre-1960")["passages"] == 2 and _lane(cov, "pre-1960")["items"] == 2
    assert _lane(cov, "pre-1960")["terms"]["vaccination"] == 2 and _lane(cov, "post-2009")["terms"]["vaccination"] == 1
    ro.close()


def test_term_counts_by_decade_and_jurisdiction(tmp_path):
    conn = _corpus(tmp_path)
    cov = coverage(conn, "vaccination hospital", Filters())
    assert cov["salient_terms"] == ["vaccination", "hospital"]
    assert [r["decade"] for r in cov["by_decade"]] == FIXED_LANES               # fixed lanes, undated last
    assert _lane(cov, "1980s")["terms"] == {"vaccination": 1, "hospital": 1}
    assert _lane(cov, "1990s")["terms"] == {"vaccination": 1, "hospital": 0}
    assert _lane(cov, "undated")["terms"] == {"vaccination": 1, "hospital": 1}
    assert _lane(cov, "1980s")["passages"] == 2 and _lane(cov, "1980s")["items"] == 1
    assert _lane(cov, "undated")["undated_passages"] == 2
    assert _lane(cov, "1990s")["matched"] == 1                                  # any-term match
    jur = {r["jurisdiction"]: r for r in cov["by_jurisdiction"]}
    assert jur["ontario"]["terms"] == {"vaccination": 1, "hospital": 0} and jur["ontario"]["passages"] == 2
    conn.close()


def test_absent_term_is_zero_in_every_decade(tmp_path):
    conn = _corpus(tmp_path)
    cov = coverage(conn, "covid vaccination", Filters())
    assert all(r["terms"]["covid"] == 0 for r in cov["by_decade"])
    assert all(r["terms"]["covid"] == 0 for r in cov["by_jurisdiction"])
    conn.close()


def test_prefix_rule_counts_sanatorium_for_sanatoria(tmp_path):
    conn = _corpus(tmp_path)
    cov = coverage(conn, "sanatoria beds", Filters())
    assert _lane(cov, "1990s")["terms"]["sanatoria"] == 1
    conn.close()


def test_filters_restrict_the_baseline(tmp_path):
    conn = _corpus(tmp_path)
    cov = coverage(conn, "vaccination", Filters(jurisdiction="alberta"))
    assert sum(r["passages"] for r in cov["by_decade"]) == 2                    # only item a
    assert _lane(cov, "1990s")["passages"] == 0 and _lane(cov, "1990s")["terms"]["vaccination"] == 0
    assert [r["jurisdiction"] for r in cov["by_jurisdiction"]] == ["alberta"]
    conn.close()
