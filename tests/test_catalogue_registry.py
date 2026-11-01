"""The catalogue fetch, the full-text fetch and the registry, with the network replaced. Covers resume,
the stop on repeated 429 or 503, page-by-page text, stable identifiers, dates kept apart, coverage
states, governance and the append-only audit trail."""
from __future__ import annotations

import gzip
import json
import socket
import sqlite3

import pytest

from archive_debugger.catalogue import fetch, fulltext, net
from archive_debugger.registry import build


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def scrape_pages(records, size):
    pages = []
    for i in range(0, len(records), size):
        more = i + size < len(records)
        pages.append(json.dumps({"items": records[i:i + size], "total": len(records) - i,
                                 "cursor": f"c{i + size}" if more else None}).encode())
    return pages


RECORDS = [
    {"identifier": "31761000000001", "title": "Annual report of the Workers' Compensation Board, 1978",
     "date": "1978", "publisher": "Ontario Ministry of Labour", "collection": ["governmentpublications", "toronto"],
     "language": "eng", "mediatype": "texts", "imagecount": "40"},
    {"identifier": "alberta-health-1999", "title": "Health insurance statistical supplement 1998-99",
     "date": None, "creator": "Alberta Health", "collection": "governmentpublications", "mediatype": "texts"},
    {"identifier": "undated-pamphlet", "title": "A pamphlet", "collection": ["governmentpublications"], "mediatype": "texts"},
]


def test_catalogue_fetch_resumes_and_checks_its_pages(tmp_path):
    pages = scrape_pages(RECORDS, 2)
    calls = []

    def get(url, params):
        calls.append(params.get("cursor"))
        return pages[len(calls) - 1]
    index = fetch.fetch_catalogue("collection:x", tmp_path, get=get, log=lambda m: None, max_pages=1)
    assert not index["complete"] and calls == [None]
    index = fetch.fetch_catalogue("collection:x", tmp_path, get=get, log=lambda m: None)
    assert index["complete"] and calls == [None, "c2"]
    assert [r["identifier"] for r in fetch.records(tmp_path)] == [r["identifier"] for r in RECORDS]
    (tmp_path / "page-0001.json.gz").write_bytes(gzip.compress(b'{"items": []}'))
    with pytest.raises(ValueError, match="sha256"):
        list(fetch.records(tmp_path))


def test_refusals_stop_the_fetch():
    counter = net.RefusalCounter(limit=3)
    counter.refused(429)
    counter.ok()
    counter.refused(503)
    counter.refused(429)
    with pytest.raises(net.TooManyRefusals):
        counter.refused(503)


def test_fulltext_takes_page_indexed_text_and_resumes(tmp_path):
    served = {"31761000000001_hocr_searchtext.txt.gz": gzip.compress(b"page one text page two text"),
              "31761000000001_hocr_pageindex.json.gz": gzip.compress(b"[[0, 13, 0, 0], [14, 27, 0, 0]]")}
    meta = {"files": [{"name": "OTHER_NAME_hocr_searchtext.txt.gz"}]}
    served["OTHER_NAME_hocr_searchtext.txt.gz"] = gzip.compress(b"text")
    calls = []

    def get(url, refusals=None):
        calls.append(url)
        name = url.rsplit("/", 1)[-1]
        if url.startswith("https://archive.org/metadata/"):
            return json.dumps(meta).encode()
        if name in served:
            return served[name]
        raise net.HttpError(404, "missing")
    counts = fulltext.run(["31761000000001", "odd-item"], tmp_path, get=get, log=lambda m: None)
    assert counts["fetched"] == 2 and counts["errors"] == 0
    rows = {json.loads(l)["identifier"]: json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text().splitlines()}
    assert rows["31761000000001"]["kind"] == "hocr"
    assert set(rows["31761000000001"]["files"]) == {"searchtext", "pageindex"}
    assert rows["odd-item"]["kind"] == "searchtext_only"
    assert "metadata" in rows["odd-item"]["files"]
    before = len(calls)
    fulltext.run(["31761000000001", "odd-item"], tmp_path, get=get, log=lambda m: None)
    assert len(calls) == before            # nothing fetched twice


