#!/usr/bin/env python3
from __future__ import annotations

import http.client
import io
import ipaddress
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


def dns_query(name: str, qtype: int = 1) -> bytes:
    qname = (
        b"".join(
            bytes([len(label)]) + label.encode("ascii")
            for label in name.split(".")
        )
        + b"\0"
    )
    return (
        struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
        + qname
        + struct.pack("!HH", qtype, 1)
    )


class NetworkSandboxTests(unittest.TestCase):
    def test_isolation_evidence_cleanup_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "isolation.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "private_network_namespace": True,
                    }
                )
            )
            network_sandbox.update_isolation_evidence(
                path,
                {
                    "cleanup_completed": True,
                    "qemu_process_reaped": True,
                },
            )
            evidence = json.loads(path.read_text())
        self.assertTrue(evidence["cleanup_completed"])
        self.assertTrue(evidence["qemu_process_reaped"])

    def test_controlled_dns_rejects_invalid_or_non_unicast_records(self):
        for records in (
            {"invalid.test": []},
            {"invalid.test": ["not-an-address"]},
            {"invalid.test": ["0.0.0.0"]},
            {"invalid.test": ["ff02::1"]},
            {"invalid.test": ["127.0.0.1"] * 9},
        ):
            with self.subTest(records=records), self.assertRaises(
                network_sandbox.SandboxError
            ):
                network_sandbox.ControlledDns.normalize_records(records)

    def test_domain_suffix_matching_respects_dns_label_boundaries(self):
        self.assertTrue(
            network_sandbox.domain_matches_suffix(
                "allowy.test",
                "allowy.test",
            )
        )
        self.assertTrue(
            network_sandbox.domain_matches_suffix(
                "api.allowy.test.",
                "allowy.test",
            )
        )
        self.assertFalse(
            network_sandbox.domain_matches_suffix(
                "evilallowy.test",
                "allowy.test",
            )
        )
        self.assertFalse(
            network_sandbox.domain_matches_suffix(
                "allowy.test.evil",
                "allowy.test",
            )
        )

    def test_controlled_http_accepts_exact_and_domain_hosts(self):
        fixture = network_sandbox.ControlledHttp(
            port=0,
            body=b"domain fixture\n",
            log_path=None,
            allowed_hosts=("exact.test",),
            allowed_domains=("allowy.test",),
        )
        fixture.start()
        port = fixture.server.server_address[1]

        def request(host: str) -> int:
            connection = http.client.HTTPConnection(
                "127.0.0.1",
                port,
                timeout=2,
            )
            connection.putrequest("GET", "/", skip_host=True)
            connection.putheader("Host", host)
            connection.endheaders()
            response = connection.getresponse()
            response.read()
            status = response.status
            connection.close()
            return status

        try:
            self.assertEqual(request("exact.test"), 200)
            self.assertEqual(request("allowy.test"), 200)
            self.assertEqual(request("api.allowy.test"), 200)
            self.assertEqual(request("evilallowy.test"), 403)
            self.assertEqual(request("allowy.test.evil"), 403)
        finally:
            fixture.close()

    def test_controlled_dns_uses_exact_then_longest_domain_suffix(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "dns.json"
            dns = network_sandbox.ControlledDns(
                host="127.0.0.1",
                port=0,
                records={"exact.example.test": "203.0.113.10"},
                domain_records={
                    "example.test": "10.0.2.2",
                    "api.example.test": "198.51.100.8",
                },
                log_path=log,
            )
            dns.start()
            try:
                exact = dns.response(dns_query("exact.example.test"))
                longest = dns.response(dns_query("v2.api.example.test"))
                suffix = dns.response(dns_query("shop.example.test"))
                denied = dns.response(dns_query("evilallowy.test"))
            finally:
                dns.close()
            requests = json.loads(log.read_text())
        self.assertEqual(
            requests[0],
            {
                "name": "exact.example.test",
                "qtype": "1",
                "decision": "allow",
                "status": "A",
                "rule": "exact:exact.example.test",
            },
        )
        self.assertEqual(
            requests[1]["rule"],
            "suffix:api.example.test",
        )
        self.assertEqual(
            requests[2]["rule"],
            "suffix:example.test",
        )
        self.assertEqual(requests[3]["status"], "NXDOMAIN")
        self.assertEqual(requests[3]["rule"], "none")
        self.assertEqual(
            str(ipaddress.ip_address(exact[-4:])),
            "203.0.113.10",
        )
        self.assertEqual(
            str(ipaddress.ip_address(longest[-4:])),
            "198.51.100.8",
        )
        self.assertEqual(
            str(ipaddress.ip_address(suffix[-4:])),
            "10.0.2.2",
        )
        self.assertEqual(struct.unpack_from("!H", denied, 6)[0], 0)

    def test_isolation_evidence_records_domain_set_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "isolation.json"
            network_sandbox.write_isolation_evidence(
                path,
                {
                    "policy": {
                        "isolation": "namespace",
                        "egress": "allowlist",
                        "dns": "controlled",
                        "allowed_hosts": [],
                        "allowed_domains": ["allowy.test"],
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
                        "hosts": {},
                        "domain_records": {
                            "allowy.test": ["10.0.2.2"],
                        },
                    },
                },
            )
            evidence = json.loads(path.read_text())
        self.assertEqual(evidence["allowed_domains"], ["allowy.test"])
        self.assertEqual(
            evidence["dns_domain_records"],
            {"allowy.test": ["10.0.2.2"]},
        )

    def test_domain_records_must_match_policy_and_allowed_endpoint(self):
        endpoints = (
            network_sandbox.EgressEndpoint(
                protocol="tcp",
                address="10.0.2.2",
                port=18443,
            ),
        )
        bindings = network_sandbox.validate_domain_record_bindings(
            {"allowy.test": ["10.0.2.2"]},
            ("allowy.test",),
            endpoints,
        )
        self.assertEqual(
            bindings,
            {
                "allowy.test": (
                    ipaddress.ip_address("10.0.2.2"),
                )
            },
        )
        with self.assertRaisesRegex(
            network_sandbox.SandboxError,
            "not covered",
        ):
            network_sandbox.validate_domain_record_bindings(
                {"allowy.test": ["203.0.113.10"]},
                ("allowy.test",),
                endpoints,
            )
        with self.assertRaisesRegex(
            network_sandbox.SandboxError,
            "exactly match",
        ):
            network_sandbox.validate_domain_record_bindings(
                {"other.test": ["10.0.2.2"]},
                ("allowy.test",),
                endpoints,
            )

    @unittest.skipUnless(socket.has_ipv6, "IPv6 loopback is required")
    def test_controlled_ipv6_dns_and_http_bind_loopback(self):
        dns = network_sandbox.ControlledDns(
            host="::1",
            port=0,
            records={"allowed.lab.test": "2001:db8:6d35::53"},
            log_path=None,
        )
        dns.start()
        try:
            self.assertEqual(dns.socket.family, socket.AF_INET6)
            self.assertGreater(dns.socket.getsockname()[1], 0)
        finally:
            dns.close()
        fixture = network_sandbox.ControlledHttp(
            host="::1",
            port=0,
            body=b"ipv6 fixture\n",
            log_path=None,
        )
        fixture.start()
        try:
            connection = http.client.HTTPConnection(
                "::1",
                fixture.server.server_address[1],
                timeout=2,
            )
            connection.request("GET", "/ipv6")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"ipv6 fixture\n")
            connection.close()
        finally:
            fixture.close()

    def test_expected_ipv6_gateway_routes_are_not_external(self):
        host_ipv6 = "fd6d:1234:5678:9abc::1"
        guest_network = ipaddress.ip_network("fd6d:1234:5678:9abc::/126")
        lines = [
            (
                "00000000000000000000000000000000 00 "
                "00000000000000000000000000000000 00 "
                f"{ipaddress.IPv6Address(host_ipv6).packed.hex()} "
                "00000400 00000001 00000000 00000001 m5g-test"
            ),
            (
                f"{guest_network.network_address.packed.hex()} 7e "
                "00000000000000000000000000000000 00 "
                "00000000000000000000000000000000 "
                "00000100 00000001 00000000 00000001 m5g-test"
            ),
            (
                f"{ipaddress.IPv6Address('fd6d:1234:5678:9abc::2').packed.hex()} "
                "80 00000000000000000000000000000000 00 "
                "00000000000000000000000000000000 "
                "00000000 00000001 00000000 00000000 m5g-test"
            ),
            (
                "fe800000000000000000000000000000 40 "
                "00000000000000000000000000000000 00 "
                "00000000000000000000000000000000 "
                "00000100 00000001 00000000 00000001 m5g-test"
            ),
        ]
        with (
            mock.patch.object(
                network_sandbox.Path,
                "is_file",
                return_value=True,
            ),
            mock.patch.object(
                network_sandbox.Path,
                "read_text",
                side_effect=lambda *args, **kwargs: (
                    "Iface Destination Gateway Flags RefCnt Use Metric Mask\n"
                    if len(args) > 0 and kwargs.get("errors") is None
                    else "\n".join(lines)
                ),
            ),
        ):
            self.assertFalse(
                network_sandbox.route_table_has_external_route(
                    expected_interface="m5g-test",
                    expected_gateway="10.213.0.1",
                    expected_network="10.213.0.0",
                    expected_ipv6_gateway=host_ipv6,
                    expected_ipv6_network=str(guest_network),
                )
            )

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
                records={
                    "allowed.lab.test": [
                        "10.0.2.2",
                        "2001:db8:6d35::53",
                    ]
                },
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
            aaaa_query = (
                struct.pack(
                    "!HHHHHH",
                    0x1236,
                    0x0100,
                    1,
                    0,
                    0,
                    0,
                )
                + qname
                + struct.pack("!HH", 28, 1)
            )
            query_socket.sendto(aaaa_query, ("127.0.0.1", dns_port))
            aaaa_response, _ = query_socket.recvfrom(4096)
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
        self.assertEqual(dns_requests[1]["decision"], "allow")
        self.assertEqual(dns_requests[1]["status"], "AAAA")
        self.assertEqual(dns_requests[2]["decision"], "deny")
        self.assertEqual(dns_requests[2]["status"], "NXDOMAIN")
        self.assertEqual(
            struct.unpack_from("!H", dns_response, 6)[0],
            1,
        )
        self.assertEqual(
            struct.unpack_from("!H", denied_response, 6)[0],
            0,
        )
        question = network_sandbox.ControlledDns.parse_question(aaaa_response)
        self.assertIsNotNone(question)
        _, query_type, query_class, question_end = question
        self.assertEqual((query_type, query_class), (28, 1))
        self.assertEqual(
            struct.unpack_from("!H", aaaa_response, 6)[0],
            1,
        )
        self.assertEqual(
            struct.unpack_from("!H", aaaa_response, question_end + 2)[0],
            28,
        )
        self.assertEqual(
            socket.inet_ntop(
                socket.AF_INET6,
                aaaa_response[question_end + 12 : question_end + 28],
            ),
            "2001:db8:6d35::53",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
