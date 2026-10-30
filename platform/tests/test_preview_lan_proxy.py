"""Narrow bridge checks; no Device Service/session/model operations."""
import importlib.util
from pathlib import Path
import socket
import threading
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[2] / "scripts" / "preview_lan_proxy.py"
SPEC = importlib.util.spec_from_file_location("preview_lan_proxy", PATH)
proxy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proxy)


class PreviewLanProxyTests(unittest.TestCase):
    def test_only_explicit_rfc1918_ipv4(self):
        for address in ("10.2.3.4", "172.16.0.1", "172.31.255.254", "192.168.1.2"):
            self.assertEqual(proxy.private_ipv4(address), address)
        for address in ("0.0.0.0", "127.0.0.1", "169.254.1.2", "172.32.0.1", "8.8.8.8", "::1", "localhost"):
            with self.assertRaises(ValueError):
                proxy.private_ipv4(address)

    def test_opaque_bidirectional_relay_and_half_close(self):
        client, left = socket.socketpair()
        right, backend = socket.socketpair()
        stopped = threading.Event()
        worker = threading.Thread(target=proxy.relay, args=(left, right, stopped))
        worker.start()
        try:
            client.settimeout(2)
            backend.settimeout(2)
            payload = b"\x00opaque\r\nAuthorization: secret-test\xff"
            client.sendall(payload)
            client.shutdown(socket.SHUT_WR)
            received = bytearray()
            while True:
                chunk = backend.recv(4096)
                if not chunk:
                    break
                received.extend(chunk)
            self.assertEqual(bytes(received), payload)
            backend.sendall(b"response\x00\xff")
            backend.shutdown(socket.SHUT_WR)
            self.assertEqual(client.recv(4096), b"response\x00\xff")
            self.assertEqual(client.recv(4096), b"")
            worker.join(2)
            self.assertFalse(worker.is_alive())
        finally:
            stopped.set()
            client.close()
            backend.close()
            worker.join(2)

    def test_idle_connection_is_bounded(self):
        client, left = socket.socketpair()
        right, backend = socket.socketpair()
        worker = threading.Thread(target=proxy.relay, args=(left, right, threading.Event()),
                                  kwargs={"idle_seconds": 0.05, "lifetime_seconds": 1})
        worker.start()
        try:
            worker.join(1)
            self.assertFalse(worker.is_alive())
        finally:
            client.close()
            backend.close()

    def test_pid_reuse_or_wrong_command_is_not_owned(self):
        instance = "a" * 32
        state = {"script": str(proxy.SCRIPT), "instance": instance, "pid": 123,
                 "process_started": "start one"}
        command = f"python3 {proxy.SCRIPT} serve --instance {instance}"
        with patch.object(proxy, "process_info", return_value=("start one", command)):
            self.assertTrue(proxy.owns_process(state))
        with patch.object(proxy, "process_info", return_value=("start two", command)):
            self.assertFalse(proxy.owns_process(state))
        with patch.object(proxy, "process_info", return_value=("start one", "unrelated process")):
            self.assertFalse(proxy.owns_process(state))


if __name__ == "__main__":
    unittest.main()
