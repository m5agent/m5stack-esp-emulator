#!/usr/bin/env python3
"""Prove Core2 board, WiFi and BLE in one QEMU guest."""
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
sys.path.insert(0, str(ROOT / "platform/tools"))

from run_profile_ui_test import (  # noqa: E402
    canonicalize_screendump,
    frame_stats,
    send_input,
    wait_qmp,
    write_rgb_png,
)
from xtensa_elf_symbols import core2_native_vhci_addresses  # noqa: E402

DEFAULT_QEMU = (
    ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"
BLE_PROBE = ROOT / "platform/tools/ble_probe.py"
NATIVE_BRIDGE_GDB = (
    ROOT / "tests/uiflow2/core2_radio_probe/native_vhci_bridge.gdb"
)
HTTP_PORT = 18089
FLASH_SIZE = 16 << 20

REQUIRED_MARKERS = (
    "UNIFIED_CORE2_BOARD",
    "UNIFIED_CORE2_DISPLAY 320 240",
    "UNIFIED_CORE2_POWER",
    "UNIFIED_CORE2_IMU",
    "UNIFIED_CORE2_RTC",
    "UNIFIED_CORE2_INA3221",
    "UNIFIED_CORE2_MIC",
    "UNIFIED_CORE2_AUDIO_PASS",
    "UNIFIED_CORE2_WIFI_CONNECTED 10.0.2.15",
    "UNIFIED_CORE2_HTTP_PASS",
    "UNIFIED_CORE2_PUBLIC_DNS",
    "UNIFIED_CORE2_PUBLIC_HTTP_PASS",
    "UNIFIED_CORE2_BLE_READY",
    "UNIFIED_CORE2_BLE_RX",
    "UNIFIED_CORE2_BLE_ACK_SENT",
    "UNIFIED_CORE2_AUDIO_HOLD",
    "UNIFIED_CORE2_READY",
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


def default_gdb() -> Path:
    explicit = os.environ.get("M5_XTENSA_GDB")
    if explicit:
        return Path(explicit)
    candidates = sorted(
        (Path.home() / ".espressif/tools/xtensa-esp-elf-gdb").glob(
            "*/xtensa-esp-elf-gdb/bin/xtensa-esp32-elf-gdb"
        )
    )
    if candidates:
        return candidates[-1]
    return Path("xtensa-esp32-elf-gdb")


class ControlledHttp:
    def __init__(self, port: int):
        self.requests: list[dict[str, str]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.requests.append(
                    {"path": self.path, "host": self.headers.get("Host", "")}
                )
                body = b"UNIFIED_CORE2_OK\n"
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
            name="core2-unified-http",
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


def run_attempt(
    args: argparse.Namespace,
    image: Path,
    attempt_dir: Path,
    attempt_index: int,
    probe: ControlledHttp,
) -> dict:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    serial_path = attempt_dir / "serial.log"
    peer_path = attempt_dir / "ble-probe.log"
    speaker_path = attempt_dir / "speaker.pcm"
    microphone_source = attempt_dir / "microphone-source.pcm"
    serial_path.write_bytes(b"")
    peer_path.write_bytes(b"")

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )
    env["M5SW_I2S_PCM_FILE"] = str(speaker_path)
    env["M5SW_I2S_RX_PCM_FILE"] = str(microphone_source)
    env["M5_NATIVE_BT_ELF"] = str(args.native_elf.resolve())
    native_symbols = core2_native_vhci_addresses(args.native_elf)
    env.update(
        {
            name: f"0x{value:08x}"
            for name, value in native_symbols.items()
        }
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/uiflow2/make_pcm_tone.py"),
            str(microphone_source),
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

    hci_port = free_port()
    gdb_port = free_port()
    qmp_path = Path("/tmp") / (
        f"m5-core2-unified-{os.getpid()}-{attempt_index}.sock"
    )
    bridge_path = attempt_dir / "native-vhci-gdb.log"
    qmp_path.unlink(missing_ok=True)
    peer_process: subprocess.Popen | None = None
    qemu: subprocess.Popen | None = None
    gdb_process: subprocess.Popen | None = None
    qmp = None
    before = None
    after = None
    qom = {}
    terminal = "timeout"
    try:
        env["BLE_HCI_TRACE"] = "1"
        with peer_path.open("wb") as peer_log:
            peer_process = subprocess.Popen(
                [
                    sys.executable,
                    str(BLE_PROBE),
                    "--port",
                    str(hci_port),
                    "--name-prefix",
                    "M5-CORE2-UNIFIED",
                    "--payload",
                    "M5_CORE2_UNIFIED",
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
            "-accel",
            "tcg,thread=single",
            "-icount",
            "shift=auto,align=off,sleep=off",
            "-m",
            "0",
            "-M",
            "m5core2",
            "-drive",
            f"file={image},if=mtd,format=raw",
            "-L",
            str(args.rom_dir),
            "-display",
            "none",
            "-serial",
            f"file:{serial_path}",
            "-qmp",
            f"unix:{qmp_path},server=on,wait=off",
            "-nic",
            "user,model=misc.esp32_wifi,id=wifi0",
            "-no-reboot",
        ]
        if args.ble_transport == "native-vhci":
            command[1:1] = [
                "-S",
                "-gdb",
                f"tcp::{gdb_port}",
            ]
        else:
            command.extend(
                [
                    "-chardev",
                    (
                        f"socket,id=hci,host=127.0.0.1,"
                        f"port={hci_port},nodelay=on"
                    ),
                    "-serial",
                    "chardev:hci",
                ]
            )
        with (attempt_dir / "qemu.stdout").open("wb") as stdout, (
            attempt_dir / "qemu.stderr"
        ).open("wb") as stderr:
            qemu = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
        if args.ble_transport == "native-vhci":
            bridge_env = env.copy()
            bridge_env["M5_NATIVE_BT_HCI_PORT"] = str(hci_port)
            bridge_env["M5_NATIVE_GDB_PORT"] = str(gdb_port)
            with bridge_path.open("wb") as bridge_output:
                gdb_process = subprocess.Popen(
                    [
                        str(args.gdb),
                        "-q",
                        "-batch",
                        "-x",
                        str(NATIVE_BRIDGE_GDB),
                    ],
                    cwd=ROOT,
                    env=bridge_env,
                    stdout=bridge_output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        qmp = wait_qmp(qmp_path, timeout=30)
        if not wait_for_text(
            serial_path, "UNIFIED_CORE2_IO_CONFIG_READY", 25
        ):
            terminal = "startup"
            raise RuntimeError("Core2 board setup marker timed out")
        qom_setup = (
            ("/machine/axp2101", "vbat-mv", 4000),
            ("/machine/axp2101", "vin-mv", 5000),
            ("/machine/axp2101", "charging", True),
            ("/machine/ina3221-40", "bus1-mv", 4800),
            ("/machine/ina3221-40", "current1-ma", 240),
            ("/machine/ina3221-40", "shunt-ohms", 0.01),
            ("/machine/pcf8563", "unix-time", 1792630923),
            ("/machine/mpu6886", "accel-x", 0.25),
            ("/machine/mpu6886", "accel-y", -0.5),
            ("/machine/mpu6886", "accel-z", 0.75),
            ("/machine/mpu6886", "gyro-x", 10),
            ("/machine/mpu6886", "gyro-y", -20),
            ("/machine/mpu6886", "gyro-z", 30),
        )
        for path, prop, value in qom_setup:
            qmp.cmd("qom-set", path=path, property=prop, value=value)

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            serial = serial_path.read_text(errors="replace")
            peer = peer_path.read_text(errors="replace")
            if "Guru Meditation" in serial or "Rebooting..." in serial:
                terminal = "guest_crash"
                break
            if all(marker in serial for marker in REQUIRED_MARKERS) and all(
                marker in peer for marker in PEER_MARKERS
            ):
                terminal = "pass"
                break
            if qemu.poll() is not None:
                terminal = "qemu_exit"
                break
            time.sleep(0.2)

        if terminal == "pass":
            before_ppm = attempt_dir / "before.ppm"
            after_ppm = attempt_dir / "after.ppm"
            qmp.cmd("screendump", filename=str(before_ppm))
            before = canonicalize_screendump(before_ppm)
            write_rgb_png(attempt_dir / "before.png", *before)
            send_input(qmp, "touch:160,183", before[:2], 1.5)
            if not wait_for_text(serial_path, "UNIFIED_CORE2_TOUCH", 8):
                terminal = "touch_timeout"
            else:
                qmp.cmd("screendump", filename=str(after_ppm))
                after = canonicalize_screendump(after_ppm)
                write_rgb_png(attempt_dir / "after.png", *after)
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
                    "/machine/ina3221-40.bus1-mv": qom_value(
                        qmp, "/machine/ina3221-40", "bus1-mv"
                    ),
                    "/machine/ina3221-40.current1-ma": qom_value(
                        qmp, "/machine/ina3221-40", "current1-ma"
                    ),
                    "/machine/pcf8563.unix-time": qom_value(
                        qmp, "/machine/pcf8563", "unix-time"
                    ),
                    "/machine/mpu6886.accel-x": qom_value(
                        qmp, "/machine/mpu6886", "accel-x"
                    ),
                    "/machine/mpu6886.gyro-x": qom_value(
                        qmp, "/machine/mpu6886", "gyro-x"
                    ),
                }
    except Exception as error:
        if terminal == "timeout":
            terminal = f"error:{error}"
    finally:
        if qmp is not None:
            try:
                qmp.close()
            except OSError:
                pass
        stop_process(gdb_process)
        stop_process(qemu)
        stop_process(peer_process)
        qmp_path.unlink(missing_ok=True)

    serial_bytes = serial_path.read_bytes()
    serial = serial_bytes.decode(errors="replace")
    peer_bytes = peer_path.read_bytes()
    peer = peer_bytes.decode(errors="replace")
    bridge_bytes = bridge_path.read_bytes() if bridge_path.is_file() else b""
    bridge = bridge_bytes.decode(errors="replace")
    pcm = speaker_path.read_bytes() if speaker_path.is_file() else b""
    microphone = (
        microphone_source.read_bytes() if microphone_source.is_file() else b""
    )
    pcm_nonzero = sum(value != 0 for value in pcm)
    pcm_peak_to_peak = (max(pcm) - min(pcm)) if pcm else 0
    microphone_nonzero = sum(value != 0 for value in microphone)
    before_stats = frame_stats(before[2]) if before is not None else (0, 0)
    after_stats = frame_stats(after[2]) if after is not None else (0, 0)
    frame_changed = (
        before is not None
        and after is not None
        and sha256(before[2]) != sha256(after[2])
    )
    accel = numeric_line(serial, "UNIFIED_CORE2_ACCEL")
    gyro = numeric_line(serial, "UNIFIED_CORE2_GYRO")
    http_requests = list(probe.requests)
    checks = {
        **{
            f"serial:{marker}": marker in serial
            for marker in REQUIRED_MARKERS
        },
        **{
            f"peer:{marker}": marker in peer
            for marker in PEER_MARKERS
        },
        "serial:UNIFIED_CORE2_TOUCH": "UNIFIED_CORE2_TOUCH" in serial,
        "numeric:accel": close_values(accel, (0.25, -0.5, 0.75), 0.02),
        "numeric:gyro": close_values(gyro, (10, -20, 30), 0.1),
        "http:controlled_request": (
            {"path": "/unified", "host": "qemu.test"} in http_requests
        ),
        "frame:nonblank": (
            before_stats[0] > 16 and after_stats[0] > 16
        ),
        "frame:input_changed": frame_changed,
        "qom:power": (
            qom.get("/machine/axp2101.vbat-mv") == 4000
            and qom.get("/machine/axp2101.vin-mv") == 5000
            and qom.get("/machine/axp2101.charging") is True
        ),
        "qom:ina3221": (
            qom.get("/machine/ina3221-40.bus1-mv") == 4800
            and qom.get("/machine/ina3221-40.current1-ma") == 240
        ),
        "qom:imu": (
            qom.get("/machine/mpu6886.accel-x") == 0.25
            and qom.get("/machine/mpu6886.gyro-x") == 10
        ),
        "audio:pcm_nonzero": pcm_nonzero > 1000,
        "audio:pcm_peak_to_peak": pcm_peak_to_peak > 64,
        "microphone:source": microphone_nonzero > 1000,
    }
    if args.ble_transport == "native-vhci":
        checks.update(
            {
                "bridge:ready": "NATIVE_VHCI_BRIDGE_READY" in bridge,
                "bridge:h2c": "NATIVE_VHCI_H2C" in bridge,
                "bridge:c2h": "NATIVE_VHCI_C2H" in bridge,
                "bridge:acl_h2c": "NATIVE_VHCI_H2C 0201" in bridge,
                "bridge:acl_c2h": "NATIVE_VHCI_C2H 0201" in bridge,
            }
        )
    status = (
        "PASS" if terminal == "pass" and all(checks.values()) else "FAIL"
    )
    return {
        "attempt": attempt_index,
        "status": status,
        "terminal": terminal,
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
        "qom": qom,
        "audio": {
            "bytes": len(pcm),
            "nonzeros": pcm_nonzero,
            "peak_to_peak": pcm_peak_to_peak,
            "sha256": sha256(pcm),
        },
        "microphone": {
            "source_bytes": len(microphone),
            "source_nonzeros": microphone_nonzero,
            "source_sha256": sha256(microphone),
        },
        "http_requests": http_requests,
        "serial_bytes": len(serial_bytes),
        "serial_sha256": sha256(serial_bytes),
        "peer_log_bytes": len(peer_bytes),
        "peer_log_sha256": sha256(peer_bytes),
        "bridge_log_sha256": sha256(bridge_bytes),
        "native_symbols": native_symbols,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument("--http-port", type=int, default=HTTP_PORT)
    parser.add_argument(
        "--ble-transport",
        choices=("hci-uart", "native-vhci"),
        default="hci-uart",
    )
    parser.add_argument("--gdb", type=Path, default=default_gdb())
    parser.add_argument(
        "--native-elf",
        type=Path,
        default=ROOT / ".work/uiflow2-core2-symbols/micropython.elf",
    )
    parser.add_argument("--require-all-attempts", action="store_true")
    args = parser.parse_args()

    image = args.image.resolve()
    if not image.is_file() or image.stat().st_size != FLASH_SIZE:
        raise SystemExit(f"Core2 image must be exactly 16 MiB: {image}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.ble_transport == "native-vhci" and not args.gdb.exists():
        raise SystemExit(f"GDB does not exist: {args.gdb}")
    if args.ble_transport == "native-vhci" and not args.native_elf.exists():
        raise SystemExit(f"native ELF does not exist: {args.native_elf}")
    attempts = []
    with ControlledHttp(args.http_port) as probe:
        for attempt_index in range(1, args.attempts + 1):
            result = run_attempt(
                args,
                image,
                args.out_dir / f"attempt-{attempt_index}",
                attempt_index,
                probe,
            )
            attempts.append(result)
            print(
                f"attempt={attempt_index} status={result['status']} "
                f"terminal={result['terminal']}"
            )
            if result["status"] == "PASS" and not args.require_all_attempts:
                break
            probe.requests.clear()

    passed = [attempt for attempt in attempts if attempt["status"] == "PASS"]
    status = (
        "PASS"
        if (
            len(passed) == len(attempts)
            if args.require_all_attempts
            else bool(passed)
        )
        else "FAIL"
    )
    selected = passed[0] if passed else attempts[-1]
    evidence = {
        "schema_version": 1,
        "scope": "simulation-only-not-hardware-validation",
        "status": status,
        "device_id": "core2",
        "ble_transport": args.ble_transport,
        "firmware": {
            "path": str(image),
            "bytes": image.stat().st_size,
            "sha256": sha256(image.read_bytes()),
        },
        "attempts": attempts,
        "selected_attempt": selected["attempt"],
        "require_all_attempts": args.require_all_attempts,
        "not_claimed": [
            "real-hardware behavior",
            (
                "bit-exact Espressif BT baseband/controller implementation"
                if args.ble_transport == "native-vhci"
                else "native ESP32 Bluetooth controller/radio model"
            ),
            "RF privacy, security, range or performance",
            "hardware equivalence of deterministic TCG/icount scheduling",
        ],
    }
    (args.out_dir / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