def make_corpus():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE items (item_id TEXT, title TEXT, creator_raw TEXT, publisher_raw TEXT, date_raw TEXT,
          collection_raw TEXT, language TEXT, page_count INTEGER, issuer_norm TEXT, issuer_method TEXT,
          jurisdiction_norm TEXT, jurisdiction_method TEXT, year INTEGER, date_method TEXT, dated INTEGER);
        CREATE TABLE pages (item_id TEXT, leaf_index INTEGER, printed_page TEXT, ocr_conf_mean REAL);
        CREATE TABLE passages (passage_id TEXT, item_id TEXT, leaf_index INTEGER, char_start INTEGER, char_end INTEGER, text TEXT);
    """)
    c.execute("INSERT INTO items VALUES ('micro_IA1', 'Report', NULL, 'Manitoba Health', '1985', '[\"microlog\"]', 'eng', 10, "
              "'Manitoba Health', 'alias', 'manitoba', 'publisher', 1985, 'exact', 1)")
    c.execute("INSERT INTO items VALUES ('31761000000001', 'x', NULL, NULL, '1978', '[]', 'eng', 40, NULL, NULL, 'ontario', "
              "'publisher', 1978, 'exact', 1)")
    c.execute("INSERT INTO pages VALUES ('micro_IA1', 3, '1', 0.9)")
    c.execute("INSERT INTO passages VALUES ('micro_IA1#3:0', 'micro_IA1', 3, 0, 20, 'Hospital beds were 6.9')")
    return c


def test_registry_builds_known_and_indexed_with_stable_ids(tmp_path):
    conn = build.open_registry(tmp_path / "r.db")
    counts = build.add_catalogue(conn, RECORDS, source_collection="governmentpublications")
    assert counts["documents"] == 3
    got = build.add_indexed(conn, make_corpus(), "microlog")
    assert got["new_documents"] == 1 and got["passages"] == 1
    states = {(r[0], r[1]) for r in conn.execute("SELECT doc_id, state FROM coverage")}
    assert ("ia:undated-pamphlet", "known") in states and ("ia:micro_IA1", "indexed") in states
    assert ("ia:31761000000001", "indexed") in states
    # The passage keeps the corpus's own id, so every v1 citation still resolves.
    row = conn.execute("SELECT doc_id, page_id FROM passages WHERE passage_id = 'micro_IA1#3:0'").fetchone()
    assert tuple(row) == ("ia:micro_IA1", "ia:micro_IA1#3")
    # Dates of different kinds stay apart; an undated record gets a derived date only from its title.
    dates = {(r[0], r[1]): r[2] for r in conn.execute("SELECT doc_id, kind, year FROM dates")}
    assert dates[("ia:31761000000001", "catalogue")] == 1978
    assert dates[("ia:alberta-health-1999", "catalogue")] is None
    assert dates[("ia:alberta-health-1999", "derived")] == 1998
    assert ("ia:undated-pamphlet", "derived") not in dates


def test_registry_rebuild_is_idempotent(tmp_path):
    conn = build.open_registry(tmp_path / "r.db")
    build.add_catalogue(conn, RECORDS, source_collection="governmentpublications")
    first = conn.execute("SELECT doc_id, record_sha256, first_seen FROM documents ORDER BY doc_id").fetchall()
    build.add_catalogue(conn, RECORDS, source_collection="governmentpublications")
    assert conn.execute("SELECT doc_id, record_sha256, first_seen FROM documents ORDER BY doc_id").fetchall() == first


def test_audit_trail_is_append_only(tmp_path):
    conn = build.open_registry(tmp_path / "r.db")
    build.add_catalogue(conn, RECORDS[:1], source_collection="governmentpublications")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM audit_trail")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE audit_trail SET actor = 'x'")


def test_governance_refuses_a_fixture_and_maps_production_policies(tmp_path):
    conn = build.open_registry(tmp_path / "r.db")
    build.add_catalogue(conn, RECORDS, source_collection="governmentpublications")
    register = tmp_path / "policies.jsonl"
    register.write_text(json.dumps({"policy_id": "p1", "targets": {"items": ["undated-pamphlet"], "collections": []},
                                    "restrict": ["export"], "authority": "A records office"}) + "\n", encoding="utf-8")
    assert build.add_governance(conn, register) == {"policies": 1, "documents": 1}
    register.write_text(json.dumps({"policy_id": "f", "fixture": True, "targets": {}}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fixture"):
        build.add_governance(conn, register)
