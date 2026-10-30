"""Summarize the cold-boot measurement runs into Markdown tables.

Reads every reports/v2/raw/boot/*.json written by scripts/v2/measure_boot.py and prints:
  1. one row per run: outcome, seconds per step, empty disk to /health 200;
  2. one row per run: memory per step (peak anonymous memory, peak cgroup memory.current,
     peak file_mapped, peak process RSS) and the steady state after the asks.
Memory is in MiB (2^20 bytes). A run that did not finish shows what it reached.

    python scripts/v2/summarize_boot.py [--dir reports/v2/raw/boot] [--match TEXT]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MIB = 2 ** 20


def mib(value) -> str:
    return "" if value is None else f"{value / MIB:,.0f}"


def load_runs(directory: Path, match: str) -> list[dict]:
    runs = []
    for path in sorted(directory.glob("*.json")):
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if match in run.get("label", path.stem):
            runs.append(run)
    return runs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", default="reports/v2/raw/boot")
    parser.add_argument("--match", default="")
    args = parser.parse_args(argv)
    runs = load_runs(Path(args.dir), args.match)
    if not runs:
        print("no runs found", file=sys.stderr)
        return 1

    print("| run | limit MiB | ok | fetch s | verify s | listen s | warm s | to /health 200 s | asks (degraded) | median ask s |")
    print("| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for run in runs:
        steps = {s["step"]: s for s in run.get("steps", [])}
        asks = steps.get("asks", {})
        print("| {label} | {limit} | {ok} | {fetch} | {verify} | {listen} | {warm} | {total} | {asks} | {median} |".format(
            label=run.get("label"), limit=mib(run.get("memory_max")), ok="yes" if run.get("ok") else "NO",
            fetch=steps.get("fetch", {}).get("seconds", ""), verify=steps.get("verify", {}).get("seconds", ""),
            listen=steps.get("listen", {}).get("seconds", ""), warm=steps.get("warm", {}).get("seconds", ""),
            total=run.get("total_seconds_to_ready") or "",
            asks=f"{asks.get('asks', '')} ({asks.get('degraded', '')})" if asks else "",
            median=asks.get("latency_median", "")))
    print()
    print("| run | step | seconds | peak anon | peak memory.current | peak file_mapped | peak RSS | memory.peak at end | oom_kill |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for run in runs:
        for s in run.get("steps", []):
            peak = s.get("max", {})
            print(f"| {run.get('label')} | {s['step']} | {s.get('seconds')} | {mib(peak.get('anon'))} | "
                  f"{mib(peak.get('current'))} | {mib(peak.get('file_mapped'))} | {mib(peak.get('VmRSS'))} | "
                  f"{mib(s.get('memory_peak'))} | {s.get('oom_kill')} |")
    print()
    print("| run | steady anon | steady memory.current | steady RSS | data files bytes | volume used bytes | error |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for run in runs:
        steady = next((s for s in run.get("steps", []) if s["step"] == "steady"), {})
        end = steady.get("end", {})
        disk = run.get("disk", {})
        print(f"| {run.get('label')} | {mib(end.get('anon'))} | {mib(end.get('current'))} | {mib(end.get('VmRSS'))} | "
              f"{disk.get('data_files_bytes', '')} | {disk.get('volume_used_bytes', '')} | {run.get('error', '')} |")
    print()
    print("| run | scope | uncached asks | retrieval ms median | retrieval ms max | outcomes | dense backend at warm |")
    print("| --- | --- | ---: | ---: | ---: | --- | --- |")
    for run in runs:
        log_path = Path(args.dir) / f"{run.get('label')}.server.log"
        for scope, row in ask_timings(log_path).items():
            values = sorted(row["retrieval_ms"])
            outcomes = ", ".join(f"{name} {count}" for name, count in sorted(row["outcomes"].items()))
            print(f"| {run.get('label')} | {scope} | {len(values)} | {values[len(values) // 2]} | {values[-1]} | "
                  f"{outcomes} | {row['dense']} |")
    return 0


def ask_timings(log_path: Path) -> dict:
    """Per scope, from the server's own log: the retrieval time and outcome of every /ask (the
    harness asks with the stub provider and nocache, so each one runs retrieval), and which dense
    backend the boot warm reported."""
    out: dict = {}
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        fields = dict(part.split("=", 1) for part in line.split() if "=" in part)
        scope = fields.get("scope")
        if not scope:
            continue
        row = out.setdefault(scope, {"retrieval_ms": [], "outcomes": {}, "dense": ""})
        if line.startswith("[ask-timing]"):
            row["retrieval_ms"].append(int(fields.get("retrieval_ms", 0)))
            outcome = fields.get("outcome", "")
            row["outcomes"][outcome] = row["outcomes"].get(outcome, 0) + 1
        elif line.startswith("[boot-warm]") and "dense=" in line:
            row["dense"] = "numpy" if "dense=numpy" in line else "sqlite-vec"
    return {scope: row for scope, row in out.items() if row["retrieval_ms"]}


if __name__ == "__main__":
    sys.exit(main())
