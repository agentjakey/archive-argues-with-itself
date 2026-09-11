"""Answer cache: a separate SQLite file (default data/cache/answers.db, git-ignored)
keyed by the full generation context, so civic.db stays read-only and a repeated
question is served without a second model call."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    key           TEXT PRIMARY KEY,
    response_json TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
"""


def cache_key(*, question: str, filters: Optional[dict], provider: str, model: str,
              prompt_sha256: str, top_k: int, temperature: Optional[float]) -> str:
    material = json.dumps({
        "question": question, "filters": filters or {}, "provider": provider, "model": model,
        "prompt_sha256": prompt_sha256, "top_k": top_k, "temperature": temperature,
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class AnswerCache:
    def __init__(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.executescript(SCHEMA)

    def get(self, key: str) -> Optional[dict]:
        row = self.conn.execute("SELECT response_json, created_at FROM answers WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return {"response": json.loads(row[0]), "created_at": row[1]}

    def put(self, key: str, response: dict) -> str:
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.conn.execute("INSERT OR REPLACE INTO answers (key, response_json, created_at) VALUES (?,?,?)",
                          (key, json.dumps(response, ensure_ascii=False), created))
        self.conn.commit()
        return created

    def close(self) -> None:
        self.conn.close()
