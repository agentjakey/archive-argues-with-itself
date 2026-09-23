"""Scope registry and scope-by-name resolution (additive layer over the existing
config + env loading).

A scope selects a topic/dataset by NAME and binds it to its own config file and its
own civic.db / vectors.db paths, replacing the CIVIC_DB_PATH / CIVIC_INDEX_PATH env
juggling. The frozen pilot is the DEFAULT scope: it is marked inherit, so it resolves
its data paths through the existing config + env loading exactly as the no-scope
default and the festival deploy do. Every other scope declares explicit paths in the
registry, ignores the CIVIC_* env overrides, and is fenced: while such a scope is
active, connecting to any database outside that scope's own paths raises.

Design contract:
  - No scope active  -> active_scope() is None -> resolution and connect run verbatim
    as before (byte-identical to the no-scope default).
  - inherit scope active (pilot) -> resolution stays legacy (env honored); no fence.
  - non-inherit scope active (microlog, education, ...) -> resolution returns the
    scope's registry paths (env IGNORED) and the fence forbids opening any other db.

The registry lives at config/scopes.toml. See that file for the format.
"""

from __future__ import annotations

import os
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

REGISTRY_PATH = Path("config/scopes.toml")


class ScopeError(Exception):
    """A scope could not be resolved (unknown name, bad registry, path drift)."""


class ScopeViolation(ScopeError):
    """A fenced (non-inherit) scope tried to open a database outside its own paths."""


