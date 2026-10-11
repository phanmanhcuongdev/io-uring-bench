# Superseded refactor validation (traditional-v1)

This historical record predates the technical audit. Current design, tests and readiness are documented in [benchmark_audit.md](benchmark_audit.md). In particular, the stricter v2 1000-connection smoke failed; do not interpret the older short test below as current readiness.

# Refactor validation and review record

## Environment and results

Validated from Windows with WSL Ubuntu, GCC/liburing, fio 3.41, Rust/Cargo 1.93, and Python 3.14 on the Windows side. Tool installation was authorized; no full benchmark was run. Linux distribution/kernel here is a test environment, not either original SATA/NVMe machine.

- All repository Bash scripts (including smoke_disk.sh): bash -n passed.
- Traditional C server: -Wall -Wextra -Werror -O2 -pthread build passed.
- Retained patched io_uring C server: upstream -Wall -O2 build passed.
- Patched shared Rust client: release build with tracked Cargo.lock and --locked passed.
- Repeated build/fetch: passed, recognized exactly the tracked correctness patches and pinned commits.
- Seven analyzer regression tests: passed. Coverage includes 32-worker bandwidth/IOPS sum, weighted latency, sample stddev, percentages, legacy exclusion/separate output, incomplete pairs, duplicate IDs and stale chart removal.
- Disk smoke: all eight workload/method combinations passed using a temporary 4 MiB regular file, one second each. Production workload ranges were only reduced in a temporary jobfile copy. JSON worker-count and error/completed-read assertions passed. Traditional QD32 produced 32 jobs; io_uring produced one job. fio --showcmd also confirmed psync numjobs=32/iodepth=1.
- Network correctness: both servers passed fragmented 64 KiB echo, half-close, 100 concurrent clients, peer disconnect and termination with 100 idle sockets.
- Real network runner smoke: one repeat, one second, 512-byte messages at 1, 100 and 1000 connections passed for both servers. Eight raw rows/logs (including a final 1-connection recheck of unique output directories) are retained under ignored results/smoke. This establishes short-run functionality only; it does not establish stable 10-repeat performance.
- Network analyzer on the original six rows: parsed successfully; no comparative SVG was generated because no pair had 10 repeats.
- git diff --check passed.

No block device was written. No 1 GiB data file was generated, no large dataset was downloaded, and no full 10-repeat suite was run. No commit or push was made. The production 256 MiB/1 GiB disk runner was not measured end-to-end on physical SATA/NVMe; device behavior and sustained 1000-connection stability remain unverified.

## Files changed or added

Modified: .gitignore; README.md; disk/scripts/prepare_data.sh and run_disk.sh; all four disk/workloads/*.fio; docs/benchmark_method.md, network_fairness.md, upstream.md and upstream-versions.tsv; network/scripts/build.sh, fetch_upstream.sh and run_network.sh; scripts/setup.sh, analyze_disk.py and analyze_network.py.

Added: .gitattributes; network/traditional/blocking_echo_server.c and Makefile; network/patches/client.patch and io_uring.patch; network/client/Cargo.lock; scripts/analysis_common.py; tests/test_analysis.py, smoke_network.py and smoke_disk.sh; docs/legacy_results.md, legacy_network_audit.md and this record.

Removed: requirements.txt (contained only a no-dependencies comment), unnecessary pip/venv setup, unused jq/sysstat installation requests, epoll fetch/build/run/manifest entries, libaio disk engine selection. No epoll vendor source existed in the initial checkout, so there was no source tree to delete. fio's distribution package may depend transitively on libaio; do not remove libraries needed by fio itself. There is no explicit libaio build/runtime selection in the new study.

## Remeasurement and historical data

QD32 SATA/NVMe and all network pairs must be measured again because the baseline architecture changed. All patched io_uring/client network pairs require fresh measurements as well. For a consistent traditional-v1 presentation, collect all four disk pairs on each intended storage device and the supported network levels with ten repeats.

The stated 220 historical measurements (80 SATA, 80 NVMe, 60 loopback) were not present in this checkout. No historical raw files were removed or relabeled. Archived README tables and original network audit preserve the original claims and provenance. Historical psync QD1 versus io_uring can still support qualified historical synchronous-I/O claims; libaio QD32 and epoll network data remain usable only for their original labeled comparisons. They must never be presented as the new Traditional QD32/network experiment. Default analyzers exclude entire legacy sessions, including their io_uring rows.

Commands, repository structure, protocol caveats and output schemas are documented in README.md. Use --legacy for a separate analysis under charts/legacy. Keep tests/smoke results separate from research measurements.
