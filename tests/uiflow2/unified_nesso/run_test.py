#!/usr/bin/env python3
"""Prove Nesso N1 board peripherals and UART1 HCI BLE in one C6 guest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/uiflow2"))

from run_profile_ui_test import (  # noqa: E402
    canonicalize_screendump,
    frame_stats,
    send_input,
    wait_qmp,
    write_rgb_png,
)

DEFAULT_QEMU = (
    ROOT / ".work/M5StopWatch-QEMU/build/qemu-c6/build/qemu-system-riscv32"
)
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu-c6/pc-bios"
BLE_PROBE = ROOT / "platform/tools/ble_probe.py"
FLASH_SIZE = 16 << 20
HTTP_PORT = 18091

SERIAL_MARKERS = (
    "UNIFIED_NESSO_BOARD 23",
    "UNIFIED_NESSO_DISPLAY 135 240",
    "UNIFIED_NESSO_IO_CONFIG_READY",
    "UNIFIED_NESSO_POWER 100 4300 1",
    "UNIFIED_NESSO_IMU 0.25 -0.50 0.75 10.0 -20.0 30.0",
    "UNIFIED_NESSO_LORA M5LORA",
    "UNIFIED_NESSO_IR 0x56 0xA3",
    "UNIFIED_NESSO_BUZZER 3500",
    "UNIFIED_NESSO_WIFI_SCAN",
    "UNIFIED_NESSO_WIFI_CONNECTED 10.0.2.15",
    "UNIFIED_NESSO_HTTP_PASS",
    "UNIFIED_NESSO_BLE_READY",
    "UNIFIED_NESSO_READY",
    "UNIFIED_NESSO_TOUCH",
    "UNIFIED_NESSO_BUTTON 1",
    "UNIFIED_NESSO_BLE_RX",
    "UNIFIED_NESSO_BLE_ACK_SENT",
)
PEER_MARKERS = (
    "BLE_BUMBLE_FOUND",
    "BLE_BUMBLE_CONNECTED",
    "BLE_BUMBLE_GATT_DISCOVERED",
    "BLE_BUMBLE_SUBSCRIBED",
    "BLE_BUMBLE_WRITE",
    "BLE_BUMBLE_NOTIFICATION_OK",
    "BLE_BUMBLE_PASS",
)
QOM_VALUES = (
    ("/machine/nesso-bq27220", "battery-mv", 4300),
    ("/machine/nesso-bq27220", "current-ma", 250),
    ("/machine/nesso-bq27220", "battery-level", 96),
    ("/machine/nesso-aw32001", "charging", True),
    ("/machine/nesso-bmi270", "accel-x", 0.25),
    ("/machine/nesso-bmi270", "accel-y", -0.50),
    ("/machine/nesso-bmi270", "accel-z", 0.75),
    ("/machine/nesso-bmi270", "gyro-x", 10),
    ("/machine/nesso-bmi270", "gyro-y", -20),
    ("/machine/nesso-bmi270", "gyro-z", 30),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_text(path: Path, marker: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.is_file() and marker in path.read_text(errors="replace"):
            return True
        time.sleep(0.1)
    return False


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class ControlledHttp:
    def __init__(self, port: int):
        self.requests: list[dict[str, str]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.requests.append(
                    {"path": self.path, "host": self.headers.get("Host", "")}
                )
                body = b"UNIFIED_NESSO_OK\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="nesso-unified-http",
            daemon=True,
        )

    def __enter__(self) -> "ControlledHttp":
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def run_check(
    script: str,
    *arguments: str,
    env: dict[str, str],
) -> dict:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests/uiflow2" / script), *arguments],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "detail": result.stdout.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    args = parser.parse_args()

    image = args.image.resolve()
    if not image.is_file() or image.stat().st_size != FLASH_SIZE:
        raise SystemExit(f"Nesso image must be exactly 16 MiB: {image}")
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    serial_path = out / "serial.log"
    peer_path = out / "ble-probe.log"
    rmt_path = out / "rmt-capture.bin"
    pcm_path = out / "buzzer.pcm"
    serial_path.write_bytes(b"")
    peer_path.write_bytes(b"")
    for path in (rmt_path, pcm_path):
        path.unlink(missing_ok=True)
    qmp_path = Path("/tmp") / f"m5-nesso-unified-{os.getpid()}.sock"
    qmp_path.unlink(missing_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )
    env["M5SW_C6_BOARD"] = "nesso-n1"
    env["M5SW_I2S_PCM_FILE"] = str(pcm_path)
    env["M5SW_RMT_TX_FILE"] = str(rmt_path)
    env["M5SW_RMT_TRACE"] = "1"
    env["M5SW_SX1262_TRACE"] = "1"
    env["BLE_HCI_TRACE"] = "1"

    hci_port = free_port()
    peer_process: subprocess.Popen | None = None
    qemu: subprocess.Popen | None = None
    qmp = None
    http_probe: ControlledHttp | None = None
    terminal = "timeout"
    before = None
    after = None
    try:
        http_probe = ControlledHttp(HTTP_PORT).__enter__()
        with peer_path.open("wb") as peer_log:
            peer_process = subprocess.Popen(
                [
                    sys.executable,
                    str(BLE_PROBE),
                    "--port",
                    str(hci_port),
                    "--name-prefix",
                    "M5-NESSO-UNIFIED",
                    "--payload",
                    "M5_NESSO_UNIFIED",
                    "--subscribe",
                    "--expect-notification-prefix",
                    "ACK:",
                    "--notification-timeout",
                    "20",
                    "--timeout",
                    str(max(45, int(args.timeout - 10))),
                    "--write-delay",
                    "2",
                    "--linger",
                    "15",
                ],
                cwd=ROOT,
                env=env,
                stdout=peer_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        if not wait_for_text(peer_path, "BLE_PROBE_READY", 10):
            raise RuntimeError("external BLE controller did not become ready")

        command = [
            str(args.qemu),
            "-M",
            "esp32c6",
            "-drive",
            f"file={image},if=mtd,format=raw,snapshot=on",
            "-L",
            str(args.rom_dir),
            "-display",
            "none",
            "-serial",
            "null",
            "-chardev",
            (
                f"socket,id=hci,host=127.0.0.1,port={hci_port},"
                "nodelay=on"
            ),
            "-serial",
            "chardev:hci",
            "-serial",
            f"file:{serial_path}",
            "-qmp",
            f"unix:{qmp_path},server=on,wait=off",
            "-nic",
            "user,model=misc.esp32c6.wifi,id=wifi0",
        ]
        with (out / "qemu.stdout").open("wb") as stdout, (
            out / "qemu.stderr"
        ).open("wb") as stderr:
            qemu = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
            )
        qmp = wait_qmp(qmp_path, timeout=30)
        if not wait_for_text(serial_path, "UNIFIED_NESSO_IO_CONFIG_READY", 40):
            raise RuntimeError("Nesso IO setup timed out")
        for path, prop, value in QOM_VALUES:
            qmp.cmd("qom-set", path=path, property=prop, value=value)
        if not wait_for_text(serial_path, "UNIFIED_NESSO_READY", 60):
            raise RuntimeError("Nesso unified setup timed out")

        before_ppm = out / "before.ppm"
        after_ppm = out / "after.ppm"
        qmp.cmd("screendump", filename=str(before_ppm))
        before = canonicalize_screendump(before_ppm)
        write_rgb_png(out / "before.png", *before)

        send_input(qmp, "touch:67,175", before[:2], 1.0)
        send_input(qmp, "key:a", before[:2], 0.8)

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            serial = serial_path.read_text(errors="replace")
            peer = peer_path.read_text(errors="replace")
            if all(marker in serial for marker in SERIAL_MARKERS) and all(
                marker in peer for marker in PEER_MARKERS
            ):
                terminal = "complete"
                break
            if qemu.poll() is not None:
                raise RuntimeError(f"QEMU exited with {qemu.returncode}")
            time.sleep(0.2)
        else:
            raise RuntimeError("Nesso unified exchange timed out")

        time.sleep(0.5)
        qmp.cmd("screendump", filename=str(after_ppm))
        after = canonicalize_screendump(after_ppm)
        write_rgb_png(out / "after.png", *after)
    finally:
        if qmp is not None:
            try:
                qmp.close()
            except OSError:
                pass
        stop_process(qemu)
        stop_process(peer_process)
        qmp_path.unlink(missing_ok=True)
        if http_probe is not None:
            http_probe.__exit__(None, None, None)

    serial_bytes = serial_path.read_bytes()
    serial = serial_bytes.decode(errors="replace")
    peer_bytes = peer_path.read_bytes()
    peer = peer_bytes.decode(errors="replace")
    rmt_nec = run_check(
        "check_rmt_nec.py",
        str(rmt_path),
        "--address",
        "0x56",
        "--command",
        "0xa3",
        env=env,
    )
    pcm = run_check(
        "check_pcm.py",
        str(pcm_path),
        "--min-nonzero",
        "1000",
        "--min-peak-to-peak",
        "1000",
        env=env,
    )
    before_stats = frame_stats(before[2]) if before is not None else (0, 0)
    after_stats = frame_stats(after[2]) if after is not None else (0, 0)
    frame_changed = (
        before is not None
        and after is not None
        and before[2] != after[2]
    )
    http_requests = list(http_probe.requests) if http_probe is not None else []
    checks = {
        **{f"serial:{marker}": marker in serial for marker in SERIAL_MARKERS},
        **{f"peer:{marker}": marker in peer for marker in PEER_MARKERS},
        "http:controlled_request": http_requests
        == [{"path": "/unified", "host": "qemu.test"}],
        "frame:nonblank": before_stats[0] > 100,
        "frame:touch_redraw": frame_changed,
        "rmt:nec": rmt_nec["status"] == "PASS",
        "pcm:buzzer": pcm["status"] == "PASS",
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    evidence = {
        "schema_version": 1,
        "scope": "simulation-only-not-hardware-validation",
        "status": status,
        "device_id": "nesso-n1",
        "profile": "nesso-board-hci-ble",
        "terminal": terminal,
        "firmware": {
            "path": str(image),
            "bytes": image.stat().st_size,
            "sha256": sha256(image.read_bytes()),
        },
        "checks": checks,
        "frame": {
            "size": list(before[:2]) if before is not None else None,
            "before_nonblack": before_stats[0],
            "before_unique_colors": before_stats[1],
            "after_nonblack": after_stats[0],
            "after_unique_colors": after_stats[1],
            "changed": frame_changed,
        },
        "rmt": {
            "bytes": rmt_path.stat().st_size if rmt_path.is_file() else 0,
            "sha256": (
                sha256(rmt_path.read_bytes()) if rmt_path.is_file() else None
            ),
            "nec": rmt_nec,
        },
        "pcm": {
            "bytes": pcm_path.stat().st_size if pcm_path.is_file() else 0,
            "sha256": (
                sha256(pcm_path.read_bytes()) if pcm_path.is_file() else None
            ),
            "check": pcm,
        },
        "serial_bytes": len(serial_bytes),
        "serial_sha256": sha256(serial_bytes),
        "peer_log_bytes": len(peer_bytes),
        "peer_log_sha256": sha256(peer_bytes),
        "http_requests": http_requests,
        "network": {
            "wifi": "PASS via QEMU ESP32-C6 MAC/DMA and SLiRP",
            "ble": "PASS via UART1 HCI offload",
        },
        "gatt": {
            "name": "M5-NESSO-UNIFIED",
            "service": "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
            "payload": "M5_NESSO_UNIFIED",
            "notification": "ACK:M5_NESSO_UNIFIED",
        },
        "not_claimed": [
            "real-hardware behavior",
            "native ESP32-C6 Bluetooth controller/radio model",
            "RF privacy, security, range or performance",
        ],
    }
    (out / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
