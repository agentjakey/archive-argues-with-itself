"""Build the normalized registry (docs/formats/registry.md) from files.

    python scripts/v2/registry.py build --catalogue data/catalogue/catalogue.jsonl.gz --indexed pilot,microlog
    python scripts/v2/registry.py stats

Writes data/registry/registry.db (gitignored). Rebuilding from the same files gives the same rows.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.registry import build  # noqa: E402

DB = REPO / "data" / "registry" / "registry.db"
REGISTER = REPO / "config" / "governance" / "policies.jsonl"


def stats(conn) -> dict:
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "documents": q("SELECT COUNT(*) FROM documents"),
        "collections": q("SELECT COUNT(*) FROM collections"),
        "coverage": {r[0]: r[1] for r in conn.execute("SELECT state, COUNT(DISTINCT doc_id) FROM coverage GROUP BY state")},
        "catalogue_dated": q("SELECT COUNT(*) FROM dates WHERE kind = 'catalogue' AND year IS NOT NULL"),
        "derived_dates": q("SELECT COUNT(*) FROM dates WHERE kind = 'derived'"),
        "jurisdictions": {r[0]: r[1] for r in conn.execute("SELECT jurisdiction, COUNT(*) FROM documents GROUP BY 1 ORDER BY 2 DESC")},
        "pages": q("SELECT COUNT(*) FROM pages"),
        "passages": q("SELECT COUNT(*) FROM passages"),
        "governed_documents": q("SELECT COUNT(DISTINCT doc_id) FROM governance"),
        "audit_events": q("SELECT COUNT(*) FROM audit_trail"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "stats", "rights", "pd-shelf"])
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--catalogue", type=Path, default=None)
    ap.add_argument("--source-collection", default="governmentpublications")
    ap.add_argument("--indexed", default="", help="collections (config/collections) to add as indexed corpora")
    ap.add_argument("--documents-only", action="store_true", help="indexed corpora: documents and coverage, not pages and passages")
    ap.add_argument("--fulltext", type=Path, default=None, help="the full-text fetch's manifest.jsonl: text versions and coverage")
    ap.add_argument("--served-shards", action="store_true",
                    help="mark the documents of every shard production serves (worker/engine/wrangler.jsonc production SHARDS, "
                         "members from data/shards/members.tsv) as indexed under that shard's scope")
    args = ap.parse_args(argv)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = build.open_registry(args.db)
    if args.command == "build":
        if args.catalogue:
            print("catalogue", build.add_catalogue(conn, build.read_catalogue(args.catalogue),
                                                    source_collection=args.source_collection))
        for name in [n for n in args.indexed.split(",") if n]:
            from archive_debugger.audit import collections
            from archive_debugger.audit.run import corpus_connection
            from archive_debugger.local_env import load_local_env
            load_local_env(log=None)
            coll = collections.load(name)
            print(name, build.add_indexed(conn, corpus_connection(coll), coll.scope,
                                               with_passages=not args.documents_only))
        if args.fulltext:
            n = 0
            for line in args.fulltext.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                text = (rec.get("files") or {}).get("searchtext") or (rec.get("files") or {}).get("djvu_txt")
                if rec.get("kind") in ("hocr", "searchtext_only", "djvu_txt") and text:
                    build.add_text(conn, rec["identifier"], store_key=text.get("r2_key") or "", sha256=text["sha256"],
                                   size=text["bytes"], source_url=f"https://archive.org/download/{rec['identifier']}/{text['name']}",
                                   page_breaks=rec["kind"] == "hocr" and "page_numbers" in rec["files"], fetched_at=rec["at"])
                    n += 1
            build.audit(conn, "add_text", str(args.fulltext), {"versions": n})
            conn.commit()
            print("fulltext", n)
        if args.served_shards:
            served = production_shards()
            members = REPO / "data" / "shards" / "members.tsv"
            n = 0
            import time
            seen = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            for line in members.read_text(encoding="utf-8").splitlines():
                did, _, shard = line.partition(chr(9))
                if shard in served:
                    conn.execute("INSERT OR IGNORE INTO coverage VALUES (?, 'indexed', ?, ?)", (did, shard, seen))
                    n += 1
            build.audit(conn, "add_served_shards", str(members), {"shards": sorted(served), "documents": n})
            conn.commit()
            print("served shards", sorted(served), n)
        print("governance", build.add_governance(conn, REGISTER))
    if args.command == "rights":
        from archive_debugger.registry import rights
        print(json.dumps(rights.apply(conn), indent=1))
        return 0
    if args.command == "pd-shelf":
        from archive_debugger.registry import rights
        per_page, source = measured_tokens_per_page()
        manifest = rights.pd_shelf_manifest(conn, per_page, source)
        out = REPO / "reports" / "v2" / "scale" / "pd_shelf_manifest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        print(json.dumps({k: manifest[k] for k in ("documents", "pages", "estimated_tokens", "tokens_per_page",
                                                   "tokens_per_page_source", "excluded")}), f"-> {out}")
        return 0
    print(json.dumps(stats(conn), indent=1))
    return 0


def production_shards() -> set:
    """The shard scopes production's engine Worker serves (its SHARDS variable), read from the config."""
    import re
    text = (REPO / "worker" / "engine" / "wrangler.jsonc").read_text(encoding="utf-8")
    production = text[text.index('"production"'):]
    value = re.search(r'"SHARDS":\s*"([^"]*)"', production).group(1)
    return {s.strip() for s in value.split(",") if s.strip()}


def measured_tokens_per_page(limit: int = 2000) -> tuple:
    """Tokens per page measured on fetched text (characters / 4 per page, over up to `limit` items
    with page indexes), or the rule's assumption when nothing is fetched yet."""
    import gzip
    from archive_debugger.registry import rights
    manifest = REPO / "data" / "fulltext" / "manifest.jsonl"
    chars = pages = items = 0
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if items >= limit:
                break
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            files = rec.get("files") or {}
            if rec.get("kind") != "hocr" or "pageindex" not in files:
                continue
            folder = REPO / "data" / "fulltext" / rec["identifier"][:2] / rec["identifier"]
            try:
                n = len(json.loads(gzip.decompress((folder / files["pageindex"]["name"]).read_bytes())))
                c = len(gzip.decompress((folder / files["searchtext"]["name"]).read_bytes()).decode("utf-8", "replace"))
            except OSError:
                continue
            chars, pages, items = chars + c, pages + n, items + 1
    if not pages:
        return rights.TOKENS_PER_PAGE, "assumed"
    return round(chars / pages / 4, 1), f"measured: characters / 4 over {pages:,} pages of {items:,} fetched items"


if __name__ == "__main__":
    sys.exit(main())
