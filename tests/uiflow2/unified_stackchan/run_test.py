#!/usr/bin/env python3
"""Prove StackChan board, WiFi and BLE in one QEMU guest."""
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
HTTP_PORT = 18087
FLASH_SIZE = 16 << 20

SERIAL_MARKERS = (
    "UNIFIED_STACKCHAN_BOARD",
    "UNIFIED_STACKCHAN_POWER 87 4000 1",
    "UNIFIED_STACKCHAN_IMU 6",
    "UNIFIED_STACKCHAN_AW9523 1 0",
    "UNIFIED_STACKCHAN_INA226 4.00 0.25 1.00",
    "UNIFIED_STACKCHAN_ALS 640 321",
    "UNIFIED_STACKCHAN_RTC 2026 10 22 6 7 8",
    "UNIFIED_STACKCHAN_RGB",
    "UNIFIED_STACKCHAN_SERVO 500 300",
    "UNIFIED_STACKCHAN_NFC",
    "UNIFIED_STACKCHAN_IR_RX 86 163",
    "UNIFIED_STACKCHAN_MIC",
    "UNIFIED_STACKCHAN_AUDIO_PASS",
    "UNIFIED_STACKCHAN_CAMERA 320x240 153600 bytes",
    "UNIFIED_STACKCHAN_WIFI_CONNECTED 10.0.2.15",
    "UNIFIED_STACKCHAN_HTTP_PASS",
    "UNIFIED_STACKCHAN_BLE_READY",
    "UNIFIED_STACKCHAN_BLE_RX",
    "UNIFIED_STACKCHAN_BLE_ACK_SENT",
    "UNIFIED_STACKCHAN_AUDIO_HOLD",
    "UNIFIED_STACKCHAN_READY",
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
                body = b"UNIFIED_STACKCHAN_OK\n"
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
            name="stackchan-unified-http",
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


def numeric_line(text: str, marker: str) -> tuple[float, ...]:
    for line in text.splitlines():
        prefix = marker + " "
        if line.startswith(prefix):
            try:
                return tuple(float(value) for value in line[len(prefix):].split())
            except ValueError:
                return ()
    return ()


def close_values(
    actual: tuple[float, ...],
    expected: tuple[float, ...],
    tolerance: float,
) -> bool:
    return len(actual) == len(expected) and all(
        abs(value - target) <= tolerance
        for value, target in zip(actual, expected)
    )


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
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument("--http-port", type=int, default=HTTP_PORT)
    args = parser.parse_args()

    image = args.image.resolve()
    if not image.is_file() or image.stat().st_size != FLASH_SIZE:
        raise SystemExit(f"StackChan image must be exactly 16 MiB: {image}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir

    efuse = out / "efuse.bin"
    efuse.write_bytes(bytearray(4096))
    qmp_path = Path("/tmp") / f"m5-stackchan-unified-{os.getpid()}.sock"
    qmp_path.unlink(missing_ok=True)

    serial_path = out / "serial.log"
    serial_path.write_bytes(b"")
    serial1_path = out / "serial1.log"
    serial1_path.write_bytes(b"")
    peer_path = out / "ble-probe.log"
    peer_path.write_bytes(b"")
    speaker_path = out / "speaker.pcm"
    microphone_path = out / "microphone-source.pcm"
    rmt_source_path = out / "nec-source.rmt"
    rmt_capture_path = out / "nec-capture.rmt"

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
        env["M5SW_I2S_RX_PCM_FILE"] = str(microphone_path)
        env["M5SW_RMT_RX_FILE"] = str(rmt_source_path)
        env["M5SW_RMT_TX_FILE"] = str(rmt_capture_path)
        env["M5SW_RMT_TRACE"] = "1"
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tests/uiflow2/make_pcm_tone.py"),
                str(microphone_path),
                "--frequency",
                "440",
                "--sample-rate",
                "16000",
                "--seconds",
                "1",
                "--amplitude",
                "12000",
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tests/uiflow2/make_rmt_nec.py"),
                str(rmt_source_path),
                "--address",
                "0x56",
                "--command",
                "0xa3",
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )

        with peer_path.open("wb") as peer_log:
            peer_process = subprocess.Popen(
                [
                    sys.executable,
                    str(BLE_PROBE),
                    "--port",
                    str(hci_port),
                    "--name-prefix",
                    "M5-STACKCHAN-UNIFIED",
                    "--payload",
                    "M5_STACKCHAN_U",
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
            "-S",
            "-M",
            "m5stackchan",
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
            "-serial",
            f"file:{serial1_path}",
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
        qom_boot = (
            ("/machine/aw9523", "input-bits", 61439),
            ("/machine/ina226", "bus-voltage-mv", 4000),
            ("/machine/ina226", "current-ma", 250),
            ("/machine/ina226", "shunt-ohms", 0.08),
            ("/machine/pcf8563", "unix-time", 1792630923),
            ("/machine/ltr553", "light-level", 640),
            ("/machine/ltr553", "proximity-level", 321),
            ("/machine/axp2101", "vbat-mv", 4000),
            ("/machine/axp2101", "vin-mv", 5000),
            ("/machine/axp2101", "charging", True),
        )
        for path, prop, value in qom_boot:
            qmp.cmd("qom-set", path=path, property=prop, value=value)
        qmp.cmd("cont")

        if not wait_for_text(
            serial_path, "UNIFIED_STACKCHAN_IMU_CONFIG_READY", 20
        ):
            raise RuntimeError("StackChan IMU setup marker timed out")
        qmp.cmd("stop")
        qom_imu = (
            ("/machine/bmm150", "mag-x", 30),
            ("/machine/bmm150", "mag-y", -20),
            ("/machine/bmm150", "mag-z", 45),
            ("/machine/bmi270", "accel-x", 0.25),
            ("/machine/bmi270", "accel-y", -0.5),
            ("/machine/bmi270", "accel-z", 0.75),
            ("/machine/bmi270", "gyro-x", 10),
            ("/machine/bmi270", "gyro-y", -20),
            ("/machine/bmi270", "gyro-z", 30),
        )
        for path, prop, value in qom_imu:
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
            raise RuntimeError("unified StackChan exchange timed out")

        before_ppm = out / "before.ppm"
        after_ppm = out / "after.ppm"
        qmp.cmd("screendump", filename=str(before_ppm))
        before = canonicalize_screendump(before_ppm)
        write_rgb_png(out / "before.png", *before)
        send_input(qmp, "touch:160,183", before[:2], 1.5)
        if not wait_for_text(serial_path, "UNIFIED_STACKCHAN_TOUCH", 8):
            raise RuntimeError("StackChan display touch was not observed")
        qmp.cmd(
            "qom-set",
            path="/machine/si12t",
            property="touch-bits",
            value=2,
        )
        if not wait_for_text(
            serial_path, "UNIFIED_STACKCHAN_BODY_TOUCH", 8
        ):
            raise RuntimeError("StackChan body touch was not observed")
        qmp.cmd("screendump", filename=str(after_ppm))
        after = canonicalize_screendump(after_ppm)
        write_rgb_png(out / "after.png", *after)

        qom = {
            "/machine/axp2101.vbat-mv": qom_value(
                qmp, "/machine/axp2101", "vbat-mv"
            ),
            "/machine/axp2101.vin-mv": qom_value(
                qmp, "/machine/axp2101", "vin-mv"
            ),
            "/machine/axp2101.charging": qom_value(
                qmp, "/machine/axp2101", "charging"
            ),
            "/machine/bmi270.accel-x": qom_value(
                qmp, "/machine/bmi270", "accel-x"
            ),
            "/machine/bmi270.accel-y": qom_value(
                qmp, "/machine/bmi270", "accel-y"
            ),
            "/machine/bmi270.accel-z": qom_value(
                qmp, "/machine/bmi270", "accel-z"
            ),
            "/machine/bmi270.gyro-x": qom_value(
                qmp, "/machine/bmi270", "gyro-x"
            ),
            "/machine/bmi270.gyro-y": qom_value(
                qmp, "/machine/bmi270", "gyro-y"
            ),
            "/machine/bmi270.gyro-z": qom_value(
                qmp, "/machine/bmi270", "gyro-z"
            ),
            "/machine/bmm150.mag-x": qom_value(
                qmp, "/machine/bmm150", "mag-x"
            ),
            "/machine/bmm150.mag-y": qom_value(
                qmp, "/machine/bmm150", "mag-y"
            ),
            "/machine/bmm150.mag-z": qom_value(
                qmp, "/machine/bmm150", "mag-z"
            ),
            "/machine/ina226.bus-voltage-mv": qom_value(
                qmp, "/machine/ina226", "bus-voltage-mv"
            ),
            "/machine/ina226.current-ma": qom_value(
                qmp, "/machine/ina226", "current-ma"
            ),
            "/machine/ltr553.light-level": qom_value(
                qmp, "/machine/ltr553", "light-level"
            ),
            "/machine/ltr553.proximity-level": qom_value(
                qmp, "/machine/ltr553", "proximity-level"
            ),
            "/machine/pcf8563.unix-time": qom_value(
                qmp, "/machine/pcf8563", "unix-time"
            ),
            "/machine/si12t.touch-bits": qom_value(
                qmp, "/machine/si12t", "touch-bits"
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
    serial1_bytes = serial1_path.read_bytes()
    peer_bytes = peer_path.read_bytes()
    peer = peer_bytes.decode(errors="replace")
    pcm = speaker_path.read_bytes() if speaker_path.is_file() else b""
    pcm_nonzero = sum(value != 0 for value in pcm)
    pcm_peak_to_peak = (max(pcm) - min(pcm)) if pcm else 0
    microphone = (
        microphone_path.read_bytes() if microphone_path.is_file() else b""
    )
    microphone_nonzero = sum(value != 0 for value in microphone)
    rmt_check = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/uiflow2/check_rmt_nec.py"),
            str(rmt_capture_path),
            "--address",
            "0x56",
            "--command",
            "0xa3",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    rmt_bytes = (
        rmt_capture_path.read_bytes() if rmt_capture_path.is_file() else b""
    )
    before_stats = frame_stats(before[2])
    after_stats = frame_stats(after[2])
    frame_changed = sha256(before[2]) != sha256(after[2])
    http_requests = list(probe.requests) if probe is not None else []
    accel = numeric_line(serial, "UNIFIED_STACKCHAN_ACCEL")
    gyro = numeric_line(serial, "UNIFIED_STACKCHAN_GYRO")
    mag = numeric_line(serial, "UNIFIED_STACKCHAN_MAG")

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
        "serial:UNIFIED_STACKCHAN_TOUCH": "UNIFIED_STACKCHAN_TOUCH" in serial,
        "serial:UNIFIED_STACKCHAN_BODY_TOUCH": (
            "UNIFIED_STACKCHAN_BODY_TOUCH" in serial
        ),
        "serial:accel": close_values(accel, (0.25, -0.5, 0.75), 0.02),
        "serial:gyro": close_values(gyro, (10, -20, 30), 0.1),
        "serial:magnetometer": close_values(mag, (30, 20, -90), 0.75),
        "qom:power": qom.get("/machine/axp2101.vbat-mv") == 4000,
        "qom:vin": qom.get("/machine/axp2101.vin-mv") == 5000,
        "qom:charging": qom.get("/machine/axp2101.charging") is True,
        "qom:imu": (
            qom.get("/machine/bmi270.accel-x") == 0.25
            and qom.get("/machine/bmi270.accel-y") == -0.5
            and qom.get("/machine/bmi270.accel-z") == 0.75
            and qom.get("/machine/bmi270.gyro-x") == 10
            and qom.get("/machine/bmi270.gyro-y") == -20
            and qom.get("/machine/bmi270.gyro-z") == 30
        ),
        "qom:magnetometer": (
            qom.get("/machine/bmm150.mag-x") == 30
            and qom.get("/machine/bmm150.mag-y") == -20
            and qom.get("/machine/bmm150.mag-z") == 45
        ),
        "qom:ina226": (
            qom.get("/machine/ina226.bus-voltage-mv") == 4000
            and qom.get("/machine/ina226.current-ma") == 250
        ),
        "qom:ltr553": (
            qom.get("/machine/ltr553.light-level") == 640
            and qom.get("/machine/ltr553.proximity-level") == 321
        ),
        "qom:rtc": isinstance(
            qom.get("/machine/pcf8563.unix-time"), int
        ),
        "qom:body_touch": qom.get("/machine/si12t.touch-bits") == 2,
        "audio:pcm_nonzero": pcm_nonzero > 1000,
        "audio:pcm_peak_to_peak": pcm_peak_to_peak > 64,
        "microphone:source": microphone_nonzero > 1000,
        "ir:nec_capture": rmt_check.returncode == 0 and bool(rmt_bytes),
    }
    status = "PASS" if all(checks.values()) else "PARTIAL"
    evidence = {
        "schema_version": 1,
        "scope": "simulation-only-not-hardware-validation",
        "status": status,
        "device_id": "stackchan",
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
        "serial1": {
            "bytes": len(serial1_bytes),
            "sha256": sha256(serial1_bytes),
        },
        "microphone": {
            "source_bytes": len(microphone),
            "source_nonzeros": microphone_nonzero,
            "source_sha256": sha256(microphone),
        },
        "ir": {
            "bytes": len(rmt_bytes),
            "sha256": sha256(rmt_bytes),
            "check": rmt_check.stdout.strip(),
        },
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
