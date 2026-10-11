"""Fault-injection peers validate the shared client, never serve as benchmark engines."""
import os, re, socket, subprocess, threading, time, unittest
from pathlib import Path
CLIENT=Path(__file__).resolve().parents[1]/'network/client/vendor/target/release/echo_bench'

@unittest.skipUnless(os.name=='posix' and CLIENT.exists(),'requires Linux release client')
class ClientTests(unittest.TestCase):
    def run_peer(self,handler):
        listener=socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen()
        port=listener.getsockname()[1]
        failures=[]
        def serve():
            try:
                with listener:
                    listener.settimeout(5)
                    conn,_=listener.accept()
                    with conn:
                        conn.settimeout(5); handler(conn)
            except (BrokenPipeError,ConnectionResetError): pass
            except Exception as exc: failures.append(exc)
        thread=threading.Thread(target=serve,daemon=True); thread.start()
        result=subprocess.run([str(CLIENT),'--address',f'127.0.0.1:{port}',
                               '--number','1','--duration','1','--length','128'],
                              capture_output=True,text=True,timeout=10)
        thread.join(timeout=6)
        self.assertFalse(thread.is_alive()); self.assertFalse(failures,failures)
        return result

    @staticmethod
    def frame(conn):
        payload=b''
        while len(payload)<128:
            data=conn.recv(128-len(payload))
            if not data: return None
            payload+=data
        return payload

    def test_fragmented_echo(self):
        def peer(conn):
            while True:
                payload=self.frame(conn)
                if payload is None: break
                conn.sendall(payload[:17]); conn.sendall(payload[17:])
        result=self.run_peer(peer)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Active connections: 1',result.stdout)
        self.assertIn('Measurement seconds: 1.000000',result.stdout)

    def test_wrong_handshake_payload_fails(self):
        def peer(conn):
            self.frame(conn); conn.sendall(b'z'*128)
        result=self.run_peer(peer)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('Speed:',result.stdout)

    def test_late_response_excluded_from_count(self):
        def peer(conn):
            conn.sendall(self.frame(conn))  # premeasurement handshake
            conn.sendall(self.frame(conn))  # first measured response
            payload=self.frame(conn)
            time.sleep(1.2)
            conn.sendall(payload)           # completes after the common deadline
        result=self.run_peer(peer)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertRegex(result.stdout,r'Responses: 1\b')
        self.assertRegex(result.stdout,r'Speed: 2\.000000 request/sec, 1\.000000 response/sec')

    def test_invalid_arguments_nonzero(self):
        result=subprocess.run([str(CLIENT),'--unknown'],capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0)
        result=subprocess.run([str(CLIENT),'--length','invalid'],capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0)

if __name__=='__main__': unittest.main()
