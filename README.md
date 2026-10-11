# Traditional I/O vs io_uring

Research question: **When is Traditional I/O faster than io_uring, and when is io_uring faster than Traditional I/O?** This repository supports reproducible disk/network experiments and a 20-minute technical presentation. There are only two current implementations: `traditional` and `io_uring`. No new measurements are claimed here.

Traditional means synchronous fio `psync` for disk and blocking POSIX `accept()`, `recv()`, `send()` with one worker thread per TCP connection for network. Linux is required; Python analysis also works on Windows.

## Structure

```text
disk/scripts/                 prepare_data.sh, run_disk.sh
disk/workloads/               four read-only fio workloads
network/traditional/          blocking_echo_server.c, Makefile
network/io_uring/vendor/       fetched pinned upstream (ignored)
network/client/vendor/         fetched shared Rust client (ignored)
network/client/Cargo.lock      pinned Rust dependencies
network/patches/               reproducible correctness fixes
network/scripts/              fetch_upstream.sh, build.sh, run_network.sh
scripts/                      setup, analyzers, shared statistics, SVG renderer
tests/                        analyzer regression and Linux smoke tests
docs/                         methodology, fairness, provenance, legacy archives
results/<device>/<host-run>/   disk JSON / network CSV and raw logs (ignored)
charts/                       CSV statistics and SVG charts (ignored)
```

## Install

```bash
bash scripts/setup.sh
bash network/scripts/fetch_upstream.sh
bash network/scripts/build.sh
```

Dependencies: fio, GCC/Make/pthreads, liburing, Rust/Cargo, Git, Python 3.10+. Analysis uses only the standard library. `build.sh` applies tracked correctness patches to the two pinned upstream components and is safe to repeat. See [provenance](docs/upstream.md).

## Disk

Explicitly prepare a regular file on the filesystem being measured (this writes 1 GiB; never use a block device):

```bash
DATA_FILE=/path/on/sata/disk_test.bin bash disk/scripts/prepare_data.sh
DATA_FILE=/path/on/sata/disk_test.bin DEVICE=sata REPEATS=1 RUNTIME=2 RAMP=0 bash disk/scripts/run_disk.sh
# After reviewing the smoke test, run the measurement manually:
DATA_FILE=/path/on/sata/disk_test.bin DEVICE=sata REPEATS=10 RUNTIME=8 RAMP=2 bash disk/scripts/run_disk.sh
python3 scripts/analyze_disk.py --root results --device sata --out charts/sata
```

Use another regular-file path and `DEVICE=nvme` for NVMe. DEVICE is only an output label.

| Workload | Pattern / block / range | Cache | Traditional | io_uring |
|---|---|---|---|---|
| cached_qd1 | sequential / 4 KiB / 256 MiB | buffered, prewarmed | 1 worker, QD1 | 1 job, QD1 |
| short_qd1 | random / 4 KiB / 1 GiB | direct | 1 worker, QD1 | 1 job, QD1 |
| random_direct_qd32 | random / 4 KiB / 1 GiB | direct | 32 workers, each QD1 | 1 job, QD32 |
| sequential_direct_qd1 | sequential / 128 KiB / 1 GiB | direct | 1 worker, QD1 | 1 job, QD1 |

`short_qd1` is Random Direct QD1. Random QD32 workers share offset 0 and a 1 GiB range; both sides use uniform sampling with replacement (`norandommap=1`, `randrepeat=1`). Aggregate address distribution matches, but exact I/O sequences differ across jobs. Random overlap and device-cache hits can occur on both sides.

Sequential QD32 was removed after audit: 32 workers repeatedly reading overlapping streams is not equivalent to one queued sequential stream. Sequential now uses QD1 on both sides. Random QD32 remains a comparison of concurrent architectures, **not isolated API overhead**: 32 synchronous worker threads versus one job with up to 32 in-flight operations. Concurrency 32 is an upper bound, not a guarantee. Inspect achieved fio depths; psync always receives `iodepth=1`.

Runtime/ramp, block size, pattern, direct mode and logical range match within each pair. Per-job JSON uses `group_reporting=0`; analyzer sums read bandwidth and IOPS across workers and weights mean completion latency by completed I/Os. See [methodology](docs/benchmark_method.md).

## Network

```bash
CONNECTIONS="1 100" REPEATS=1 DURATION=2 MSG_BYTES=512 bash network/scripts/run_network.sh
# Include 1000 only after it passes a smoke test on this host:
CONNECTIONS="1000" REPEATS=1 DURATION=2 MSG_BYTES=512 bash network/scripts/run_network.sh
CONNECTIONS="1 100" REPEATS=10 DURATION=8 MSG_BYTES=512 DEVICE=loopback bash network/scripts/run_network.sh
python3 scripts/analyze_network.py --root results --device loopback --out charts/network
```

