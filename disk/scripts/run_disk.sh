#!/usr/bin/env bash
# Run fio JSON output for each configuration with interleaved comparison order.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source_file="${DATA_FILE:-$ROOT/data/disk_test.bin}"
# fio treats colons as file separators and requires escaping them.
fio_file="${source_file//\\/\\\\}"
fio_file="${fio_file//:/\\:}"
REPEATS="${REPEATS:-10}"
RUNTIME="${RUNTIME:-8}"
RAMP="${RAMP:-2}"
DEVICE="${DEVICE:-sata}"   # a label for the results directory, NOT a block device
[[ "$DEVICE" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Invalid DEVICE label' >&2; exit 1; }
[[ "$REPEATS" =~ ^(0|[1-9][0-9]*)$ ]] && (( REPEATS > 0 )) || { echo 'REPEATS must be positive' >&2; exit 1; }
[[ "$RUNTIME" =~ ^(0|[1-9][0-9]*)$ ]] && (( RUNTIME > 0 )) || { echo 'RUNTIME must be positive' >&2; exit 1; }
[[ "$RAMP" =~ ^(0|[1-9][0-9]*)$ ]] || { echo 'RAMP must be nonnegative' >&2; exit 1; }
command -v fio >/dev/null || { echo 'Missing fio. Run bash scripts/setup.sh' >&2; exit 1; }
[[ -f "$source_file" ]] || { echo "File missing: $source_file. Run disk/scripts/prepare_data.sh" >&2; exit 1; }
(( $(stat -c %s "$source_file") >= 1073741824 )) || { echo 'File should be >=1 GiB' >&2; exit 1; }
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$ROOT/results/$DEVICE"
SESSION="$(mktemp -d "$ROOT/results/$DEVICE/$(hostname)-$STAMP-XXXXXX")"
OUT="$SESSION/disk"
mkdir -p "$OUT"
echo running > "$OUT/status.txt"
finish() {
    rc=$?
    if (( rc != 0 )); then echo "failed exit=$rc" > "$OUT/status.txt"; fi
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
{
    echo "methodology=traditional-v2"
    echo "concurrency_qd32=32x1_psync_vs_1x32_io_uring uniform_with_replacement_shared_1GiB_range"
    echo "hostname=$(hostname)"
    echo "timestamp_utc=$STAMP"
    echo "kernel=$(uname -r)"
    echo "fio=$(fio --version)"
    sha256sum "$ROOT"/disk/workloads/*.fio
    lscpu || true
    echo "device_label=$DEVICE"
    echo "data_file=$source_file"
    echo "runtime_sec=$RUNTIME"
    echo "ramp_sec=$RAMP"
    echo "repeats=$REPEATS"
    echo "scenarios=cached_qd1 short_qd1 random_direct_qd32 sequential_direct_qd1"
    lsblk -d -o NAME,MODEL,SIZE,ROTA,TRAN || true
    df -hT "$source_file" || true
} > "$OUT/metadata.txt"

run() {
    local scenario="$1" engine="$2" iteration="$3" jobfile="$4"
    local label="$engine" workers=1 depth=1
    if [[ "$engine" == traditional ]]; then engine=psync; fi
    if [[ "$scenario" == *_qd32 ]]; then
      if [[ "$label" == traditional ]]; then workers=32; else depth=32; fi
    fi
    local output="$OUT/${scenario}__${label}__run$(printf '%02d' "$iteration").json"
    echo "[$iteration/$REPEATS] $scenario $engine -> $(basename "$output")"
    if ! fio --readonly --ioengine="$engine" --filename="$fio_file" \
      --numjobs="$workers" --iodepth="$depth" --group_reporting=0 --offset=0 --runtime="$RUNTIME" --ramp_time="$RAMP" --output-format=json --output="$output" "$jobfile"; then
        echo "fio failed; output: $output" >&2
        exit 1
    fi
    python3 - "$output" "$workers" <<'PY'
import json,sys
p=sys.argv[1]
with open(p) as f: x=json.load(f)
if len(x.get('jobs',[])) != int(sys.argv[2]): raise SystemExit(f'Unexpected fio worker count in {p}')
errors=[(j.get('jobname'), j.get('error',0)) for j in x.get('jobs',[]) if j.get('error',0)]
if errors: raise SystemExit(f'fio job errors in {p}: {errors}')
if any(j['read']['total_ios'] <= 0 or j['read']['bw_bytes'] <= 0 for j in x['jobs']): raise SystemExit(f'Worker completed no reads in {p}')
PY
}

# traditional-v2: QD32 compares concurrent architectures, not isolated API overhead.
# Run alternating order for each repeat to reduce temperature / background-load bias.
for ((i=1; i<=REPEATS; i++)); do
    if (( i%2==1 )); then
      order1=(traditional io_uring); order2=(traditional io_uring)
    else
      order1=(io_uring traditional); order2=(io_uring traditional)
    fi
    # Warm the page cache explicitly for this scenario.
    for engine in "${order1[@]}"; do
       head -c 268435456 -- "$source_file" > /dev/null
       run cached_qd1 "$engine" "$i" "$ROOT/disk/workloads/cached_qd1.fio"
    done
    for engine in "${order1[@]}"; do
       run short_qd1 "$engine" "$i" "$ROOT/disk/workloads/short_qd1.fio"
    done
    for scenario in random_direct_qd32 sequential_direct_qd1; do
      for engine in "${order2[@]}"; do
        run "$scenario" "$engine" "$i" "$ROOT/disk/workloads/$scenario.fio"
      done
    done
done
echo complete > "$OUT/status.txt"
echo "Disk JSON results: $OUT"
echo "Next: python3 scripts/analyze_disk.py --root results --out charts"
