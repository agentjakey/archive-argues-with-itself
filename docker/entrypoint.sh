#!/bin/sh
# Boot: provision each ENABLED scope's data files onto its volume paths from the scope's
# configured source (Cloudflare R2, or the GitHub release as a fallback), verify their sha256
# (config/scopes.toml), and only then serve. A missing R2 cred/object or a checksum mismatch
# exits non-zero, so the container never serves half-provisioned. Progress is logged every
# 100 MB. See docs/deploy.md.
set -eu

python -m archive_debugger.boot

# Optional index residency: copy the read-only data off the (slow) network volume into a faster
# local or tmpfs directory so the exact dense scan stays warm on a RAM-limited instance. Opt-in via
# CIVIC_RESIDENT_DIR; unset means a no-op and a byte-identical boot. cp -p preserves mtime, so the
# answer-cache fingerprint (which keys on file size and mtime) still matches and warmed answers keep
# hitting. A missing source, a failed copy, or a too-small target falls back to the volume path, so
# boot never breaks. Enable only when the instance has RAM/space for the enabled scopes' indexes.
if [ -n "${CIVIC_RESIDENT_DIR:-}" ]; then
    resident_copy() {  # $1=source path, $2=destination path, $3=env var name to re-point
        src="$1"; dest="$2"; var="$3"
        if [ -n "$src" ] && [ -f "$src" ]; then
            mkdir -p "$(dirname "$dest")" 2>/dev/null || true
            if cp -p "$src" "$dest" 2>/dev/null; then
                export "$var=$dest"
                echo "[resident] $var -> $dest"
            else
                echo "[resident] skip $var (copy failed); using $src"
            fi
        fi
        return 0
    }
    resident_copy "${CIVIC_DB_PATH:-}"       "$CIVIC_RESIDENT_DIR/civic.db"                           CIVIC_DB_PATH
    resident_copy "${CIVIC_INDEX_PATH:-}"    "$CIVIC_RESIDENT_DIR/index/vectors.db"                   CIVIC_INDEX_PATH
    resident_copy "${MICROLOG_DB_PATH:-}"    "$CIVIC_RESIDENT_DIR/microlog/civic_microlog.db"         MICROLOG_DB_PATH
    resident_copy "${MICROLOG_INDEX_PATH:-}" "$CIVIC_RESIDENT_DIR/microlog/index/vectors_microlog.db" MICROLOG_INDEX_PATH
fi

mkdir -p "$(dirname "$CIVIC_CACHE_PATH")"
exec uvicorn archive_debugger.api.app:app --host 0.0.0.0 --port "${PORT:-8080}"
