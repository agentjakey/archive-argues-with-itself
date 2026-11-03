"""Check every link in the public docs: README, CHANGELOG, CONTRIBUTING, SECURITY and docs/**.

    python scripts/check_doc_links.py            # files and anchors in this repository only
    python scripts/check_doc_links.py --online   # also fetch every http(s) link once

A relative link must name a file or folder that exists; a link with #anchor into a Markdown file must
match one of its headings (GitHub's anchor rule: lower case, punctuation dropped, spaces to dashes).
Links into docs/v2 (private working notes) are refused. Prints one line per broken link and exits 1
when there is any."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)|!\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)


def public_docs() -> list:
    files = subprocess.run(["git", "ls-files", "*.md"], cwd=REPO, capture_output=True, text=True).stdout.split()
    keep = []
    for f in files:
        if f in ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md") or f.startswith("docs/"):
            keep.append(REPO / f)
    return keep


def anchor(text: str) -> str:
    text = re.sub(r"[`*_]", "", text.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set:
    return {anchor(h) for h in HEADING.findall(path.read_text(encoding="utf-8"))}


def check(online: bool) -> list:
    broken = []
    seen_urls: dict = {}
    for doc in public_docs():
        body = re.sub(r"```.*?```", "", doc.read_text(encoding="utf-8"), flags=re.DOTALL)
        for m in LINK.finditer(body):
            target = m.group(1) or m.group(2)
            where = f"{doc.relative_to(REPO).as_posix()}: {target}"
            if target.startswith(("http://", "https://")):
                if online:
                    if target not in seen_urls:
                        seen_urls[target] = fetch(target)
                    if seen_urls[target]:
                        broken.append(f"{where} ({seen_urls[target]})")
                continue
            if target.startswith(("mailto:", "#")):
                if target.startswith("#") and anchor(target[1:]) not in anchors(doc):
                    broken.append(f"{where} (no such heading)")
                continue
            path_part, _, frag = target.partition("#")
            dest = (doc.parent / path_part).resolve()
            if "docs/v2" in dest.as_posix():
                broken.append(f"{where} (links to the private docs/v2)")
            elif not dest.exists():
                broken.append(f"{where} (no such file)")
            elif frag and dest.suffix == ".md" and anchor(frag) not in anchors(dest):
                broken.append(f"{where} (no such heading)")
    return broken


def fetch(url: str) -> str:
    """'' when the link answers, else the reason."""
    req = urllib.request.Request(url, method="GET", headers={"user-agent": "archive-argues-link-check (hello@archiveargues.org)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:      # noqa: S310 - the docs' own links
            return "" if resp.status < 400 else f"HTTP {resp.status}"
    except Exception as exc:  # noqa: BLE001 - any failure is reported, not raised
        code = getattr(exc, "code", None)
        return f"HTTP {code}" if code else type(exc).__name__


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--online", action="store_true")
    args = ap.parse_args(argv)
    broken = check(args.online)
    for line in broken:
        print(line)
    print(f"{len(broken)} broken link(s)")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
