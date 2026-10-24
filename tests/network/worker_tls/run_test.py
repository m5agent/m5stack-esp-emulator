#!/usr/bin/env python3
"""Exercise Device Service HTTPS/mTLS with the signed worker executor."""

from __future__ import annotations

import argparse
import hashlib
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
import urllib.request
import zipfile
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


def upload_artifact(
    base_url: str,
    token: str,
    ssl_context: ssl.SSLContext,
    path: Path,
) -> dict:
    request = urllib.request.Request(
        base_url + "/api/v1/artifacts",
        data=path.read_bytes(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": path.name,
        },
        method="POST",
    )
    with urllib.request.urlopen(
        request,
        timeout=60,
        context=ssl_context,
    ) as response:
        return json.loads(response.read())


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
    job_group = parser.add_mutually_exclusive_group()
    job_group.add_argument(
        "--real-qemu-job",
        action="store_true",
        help="submit and execute a real StickS3 QEMU job over mTLS",
    )
    job_group.add_argument(
        "--real-unified-job",
        action="store_true",
        help="execute a unified StickS3 board/WiFi/BLE job over mTLS",
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

            job_id: str | None = None
            firmware_sha256 = ""
            real_job = args.real_qemu_job or args.real_unified_job
            if real_job:
                source_image = (
                    ROOT
                    / "platform/.cache/firmware/sticks3/uiflow2.bin"
                )
                if not source_image.is_file():
                    raise RuntimeError(
                        "StickS3 reference firmware is not cached"
                    )
                flash_size = 8 << 20
                source = source_image.read_bytes()
                if len(source) > flash_size:
                    raise RuntimeError("StickS3 reference exceeds flash size")
                if args.real_unified_job:
                    build_dir = (
                        ROOT
                        / ".work/uiflow-core2-2.5.3/m5stack/"
                        "build-M5STACK_StickS3-unified"
                    )
                    if not build_dir.is_dir():
                        raise RuntimeError(
                            "StickS3 unified build is not available"
                        )
                    full_image = temp_dir / "sticks3-unified-full.bin"
                    compose_env = os.environ.copy()
                    compose_env["PYTHONPATH"] = str(ROOT / ".work/py")
                    composed = subprocess.run(
                        [
                            sys.executable,
                            str(
                                ROOT
                                / "tests/uiflow2/unified_sticks3/"
                                "make_image.py"
                            ),
                            "--base",
                            str(source_image),
                            "--build-dir",
                            str(build_dir),
                            "--out",
                            str(full_image),
                        ],
                        cwd=ROOT,
                        env=compose_env,
                        capture_output=True,
                        timeout=120,
                    )
                    if composed.returncode != 0:
                        raise RuntimeError(
                            "unified image compose failed: "
                            + composed.stderr.decode(errors="replace")[-1000:]
                        )
                else:
                    full_image = temp_dir / "sticks3-reference-full.bin"
                    full_image.write_bytes(
                        source + b"\xff" * (flash_size - len(source))
                    )
                artifact = upload_artifact(
                    base_url,
                    token,
                    mtls_context,
                    full_image,
                )
                firmware = with_mtls.json(
                    "/api/v1/firmware",
                    method="POST",
                    payload={
                        "device_id": "sticks3",
                        "kind": "merged",
                        "artifact_id": artifact["artifact_id"],
                    },
                )
                firmware_sha256 = str(firmware["sha256"])
                job_label = (
                    "worker-mtls-sticks3-unified"
                    if args.real_unified_job
                    else "worker-mtls-sticks3-qemu"
                )
                network = (
                    {
                        "profile": "uiflow2-sticks3-unified",
                        "attempts": 1,
                        "capture_pcap": True,
                    }
                    if args.real_unified_job
                    else None
                )
                submitted = with_mtls.json(
                    "/api/v1/jobs",
                    method="POST",
                    payload={
                        "label": job_label,
                        "request": {
                            "session": {
                                "device_id": "sticks3",
                                "runtime": (
                                    "qemu-unified"
                                    if args.real_unified_job
                                    else "qemu"
                                ),
                                "firmware_id": firmware["firmware_id"],
                                "ready_timeout_seconds": 180,
                                **(
                                    {"network": network}
                                    if network is not None
                                    else {}
                                ),
                            },
                            "evidence_include": [
                                "manifest",
                                "serial",
                                "frames",
                                "logs",
                                *(
                                    ["network"]
                                    if args.real_unified_job
                                    else []
                                ),
                                "qom",
                            ],
                        },
                        "required_capabilities": {
                            "qemu": True,
                            **(
                                {"pcap": True}
                                if args.real_unified_job
                                else {}
                            ),
                        },
                        "max_attempts": 1,
                        "idempotency_key": (
                            job_label + "-" + secrets.token_hex(8)
                        ),
                    },
                )
                job_id = str(submitted["job"]["job_id"])

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
                    (
                        '{"qemu": true, "pcap": true}'
                        if args.real_unified_job
                        else '{"qemu": true}'
                    ),
                    "--session-timeout",
                    "240",
                    "--once",
                ],
                cwd=ROOT,
                env=worker_env,
                capture_output=True,
                timeout=300 if real_job else 30,
            )
            if worker.returncode != 0:
                raise RuntimeError(
                    "worker agent failed over mTLS: "
                    + worker.stderr.decode(errors="replace")[-1000:]
                )
            checks["worker_agent_signed_requests_over_mtls"] = "PASS"

            live_job: dict[str, object] = {}
            if job_id is not None:
                terminal = with_mtls.json(f"/api/v1/jobs/{job_id}")
                job = terminal["job"]
                result = job.get("result")
                result = result if isinstance(result, dict) else {}
                if (
                    job.get("status") != "completed"
                    or result.get("state") != "PASS"
                    or int(job.get("attempts", 0)) != 1
                ):
                    raise RuntimeError(f"mTLS job did not complete PASS: {job}")
                evidence_path = worker_dir / job_id / "evidence.zip"
                evidence = evidence_path.read_bytes()
                evidence_sha256 = hashlib.sha256(evidence).hexdigest()
                if (
                    len(evidence_sha256) != 64
                    or evidence_sha256 != result.get("evidence_sha256")
                ):
                    raise RuntimeError("mTLS job evidence SHA256 mismatch")
                with zipfile.ZipFile(evidence_path) as archive:
                    names = archive.namelist()
                for required in (
                    "manifest.json",
                    "serial.log",
                ):
                    if required not in names:
                        raise RuntimeError(
                            f"mTLS job evidence lacks {required}"
                        )
                checks["real_sticks3_qemu_job_over_mtls"] = "PASS"
                checks["terminal_job_pass"] = "PASS"
                checks["job_evidence_sha256"] = "PASS"
                unified_job: dict[str, object] = {}
                if args.real_unified_job:
                    with zipfile.ZipFile(evidence_path) as archive:
                        serial = archive.read("serial.log").decode(
                            errors="replace"
                        )
                        network_evidence = json.loads(
                            archive.read("network/evidence.json")
                        )
                        pcap_bytes = len(
                            archive.read("network/capture.pcap")
                        )
                        frames = [
                            name
                            for name in archive.namelist()
                            if name.startswith("frames/")
                            and name.endswith(".png")
                        ]
                        frame_bytes = (
                            len(archive.read(frames[0])) if frames else 0
                        )
                    required_markers = (
                        "UNIFIED_STICKS3_BOOT",
                        "UNIFIED_STICKS3_MAIN",
                        "UNIFIED_STICKS3_WIFI_CONNECTED",
                        "UNIFIED_STICKS3_HTTP_PASS",
                        "UNIFIED_STICKS3_BLE_READY",
                        "UNIFIED_STICKS3_BLE_RX",
                        "UNIFIED_STICKS3_BLE_ACK_SENT",
                        "UNIFIED_STICKS3_READY",
                    )
                    missing = [
                        marker
                        for marker in required_markers
                        if marker not in serial
                    ]
                    if missing:
                        raise RuntimeError(
                            f"unified evidence lacks markers: {missing}"
                        )
                    if (
                        network_evidence.get("status") != "PASS"
                        or not network_evidence.get("checks")
                        or not all(network_evidence["checks"].values())
                    ):
                        raise RuntimeError(
                            "unified network evidence is not PASS"
                        )
                    if pcap_bytes <= 0 or frame_bytes <= 0:
                        raise RuntimeError(
                            "unified evidence lacks non-empty pcap or frame"
                        )
                    checks["unified_sticks3_markers_over_mtls"] = "PASS"
                    checks["unified_network_evidence_over_mtls"] = "PASS"
                    checks["unified_pcap_over_mtls"] = "PASS"
                    checks["unified_frame_over_mtls"] = "PASS"
                    unified_job = {
                        "serial_markers": "PASS",
                        "network_evidence": "PASS",
                        "pcap_bytes": pcap_bytes,
                        "frame_bytes": frame_bytes,
                    }
                live_job = {
                    "status": job["status"],
                    "result_state": result["state"],
                    "attempts": job["attempts"],
                    "evidence_bytes": len(evidence),
                    "evidence_sha256": evidence_sha256,
                    "firmware_sha256": firmware_sha256,
                    "evidence_contains_manifest_and_serial": "PASS",
                    **unified_job,
                }

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
                "scope": (
                    "same-host-loopback-real-tls-unified-job"
                    if args.real_unified_job
                    else (
                        "same-host-loopback-real-tls-qemu-job"
                        if args.real_qemu_job
                        else "same-host-loopback-real-tls-process"
                    )
                ),
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
                "live_job": live_job,
                "not_claimed": [
                    "cross-host network topology or latency",
                    "certificate or worker credential rotation",
                    "production CA and certificate lifecycle",
                    "multi-host scheduling or worker continuity",
                    "hardware validation",
                ],
            }
            if not real_job:
                payload["not_claimed"].insert(
                    3,
                    "real QEMU job execution over mTLS",
                )
            elif args.real_qemu_job:
                payload["not_claimed"].insert(
                    3,
                    "unified board/network application PASS for the QEMU job",
                )
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
