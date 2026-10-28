#!/usr/bin/env python3
"""Deterministic host QMP initialization races; no QEMU or Device Service API.

Uses the existing temporary service fixture and actual DeviceSession methods.
The peer doubles represent host transport scheduling, never guest values.
"""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "platform/tests"), str(ROOT / "platform/tools")]
import device_service
import test_device_service as service_tests
import run_profile_ui_test as profile_runner


class Process:
    pid = 424242

    def poll(self):
        return None


class Socket:
    def settimeout(self, value):
        self.timeout = value


class Connection:
    def __init__(self):
        self.sock = Socket()
        self.closed = False
        self.calls = []

    def cmd(self, name, **arguments):
        self.calls.append((name, arguments))
        return {"return": {"status": "running"}}

    def close(self):
        self.closed = True


class StartupQMPTests(unittest.TestCase):
    module = device_service

    def setUp(self):
        self.fixture = service_tests.DeviceServiceUnitTests(methodName="runTest")
        self.fixture.setUp()
        self.session = self.fixture._stopped_session()
        self.audio_fixture = mock.patch.object(
            self.session, "_prepare_microphone_tone"
        )
        self.audio_fixture.start()
        self.session.state = "booting"
        self.connection = Connection()
        self.creations = []
        self.errors = []

    def tearDown(self):
        # Never let fixture cleanup interpret the synthetic PID as host-owned.
        self.audio_fixture.stop()
        self.session._proc = None
        self.session.pid = None
        self.session._qmp = None
        self.session.state = "stopped"
        self.fixture.tearDown()

    def connect(self, path, timeout):
        self.creations.append((str(path), timeout))
        if len(self.creations) > 1:
            raise RuntimeError("second QMP connection cannot get greeting")
        return self.connection

    def launch(self):
        try:
            self.session._launch()
        except Exception as error:
            self.errors.append(error)

    def test_http_connection_before_launch_is_reused(self):
        inspect_entered = threading.Event()
        continue_inspect = threading.Event()

        def inspect(_pid):
            inspect_entered.set()
            if not continue_inspect.wait(2):
                raise AssertionError("test did not release identity barrier")
            return {"exists": True, "start_token": "hermetic-process"}

        with mock.patch.object(self.module.subprocess, "Popen", return_value=Process()), \
             mock.patch.object(self.module, "inspect_process", side_effect=inspect), \
             mock.patch.object(self.module, "wait_qmp", side_effect=self.connect):
            thread = threading.Thread(target=self.launch)
            thread.start()
            try:
                self.assertTrue(inspect_entered.wait(2))
                self.assertEqual(self.session._qmp_call("query-status"),
                                 {"return": {"status": "running"}})
                self.assertIs(self.session._qmp, self.connection)
            finally:
                continue_inspect.set()
                thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(self.errors, [])
            self.assertEqual(len(self.creations), 1)
            self.assertIs(self.session._qmp, self.connection)

    def test_launch_handshake_blocks_concurrent_http_initializer(self):
        handshake_entered = threading.Event()
        continue_handshake = threading.Event()
        http_lock_attempted = threading.Event()
        http_observed_busy_lock = []
        http_results = []
        http_thread = None

        class ObservedLock:
            def __init__(self):
                self.lock = threading.RLock()

            def __enter__(self):
                if threading.current_thread() is http_thread:
                    acquired = self.lock.acquire(blocking=False)
                    http_observed_busy_lock.append(not acquired)
                    http_lock_attempted.set()
                    if not acquired:
                        self.lock.acquire()
                else:
                    self.lock.acquire()
                return self

            def __exit__(self, *unused):
                self.lock.release()

        self.session._lock = ObservedLock()

        def connect(path, timeout):
            connection = self.connect(path, timeout)
            handshake_entered.set()
            if not continue_handshake.wait(2):
                raise AssertionError("test did not release handshake barrier")
            return connection

        def http_query():
            try:
                http_results.append(self.session._qmp_call("query-status"))
            except Exception as error:
                self.errors.append(error)

        identity = {"exists": True, "start_token": "hermetic-process"}
        with mock.patch.object(self.module.subprocess, "Popen", return_value=Process()), \
             mock.patch.object(self.module, "inspect_process", return_value=identity), \
             mock.patch.object(self.module, "wait_qmp", side_effect=connect):
            launch_thread = threading.Thread(target=self.launch)
            launch_thread.start()
            http_thread = threading.Thread(target=http_query)
            try:
                self.assertTrue(handshake_entered.wait(2))
                http_thread.start()
                self.assertTrue(http_lock_attempted.wait(2))
                # The request must remain blocked until the shared handshake
                # completes; it must never attempt a second QMP connection.
                self.assertEqual(http_observed_busy_lock, [True])
            finally:
                continue_handshake.set()
                launch_thread.join(2)
                if http_thread.ident is not None:
                    http_thread.join(2)
            self.assertFalse(launch_thread.is_alive())
            self.assertFalse(http_thread.is_alive())
            self.assertEqual(self.errors, [])
            self.assertEqual(len(self.creations), 1)
            self.assertEqual(http_results, [{"return": {"status": "running"}}])

    def test_real_startup_failure_keeps_original_timeout_and_error(self):
        identity = {"exists": True, "start_token": "hermetic-process"}
        cause = RuntimeError("sentinel: controller greeting unavailable")
        with mock.patch.object(self.module.subprocess, "Popen", return_value=Process()), \
             mock.patch.object(self.module, "inspect_process", return_value=identity), \
             mock.patch.object(self.module, "wait_qmp", side_effect=cause) as connect:
            with self.assertRaises(self.module.ServiceError) as caught:
                self.session._launch()
        self.assertEqual(caught.exception.code, "qmp_timeout")
        self.assertEqual(caught.exception.status, 504)
        self.assertIs(caught.exception.__cause__, cause)
        self.assertIn(str(cause), str(caught.exception))
        self.assertEqual(self.module.QMP_START_TIMEOUT, 60)
        connect.assert_called_once_with(self.session.qmp_path, timeout=60)
        self.assertIsNone(self.session._qmp)

    def test_real_command_timeout_remains_failure_and_closes_connection(self):
        self.session._proc = Process()
        self.session._qmp = self.connection
        with mock.patch.object(self.connection, "cmd", side_effect=TimeoutError("sentinel timeout")):
            with self.assertRaises(self.module.ServiceError) as caught:
                self.session._qmp_call("screendump", filename="not-created.ppm")
        self.assertEqual(caught.exception.code, "qmp_timeout")
        self.assertEqual(caught.exception.status, 504)
        self.assertTrue(self.connection.closed)
        self.assertIsNone(self.session._qmp)

    def test_existing_socket_with_busy_peer_is_reported_as_did_not_appear(self):
        # A transport-only peer follows QEMU's single accepted client rule:
        # hold the first connection, leaving a second client without greeting.
        with tempfile.TemporaryDirectory(prefix="m5qmp-race-", dir="/tmp") as tmp:
            path = Path(tmp) / "qmp.sock"
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(path))
            listener.listen(2)
            listener.settimeout(2)
            peer_errors = []

            def peer():
                try:
                    connection, _ = listener.accept()
                    with connection, connection.makefile("rb") as stream:
                        connection.sendall(b'{"QMP":{"version":{}}}\n')
                        for line in stream:
                            json.loads(line)
                            connection.sendall(b'{"return":{}}\n')
                except Exception as error:
                    peer_errors.append(error)

            thread = threading.Thread(target=peer)
            thread.start()
            first = profile_runner.QMP(path, timeout=0.2)
            qmp_type = profile_runner.QMP
            socket_factory = socket.socket
            failed_sockets = []

            def make_socket(*args, **kwargs):
                connection = socket_factory(*args, **kwargs)
                failed_sockets.append(connection)
                return connection

            try:
                with mock.patch.object(profile_runner.socket, "socket", side_effect=make_socket), \
                     mock.patch.object(profile_runner, "QMP",
                                       side_effect=lambda p: qmp_type(p, timeout=0.02)):
                    with self.assertRaisesRegex(RuntimeError, "QMP socket did not appear"):
                        profile_runner.wait_qmp(path, timeout=0.05)
                self.assertTrue(failed_sockets)
                self.assertTrue(all(connection.fileno() == -1 for connection in failed_sockets),
                                "failed handshakes must release their socket descriptors")
                self.assertTrue(path.exists())
                self.assertEqual(first.cmd("query-status"), {"return": {}})
            finally:
                first.close()
                listener.close()
                thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(peer_errors, [])


if __name__ == "__main__":
    unittest.main()
