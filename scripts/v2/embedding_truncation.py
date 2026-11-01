"""How much of each passage the dense model actually reads (Phase 2 Part A).

    python scripts/v2/embedding_truncation.py --per-collection 20000 --seed 20261101

The dense model (paraphrase-multilingual-MiniLM-L12-v2 through fastembed) truncates its input. This
script reads the truncation fastembed applies, then tokenizes a seeded random sample of passages from
each corpus with the model's own tokenizer, untruncated, and reports the token-length distribution,
the share of passages longer than the limit, and the share of each passage's words that fall inside
the limit (the part that is embedded). Reads the corpus databases read-only; no network beyond what
fastembed needs to find its cached model. Writes reports/v2/baseline/embedding_truncation.json."""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
OUT = REPO / "reports" / "v2" / "baseline" / "embedding_truncation.json"
BUCKETS = (64, 128, 192, 256, 384, 512, 768, 1024)


def sample_passages(conn, size: int, seed: int) -> list:
    top = conn.execute("SELECT max(rowid) FROM passages").fetchone()[0]
    rng = random.Random(seed)
    rowids = sorted(rng.sample(range(1, top + 1), min(size * 2, top)))
    out = []
    for start in range(0, len(rowids), 900):
        chunk = rowids[start:start + 900]
        marks = ",".join("?" * len(chunk))
        out.extend(r[0] for r in conn.execute(f"SELECT text FROM passages WHERE rowid IN ({marks})", chunk))
        if len(out) >= size:
            break
    return out[:size]


def main(argv=None) -> int:
    from archive_debugger import scopes
    from archive_debugger.eval.rundb import open_corpus_read_only
    from archive_debugger.local_env import load_local_env
    from fastembed import TextEmbedding
    load_local_env(log=lambda m: None)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-collection", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=20261101)
    parser.add_argument("--scopes", nargs="*", default=["pilot", "microlog"])
    args = parser.parse_args(argv)

    model = TextEmbedding(model_name=MODEL)
    tok = model.model.tokenizer
    truncation = dict(tok.truncation or {})
    limit = int(truncation.get("max_length") or 0)
    tok.no_truncation()
    tok.no_padding()
    report = {"model": MODEL, "fastembed_truncation": truncation, "limit_tokens": limit, "seed": args.seed, "scopes": {}}
    for name in args.scopes:
        conn = open_corpus_read_only(scopes.resolve_scope(name).db_path)
        texts = sample_passages(conn, args.per_collection, args.seed)
        lengths, embedded_share = [], []
        for start in range(0, len(texts), 512):
            batch = texts[start:start + 512]
            for text, enc in zip(batch, tok.encode_batch(batch)):
                n = len(enc.ids)
                lengths.append(n)
                words = text.split()
                if n <= limit or not words:
                    embedded_share.append(1.0)
                    continue
                # the last character inside the limit (the final token is the closing special token)
                cut = max((end for (start_, end), wid in zip(enc.offsets[:limit - 1], enc.word_ids[:limit - 1])
                           if wid is not None), default=0)
                embedded_share.append(len(text[:cut].split()) / len(words))
        lengths.sort()
        q = lambda p: lengths[min(len(lengths) - 1, int(p * len(lengths)))]
        report["scopes"][name] = {
            "passages_sampled": len(lengths),
            "tokens": {"mean": round(statistics.mean(lengths), 1), "p10": q(0.10), "p50": q(0.50), "p90": q(0.90),
                       "p99": q(0.99), "max": lengths[-1]},
            "share_over_limit": round(sum(1 for n in lengths if n > limit) / len(lengths), 4),
            "histogram": {f"<= {b}": sum(1 for n in lengths if n <= b) for b in BUCKETS}
                         | {f"> {BUCKETS[-1]}": sum(1 for n in lengths if n > BUCKETS[-1])},
            "words_embedded_share": {"mean": round(statistics.mean(embedded_share), 4),
                                     "p10": round(sorted(embedded_share)[int(0.10 * len(embedded_share))], 4),
                                     "p50": round(statistics.median(embedded_share), 4)},
        }
        print(name, json.dumps(report["scopes"][name]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
