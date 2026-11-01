"""Judge items (docs/formats/audit.md): one kept answer sentence with the question it answers
and the full text of every passage it cites. Built from a collection's v1 audit worksheet; the
answer's retrieved evidence comes from the recorded answer when one exists for the same question
and sentence. People's labels are kept in a separate file, so a judge never sees them."""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

from archive_debugger.audit.collections import Collection
from archive_debugger.audit.records import iter_jsonl

ITEM_FORMAT = 1
CITATION_FIELDS = ("passage_id", "item_id", "title", "year", "jurisdiction", "leaf_index", "printed_page",
                   "deep_link", "text")


def item_id(collection: str, qid: str, sentence_no: int) -> str:
    return f"{collection}:{qid}:s{int(sentence_no)}"


def _year(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _recorded_answers(index_path: Optional[Path]) -> dict:
    """{qid: (filters, recorded response)} for the recorded answers to seed questions."""
    if not index_path or not Path(index_path).exists():
        return {}
    index = json.loads(Path(index_path).read_text(encoding="utf-8"))
    out = {}
    for entry in index.get("answers") or []:
        label = entry.get("label") or ""
        if not entry.get("file") or not label.startswith("seed:"):
            continue
        qid = label.split(":", 1)[1]
        # entry paths are relative to the collection's folder, which holds answers/index.json
        response = json.loads((Path(index_path).parent.parent / entry["file"]).read_text(encoding="utf-8"))
        out[qid] = (entry.get("filters") or {}, response)
    return out


def build_v1_items(collection: Collection) -> list[dict]:
    """Every kept sentence of the collection's v1 answers, in worksheet order."""
    if collection.v1 is None:
        raise ValueError(f"collection {collection.name} has no [v1] sources")
    recorded = _recorded_answers(collection.v1.answers_index)
    sentences: dict = {}
    for row in iter_jsonl(collection.v1.worksheet):
        if row.get("kind") == "sentence":
            sentences.setdefault(row["qid"], []).append(row)
    items = []
    for qid, rows in sentences.items():
        rows.sort(key=lambda r: int(r["sentence_no"]))
        answer_text = " ".join(r["text"] for r in rows)
        filters, response = recorded.get(qid, ({}, None))
        recorded_sentences = [s["text"] for s in (response or {}).get("answer", {}).get("sentences") or []]
        same_answer = recorded_sentences == [r["text"] for r in rows]
        retrieved = [e["passage_id"] for e in response["evidence"] if e.get("in_prompt")] if response and same_answer else None
        for r in rows:
            citations = []
            for c in r.get("cited") or []:
                cite = {k: c.get(k) for k in CITATION_FIELDS}
                cite["year"] = _year(cite["year"])
                cite["leaf_index"] = int(cite["leaf_index"])
                citations.append(cite)
            items.append({
                "format": ITEM_FORMAT,
                "item_id": item_id(collection.name, qid, r["sentence_no"]),
                "collection": collection.name,
                "qid": qid,
                "question": r["question"],
                "filters": filters if same_answer else {},
                "sentence_no": int(r["sentence_no"]),
                "sentence": r["text"],
                "answer_text": answer_text,
                "citations": citations,
                "retrieved_ids": retrieved,
                "source": "v1",
                "generated_at": r.get("generated_at"),
            })
    return items


def v1_labels(collection: Collection) -> dict:
    """{item_id: class} for the SUPPORTS check, from the author-reviewed v1 decisions, mapped
    through the collection's label_map. A sentence with no decision is left out."""
    v1 = collection.v1
    if v1 is None or v1.labels is None:
        return {}
    out = {}
    if v1.labels_kind == "by_question":
        raw = json.loads(Path(v1.labels).read_text(encoding="utf-8"))
        for qid, by_sentence in raw.items():
            if qid.startswith("_"):
                continue
            for sentence_no, label in by_sentence.items():
                if label in v1.label_map:
                    out[item_id(collection.name, qid, sentence_no)] = v1.label_map[label]
    else:
        for row in iter_jsonl(v1.labels):
            if row.get("kind") == "sentence" and row.get("judgment") in v1.label_map:
                out[item_id(collection.name, row["qid"], row["sentence_no"])] = v1.label_map[row["judgment"]]
    return out


def select_answers(items: list[dict], count: int, seed: int) -> list[dict]:
    """Every item of `count` answers chosen at random (by seed) among the answers present, spread
    evenly over the collections in `items`. Used for the first measured runs."""
    by_collection: dict = {}
    for it in items:
        by_collection.setdefault(it["collection"], set()).add(it["qid"])
    rng = random.Random(seed)
    names = sorted(by_collection)
    chosen = set()
    per = [count // len(names) + (1 if i < count % len(names) else 0) for i in range(len(names))]
    for name, n in zip(names, per):
        qids = sorted(by_collection[name])
        for qid in rng.sample(qids, min(n, len(qids))):
            chosen.add((name, qid))
    return [it for it in items if (it["collection"], it["qid"]) in chosen]
