# Third-party components & provenance

- `fio`: https://github.com/axboe/fio — benchmark tool, installed via distro package manager. The distro carries its corresponding license.
- `liburing`: https://github.com/axboe/liburing — userspace library provided by distro, subject to upstream licensing.
- `frevib/epoll-echo-server`: https://github.com/frevib/epoll-echo-server — MIT-licensed C echo server.
- `frevib/io_uring-echo-server`: https://github.com/frevib/io_uring-echo-server — MIT-licensed C echo server; requires certain io_uring kernel capabilities.
- `haraldh/rust_echo_bench`: https://github.com/haraldh/rust_echo_bench — MIT-licensed Rust benchmark client.

`network/scripts/fetch_upstream.sh` clones each repository into a local ignored `vendor/` folder and writes the exact commit hashes to `docs/upstream-versions.tsv`. When reproducing a run, reuse the recorded commits (e.g. `git -C network/.../vendor checkout <hash>` after fetching full history if necessary).

Do not present upstream code as originally authored here. If you eventually vendor source into this repository, include the complete license texts and attribution.

The local LICENSE files for all three fetched repositories were checked and contain the MIT license at the commits recorded in `upstream-versions.tsv`. Recheck the license if these commits change. Local upstream checkouts and their licenses are preserved but excluded from the first commit; they are independent nested Git repositories, not submodules. Python analysis uses only the standard library.
