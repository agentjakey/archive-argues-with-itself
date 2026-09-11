#!/bin/sh
# Boot: make sure the two data files are under the data dir and match the published
# checksums (downloading from DATA_RELEASE_URL with resume when they are absent),
# then serve. Progress is logged every 100 MB. See docs/DEPLOY.md.
set -eu

python -m archive_debugger.data_release

mkdir -p "$(dirname "$CIVIC_CACHE_PATH")"
exec uvicorn archive_debugger.api.app:app --host 0.0.0.0 --port "${PORT:-8080}"
