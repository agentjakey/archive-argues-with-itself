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
#
# On a Windows host (Docker Desktop on WSL2) the WSL VM's caches are dropped before the run, and a
# watchdog stops the container if the host's available memory falls under HOST_MIN_AVAILABLE_MB
# (default 2000), so a run cannot starve the machine. Such a run is logged with host_abort=1 and is
# not a measurement of the container.
set -u

IMAGE="$1"; MEMORY="$2"; MODE="$3"; SCOPES="$4"; DENSE="$5"; LABEL="$6"; shift 6
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$REPO/reports/v2/raw/boot"
mkdir -p "$OUT"
VOLUME="archive-measure-run-$LABEL"
CONTAINER="measure-$LABEL"
HOST_MIN_AVAILABLE_MB="${HOST_MIN_AVAILABLE_MB:-2000}"

to_host() { if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else echo "$1"; fi; }

host_available_mb() {
  command -v powershell.exe >/dev/null 2>&1 || { echo ""; return; }
  powershell.exe -NoProfile -NonInteractive -Command \
    "[int](Get-Counter '\Memory\Available MBytes').CounterSamples[0].CookedValue" 2>/dev/null | tr -d '\r'
}

watchdog() {
  while sleep 5; do
    docker inspect "$CONTAINER" >/dev/null 2>&1 || continue
    available="$(host_available_mb)"
    [ -z "$available" ] && continue
    if [ "$available" -lt "$HOST_MIN_AVAILABLE_MB" ]; then
      echo "host available ${available} MB < ${HOST_MIN_AVAILABLE_MB} MB: stopping $CONTAINER" >> "$OUT/$LABEL.host_abort"
      docker kill "$CONTAINER" >/dev/null 2>&1
      return
    fi
  done
}

MSYS_NO_PATHCONV=1 docker run --rm --privileged --entrypoint sh "$IMAGE" \
  -c "sync; echo 3 > /proc/sys/vm/drop_caches" >/dev/null 2>&1
rm -f "$OUT/$LABEL.host_abort"
docker volume rm -f "$VOLUME" >/dev/null 2>&1
docker volume create "$VOLUME" >/dev/null
watchdog &
WATCHDOG_PID=$!
start=$(date +%s)
MSYS_NO_PATHCONV=1 docker run --rm --name "$CONTAINER" \
  --network none --memory="$MEMORY" --memory-swap="$MEMORY" \
  -v archive-measure-src:/src:ro \
  -v "$VOLUME":/data \
  -v "$(to_host "$REPO/scripts/v2")":/harness:ro \
  -v "$(to_host "$OUT")":/out \
  "$IMAGE" python /harness/measure_boot.py --mode "$MODE" --scopes "$SCOPES" --dense "$DENSE" \
  --label "$LABEL" --out "/out/$LABEL.json" "$@" > "$OUT/$LABEL.stdout.log" 2>&1
code=$?
end=$(date +%s)
kill "$WATCHDOG_PID" >/dev/null 2>&1
wait "$WATCHDOG_PID" 2>/dev/null
host_abort=0
[ -f "$OUT/$LABEL.host_abort" ] && host_abort=1
docker volume rm -f "$VOLUME" >/dev/null 2>&1
echo "label=$LABEL image=$IMAGE memory=$MEMORY mode=$MODE scopes=$SCOPES dense=$DENSE exit=$code host_abort=$host_abort wall_s=$((end - start))" \
  | tee -a "$OUT/runs.log"
