#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from serve import ServiceHTTPServer, Handler  # noqa: E402
from transport_security import (  # noqa: E402
    TransportSecurityError,
    build_client_tls_context,
    build_server_tls_context,
)
from worker_agent import Api, WorkerAgentError  # noqa: E402


class QuietTlsServer(ServiceHTTPServer):
    def handle_error(self, request, client_address) -> None:
        # A deliberate client-certificate rejection aborts the TLS handshake
        # before an HTTP request exists. The test observes the client failure.
        return


class DrainTestHandler(BaseHTTPRequestHandler):
    slow_started = threading.Event()
    slow_release = threading.Event()

    def do_GET(self) -> None:
        if self.path == "/slow":
            type(self).slow_started.set()
            if not type(self).slow_release.wait(timeout=10):
                self.send_error(503)
                return
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args) -> None:
        return


class TransportSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("openssl") is None:
            raise unittest.SkipTest("openssl is required for TLS integration tests")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cert_dir = Path(cls.tmp.name)
        cls._generate_certificates()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    @classmethod
    def _run_openssl(cls, *args: str) -> None:
        subprocess.run(
            ["openssl", *args],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )

    @classmethod
    def _generate_certificates(cls) -> None:
        ca_config = cls.cert_dir / "ca.cnf"
        ca_config.write_text(
            "[req]\n"
            "prompt = no\n"
            "distinguished_name = dn\n"
            "x509_extensions = v3_ca\n"
            "[dn]\n"
            "CN = M5 Test CA\n"
            "[v3_ca]\n"
            "basicConstraints = critical,CA:TRUE\n"
            "keyUsage = critical,keyCertSign,cRLSign\n"
            "subjectKeyIdentifier = hash\n"
            "authorityKeyIdentifier = keyid:always\n"
        )
        cls._run_openssl(
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-sha256",
            "-days",
            "2",
            "-config",
            str(ca_config),
            "-keyout",
            str(cls.cert_dir / "ca.key"),
            "-out",
            str(cls.cert_dir / "ca.crt"),
        )
        for name, usage, subject_alt_name in (
            ("server", "serverAuth", "IP:127.0.0.1"),
            ("client", "clientAuth", ""),
        ):
            key = cls.cert_dir / f"{name}.key"
            csr = cls.cert_dir / f"{name}.csr"
            cert = cls.cert_dir / f"{name}.crt"
            extension = cls.cert_dir / f"{name}.ext"
            cls._run_openssl(
                "req",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-sha256",
                "-subj",
                f"/CN=M5 Test {name}",
                "-keyout",
                str(key),
                "-out",
                str(csr),
            )
            extension.write_text(
                "basicConstraints = critical,CA:FALSE\n"
                "keyUsage = critical,digitalSignature,keyEncipherment\n"
                "subjectKeyIdentifier = hash\n"
                "authorityKeyIdentifier = keyid,issuer\n"
                f"extendedKeyUsage = {usage}\n"
                + (
                    f"subjectAltName = {subject_alt_name}\n"
                    if subject_alt_name
                    else ""
                )
            )
            cls._run_openssl(
                "x509",
                "-req",
                "-in",
                str(csr),
                "-CA",
                str(cls.cert_dir / "ca.crt"),
                "-CAkey",
                str(cls.cert_dir / "ca.key"),
                "-CAcreateserial",
                "-days",
                "2",
                "-sha256",
                "-extfile",
                str(extension),
                "-out",
                str(cert),
            )

    @contextmanager
    def tls_server(self, *, require_client_certificate: bool):
        context = build_server_tls_context(
            self.cert_dir / "server.crt",
            self.cert_dir / "server.key",
            (
                self.cert_dir / "ca.crt"
                if require_client_certificate
                else None
            ),
        )
        server = QuietTlsServer(("127.0.0.1", 0), Handler)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"https://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_https_worker_client_verifies_server_certificate(self):
        with self.tls_server(require_client_certificate=False) as base_url:
            client_context = build_client_tls_context(
                ca_file=self.cert_dir / "ca.crt"
            )
            response = Api(
                base_url,
                ssl_context=client_context,
            ).json("/api/health")
        self.assertTrue(response["ok"])

    def test_mtls_requires_a_trusted_client_certificate(self):
        with self.tls_server(require_client_certificate=True) as base_url:
            without_client_cert = Api(
                base_url,
                ssl_context=build_client_tls_context(
                    ca_file=self.cert_dir / "ca.crt"
                ),
            )
            with self.assertRaises(WorkerAgentError):
                without_client_cert.json("/api/health")

            with_client_cert = Api(
                base_url,
                ssl_context=build_client_tls_context(
                    ca_file=self.cert_dir / "ca.crt",
                    client_cert_file=self.cert_dir / "client.crt",
                    client_key_file=self.cert_dir / "client.key",
                ),
            )
            response = with_client_cert.json("/api/health")
        self.assertTrue(response["ok"])

    def test_untrusted_server_certificate_is_rejected(self):
        with self.tls_server(require_client_certificate=False) as base_url:
            with self.assertRaises(WorkerAgentError):
                Api(
                    base_url,
                    ssl_context=build_client_tls_context(),
                ).json("/api/health")

    def test_tls_credentials_must_be_provided_in_pairs(self):
        with self.assertRaises(TransportSecurityError):
            build_client_tls_context(
                client_cert_file=self.cert_dir / "client.crt"
            )
        with self.assertRaises(TransportSecurityError):
            build_client_tls_context(
                ca_file=self.cert_dir / "missing-ca.crt"
            )
        with self.assertRaises(WorkerAgentError):
            Api(
                "http://127.0.0.1:1",
                ssl_context=build_client_tls_context(),
            )

    def test_security_reload_waits_for_active_requests(self):
        DrainTestHandler.slow_started.clear()
        DrainTestHandler.slow_release.clear()
        reloaded = threading.Event()

        def reload_callback():
            reloaded.set()
            return None

        server = ServiceHTTPServer(
            ("127.0.0.1", 0),
            DrainTestHandler,
            reload_callback=reload_callback,
            reload_drain_timeout=5,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        responses: list[int] = []
        errors: list[BaseException] = []

        def request_slow():
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{server.server_port}/slow",
                    timeout=10,
                ) as response:
                    responses.append(response.status)
                    self.assertEqual(response.read(), b"ok")
            except Exception as error:
                errors.append(error)

        client = threading.Thread(target=request_slow)
        client.start()
        try:
            self.assertTrue(DrainTestHandler.slow_started.wait(timeout=5))
            self.assertEqual(server.request_gate.active, 1)
            server.request_security_reload()

            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if server.request_gate.draining:
                    break
                time.sleep(0.05)
            self.assertTrue(server.request_gate.draining)
            self.assertFalse(reloaded.is_set())

            DrainTestHandler.slow_release.set()
            client.join(timeout=10)
            self.assertFalse(client.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(responses, [200])
            self.assertTrue(reloaded.wait(timeout=5))
        finally:
            DrainTestHandler.slow_release.set()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            client.join(timeout=2)

    def test_security_reload_timeout_keeps_old_configuration(self):
        DrainTestHandler.slow_started.clear()
        DrainTestHandler.slow_release.clear()
        reloaded = threading.Event()

        def reload_callback():
            reloaded.set()
            return None

        server = ServiceHTTPServer(
            ("127.0.0.1", 0),
            DrainTestHandler,
            reload_callback=reload_callback,
            reload_drain_timeout=0.2,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        responses: list[int] = []

        def request_slow():
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/slow",
                timeout=10,
            ) as response:
                responses.append(response.status)
                response.read()

        client = threading.Thread(target=request_slow)
        client.start()
        try:
            self.assertTrue(DrainTestHandler.slow_started.wait(timeout=5))
            server.request_security_reload()

            deadline = time.monotonic() + 5
            drain_started = False
            while time.monotonic() < deadline:
                drain_started = (
                    drain_started or server.request_gate.draining
                )
                if (
                    drain_started
                    and not server.request_gate.draining
                    and not reloaded.is_set()
                ):
                    break
                time.sleep(0.05)
            self.assertTrue(drain_started)
            self.assertFalse(server.request_gate.draining)
            self.assertFalse(reloaded.is_set())

            DrainTestHandler.slow_release.set()
            client.join(timeout=10)
            self.assertFalse(client.is_alive())
            self.assertEqual(responses, [200])
        finally:
            DrainTestHandler.slow_release.set()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            client.join(timeout=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
