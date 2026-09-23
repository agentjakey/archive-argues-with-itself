#!/bin/sh
# Boot: provision each ENABLED scope's data files onto its volume paths from the scope's
# configured source (Cloudflare R2, or the GitHub release as a fallback), verify their sha256
# (config/scopes.toml), and only then serve. A missing R2 cred/object or a checksum mismatch
# exits non-zero, so the container never serves half-provisioned. Progress is logged every
# 100 MB. See docs/deploy.md.
set -eu

python -m archive_debugger.boot

mkdir -p "$(dirname "$CIVIC_CACHE_PATH")"
exec uvicorn archive_debugger.api.app:app --host 0.0.0.0 --port "${PORT:-8080}"
