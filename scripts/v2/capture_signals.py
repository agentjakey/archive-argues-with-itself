"""AI and TDM preference signals in effect at each capture of the bounded web-archive set.

    python scripts/v2/capture_signals.py --name wayback-hc-tobacco

Reads data/sources/<name>.jsonl (written by second_source.py), and for each capture records the
robots.txt and TDMRep files in effect, the captured X-Robots-Tag and TDM headers and the page's
robots/TDM meta tags (archive_debugger.sources.signals), each with the capture it came from. Writes
data/sources/signals-<name>.jsonl and, for any capture where a signal restricts AI use, a candidate
policy record in data/sources/signal-policy-candidates-<name>.jsonl for a person to review; the
governance register is never written here. The consent-ledger package is not installed, so the raw
robots.txt capture ids (timestamp and digest) are stored with each record. Staging data only.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.sources import signals  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="wayback-hc-tobacco")
    args = ap.parse_args(argv)
    src = REPO / "data" / "sources" / f"{args.name}.jsonl"
    reader = signals.SignalReader()
    rows, candidates = [], []
    for line in src.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        ts, url = rec["identifier"].split("/", 1)
        sig = signals.as_dict(reader.for_capture(url, ts))
        rows.append(sig)
        if sig["restricts_ai"]:
            candidates.append({"format": 1, "policy_id": f"candidate-{args.name}-{ts}", "targets": {"items": [], "collections": []},
                               "capture": rec["identifier"], "restrict": ["generate", "export"],
                               "authority": f"{sig['host']}, in its own published signals at capture {ts}",
                               "basis": "AI or TDM preference signals in effect at capture time (see signals file)",
                               "status": "candidate: a person decides whether this becomes a policy record"})
    out = REPO / "data" / "sources" / f"signals-{args.name}.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=True) + "\n" for r in rows), encoding="utf-8")
    cand = REPO / "data" / "sources" / f"signal-policy-candidates-{args.name}.jsonl"
    cand.write_text("".join(json.dumps(c, ensure_ascii=True) + "\n" for c in candidates), encoding="utf-8")
    print(json.dumps({"captures": len(rows),
                      "robots": dict(Counter(r["robots"]["state"] for r in rows)),
                      "tdmrep": dict(Counter(r["tdmrep"]["state"] for r in rows)),
                      "headers_found": sum(1 for r in rows if r["headers"]),
                      "meta_found": sum(1 for r in rows if r["meta"]),
                      "restricts_ai": dict(Counter(str(r["restricts_ai"]) for r in rows)),
                      "candidates": len(candidates)}, indent=1), f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
