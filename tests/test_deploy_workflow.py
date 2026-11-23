"""The deploy workflow deploys only on a manual run: no branch push and no release tag deploys.

Read as text (the repo has no YAML dependency): the top-level `on:` block and the guard on the first
job, which every deploying job needs.
"""
from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml"


def _top_level_block(text: str, key: str) -> list[str]:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip() == f"{key}:")
    block = []
    for line in lines[start + 1:]:
        if line and not line.startswith((" ", "#")):
            break
        block.append(line)
    return block


def _job_block(text: str, job: str) -> list[str]:
    jobs = _top_level_block(text, "jobs")
    start = next(i for i, line in enumerate(jobs) if line.rstrip() == f"  {job}:")
    block = []
    for line in jobs[start + 1:]:
        if re.match(r"^  \S", line):
            break
        block.append(line)
    return block


def test_triggers_are_manual_runs_only():
    text = WORKFLOW.read_text(encoding="utf-8")
    on = [line.split("#")[0].rstrip() for line in _top_level_block(text, "on")]
    on = [line for line in on if line.strip()]
    events = [line.strip().rstrip(":") for line in on if re.match(r"^  \S", line)]
    assert events == ["workflow_dispatch"]
    assert not any("branches" in line or "tags" in line for line in on)


def test_every_deploying_job_sits_behind_the_guard():
    text = WORKFLOW.read_text(encoding="utf-8")
    guard = [line.strip() for line in _job_block(text, "test") if line.strip().startswith("if:")]
    assert guard == ["if: ${{ github.event_name == 'workflow_dispatch' }}"]
    for job in ("site", "engine"):
        assert "    needs: test" in _job_block(text, job)


def test_production_needs_main_and_a_typed_confirmation_and_defaults_are_safe():
    text = WORKFLOW.read_text(encoding="utf-8")
    test_job = "\n".join(_job_block(text, "test"))
    # the production check is the first step of the job every deploying job needs
    first_step = test_job.split("      - ", 2)[1]
    assert "production needs main" in first_step
    assert '"$GITHUB_REF" != "refs/heads/main"' in first_step
    assert '"$CONFIRM" != "deploy production"' in first_step
    # nothing falls back to production, and the default target leaves the laptop-published site alone
    assert "|| 'production'" not in text
    assert "default: engine" in "\n".join(_top_level_block(text, "on"))


def test_the_workflow_runs_the_same_wrangler_as_the_workers_lockfiles():
    import json
    text = WORKFLOW.read_text(encoding="utf-8")
    pinned = set(re.findall(r'wranglerVersion: "([^"]+)"', text))
    root = WORKFLOW.parents[2]
    for pkg in ("worker/engine/package.json", "worker/site/package.json"):
        assert pinned == {json.loads((root / pkg).read_text(encoding="utf-8"))["devDependencies"]["wrangler"]}
