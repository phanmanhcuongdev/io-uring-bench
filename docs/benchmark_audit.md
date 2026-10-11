# Technical audit ? Traditional I/O vs io_uring

Audit date: 2026-10-11. Scope: current source, workload definitions, pinned upstream checkouts and tracked patches, runners, analyzers, tests, README and methodology. The earlier refactor report was not used as evidence of correctness. No official suite, large data preparation, commit or push was performed. Historical raw files were not changed.

## A. Audit findings

Locations refer to the final source or the replacement for removed code; vendor fixes are reproducible through network/patches/*.patch. Critical findings: none identified. High findings below have been fixed; target-host validation remains a condition, not a performance claim.

| ID | Severity | File / location | Cause and effect on measurements | Status |
|---|---|---|---|---|
| F01 | High | network/client/vendor/src/main.rs, setup/window/count loop; network/patches/client.patch | Previously workers started traffic while others were still being spawned/connected, timer began later, and draining responses were counted after stopping; dividing those totals by requested seconds distorted rates and effective connection count. Now every worker completes a verified handshake, waits at a barrier, uses one monotonic deadline, and counts only operations completed inside the common window. Collection duration is separate. | Fixed |
| F02 | High | removed disk/workloads/sequential_direct_qd32.fio; replacement sequential_direct_qd1.fio; disk/scripts/run_disk.sh:93 | 32 synchronous workers repeatedly traversed overlapping offset-zero streams while io_uring traversed one queued stream. Duplicate nearby reads and device-cache reuse could strongly bias the alleged sequential comparison. Replaced with one stream/QD1 on both sides. Partitioning 32 workers would instead produce 32 disjoint streams versus one stream and would still change the access schedule, so it was not adopted as an equivalent test. | Fixed |
| F03 | High | scripts/analyze_disk.py:17, error and worker validation; scripts/analyze_network.py, count/window validation | Disk parser previously printed SKIP for damaged/error JSON and could summarize the surviving runs successfully. It did not validate the number of jobs, so missing workers or grouped QD32 output could be accepted as a valid Traditional run. Now selected invalid JSON/jobs/metrics fail with nonzero exit; v2 Traditional random QD32 requires 32 ungrouped jobs, all performing reads. Network rate must agree with counts/window and active connections. | Fixed |
| F04 | High | disk/scripts/run_disk.sh:25; network/scripts/run_network.sh:76; scripts/analysis_common.py:23 | A late runner failure could leave ten earlier valid pairs while analysis still produced a success chart. There was no declaration of full-session completion. Runners now persist running/failed/complete status and expected workload/connection/repeat sets; analyzers reject selected failed/running sessions, absent CSV/JSON, duplicates, missing or unexpected measurements. No successful subset is silently salvaged. | Fixed |
| F05 | Medium | disk/scripts/run_disk.sh:93 | Previous ordering was Traditional random, Traditional sequential, io_uring random, io_uring sequential; sequential I/O intervened between random comparison partners. Now each workload runs adjacent method pairs, reversing method order each repetition. Fixed scenario order and carry-over still remain. | Fixed |
| F06 | Medium | disk/workloads/random_direct_qd32.fio and short_qd1.fio | Default per-job random maps gave 32 workers independent coverage maps while one io_uring job had one map. Both now explicitly use uniform sampling with replacement (norandommap=1) and reproducible per-job random streams (randrepeat=1). Aggregate address distributions match; exact sequences and cross-worker repetitions do not. | Fixed |
| F07 | Medium | disk/scripts/run_disk.sh:52; random_direct_qd32.fio | 32xQD1 and 1xQD32 have equal upper bounds, not equal time-varying outstanding I/O. Thread scheduling, CPU use, independent random streams and asynchronous queue occupancy differ. This is a concurrent-architecture experiment, not isolated syscall/API overhead. Inspect achieved depths and CPU on target. | Accepted limitation |
| F08 | Medium | disk/scripts/run_disk.sh, cache prewarm; cached_qd1.fio; direct workloads | Prewarming 256 MiB does not prove residency throughout measurement under memory pressure. direct=1 bypasses page cache but not device/controller/virtual-storage caches. Repeated 1 GiB ranges are not cold-media tests. Cached QD1 is valid as prewarmed buffered sequential reading; calling it memory-only requires target evidence. | Accepted limitation; target cache/memory checks required |
| F09 | Medium | network/traditional/blocking_echo_server.c:24,80; network/io_uring/vendor/io_uring_echo_server.c, CQ loop | Traditional can consume many CPU cores; io_uring uses one application completion loop, a provided-buffer pool and batching. Same socket workload does not equal same CPU budget or buffer lifecycle. Differences cannot be attributed solely to syscalls. Both servers correctly handle TCP chunks/partial writes in tested cases. | Accepted limitation |
| F10 | Medium | network/client/vendor/src/main.rs, zero-response check; network/scripts/run_network.sh:13 | The stricter one-second WSL 1000-connection smoke failed: some established client workers completed zero measured responses. Runner returned 1 and retained failed status; no success row was appended. Defaults are now1/100. 1000 is optional and must pass both target servers with the intended window/resources; the short failure does not prove 15-second operation impossible. | Fixed selection; 1000 excluded pending target validation |
| F11 | Medium | network client/server architecture; scripts/proc_snapshot.py; network/scripts/run_network.sh:104 | Old ~20k RPS plateaus do not identify the limiting component. Client threads, server CPU, TCP stack/Nagle/delayed ACK, VM scheduling and loopback CPU contention are competing hypotheses. Added process CPU snapshots and optional client time -v; diagnostic protocol below requires direct resource evidence. | Open investigation, not a correctness blocker for1/100 |
| F12 | Medium | network/io_uring/vendor/io_uring_echo_server.c, accept/read error branches and startup; network/patches/io_uring.patch | Unsupported required ring features previously exited0; accept resource failures were silently rearmed, and transient read errors closed sockets. Unsupported features/resource failures now exit nonzero, transient errors rearm, socket options/arguments are checked. Existing partial-send offsets and buffer-ownership guards were reviewed and retained. Process teardown closes ring/fds on termination; graceful application draining is not promised. | Fixed; teardown semantics accepted |
| F13 | Medium | scripts/analyze_disk.py and analyze_network.py, grouping/statistics | Ten repeats and a small median difference do not imply independent observations, significance, or causation. Groups retain device/host/session/workload/implementation; mean/median/sample stddev and CV are exported. No confidence interval is fabricated. Fixed order, cache carry-over and thermals can correlate repeats. | Accepted limitation; inspect spread/drift and collect longer target runs when needed |
| F14 | Low | scripts/analyze_disk.py, plot labels and latency unit; scripts/svg_plot.py:45 | Long hostname-first labels could truncate the workload/engine distinction, and the latency unit was mojibake. Labels now lead with workload/method (or connection count), full provenance remains in SVG titles/CSV, unit is ASCII us. Renderer uses zero-based nonnegative bar widths and a1x reference for ratios. | Fixed |
| F15 | Medium | network/scripts/build.sh:14; docs/upstream-versions.tsv | Reverse-apply check alone could accept tracked patches plus unrelated source modifications, reducing reproducibility. Build now verifies pinned commit, exact tracked diff and clean index; Cargo dependencies are locked. Fetch/build repeated successfully. | Fixed |
| F16 | Low | disk/scripts/prepare_data.sh:19; network client numeric parsing | dd already uses correct conv=excl,fsync; exclusive creation avoids overwrites and prepare refuses existing undersized targets. Client numeric parse previously fell back to defaults on malformed input; now fails nonzero. Runner also validates arguments and duplicate/empty connection lists. | Verified / Fixed |

No new engine or I/O model was added. Blocking Traditional remains synchronous POSIX I/O. The sequential workload file was removed, not any historical raw measurement. New methodology is traditional-v2; default analyzers reject mixing v1/original legacy into v2 charts. --legacy is only for the original unmarked archive.

## B. Final benchmark design

All disk reads use a regular existing file, offset0, time_based=1, thread=1 and group_reporting=0. Official commands below explicitly use RUNTIME=30, RAMP=5, REPEATS=10; script defaults remain8/2 seconds. File must contain allocated non-sparse data on the intended filesystem.

| Workload | Common work and cache mode | Traditional | io_uring | Main metrics / valid inference |
|---|---|---|---|---|
| cached_qd1 | Sequential4 KiB, 256 MiB, buffered, invalidate=0; prewarm before both | psync, numjobs1, iodepth1 | numjobs1, iodepth1 | MiB/s, IOPS, I/O-weighted mean completion latency; performance of prewarmed buffered reads |
| short_qd1 (Random Direct QD1) | Uniform random4 KiB with replacement, 1 GiB, direct=1, invalidate=1 | psync1x1 | io_uring1x1 | MiB/s, IOPS, mean completion latency; low-concurrency direct random reads |
| random_direct_qd32 | Same distribution/block/range/direct mode as QD1 | psync32 workers x depth1 | io_uring1 job x depth32 | Sum per-job MiB/s/IOPS, weighted completion latency; concurrent architecture, not API-only overhead |
| sequential_direct_qd1 | Sequential128 KiB, 1 GiB, direct=1, invalidate=1 | psync1x1 | io_uring1x1 | MiB/s, IOPS, mean completion latency; one-stream direct reading, no claim about sequentialQD32 |
| TCP loopback C1 | 512-byte lockstep messages,1 verified connection, common15-second window | Blocking accept/recv/send, one worker | Single completion loop / provided buffers | Completed application responses/s; requests/s and counts are integrity/diagnostic metrics |
| TCP loopback C100 | Same,100 verified connections | One blocking worker per connection | Same io_uring server | Aggregate responses/s with scheduling/CPU/stack costs |
| TCP loopback C1000 (conditional) | Same,1000 verified connections |1000 workers required | Same io_uring server | Excluded unless both target implementations pass smoke/resource checks without zero-response workers/errors |

Both servers use IPv4 wildcard listener, backlog512, SO_REUSEADDR,2048-byte receive chunks and default TCP buffer sizing. TCP_NODELAY is false on both servers and explicitly false on client. These are byte-stream echo servers: message framing lives in the shared client, whose write_all/read_exact and content check enforce complete lockstep request/response semantics. Messages larger than a chunk are legal but can change packetization/Nagle effects; do not merge different message-size sessions.

Time-based experiments deliberately allow the faster implementation to complete more work. Equivalent means equal request size/distribution/cache mode/logical range/concurrency limit and measured duration, not equal completed operation counts. Disk per-worker rates are summed once because their time-based intervals are intended to match; large worker start/runtime skew on an overloaded target invalidates the concurrency interpretation. Already-aggregated legacy group reporting is not multiplied by numjobs.

## C. Fairness assessment and causal scope

Ensured: two genuine implementations only; matched per-pair configuration; shared client; partial TCP handling; content verification; confirmed connection startup; common measurement deadline; explicit failure status; adjacent/reversed-order pairs; new schema/methodology separation; exact expected sample identities; no cross-host/session aggregation; raw history preserved.

Not ensured: equal CPU cores consumed, identical random/sequential schedules outside the QD1 pairs, fixed device-cache state, constant CPU frequency, absence of hypervisor contention, identical internal batching/buffers, or constant instantaneous outstanding I/O. One accepted socket per worker is not proof that all workers execute simultaneously. Nagle/delayed ACK stays enabled; it is part of this defined workload rather than a claim about all socket applications. No network latency distribution/p99 is measured. fio clat is mean completion latency, not application end-to-end latency.

The four research questions can be answered to these degrees:

1. **When Traditional wins:** directly supported only by new repeated pairs on named machines/workloads/configurations, with variability reported. No winner is assumed from implementation style.
2. **When io_uring wins:** same requirement; wins may depend on concurrency, cache/media latency, CPU availability and this particular server implementation. It may also lose; benchmark design does not force either outcome.
3. **Why differences arise:** throughput alone cannot establish causality. Use CPU/context-switch/depth/syscall/TCP diagnostics to test hypotheses. Architecture/source differences suggest explanations, not measured attribution by themselves.
4. **Practical use:** evidence can guide these synchronous small-read workloads and these closed-loop echo architectures. It does not support universal advice, NIC throughput, production tail latency, arbitrary application pipelines, or all possible io_uring implementations. No results for writes, cold media, queued sequential reading, SQPOLL or unrelated technologies are claimed.

### Investigating the old ~20k responses/s plateau

The original220 raw measurements are absent from this checkout, so their CPU/run state cannot be reconstructed. Do not claim the historical client was the bottleneck.

A current one-second WSL C100 smoke produced818,673 Traditional responses/s versus51,017 io_uring responses/s. This refutes a universal20k cap for the *current* shared client on this WSL host; it does not identify the cause on the original machine or measure reliable comparative performance. Process snapshots bracketing that client invocation showed Traditional7.74 CPU-seconds in1.156 wall-seconds versus io_uring0.99 in1.149. The counters support actual multicore use by Traditional; they include handshake/setup/drain, and therefore are not exact measurement-window utilization or syscall-cost attribution. No ten-repeat CPU study was run.

Verification procedure on the target:

- Keep kernel/VM allocation/message size/duration/profile setting fixed. Compare request counts/rates, response counts/rates, declared and handshake-verified connections, collection duration, errors and every worker's nonzero-response gate. The difference between requests and responses can include the intentionally excluded final response at the deadline; it does not automatically indicate packet loss.
- Run PROFILE=1 diagnostic pairs; inspect client .client.resources for user/system CPU, elapsed, RSS and voluntary/involuntary context switches. Inspect .server.before.json/.after.json for CPU deltas divided by the *snapshot interval*. More than one CPU-second per wall-second indicates multicore use. /proc status context-switch fields are main-thread counters, not all-worker sums. Profiling changes overhead and must stay in separate sessions from primary measurements.
- For time-resolved evidence, observe both client and server with pidstat -u -w -t and host cores with mpstat -P ALL during a longer diagnostic run. Look for per-core saturation, client worker starvation, server single-core saturation, CPU steal/host contention, blocked workers and increasing context switches. Record exact process IDs and CPU allocation.
- Inspect ss -tinp for established socket counts, Send-Q/Recv-Q and TCP information while traffic runs. Default Nagle/delayed ACK and chunk/segment boundaries are hypotheses for small-message stalls; errors or queues/CPU traces are needed before claiming this cause. Use the existing MSG_BYTES control for separately labeled diagnostic sessions, not a combined chart.
- If host cores are sufficient, use explicit disjoint CPU sets for client/server in a separate diagnostic experiment to test shared-host contention. This changes the protocol and must not be merged into primary results. Optional perf stat can collect cycles/instructions/context switches and syscall tracepoints if permissions allow; record profiler overhead. Neither lower RPS nor a plateau alone proves a client or syscall bottleneck.

## D. Validation results

Current environment: Windows Python3.14 plus WSL Ubuntu, Linux6.18.33.2-microsoft-standard-WSL2, GCC/liburing, fio3.41, Rust/Cargo1.93. This is not evidence for Debian/Proxmox hardware performance.

| Check | Result / scope |
|---|---|
| Bash syntax | All disk/network/setup/smoke scripts passed bash -n |
| Build | Traditional built with Wall/Wextra/Werror/O2/pthreads; patched io_uring built with upstream Wall/O2; shared Rust release client built with --locked |
| Source pinning | Repeated fetch/build accepted exactly the pinned commits and tracked patches; unknown tracked modifications are rejected |
| Regression |15 analyzer tests passed on Windows, Linux-only4 client tests skipped there; all19 passed in WSL |
| Client fault injection | Fragmented reply accepted; wrong handshake payload and invalid CLI failed; a deliberately delayed second response was excluded from the1-second count |
| Network correctness | Both servers passed fragmented64 KiB echo, half-close,100 concurrent peers, disconnect and shutdown with100 idle sockets |
| fio correctness | All8 new workload/method configurations passed1-second tests on a4 MiB temporary regular file; QD32 Traditional produced32 successful jobs and io_uring one job |
| Analyzer against real fio | Parsed all8 actual smoke JSONs, exported summaries and generated no comparative chart because declared repeats=1 |
| Network runner + analyzer | Default1/100 complete v2 session passed; rates/counts/window/connections parsed correctly; no comparative chart at one repeat |
| Network1000 | One-second Traditional test failed its zero-response-worker gate, returned1 and persisted failed status. io_uring1000 was not attempted in that aborted v2 session. It is not accepted throughput |
| Diagnostic counters | Server before/after CPU snapshots and PROFILE=1 client time -v files were generated in short runs; no causal/full profiling study |
| Exit codes / missing data | Tests cover corrupt JSON, incomplete pairs, wrong/grouped worker count, missing CSV, failed status, duplicates, rate/count mismatch and stale chart cleanup; failures return nonzero |
| SVG integrity | Fixture-based charts represent medians/ratios, use1x reference; full values/provenance retained; no smoke comparative SVG |

No physical SATA/NVMe end-to-end production-range test, sustained1000-connection test, cold-media check, cache-residency proof,10-repeat confidence study, NIC experiment or hypervisor isolation validation was performed. No raw block device was written and no1 GiB benchmark file was generated. Small temporary fixture files are not benchmark results; failed/smoke raw logs remain separate and unchanged.

## E. Readiness decision

**CONDITIONALLY READY** for the v2 disk design and Network1/100. No identified Critical/High correctness issue remains open in that selected design. This is permission to proceed through target validation, not a claim that WSL smoke performance generalizes.

Before official measurement:

1. Confirm SATA_FILE and NVME_FILE map to the intended distinct storage, including Proxmox host backing devices/cache modes if virtualized. Guest labels alone do not prove physical SATA/NVMe identity.
2. Confirm full file allocation, O_DIRECT support, kernel io_uring feature/policy support, sufficient page-cache headroom and stable CPU/power/VM allocation. Do not call cached QD1 memory-only without residency/pressure evidence, or direct tests cold-media throughput.
3. Smoke-test both implementations on target at production-range settings; inspect errors, number of fio jobs, per-job runtimes and achieved iodepth_level rather than assuming32 real outstanding requests.
4. For network, use1/100 by default. Add1000 only if both target servers pass intended-duration smoke without setup/error/zero-response workers and fd/thread/cgroup/CPU/memory limits are recorded. Otherwise report it as excluded, do not salvage a successful subset.
5. Inspect per-run spread, CV, drift and thermal/system activity. If30-second/15-second runs are still unstable, change the explicitly recorded protocol and rerun the whole pair/session. Ten repeats are a completeness rule, not statistical certainty.

## F. Exact Linux commands

Run from the repository root on the target Linux host. Commands below are supplied for manual execution only; none of the official suites were executed during audit. Replace variables with real regular-file paths and inspect mounts; no mount point is assumed.

```bash
bash scripts/setup.sh
bash network/scripts/fetch_upstream.sh
bash network/scripts/build.sh
for f in disk/scripts/*.sh network/scripts/*.sh scripts/*.sh tests/*.sh; do
  bash -n "$f" || exit 1
done
python3 -m unittest discover -s tests -v
python3 tests/smoke_network.py
bash tests/smoke_disk.sh
uname -a
fio --version
lscpu
lsblk -o NAME,MODEL,SIZE,ROTA,TRAN,FSTYPE,MOUNTPOINTS
free -h
ulimit -n
ulimit -u
cat /proc/sys/kernel/io_uring_disabled 2>/dev/null || true
cat /sys/fs/cgroup/pids.max 2>/dev/null || true
```

Supply paths on the verified filesystems; existing parent directories must exist for findmnt:

```bash
export SATA_FILE='/replace/with/absolute/path/on/sata/disk_test.bin'
export NVME_FILE='/replace/with/absolute/path/on/nvme/disk_test.bin'
findmnt -T "$(dirname "$SATA_FILE")"
findmnt -T "$(dirname "$NVME_FILE")"
# Explicit preparation writes allocated regular files; skip if already prepared.
DATA_FILE="$SATA_FILE" bash disk/scripts/prepare_data.sh
DATA_FILE="$NVME_FILE" bash disk/scripts/prepare_data.sh
stat -c '%n size=%s allocated_blocks=%b block_unit=%B' "$SATA_FILE" "$NVME_FILE"
# Inspect allocation/extents and storage caches with appropriate target filesystem tools.
# Confirm no compressed/sparse/virtual backing artifact invalidates the storage interpretation.
DATA_FILE="$SATA_FILE" DEVICE=sata-smoke REPEATS=1 RUNTIME=2 RAMP=0 bash disk/scripts/run_disk.sh
DATA_FILE="$NVME_FILE" DEVICE=nvme-smoke REPEATS=1 RUNTIME=2 RAMP=0 bash disk/scripts/run_disk.sh
python3 scripts/analyze_disk.py --root results --device sata-smoke --out charts/sata-smoke
python3 scripts/analyze_disk.py --root results --device nvme-smoke --out charts/nvme-smoke
# Review raw fio iodepth_level, runtimes and job counts before official measurements.
DATA_FILE="$SATA_FILE" DEVICE=sata REPEATS=10 RUNTIME=30 RAMP=5 bash disk/scripts/run_disk.sh
DATA_FILE="$NVME_FILE" DEVICE=nvme REPEATS=10 RUNTIME=30 RAMP=5 bash disk/scripts/run_disk.sh
python3 scripts/analyze_disk.py --root results --device sata --out charts/v2-sata
python3 scripts/analyze_disk.py --root results --device nvme --out charts/v2-nvme
```

Network target validation and official1/100 protocol:

```bash
CONNECTIONS="1 100" DEVICE=network-smoke REPEATS=1 DURATION=3 MSG_BYTES=512 bash network/scripts/run_network.sh
python3 scripts/analyze_network.py --root results --device network-smoke --out charts/network-smoke
# Optional: target validation only; if this fails, keep1000 excluded.
CONNECTIONS="1000" DEVICE=network1000-smoke REPEATS=1 DURATION=15 MSG_BYTES=512 bash network/scripts/run_network.sh
# Do not include1000 in official levels without reviewing both implementations' success.
NETWORK_LEVELS="1 100"
CONNECTIONS="$NETWORK_LEVELS" DEVICE=loopback REPEATS=10 DURATION=15 MSG_BYTES=512 bash network/scripts/run_network.sh
python3 scripts/analyze_network.py --root results --device loopback --out charts/v2-network
```

If a selected session fails, analysis intentionally exits nonzero even if earlier measurements exist. Preserve it; rerun under a new explicit DEVICE label and select that label rather than deleting failed rows/status or changing metadata to complete. Session names remain separate in CSV/SVG even under one label. Superseded v1 data and original legacy stay outside default analysis.

Separate diagnostic commands (optional sysstat tools are not benchmark dependencies):

```bash
# PROFILE requires /usr/bin/time; install the system time package explicitly if missing.
PROFILE=1 CONNECTIONS="1 100" DEVICE=network-profile REPEATS=1 DURATION=15 MSG_BYTES=512 bash network/scripts/run_network.sh
# In another terminal during a diagnostic run, obtain exact PIDs from ps, then set:
ps -eo pid,comm,args
# export SERVER_PID='<actual numeric server PID>' CLIENT_PID='<actual numeric client PID>'
pidstat -u -w -t -p "$SERVER_PID,$CLIENT_PID" 1
mpstat -P ALL 1
ss -tinp state established '( sport = :18888 or dport = :18888 )'
```

Stop interactive monitors manually. Keep diagnostic/profile data separate from the primary study. Findings based only on source or resource counters are hypotheses unless corroborated by controlled measurements on the target.