Default concurrency is 1 and 100. Add 1000 only after both implementations pass a smoke test on the target host. The audited WSL one-second 1000-connection run failed because some client workers completed zero responses; it is retained as a failed session, not a throughput result. An error aborts the runner; do not use incomplete or failed runs as a complete pair. Servers restart for every run, execution order alternates, and the same client sends the same message size to each server. `HOST` is restricted to 127.0.0.1; upstream and Traditional listeners bind IPv4 wildcard. Default port is 18888.

Both servers echo TCP byte streams using 2048-byte receive chunks, backlog 512 and SO_REUSEADDR. TCP_NODELAY is off on servers and explicitly off on the shared client. Socket buffer sizing uses system defaults. Traditional uses blocking worker threads; io_uring uses a single completion loop with a provided-buffer pool and batching. Throughput differences include architecture, scheduling, buffering, client cost and batching; they cannot be attributed solely to syscalls. Loopback measures shared-host TCP work, not NIC capacity. See [fairness and remaining limitations](docs/network_fairness.md).

## Data and charts

New runs are marked `methodology=traditional-v2` in metadata; network CSV also carries this column. New disk filenames use `scenario__traditional__run01.json` or `scenario__io_uring__run01.json`. Network CSV columns: `methodology,server,connections,repeat,rps,responses_per_second,raw_log,request_count,response_count,measurement_seconds,active_connections`. All workers complete a verified echo handshake before a barrier releases a shared monotonic measurement window. Only sends/responses completed inside that window count. Draining may extend collection time; late responses do not inflate throughput. Every worker must complete a measured response. The handshake is not a sustained steady-state warmup.

Analyzers export per-session statistics: mean, median, sample standard deviation (zero for one sample), and percentage difference `100 * (io_uring / traditional - 1)` for mean and median throughput. Positive percentages favor io_uring. Disk summary fields without a statistic suffix retain their historical median meaning. Completion latency is not end-to-end latency. Charts use medians and require at least 10 unique, positive, matched repeat IDs with positive finite throughput for both implementations. Complete planned smoke sessions appear in summaries but not comparative SVGs. Selected failed/running sessions, missing rows, duplicate IDs, bad worker counts and invalid metrics abort analysis with nonzero exit. Runners persist `status.txt` and expected scenarios/connections/repeats; analyzers check the whole declared session. Use `--device sata`, `--device nvme` or `--device loopback` to explicitly select measurement labels and exclude separately labeled smoke sessions. Hosts/sessions remain separate; no cross-machine averaging.

Outputs: disk_runs.csv, disk_medians.csv, disk_speedups.csv, disk_throughput.svg, disk_clatency.svg, disk_speedup.svg; network_runs.csv, network_medians.csv, network_speedups.csv, network_speedup.svg. Use separate output directories for different protocol settings. SVGs can be inserted into slides; use CSV spread when discussing small differences.

Historical raw measurements must remain unchanged. The reported archive contains SATA 80, NVMe 80 and loopback 60 runs, but **raw results are not present in this checkout**. [Archived tables](docs/legacy_results.md) and [original fairness audit](docs/legacy_network_audit.md) preserve labels/provenance. Old psync QD1 pairs can support historical synchronous-vs-io_uring claims, subject to original conditions; old libaio QD32 and epoll network pairs only support their original comparisons. Neither is evidence for the new Traditional QD32/network design.

```bash
python3 scripts/analyze_disk.py --root results --out charts --legacy
python3 scripts/analyze_network.py --root results --out charts --legacy
```

Legacy mode selects only original sessions without a methodology marker and writes into `charts/legacy/`. The default selects only `traditional-v2`, excluding both original legacy and superseded `traditional-v1`, including their io_uring rows. Remeasure all new disk/network pairs on intended machines before presenting a unified traditional-v2 study; do not merge archived bars into new charts.

For a 20-minute talk: question/design (3 min), disk patterns/concurrency (5), network architecture (4), measured results and spread (5), limitations and conclusions (3). Draw conclusions only after collecting new measurements. No automatic full suite, commit or push is part of refactoring.

## Validation

```bash
python3 -m unittest discover -s tests -v
python3 tests/smoke_network.py   # after network build
bash tests/smoke_disk.sh        # 4 MiB temporary file, eight 1-second checks
```

These smoke tests validate correctness, not performance. See [refactor validation](docs/refactor_validation.md) for the tested environment and outstanding measurements.

## Audit and profiling

Read [benchmark audit](docs/benchmark_audit.md) before official measurements. Readiness is conditional on target-host smoke tests, real storage/cache checks and resource limits; no performance conclusion comes from WSL smoke tests. `PROFILE=1` optionally saves `/usr/bin/time -v` client resources (requires the system `time` utility). Server `/proc` counters are captured before/after each client run. These include setup and collection and are diagnostics, not exact measurement-window CPU rates. Main-thread context counters are not all-worker totals. Use pidstat/mpstat in separate diagnostic runs for per-thread CPU and scheduling evidence. CV is exported; ten repeats alone do not establish significance or causal explanations.
