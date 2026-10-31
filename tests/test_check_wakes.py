"""scripts/v2/check_wakes.py flags every finished wake that did not end in "slept: idle"."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _module():
    spec = importlib.util.spec_from_file_location("check_wakes", REPO / "scripts" / "v2" / "check_wakes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wake(name, started, exit_reason, mode="snapshot-restore", check=None):
    return {"release": "2026-10-31.1", "name": name, "mode": mode, "instance": "standard-2",
            "started_at": started, "port_open_seconds": 1.2, "ready_seconds": 24.5,
            "provision": None, "snapshot_check": check, "exit": exit_reason}


def test_only_unclean_finished_wakes_are_flagged():
    mod = _module()
    health = {"status": "waking", "release": "2026-10-31.1",
              "engines": [{"name": "pilot", "status": "ready", "error": None},
                          {"name": "microlog", "status": "asleep", "error": "snapshot check failed: x"}],
              "wakes": [_wake("pilot", "2026-10-31T10:00:00Z", "slept: idle", check="passed"),
                        _wake("microlog", "2026-10-31T09:00:00Z", "snapshot check failed: snapshot dropped", check="failed"),
                        _wake("microlog", "2026-10-31T11:00:00Z", "exited: out of memory", mode="r2-download"),
                        _wake("pilot", "2026-10-31T12:00:00Z", None, check="running")]}
    lines, flagged = mod.review(health)
    assert flagged == 2
    rows = [line for line in lines if line.startswith("  ") and "T" in line and "Z" in line]
    assert [row.split()[0] for row in rows] == ["FLAG", "ok", "FLAG", "OPEN"]     # oldest first
    assert "error: snapshot check failed: x" in "\n".join(lines)
    assert lines[-1] == "2 flagged"


def test_nothing_flagged_when_every_wake_slept_idle():
    mod = _module()
    lines, flagged = mod.review({"status": "asleep", "release": "r", "engines": [],
                                 "wakes": [_wake("pilot", "2026-10-31T10:00:00Z", "slept: idle")]})
    assert flagged == 0
    assert lines[-1].startswith("nothing flagged")
    lines, flagged = mod.review({"status": "asleep", "release": "r", "engines": []})
    assert flagged == 0 and "0 wakes" in lines
