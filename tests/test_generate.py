"""Phase 9 generation tests. Hermetic: stub LLM, stub embedder, temp db, no network."""
from __future__ import annotations

import functools
import subprocess
import sys

from archive_debugger.generate import answer as gen
from archive_debugger.generate.llm import CitedSentence, Draft, StubLLM
from archive_debugger.ingest import db
from archive_debugger.retrieve import citation, index, search
from archive_debugger.retrieve.config import RetrieveConfig
from archive_debugger.retrieve.embed import StubEmbedder

MIN = {"min_items": 2, "min_passages": 3}


def _seed(conn, n_items=3, per_item=2, text="vaccination programme text", fts=True):
    hits = []
    for i in range(n_items):
        item = f"item{i}"
        conn.execute("INSERT INTO items (item_id, title, year, dated, decade, jurisdiction_norm) VALUES (?,?,?,?,?,?)",
                     (item, f"T{i}", 1985, 1, "1980s", "alberta"))
        for leaf in range(per_item):
            pid = f"{item}#{leaf}:0"
            conn.execute("INSERT INTO pages (page_id,item_id,leaf_index,printed_page) VALUES (?,?,?,?)",
                         (f"{item}#{leaf}", item, leaf, str(leaf + 1)))
            conn.execute("INSERT INTO passages (passage_id,item_id,page_id,leaf_index,text) VALUES (?,?,?,?,?)",
                         (pid, item, f"{item}#{leaf}", leaf, text))
            hits.append({"passage_id": pid, "item_id": item, "title": f"T{i}", "year": 1985, "dated": 1,
                         "decade": "1980s", "jurisdiction": "alberta", "leaf_index": leaf,
                         "printed_page": str(leaf + 1), "text": text,
                         "page_deep_link": citation.deep_link(item, leaf),
                         "bm25_rank": (len(hits) + 1) if fts else None, "dense_rank": len(hits) + 1})
    conn.commit()
    return hits


def _compose(conn, hits, draft):
    return gen.compose("q", hits, StubLLM(draft), functools.partial(citation.verify_citations, conn), **MIN)


def test_unknown_id_is_rejected_then_abstains_unverified():
    conn = db.init_db(":memory:")
    hits = _seed(conn)
    a = _compose(conn, hits, Draft(sentences=[CitedSentence(text="Claim.", cited_ids=["ghost#0:0"])]))
    assert a.abstained and a.text == gen.ABSTAIN_UNVERIFIED
    assert a.unsupported[0]["reason"].startswith("citation failed") and a.coverage.n_passages == 6
    conn.close()


def test_id_outside_retrieved_set_is_rejected():
    conn = db.init_db(":memory:")
    hits = _seed(conn)
    outside = hits.pop()
    a = _compose(conn, hits, Draft(sentences=[
        CitedSentence(text="Bad.", cited_ids=[outside["passage_id"]]),
        CitedSentence(text="Good.", cited_ids=[hits[0]["passage_id"]])]))
    assert a.text == "Good." and "citation failed" in a.unsupported[0]["reason"]
    conn.close()


def test_thin_fts_subset_abstains_without_calling_model():
    conn = db.init_db(":memory:")
    hits = _seed(conn, n_items=3, per_item=2, fts=False)   # 6 dense-only hits, 0 FTS matches
    llm = StubLLM(Draft(sentences=[CitedSentence(text="x", cited_ids=[hits[0]["passage_id"]])]))
    a = gen.compose("q", hits, llm, functools.partial(citation.verify_citations, conn), **MIN)
    assert a.abstained
    assert a.text == ("the record here is thin: 0 items and 0 passages match the question's terms "
                      "(0 of 6 retrieved passages are undated)")
    assert llm.calls == 0 and a.coverage.n_fts_passages == 0
    conn.close()


