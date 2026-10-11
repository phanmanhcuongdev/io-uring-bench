#!/usr/bin/env bash
# Compare blocking POSIX and io_uring echo servers with one shared client workload.
# Server and client on same host use loopback; results are NOT real network-card throughput.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLIENT="$ROOT/network/client/vendor/target/release/echo_bench"
TRADITIONAL="$ROOT/network/traditional/blocking_echo_server"
URING="$ROOT/network/io_uring/vendor/io_uring_echo_server"
for bin in "$CLIENT" "$TRADITIONAL" "$URING"; do [[ -x "$bin" ]] || { echo "Missing $bin (run network/scripts/build.sh)" >&2; exit 1; }; done
PORT="${PORT:-18888}"; HOST="${HOST:-127.0.0.1}"
REPEATS="${REPEATS:-10}"; DURATION="${DURATION:-8}"; MSG_BYTES="${MSG_BYTES:-512}"
DEVICE="${DEVICE:-loopback}"
CONNECTIONS="${CONNECTIONS:-1 100}"
PROFILE="${PROFILE:-0}"
[[ "$PROFILE" == 0 || "$PROFILE" == 1 ]] || exit 1
if [[ "$PROFILE" == 1 ]]; then [[ -x /usr/bin/time ]] || { echo "PROFILE needs /usr/bin/time" >&2; exit 1; }; fi
[[ "$DEVICE" =~ ^[A-Za-z0-9_-]+$ ]] || exit 1
for v in "$PORT" "$REPEATS" "$DURATION" "$MSG_BYTES"; do [[ "$v" =~ ^(0|[1-9][0-9]*)$ ]] && (( v>0 )) || { echo "Invalid numeric argument: $v" >&2; exit 1; }; done
(( PORT <= 65535 )) || { echo 'PORT must be <=65535' >&2; exit 1; }
declare -A seen_connections=()
read -r -a levels <<< "$CONNECTIONS"
(( ${#levels[@]} > 0 )) || { echo 'Empty CONNECTIONS' >&2; exit 1; }
for level in "${levels[@]}"; do
  [[ "$level" == 1 || "$level" == 100 || "$level" == 1000 ]] || { echo 'Supported levels: 1, 100, 1000' >&2; exit 1; }
  [[ -z "${seen_connections[$level]:-}" ]] || { echo 'Duplicate CONNECTIONS' >&2; exit 1; }
  seen_connections[$level]=1
done
[[ "$HOST" == '127.0.0.1' ]] || { echo 'This local runner supports HOST=127.0.0.1 only' >&2; exit 1; }
# Refuse occupied ports rather than accidentally measuring an unrelated server.
python3 - "$HOST" "$PORT" <<'PYPORT'
import socket, sys
with socket.socket() as sock:
    sock.bind((sys.argv[1], int(sys.argv[2])))
PYPORT
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$ROOT/results/$DEVICE"
SESSION="$(mktemp -d "$ROOT/results/$DEVICE/$(hostname)-$STAMP-XXXXXX")"
OUT="$SESSION/network"
mkdir -p "$OUT"
echo running > "$OUT/status.txt"
printf 'methodology,server,connections,repeat,rps,responses_per_second,raw_log,request_count,response_count,measurement_seconds,active_connections\n' > "$OUT/runs.csv"
# A thousand TCP connections can exceed the default process fd limit.
if (( $(ulimit -n) < 8192 )); then
  ulimit -n 8192 2>/dev/null || echo 'WARNING: cannot raise open-file limit; 1000 clients may fail' >&2
fi
{
  echo "methodology=traditional-v2"
  echo "repeats=$REPEATS"
  echo "duration_sec=$DURATION"
  echo "message_bytes=$MSG_BYTES"
  echo "connections=$CONNECTIONS"
  echo "profile=$PROFILE"
  echo "timing=verified_handshake_barrier_monotonic_deadline"
  echo "tcp_nodelay=0 server_buffer=2048 client=thread_per_connection"
  sha256sum "$CLIENT" "$TRADITIONAL" "$URING"
  echo "hostname=$(hostname)"
  echo "timestamp_utc=$STAMP"
  echo "kernel=$(uname -r)"
  echo "fd_limit=$(ulimit -n) thread_limit=$(ulimit -u)"
  lscpu || true
  sysctl net.ipv4.tcp_rmem net.ipv4.tcp_wmem net.core.rmem_default net.core.wmem_default 2>/dev/null || true
  echo "host=$HOST port=$PORT duration_sec=$DURATION message_bytes=$MSG_BYTES repeats=$REPEATS"
  for d in io_uring client; do
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
finish() {
  rc=$?
  stop_server
  if (( rc != 0 )); then echo "failed exit=$rc" > "$OUT/status.txt"; fi
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
for connections in $CONNECTIONS; do
  [[ "$connections" =~ ^[1-9][0-9]*$ ]] && (( connections <= 1000 )) || { echo 'Connections must be 1..1000' >&2; exit 1; }
  for ((i=1; i<=REPEATS; i++)); do
    if (( i%2 )); then methods=(traditional io_uring); else methods=(io_uring traditional); fi
    for method in "${methods[@]}"; do
      stop_server
      if [[ "$method" == traditional ]]; then bin="$TRADITIONAL"; else bin="$URING"; fi
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
      client_cmd=("$CLIENT" --address "$HOST:$PORT" --number "$connections" --duration "$DURATION" --length "$MSG_BYTES")
      if [[ "$PROFILE" == 1 ]]; then client_cmd=(/usr/bin/time -v -o "$log.client.resources" "${client_cmd[@]}"); fi
      python3 "$ROOT/scripts/proc_snapshot.py" "$SERVER_PID" > "$log.server.before.json"
      timeout --signal=TERM --kill-after=5s "$((DURATION + 60))s" "${client_cmd[@]}" 2>&1 | tee "$log"
      python3 "$ROOT/scripts/proc_snapshot.py" "$SERVER_PID" > "$log.server.after.json"
      kill -0 "$SERVER_PID" 2>/dev/null || { echo "Server exited during measurement: $method" >&2; exit 1; }
      python3 - "$method" "$connections" "$i" "$log" "$OUT/runs.csv" <<'PY'
import csv,re,sys
method,connections,repeat,log,dest=sys.argv[1:]
txt=open(log).read()
m=re.search(r'Speed:\s*([0-9.]+)\s+request/sec,\s*([0-9.]+)\s+response/sec',txt)
if not m: raise SystemExit(f'Could not parse throughput: {log}')
def field(name):
    found=re.search(r'^'+name+r':\s*([0-9.]+)$',txt,re.M)
    if not found: raise SystemExit(f'Missing {name}: {log}')
    return found[1]
active=field('Active connections')
if int(active) != int(connections): raise SystemExit('Active connection mismatch')
with open(dest,'a',newline='') as f:
    csv.writer(f).writerow(["traditional-v2",method,connections,repeat,m[1],m[2],log,field('Requests'),field('Responses'),field('Measurement seconds'),active])
PY
      stop_server
      sleep 0.2
    done
  done
done
echo complete > "$OUT/status.txt"
echo "Network output: $OUT"
