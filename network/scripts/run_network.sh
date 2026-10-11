#!/usr/bin/env bash
# Compare local upstream TCP echo servers, identical client workload and duration.
# Server and client on same host use loopback; results are NOT real network-card throughput.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLIENT="$ROOT/network/client/vendor/target/release/echo_bench"
EPOLL="$ROOT/network/traditional/vendor/epoll_echo_server"
URING="$ROOT/network/io_uring/vendor/io_uring_echo_server"
for bin in "$CLIENT" "$EPOLL" "$URING"; do [[ -x "$bin" ]] || { echo "Missing $bin (run network/scripts/build.sh)" >&2; exit 1; }; done
PORT="${PORT:-18888}"; HOST="${HOST:-127.0.0.1}"
REPEATS="${REPEATS:-10}"; DURATION="${DURATION:-8}"; MSG_BYTES="${MSG_BYTES:-512}"
DEVICE="${DEVICE:-sata}"
[[ "$DEVICE" =~ ^[A-Za-z0-9_-]+$ ]] || exit 1
for v in "$PORT" "$REPEATS" "$DURATION" "$MSG_BYTES"; do [[ "$v" =~ ^(0|[1-9][0-9]*)$ ]] && (( v>0 )) || { echo "Invalid numeric argument: $v" >&2; exit 1; }; done
(( PORT <= 65535 )) || { echo 'PORT must be <=65535' >&2; exit 1; }
[[ "$HOST" == '127.0.0.1' ]] || { echo 'This local runner supports HOST=127.0.0.1 only' >&2; exit 1; }
# Refuse occupied ports rather than accidentally measuring an unrelated server.
python3 - "$HOST" "$PORT" <<'PYPORT'
import socket, sys
with socket.socket() as sock:
    sock.bind((sys.argv[1], int(sys.argv[2])))
PYPORT
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$ROOT/results/$DEVICE/$(hostname)-$STAMP/network"
mkdir -p "$OUT"
printf 'server,connections,repeat,rps,responses_per_second,raw_log\n' > "$OUT/runs.csv"
# A thousand TCP connections can exceed the default process fd limit.
if (( $(ulimit -n) < 8192 )); then
  ulimit -n 8192 2>/dev/null || echo 'WARNING: cannot raise open-file limit; 1000 clients may fail' >&2
fi
{
  echo "hostname=$(hostname)"
  echo "timestamp_utc=$STAMP"
  echo "kernel=$(uname -r)"
  echo "host=$HOST port=$PORT duration_sec=$DURATION message_bytes=$MSG_BYTES repeats=$REPEATS"
  for d in traditional io_uring client; do
    git -C "$ROOT/network/$d/vendor" rev-parse HEAD
    git -C "$ROOT/network/$d/vendor" status --short
  done
} > "$OUT/metadata.txt"
SERVER_PID=''
stop_server() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    SERVER_PID=''
  fi
}
trap stop_server EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
for connections in ${CONNECTIONS:-1 100 1000}; do
  for ((i=1; i<=REPEATS; i++)); do
    if (( i%2 )); then methods=(epoll io_uring); else methods=(io_uring epoll); fi
    for method in "${methods[@]}"; do
      stop_server
      if [[ "$method" == epoll ]]; then bin="$EPOLL"; else bin="$URING"; fi
      log="$OUT/${method}_c${connections}_run$(printf '%02d' "$i").log"
      "$bin" "$PORT" >"$log.server" 2>&1 & SERVER_PID=$!
      # Wait for server readiness, but avoid external tools.
      ready=0
      for _ in $(seq 1 30); do
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then break; fi
        if (echo > "/dev/tcp/$HOST/$PORT") 2>/dev/null; then ready=1; break; fi
        sleep 0.1
      done
      ((ready)) || { echo "Server not ready: $method (see $log.server)" >&2; exit 1; }
      echo "[$i/$REPEATS] $method connections=$connections"
      timeout --signal=TERM --kill-after=5s "$((DURATION + 15))s" "$CLIENT" --address "$HOST:$PORT" --number "$connections" --duration "$DURATION" --length "$MSG_BYTES" | tee "$log"
      kill -0 "$SERVER_PID" 2>/dev/null || { echo "Server exited during measurement: $method" >&2; exit 1; }
      python3 - "$method" "$connections" "$i" "$log" "$OUT/runs.csv" <<'PY'
import csv,re,sys
method,connections,repeat,log,dest=sys.argv[1:]
txt=open(log).read()
m=re.search(r'Speed:\s*([0-9]+)\s+request/sec,\s*([0-9]+)\s+response/sec',txt)
if not m: raise SystemExit(f'Could not parse throughput: {log}')
with open(dest,'a',newline='') as f:
    csv.writer(f).writerow([method,connections,repeat,m[1],m[2],log])
PY
      stop_server
      sleep 0.2
    done
  done
done
echo "Network output: $OUT"
