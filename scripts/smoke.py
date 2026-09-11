"""Smoke test for a running API: /health, /examples, one GET /ask with provider=stub,
one /coverage. Standard library only. Exit 0 when every check passes, 1 otherwise.

    python scripts/smoke.py http://127.0.0.1:8000
    python scripts/smoke.py https://archive-argues-with-itself.fly.dev

provider=stub means no model is called and no key is needed; the check covers
retrieval, the answer shape, the trail, and the coverage view."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 300


def get(base: str, path: str) -> tuple[int, object, float]:
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(base + path, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), time.perf_counter() - t0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body, time.perf_counter() - t0
    except (urllib.error.URLError, TimeoutError, OSError) as exc:   # unreachable, refused, or timed out
        return 0, f"{type(exc).__name__}: {exc}", time.perf_counter() - t0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python scripts/smoke.py BASE_URL")
        return 2
    base = argv[0].rstrip("/")
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{'ok  ' if ok else 'FAIL'} {name}{(': ' + detail) if detail else ''}")
        if not ok:
            failures.append(name)

    status, health, dt = get(base, "/health")
    check("/health status 200", status == 200, f"{status} in {dt:.1f}s")
    corpus = health.get("corpus", {}) if isinstance(health, dict) else {}
    check("/health reports a corpus", isinstance(corpus.get("items"), int) and corpus["items"] > 0,
          f"items={corpus.get('items')} passages={corpus.get('passages')} pilot_window={corpus.get('pilot_window')}")

    status, examples, dt = get(base, "/examples")
    check("/examples status 200", status == 200, f"{status} in {dt:.1f}s")
    check("/examples is a non-empty list with qid and text",
          isinstance(examples, list) and len(examples) > 0 and all("qid" in e and "text" in e for e in examples),
          f"{len(examples) if isinstance(examples, list) else 'n/a'} questions")
    question = examples[0]["text"] if isinstance(examples, list) and examples else "vaccination hospital"

    params = urllib.parse.urlencode({"q": question, "provider": "stub", "nocache": 1})
    status, ask, dt = get(base, f"/ask?{params}")
    check("GET /ask (stub) status 200", status == 200, f"{status} in {dt:.1f}s")
    if isinstance(ask, dict):
        answer, evidence = ask.get("answer", {}), ask.get("evidence", [])
        check("/ask answer has coverage and abstained flag",
              isinstance(answer, dict) and "abstained" in answer and "coverage" in answer)
        check("/ask returns an evidence trail", isinstance(evidence, list) and len(evidence) > 0,
              f"{len(evidence)} rows, {sum(1 for e in evidence if e.get('in_prompt'))} sent to the model")
        check("/ask evidence rows carry page-level deep links",
              all(isinstance(e.get("deep_link"), str) and "/page/n" in e["deep_link"] for e in evidence))
    else:
        check("/ask returned JSON", False, str(ask)[:200])

    params = urllib.parse.urlencode({"q": question})
    status, cov, dt = get(base, f"/coverage?{params}")
    check("/coverage status 200", status == 200, f"{status} in {dt:.1f}s")
    check("/coverage has salient terms and decade rows",
          isinstance(cov, dict) and isinstance(cov.get("salient_terms"), list) and len(cov.get("by_decade", [])) >= 6,
          f"terms={cov.get('salient_terms') if isinstance(cov, dict) else 'n/a'}")

    print(f"\n{len(failures)} failure(s)" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
