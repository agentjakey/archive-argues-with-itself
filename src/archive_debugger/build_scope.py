"""One-command scope builder.

Runs the full build pipeline for a NAMED scope, in sequence:

    harvest -> loader -> build -> normalize -> sections -> embed

Every stage resolves its paths from the scope registry (config/scopes.toml), every
stage is resumable (rerun the command to continue), and the scope is fenced for the
whole run so it can only touch its own databases, never another scope's, especially
the pilot's. Output is structured status only (stage, counts, completeness/alignment,
pass/fail); no raw document or passage content is ever printed.

    python -m archive_debugger.build_scope --scope microlog --contact you@example.com

The pilot is the frozen DEFAULT scope and is never built through here (this refuses to
run against an inherit scope). A bounded dry run proves the chaining without a full
crawl:

    python -m archive_debugger.build_scope --scope microlog --contact you@example.com --dry-run 25

Resuming after a stop: rerun the same command. Harvest resumes from its download
checkpoint, build skips items already parsed (--resume), normalize/sections recompute,
and embed skips passages already vectorized.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from archive_debugger import scopes
from archive_debugger.harvest import fetch
from archive_debugger.ingest import build as build_mod
from archive_debugger.ingest import db, loader, normalize, sections
from archive_debugger.retrieve import index as index_mod
from archive_debugger.retrieve.config import load_retrieve_config
from archive_debugger.retrieve.embed import make_embedder

STAGES = ("harvest", "loader", "build", "normalize", "sections", "embed")


def _log(stage: str, status: str, detail: str = "") -> None:
    """Structured status line. Never carries document or passage text."""
    line = f"[{stage}] {status}"
    if detail:
        line += f"  {detail}"
    print(line, flush=True)


def _selected_stages(args) -> list[str]:
    stages = list(STAGES)
    if args.only:
        return [args.only]
    if args.from_stage:
        stages = stages[stages.index(args.from_stage):]
    if args.skip_embed and "embed" in stages:
        stages = [s for s in stages if s != "embed"]
    return stages


def run_harvest(scope: scopes.Scope, *, contact: str, dry: Optional[int], offline: bool) -> None:
    _log("harvest", "START", f"out={scope.harvest_dir} cache={scope.cache_dir} offline={offline}")
    summary = fetch.run(
        scope.config_path,
        scope.harvest_dir,
        contact=contact,
        do_download=(dry is None and not offline),
        download_sample=(dry if (dry is not None and not offline) else None),
        offline=offline,
    )
    _log("harvest", "OK",
         f"manifest={summary.get('manifest_count')} usable={summary.get('usable_count')} "
         f"floor={summary.get('usable_floor')} clears_floor={summary.get('clears_floor')}")


def run_loader(scope: scopes.Scope) -> None:
    _log("loader", "START", f"items={scope.items_path} db={scope.db_path}")
    if not scope.items_path.exists():
        raise FileNotFoundError(f"items file not found at {scope.items_path}; run the harvest stage first")
    conn = db.init_db(db.resolve_db_path(scope.config_path))
    try:
        count = loader.load_raw_items(conn, scope.items_path)
    finally:
        conn.close()
    _log("loader", "OK", f"items_loaded={count}")


def run_build(scope: scopes.Scope, *, dry: Optional[int]) -> None:
    _log("build", "START", f"cache={scope.cache_dir} db={scope.db_path}")
    conn = db.init_db(db.resolve_db_path(scope.config_path))
    try:
        records = build_mod._read_records(scope.items_path)
        stats = build_mod.build_corpus(conn, records, scope.cache_dir, limit=dry, resume=True)
    finally:
        conn.close()
    _log("build", "OK",
         f"items_parsed={stats['items_parsed']} skipped_done={stats['items_skipped_done']} "
         f"pending_download={stats['items_pending_download']} pages={stats['total_pages']} "
         f"passages={stats['total_passages']} alignment_risk={stats['alignment_risk']} "
         f"zero_text_items={stats['zero_usable_text_items']}")


def run_normalize(scope: scopes.Scope) -> None:
    out = scope.reports_dir / "phase5"
    _log("normalize", "START", f"db={scope.db_path} out={out}")
    result = normalize.run(scope.config_path, out)
    _log("normalize", "OK", f"items={result['items']} coverage_cells={result['coverage_cells']}")


def run_sections(scope: scopes.Scope, *, dry: Optional[int]) -> None:
    out = scope.reports_dir / "phase13"
    _log("sections", "START", f"db={scope.db_path} out={out}")
    result = sections.run(scope.config_path, out_dir=out, limit=dry)
    counts = result.get("counts", {})
    _log("sections", "OK",
         f"pages_walked={result.get('pages_walked')} "
         f"front={counts.get('front', 0)} body={counts.get('body', 0)} back={counts.get('back', 0)}")


def run_embed(scope: scopes.Scope, *, dry: Optional[int], limit_embed: Optional[int], embedder_override: Optional[str]) -> None:
    _log("embed", "START", f"db={scope.db_path} index={scope.index_path}")
    cfg = load_retrieve_config(scope.config_path, embedder_override=embedder_override)
    embedder = make_embedder(cfg.embedder, cfg.embedding_model, cfg.embedding_dim)
    limit = dry if dry is not None else limit_embed
    wrote = index_mod.build_index(cfg.db_path, cfg.index_path, embedder,
                                  model_id=cfg.embedding_model, batch_size=cfg.batch_size, limit=limit)
    import sqlite3
    conn = sqlite3.connect(str(cfg.index_path))
    total = conn.execute("SELECT COUNT(*) FROM passages_vec").fetchone()[0]
    conn.close()
    _log("embed", "OK", f"new_vectors={wrote} total_vectors={total}")


def build(scope_name: str, *, contact: str = "", dry: Optional[int] = None, offline: bool = False,
          from_stage: Optional[str] = None, only: Optional[str] = None, skip_embed: bool = False,
          limit_embed: Optional[int] = None, embedder_override: Optional[str] = None) -> int:
    scope = scopes.resolve_scope(scope_name)
    if scope.inherit:
        _log("build_scope", "REFUSED",
             f"scope {scope.name!r} is the frozen default (pilot); it is not built through this command")
        return 2

    args = argparse.Namespace(from_stage=from_stage, only=only, skip_embed=skip_embed)
    stages = _selected_stages(args)

    _log("build_scope", "START",
         f"scope={scope.name} config={scope.config_path} db={scope.db_path} index={scope.index_path} "
         f"stages={','.join(stages)}" + (f" dry_run={dry}" if dry is not None else ""))

    # Fail fast on a harvest that would hit the network without a contact.
    if "harvest" in stages and not offline:
        contact = contact or fetch.load_pilot(scope.config_path).contact
        if not contact:
            _log("build_scope", "REFUSED",
                 "harvest needs a contact for the User-Agent; pass --contact you@example.com or use --offline")
            return 2

    started = time.monotonic()
    with scopes.activate(scope):
        for name in stages:
            try:
                if name == "harvest":
                    run_harvest(scope, contact=contact, dry=dry, offline=offline)
                elif name == "loader":
                    run_loader(scope)
                elif name == "build":
                    run_build(scope, dry=dry)
                elif name == "normalize":
                    run_normalize(scope)
                elif name == "sections":
                    run_sections(scope, dry=dry)
                elif name == "embed":
                    run_embed(scope, dry=dry, limit_embed=limit_embed, embedder_override=embedder_override)
            except Exception as exc:  # noqa: BLE001 - report the failing stage and stop; rerun continues
                _log(name, "FAIL", f"{type(exc).__name__}: {exc}")
                _log("build_scope", "STOPPED", f"at {name} (rerun the same command to continue)")
                return 1

    elapsed = time.monotonic() - started
    _log("build_scope", "DONE", f"scope={scope.name} stages={len(stages)} ok elapsed={elapsed:.1f}s")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="One-command scope builder: harvest -> ingest -> embed for a named scope.")
    p.add_argument("--scope", required=True, help="scope name from config/scopes.toml (not the frozen default)")
    p.add_argument("--contact", default="", help="contact (email or URL) for the harvest User-Agent")
    p.add_argument("--dry-run", type=int, default=None, dest="dry",
                   help="bounded run: cap N items harvested/parsed/embedded to prove chaining without the full crawl")
    p.add_argument("--offline", action="store_true", help="harvest from cache only (no network); fail on cache miss")
    p.add_argument("--from", dest="from_stage", choices=STAGES, default=None, help="start at this stage")
    p.add_argument("--only", choices=STAGES, default=None, help="run only this stage")
    p.add_argument("--skip-embed", action="store_true", help="run everything except the (long) embed stage")
    p.add_argument("--limit-embed", type=int, default=None, help="cap NEW vectors this run (resumable batches)")
    p.add_argument("--embedder", default=None, help="override the embedder (e.g. stub for a fixture run)")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        return build(args.scope, contact=args.contact, dry=args.dry, offline=args.offline,
                     from_stage=args.from_stage, only=args.only, skip_embed=args.skip_embed,
                     limit_embed=args.limit_embed, embedder_override=args.embedder)
    except scopes.ScopeError as exc:
        _log("build_scope", "ERROR", str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
