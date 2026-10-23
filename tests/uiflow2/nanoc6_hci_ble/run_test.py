#!/usr/bin/env python3
"""Prove NanoC6 board peripherals and UART1 HCI BLE in one C6 guest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/uiflow2"))

from run_profile_ui_test import wait_qmp  # noqa: E402

DEFAULT_QEMU = (
    ROOT / ".work/M5StopWatch-QEMU/build/qemu-c6/build/qemu-system-riscv32"
)
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu-c6/pc-bios"
BLE_PROBE = ROOT / "platform/tools/ble_probe.py"
FLASH_SIZE = 4 << 20

BOARD_MARKERS = (
    "NANOC6_HCI_BOARD 140",
    "NANOC6_HCI_RGB 1 00FF00",
    "NANOC6_HCI_BLUE 1",
    "NANOC6_HCI_IR 0x56 0xA3",
    "NANOC6_HCI_BUTTON_READY",
    "NANOC6_HCI_BUTTON_PRESS",
    "NANOC6_HCI_BUTTON_RELEASE",
    "NANOC6_HCI_BLUE 0",
    "NANOC6_HCI_READY",
)
BLE_MARKERS = (
    "NANOC6_HCI_BLE_READY",
    "NANOC6_HCI_BLE_RX",
    "NANOC6_HCI_BLE_ACK_SENT",
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


def wait_for_text(path: Path, marker: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.is_file() and marker in path.read_text(errors="replace"):
            return True
        if not path.is_file():
            time.sleep(0.05)
        else:
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
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    args = parser.parse_args()

    image = args.image.resolve()
    if not image.is_file() or image.stat().st_size != FLASH_SIZE:
        raise SystemExit(f"NanoC6 image must be exactly 4 MiB: {image}")
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    serial_path = out / "serial.log"
    peer_path = out / "ble-probe.log"
    rmt_path = out / "rmt-capture.bin"
    serial_path.write_bytes(b"")
    peer_path.write_bytes(b"")
    rmt_path.unlink(missing_ok=True)
    qmp_path = Path("/tmp") / f"m5-nanoc6-hci-{os.getpid()}.sock"
    qmp_path.unlink(missing_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )
    env["M5SW_C6_BOARD"] = "nanoc6"
    env["M5SW_RMT_TX_FILE"] = str(rmt_path)
    env["M5SW_RMT_TRACE"] = "1"
    env["BLE_HCI_TRACE"] = "1"

    hci_port = free_port()
    peer_process: subprocess.Popen | None = None
    qemu: subprocess.Popen | None = None
    qmp = None
    try:
        with peer_path.open("wb") as peer_log:
            peer_process = subprocess.Popen(
                [
                    sys.executable,
                    str(BLE_PROBE),
                    "--port",
                    str(hci_port),
                    "--name-prefix",
                    "M5-NANOC6-HCI",
                    "--payload",
                    "M5_NANOC6_HCI",
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
                    "10",
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
            f"file={image},if=mtd,format=raw",
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
        if not wait_for_text(serial_path, "NANOC6_HCI_BUTTON_READY", 40):
            raise RuntimeError("NanoC6 board/button setup timed out")
        if not wait_for_text(serial_path, "NANOC6_HCI_READY", 20):
            raise RuntimeError("NanoC6 BLE server setup timed out")

        gpio_before = {
            "gpio7": qom_value(qmp, "/machine", "gpio7-level"),
            "gpio9": qom_value(qmp, "/machine", "gpio9-level"),
            "gpio19": qom_value(qmp, "/machine", "gpio19-level"),
        }
        qmp.cmd("qom-set", path="/machine", property="button-gpio9", value=True)
        if not wait_for_text(serial_path, "NANOC6_HCI_BUTTON_PRESS", 8):
            raise RuntimeError("NanoC6 button press was not observed")
        qmp.cmd("qom-set", path="/machine", property="button-gpio9", value=False)
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            serial = serial_path.read_text(errors="replace")
            peer = peer_path.read_text(errors="replace")
            if all(marker in serial for marker in BOARD_MARKERS) and all(
                marker in serial for marker in BLE_MARKERS
            ) and all(marker in peer for marker in PEER_MARKERS):
                break
            if qemu.poll() is not None:
                raise RuntimeError(f"QEMU exited with {qemu.returncode}")
            time.sleep(0.2)
        else:
            raise RuntimeError("NanoC6 HCI BLE exchange timed out")
        gpio_after = {
            "gpio7": qom_value(qmp, "/machine", "gpio7-level"),
            "gpio9": qom_value(qmp, "/machine", "gpio9-level"),
            "gpio19": qom_value(qmp, "/machine", "gpio19-level"),
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

    serial_bytes = serial_path.read_bytes()
    serial = serial_bytes.decode(errors="replace")
    peer_bytes = peer_path.read_bytes()
    peer = peer_bytes.decode(errors="replace")
    ws_check = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/uiflow2/check_rmt_ws2812.py"),
            str(rmt_path),
            "--led",
            "0,255,0",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    nec_check = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/uiflow2/check_rmt_nec.py"),
            str(rmt_path),
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
    checks = {
        **{f"serial:{marker}": marker in serial for marker in BOARD_MARKERS},
        **{f"serial:{marker}": marker in serial for marker in BLE_MARKERS},
        **{f"peer:{marker}": marker in peer for marker in PEER_MARKERS},
        "gpio:rgb_power": gpio_before["gpio19"] is True,
        "gpio:blue_on": gpio_before["gpio7"] is True,
        "gpio:button_idle_high": gpio_before["gpio9"] is True,
        "gpio:blue_off": gpio_after["gpio7"] is False,
        "gpio:button_release_high": gpio_after["gpio9"] is True,
        "rmt:ws2812_green": ws_check.returncode == 0,
        "rmt:nec": nec_check.returncode == 0,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    evidence = {
        "schema_version": 1,
        "scope": "simulation-only-not-hardware-validation",
        "status": status,
        "device_id": "nanoc6",
        "profile": "nanoc6-board-hci-ble",
        "firmware": {
            "path": str(image),
            "bytes": image.stat().st_size,
            "sha256": sha256(image.read_bytes()),
        },
        "checks": checks,
        "gpio": {"before": gpio_before, "after": gpio_after},
        "rmt": {
            "capture_bytes": rmt_path.stat().st_size
            if rmt_path.is_file()
            else 0,
            "capture_sha256": sha256(rmt_path.read_bytes())
            if rmt_path.is_file()
            else None,
            "ws2812_check": ws_check.stdout.strip(),
            "nec_check": nec_check.stdout.strip(),
        },
        "serial_bytes": len(serial_bytes),
        "serial_sha256": sha256(serial_bytes),
        "peer_log_bytes": len(peer_bytes),
        "peer_log_sha256": sha256(peer_bytes),
        "network": {
            "wifi": "NOT RUN",
            "wifi_reason": "QEMU ESP32-C6 machine has no WiFi MAC/PHY data plane",
            "ble": "PASS via UART1 HCI offload",
        },
        "not_claimed": [
            "real-hardware behavior",
            "WiFi on the QEMU C6 machine",
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
