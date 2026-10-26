#!/usr/bin/env python3
"""Prove PaperColor board, WiFi and BLE in one QEMU guest."""
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
HTTP_PORT = 18085
FLASH_SIZE = 16 << 20

SERIAL_MARKERS = (
    "UNIFIED_PAPERCOLOR_BOARD",
    "UNIFIED_PAPERCOLOR_POWER",
    "UNIFIED_PAPERCOLOR_SHT40",
    "UNIFIED_PAPERCOLOR_AUDIO_PASS",
    "UNIFIED_PAPERCOLOR_WIFI_CONNECTED 10.0.2.15",
    "UNIFIED_PAPERCOLOR_HTTP_PASS",
    "UNIFIED_PAPERCOLOR_BLE_READY",
    "UNIFIED_PAPERCOLOR_BLE_RX",
    "UNIFIED_PAPERCOLOR_BLE_ACK_SENT",
    "UNIFIED_PAPERCOLOR_AUDIO_HOLD",
    "UNIFIED_PAPERCOLOR_READY",
    "UNIFIED_PAPERCOLOR_KEY",
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
                body = b"UNIFIED_PAPERCOLOR_OK\n"
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
            name="papercolor-unified-http",
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
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument("--http-port", type=int, default=HTTP_PORT)
    args = parser.parse_args()

    image = args.image.resolve()
    if not image.is_file() or image.stat().st_size != FLASH_SIZE:
        raise SystemExit(f"PaperColor image must be exactly 16 MiB: {image}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir

    efuse = out / "efuse.bin"
    efuse.write_bytes(bytearray(4096))
    qmp_path = Path("/tmp") / f"m5-papercolor-unified-{os.getpid()}.sock"
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
                    "M5-PAPERCOLOR-UNIFIED",
                    "--payload",
                    "M5_PAPERCOLOR_U",
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
            "-M",
            "m5papercolor",
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

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            serial = serial_path.read_text(errors="replace")
            peer = peer_path.read_text(errors="replace")
            if all(marker in serial for marker in SERIAL_MARKERS[:-1]) and all(
                marker in peer for marker in PEER_MARKERS
            ):
                break
            if qemu.poll() is not None:
                raise RuntimeError(f"QEMU exited with {qemu.returncode}")
            time.sleep(0.2)
        else:
            raise RuntimeError("unified PaperColor exchange timed out")

        before_ppm = out / "before.ppm"
        after_ppm = out / "after.ppm"
        qmp.cmd("screendump", filename=str(before_ppm))
        before = canonicalize_screendump(before_ppm)
        write_rgb_png(out / "before.png", *before)
        send_input(qmp, "key:a", before[:2], 2.0)
        qmp.cmd("screendump", filename=str(after_ppm))
        after = canonicalize_screendump(after_ppm)
        write_rgb_png(out / "after.png", *after)

        qom = {
            "/machine/m5pm1.vbat-mv": qom_value(
                qmp, "/machine/m5pm1", "vbat-mv"
            ),
            "/machine/sht40.temperature-c": qom_value(
                qmp, "/machine/sht40", "temperature-c"
            ),
            "/machine/sht40.humidity-pct": qom_value(
                qmp, "/machine/sht40", "humidity-pct"
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
        "frame:key_changed": frame_changed,
        "qom:power": qom.get("/machine/m5pm1.vbat-mv") == 4000,
        "qom:sht40": (
            qom.get("/machine/sht40.temperature-c") == 25
            and qom.get("/machine/sht40.humidity-pct") == 50
        ),
        "audio:pcm_nonzero": bool(pcm) and any(pcm),
    }
    status = "PASS" if all(checks.values()) else "PARTIAL"
    evidence = {
        "schema_version": 1,
        "scope": "simulation-only-not-hardware-validation",
        "status": status,
        "device_id": "papercolor",
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
            "nonzeros": sum(value != 0 for value in pcm),
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
            "native ESP32-S3 Bluetooth controller model",
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
