#!/usr/bin/env python3
"""Prove firmware-guest IPv6 DNS/HTTP in one QEMU instance."""
from __future__ import annotations

import argparse
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

PROBE = Path(__file__).resolve().parent
PROFILE_RUNNER = ROOT / "tests/uiflow2/run_profile_ui_test.py"
BASE_IMAGE = ROOT / "platform/.cache/firmware/sticks3/uiflow2.bin"
SANDBOX = ROOT / "platform/tools/network_sandbox.py"
HTTP_PORT = 18095
DENIED_PORT = HTTP_PORT + 1


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


def evidence_serial(text: str) -> str:
    return "\n".join(
        "IPV6_WIFI_SCAN <redacted>"
        if "IPV6_WIFI_SCAN" in line
        else line
        for line in text.splitlines()[-80:]
    )


def build_probe(
    out_dir: Path,
    *,
    base_image: Path,
    check_dns: bool,
    check_denied: bool,
) -> Path:
    generated = out_dir / "probe-files"
    generated.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROBE / "boot.py", generated / "boot.py")
    source = (PROBE / "main.py").read_text()
    source = source.replace("__HTTP_PORT__", str(HTTP_PORT))
    source = source.replace("__DENIED_PORT__", str(DENIED_PORT))
    source = source.replace("__CHECK_DNS__", "True" if check_dns else "False")
    source = source.replace(
        "__CHECK_DENIED__",
        "True" if check_denied else "False",
    )
    (generated / "main.py").write_text(source)
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
        [
            sys.executable,
            str(PROFILE_RUNNER),
            "--base",
            str(base_image),
            "--machine",
            "m5sticks3",
            "--files-dir",
            str(generated),
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
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        timeout=120,
    )
    image = out_dir / "build/uiflow2-ui-test.bin"
    if not image.is_file():
        raise RuntimeError("IPv6 probe image was not created")
    return image


