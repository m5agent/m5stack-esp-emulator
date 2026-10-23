#!/usr/bin/env python3
from __future__ import annotations

import http.client
import io
import json
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

import network_sandbox  # noqa: E402


class NetworkSandboxTests(unittest.TestCase):
    def test_non_linux_refuses_to_run(self):
        with mock.patch.object(network_sandbox.sys, "platform", "darwin"):
            with self.assertRaisesRegex(
                network_sandbox.SandboxError,
                "requires Linux",
            ):
                network_sandbox.run({}, ["/bin/true"])

    def test_unshare_failure_refuses_to_run_command(self):
        called = False

        def should_not_run(*_args, **_kwargs):
            nonlocal called
            called = True
            raise AssertionError("command must not start")

        with (
            mock.patch.object(network_sandbox.sys, "platform", "linux"),
            mock.patch.object(
                network_sandbox.os,
                "unshare",
                side_effect=PermissionError("denied"),
                create=True,
            ),
            mock.patch.object(
                network_sandbox.os,
                "CLONE_NEWNET",
                0x40000000,
                create=True,
            ),
            mock.patch.object(
                network_sandbox.subprocess,
                "Popen",
                side_effect=should_not_run,
            ),
        ):
            with self.assertRaisesRegex(
                network_sandbox.SandboxError,
                "cannot create network namespace",
            ):
                network_sandbox.run({}, ["/bin/true"])
        self.assertFalse(called)

    def test_invalid_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sandbox.json"
            path.write_text("{broken")
            with self.assertRaisesRegex(
                network_sandbox.SandboxError,
                "invalid sandbox config",
            ):
                network_sandbox.load_config(path)

    def test_main_reports_fail_closed_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sandbox.json"
            path.write_text(json.dumps({}))
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    network_sandbox.sys,
                    "argv",
                    [
                        "network_sandbox.py",
                        "--config",
                        str(path),
                        "--",
                        "/bin/true",
                    ],
                ),
                mock.patch.object(
                    network_sandbox.sys,
                    "platform",
                    "darwin",
                ),
                redirect_stderr(stderr),
            ):
                result = network_sandbox.main()
        self.assertEqual(result, 126)
        self.assertIn("requires Linux", stderr.getvalue())

    @unittest.skipUnless(shutil.which("openssl"), "openssl is required")
    def test_tls_fixture_records_allow_and_deny_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cert = root / "server.crt"
            key = root / "server.key"
            subprocess.run(
                [
                    shutil.which("openssl"),
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=allowed.lab.test",
                    "-addext",
                    "subjectAltName=DNS:allowed.lab.test,IP:127.0.0.1",
                    "-keyout",
                    str(key),
                    "-out",
                    str(cert),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log = root / "requests.json"
            fixture = network_sandbox.ControlledHttp(
                port=0,
                body=b"allowlist fixture\n",
                log_path=log,
                allowed_hosts=("allowed.lab.test",),
                tls={"certfile": str(cert), "keyfile": str(key)},
            )
            fixture.start()
            port = fixture.server.server_address[1]
            context = ssl.create_default_context(cafile=str(cert))

            def request(host: str) -> tuple[int, bytes]:
                connection = http.client.HTTPSConnection(
                    "127.0.0.1",
                    port,
                    context=context,
                )
                connection.putrequest(
                    "GET",
                    f"/{host}",
                    skip_host=True,
                )
                connection.putheader("Host", host)
                connection.endheaders()
                response = connection.getresponse()
                data = response.read()
                connection.close()
                return response.status, data

            allowed = request("allowed.lab.test")
            denied = request("denied.lab.test")
            fixture.close()
            requests = json.loads(log.read_text())
            isolation_path = root / "isolation.json"
            network_sandbox.write_isolation_evidence(
                isolation_path,
                {
                    "policy": {
                        "isolation": "namespace",
                        "egress": "allowlist",
                        "dns": "controlled",
                        "allowed_hosts": ["allowed.lab.test"],
                        "allowed_endpoints": [
                            {
                                "protocol": "tcp",
                                "address": "10.0.2.2",
                                "port": 18443,
                            }
                        ],
                    },
                    "dns": {
                        "mode": "controlled",
                        "hosts": {
                            "allowed.lab.test": "10.0.2.2",
                        },
                    },
                    "http": {
                        "tls": {
                            "certfile": str(cert),
                            "keyfile": str(key),
                        }
                    },
                },
            )
            isolation = json.loads(isolation_path.read_text())
            dns_log = root / "dns.json"
            dns = network_sandbox.ControlledDns(
                host="127.0.0.1",
                port=0,
                records={"allowed.lab.test": "10.0.2.2"},
                log_path=dns_log,
            )
            dns.start()
            dns_port = dns.socket.getsockname()[1]
            qname = (
                b"".join(
                    bytes([len(label)]) + label
                    for label in (b"allowed", b"lab", b"test")
                )
                + b"\0"
            )
            query = (
                struct.pack(
                    "!HHHHHH",
                    0x1234,
                    0x0100,
                    1,
                    0,
                    0,
                    0,
                )
                + qname
                + struct.pack("!HH", 1, 1)
            )
            query_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            query_socket.settimeout(2)
            query_socket.sendto(query, ("127.0.0.1", dns_port))
            dns_response, _ = query_socket.recvfrom(4096)
            denied_qname = (
                b"".join(
                    bytes([len(label)]) + label
                    for label in (b"denied", b"lab", b"test")
                )
                + b"\0"
            )
            denied_query = (
                struct.pack(
                    "!HHHHHH",
                    0x1235,
                    0x0100,
                    1,
                    0,
                    0,
                    0,
                )
                + denied_qname
                + struct.pack("!HH", 1, 1)
            )
            query_socket.sendto(denied_query, ("127.0.0.1", dns_port))
            denied_response, _ = query_socket.recvfrom(4096)
            query_socket.close()
            dns.close()
            dns_requests = json.loads(dns_log.read_text())

        self.assertEqual(allowed[0], 200)
        self.assertEqual(denied[0], 403)
        self.assertEqual(
            [row["decision"] for row in requests],
            ["allow", "deny"],
        )
        self.assertEqual(
            [row["status"] for row in requests],
            ["200", "403"],
        )
        self.assertEqual(
            isolation["allowed_hosts"],
            ["allowed.lab.test"],
        )
        self.assertTrue(isolation["tls_gateway"])
        self.assertTrue(isolation["controlled_dns"])
        self.assertEqual(
            isolation["egress_enforcement"],
            "nftables-input-output-default-drop",
        )
        self.assertEqual(
            isolation["allowed_endpoints"],
            [
                {
                    "protocol": "tcp",
                    "address": "10.0.2.2",
                    "port": 18443,
                }
            ],
        )
        self.assertEqual(
            isolation["dns_records"],
            {"allowed.lab.test": "10.0.2.2"},
        )
        self.assertEqual(dns_requests[0]["decision"], "allow")
        self.assertEqual(dns_requests[0]["status"], "A")
        self.assertEqual(dns_requests[1]["decision"], "deny")
        self.assertEqual(dns_requests[1]["status"], "NXDOMAIN")
        self.assertEqual(
            struct.unpack_from("!H", dns_response, 6)[0],
            1,
        )
        self.assertEqual(
            struct.unpack_from("!H", denied_response, 6)[0],
            0,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
