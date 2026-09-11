"""Gold-label store. Human judgments live here; candidate question text in
eval_questions is never used as gold (N4)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def list_questions(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT qid, text, topic, qtype, filters_json, notes FROM eval_questions ORDER BY qid")]


def get_question(conn: sqlite3.Connection, qid: str):
    r = conn.execute(
        "SELECT qid, text, topic, qtype, filters_json, notes FROM eval_questions WHERE qid=?",
        (qid,)).fetchone()
    return dict(r) if r else None


def gold_verdict(conn: sqlite3.Connection, qid: str):
    r = conn.execute("SELECT answerable, labeled_ts FROM eval_question_gold WHERE qid=?", (qid,)).fetchone()
    return dict(r) if r else None


def is_labeled(conn: sqlite3.Connection, qid: str) -> bool:
    return gold_verdict(conn, qid) is not None


def get_labels(conn: sqlite3.Connection, qid: str) -> dict:
    return {r["passage_id"]: r["relevance"]
            for r in conn.execute("SELECT passage_id, relevance FROM eval_labels WHERE qid=?", (qid,))}


def write_label(conn: sqlite3.Connection, qid: str, passage_id: str, relevance: int) -> None:
    conn.execute("INSERT OR REPLACE INTO eval_labels (qid, passage_id, relevance) VALUES (?,?,?)",
                 (qid, passage_id, int(relevance)))
    conn.commit()


def write_gold(conn: sqlite3.Connection, qid: str, answerable: int) -> None:
    conn.execute("INSERT OR REPLACE INTO eval_question_gold (qid, answerable, labeled_ts) VALUES (?,?,?)",
                 (qid, int(answerable), datetime.now(timezone.utc).isoformat(timespec="seconds")))
    conn.commit()


def clear_labels(conn: sqlite3.Connection, qid: str) -> None:
    conn.execute("DELETE FROM eval_labels WHERE qid=?", (qid,))
    conn.execute("DELETE FROM eval_question_gold WHERE qid=?", (qid,))
    conn.commit()
