"""Every file a scope's release consists of, from the scope registry (config/scopes.toml) alone.

A collection is added by config plus data: its registry entry names its R2 keys and published
sha256, and its `release_dir`, the folder that holds its files under the data root (the
container's /data, or a local folder of verified copies). From those, one rule places every file:

    <release_dir>/<database file>                         the corpus database          (kind db)
    <release_dir>/index/<vectors file>                    the vectors database         (kind index)
    <release_dir>/index/dense/<vectors stem>.matrix.npy   dense artifacts, when published
    <release_dir>/index/dense/<vectors stem>.ids.npy
    <release_dir>/index/dense/<vectors stem>.dense.json
    <release_dir>/<database stem>.facts.json              precomputed corpus facts, when published

The boot, the R2 stand-in, the artifact upload, the baked image, the parity check and the engine
Worker's allow list all read this module, so none of them names a scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from archive_debugger import scopes


@dataclass(frozen=True)
class ReleaseFile:
    scope: str
    kind: str            # db, index, dense_matrix, dense_ids, dense_manifest, facts
    key: str             # R2 object key
    sha256: str
    relative: str        # path under the data root, POSIX form

    def path(self, root: Path) -> Path:
        return Path(root) / PurePosixPath(self.relative)


class ReleaseError(ValueError):
    """The registry does not describe a scope's release completely."""


def scope_names(registry: Optional[dict] = None) -> list[str]:
    reg = registry if registry is not None else scopes.load_registry()
    return list((reg.get("scopes") or {}).keys())


def _entry(scope: str, registry: dict) -> dict:
    entry = (registry.get("scopes") or {}).get(scope)
    if not entry:
        raise ReleaseError(f"scope {scope!r} is not in config/scopes.toml")
    return entry


def scope_files(scope: str, registry: Optional[dict] = None) -> list[ReleaseFile]:
    """Every published file of one scope, in a fixed order (db, index, dense, facts)."""
    reg = registry if registry is not None else scopes.load_registry()
    entry = _entry(scope, reg)
    r2 = entry.get("r2") or {}
    for name in ("db_key", "db_sha256", "index_key", "index_sha256"):
        if not r2.get(name):
            raise ReleaseError(f"[{scope}] config/scopes.toml has no r2.{name}")
    base = PurePosixPath(str(entry.get("release_dir") or "").strip("/"))
    db_name = PurePosixPath(r2["db_key"]).name
    index_name = PurePosixPath(r2["index_key"]).name
    index_stem = PurePosixPath(index_name).stem
    out = [
        ReleaseFile(scope, "db", r2["db_key"], r2["db_sha256"].lower(), str(base / db_name)),
        ReleaseFile(scope, "index", r2["index_key"], r2["index_sha256"].lower(), str(base / "index" / index_name)),
    ]
    dense = entry.get("dense") or {}
    for part, suffix in (("matrix", ".matrix.npy"), ("ids", ".ids.npy"), ("manifest", ".dense.json")):
        if dense.get(f"{part}_key"):
            out.append(ReleaseFile(scope, f"dense_{part}", dense[f"{part}_key"], dense[f"{part}_sha256"].lower(),
                                   str(base / "index" / "dense" / f"{index_stem}{suffix}")))
    facts = entry.get("facts") or {}
    if facts.get("key"):
        out.append(ReleaseFile(scope, "facts", facts["key"], facts["sha256"].lower(),
                               str(base / f"{PurePosixPath(db_name).stem}.facts.json")))
    return out


def all_files(registry: Optional[dict] = None) -> list[ReleaseFile]:
    reg = registry if registry is not None else scopes.load_registry()
    return [f for name in scope_names(reg) for f in scope_files(name, reg)]


def facts_path(db_file: Path) -> Path:
    """Where a corpus database's precomputed facts sit: beside it, named after it."""
    return Path(db_file).with_name(Path(db_file).stem + ".facts.json")


def curated_files(scope: str, registry: Optional[dict] = None) -> tuple[Optional[Path], Optional[Path]]:
    """A scope's seed questions file and stories file, from its registry entry (None when unset)."""
    reg = registry if registry is not None else scopes.load_registry()
    entry = _entry(scope, reg)
    seed = Path(entry["seed"]) if entry.get("seed") else None
    stories = Path(entry["stories"]) if entry.get("stories") else None
    return seed, stories


def path_env_names(scope: str, registry: Optional[dict] = None) -> tuple[str, str]:
    """The environment variables that relocate a scope's database and vectors database: CIVIC_* for
    the inherit (default) scope, <NAME>_DB_PATH and <NAME>_INDEX_PATH for any other (scopes.py)."""
    reg = registry if registry is not None else scopes.load_registry()
    if _entry(scope, reg).get("inherit"):
        return "CIVIC_DB_PATH", "CIVIC_INDEX_PATH"
    base = "".join(ch if ch.isalnum() else "_" for ch in scope).upper()     # the same rule as scopes.py
    return f"{base}_DB_PATH", f"{base}_INDEX_PATH"
