"""Prove the serve path on CPU: the v2 writer through an OpenAI-compatible server on this machine.

    python scripts/v2/serve_proof.py --base-url http://127.0.0.1:11434/v1 --model qwen2.5:7b-instruct

Takes questions and their retrieved evidence from the bounded run (data/bounded/bc_govpubs/
answers-bounded-1.json: the same passages the production writer saw), sends each through run A's
openai_compat writer (src/archive_debugger/generate/writers.py) with the v2 system prompt, and checks
that the reply is a valid Draft2 whose every cited id was in the evidence. Prints per question the
latency, the evidence state and the citation check. Local only, no paid call: a llama.cpp or Ollama
server is the CPU stand-in for the cluster's vLLM Deployment, which speaks the same API.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.generate import answer_v2, writers  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--answers", default=str(REPO / "data" / "bounded" / "bc_govpubs" / "answers-bounded-1.json"))
    ap.add_argument("--questions", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=600.0)
    args = ap.parse_args(argv)
    endpoint = writers.Endpoint(provider="openai_compat", base_url=args.base_url, key_env="SERVE_PROOF_KEY")
    writer = writers.OpenAICompatWriter(endpoint, args.model, 1200, timeout=args.timeout,
                                        env={"SERVE_PROOF_KEY": "local-no-key"})
    rows = []
    for a in json.loads(Path(args.answers).read_text(encoding="utf-8"))[: args.questions]:
        hits = a["evidence"][:8]
        ids = {h["passage_id"] for h in hits}
        started = time.time()
        try:
            draft = writer.draft(answer_v2.SYSTEM, answer_v2.build_user_prompt(a["question"], hits))
            cited = [c for s in draft.sentences for c in s.cited_ids]
            row = {"question": a["question"][:80], "seconds": round(time.time() - started, 1), "valid_draft2": True,
                   "sentences": len(draft.sentences), "evidence_state": draft.evidence_state,
                   "cited": len(cited), "cited_outside_evidence": sorted(set(cited) - ids)}
        except Exception as exc:          # a refused or malformed reply is a result, recorded as such
            row = {"question": a["question"][:80], "seconds": round(time.time() - started, 1), "valid_draft2": False,
                   "error": str(exc)[:300]}
        rows.append(row)
        print(json.dumps(row), flush=True)
    ok = all(r.get("valid_draft2") and not r.get("cited_outside_evidence") for r in rows)
    print(json.dumps({"model": args.model, "base_url": args.base_url, "questions": len(rows), "all_valid": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
