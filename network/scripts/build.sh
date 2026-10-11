#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# Keep fixes reviewable and reproducible without vendoring whole upstream trees.
for component in io_uring client; do
  dest="$ROOT/network/$component/vendor"
  patch="$ROOT/network/patches/$component.patch"
  [[ -d "$dest/.git" ]] || { echo 'Run network/scripts/fetch_upstream.sh first' >&2; exit 1; }
  expected="$(awk -F '\t' -v rel="network/$component/vendor" '$1==rel {print $3}' "$ROOT/docs/upstream-versions.tsv")"
  [[ "$(git -C "$dest" rev-parse HEAD)" == "$expected" ]] || { echo "Wrong upstream revision: $component" >&2; exit 1; }
  if git -C "$dest" apply --reverse --check "$patch" 2>/dev/null; then :
  else git -C "$dest" apply --check "$patch"; git -C "$dest" apply "$patch"; fi
  [[ "$(git -C "$dest" diff --binary)" == "$(cat "$patch")" ]] && git -C "$dest" diff --cached --quiet || {
    echo "Unrecognized source modifications: $component" >&2; exit 1;
  }
done
make -C "$ROOT/network/traditional"
make -C "$ROOT/network/io_uring/vendor" io_uring_echo_server
cp "$ROOT/network/client/Cargo.lock" "$ROOT/network/client/vendor/Cargo.lock"
cargo build --locked --manifest-path "$ROOT/network/client/vendor/Cargo.toml" --release
