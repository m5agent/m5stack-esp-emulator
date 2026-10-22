#!/usr/bin/env python3
"""Build and run the classic ESP32 QEMU OpenETH data-plane probe."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEST_DIR = Path(__file__).resolve().parent
IDF_PATH = ROOT / ".work/esp-idf-v5.5.4"
QEMU = ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"
PAYLOAD = b"\xab" * (1024 * 1024)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path != "/bigfile":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()
        try:
            for offset in range(0, len(PAYLOAD), 4 * 1024):
                self.wfile.write(PAYLOAD[offset:offset + 4 * 1024])
                self.wfile.flush()
                time.sleep(0.02)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_firmware(timeout: float) -> Path:
    toolchain = (
        Path.home()
        / ".espressif/tools/xtensa-esp-elf/esp-14.2.0_20260121"
        / "xtensa-esp-elf/bin"
    )
    python_env = Path.home() / ".espressif/python_env/idf5.5_py3.13_env"
    merged = TEST_DIR / "build_esp32/merged.bin"
    command = f"""
set -euo pipefail
export PATH={json.dumps(str(toolchain))}:$PATH
export IDF_PATH={json.dumps(str(IDF_PATH))}
export IDF_PYTHON_ENV_PATH={json.dumps(str(python_env))}
source {json.dumps(str(IDF_PATH / "export.sh"))} >/dev/null
idf.py -C {json.dumps(str(TEST_DIR))} -B build_esp32 set-target esp32
idf.py -C {json.dumps(str(TEST_DIR))} -B build_esp32 build
idf.py -C {json.dumps(str(TEST_DIR))} -B build_esp32 merge-bin -o {json.dumps(str(merged))}
"""
    subprocess.run(
        ["bash", "-lc", command],
        cwd=TEST_DIR,
        check=True,
        timeout=timeout,
    )
    if not merged.is_file():
        raise RuntimeError(f"build did not create {merged}")
    with merged.open("r+b") as image:
        image.truncate(16 * 1024 * 1024)
    return merged


def run_qemu(firmware: Path, out_dir: Path, timeout: float) -> tuple[int, str]:
    serial = out_dir / "serial.log"
    serial.unlink(missing_ok=True)
    command = [
        str(QEMU),
        "-m",
        "0",
        "-M",
        "m5core2",
        "-drive",
        f"file={firmware},if=mtd,format=raw",
        "-L",
        str(ROM_DIR),
        "-display",
        "none",
        "-serial",
        f"file:{serial}",
        "-nic",
        "user,model=open_eth",
        "-no-reboot",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            text = serial.read_text(errors="replace") if serial.exists() else ""
            if "CORE2_OPENETH_RESULT:" in text:
                break
            if process.poll() is not None:
                break
            time.sleep(0.1)
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
    stderr = process.stderr.read() if process.stderr else ""
    return process.returncode or 0, stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("/tmp/core2-openeth"))
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--build-timeout", type=float, default=240)
    parser.add_argument("--run-timeout", type=float, default=60)
    args = parser.parse_args()

    if not IDF_PATH.is_dir() or not QEMU.is_file():
        raise SystemExit("ESP-IDF or QEMU runtime is missing")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    firmware = (
        TEST_DIR / "build_esp32/merged.bin"
        if args.skip_build
        else build_firmware(args.build_timeout)
    )

    server = ThreadingHTTPServer(("127.0.0.1", 8070), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        qemu_exit, qemu_stderr = run_qemu(
            firmware,
            args.out_dir,
            args.run_timeout,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    serial_path = args.out_dir / "serial.log"
    serial = serial_path.read_text(errors="replace")
    passed = (
        "CORE2_OPENETH_HTTP: status=200 content_length=1048576" in serial
        and "CORE2_OPENETH_TRANSFER: bytes=1048576 expected=1048576 complete=1"
        in serial
        and "CORE2_OPENETH_RESULT: PASSED" in serial
    )
    evidence = {
        "schema_version": 1,
        "scope": "simulation-only-not-hardware-validation",
        "status": "PASS" if passed else "FAIL",
        "transport": "qemu-openeth-ethernet",
        "wifi_claimed": False,
        "qemu": {
            "path": str(QEMU.relative_to(ROOT)),
            "sha256": sha256(QEMU),
            "exit_code": qemu_exit,
            "stderr": qemu_stderr[-4000:],
        },
        "firmware": {
            "path": str(firmware.relative_to(ROOT)),
            "bytes": firmware.stat().st_size,
            "sha256": sha256(firmware),
        },
        "http": {
            "expected_bytes": len(PAYLOAD),
            "expected_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
        },
        "serial": {
            "bytes": serial_path.stat().st_size,
            "sha256": sha256(serial_path),
        },
        "not_claimed": [
            "ESP32 WiFi association",
            "ESP32 BLE",
            "real-hardware behavior",
        ],
    }
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
