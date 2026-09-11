"""Build a tiny civic.db + vectors.db pair for CI smoke runs of the real API.

Twelve small dated items across the pilot decades, two passages each, the seed
questions loaded (no gold: labels are human work, N4), and a stub-embedder vector
index at the configured dimension so `CIVIC_EMBEDDER=stub` serves it. Nothing here
touches the network or the real corpus.

    python scripts/make_fixture_db.py OUT_DIR
    -> OUT_DIR/civic.db, OUT_DIR/vectors.db"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from archive_debugger.eval import questions
from archive_debugger.ingest import db
from archive_debugger.retrieve import index
from archive_debugger.retrieve.embed import StubEmbedder

TEXTS = [
    "The provincial tuberculosis control programme reported sanatorium admissions and outpatient clinics.",
    "Public health authorities recommended vaccination of school children against diphtheria and polio.",
    "Hospital insurance coverage was extended to all residents; premiums were abolished for seniors.",
    "The commission examined occupational health and safety risks from asbestos in mines and mills.",
    "Community health nurses reported on maternal and infant mortality in rural districts.",
    "The task force on tobacco control recommended higher taxes and smoke-free public places.",
]


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python scripts/make_fixture_db.py OUT_DIR")
        return 2
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    civ, vectors = out / "civic.db", out / "vectors.db"
    for p in (civ, vectors):
        if p.exists():
            p.unlink()
    with Path("config/pilot.toml").open("rb") as fh:
        cfg = tomllib.load(fh)
    dim = int(cfg["index"]["embedding_dim"])

    conn = db.init_db(str(civ))
    jurisdictions = ["federal", "ontario", "alberta"]
    doc_types = ["annual_report", "royal_commission", "other", "commission"]
    for k in range(12):
        item, year = f"fixture{k:02d}", 1962 + 4 * k            # 1962 .. 2006
        conn.execute(
            "INSERT INTO items (item_id, title, dated, year, decade, jurisdiction_norm, doc_type_norm, details_url) "
            "VALUES (?,?,1,?,?,?,?,?)",
            (item, f"Fixture report {year}", year, f"{(year // 10) * 10}s", jurisdictions[k % 3], doc_types[k % 4],
             f"https://archive.org/details/{item}"))
        for leaf in range(2):
            text = TEXTS[(k + leaf) % len(TEXTS)]
            conn.execute("INSERT INTO pages (page_id, item_id, leaf_index, printed_page, char_count, has_text, section_class) "
                         "VALUES (?,?,?,?,?,1,'body')", (f"{item}#{leaf}", item, leaf, str(leaf + 1), len(text)))
            conn.execute("INSERT INTO passages (passage_id, item_id, page_id, leaf_index, char_start, char_end, text, "
                         "token_count, ocr_quality) VALUES (?,?,?,?,0,?,?,?,'0.95')",
                         (f"{item}#{leaf}:0", item, f"{item}#{leaf}", leaf, len(text), text, len(text.split())))
    seed = Path("eval/seed_questions.jsonl")
    if seed.exists():
        questions.insert_questions(conn, list(questions.load_seed(seed)))
    conn.commit()
    conn.close()
    wrote = index.build_index(civ, vectors, StubEmbedder(dim=dim), model_id="stub", batch_size=8)
    print(f"fixture: {civ} and {vectors} ({wrote} vectors, dim {dim})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
