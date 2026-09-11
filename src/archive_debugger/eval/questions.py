"""Load candidate eval questions from the human-edited seed file into
eval_questions. Candidate TEXT + scoping hints only -- never labels, expected
answers, or expected period/jurisdiction gold (N4)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from archive_debugger.ingest import db

QTYPES = {"factual", "temporal_comparison", "abstention_probe"}


def load_seed(path: Path) -> list[dict]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(json.loads(line))
    return out


def insert_questions(conn, records, *, replace=False) -> int:
    verb = "INSERT OR REPLACE INTO" if replace else "INSERT OR IGNORE INTO"
    sql = verb + " eval_questions (qid, text, topic, qtype, filters_json, notes) VALUES (?,?,?,?,?,?)"
    n = 0
    for r in records:
        qtype = r.get("qtype")
        if qtype is not None and qtype not in QTYPES:
            raise ValueError(f"{r.get('qid')}: qtype must be null or one of {sorted(QTYPES)}")
        conn.execute(sql, (r["qid"], r["text"], r.get("topic"), qtype,
                           json.dumps(r.get("filters") or {}, ensure_ascii=False), r.get("notes")))
        n += 1
    conn.commit()
    return n


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Load candidate eval questions (candidate text only).")
    p.add_argument("--config", default="config/pilot.toml", type=Path)
    p.add_argument("--file", default="eval/seed_questions.jsonl", type=Path)
    p.add_argument("--replace", action="store_true",
                   help="overwrite candidate text (never touches eval_labels / eval_question_gold)")
    args = p.parse_args(argv)
    conn = db.init_db(db.resolve_db_path(args.config))
    try:
        n = insert_questions(conn, load_seed(args.file), replace=args.replace)
    finally:
        conn.close()
    print(f"loaded {n} candidate questions from {args.file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
