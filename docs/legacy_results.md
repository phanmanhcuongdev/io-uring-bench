# Archived README before traditional-v1

Historical tables and labels below describe the original methodology. Raw measurements are not present in this checkout.

# Linux io_uring Benchmarks — Disk + Network

A reproducible learning and benchmarking project comparing conventional Linux I/O interfaces with **io_uring**.

The project reuses established open-source tools rather than rewriting the benchmark engines.

## Overview

Two categories of I/O are examined:

- **Disk I/O:** synchronous and asynchronous file operations using fio.
- **Network I/O:** TCP echo servers implemented with epoll and io_uring.

Each workload is executed repeatedly. Raw measurements are collected and analyzed to produce summary CSV files and SVG charts.

The objective is to investigate when io_uring performs better or worse under specific workloads, not to claim universal superiority.

## Technologies

| Component | Technology |
|---|---|
| Disk benchmark | fio |
| Traditional synchronous I/O | psync |
| Traditional asynchronous I/O | libaio |
| Modern asynchronous I/O | io_uring |
| Network baseline | epoll echo server |
| Network comparison | io_uring echo server |
| Network client | Rust echo benchmark |
| Automation | Bash |
| Analysis | Python standard library |
| Visualization | SVG |

## Project structure

```text
io-uring-bench/
├── disk/
│   ├── scripts/
│   │   ├── prepare_data.sh
│   │   └── run_disk.sh
│   └── workloads/
│       ├── cached_qd1.fio
│       ├── short_qd1.fio
│       ├── random_direct_qd32.fio
│       └── sequential_direct_qd32.fio
├── network/
│   └── scripts/
│       ├── fetch_upstream.sh
│       ├── build.sh
│       └── run_network.sh
├── scripts/
│   ├── setup.sh
│   ├── analyze_disk.py
│   ├── analyze_network.py
│   └── svg_plot.py
├── docs/
│   ├── benchmark_method.md
│   ├── network_fairness.md
│   ├── upstream.md
│   └── upstream-versions.tsv
├── requirements.txt
├── .gitignore
└── README.md
```

Generated runtime directories are created automatically.

## Quick start

The benchmark suite is intended for Linux.

The original measurements were performed on Debian 13.

### 1. Install dependencies

```bash
bash scripts/setup.sh
```

The setup script installs tools including:

- fio
- liburing development headers
- GCC and Make
- Rust and Cargo
- Python 3

It also creates a local Python virtual environment.

### 2. Disk benchmark

Prepare a regular 1 GiB test file:

```bash
bash disk/scripts/prepare_data.sh
```

Smoke test:

```bash
REPEATS=1 RUNTIME=2 RAMP=0 DEVICE=sata \
bash disk/scripts/run_disk.sh
```

Full benchmark:

```bash
REPEATS=10 RUNTIME=8 RAMP=2 DEVICE=sata \
bash disk/scripts/run_disk.sh
```

Analyze results:

```bash
.venv/bin/python scripts/analyze_disk.py \
  --root results --out charts
```

The `DEVICE` variable is an output label, not a physical device selector.

To test another filesystem, set `DATA_FILE` to a regular file path located on the intended storage device.

The scripts do not benchmark raw block devices.

### Disk workloads

| Workload | Baseline | Comparison | QD | Description |
|---|---|---|---:|---|
| cached_qd1 | psync | io_uring | 1 | Buffered 4 KiB reads |
| short_qd1 | psync | io_uring | 1 | Random direct 4 KiB reads |
| random_direct_qd32 | libaio | io_uring | 32 | Random direct 4 KiB reads |
| sequential_direct_qd32 | libaio | io_uring | 32 | Sequential direct 128 KiB reads |

The high-queue-depth experiments compare libaio against io_uring because psync is a synchronous fio engine and cannot represent 32 outstanding asynchronous I/O operations.

The test uses a regular input file, read-only workloads and alternating engine order.

### 3. Network benchmark

Fetch the exact upstream source revisions:

```bash
bash network/scripts/fetch_upstream.sh
```

Build the echo servers and Rust client:

```bash
bash network/scripts/build.sh
```

Smoke test:

```bash
DEVICE=loopback CONNECTIONS=1 REPEATS=1 DURATION=3 MSG_BYTES=64 \
bash network/scripts/run_network.sh
```

Full benchmark:

```bash
DEVICE=loopback CONNECTIONS="1 100 1000" REPEATS=10 DURATION=5 MSG_BYTES=64 \
bash network/scripts/run_network.sh
```

