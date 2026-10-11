# Linux io_uring Benchmarks — Disk + Network

A reproducible **learning & benchmarking harness** comparing conventional Linux I/O interfaces with io_uring. It **reuses upstream engines** rather than rewriting them:

- **Disk**: [fio](https://github.com/axboe/fio) `psync`, `libaio`, `io_uring` engines.
- **Network**: [frevib/epoll-echo-server](https://github.com/frevib/epoll-echo-server), [frevib/io_uring-echo-server](https://github.com/frevib/io_uring-echo-server), [haraldh/rust_echo_bench](https://github.com/haraldh/rust_echo_bench).
- **Analysis**: Python standard library/SVG, with raw output retained alongside metadata.

## Quick start (Debian 13)

Run commands from the repository root (`io-uring-bench/`). Runtime data, result, chart and vendor directories are created automatically; no placeholder files are required.

```bash
bash scripts/setup.sh
bash disk/scripts/prepare_data.sh
REPEATS=1 RUNTIME=2 RAMP=0 DEVICE=sata bash disk/scripts/run_disk.sh  # smoke test
REPEATS=10 RUNTIME=8 RAMP=2 DEVICE=sata bash disk/scripts/run_disk.sh
.venv/bin/python scripts/analyze_disk.py --root results --out charts
```

`DEVICE` is only an output **label**, not a storage device selector. The test file must physically reside on the desired filesystem. `DATA_FILE=/your/safe/path/disk_test.bin` may be used with both scripts. The preparation script writes a **regular file**, never a raw block device. It creates 1 GiB of random data by default; it never overwrites an existing smaller file.

Run the same commands on SATA and NVMe Linux hosts with `DEVICE=sata` or `DEVICE=nvme`. Copy their generated `results/<device>/...` directories to one machine, then run `analyze_disk.py`. Do not compare the raw absolute numbers as if differences come solely from interface type when CPU/kernel/filesystem differ.

**Disk comparisons**:

| Workload | Engines | Queue Depth | Purpose |
|---|---|---:|---|
| `cached_qd1` | psync vs io_uring | 1 | Buffered read overhead; cache prewarmed |
| `short_qd1` | psync vs io_uring | 1 | Small random direct read overhead |
| `random_direct_qd32` | libaio vs io_uring | 32 | Random I/O concurrency |
| `sequential_direct_qd32` | libaio vs io_uring | 32 | Direct sequential throughput |

`psync` is synchronous and does not produce genuine asynchronous QD32. Therefore high-QD workloads compare `libaio` against `io_uring` **at the same QD**. This measures their relative behavior, not a universal comparison against *all* traditional I/O APIs. Win/loss cases are **hypotheses**, not guaranteed outputs.

Tests use read-only fio jobs, same regular input file, 10 repeats by default, alternating engine order within repeats, and collect raw fio JSON. `O_DIRECT` tests use aligned block sizes. `ramp_time` is excluded from fio's measured interval. The cached test explicitly prewarms its 256 MiB working set before each engine, but background pressure may still evict them.

## Network echo benchmark

```bash
bash network/scripts/fetch_upstream.sh
bash network/scripts/build.sh
REPEATS=1 DURATION=3 DEVICE=sata bash network/scripts/run_network.sh    # smoke test
REPEATS=10 DURATION=8 DEVICE=sata bash network/scripts/run_network.sh
.venv/bin/python scripts/analyze_network.py --root results --out charts
```

This local runner starts an upstream **epoll** or **io_uring** echo server on port `18888`, then runs the same Rust client against `127.0.0.1:18888`. The server bind address is controlled by upstream code; loopback client traffic does not guarantee a loopback-only listener. It tests 1, 100, and 1000 connections (may be limited by RAM/file descriptor limits). Results are **loopback networking**, not NIC throughput. Do not use these untrusted upstream servers on public interfaces; review their code before exposing ports. Ports must be free. `PORT=...` changes listening port. Setup installs Rust/Cargo. The Rust client uses crates from its own repository, downloaded at build time. This integration is subject to upstream build/runtime compatibility. See [the network fairness audit](docs/network_fairness.md) for verified implementation differences. Network charts include only matched experiments with at least 10 runs per engine for 1, 100 and 1000 connections; CSV summaries retain smoke tests.

## Output

- Raw fio JSON: `results/<device>/<host>-<timestamp>/disk/`
- Network logs + `runs.csv`: `results/<device>/<host>-<timestamp>/network/`
- Graphs + summary CSVs: `charts/` (generated)
- Upstream git commit manifest: `docs/upstream-versions.tsv` (recorded provenance; include it in Git)

`data/`, `results/`, `charts/`, `.venv/` and fetched `network/*/vendor/` checkouts (including their nested Git metadata and binaries) are ignored. Keep the vendor directories locally; fetch/build them on a fresh checkout. `results/` and `charts/` data are not committed by default. Preserve representative outputs for your slides or attach them to a release.

## Threats to validity

- Page Cache, background I/O, CPU scaling, thermals, write amplification, filesystem, file layout, kernel and fio versions, virtualized vs native devices, and disk health.
- `fio` bandwidth from elapsed read measurements: not independently verified disk bus throughput.
- An echo client can saturate CPU or memory; both servers should use identical machine/load/configuration and runs should alternate order.
- When running on different computers, differences cannot be attributed solely to SATA vs NVMe.

## Attribution

Upstream repos and license terms are described in [`docs/upstream.md`](docs/upstream.md). This repo's scripts and job files are independent glue code; upstream source is fetched into ignored vendor directories. No upstream licensing notices are removed.

Analysis reports medians and min/max spread. Network RPS counts completed responses. Disk latency charts report completion latency (`clat`), not total submission-plus-completion latency.

The project currently has no license for its original glue code; public visibility alone does not grant permission to reuse it. Choose a license before distributing it as open source.
