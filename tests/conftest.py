"""Test-session guards. The CIVIC_* env overrides (and .env, which api.app loads at
import) must never redirect a test at the real database; every test starts with
them unset and sees only the paths it builds itself."""
from __future__ import annotations

import pytest

_ENV_OVERRIDES = ("CIVIC_DB_PATH", "CIVIC_INDEX_PATH", "CIVIC_CACHE_PATH")


@pytest.fixture(autouse=True)
def _no_data_path_overrides(monkeypatch):
    for var in _ENV_OVERRIDES:
        monkeypatch.delenv(var, raising=False)
