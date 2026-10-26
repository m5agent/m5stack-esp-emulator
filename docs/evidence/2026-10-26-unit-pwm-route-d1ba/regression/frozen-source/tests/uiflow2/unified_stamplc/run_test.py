#!/usr/bin/env python3
"""Prove StamPLC board, WiFi and BLE in one QEMU guest."""
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
    ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"
BLE_PROBE = ROOT / "platform/tools/ble_probe.py"
HTTP_PORT = 18088
FLASH_SIZE = 8 << 20

SERIAL_MARKERS = (
    "UNIFIED_STAMPLC_BOARD",
    "UNIFIED_STAMPLC_DISPLAY 240 135",
    "UNIFIED_STAMPLC_RELAYS 1 0",
    "UNIFIED_STAMPLC_INPUTS 1 1 1 1 1 1 1 1",
    "UNIFIED_STAMPLC_RGB 1 1 0",
    "UNIFIED_STAMPLC_LM75 37.5 2580",
    "UNIFIED_STAMPLC_INA226 4.00 0.25 1.00",
    "UNIFIED_STAMPLC_RTC 2026 10 22 7 8 9",
    "UNIFIED_STAMPLC_CAN 0x123 b'M5CAN!'",
    "UNIFIED_STAMPLC_RS485 b'M5RS485'",
    "UNIFIED_STAMPLC_AUDIO_PASS",
    "UNIFIED_STAMPLC_WIFI_CONNECTED 10.0.2.15",
    "UNIFIED_STAMPLC_HTTP_PASS",
    "UNIFIED_STAMPLC_BLE_READY",
    "UNIFIED_STAMPLC_BLE_RX",
    "UNIFIED_STAMPLC_BLE_ACK_SENT",
    "UNIFIED_STAMPLC_AUDIO_HOLD",
    "UNIFIED_STAMPLC_READY",
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


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ControlledHttp:
    def __init__(self, port: int):
        self.requests: list[dict[str, str]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.requests.append(
                    {"path": self.path, "host": self.headers.get("Host", "")}
                )
                body = b"UNIFIED_STAMPLC_OK\n"
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
            name="stamplc-unified-http",
            daemon=True,
        )

    def __enter__(self) -> "ControlledHttp":
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def wait_for_text(path: Path, marker: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.is_file() and marker in path.read_text(errors="replace"):
            return True
        time.sleep(0.1)
    return False


def qom_value(qmp, path: str, prop: str):
    try:
        return qmp.cmd("qom-get", path=path, property=prop)["return"]
    except Exception as error:
        return {"error": str(error)}


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument("--http-port", type=int, default=HTTP_PORT)
    args = parser.parse_args()

    image = args.image.resolve()
    if not image.is_file() or image.stat().st_size != FLASH_SIZE:
        raise SystemExit(f"StamPLC image must be exactly 8 MiB: {image}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir

    efuse = out / "efuse.bin"
    efuse.write_bytes(bytearray(4096))
    qmp_path = Path("/tmp") / f"m5-stamplc-unified-{os.getpid()}.sock"
    qmp_path.unlink(missing_ok=True)

    serial_path = out / "serial.log"
    serial_path.write_bytes(b"")
    peer_path = out / "ble-probe.log"
    peer_path.write_bytes(b"")
    speaker_path = out / "speaker.pcm"

    peer_process: subprocess.Popen | None = None
    qemu: subprocess.Popen | None = None
    qmp = None
    probe: ControlledHttp | None = None
    try:
        probe = ControlledHttp(args.http_port).__enter__()
        hci_port = free_port()
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
        )
        env["M5SW_CAN_ECHO"] = "1"
        env["M5SW_RS485_ECHO"] = "1"
        env["M5SW_I2S_DMA_IRQ"] = "1"
        env["M5SW_I2S_PCM_FILE"] = str(speaker_path)

        with peer_path.open("wb") as peer_log:
            peer_process = subprocess.Popen(
                [
                    sys.executable,
                    str(BLE_PROBE),
                    "--port",
                    str(hci_port),
                    "--name-prefix",
                    "M5-STAMPLC-UNIFIED",
                    "--payload",
                    "M5_STAMPLC_U",
                    "--subscribe",
                    "--expect-notification-prefix",
                    "ACK:",
                    "--notification-timeout",
                    "15",
                    "--timeout",
                    str(max(30, int(args.timeout - 10))),
                    "--write-delay",
                    "2",
                    "--linger",
                    "20",
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
            "-snapshot",
            "-M",
            "m5stamplc",
            "-drive",
            f"file={image},if=mtd,format=raw",
            "-drive",
            f"if=none,id=efuse,file={efuse},format=raw",
            "-L",
            str(args.rom_dir),
            "-display",
            "none",
            "-serial",
            f"file:{serial_path}",
            "-chardev",
            (
                f"socket,id=hci,host=127.0.0.1,port={hci_port},"
                "nodelay=on"
            ),
            "-serial",
            "chardev:hci",
            "-qmp",
            f"unix:{qmp_path},server=on,wait=off",
            "-nic",
            "user,model=misc.esp32s3.wifi,id=wifi0",
            "-global",
            "driver=nvram.esp32s3.efuse,property=drive,value=efuse",
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
        qmp = wait_qmp(qmp_path, timeout=20)
        if not wait_for_text(
            serial_path, "UNIFIED_STAMPLC_IO_CONFIG_READY", 20
        ):
            raise RuntimeError("StamPLC board setup marker timed out")
        qmp.cmd("stop")
        qom_setup = (
            ("/machine/lm75-48", "temperature-c", 37.5),
            ("/machine/ina226-40", "bus-voltage-mv", 4000),
            ("/machine/ina226-40", "current-ma", 250),
            ("/machine/ina226-40", "shunt-ohms", 0.08),
            ("/machine/aw9523-59", "input-bits", 61680),
            ("/machine/rx8130-32", "unix-time", 1792630923),
        )
        for path, prop, value in qom_setup:
            qmp.cmd("qom-set", path=path, property=prop, value=value)
        qmp.cmd("cont")

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            serial = serial_path.read_text(errors="replace")
            peer = peer_path.read_text(errors="replace")
            if all(marker in serial for marker in SERIAL_MARKERS) and all(
                marker in peer for marker in PEER_MARKERS
            ):
                break
            if qemu.poll() is not None:
                raise RuntimeError(f"QEMU exited with {qemu.returncode}")
            time.sleep(0.2)
        else:
            raise RuntimeError("unified StamPLC exchange timed out")

        before_ppm = out / "before.ppm"
        after_ppm = out / "after.ppm"
        qmp.cmd("screendump", filename=str(before_ppm))
        before = canonicalize_screendump(before_ppm)
        write_rgb_png(out / "before.png", *before)
        send_input(qmp, "key:a", before[:2], 1.5)
        if not wait_for_text(serial_path, "UNIFIED_STAMPLC_KEY", 8):
            raise RuntimeError("StamPLC key input was not observed")
        qmp.cmd("screendump", filename=str(after_ppm))
        after = canonicalize_screendump(after_ppm)
        write_rgb_png(out / "after.png", *after)

        qom = {
            "/machine/lm75-48.temperature-c": qom_value(
                qmp, "/machine/lm75-48", "temperature-c"
            ),
            "/machine/ina226-40.bus-voltage-mv": qom_value(
                qmp, "/machine/ina226-40", "bus-voltage-mv"
            ),
            "/machine/ina226-40.current-ma": qom_value(
                qmp, "/machine/ina226-40", "current-ma"
            ),
            "/machine/aw9523-59.input-bits": qom_value(
                qmp, "/machine/aw9523-59", "input-bits"
            ),
            "/machine/rx8130-32.unix-time": qom_value(
                qmp, "/machine/rx8130-32", "unix-time"
            ),
        }
    finally:
        if qmp is not None:
            try:
                qmp.close()
            except OSError:
                pass
        stop_process(qemu)
        stop_process(peer_process)
        qmp_path.unlink(missing_ok=True)
        if probe is not None:
            probe.__exit__(None, None, None)

    serial_bytes = serial_path.read_bytes()
    serial = serial_bytes.decode(errors="replace")
    peer_bytes = peer_path.read_bytes()
    peer = peer_bytes.decode(errors="replace")
    pcm = speaker_path.read_bytes() if speaker_path.is_file() else b""
    pcm_nonzero = sum(value != 0 for value in pcm)
    pcm_peak_to_peak = (max(pcm) - min(pcm)) if pcm else 0
    before_stats = frame_stats(before[2])
    after_stats = frame_stats(after[2])
    frame_changed = sha256(before[2]) != sha256(after[2])
    http_requests = list(probe.requests) if probe is not None else []

    checks = {
        **{
            f"serial:{marker}": marker in serial
            for marker in SERIAL_MARKERS
        },
        **{
            f"peer:{marker}": marker in peer
            for marker in PEER_MARKERS
        },
        "http:controlled_request": http_requests
        == [{"path": "/unified", "host": "qemu.test"}],
        "frame:nonblank": before_stats[0] > 16 and after_stats[0] > 16,
        "frame:input_changed": frame_changed,
        "serial:UNIFIED_STAMPLC_KEY": "UNIFIED_STAMPLC_KEY" in serial,
        "qom:lm75": qom.get("/machine/lm75-48.temperature-c") == 37.5,
        "qom:ina226": (
            qom.get("/machine/ina226-40.bus-voltage-mv") == 4000
            and qom.get("/machine/ina226-40.current-ma") == 250
        ),
        "qom:input_bits": qom.get("/machine/aw9523-59.input-bits") == 61680,
        "qom:rtc": isinstance(
            qom.get("/machine/rx8130-32.unix-time"), int
        ),
        "audio:pcm_nonzero": pcm_nonzero > 1000,
        "audio:pcm_peak_to_peak": pcm_peak_to_peak > 64,
    }
    status = "PASS" if all(checks.values()) else "PARTIAL"
    evidence = {
        "schema_version": 1,
        "scope": "simulation-only-not-hardware-validation",
        "status": status,
        "device_id": "stamplc",
        "firmware": {
            "path": str(image),
            "bytes": image.stat().st_size,
            "sha256": sha256(image.read_bytes()),
        },
        "checks": checks,
        "frame": {
            "before": {
                "nonblack": before_stats[0],
                "colors": before_stats[1],
            },
            "after": {
                "nonblack": after_stats[0],
                "colors": after_stats[1],
            },
            "changed": frame_changed,
        },
        "audio": {
            "bytes": len(pcm),
            "nonzeros": pcm_nonzero,
            "peak_to_peak": pcm_peak_to_peak,
            "sha256": sha256(pcm),
        },
        "qom": qom,
        "http_requests": http_requests,
        "serial_bytes": len(serial_bytes),
        "serial_sha256": sha256(serial_bytes),
        "peer_log_bytes": len(peer_bytes),
        "peer_log_sha256": sha256(peer_bytes),
        "not_claimed": [
            "real-hardware behavior",
            "native ESP32-S3 WiFi PHY or Bluetooth controller model",
            "physical relay contact or isolated input behavior",
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
