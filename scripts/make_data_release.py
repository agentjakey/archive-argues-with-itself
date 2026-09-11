"""Prepare the data release: sha256 checksums for civic.db and vectors.db written to
data-release.sha256, plus the exact `gh release create` command to publish both
files and the checksum file as release assets. Does not upload anything.

    python scripts/make_data_release.py [--tag data-v1] [--db PATH] [--index PATH] [--out data-release.sha256]

Paths default to the CIVIC_DB_PATH / CIVIC_INDEX_PATH env vars (loaded from .env),
then to config/pilot.toml. GitHub release assets are capped at 2 GiB each; the
script refuses files over that limit."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from archive_debugger.data_release import CHECKSUM_FILE, write_checksums

GITHUB_ASSET_LIMIT = 2 * 1024 ** 3


def main(argv=None) -> int:
    from dotenv import load_dotenv  # CLI only
    load_dotenv(".env")
    from archive_debugger.retrieve.config import load_retrieve_config
    cfg = load_retrieve_config(Path("config/pilot.toml"))
    p = argparse.ArgumentParser(description="Write data-release.sha256 and print the gh release command.")
    p.add_argument("--tag", default="data-v1")
    p.add_argument("--db", default=cfg.db_path, type=Path)
    p.add_argument("--index", default=cfg.index_path, type=Path)
    p.add_argument("--out", default=Path(CHECKSUM_FILE), type=Path)
    p.add_argument("--repo", default="agentjakey/archive-argues-with-itself")
    args = p.parse_args(argv)

    files = {"civic.db": args.db, "vectors.db": args.index}
    for name, path in files.items():
        if not Path(path).exists():
            print(f"missing {name}: {path}")
            return 2
        size = Path(path).stat().st_size
        if size > GITHUB_ASSET_LIMIT:
            print(f"{name} is {size:,} bytes, over the 2 GiB GitHub release asset limit; split or host elsewhere")
            return 2
    text = write_checksums(files, args.out)
    print(f"\nwrote {args.out}:\n{text}")
    sizes = ", ".join(f"{n} {Path(pth).stat().st_size:,} bytes" for n, pth in files.items())
    print("publish with (one-time; the tag is created on the current commit):\n")
    print(f'gh release create {args.tag} "{args.db}#civic.db" "{args.index}#vectors.db" "{args.out}" '
          f'--repo {args.repo} --title "Corpus data {args.tag}" '
          f'--notes "civic.db and vectors.db for the public_health pilot ({sizes}). '
          f'Verify with: sha256sum -c {CHECKSUM_FILE}"')
    print(f"\nthen set DATA_RELEASE_URL=https://github.com/{args.repo}/releases/download/{args.tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
