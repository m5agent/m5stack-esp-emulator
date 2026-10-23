#!/usr/bin/env python3
"""Prove custom-CA TLS and Host allowlisting in one QEMU guest."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from network_sandbox import ControlledHttp  # noqa: E402
from pcap_summary import summarize_pcap  # noqa: E402


PROBE = Path(__file__).resolve().parent / "probe"
PROFILE_RUNNER = ROOT / "tests/uiflow2/run_profile_ui_test.py"
BASE_IMAGE = ROOT / "platform/.cache/firmware/sticks3/uiflow2.bin"
SANDBOX = ROOT / "platform/tools/network_sandbox.py"
TLS_PORT = 18443
REQUIRED_SERIAL = (
    "TLS_WIFI_READY",
    "TLS_CONTEXT_READY",
    "TLS_CA_LOADED",
    "TLS_ALLOWED PASS",
    "TLS_DENIED PASS",
    "TLS_ALLOWLIST_RESULT PASS",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
        process.wait(timeout=5)


def make_certificate(root: Path) -> tuple[Path, Path]:
    openssl = shutil.which("openssl")
    if openssl is None:
        raise RuntimeError("openssl is required to generate the test CA")
    cert = root / "test-ca.crt"
    key = root / "test-ca.key"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-not_before",
            "19700101000000Z",
            "-not_after",
            "20350101000000Z",
            "-subj",
            "/CN=allowed.lab.test",
            "-addext",
            "subjectAltName=DNS:allowed.lab.test,IP:127.0.0.1,IP:10.0.2.2",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return cert, key


def build_probe(
    out_dir: Path,
    cert: Path,
) -> Path:
    generated_probe = out_dir / "probe-files"
    generated_probe.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROBE / "boot.py", generated_probe / "boot.py")
    source = (PROBE / "main.py").read_text()
    source = source.replace("__TLS_PORT__", str(TLS_PORT))
    ca_b64 = base64.b64encode(cert.read_bytes()).decode("ascii")
    source = source.replace("__CA_PEM_B64__", ca_b64)
    (generated_probe / "main.py").write_text(source)
    command = [
        sys.executable,
        str(PROFILE_RUNNER),
        "--base",
        str(BASE_IMAGE),
        "--machine",
        "m5sticks3",
        "--files-dir",
        str(generated_probe),
        "--vfs-offset",
        "0x641000",
        "--vfs-size",
        "0x1BE000",
        "--flash-size",
        "0x800000",
        "--expected-size",
        "135x240",
        "--efuse-pkg-version",
        "1",
        "--out-dir",
        str(out_dir / "build"),
        "--build-only",
    ]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [
                str(ROOT / ".work/py"),
                environment.get("PYTHONPATH", ""),
            ],
        )
    )
    subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=True,
        timeout=120,
    )
    image = out_dir / "build/uiflow2-ui-test.bin"
    if not image.is_file():
        raise RuntimeError("TLS allowlist probe image was not created")
    return image


def qemu_command(
    qemu: Path,
    image: Path,
    rom_dir: Path,
    out: Path,
) -> list[str]:
    serial = out / "serial.log"
    pcap = out / "network.pcap"
    efuse = out / "efuse.bin"
    efuse_data = bytearray(4096)
    efuse_data[36:40] = (1 << 21).to_bytes(4, "little")
    efuse.write_bytes(efuse_data)
    return [
        str(qemu),
        "-accel",
        "tcg,thread=single",
        "-snapshot",
        "-m",
        "8M",
        "-M",
        "m5sticks3",
        "-drive",
        f"file={image},if=mtd,format=raw",
        "-drive",
        f"if=none,id=efuse,file={efuse},format=raw",
        "-L",
        str(rom_dir),
        "-display",
        "none",
        "-serial",
        f"file:{serial}",
        "-serial",
        "null",
        "-nic",
        "user,model=misc.esp32s3.wifi,id=wifi0",
        "-object",
        (
            "filter-dump,id=netdump,netdev=wifi0,"
            f"file={pcap},maxlen=262144"
        ),
        "-global",
        "driver=nvram.esp32s3.efuse,property=drive,value=efuse",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--rom-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=75)
    parser.add_argument(
        "--isolation",
        choices=("trusted-host", "namespace"),
        default="trusted-host",
    )
    args = parser.parse_args()
    if not args.qemu.is_file() or not args.rom_dir.is_dir():
        parser.error("--qemu and --rom-dir must exist")
    if args.isolation == "namespace" and sys.platform != "linux":
        parser.error("namespace isolation requires Linux")

    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cert_dir = Path(tempfile.mkdtemp(prefix="m5-tls-allowlist-cert-"))
    fixture: ControlledHttp | None = None
    process: subprocess.Popen | None = None
    stderr_handle = None
    certificate_sha256: str | None = None
    started = time.monotonic()
    try:
        cert, key = make_certificate(cert_dir)
        certificate_sha256 = sha256(cert)
        image = build_probe(out, cert)
        qemu = qemu_command(
            args.qemu.resolve(),
            image,
            args.rom_dir.resolve(),
            out,
        )
        if args.isolation == "namespace":
            sandbox_config = out / "sandbox.json"
            sandbox_config.write_text(
                json.dumps(
                    {
                        "policy": {
                            "isolation": "namespace",
                            "egress": "allowlist",
                            "dns": "deny",
                            "allowed_hosts": ["allowed.lab.test"],
                        },
                        "http": {
                            "port": TLS_PORT,
                            "body": "TLS_ALLOWLIST_OK\n",
                            "log": str(out / "tls-requests.json"),
                            "allowed_hosts": ["allowed.lab.test"],
                            "tls": {
                                "certfile": str(cert),
                                "keyfile": str(key),
                            },
                        },
                        "isolation_evidence": str(
                            out / "isolation.json"
                        ),
                    },
                    indent=2,
                )
                + "\n"
            )
            command = [
                sys.executable,
                str(SANDBOX),
                "--config",
                str(sandbox_config),
                "--",
                *qemu,
            ]
        else:
            fixture = ControlledHttp(
                port=TLS_PORT,
                body=b"TLS_ALLOWLIST_OK\n",
                log_path=out / "tls-requests.json",
                allowed_hosts=("allowed.lab.test",),
                tls={"certfile": str(cert), "keyfile": str(key)},
            )
            fixture.start()
            command = qemu

        serial = out / "serial.log"
        stderr_handle = (out / "qemu.stderr").open("wb")
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=stderr_handle,
            start_new_session=True,
        )
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            text = (
                serial.read_text(errors="replace")
                if serial.is_file()
                else ""
            )
            if all(marker in text for marker in REQUIRED_SERIAL):
                break
            if process.poll() is not None:
                break
            time.sleep(0.1)
    finally:
        stop_process(process)
        if stderr_handle is not None:
            stderr_handle.close()
        if fixture is not None:
            fixture.close()
        shutil.rmtree(cert_dir, ignore_errors=True)

    serial = (
        (out / "serial.log").read_text(errors="replace")
        if (out / "serial.log").is_file()
        else ""
    )
    request_log = out / "tls-requests.json"
    requests = (
        json.loads(request_log.read_text())
        if request_log.is_file()
        else []
    )
    capture_path = out / "network.pcap"
    capture = (
        summarize_pcap(capture_path)
        if capture_path.is_file() and capture_path.stat().st_size > 24
        else {}
    )
    qemu_stderr_path = out / "qemu.stderr"
    qemu_stderr = (
        qemu_stderr_path.read_text(errors="replace")
        if qemu_stderr_path.is_file()
        else ""
    )
    expected_requests = [
        {
            "path": "/allowed",
            "host": "allowed.lab.test",
            "decision": "allow",
            "status": "200",
        },
        {
            "path": "/denied",
            "host": "denied.lab.test",
            "decision": "deny",
            "status": "403",
        },
    ]
    checks = {
        **{
            marker: marker in serial
            for marker in REQUIRED_SERIAL
        },
        "tls_allow_and_deny": requests == expected_requests,
        "dhcp": bool(capture.get("dhcp", {}).get("guest_addresses")),
        "tls_port_observed": any(
            flow.get("protocol") == "TCP"
            and flow.get("destination", "").endswith(f":{TLS_PORT}")
            for flow in capture.get("flows", [])
        ),
        "pcap_written": bool(capture),
    }
    if args.isolation == "namespace":
        isolation_path = out / "isolation.json"
        isolation = (
            json.loads(isolation_path.read_text())
            if isolation_path.is_file()
            else {}
        )
        checks["private_namespace"] = (
            isolation.get("private_network_namespace") is True
        )
        checks["no_external_route"] = (
            isolation.get("external_route") is False
        )
        checks["allowlist_evidence"] = (
            isolation.get("allowed_hosts")
            == ["allowed.lab.test"]
        )
    status = "PASS" if all(checks.values()) else "FAIL"
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-sticks3-tls-host-allowlist",
        "scope": "virtual-device-namespace-lab-tls-not-hardware-rf",
        "status": status,
        "duration_seconds": round(time.monotonic() - started, 3),
        "isolation": args.isolation,
        "image_sha256": sha256(image),
        "base_image_sha256": sha256(BASE_IMAGE),
        "certificate_sha256": certificate_sha256,
        "checks": checks,
        "tls_requests": requests,
        "packet_capture": {
            key: value
            for key, value in capture.items()
            if key not in {"flows"}
        },
        "not_claimed": [
            "real-hardware TLS or RF behavior",
            "arbitrary public-internet allowlisting",
            "certificate-pinned or mutual-TLS firmware",
            "malicious-firmware safety",
        ],
    }
    if status != "PASS":
        if (
            "TLS_CA_DECODE_DONE" in serial
            and "TLS_CONTEXT_READY" not in serial
            and "[AES] Error reading from GDMA buffer" in qemu_stderr
        ):
            evidence["blocker"] = (
                "ssl_context_creation_stalls_after_esp32s3_aes_gdma_read_error"
            )
        else:
            evidence["blocker"] = "tls_allowlist_probe_did_not_complete"
    (out / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
