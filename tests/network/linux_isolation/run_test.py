#!/usr/bin/env python3
"""Run one StickS3 QEMU guest inside a Linux network namespace."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from pcap_summary import summarize_pcap  # noqa: E402


SANDBOX = ROOT / "platform/tools/network_sandbox.py"
HTTP_PORT = 18080
REQUIRED_SERIAL = {
    "wifi_dhcp": "UNIFIED_STICKS3_WIFI_CONNECTED 10.0.2.15",
    "controlled_http": "UNIFIED_STICKS3_HTTP_PASS",
    "public_dns_denied": "UNIFIED_STICKS3_PUBLIC_HTTP_ERROR",
    "guest_ready": "UNIFIED_STICKS3_READY",
}


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--rom-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=45)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("this integration test must run on Linux")
    for label, path in (
        ("QEMU", args.qemu),
        ("firmware", args.image),
        ("ROM directory", args.rom_dir),
        ("sandbox runner", SANDBOX),
    ):
        if not path.exists():
            parser.error(f"{label} does not exist: {path}")
    if args.image.stat().st_size != 8 << 20:
        parser.error("StickS3 image must be exactly 8 MiB")

    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    serial_path = out / "serial.log"
    pcap_path = out / "network.pcap"
    http_log = out / "http.json"
    isolation_path = out / "isolation.json"
    for path in (serial_path, pcap_path, http_log, isolation_path):
        path.unlink(missing_ok=True)
    efuse = out / "efuse.bin"
    efuse_data = bytearray(4096)
    efuse_data[36:40] = (1 << 21).to_bytes(4, "little")
    efuse.write_bytes(efuse_data)
    qmp_path = out / "qmp.sock"
    qmp_path.unlink(missing_ok=True)
    sandbox_config = out / "sandbox.json"
    sandbox_config.write_text(
        json.dumps(
            {
                "isolation_evidence": str(isolation_path),
                "http": {
                    "port": HTTP_PORT,
                    "body": "UNIFIED_STICKS3_OK\n",
                    "log": str(http_log),
                },
            },
            indent=2,
        )
        + "\n"
    )

    qemu_command = [
        str(args.qemu.resolve()),
        "-accel",
        "tcg,thread=single",
        "-snapshot",
        "-m",
        "8M",
        "-M",
        "m5sticks3",
        "-drive",
        f"file={args.image.resolve()},if=mtd,format=raw",
        "-drive",
        f"if=none,id=efuse,file={efuse},format=raw",
        "-L",
        str(args.rom_dir.resolve()),
        "-display",
        "none",
        "-serial",
        f"file:{serial_path}",
        "-chardev",
        "socket,id=hci,host=127.0.0.1,port=19544,server=on,wait=off,nodelay=on",
        "-serial",
        "chardev:hci",
        "-qmp",
        f"unix:{qmp_path},server=on,wait=off",
        "-nic",
        "user,model=misc.esp32s3.wifi,id=wifi0",
        "-object",
        (
            "filter-dump,id=netdump,netdev=wifi0,"
            f"file={pcap_path},maxlen=262144"
        ),
        "-global",
        "driver=nvram.esp32s3.efuse,property=drive,value=efuse",
    ]
    command = [
        sys.executable,
        str(SANDBOX),
        "--config",
        str(sandbox_config),
        "--",
        *qemu_command,
    ]
    process: subprocess.Popen | None = None
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = started + args.timeout
        while time.monotonic() < deadline:
            serial = (
                serial_path.read_text(errors="replace")
                if serial_path.is_file()
                else ""
            )
            if all(marker in serial for marker in REQUIRED_SERIAL.values()):
                break
            if process.poll() is not None:
                break
            time.sleep(0.1)
    finally:
        stop_process(process)

    serial = (
        serial_path.read_text(errors="replace")
        if serial_path.is_file()
        else ""
    )
    requests = json.loads(http_log.read_text()) if http_log.is_file() else []
    isolation = (
        json.loads(isolation_path.read_text())
        if isolation_path.is_file()
        else {}
    )
    capture = (
        summarize_pcap(pcap_path)
        if pcap_path.is_file() and pcap_path.stat().st_size > 24
        else {}
    )
    external_destinations = [
        row
        for row in capture.get("egress_destinations", [])
        if row.get("scope") in {"global", "slirp-redirect"}
    ]
    checks = {
        "private_namespace": (
            isolation.get("private_network_namespace") is True
        ),
        "no_external_route": isolation.get("external_route") is False,
        **{
            name: marker in serial
            for name, marker in REQUIRED_SERIAL.items()
        },
        "controlled_http_request": requests
        == [{"path": "/unified", "host": "qemu.test"}],
        "dhcp": bool(capture.get("dhcp", {}).get("guest_addresses")),
        "dns_query_observed": (
            "example.com." in capture.get("dns", {}).get("queries", [])
        ),
        "dns_response_denied": (
            "example.com." not in capture.get("dns", {}).get("responses", [])
        ),
        "no_external_destination": not external_destinations,
        "pcap_written": bool(capture),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-sticks3-linux-network-namespace-proof",
        "scope": "virtual-device-network-isolation-not-hardware-rf",
        "status": status,
        "duration_seconds": round(time.monotonic() - started, 3),
        "firmware": {
            "bytes": args.image.stat().st_size,
            "sha256": sha256(args.image),
        },
        "qemu": {
            "version_target": "xtensa-softmmu",
            "sha256": sha256(args.qemu),
        },
        "checks": checks,
        "isolation": isolation,
        "http_requests": requests,
        "packet_capture": {
            key: value
            for key, value in capture.items()
            if key not in {"flows"}
        },
        "artifacts": {
            name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
            for name, path in (
                ("serial.log", serial_path),
                ("http.json", http_log),
                ("network.pcap", pcap_path),
                ("isolation.json", isolation_path),
            )
            if path.is_file()
        },
        "not_claimed": [
            "real-hardware RF behavior",
            "WPA2 or WPA3 security",
            "TLS certificate correctness",
            "malicious-firmware safety",
            "external egress allowlists",
        ],
    }
    evidence_path = out / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
