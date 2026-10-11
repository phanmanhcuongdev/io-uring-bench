#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[[ -f "$ROOT/network/traditional/vendor/Makefile" ]] || { echo 'Run bash network/scripts/fetch_upstream.sh first' >&2; exit 1; }
[[ -f "$ROOT/network/io_uring/vendor/Makefile" ]] || { echo 'Missing io_uring source' >&2; exit 1; }
[[ -f "$ROOT/network/client/vendor/Cargo.toml" ]] || { echo 'Missing Rust echo bench source' >&2; exit 1; }
make -C "$ROOT/network/traditional/vendor"
make -C "$ROOT/network/io_uring/vendor" io_uring_echo_server
cargo build --manifest-path "$ROOT/network/client/vendor/Cargo.toml" --release
printf '\nExecutables:\n  %s\n' \
 "$ROOT/network/traditional/vendor/epoll_echo_server" \
 "$ROOT/network/io_uring/vendor/io_uring_echo_server" \
 "$ROOT/network/client/vendor/target/release/echo_bench"
