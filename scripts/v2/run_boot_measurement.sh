#!/usr/bin/env bash
# One cold-boot measurement: a fresh container on a fresh, empty Docker volume, network off, under a
# memory limit with swap off, running scripts/v2/measure_boot.py inside the serving image.
#
#   scripts/v2/run_boot_measurement.sh IMAGE MEMORY MODE SCOPES DENSE LABEL [extra harness args]
#   scripts/v2/run_boot_measurement.sh archive-v2:abc123 12g server both numpy both-numpy-12g
#
# The data source is the Docker volume archive-measure-src, filled once from copies verified against
# the sha256 in config/scopes.toml. Output: reports/v2/raw/boot/LABEL.json (+ .server.log).
# The container's exit code is printed; 137 means the kernel killed it for memory.
set -u

IMAGE="$1"; MEMORY="$2"; MODE="$3"; SCOPES="$4"; DENSE="$5"; LABEL="$6"; shift 6
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$REPO/reports/v2/raw/boot"
mkdir -p "$OUT"
VOLUME="archive-measure-run-$LABEL"

to_host() { if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else echo "$1"; fi; }

docker volume rm -f "$VOLUME" >/dev/null 2>&1
docker volume create "$VOLUME" >/dev/null
start=$(date +%s)
MSYS_NO_PATHCONV=1 docker run --rm --name "measure-$LABEL" \
  --network none --memory="$MEMORY" --memory-swap="$MEMORY" \
  -v archive-measure-src:/src:ro \
  -v "$VOLUME":/data \
  -v "$(to_host "$REPO/scripts/v2")":/harness:ro \
  -v "$(to_host "$OUT")":/out \
  "$IMAGE" python /harness/measure_boot.py --mode "$MODE" --scopes "$SCOPES" --dense "$DENSE" \
  --label "$LABEL" --out "/out/$LABEL.json" "$@" > "$OUT/$LABEL.stdout.log" 2>&1
code=$?
end=$(date +%s)
docker volume rm -f "$VOLUME" >/dev/null 2>&1
echo "label=$LABEL image=$IMAGE memory=$MEMORY mode=$MODE scopes=$SCOPES dense=$DENSE exit=$code wall_s=$((end - start))" \
  | tee -a "$OUT/runs.log"
