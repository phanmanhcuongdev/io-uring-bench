# Network benchmark fairness audit

## Evidence and scope

Reviewed local, unmodified upstream source (no benchmark reruns or upstream changes):

- [epoll server](https://github.com/frevib/epoll-echo-server/blob/22f325165c3e9749aca85a777cbb8f9b66ea7a27/epoll_echo_server.c), commit `22f325165c3e9749aca85a777cbb8f9b66ea7a27`.
- [io_uring server](https://github.com/frevib/io_uring-echo-server/blob/dc00940baeec2ac577410dfa4d881d0852b01a08/io_uring_echo_server.c), commit `dc00940baeec2ac577410dfa4d881d0852b01a08`.
- [Rust client](https://github.com/haraldh/rust_echo_bench/blob/920f8a5a2ab4d99ebb71bdc1b9fe9e62e303ecdf/src/main.rs), commit `920f8a5a2ab4d99ebb71bdc1b9fe9e62e303ecdf`.
- [Runner](../network/scripts/run_network.sh), upstream Makefiles, existing metadata, CSVs and client/server logs.

The links above reference immutable upstream commits. Local vendor directories are ignored by Git. Source differences below are verified; their performance effects are hypotheses, not measured syscall or CPU profiles. Both C Makefiles default to `-Wall -O2 -D_GNU_SOURCE`; the Rust build script requests release mode. Existing metadata does not prove exact binary build flags or source-to-binary identity.

## Verified server differences

| Area | epoll | io_uring | Possible effect |
|---|---|---|---|
| Socket setup | IPv4 TCP, `INADDR_ANY`, backlog 512; no `SO_REUSEADDR`; accepted sockets use `accept4(..., SOCK_NONBLOCK)` | Same address family, wildcard bind and backlog; sets `SO_REUSEADDR`; accept flags 0, so accepted sockets are blocking | Restart behavior differs. Blocking descriptors here are used through asynchronous ring operations, not a blocking user-space receive loop. Neither server restricts its listener to loopback. |
| TCP options | No explicit `TCP_NODELAY`, socket buffer sizing or reuse option | No explicit `TCP_NODELAY` or socket buffer sizing | Small-message timing depends on kernel TCP defaults; default buffers are not recorded. |
| Event loop | Single thread; `epoll_wait` returns up to 128 events; listener is level triggered, clients use `EPOLLIN | EPOLLET` | Single thread; ring SQ depth 2048; `io_uring_submit_and_wait(..., 1)`, then traverses available CQEs and advances CQ in bulk | Readiness and completion are different work units. Batching and queue limits differ; event count alone does not establish equal work. No SQPOLL, multishot receive/accept or fixed-file registration is requested. |
| Data path | One `recv` of at most 2048 bytes, then one immediate `send` per event | READ completion queues SEND; WRITE completion queues buffer return and next RECV | epoll has direct receive/send syscalls; io_uring batches queued operations across connections but adds send and buffer-return completions. Actual syscall counts were not measured. A one-connection lockstep client offers little cross-connection batching. |
| Buffers | One shared 2048-byte stack buffer, reused after `send` returns | Global 4096 × 2048-byte pool (8 MiB); legacy `PROVIDE_BUFFERS`, `IOSQE_BUFFER_SELECT`, buffer held until send completes | Different memory footprint and buffer bookkeeping. Buffer selection does not establish zero-copy networking. Each successful echo normally adds a buffer-provision SQE/CQE. |
| Connection handling | Accepts one connection per listener event; adds it through `epoll_ctl` | One outstanding single-shot accept, rearmed on completion; queues a receive for each accepted fd | Connection startup and accept scheduling differ. Both serve many sockets on one server thread, not one server thread per connection. |

## Correctness limitations in upstream code

- **epoll edge-trigger handling:** the client event branch does not drain `recv` until `EAGAIN`. Data remaining after one read can stall with edge triggering. `recv <= 0` also treats transient errors like disconnects. The current 64-byte lockstep workload reduces exposure but does not prove correctness for arbitrary TCP segmentation or larger messages.
- **epoll sends and cleanup:** the `send` return value is ignored; partial writes and `EAGAIN` have no retry or writable-event queue. Disconnects use `shutdown` without `close`, leaking descriptors until process exit. Restarting the server for every run bounds accumulation but does not fix it.
- **io_uring sends:** WRITE completions do not inspect `cqe->res` or retain the requested length for partial-send retries. Buffers are returned and reads rearmed even after failed/short sends.
- **io_uring resource/error handling:** helper functions do not check whether `io_uring_get_sqe` returns NULL. Submission/wait results are unchecked in the loop. `-ENOBUFS` exits the server. READ error/EOF handling returns the extracted buffer ID without checking `IORING_CQE_F_BUFFER`, so an error without a selected buffer can return an incorrect buffer. Ring exhaustion and error paths are not equivalent to epoll behavior.
- Both use send flags 0 without explicit SIGPIPE suppression. Neither implementation is a robust production echo server.

These are verified source weaknesses, not evidence that they occurred in the retained runs. Existing logs contain no matching client error/panic or server failure messages, but empty/buffered server logs cannot prove absence of every failure.

## Client bottlenecks and measurement

The Rust client spawns one OS thread per TCP connection. Each thread uses a blocking `TcpStream`, `write_all`, then one `read`, with at most one request awaiting its response. At 1000 connections, client thread scheduling, context switches, TCP processing and server work compete on the same host. There is no CPU affinity or client/server CPU isolation in the runner; a throughput plateau may be client/host limited.

TCP is a byte stream: a valid short `read` is treated as an error rather than completed with `read_exact`. Payload bytes are not checked. A worker error can reduce active concurrency while the client still prints aggregate throughput. A connection panic can leave the main receiver waiting; blocking I/O has no socket timeout. The runner's external timeout bounds execution but does not repair these issues.

The timer sleeps for the requested duration after thread spawning, with no barrier ensuring all connections are ready. Startup overlaps measurement and worker collection can extend beyond the stop time. Totals are divided by the requested duration, not measured wall time; there is no separate warmup interval. Request and response counts can differ at shutdown. Analysis uses completed **responses/sec**, which is preferable to sent requests but retains these timing limitations.

## Existing results and chart selection

| Session under `results/loopback/` | Connections | Runs per engine | Message / requested duration | Main chart |
|---|---:|---:|---|---|
| `compag-20261011T121451Z` | 1 | 10 | 64 bytes / 5 s | Included |
| `compag-20261011T121451Z` | 100 | 10 | 64 bytes / 5 s | Included |
| `compag-20261011T122530Z` | 1000 | 10 | 64 bytes / 5 s | Included |
| `compag-20261011T122219Z` | 1000 | 1 | 64 bytes / 3 s | Excluded smoke test |

The separate `results/sata/compag-20261011T120631Z` pair is also excluded (1 connection, 1 run per engine, 64 bytes / 2 s). Its `sata` label does not make this a storage benchmark.

The three included experiments have matching repeat IDs 1–10 for both engines. Their 60 client logs agree with the CSV rates and configuration and show no error messages. Metadata records the same host, kernel `6.12.111+deb13-amd64`, source commits and workload settings. The 1000-connection experiment was collected in a separate session, so host state may differ. The runner alternates engine order by repeat and restarts servers, reducing order effects without controlling CPU frequency, thermals or background activity.

Analysis keeps all session summaries, including smoke tests, in `charts/network_medians.csv`; no raw results are changed. The main SVG includes only connection counts 1, 100 and 1000 with at least 10 unique, matching positive repeat IDs per engine and finite positive response rates. Duplicate IDs, unmatched runs and incomplete pairs are excluded. Bars sort numerically and omit hostname/timestamp labels; the CSV retains provenance. This is a completeness gate, not automatic proof of TCP correctness or benchmark fairness.

## Interpretation

The chart compares these two implementations under this thread-based loopback workload. It does **not** isolate the cost of epoll versus io_uring or establish NIC throughput, universal superiority, or equivalent implementations. Differences in buffer lifecycle, batching, error handling, client scheduling and measurement timing remain confounders. No upstream fixes, new measurements or profiling were performed in this audit.
