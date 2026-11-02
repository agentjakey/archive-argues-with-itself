"""Choosing an OCR engine on our worst pages, against a person's transcription.

    python scripts/v2/ocr_eval.py sample --collection microlog --pages 100
    python scripts/v2/ocr_eval.py score --engine-output <outputs.jsonl> [--engine-output ...]

`sample` picks the collection's worst body pages by the corpus's OCR quality score (the same choice
as the OCR job), drops pages that touch a care topic, spreads them over items (at most 3 a document),
and writes config/ocr_eval/sample.jsonl (committed: the sample is a decision) and, for each page, a
transcription file to fill in under data/ocr_eval/transcriptions/<item>__<leaf>.txt: the old OCR text
to correct against the page image, whose link is on the file's first line. A person types what the
page says; their files are the reference (author-reviewed when Jake does it alone).

`score` reads engine outputs (JSON lines {page_ref, text}, the OCR job's per-page output) and, for each
engine over the pages with a finished transcription:

  CER            character error rate: Levenshtein distance / reference length, whitespace collapsed
  hallucination  an added span: three or more consecutive output words, none of which is in the
                 reference (nor one edit away from a reference word). A recognition error changes
                 words; a hallucination adds words the page does not have.
  verdict        FAIL when any page has an added span, whatever the CER; otherwise the CER, with a
                 95% bootstrap interval over pages

Candidates (checked 2026-11-01): PaddleOCR-VL-1.6 (Apache-2.0), olmOCR 2 (Apache-2.0), docTR and
Tesseract (Apache-2.0). Chandra OCR 2 is not a candidate: its weights are under a modified OpenRAIL-M
licence with a revenue cap and a no-compete clause (docs/MODELS.md).
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

SAMPLE = REPO / "config" / "ocr_eval" / "sample.jsonl"
TRANSCRIPTIONS = REPO / "data" / "ocr_eval" / "transcriptions"
HEADER = "# "
WORD = re.compile(r"[^\W_]+", re.UNICODE)
SPAN = 3


def corpus(collection: str) -> sqlite3.Connection:
    from archive_debugger.audit import collections
    from archive_debugger.audit.run import corpus_connection
    from archive_debugger.local_env import load_local_env
    load_local_env(log=None)
    return corpus_connection(collections.load(collection))


def transcription_path(page_ref: str) -> Path:
    item, leaf = page_ref.split("#")
    return TRANSCRIPTIONS / f"{item}__{leaf}.txt"


def cmd_sample(args) -> int:
    from archive_debugger.exhibit import care as care_mod, settings
    rules = settings.load().care
    conn = corpus(args.collection)
    conn.row_factory = sqlite3.Row
    worst = conn.execute(
        "SELECT p.item_id, p.leaf_index, AVG(CAST(p.ocr_quality AS REAL)) AS q, i.title FROM passages p "
        "JOIN items i ON i.item_id = p.item_id WHERE p.ocr_quality IS NOT NULL AND LENGTH(p.text) > 400 "
        "GROUP BY p.item_id, p.leaf_index ORDER BY q ASC LIMIT ?", (args.pages * 20,)).fetchall()
    chosen, per_item = [], {}
    for r in worst:
        if len(chosen) >= args.pages or per_item.get(r["item_id"], 0) >= 3:
            continue
        text = "\n".join(t[0] for t in conn.execute(
            "SELECT text FROM passages WHERE item_id = ? AND leaf_index = ? ORDER BY char_start", (r["item_id"], r["leaf_index"])))
        if care_mod.care_flags([r["title"] or "", text], rules):
            continue
        per_item[r["item_id"]] = per_item.get(r["item_id"], 0) + 1
        chosen.append({"page_ref": f"{r['item_id']}#{r['leaf_index']}", "item_id": r["item_id"], "leaf": int(r["leaf_index"]),
                       "collection": args.collection, "old_quality": round(r["q"], 4),
                       "image": f"https://archive.org/download/{r['item_id']}/page/n{r['leaf_index']}.jpg",
                       "page": f"https://archive.org/details/{r['item_id']}/page/n{r['leaf_index']}", "_old": text})
    SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE.write_text("".join(json.dumps({k: v for k, v in p.items() if k != "_old"}) + "\n" for p in chosen), encoding="utf-8")
    TRANSCRIPTIONS.mkdir(parents=True, exist_ok=True)
    made = 0
    for p in chosen:
        path = transcription_path(p["page_ref"])
        if path.exists():
            continue                     # never overwrite a person's work
        path.write_text(f"{HEADER}{p['page']}\n{HEADER}Correct the text below to what the page says, then delete "
                        f"this line and add a line '{HEADER}done' at the top.\n{p['_old']}\n", encoding="utf-8")
        made += 1
    print(json.dumps({"pages": len(chosen), "documents": len(per_item), "templates_written": made, "sample": str(SAMPLE)}))
    return 0


def words(text: str) -> list:
    return [w.lower() for w in WORD.findall(text)]


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def near(word: str, vocab: set) -> bool:
    if word in vocab:
        return True
    if len(word) <= 3:
        return False
    return any(abs(len(word) - len(v)) <= 1 and levenshtein(word, v) <= 1 for v in vocab)


def added_spans(output: str, reference: str) -> list:
    vocab = set(words(reference))
    out, run = [], []
    for w in words(output):
        if near(w, vocab):
            if len(run) >= SPAN:
                out.append(" ".join(run))
            run = []
        else:
            run.append(w)
    if len(run) >= SPAN:
        out.append(" ".join(run))
    return out


def cer(output: str, reference: str) -> float:
    o, r = " ".join(output.split()), " ".join(reference.split())
    return levenshtein(o, r) / max(1, len(r))


def reference(page_ref: str):
    path = transcription_path(page_ref)
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != f"{HEADER}done":
        return None
    return "\n".join(l for l in lines if not l.startswith(HEADER))


def score(outputs: dict, refs: dict, seed: int = 7) -> dict:
    pages = sorted(set(outputs) & set(refs))
    rows = [{"page_ref": p, "cer": cer(outputs[p], refs[p]), "added": added_spans(outputs[p], refs[p])} for p in pages]
    if not rows:
        return {"pages": 0}
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(rows)["cer"] for _ in rows) / len(rows) for _ in range(2000))
    hallucinated = [r for r in rows if r["added"]]
    return {"pages": len(rows), "cer": round(sum(r["cer"] for r in rows) / len(rows), 4),
            "cer_95": [round(means[49], 4), round(means[1949], 4)],
            "pages_with_added_text": len(hallucinated), "examples": [(r["page_ref"], r["added"][:2]) for r in hallucinated[:5]],
            "verdict": "FAIL: adds text the page does not have" if hallucinated else "pass"}


def cmd_score(args) -> int:
    sample = [json.loads(l) for l in SAMPLE.read_text(encoding="utf-8").splitlines() if l.strip()]
    refs = {p["page_ref"]: r for p in sample if (r := reference(p["page_ref"])) is not None}
    if not refs:
        print(f"no finished transcriptions yet in {TRANSCRIPTIONS} (a file counts once its first line is '{HEADER}done')")
        return 1
    result = {}
    for path in args.engine_output:
        outputs = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                outputs[row["page_ref"]] = row["text"]
        result[Path(path).stem] = score(outputs, refs)
    print(json.dumps({"references": len(refs), "engines": result}, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["sample", "score"])
    ap.add_argument("--collection", default="microlog")
    ap.add_argument("--pages", type=int, default=100)
    ap.add_argument("--engine-output", action="append", default=[])
    args = ap.parse_args(argv)
    return {"sample": cmd_sample, "score": cmd_score}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
