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

# Each file: (path under --src, path inside /data, scopes.toml scope, field holding its sha256).
LAYOUT = [
    ("civic.db", "civic.db", "pilot", ("r2", "db_sha256")),
    ("index/dense/vectors.matrix.npy", "index/dense/vectors.matrix.npy", "pilot", ("dense", "matrix_sha256")),
    ("index/dense/vectors.ids.npy", "index/dense/vectors.ids.npy", "pilot", ("dense", "ids_sha256")),
    ("index/dense/vectors.dense.json", "index/dense/vectors.dense.json", "pilot", ("dense", "manifest_sha256")),
    ("microlog/civic_microlog.db", "microlog/civic_microlog.db", "microlog", ("r2", "db_sha256")),
    ("microlog/index/dense/vectors_microlog.matrix.npy", "microlog/index/dense/vectors_microlog.matrix.npy", "microlog",
     ("dense", "matrix_sha256")),
    ("microlog/index/dense/vectors_microlog.ids.npy", "microlog/index/dense/vectors_microlog.ids.npy", "microlog",
     ("dense", "ids_sha256")),
    ("microlog/index/dense/vectors_microlog.dense.json", "microlog/index/dense/vectors_microlog.dense.json", "microlog",
     ("dense", "manifest_sha256")),
]


def run(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=REPO)


def stage(src: Path, dest: Path) -> None:
    sys.path.insert(0, str(REPO / "src"))
    from archive_debugger import scopes
    from archive_debugger.retrieve.dense import file_sha256
    registry = scopes.load_registry()
    for rel_src, rel_dest, scope, (block, field) in LAYOUT:
        source = src / rel_src
        target = dest / rel_dest
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, target)
        except OSError:
            shutil.copyfile(source, target)
        expected = registry["scopes"][scope][block][field].lower()
        actual = file_sha256(target)
        if actual != expected:
            raise SystemExit(f"{rel_src}: sha256 {actual[:16]}... is not the published {expected[:16]}...; not building")
        print(f"verified {rel_dest}", flush=True)


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
