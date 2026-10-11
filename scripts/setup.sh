#!/usr/bin/env bash
# Install dependencies for the io-uring benchmark suite.
# Run from any directory: bash /path/to/io-uring-bench/scripts/setup.sh
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
    SUDO=()
else
    if ! command -v sudo >/dev/null 2>&1; then
        echo "ERROR: sudo is required for package installation." >&2
        exit 1
    fi
    SUDO=(sudo)
fi

echo "==> Installing system dependencies..."
if command -v apt-get >/dev/null 2>&1; then
    "${SUDO[@]}" apt-get update
    "${SUDO[@]}" apt-get install -y \
        fio git python3 \
        build-essential liburing-dev cargo rustc
elif command -v dnf >/dev/null 2>&1; then
    # Some RHEL-based systems do not provide liburing-devel by default.
    "${SUDO[@]}" dnf install -y \
        fio git python3 gcc make liburing-devel cargo rust
elif command -v pacman >/dev/null 2>&1; then
    "${SUDO[@]}" pacman -S --needed --noconfirm \
        fio git python base-devel liburing rust
else
    echo "ERROR: Unsupported package manager (apt-get/dnf/pacman required)." >&2
    exit 1
fi

echo "==> Checking io_uring availability..."
if [[ -r /proc/sys/kernel/io_uring_disabled ]]; then
    URING_DISABLED="$(cat /proc/sys/kernel/io_uring_disabled)"
    echo "kernel.io_uring_disabled=$URING_DISABLED"
    if [[ "$URING_DISABLED" != "0" ]]; then
        echo "WARNING: io_uring may be restricted. Check kernel policy before running benchmarks." >&2
        echo "         This script does not change kernel security settings." >&2
    fi
else
    echo "WARNING: kernel.io_uring_disabled is not exposed; verify io_uring with a test run." >&2
fi

echo "==> Tool versions"
fio --version
python3 --version

echo "==> Setup complete. Analysis uses python3 (standard library only)."
