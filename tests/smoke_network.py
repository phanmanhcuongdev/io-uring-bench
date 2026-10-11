"""Linux correctness smoke test, not a throughput measurement."""
import concurrent.futures
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]

def check(binary):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0)); port=probe.getsockname()[1]
    proc=subprocess.Popen([str(binary),str(port)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            if proc.poll() is not None: raise RuntimeError(proc.stdout.read().decode())
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2): pass
                break
            except OSError: time.sleep(.1)
        else: raise RuntimeError('readiness timeout')
        def echo(_):
            payload=bytes(range(256))*256
            with socket.create_connection(('127.0.0.1',port),timeout=5) as client:
                client.settimeout(5)
                for start in range(0,len(payload),317): client.sendall(payload[start:start+317])
                client.shutdown(socket.SHUT_WR)
                received=bytearray()
                while True:
                    chunk=client.recv(193)
                    if not chunk: break
                    received.extend(chunk)
                assert received == payload, (len(received),len(payload))
        echo(0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as workers:
            list(workers.map(echo,range(100)))
        # Peer closes without reading; next client must still work.
        with socket.create_connection(('127.0.0.1',port),timeout=5) as client:
            client.sendall(b'x'*8192)
        echo(0)
        idle=[socket.create_connection(('127.0.0.1',port),timeout=5) for _ in range(100)]
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
        for client in idle: client.close()
        assert proc.returncode in (0,-signal.SIGTERM), proc.returncode
        print(f'PASS {binary.name}: fragmented 64KiB echo, half-close, 100 workers, disconnect, idle shutdown')
    finally:
        if proc.poll() is None: proc.kill(); proc.wait()

if __name__=='__main__':
    check(ROOT/'network/traditional/blocking_echo_server')
    check(ROOT/'network/io_uring/vendor/io_uring_echo_server')
