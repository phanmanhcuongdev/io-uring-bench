# Third-party components & provenance

This project reuses existing open-source components.

## Dependencies

- [fio](https://github.com/axboe/fio) — Disk I/O benchmarking tool, installed through the system package manager.
- [liburing](https://github.com/axboe/liburing) — Userspace interface for Linux io_uring, installed through the system package manager.
- [frevib/epoll-echo-server](https://github.com/frevib/epoll-echo-server) — MIT-licensed C echo server.
- [frevib/io_uring-echo-server](https://github.com/frevib/io_uring-echo-server) — MIT-licensed C echo server.
- [haraldh/rust_echo_bench](https://github.com/haraldh/rust_echo_bench) — MIT-licensed Rust benchmark client.

## Reproducibility

The file `docs/upstream-versions.tsv` is the source of truth for pinned upstream versions.

Run:

```bash
bash network/scripts/fetch_upstream.sh
```

The fetch script:

1. Clones missing upstream repositories into their respective `vendor/` directories.
2. Checks out the exact commit SHA recorded in the manifest.
3. Verifies existing repositories against the recorded commit.
4. Refuses to overwrite modified tracked source files.
5. Does not silently update upstream dependencies or rewrite the manifest.

To intentionally upgrade an upstream dependency, review the changes, update its commit SHA in the manifest, rebuild and rerun the relevant benchmarks.

## Licensing

The three network upstream repositories are MIT-licensed at the recorded revisions.

Their source code, Git metadata and original license files remain within local `vendor/` directories, which are excluded from this repository.

If upstream source is distributed directly in the future, retain the corresponding copyright and license notices.

The scripts, fio workload definitions, analysis utilities and documentation maintained in this repository are separate from those upstream projects.

## Limitations

Pinning source revisions improves reproducibility but does not guarantee identical measurements across machines.

Results also depend on the kernel, compiler, runtime libraries, CPU, storage hardware, filesystem and operating environment.