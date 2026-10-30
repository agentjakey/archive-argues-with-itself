"""Build the engine image with the release's data inside (provisioning option "image").

1. Builds the serving image from the repo Dockerfile (tag archive-engine:local), unless --base is
   given.
2. Stages the corpus databases and the dense artifacts in the container's /data layout, as hard
   links where the filesystem allows (copies otherwise), and checks every staged file against the
   sha256 in config/scopes.toml. A file that does not match stops the build.
3. Builds docker/Dockerfile.baked with the staging folder as the named build context "data".

The vectors databases are not included: with the numpy backend the boot writes a small stand-in
index and the dense leg comes from the artifacts (retrieve/dense.py, provision.py).

Pushing the image to Cloudflare's registry is an account step (docs/v2/HOSTING.md):
    npx wrangler containers push archive-engine-baked:<tag>

    python scripts/v2/build_baked_image.py --src C:/civic-measure/src --tag 2026-10-30.1
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

def run(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=REPO)


def stage(src: Path, dest: Path) -> None:
    """Every release file except the vectors databases (the numpy backend uses the artifacts), from
    the scope registry, linked into dest in the /data layout and checked against its sha256."""
    sys.path.insert(0, str(REPO / "src"))
    from archive_debugger import release_files
    from archive_debugger.retrieve.dense import file_sha256
    for f in release_files.all_files():
        if f.kind == "index":
            continue
        source, target = f.path(src), f.path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, target)
        except OSError:
            shutil.copyfile(source, target)
        actual = file_sha256(target)
        if actual != f.sha256:
            raise SystemExit(f"{f.relative}: sha256 {actual[:16]}... is not the published {f.sha256[:16]}...; not building")
        print(f"verified {f.relative}", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", required=True, type=Path, help="folder with the verified data, laid out as LAYOUT")
    parser.add_argument("--tag", required=True, help="release tag for the image")
    parser.add_argument("--base", default=None, help="an existing serving image to build on")
    args = parser.parse_args(argv)
    base = args.base or "archive-engine:local"
    if args.base is None:
        run(["docker", "build", "-t", base, "."])
    with tempfile.TemporaryDirectory(prefix="baked-data-", dir=args.src.parent) as tmp:
        stage(args.src, Path(tmp))
        run(["docker", "build", "-f", "docker/Dockerfile.baked", "--build-arg", f"BASE_IMAGE={base}",
             "--build-context", f"data={tmp}", "-t", f"archive-engine-baked:{args.tag}", "."])
    print(f"built archive-engine-baked:{args.tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
