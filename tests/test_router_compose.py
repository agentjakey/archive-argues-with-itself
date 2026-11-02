"""The cross-shard router's engine side: a shard's evidence-only reply carries its candidates' text and
query-term counts only for the engine Worker, and POST /compose writes one answer from evidence merged
across shards, checking citations against exactly the rows supplied."""
from __future__ import annotations

from fastapi.testclient import TestClient

from archive_debugger.api.app import SuppliedEvidence
from archive_debugger.generate.llm import CitedSentence, Draft, StubLLM
from tests.test_api import _app, _retriever

ROUTER = {"x-civic-router": "1"}


def test_router_rows_go_only_to_the_worker(tmp_path):
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta"), ("b", 1990, "ontario")])
    with TestClient(_app(tmp_path, r)) as c:
        plain = c.post("/ask", json={"question": "vaccination hospital", "evidence_only": True}).json()
        routed = c.post("/ask", json={"question": "vaccination hospital", "evidence_only": True}, headers=ROUTER).json()
        answered = c.post("/ask", json={"question": "vaccination hospital"}, headers=ROUTER).json()
    assert "router" not in plain and "router" not in answered        # never to a visitor, never with an answer
    rows = routed["router"]["hits"]
    assert rows and all(row["text"] == "vaccination hospital programme" for row in rows)
    assert rows[0]["tf"] == {"vaccination": 1, "hospital": 1} and rows[0]["dl"] == 3
    assert {"passage_id", "item_id", "leaf_index", "page_deep_link", "date_method"} <= set(rows[0])


def test_compose_answers_from_supplied_rows_and_cites_only_them(tmp_path):
    r, _ = _retriever(tmp_path, [("a", 1985, "alberta")])
    supplied = [
        {"passage_id": "far#3:0", "item_id": "far", "leaf_index": 3, "page_deep_link": "https://archive.org/details/far/page/n3",
         "text": "vaccination hospital programme in another shard", "title": "Far report", "year": 1970,
         "jurisdiction": "manitoba", "date_method": "exact"},
        {"passage_id": "near#0:0", "item_id": "near", "leaf_index": 0, "page_deep_link": "https://archive.org/details/near/page/n0",
         "text": "vaccination hospital beds", "title": "Near report", "year": 1980, "jurisdiction": "alberta"},
        {"passage_id": "mid#2:0", "item_id": "mid", "leaf_index": 2, "page_deep_link": "https://archive.org/details/mid/page/n2",
         "text": "vaccination hospital wards", "title": "Mid report", "year": 1975, "jurisdiction": "ontario"},
        {"passage_id": "bad", "text": "no item named"},                               # dropped: no page to link
    ]
    llm = StubLLM(Draft(sentences=[CitedSentence(text="A programme ran.", cited_ids=["far#3:0"]),
                                   CitedSentence(text="Invented.", cited_ids=["a#0:0"])]))
    with TestClient(_app(tmp_path, r, llm=llm)) as c:
        refused = c.post("/compose", json={"question": "vaccination hospital", "hits": supplied})
        out = c.post("/compose", json={"question": "vaccination hospital", "hits": supplied,
                                       "prompt_ids": ["far#3:0", "near#0:0", "mid#2:0", "bad"]}, headers=ROUTER).json()
        again = c.post("/ask", json={"question": "vaccination hospital"}).json()
    assert refused.status_code == 404                                   # a visitor cannot reach it
    assert {e["passage_id"] for e in out["evidence"]} == {"far#3:0", "near#0:0", "mid#2:0"}
    cited = {e["passage_id"] for e in out["evidence"] if e["cited"]}
    assert cited == {"far#3:0"}                                         # a#0:0 is in this engine's DB, not the evidence
    assert next(e for e in out["evidence"] if e["passage_id"] == "far#3:0")["date_method"] == "exact"
    assert out["answer"]["cached"] is None
    assert again["answer"]["cached"] is None                            # nothing was stored for the question


def test_supplied_evidence_checks():
    verify = SuppliedEvidence([{"passage_id": "x#1:0", "item_id": "x", "leaf_index": 1}])
    ok, missing, unseen = verify(["x#1:0", "y#0:0", "x#1:0"], ["x#1:0"])[0], verify(["y#0:0"], ["y#0:0"])[0], \
        verify(["x#1:0"], [])[0]
    assert ok.ok and ok.deep_link.endswith("/page/n1")
    assert not missing.exists and not missing.ok
    assert unseen.exists and not unseen.in_evidence and not unseen.ok
