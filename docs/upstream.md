# Third-party source and reproducibility

Current dependencies: fio, liburing, and two MIT-licensed pinned upstream repositories listed in upstream-versions.tsv: frevib/io_uring-echo-server and haraldh/rust_echo_bench. The blocking Traditional server is maintained here; there is no epoll runtime/build dependency.

fetch_upstream.sh clones and verifies pinned commits, refusing unrecognized tracked modifications. build.sh applies network/patches/io_uring.patch and client.patch idempotently before building. network/client/Cargo.lock pins Rust dependencies; build uses --locked. Patches are part of the methodology; rerun both methods if they change. Keep upstream licenses with downloaded source. Vendor source and build products are ignored; tracked patches make clean checkouts reproducible. Metadata includes binary hashes and upstream Git status.

For an upstream upgrade, review source, update manifest, regenerate/review patches and remeasure. Do not silently change revisions. Historical epoll provenance remains in legacy_results.md and legacy_network_audit.md solely to identify archived results. No historical raw data is deleted by these scripts.

The project has no license for its original glue code; public availability does not automatically grant reuse permission.
