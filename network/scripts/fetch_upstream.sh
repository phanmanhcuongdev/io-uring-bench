#!/usr/bin/env bash
# Download upstream sources as isolated copies; do not silently overwrite local modifications.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
clone_one() {
  local url="$1" dest="$2"
  if [[ -d "$dest/.git" ]]; then
    echo "PRESENT: $dest (no auto-pull)"
  elif [[ -e "$dest" ]] && [[ -n "$(ls -A "$dest" 2>/dev/null)" ]]; then
    echo "ERROR: $dest exists and is not a git checkout" >&2; exit 1
  else
    git clone --depth 1 "$url" "$dest"
  fi
}
clone_one https://github.com/frevib/epoll-echo-server.git "$ROOT/network/traditional/vendor"
clone_one https://github.com/frevib/io_uring-echo-server.git "$ROOT/network/io_uring/vendor"
clone_one https://github.com/haraldh/rust_echo_bench.git "$ROOT/network/client/vendor"
{
 for d in "$ROOT/network/traditional/vendor" "$ROOT/network/io_uring/vendor" "$ROOT/network/client/vendor"; do
   printf '%s\t%s\t%s\n' "${d#$ROOT/}" "$(git -C "$d" remote get-url origin)" "$(git -C "$d" rev-parse HEAD)"
 done
} > "$ROOT/docs/upstream-versions.tsv"
echo "Fetched. Exact versions recorded in docs/upstream-versions.tsv"
