# Measurement protocol

1. Confirm device model, filesystem, kernel and fio version in the automatically generated metadata.
2. Ensure `DATA_FILE` resides physically on the desired device. Do not benchmark the system's raw block devices; this suite uses only a regular file.
3. Warm up (ramp) is excluded from measurement. For cache tests, the 256 MiB working set is read before each engine to prewarm page cache.
4. Keep block size, access distribution, cache mode, request depth and number of workers identical **within a pair**. Each run alternates engine order.
5. Compare `psync` vs io_uring at QD 1; compare `libaio` vs io_uring at QD 32. Never interpret `psync` at QD 32 as proof of 32 outstanding I/Os.
6. Run the full suite 10 times per engine/workload. Report median and spread; don't cherry-pick a run.
7. If upstream/network binaries fail to build/run, mark network data unavailable rather than claiming numbers.
8. Use graphics from `charts/` only after real measurements. No pre-filled benchmark outcomes.
