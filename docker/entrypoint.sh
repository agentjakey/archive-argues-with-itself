#!/bin/sh
# Wait for the data files on the volume, then serve. The API opens civic.db and
# vectors.db read-only at startup, so a first deploy before the upload would
# crash-loop; waiting keeps the machine up for `fly sftp`.
set -eu

until [ -f "$CIVIC_DB_PATH" ] && [ -f "$CIVIC_INDEX_PATH" ]; do
  echo "waiting for $CIVIC_DB_PATH and $CIVIC_INDEX_PATH (see docs/DEPLOY.md)"
  sleep 30
done

mkdir -p "$(dirname "$CIVIC_CACHE_PATH")"
exec uvicorn archive_debugger.api.app:app --host 0.0.0.0 --port "${PORT:-8080}"