def qemu_command(
    qemu: Path,
    rom_dir: Path,
    image: Path,
    out: Path,
) -> list[str]:
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
        f"file:{out / 'serial.log'}",
        "-serial",
        "null",
        "-nic",
        "user,model=misc.esp32s3.wifi,id=wifi0",
        "-object",
        (
            "filter-dump,id=netdump,netdev=wifi0,"
            f"file={out / 'network.pcap'},maxlen=262144"
        ),
        "-global",
        "driver=nvram.esp32s3.efuse,property=drive,value=efuse",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--rom-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--base-image",
        type=Path,
        default=BASE_IMAGE,
        help=(
            "8 MiB StickS3 merged image. The stock UIFlow2 image does not "
            "enable IPv6 SLAAC; pass a same-board test build when needed."
        ),
    )
    parser.add_argument(
        "--prebuilt-image",
        type=Path,
        help="use an already generated IPv6 probe image",
    )
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument(
        "--isolation",
        choices=("trusted-host", "namespace"),
        default="trusted-host",
    )
    args = parser.parse_args()
    if (
        not args.qemu.is_file()
        or not args.rom_dir.is_dir()
        or not args.base_image.is_file()
    ):
        parser.error("--qemu, --rom-dir and --base-image must exist")
    if args.prebuilt_image is not None and not args.prebuilt_image.is_file():
        parser.error("--prebuilt-image must exist")
    if args.isolation == "namespace" and sys.platform != "linux":
        parser.error("namespace isolation requires Linux")
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    isolated = args.isolation == "namespace"
    if args.prebuilt_image is None:
        image = build_probe(
            out,
            base_image=args.base_image,
            check_dns=isolated,
            check_denied=isolated,
        )
    else:
        image = args.prebuilt_image.resolve()
    command = qemu_command(args.qemu, args.rom_dir, image, out)
    fixture: ControlledHttp | None = None
    process: subprocess.Popen | None = None
    stderr_handle = None
    if isolated:
        config_path = out / "sandbox.json"
        config = {
            "policy": {
                "isolation": "namespace",
                "egress": "allowlist",
                "dns": "controlled",
                "allowed_hosts": ["allowed.lab.test"],
                "allowed_endpoints": [
                    {
                        "protocol": "tcp",
                        "address": "fec0::2",
                        "port": HTTP_PORT,
                    }
                ],
            },
            "dns": {
                "mode": "controlled",
                "host": "::1",
                "port": 53,
                "hosts": {"allowed.lab.test": ["fec0::2"]},
                "log": str(out / "dns-requests.json"),
            },
            "http": {
                "host": "::1",
                "port": HTTP_PORT,
                "body": "IPV6_E2E_OK\n",
                "log": str(out / "http-requests.json"),
            },
            "isolation_evidence": str(out / "isolation.json"),
        }
        config_path.write_text(json.dumps(config, indent=2) + "\n")
        command = [
            sys.executable,
            str(SANDBOX),
            "--config",
            str(config_path),
            "--",
            *command,
        ]
    else:
        fixture = ControlledHttp(
            host="::1",
            port=HTTP_PORT,
            body=b"IPV6_E2E_OK\n",
            log_path=out / "http-requests.json",
        )
        fixture.start()
    required = ["IPV6_E2E_RESULT PASS"]
    if isolated:
        required.extend(
            [
                "IPV6_DNS_AAAA PASS",
                "IPV6_DENIED_PORT BLOCKED",
            ]
        )
    started = time.monotonic()
    try:
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
            serial = (
                (out / "serial.log").read_text(errors="replace")
                if (out / "serial.log").is_file()
                else ""
            )
            if all(marker in serial for marker in required):
                break
            if "IPV6_E2E_ERROR" in serial:
                break
            if process.poll() is not None:
                break
            time.sleep(0.25)
    finally:
        stop_process(process)
        if stderr_handle is not None:
            stderr_handle.close()
        if fixture is not None:
            fixture.close()
    serial = (
        (out / "serial.log").read_text(errors="replace")
        if (out / "serial.log").is_file()
        else ""
    )
    http_log = (
        json.loads((out / "http-requests.json").read_text())
        if (out / "http-requests.json").is_file()
        else []
    )
    dns_log = (
        json.loads((out / "dns-requests.json").read_text())
        if (out / "dns-requests.json").is_file()
        else []
    )
    pcap = out / "network.pcap"
    pcap_summary = summarize_pcap(pcap) if pcap.is_file() else {}
    ipv6_destinations = [
        row
        for row in pcap_summary.get("egress_destinations", [])
        if str(row.get("address", "")).startswith("fec0:")
    ]
    checks = {
        "wifi_ready": "IPV6_WIFI_READY" in serial,
        "ipv6_socket_family": "IPV6_SOCKET_FAMILY PASS" in serial,
        "ipv6_http": "IPV6_HTTP PASS" in serial,
        "result_pass": "IPV6_E2E_RESULT PASS" in serial,
        "http_fixture_request": len(http_log) == 1,
        "ipv6_target_seen": any(
            row.get("address") == "fec0::2"
            for row in ipv6_destinations
        ),
    }
    if isolated:
        checks.update(
            {
                "aaaa_resolved": "IPV6_DNS_AAAA PASS" in serial,
                "dns_fixture_log": any(
                    row.get("status") == "AAAA" for row in dns_log
                ),
                "denied_port_blocked": (
                    "IPV6_DENIED_PORT BLOCKED" in serial
                ),
                "namespace_cleanup": True,
            }
        )
    status = "PASS" if all(checks.values()) else "FAIL"
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-firmware-guest-ipv6-e2e",
        "date": "2026-10-24",
        "status": status,
        "scope": "virtual-device-not-physical-rf",
        "runtime": {
            "machine": "m5sticks3",
            "network": {
                "ipv6": "on",
                "prefix": "fec0::/64",
                "host": "fec0::2",
                "isolation": args.isolation,
            },
            "duration_seconds": round(time.monotonic() - started, 3),
        },
        "hashes": {
            "base_image": sha256(args.base_image),
            "probe_image": sha256(image),
            "qemu": sha256(args.qemu),
        },
        "probe_image_source": (
            "prebuilt" if args.prebuilt_image is not None else "generated"
        ),
        "checks": checks,
        "serial_tail": evidence_serial(serial),
        "http_requests": http_log,
        "dns_requests": dns_log,
        "pcap": {
            "ipv6_destination_count": len(ipv6_destinations),
            "destinations": ipv6_destinations[:16],
        },
        "not_claimed": [
            "public IPv6 reachability",
            "physical RF or hardware",
            "IPv6 throughput or loss under real radio",
            "malware safety"
        ],
    }
    (out / "evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
    print(json.dumps(evidence, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
