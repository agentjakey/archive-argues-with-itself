"""Run the held-out questions once through a running API with its configured provider
and record, per question, whether the tool abstained or answered, against the gold
verdict in the file. Standard library only. Writes the machine summary to
reports/phase16/holdout_run.json and the human-readable report to
docs/evaluation/holdout_run.md. Cached answers are allowed (the API reads its cache first).

    python scripts/run_holdout.py http://127.0.0.1:8000 [--file eval/holdout_questions.jsonl]

The held-out file is never used in any sweep or design decision; this script only
reports what the frozen system did with it."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TIMEOUT = 600


def post(base: str, body: dict):
    req = urllib.request.Request(base + "/ask", data=json.dumps(body).encode("utf-8"),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("base_url")
    p.add_argument("--file", default=Path("eval/holdout_questions.jsonl"), type=Path)
    p.add_argument("--out", default=Path("reports/phase16"), type=Path)          # machine artifact (holdout_run.json)
    p.add_argument("--evidence", default=Path("docs/evaluation"), type=Path)     # human-readable report
    args = p.parse_args(argv)
    base = args.base_url.rstrip("/")
    rows = [json.loads(l) for l in args.file.read_text(encoding="utf-8").splitlines() if l.strip()]
    with urllib.request.urlopen(base + "/health", timeout=60) as resp:
        health = json.loads(resp.read().decode("utf-8"))
    results = []
    for q in rows:
        t0 = time.perf_counter()
        status, body = post(base, {"question": q["text"], "filters": q.get("filters") or {}})
        dt = round(time.perf_counter() - t0, 1)
        if status != 200 or not isinstance(body, dict):
            results.append({**q, "status": status, "error": str(body)[:200], "seconds": dt})
            print(f"{q['qid']}  FAIL {status}")
            continue
        ans = body["answer"]
        outcome = "abstained" if ans["abstained"] else "answered"
        results.append({**q, "status": 200, "outcome": outcome, "cached": bool(ans.get("cached")),
                        "abstention_text": ans.get("abstention_text"), "sentences": len(ans.get("sentences", [])),
                        "verified_citations": len(ans.get("verified_citations", [])),
                        "uncovered_terms": ans.get("coverage", {}).get("uncovered_terms"), "seconds": dt})
        print(f"{q['qid']}  gold={q['gold']:10} {outcome:9} {dt}s")
    abstain_gold = [r for r in results if r["gold"] == "abstain" and r.get("status") == 200]
    ans_gold = [r for r in results if r["gold"] == "answerable" and r.get("status") == 200]
    summary = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": health.get("provider"), "model": health.get("model"),
        "n": len(rows), "failed": sum(1 for r in results if r.get("status") != 200),
        "gold_abstain": {"n": len(abstain_gold), "abstained": sum(1 for r in abstain_gold if r["outcome"] == "abstained"),
                         "answered": [r["qid"] for r in abstain_gold if r["outcome"] == "answered"]},
        "gold_answerable": {"n": len(ans_gold), "answered": sum(1 for r in ans_gold if r["outcome"] == "answered"),
                            "abstained": [r["qid"] for r in ans_gold if r["outcome"] == "abstained"]},
        "results": results,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    args.evidence.mkdir(parents=True, exist_ok=True)
    (args.out / "holdout_run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    L = ["# Held-out run", "", f"{summary['ts']} (UTC); provider {summary['provider']}, model {summary['model']}; "
         f"{summary['n']} questions from `{args.file.as_posix()}`, one run, no sweep, no tuning.", "",
         f"- gold-abstain probes: {summary['gold_abstain']['abstained']}/{summary['gold_abstain']['n']} abstained"
         + (f"; answered: {', '.join(summary['gold_abstain']['answered'])}" if summary['gold_abstain']['answered'] else ""),
         f"- gold-answerable: {summary['gold_answerable']['answered']}/{summary['gold_answerable']['n']} answered"
         + (f"; abstained: {', '.join(summary['gold_answerable']['abstained'])}" if summary['gold_answerable']['abstained'] else ""),
         "", "| qid | gold | outcome | sentences | citations | uncovered terms | s |", "| --- | --- | --- | ---: | ---: | --- | ---: |"]
    for r in results:
        if r.get("status") != 200:
            L.append(f"| {r['qid']} | {r['gold']} | FAIL {r['status']} | | | | {r['seconds']} |")
        else:
            L.append(f"| {r['qid']} | {r['gold']} | {r['outcome']} | {r['sentences']} | {r['verified_citations']} | "
                     f"{', '.join(r['uncovered_terms'] or [])} | {r['seconds']} |")
    (args.evidence / "holdout_run.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
