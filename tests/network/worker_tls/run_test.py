#!/usr/bin/env python3
"""Exercise Device Service HTTPS/mTLS with the signed worker executor."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import secrets
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from transport_security import build_client_tls_context  # noqa: E402
from worker_agent import Api, WorkerAgentError  # noqa: E402


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_openssl(*args: str) -> None:
    subprocess.run(
        ["openssl", *args],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )


def generate_certificates(directory: Path) -> None:
    ca_config = directory / "ca.cnf"
    ca_config.write_text(
        "[req]\n"
        "prompt = no\n"
        "distinguished_name = dn\n"
        "x509_extensions = v3_ca\n"
        "[dn]\n"
        "CN = M5 Worker TLS Test CA\n"
        "[v3_ca]\n"
        "basicConstraints = critical,CA:TRUE\n"
        "keyUsage = critical,keyCertSign,cRLSign\n"
        "subjectKeyIdentifier = hash\n"
        "authorityKeyIdentifier = keyid:always\n"
    )
    run_openssl(
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
        str(directory / "ca.key"),
        "-out",
        str(directory / "ca.crt"),
    )
    for name, usage, subject_alt_name in (
        ("server", "serverAuth", "IP:127.0.0.1"),
        ("client", "clientAuth", ""),
    ):
        key = directory / f"{name}.key"
        csr = directory / f"{name}.csr"
        cert = directory / f"{name}.crt"
        extension = directory / f"{name}.ext"
        run_openssl(
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-sha256",
            "-subj",
            f"/CN=M5 Worker TLS Test {name}",
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
        run_openssl(
            "x509",
            "-req",
            "-in",
            str(csr),
            "-CA",
            str(directory / "ca.crt"),
            "-CAkey",
            str(directory / "ca.key"),
            "-CAcreateserial",
            "-days",
            "2",
            "-sha256",
            "-extfile",
            str(extension),
            "-out",
            str(cert),
        )


def observed_tls_version(port: int, context: ssl.SSLContext) -> str:
    connection = http.client.HTTPSConnection(
        "127.0.0.1",
        port,
        timeout=5,
        context=context,
    )
    try:
        connection.connect()
        tls_version = (
            str(connection.sock.version())
            if connection.sock is not None
            else ""
        )
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        response.read()
        if response.status != 200 or not tls_version:
            raise RuntimeError(f"TLS health returned HTTP {response.status}")
        return tls_version
    finally:
        connection.close()


def wait_for_https(
    api: Api,
    process: subprocess.Popen,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Device Service exited with {process.returncode}")
        try:
            if api.json("/api/health").get("ok"):
                return
        except (OSError, WorkerAgentError):
            time.sleep(0.1)
    raise TimeoutError("Device Service HTTPS health did not become ready")


def write_evidence(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=(
            Path(__file__).parent
            / "evidence-2026-10-24-tls-mtls-pass.json"
        ),
    )
    args = parser.parse_args()
    if shutil.which("openssl") is None:
        raise SystemExit("openssl is required")

    checks: dict[str, str] = {
        "https_server_ready": "FAIL",
        "server_certificate_verified": "FAIL",
        "client_certificate_required": "FAIL",
        "mtls_client_certificate_accepted": "FAIL",
        "unsigned_worker_claim_rejected": "FAIL",
        "worker_agent_signed_requests_over_mtls": "FAIL",
        "no_plaintext_http_fallback": "FAIL",
    }
    with tempfile.TemporaryDirectory(prefix="m5-worker-tls-") as temp:
        temp_dir = Path(temp)
        pki = temp_dir / "pki"
        pki.mkdir()
        generate_certificates(pki)
        state_dir = temp_dir / "state"
        worker_dir = temp_dir / "worker"
        server_log = temp_dir / "service.log"
        port = free_tcp_port()
        token = secrets.token_urlsafe(24)
        base_url = f"https://127.0.0.1:{port}"
        client_ca_context = build_client_tls_context(ca_file=pki / "ca.crt")
        mtls_context = build_client_tls_context(
            ca_file=pki / "ca.crt",
            client_cert_file=pki / "client.crt",
            client_key_file=pki / "client.key",
        )

        with server_log.open("wb") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "platform/tools/serve.py"),
                    str(port),
                    "--bind",
                    "127.0.0.1",
                    "--state-dir",
                    str(state_dir),
                    "--max-sessions",
                    "1",
                    "--max-per-device",
                    "1",
                    "--api-token",
                    token,
                    "--tls-cert",
                    str(pki / "server.crt"),
                    "--tls-key",
                    str(pki / "server.key"),
                    "--tls-client-ca",
                    str(pki / "ca.crt"),
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        try:
            with_mtls = Api(
                base_url,
                token,
                ssl_context=mtls_context,
            )
            wait_for_https(with_mtls, process, 15)
            checks["https_server_ready"] = "PASS"
            checks["server_certificate_verified"] = "PASS"
            tls_version = observed_tls_version(port, mtls_context)

            without_client_cert = Api(
                base_url,
                token,
                ssl_context=client_ca_context,
            )
            try:
                without_client_cert.json("/api/health")
            except WorkerAgentError:
                checks["client_certificate_required"] = "PASS"
            else:
                raise RuntimeError(
                    "mTLS server accepted a client without a certificate"
                )

            checks["mtls_client_certificate_accepted"] = "PASS"

            unsigned_identity = {
                "worker_id": "tls-probe",
                "instance_id": "tls-probe-instance",
                "generation": 1,
            }
            try:
                with_mtls.json(
                    "/api/v1/jobs/claim",
                    method="POST",
                    payload=unsigned_identity,
                )
            except WorkerAgentError as error:
                if "HTTP 401" not in str(error):
                    raise
                unsigned_claim_http = 401
                checks["unsigned_worker_claim_rejected"] = "PASS"
            else:
                raise RuntimeError("mTLS bypassed signed worker authentication")

            worker_env = os.environ.copy()
            worker_env["PYTHONPATH"] = str(ROOT / "platform/tools")
            worker = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "platform/tools/worker_agent.py"),
                    "--service-url",
                    base_url,
                    "--token",
                    token,
                    "--ca-file",
                    str(pki / "ca.crt"),
                    "--client-cert",
                    str(pki / "client.crt"),
                    "--client-key",
                    str(pki / "client.key"),
                    "--worker-id",
                    "tls-worker",
                    "--work-dir",
                    str(worker_dir),
                    "--capabilities-json",
                    '{"qemu": true}',
                    "--once",
                ],
                cwd=ROOT,
                env=worker_env,
                capture_output=True,
                timeout=30,
            )
            if worker.returncode != 0:
                raise RuntimeError(
                    "worker agent failed over mTLS: "
                    + worker.stderr.decode(errors="replace")[-1000:]
                )
            checks["worker_agent_signed_requests_over_mtls"] = "PASS"

            try:
                Api(
                    f"http://127.0.0.1:{port}",
                    token,
                ).json("/api/health")
            except WorkerAgentError:
                checks["no_plaintext_http_fallback"] = "PASS"
            else:
                raise RuntimeError("plaintext HTTP unexpectedly succeeded")

            payload = {
                "schema_version": 1,
                "kind": "m5stack-worker-tls-mtls-transport",
                "date": "2026-10-24",
                "status": "PASS",
                "validation": "transport-security validation",
                "scope": "same-host-loopback-real-tls-process",
                "tls": {
                    "minimum_version": "TLSv1.2",
                    "observed_version": tls_version,
                    "server_certificate_verification": "PASS",
                    "client_certificate_required": "PASS",
                    "ephemeral_test_pki": True,
                },
                "worker_transport": {
                    "base_url_scheme": "https",
                    "bearer_and_worker_hmac_preserved": "PASS",
                    "unsigned_claim_http": unsigned_claim_http,
                    "worker_agent_exit_code": worker.returncode,
                },
                "checks": checks,
                "not_claimed": [
                    "cross-host network topology or latency",
                    "certificate or worker credential rotation",
                    "production CA and certificate lifecycle",
                    "real QEMU job execution over mTLS",
                    "multi-host scheduling or worker continuity",
                    "hardware validation",
                ],
            }
            if not all(value == "PASS" for value in checks.values()):
                raise RuntimeError(f"TLS checks incomplete: {checks}")
            write_evidence(args.out, payload)
            print(f"evidence={args.out}")
            print(json.dumps(payload, indent=2))
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
