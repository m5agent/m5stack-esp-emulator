#!/usr/bin/env python3
"""Exercise stock Core2 WiFi through the OpenMAC QEMU model."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FILES = Path(__file__).resolve().parent / "files"
PROFILE_RUNNER = ROOT / "tests/uiflow2/run_profile_ui_test.py"
BASE = ROOT / "platform/.cache/firmware/core2/uiflow2.bin"
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"
DEFAULT_QEMU = (
    ROOT
    / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ProbeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self.server.requests.append(self.path)  # type: ignore[attr-defined]
        body = b"CORE2_HOST_HTTP_OK\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def start_http_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
    server.requests = []  # type: ignore[attr-defined]
    return server


def build_image(base: Path, out_dir: Path, http_port: int) -> Path:
    files_dir = out_dir / "probe-files"
    files_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FILES / "boot.py", files_dir / "boot.py")
    main_py = (FILES / "main.py").read_text()
    (files_dir / "main.py").write_text(
        main_py.replace("__HTTP_PORT__", str(http_port))
    )
    command = [
        "python3",
        str(PROFILE_RUNNER),
        "--base",
        str(base),
        "--machine",
        "m5core2",
        "--files-dir",
        str(files_dir),
        "--vfs-offset",
        "0x820000",
        "--vfs-size",
        "0x7DF000",
        "--flash-size",
        "0x1000000",
        "--expected-size",
        "320x240",
        "--efuse-driver",
        "none",
        "--memory",
        "0",
        "--out-dir",
        str(out_dir),
        "--build-only",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )
    subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=True,
        timeout=90,
        stdout=subprocess.DEVNULL,
    )
    image = out_dir / "uiflow2-ui-test.bin"
    if not image.is_file():
        raise RuntimeError(f"probe build did not create {image}")
    return image


def parse_probe(serial: str) -> dict:
    scan_match = re.search(r"CORE2_WIFI_SCAN_OK\s+(\d+)", serial)
    ip_match = re.search(r"CORE2_WIFI_IP\s+(\d+\.\d+\.\d+\.\d+)", serial)
    http_match = re.search(r"CORE2_HTTP_RX\s+(.+)", serial)
    result_match = re.search(r"CORE2_WIFI_RESULT:\s+(PASSED|FAILED)", serial)
    return {
        "boot": "CORE2_WIFI_BOOT_FLAG" in serial,
        "main": "CORE2_WIFI_MAIN_START" in serial,
        "active": "CORE2_WIFI_ACTIVE True" in serial,
        "scan_count": int(scan_match.group(1)) if scan_match else 0,
        "known_ssid": "myssid" in serial,
        "connect_returned": "CORE2_WIFI_CONNECT_RETURNED None" in serial,
        "connected": "CORE2_WIFI_CONNECTED True" in serial,
        "ip": ip_match.group(1) if ip_match else None,
        "http_200": "CORE2_HTTP_OK" in serial,
        "http_response": http_match.group(1) if http_match else None,
        "terminal_result": result_match.group(1) if result_match else None,
    }


def run_qemu(
    qemu: Path,
    rom_dir: Path,
    image: Path,
    out_dir: Path,
    timeout: float,
) -> tuple[int, str, str]:
    serial_path = out_dir / "serial.log"
    stdout_path = out_dir / "qemu.stdout"
    stderr_path = out_dir / "qemu.stderr"
    command = [
        str(qemu),
        "-m",
        "0",
        "-M",
        "m5core2",
        "-drive",
        f"file={image},if=mtd,format=raw",
        "-L",
        str(rom_dir),
        "-display",
        "none",
        "-serial",
        f"file:{serial_path}",
        "-no-reboot",
        "-nic",
        "user,model=misc.esp32_wifi,id=wifi0",
    ]
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            serial = (
                serial_path.read_text(errors="replace")
                if serial_path.exists()
                else ""
            )
            if "CORE2_WIFI_RESULT:" in serial or process.poll() is not None:
                break
            time.sleep(0.1)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
    returncode = process.returncode
    serial = (
        serial_path.read_text(errors="replace")
        if serial_path.exists()
        else ""
    )
    return returncode or 0, serial, stderr_path.read_text(errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/core2-openmac-wifi"),
    )
    parser.add_argument("--timeout", type=float, default=12)
    parser.add_argument("--attempts", type=int, default=5)
    args = parser.parse_args()

    for label, path in (
        ("QEMU", args.qemu),
        ("ROM directory", args.rom_dir),
        ("base firmware", args.base),
    ):
        if not path.exists():
            parser.error(f"{label} does not exist: {path}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    http_server = start_http_server()
    http_server_thread = threading.Thread(
        target=http_server.serve_forever,
        name="core2-http-probe",
        daemon=True,
    )
    http_server_thread.start()
    http_port = int(http_server.server_port)
    try:
        built_image = build_image(args.base, args.out_dir, http_port)
        firmware_sha256 = sha256(built_image)
        attempts = []
        passed_attempt = None
        for attempt_index in range(1, args.attempts + 1):
            attempt_dir = args.out_dir / f"attempt-{attempt_index}"
            attempt_dir.mkdir(parents=True, exist_ok=True)
            image = attempt_dir / "firmware-under-test.bin"
            shutil.copyfile(built_image, image)
            request_offset = len(http_server.requests)
            qemu_exit, serial, qemu_stderr = run_qemu(
                args.qemu,
                args.rom_dir,
                image,
                attempt_dir,
                args.timeout,
            )
            probe = parse_probe(serial)
            attempt_requests = list(http_server.requests[request_offset:])
            passed = bool(
                probe["boot"]
                and probe["main"]
                and probe["active"]
                and probe["scan_count"] > 0
                and probe["known_ssid"]
                and probe["connect_returned"]
                and probe["connected"]
                and probe["ip"] is not None
                and probe["http_200"]
                and probe["terminal_result"] == "PASSED"
                and "/" in attempt_requests
            )
            attempt = {
                "attempt": attempt_index,
                "status": "PASS" if passed else "FAIL",
                "qemu_exit_code": qemu_exit,
                "qemu_stderr": qemu_stderr[-2000:],
                "serial": probe,
                "http_requests": attempt_requests,
                "serial_path": str(attempt_dir / "serial.log"),
                "serial_sha256": sha256(attempt_dir / "serial.log"),
            }
            attempts.append(attempt)
            if passed:
                passed_attempt = attempt_index
                break
    finally:
        http_server.shutdown()
        http_server.server_close()
        http_server_thread.join(timeout=3)

    status = "PASS" if passed_attempt is not None else "FAIL"
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-core2-openmac-wifi-http",
        "scope": "simulation-only-not-hardware-validation",
        "status": status,
        "profile": "core2-stock-uiflow2-openmac-http",
        "firmware": {
            "path": str(built_image),
            "bytes": built_image.stat().st_size,
            "sha256": firmware_sha256,
            "base_sha256": sha256(args.base),
        },
        "qemu": {
            "path": str(args.qemu),
            "sha256": sha256(args.qemu),
            "machine": "m5core2",
            "psram_mib": 0,
            "nic": "user,model=misc.esp32_wifi",
            "http_probe_port": http_port,
        },
        "attempts": attempts,
        "passed_attempt": passed_attempt,
        "not_claimed": [
            "DNS behavior",
            "remote internet access",
            "BLE",
            "real radio behavior",
            "real-hardware validation",
        ],
    }
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
