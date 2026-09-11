"""Phase 13 section classifier tests. Deterministic rules on synthetic page text;
the ingest command on a fixture db."""
from __future__ import annotations

import sqlite3

import pytest

from archive_debugger.ingest import db, sections

N = 100  # leaves in the synthetic item: front zone = leaves 0-5, back zone = leaves 95-99

TOC = "CONTENTS\nIntroduction ........ 1\nHistory of the programme ........ 7\nFindings ........ 15\nRecommendations ........ 40\nAppendix A ........ 55\n"
TRANSMITTAL = ("To His Honour the Lieutenant Governor.\nMay it please Your Honour: I have the honour to submit the "
               "annual report of the Department of Health for the year ending March 31.\nRespectfully submitted,\nMinister of Health")
REFERENCES = ("References\n1. Smith J. Tuberculosis control in Alberta. Can J Public Health 1972; 63(4): 301-309.\n"
              "2. Jones A. Sanatorium admissions. Can Med Assoc J 1968; 99: 1123-1130.\n"
              "3. Brown K. Chest clinic follow-up. Am Rev Respir Dis 1970; 101: 45-52.\n"
              "4. Department of National Health and Welfare. Annual report 1975. Ottawa.\n")
INDEX = "INDEX\n" + "\n".join(f"{w}, {i * 3 + 2}, {i * 7 + 11}" for i, w in enumerate(
    ["Alberta", "Beds", "Clinics", "Diphtheria", "Epidemics", "Funding", "Grants", "Hospitals", "Immunization"]))
BODY = ("The programme expanded in 1968 when the province opened three chest clinics. Admissions to the "
        "sanatorium declined steadily as outpatient chemotherapy replaced institutional care, and by the end of "
        "the decade the Board reported that the average length of stay had fallen below six months. " * 3)


def test_front_zone_rules():
    assert sections.classify(0, N, BODY) == ("front", "cover")
    assert sections.classify(3, N, TRANSMITTAL) == ("front", "transmittal")
    assert sections.classify(4, N, TOC) == ("front", "contents")
    assert sections.classify(5, N, "DEPARTMENT OF HEALTH\nANNUAL REPORT\n1972") == ("front", "title_page")
    assert sections.classify(5, N, BODY) == ("body", "default")          # body text in the front zone stays body


def test_back_rules_anywhere_and_in_zone():
    assert sections.classify(50, N, REFERENCES) == ("back", "references_heading")   # per-chapter references count
    no_head = REFERENCES.split("\n", 1)[1]
    assert sections.classify(50, N, no_head) == ("back", "reference_list")        # journal citations without heading
    assert sections.classify(98, N, INDEX) == ("back", "index")
    numbered = "\n".join(f"{i}. Appendix table {i}" for i in range(1, 7))
    assert sections.classify(98, N, numbered) == ("back", "back_zone_list")
    assert sections.classify(50, N, numbered) == ("body", "default")              # weak list mid-item is body


def test_title_page_outside_front_zone_is_body():
    assert sections.classify(60, N, "PART TWO\nFINDINGS") == ("body", "default")


def _fixture(tmp_path):
    civ = tmp_path / "civic.db"
    conn = db.init_db(str(civ))
    conn.execute("INSERT INTO items (item_id, title) VALUES ('it', 'Annual report')")
    texts = {0: "ANNUAL REPORT", 1: TOC, 2: BODY, 3: BODY, 4: REFERENCES, 5: BODY, 6: INDEX}
    for leaf in range(8):                      # leaf 7: no text -> stays NULL
        conn.execute("INSERT INTO pages (page_id, item_id, leaf_index, has_text) VALUES (?,?,?,?)",
                     (f"it#{leaf}", "it", leaf, int(leaf in texts)))
        if leaf in texts:
            conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, text) VALUES (?,?,?,?,0,?)",
                         (f"it#{leaf}:0", "it", f"it#{leaf}", leaf, texts[leaf]))
    conn.commit()
    conn.close()
    return civ


def test_classify_db_writes_columns_and_report(tmp_path):
    civ = _fixture(tmp_path)
    conn = db.init_db(str(civ))
    result = sections.classify_db(conn, sample=20, seed=13, batch=3, progress=lambda _m: None)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"      # prior mode restored
    got = dict(conn.execute("SELECT leaf_index, section_class FROM pages ORDER BY leaf_index"))
    conn.close()
    assert got == {0: "front", 1: "front", 2: "body", 3: "body", 4: "back", 5: "body", 6: "back", 7: None}
    assert result["pages_classified"] == 7 and result["pages_no_text_in_walk"] == 1
    assert result["pages_unclassified_null"] == 1 and result["pages_walked"] == 8
    assert result["timing"]["pages_per_s"] > 0
    assert result["counts"] == {"front": 2, "body": 3, "back": 2}
    assert result["passages_by_class"] == {"back": 2, "body": 3, "front": 2}
    assert len(result["samples"]["back"]) == 2 and result["samples"]["back"][0]["excerpt"]
    sections.write_report(result, tmp_path / "out")
    md = (tmp_path / "out" / "sections_report.md").read_text(encoding="utf-8")
    assert "## Sample: front" in md and "[references_heading]" in md


def test_limit_walks_a_prefix_and_projects(tmp_path):
    civ = _fixture(tmp_path)
    conn = db.init_db(str(civ))
    result = sections.classify_db(conn, limit=3, progress=lambda _m: None)
    assert result["pages_walked"] == 3 and result["pages_total"] == 8
    assert result["timing"]["projected_total_s"] is not None
    assert conn.execute("SELECT COUNT(section_class) FROM pages").fetchone()[0] == 3
    conn.close()


def test_busy_db_aborts_before_writing(tmp_path):
    civ = _fixture(tmp_path)
    holder = sqlite3.connect(str(civ), isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")                       # another writer holds the db
    conn = sqlite3.connect(str(civ), timeout=0.2)
    try:
        with pytest.raises(sections.DatabaseBusy):
            sections.classify_db(conn, progress=lambda _m: None)
    finally:
        conn.close()
        holder.execute("ROLLBACK")
        holder.close()
