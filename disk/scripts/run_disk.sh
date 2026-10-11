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
OUT="$ROOT/results/$DEVICE/$(hostname)-$STAMP/disk"
mkdir -p "$OUT"
{
    echo "hostname=$(hostname)"
    echo "timestamp_utc=$STAMP"
    echo "kernel=$(uname -r)"
    echo "fio=$(fio --version)"
    echo "device_label=$DEVICE"
    echo "data_file=$source_file"
    echo "runtime_sec=$RUNTIME"
    echo "ramp_sec=$RAMP"
    echo "repeats=$REPEATS"
    lsblk -d -o NAME,MODEL,SIZE,ROTA,TRAN || true
    df -hT "$source_file" || true
} > "$OUT/metadata.txt"

run() {
    local scenario="$1" engine="$2" iteration="$3" jobfile="$4"
    local output="$OUT/${scenario}__${engine}__run$(printf '%02d' "$iteration").json"
    echo "[$iteration/$REPEATS] $scenario $engine -> $(basename "$output")"
    if ! fio --readonly --ioengine="$engine" --filename="$fio_file" \
      --runtime="$RUNTIME" --ramp_time="$RAMP" --output-format=json --output="$output" "$jobfile"; then
        echo "fio failed; output: $output" >&2
        exit 1
    fi
    python3 - "$output" <<'PY'
import json,sys
p=sys.argv[1]
with open(p) as f: x=json.load(f)
if not x.get('jobs'): raise SystemExit(f'No fio jobs in {p}')
errors=[(j.get('jobname'), j.get('error',0)) for j in x.get('jobs',[]) if j.get('error',0)]
if errors: raise SystemExit(f'fio job errors in {p}: {errors}')
PY
}

# Cached 4k read, QD1 (psync vs uring) and direct QD32 (libaio vs uring).
# Run alternating order for each repeat to reduce temperature / background-load bias.
for ((i=1; i<=REPEATS; i++)); do
    if (( i%2==1 )); then
      order1=(psync io_uring); order2=(libaio io_uring)
    else
      order1=(io_uring psync); order2=(io_uring libaio)
    fi
    # Warm the page cache explicitly for this scenario.
    for engine in "${order1[@]}"; do
       head -c 268435456 -- "$source_file" > /dev/null
       run cached_qd1 "$engine" "$i" "$ROOT/disk/workloads/cached_qd1.fio"
    done
    for engine in "${order1[@]}"; do
       run short_qd1 "$engine" "$i" "$ROOT/disk/workloads/short_qd1.fio"
    done
    for engine in "${order2[@]}"; do
       run random_direct_qd32 "$engine" "$i" "$ROOT/disk/workloads/random_direct_qd32.fio"
       run sequential_direct_qd32 "$engine" "$i" "$ROOT/disk/workloads/sequential_direct_qd32.fio"
    done
done
echo "Disk JSON results: $OUT"
echo "Next: .venv/bin/python scripts/analyze_disk.py --root results --out charts"
