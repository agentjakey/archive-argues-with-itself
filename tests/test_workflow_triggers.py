"""No workflow that reads a secret can be started by a pull request, from a fork or anywhere else.

Every workflow that names `secrets.` must be triggered only by workflow_dispatch, schedule or a push
to main (push events never come from forks), and never by pull_request or pull_request_target. The
workflows that do run on pull requests (ci.yml) must read no secrets at all. Branch triggers name
main only: work happens on main. Read as text (the repo has no YAML dependency).
"""
from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml"))
PR_EVENTS = ("pull_request", "pull_request_target")


def triggers(text: str) -> list:
    """The event names under the top-level `on:` (block form or the inline list form)."""
    inline = re.search(r"^on:\s*\[(.*)\]\s*$", text, re.M)
    if inline:
        return [e.strip() for e in inline.group(1).split(",")]
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip() == "on:")
    events = []
    for line in lines[start + 1:]:
        if line and not line.startswith((" ", "#")):
            break
        m = re.match(r"^  ([a-z_]+):", line)
        if m:
            events.append(m.group(1))
    return events


def test_secret_reading_workflows_never_run_for_pull_requests():
    checked = 0
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        if "secrets." not in text:
            continue
        checked += 1
        events = triggers(text)
        assert not any(e in PR_EVENTS for e in events), f"{path.name} reads secrets and runs on {events}"
    assert checked >= 4


def test_pull_request_workflows_read_no_secrets():
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        if any(e in PR_EVENTS for e in triggers(text)):
            assert "secrets." not in text, f"{path.name} runs on pull requests and reads secrets"


def test_branch_triggers_name_main_only():
    for path in WORKFLOWS:
        for m in re.finditer(r"branches:\s*\[([^\]]*)\]", path.read_text(encoding="utf-8")):
            assert [b.strip().strip("'\"") for b in m.group(1).split(",")] == ["main"], path.name
