#!/usr/bin/env bash
# Fetch upstream repositories at the exact commits recorded in the manifest.
# Never overwrite local source modifications or change pinned versions silently.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANIFEST="$ROOT/docs/upstream-versions.tsv"

[[ -f "$MANIFEST" ]] || {
    echo "ERROR: Missing $MANIFEST" >&2
    exit 1
}

clone_one() {
    local rel="$1"
    local url="$2"
    local sha="$3"
    local dest="$ROOT/$rel"
    local expected_url

    case "$rel" in
        network/io_uring/vendor)
            expected_url="https://github.com/frevib/io_uring-echo-server.git"
            ;;
        network/client/vendor)
            expected_url="https://github.com/haraldh/rust_echo_bench.git"
            ;;
        *)
            echo "ERROR: Unknown vendor path: $rel" >&2
            exit 1
            ;;
    esac

    [[ "$url" == "$expected_url" ]] || {
        echo "ERROR: Unexpected upstream URL for $rel" >&2
        exit 1
    }

    [[ "$sha" =~ ^[0-9a-fA-F]{40}$ ]] || {
        echo "ERROR: Invalid commit SHA for $rel" >&2
        exit 1
    }

    if [[ -d "$dest/.git" ]]; then
        echo "EXISTS: $rel"

        [[ "$(git -C "$dest" remote get-url origin)" == "$url" ]] || {
            echo "ERROR: Origin URL mismatch: $rel" >&2
            exit 1
        }

        if ! git -C "$dest" diff --quiet ||
           ! git -C "$dest" diff --cached --quiet; then
            component="$(basename "$(dirname "$rel")")"
            patch="$ROOT/network/patches/$component.patch"
            actual="$(git -C "$dest" diff --binary)"
            expected="$(cat "$patch")"
            [[ "$actual" == "$expected" ]] && git -C "$dest" diff --cached --quiet || {
                echo "ERROR: Unrecognized local modifications: $rel" >&2; exit 1;
            }
        fi

    elif [[ -e "$dest" ]] && [[ -n "$(ls -A "$dest" 2>/dev/null)" ]]; then
        echo "ERROR: Non-empty directory is not a Git checkout: $dest" >&2
        exit 1
    else
        echo "CLONE: $url"
        git clone --no-checkout "$url" "$dest"
    fi

    # A recorded commit may not be present in an existing shallow clone.
    if ! git -C "$dest" cat-file -e "${sha}^{commit}" 2>/dev/null; then
        git -C "$dest" fetch --no-tags origin "$sha"
    fi

    if [[ "$(git -C "$dest" rev-parse HEAD)" != "$sha" ]] ||
       [[ -z "$(git -C "$dest" ls-files)" ]]; then
        git -C "$dest" checkout --detach "$sha"
    fi

    # Check whether the expected files are actually checked out.
    [[ -n "$(git -C "$dest" ls-files)" ]] || {
        echo "ERROR: Empty source checkout: $rel" >&2
        exit 1
    }

    [[ "$(git -C "$dest" rev-parse HEAD)" == "$sha" ]] || {
        echo "ERROR: Commit mismatch: $rel" >&2
        exit 1
    }

    echo "PINNED: $rel @ $sha"
}

count=0

while IFS=$'\t' read -r rel url sha; do
    [[ -z "$rel" ]] && continue
    clone_one "$rel" "$url" "$sha"
    ((count += 1))
done < "$MANIFEST"

[[ "$count" -eq 2 ]] || {
    echo "ERROR: Expected 2 upstream entries, found $count" >&2
    exit 1
}

echo "All upstream repositories verified."