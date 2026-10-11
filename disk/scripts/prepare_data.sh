#!/usr/bin/env bash
# Writes a regular file on the target filesystem (NEVER a raw block device).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FILE="${DATA_FILE:-$ROOT/data/disk_test.bin}"
SIZE_MB="${SIZE_MB:-1024}"
[[ "$SIZE_MB" =~ ^(0|[1-9][0-9]*)$ ]] && (( SIZE_MB >= 1024 )) || { echo "SIZE_MB must be >=1024 for the default fio jobs" >&2; exit 1; }
[[ "$FILE" != /dev/* ]] || { echo 'Refusing to write under /dev' >&2; exit 1; }
mkdir -p "$(dirname "$FILE")"
if [[ -f "$FILE" ]] && (( $(stat -c %s "$FILE") >= SIZE_MB*1048576 )); then
  echo "Existing file: $FILE ($(stat -c %s "$FILE") bytes)"; exit 0
fi
if [[ -e "$FILE" || -L "$FILE" ]]; then echo "Refusing to overwrite existing file: $FILE" >&2; exit 1; fi
if [[ ! -w "$(dirname "$FILE")" ]]; then echo 'Target directory is not writable' >&2; exit 1; fi
avail=$(df -Pk "$(dirname "$FILE")" | awk 'NR==2 {print $4}')
if (( avail < (SIZE_MB+512)*1024 )); then echo 'Not enough free disk space (need file + 512 MiB headroom)' >&2; exit 1; fi
# Real file data, not just sparse extents; slow on some drives.
echo "Creating $SIZE_MB MiB test file: $FILE"
dd if=/dev/urandom of="$FILE" bs=1M count="$SIZE_MB" conv=excl,fsync status=progress
