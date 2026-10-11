#!/usr/bin/env bash
# Correctness only: 4 MiB temporary regular file, never storage performance data.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT
OUT="$TMP/results/smoke/local/disk"
mkdir -p "$OUT"
printf 'methodology=traditional-v2\nrepeats=1\nscenarios=cached_qd1 short_qd1 random_direct_qd32 sequential_direct_qd1\n' > "$OUT/metadata.txt"
dd if=/dev/urandom of="$TMP/input" bs=1M count=4 conv=excl,fsync status=none
for workload in "$ROOT"/disk/workloads/*.fio; do
  sed -E 's/^size=.*/size=4m/' "$workload" > "$TMP/job.fio"
  for method in traditional io_uring; do
    workers=1; depth=1; engine="$method"
    [[ "$method" != traditional ]] || engine=psync
    if [[ "$workload" == *_qd32.fio ]]; then
      if [[ "$method" == traditional ]]; then workers=32; else depth=32; fi
    fi
    output="$OUT/$(basename "$workload" .fio)__${method}__run01.json"
    fio --readonly --ioengine="$engine" --filename="$TMP/input" --numjobs="$workers" \
      --iodepth="$depth" --runtime=1 --ramp_time=0 --output-format=json \
      --output="$output" "$TMP/job.fio"
    python3 - "$output" "$workers" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); jobs=x['jobs']
assert len(jobs)==int(sys.argv[2]), len(jobs)
assert all(j['error']==0 and j['read']['io_bytes']>0 for j in jobs)
PY
    echo "PASS $(basename "$workload") $method workers=$workers depth=$depth (4 MiB smoke only)"
  done
done
echo complete > "$OUT/status.txt"
python3 "$ROOT/scripts/analyze_disk.py" --root "$TMP/results" --out "$TMP/charts"
test -f "$TMP/charts/disk_runs.csv"
test ! -f "$TMP/charts/disk_throughput.svg"
