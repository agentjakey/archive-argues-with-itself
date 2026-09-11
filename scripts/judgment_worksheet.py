"""Phase 16 judgment worksheet: every kept (verified) sentence of every cached real-
provider answer, with the FULL text of each passage it cites, so Jake can mark each
sentence supported / partly / not. Reads the answer cache and civic.db only; no model,
no network. Writes reports/phase16/judgment_worksheet.jsonl (one record per sentence,
judgment left empty) and judgment_worksheet.md (readable form), plus a summary of
abstentions and failed sentences.

    python scripts/judgment_worksheet.py [--seed eval/seed_questions.jsonl] [--out reports/phase16]

Records:
  {"kind": "sentence", "qid", "question", "sentence_no", "text", "cited": [{passage_id, item_id,
   title, year, jurisdiction, leaf_index, printed_page, deep_link, text}], "judgment": ""}
  {"kind": "abstention", "qid", "question", "abstention_text", "unsupported": [...]}
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def load_seed(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rows.append(json.loads(line))
    return rows


def passage_details(conn: sqlite3.Connection, pids: list[str]) -> dict:
    if not pids:
        return {}
    marks = ",".join("?" * len(pids))
    out = {}
    for r in conn.execute(
            f"SELECT p.passage_id, p.item_id, i.title, i.year, i.jurisdiction_norm, g.leaf_index, g.printed_page, p.text "
            f"FROM passages p JOIN pages g ON g.page_id = p.page_id JOIN items i ON i.item_id = p.item_id "
            f"WHERE p.passage_id IN ({marks})", pids):
        pid, item, title, year, jur, leaf, printed, text = r
        out[pid] = {"passage_id": pid, "item_id": item, "title": title, "year": year, "jurisdiction": jur,
                    "leaf_index": leaf, "printed_page": printed,
                    "deep_link": f"https://archive.org/details/{item}/page/n{leaf}", "text": text}
    return out


def build(seed: list[dict], cache_db: Path, civic_db: Path, config_path: Path) -> tuple[list[dict], dict]:
    from archive_debugger.api.app import answer_cache_key
    from archive_debugger.api.cache import retrieval_fingerprint
    from archive_debugger.generate.cli import load_generate_config
    from archive_debugger.retrieve.config import load_retrieve_config
    gcfg = load_generate_config(config_path)
    sha = retrieval_fingerprint(load_retrieve_config(config_path))
    cache = sqlite3.connect(f"file:{cache_db}?mode=ro", uri=True)
    civic = sqlite3.connect(f"file:{civic_db}?mode=ro", uri=True)
    records: list[dict] = []
    summary = {"questions": len(seed), "cached": 0, "missing": [], "answered": 0, "abstained": 0,
               "sentences": 0, "unsupported_sentences": 0, "model": gcfg["model"], "provider": gcfg["provider"]}
    for q in seed:
        key = answer_cache_key(gcfg, gcfg["provider"], gcfg["model"], q["text"], q.get("filters") or {}, sha)
        row = cache.execute("SELECT response_json, created_at FROM answers WHERE key = ?", (key,)).fetchone()
        if row is None:
            summary["missing"].append(q["qid"])
            continue
        summary["cached"] += 1
        resp = json.loads(row[0])
        ans = resp["answer"]
        summary["unsupported_sentences"] += len(ans.get("unsupported", []))
        if ans.get("abstained"):
            summary["abstained"] += 1
            records.append({"kind": "abstention", "qid": q["qid"], "question": q["text"],
                            "abstention_text": ans.get("abstention_text"), "unsupported": ans.get("unsupported", []),
                            "coverage": ans.get("coverage"), "generated_at": row[1]})
            continue
        summary["answered"] += 1
        pids = sorted({pid for s in ans["sentences"] for pid in s["cited_ids"]})
        details = passage_details(civic, pids)
        for n, s in enumerate(ans["sentences"], start=1):
            summary["sentences"] += 1
            records.append({"kind": "sentence", "qid": q["qid"], "question": q["text"], "sentence_no": n,
                            "text": s["text"], "cited": [details[pid] for pid in s["cited_ids"] if pid in details],
                            "judgment": "", "generated_at": row[1]})
        if ans.get("unsupported"):
            records.append({"kind": "unsupported", "qid": q["qid"], "question": q["text"], "unsupported": ans["unsupported"]})
    cache.close()
    civic.close()
    return records, summary


def write(records: list[dict], summary: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "judgment_worksheet.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    lines = ["# Phase 16 judgment worksheet", "",
             f"Every kept sentence of every cached answer ({summary['provider']}, {summary['model']}), with the full",
             "text of each cited passage. Mark each sentence: supported / partly / not. Judgments are recorded",
             "in eval/judgments_phase16.json, not here.", "",
             f"- questions: {summary['questions']}; cached answers: {summary['cached']}; missing from cache: {summary['missing'] or 'none'}",
             f"- answered: {summary['answered']}; abstained: {summary['abstained']}",
             f"- kept sentences to judge: {summary['sentences']}; sentences dropped as unsupported by the verifier/guard: {summary['unsupported_sentences']}",
             ""]
    current = None
    for r in records:
        if r["qid"] != current:
            current = r["qid"]
            lines += [f"## {r['qid']}: {r['question']}", ""]
        if r["kind"] == "abstention":
            lines += [f"ABSTAINED: {r['abstention_text']}", ""]
            for u in r["unsupported"]:
                lines += [f"- dropped: \"{u['text']}\" ({u['reason']})"]
            lines.append("")
        elif r["kind"] == "unsupported":
            lines += ["Dropped by the verifier or the fact-leak guard (not judged):"]
            for u in r["unsupported"]:
                lines += [f"- \"{u['text']}\" ({u['reason']})"]
            lines.append("")
        else:
            lines += [f"### Sentence {r['sentence_no']}  [judgment: ______ ]", "", f"> {r['text']}", ""]
            for c in r["cited"]:
                page = f"p. {c['printed_page']} (leaf {c['leaf_index']})" if c["printed_page"] else f"leaf {c['leaf_index']}"
                lines += [f"**{c['passage_id']}**  {c['title']} ({c['year']}, {c['jurisdiction']}), {page}  ",
                          f"{c['deep_link']}", "", "```", (c["text"] or "").strip(), "```", ""]
    (out_dir / "judgment_worksheet.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "judgment_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    from dotenv import load_dotenv  # CLI only
    load_dotenv(".env")
    from archive_debugger.api.app import DEFAULT_CACHE
    from archive_debugger.ingest.db import ENV_CACHE_PATH, env_path, resolve_db_path
    p = argparse.ArgumentParser(description="Build the Phase 16 sentence-level judgment worksheet from the answer cache.")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--seed", default=Path("eval/seed_questions.jsonl"), type=Path)
    p.add_argument("--out", default=Path("reports/phase16"), type=Path)
    args = p.parse_args(argv)
    records, summary = build(load_seed(args.seed), env_path(ENV_CACHE_PATH, DEFAULT_CACHE),
                             resolve_db_path(args.config), args.config)
    write(records, summary, args.out)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
