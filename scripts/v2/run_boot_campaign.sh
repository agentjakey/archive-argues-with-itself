#!/usr/bin/env bash
# The Phase 0 cold-boot measurements, one fresh container and empty volume each, run in sequence.
# Results: reports/v2/raw/boot/*.json, one line per run in reports/v2/raw/boot/runs.log.
#
#   scripts/v2/run_boot_campaign.sh BASELINE_IMAGE V2_IMAGE baseline|limits|all
#
# "baseline": every scope and dense backend at 12g (the standard-4 size), the pre-fix image's numpy
# boot for comparison, and the in-process breakdown with the mmap setting on and off.
# "limits": both scopes, server mode, at decreasing memory limits, for the smallest safe size of
# each dense backend (and the pre-fix image at the limits where the fix matters).
set -u
BASE="$1"; V2="$2"; WHICH="${3:-all}"
RUN="$(dirname "$0")/run_boot_measurement.sh"

if [ "$WHICH" = "baseline" ] || [ "$WHICH" = "all" ]; then
  for scopes in both pilot microlog; do
    for dense in sqlite numpy; do
      bash "$RUN" "$V2" 12g server "$scopes" "$dense" "v2-server-$scopes-$dense-12g"
    done
  done
  bash "$RUN" "$BASE" 12g server both numpy "base-server-both-numpy-12g"
  for dense in sqlite numpy; do
    for mmap in on off; do
      bash "$RUN" "$V2" 12g inprocess both "$dense" "v2-inproc-both-$dense-mmap$mmap-12g" --mmap "$mmap"
    done
  done
fi

if [ "$WHICH" = "limits" ] || [ "$WHICH" = "all" ]; then
  for mem in 8g 6g 5g 4g 3g; do
    bash "$RUN" "$V2" "$mem" server both numpy "v2-server-both-numpy-$mem"
    bash "$RUN" "$BASE" "$mem" server both numpy "base-server-both-numpy-$mem"
  done
  for mem in 4g 3g 2g 1536m 1g; do
    bash "$RUN" "$V2" "$mem" server both sqlite "v2-server-both-sqlite-$mem"
  done
fi