def test_well_formed_answer_passes_with_page_level_links():
    conn = db.init_db(":memory:")
    hits = _seed(conn)
    ids = [h["passage_id"] for h in hits[:2]]
    a = _compose(conn, hits, Draft(sentences=[CitedSentence(text="Alberta ran a programme in 1985.", cited_ids=ids)]))
    assert not a.abstained and a.unsupported == [] and a.text == "Alberta ran a programme in 1985."
    assert {c["passage_id"] for c in a.verified_citations} == set(ids)
    assert all(c["deep_link"] == citation.deep_link(c["item_id"], c["leaf_index"]) for c in a.verified_citations)
    conn.close()


def test_year_in_passage_text_is_allowed():
    conn = db.init_db(":memory:")
    hits = _seed(conn, text="the 1970 survey of vaccination")   # item year 1985, text says 1970
    a = _compose(conn, hits, Draft(sentences=[CitedSentence(text="A survey ran in 1970.", cited_ids=[hits[0]["passage_id"]])]))
    assert not a.abstained and a.text == "A survey ran in 1970."
    conn.close()


def test_year_absent_everywhere_is_unsupported():
    conn = db.init_db(":memory:")
    hits = _seed(conn)
    a = _compose(conn, hits, Draft(sentences=[CitedSentence(text="This happened in 1999.", cited_ids=[hits[0]["passage_id"]])]))
    assert a.abstained and a.text == gen.ABSTAIN_UNVERIFIED and "year or page" in a.unsupported[0]["reason"]
    conn.close()


def test_key_contract_real_retriever_to_compose(tmp_path):
    civ = tmp_path / "civic.db"
    conn = db.init_db(str(civ))
    text = "vaccination hospital programme"
    for item, jur in (("itemA", "alberta"), ("itemB", "ontario")):
        conn.execute("INSERT INTO items (item_id, title, dated, year, decade, jurisdiction_norm, details_url) VALUES (?,?,?,?,?,?,?)",
                     (item, item, 1, 1985, "1980s", jur, f"https://archive.org/details/{item}"))
        for leaf in (0, 1):
            conn.execute("INSERT INTO pages (page_id, item_id, leaf_index, printed_page, has_text) VALUES (?,?,?,?,1)",
                         (f"{item}#{leaf}", item, leaf, str(leaf + 1)))
            conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, text, token_count, ocr_quality) VALUES (?,?,?,?,0,30,?,3,'0.95')",
                         (f"{item}#{leaf}:0", item, f"{item}#{leaf}", leaf, text))
    conn.commit()
    conn.close()
    vectors = tmp_path / "vectors.db"
    index.build_index(civ, vectors, StubEmbedder(dim=64), model_id="stub", batch_size=8)
    cfg = RetrieveConfig(db_path=civ, index_path=vectors, embedder="stub", embedding_model="stub",
                         embedding_dim=64, batch_size=8, candidates=10, rrf_k=60,
                         downweights={"high": 1.0, "medium": 0.9, "low": 0.75})
    r = search.Retriever(None, embedder=StubEmbedder(dim=64), cfg=cfg)
    try:
        hits = r.search("vaccination hospital", top_k=10)
        assert {"passage_id", "item_id", "title", "year", "dated", "decade", "jurisdiction",
                "leaf_index", "printed_page", "page_deep_link", "text", "bm25_rank", "dense_rank"} <= set(hits[0])
        draft = Draft(sentences=[CitedSentence(text="Both provinces ran programmes.", cited_ids=[hits[0]["passage_id"]])])
        a = gen.compose("q", hits, StubLLM(draft), functools.partial(citation.verify_citations, r.conn), **MIN)
        assert not a.abstained and a.verified_citations[0]["deep_link"] == hits[0]["page_deep_link"]
    finally:
        r.close()


def test_importing_generate_does_not_import_anthropic():
    code = ("import archive_debugger.generate.answer, archive_debugger.generate.llm, sys; "
            "assert 'anthropic' not in sys.modules")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