Analyze results:

```bash
.venv/bin/python scripts/analyze_network.py \
  --root results --out charts
```

The local runner starts one server at a time and uses the same Rust client against `127.0.0.1:18888`.

The workload uses TCP loopback. It does not measure physical network interface throughput.

Note that the upstream servers bind to the wildcard IPv4 address rather than strictly to loopback. Run the experiment only in an appropriate trusted environment.

The two server implementations also have meaningful internal differences. See [Network Fairness Audit](network_fairness.md).

## Experimental results

The following are measurements collected on an older HP Compaq laptop running Debian 13 with Linux kernel `6.12.111+deb13-amd64`.

These values are specific to the tested machine, workloads and software implementations.

### Disk results — SATA SSD

Median throughput from 10 repetitions per engine/workload.

| Workload | Baseline MiB/s | io_uring MiB/s | Difference |
|---|---:|---:|---:|
| cached_qd1 | 337.912 | 300.435 | -11.09% |
| short_qd1 | 20.849 | 21.025 | +0.85% |
| random_direct_qd32 | 110.616 | 114.396 | +3.42% |
| sequential_direct_qd32 | 256.830 | 257.087 | +0.10% |

The cached workload favors psync, whereas io_uring performs slightly better in the tested direct I/O workloads.

Small differences should not be interpreted as universal performance advantages.

### Network results — TCP loopback

Median completed responses per second from 10 repetitions per server/concurrency level.

Configuration: 64-byte messages, 5 seconds per run.

| Connections | epoll responses/s | io_uring responses/s | Difference |
|---|---:|---:|---:|
| 1 | 24089 | 22391 | -7.05% |
| 100 | 20603 | 20224.5 | -1.84% |
| 1000 | 20572.5 | 19872.5 | -3.40% |

For these specific implementations, epoll achieved higher median throughput at all three tested concurrency levels.

This experiment does not isolate epoll versus io_uring kernel-interface overhead.

See [Network Fairness Audit](network_fairness.md) for implementation differences, client limitations and threats to validity.

## Generated outputs

Disk:

```text
results/<device>/<host-run>/disk/
```

Network:

```text
results/<device>/<host-run>/network/
```

Analysis:

```text
charts/
├── disk_runs.csv
├── disk_medians.csv
├── disk_speedups.csv
├── disk_throughput.svg
├── disk_clatency.svg
├── disk_speedup.svg
├── network_medians.csv
└── network_speedup.svg
```

Raw benchmark data and generated charts are ignored by Git to avoid committing unnecessary artifacts.

The tables above provide a representative snapshot of measured results. Complete raw data remains available in the original measurement environment.

## Reproducibility

The exact upstream Network source commits are recorded in [docs/upstream-versions.tsv](upstream-versions.tsv).

The fetch script checks out these pinned revisions rather than silently using the latest upstream HEAD.

For valid comparisons:

1. Use the same workload configuration for both engines.
2. Repeat measurements rather than relying on a single run.
3. Alternate execution order to reduce ordering bias.
4. Record software versions and hardware characteristics.
5. Preserve raw logs for inspection.

The `scripts/analyze_network.py` script generates the main Network chart only from complete, matched experiments containing at least 10 unique runs per engine.

## Threats to validity

Benchmark results may be affected by:

- CPU architecture and frequency scaling.
- Linux kernel and library versions.
- Filesystem and page-cache behavior.
- SSD health, storage interface and device characteristics.
- Background system load and thermal conditions.
- Client and server implementation differences.
- Thread scheduling and context-switch overhead.
- Benchmark duration and measurement methodology.

Disk latency figures report fio completion latency rather than full end-to-end request latency.

Network measurements use TCP loopback, with the client and server sharing host resources.

These results should not be generalized to arbitrary applications or hardware configurations.

## References and attribution

- [Linux io_uring documentation](https://man7.org/linux/man-pages/man7/io_uring.7.html)
- [fio](https://github.com/axboe/fio)
- [liburing](https://github.com/axboe/liburing)
- [epoll echo server](https://github.com/frevib/epoll-echo-server)
- [io_uring echo server](https://github.com/frevib/io_uring-echo-server)
- [Rust echo benchmark](https://github.com/haraldh/rust_echo_bench)

Third-party licensing and exact source revisions are documented in [docs/upstream.md](upstream.md).

The project currently has no license for its original glue code. Public availability does not automatically grant permission for reuse.