@dataclass(frozen=True)
class Scope:
    name: str
    config_path: Path
    db_path: Path
    index_path: Path
    cache_dir: Path
    inherit: bool

    # Working directories for a build of this scope, derived from the db path's parent
    # so harvest output, OCR cache, and reports all live under one isolated root. These
    # are only used for non-inherit scopes (the pilot is never rebuilt through here).
    @property
    def data_root(self) -> Path:
        return self.db_path.parent

    @property
    def harvest_dir(self) -> Path:
        return self.data_root / "harvest"

    @property
    def items_path(self) -> Path:
        return self.harvest_dir / "items.jsonl"

    @property
    def reports_dir(self) -> Path:
        return self.data_root / "reports"

    def allowed_db_paths(self) -> set[str]:
        """The only database paths a fenced run of this scope may open, normalized for
        the platform (case-insensitive on Windows)."""
        return {os.path.normcase(str(Path(p).resolve())) for p in (self.db_path, self.index_path)}


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def load_registry(registry_path: Optional[Path] = None) -> dict:
    path = Path(registry_path or REGISTRY_PATH)
    if not path.exists():
        raise ScopeError(f"scope registry not found at {path}")
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _config_declared_paths(config_path: Path) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(db_path, index_path, cache_dir) as literally declared in a scope's config file,
    with no env override applied. Used to keep the registry and the config in agreement."""
    with Path(config_path).open("rb") as fh:
        raw = tomllib.load(fh)
    db_path = raw.get("index", {}).get("db_path")
    index_path = raw.get("retrieve", {}).get("index_path")
    cache_dir = raw.get("harvest", {}).get("cache_dir")
    return db_path, index_path, cache_dir


def resolve_scope(name: str, *, registry_path: Optional[Path] = None) -> Scope:
    """Look a scope up by name and return its fully resolved paths.

    For an inherit scope (the pilot) the data paths come from the existing env-honoring
    loaders, so the result matches the no-scope default and the deploy. For any other
    scope the paths come from the registry, the CIVIC_* env is ignored, and the registry
    paths are checked against the scope config so the two can never silently drift.
    """
    registry = load_registry(registry_path)
    scopes_table = registry.get("scopes", {})
    if name not in scopes_table:
        known = ", ".join(sorted(scopes_table)) or "(none)"
        raise ScopeError(f"unknown scope {name!r}; registered scopes: {known}")
    entry = scopes_table[name]
    config_path = Path(entry["config"])
    if not config_path.exists():
        raise ScopeError(f"scope {name!r} points at missing config {config_path}")

    default_name = registry.get("default")
    inherit = bool(entry.get("inherit", False)) or name == default_name

    cfg_db, cfg_index, cfg_cache = _config_declared_paths(config_path)
    cache_dir = Path(entry.get("cache_dir") or cfg_cache or "raw")

    if inherit:
        # Resolve exactly as the no-scope default and the festival deploy: config + env.
        # No scope is active at this point, so these loaders take their legacy path.
        from archive_debugger.ingest.db import resolve_db_path
        from archive_debugger.retrieve.config import load_retrieve_config

        db_path = Path(resolve_db_path(config_path))
        index_path = Path(load_retrieve_config(config_path).index_path)
        return Scope(name=name, config_path=config_path, db_path=db_path,
                     index_path=index_path, cache_dir=cache_dir, inherit=True)

    # Fenced scope: registry paths are authoritative and the env is ignored.
    db_path = Path(entry.get("db_path") or cfg_db or "")
    index_path = Path(entry.get("index_path") or cfg_index or "")
    if not str(db_path) or not str(index_path):
        raise ScopeError(f"scope {name!r} must declare db_path and index_path in the registry")

    # Drift guard: if the config also declares these, they must agree with the registry,
    # so a scoped build cannot land its data somewhere the config disowns.
    if cfg_db is not None and Path(cfg_db) != db_path:
        raise ScopeError(f"scope {name!r} db_path {db_path} disagrees with {config_path} [index].db_path {cfg_db}")
    if cfg_index is not None and Path(cfg_index) != index_path:
        raise ScopeError(f"scope {name!r} index_path {index_path} disagrees with {config_path} [retrieve].index_path {cfg_index}")

    return Scope(name=name, config_path=config_path, db_path=db_path,
                 index_path=index_path, cache_dir=cache_dir, inherit=False)


def registered_scopes(registry_path: Optional[Path] = None) -> list[str]:
    return sorted(load_registry(registry_path).get("scopes", {}))


def parse_enabled_scopes(raw: Optional[str]) -> Optional[set]:
    """CIVIC_ENABLED_SCOPES -> the set of scopes a deployment exposes, or None (all scopes). A scope
    not enabled is never built, served, or listed by /scopes, so a pilot-only deploy cannot advertise
    a scope it has no data for. The base/default scope is always served (a process must serve one).
    Lives here (not in the api layer) so the boot provisioner can share it without importing the app."""
    if not raw:
        return None
    names = {s.strip() for s in raw.split(",") if s.strip()}
    return names or None


# --------------------------------------------------------------------------- #
# Active scope + fence
# --------------------------------------------------------------------------- #

# A process builds or serves exactly one scope at a time. This is a process-wide global
# (not thread-local) on purpose: the read-only server opens its one connection on a
# startup thread and serves requests from a threadpool, and the fence must hold across
# both. Nesting is handled by save/restore in activate(), and set_active() lets the
# server pin a scope for its whole lifetime.
_ACTIVE: Optional[Scope] = None


def active_scope() -> Optional[Scope]:
    return _ACTIVE


def set_active(scope: Optional[Scope]) -> None:
    """Pin the active scope for the rest of the process (used by the long-lived server).
    Prefer activate() for bounded work."""
    global _ACTIVE
    _ACTIVE = scope


@contextmanager
def activate(scope: Optional[Scope]) -> Iterator[Optional[Scope]]:
    """Make `scope` the active scope for the duration of the block. Passing None is a
    no-op that keeps the legacy (no-scope) behavior, so callers can always wrap their
    body in `with activate(scope):` whether or not a scope was requested."""
    global _ACTIVE
    previous = _ACTIVE
    _ACTIVE = scope
    try:
        yield scope
    finally:
        _ACTIVE = previous


def guard_path(db_path) -> None:
    """Fence for database opens. A no-op unless a non-inherit scope is active; then the
    path being opened must be one of that scope's own database paths, or ScopeViolation
    is raised. This makes a fenced build physically unable to open or write another
    scope's databases, especially the pilot's."""
    scope = active_scope()
    if scope is None or scope.inherit:
        return
    resolved = os.path.normcase(str(Path(db_path).resolve()))
    if resolved not in scope.allowed_db_paths():
        raise ScopeViolation(
            f"scope {scope.name!r} may only open its own databases "
            f"({scope.db_path}, {scope.index_path}); refused to open {db_path}"
        )


# --------------------------------------------------------------------------- #
# CLI helpers
# --------------------------------------------------------------------------- #


def add_scope_argument(parser) -> None:
    """Add the optional --scope flag to a stage's argument parser. With no --scope the
    stage behaves exactly as before (the default pilot corpus)."""
    parser.add_argument(
        "--scope",
        default=None,
        help="build/serve a named scope from config/scopes.toml (default: the pilot, "
             "resolved exactly as today). A non-default scope uses only its own db paths.",
    )
