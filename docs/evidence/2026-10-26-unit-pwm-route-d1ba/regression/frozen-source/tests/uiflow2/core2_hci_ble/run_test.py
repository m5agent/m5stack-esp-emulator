#!/usr/bin/env python3
"""Prove Core2 UIFlow2 BLE through a real HCI-UART controller data plane."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROBE_DIR = Path(__file__).resolve().parent
COMMON_LIB = ROOT / "tests/uiflow2/lib"
PUBLIC_BASE = ROOT / "platform/.cache/firmware/core2/uiflow2.bin"
DEFAULT_APP_BUILD = (
    ROOT
    / ".work/uiflow-core2-2.5.3/m5stack/build-M5STACK_Core2-hciuart3"
)
DEFAULT_QEMU = (
    ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"
DEFAULT_LITTLEFS = (
    ROOT / ".work/uiflow-core2-2.5.3/tools/littlefs/prebuilt/littlefs2"
)
BLE_PROBE = ROOT / "platform/tools/ble_probe.py"

FLASH_SIZE = 0x1000000
BOOTLOADER_OFFSET = 0x1000
PARTITION_OFFSET = 0x8000
APP_OFFSET = 0x10000
VFS_OFFSET = 0x820000
VFS_SIZE = 0x7DF000

SERIAL_MARKERS = (
    "CORE2_HCI_BOOT",
    "CORE2_HCI_MAIN_START",
    "CORE2_HCI_BLE_READY",
    "CORE2_HCI_BLE_RX",
    "CORE2_HCI_BLE_ACK_SENT",
)
PROBE_MARKERS = (
    "BLE_BUMBLE_FOUND",
    "BLE_BUMBLE_CONNECTED",
    "BLE_BUMBLE_GATT_DISCOVERED",
    "BLE_BUMBLE_SUBSCRIBED",
    "BLE_BUMBLE_WRITE",
    "BLE_BUMBLE_NOTIFICATION_OK",
    "BLE_BUMBLE_PASS",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def read_markers(path: Path, markers: tuple[str, ...]) -> dict[str, bool]:
    text = path.read_text(errors="replace") if path.exists() else ""
    return {marker: marker in text for marker in markers}


def read_sdkconfig(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def verify_hci_build(build_dir: Path, base: Path) -> dict[str, str]:
    sdkconfig_path = build_dir / "sdkconfig"
    required_files = (
        build_dir / "bootloader/bootloader.bin",
        build_dir / "partition_table/partition-table.bin",
        build_dir / "micropython.bin",
        build_dir / "micropython.elf",
        sdkconfig_path,
    )
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        raise RuntimeError("missing HCI-UART build files: " + ", ".join(missing))

    config = read_sdkconfig(sdkconfig_path)
    expected = {
        "CONFIG_BT_CONTROLLER_DISABLED": "y",
        "CONFIG_BT_NIMBLE_TRANSPORT_UART": "y",
        "CONFIG_BT_NIMBLE_TRANSPORT_UART_PORT": "1",
        "CONFIG_BT_NIMBLE_UART_RX_PIN": "32",
        "CONFIG_BT_NIMBLE_UART_TX_PIN": "33",
    }
    mismatches = {
        key: config.get(key)
        for key, value in expected.items()
        if config.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"unexpected HCI-UART config: {mismatches}")

    watchdog_ms = int(config.get("CONFIG_ESP_INT_WDT_TIMEOUT_MS", "0"))
    if watchdog_ms < 10000:
        raise RuntimeError(
            "Core2 HCI test build needs CONFIG_ESP_INT_WDT_TIMEOUT_MS >= 10000 "
            "so QEMU flash service does not trigger a false interrupt watchdog"
        )
    if not base.is_file():
        raise RuntimeError(f"public core2 base image is missing: {base}")
    return {
        key: config[key]
        for key in (
            "CONFIG_BT_CONTROLLER_DISABLED",
            "CONFIG_BT_NIMBLE_TRANSPORT_UART",
            "CONFIG_BT_NIMBLE_TRANSPORT_UART_PORT",
            "CONFIG_BT_NIMBLE_UART_RX_PIN",
            "CONFIG_BT_NIMBLE_UART_TX_PIN",
            "CONFIG_BT_NIMBLE_HCI_UART_BAUDRATE",
            "CONFIG_ESP_INT_WDT_TIMEOUT_MS",
        )
        if key in config
    }


def append_segment(image: bytearray, offset: int, path: Path) -> None:
    data = path.read_bytes()
    end = offset + len(data)
    if end > len(image):
        raise RuntimeError(f"{path} does not fit at {offset:#x}")
    image[offset:end] = data


def build_flash_image(
    base: Path,
    build_dir: Path,
    littlefs_tool: Path,
    out_dir: Path,
) -> Path:
    image = bytearray(base.read_bytes())
    if len(image) > FLASH_SIZE:
        raise RuntimeError(f"base image is larger than {FLASH_SIZE:#x}")
    image.extend(b"\xff" * (FLASH_SIZE - len(image)))
    append_segment(image, BOOTLOADER_OFFSET, build_dir / "bootloader/bootloader.bin")
    append_segment(
        image,
        PARTITION_OFFSET,
        build_dir / "partition_table/partition-table.bin",
    )
    append_segment(image, APP_OFFSET, build_dir / "micropython.bin")

    with tempfile.TemporaryDirectory(prefix="core2-hci-files-") as temp:
        files_dir = Path(temp) / "files"
        files_dir.mkdir()
        for source in (COMMON_LIB / "rtc_probe.py", PROBE_DIR / "boot.py", PROBE_DIR / "main.py"):
            shutil.copyfile(source, files_dir / source.name)
        vfs_path = Path(temp) / "vfs.bin"
        subprocess.run(
            [
                str(littlefs_tool),
                "-c",
                "-b",
                "core2",
                "-i",
                str(files_dir),
                "-o",
                str(vfs_path),
                "-s",
                hex(VFS_SIZE),
            ],
            check=True,
            timeout=60,
        )
        vfs = vfs_path.read_bytes()
        if len(vfs) != VFS_SIZE:
            raise RuntimeError(
                f"LittleFS produced {len(vfs):#x} bytes, expected {VFS_SIZE:#x}"
            )
        image[VFS_OFFSET : VFS_OFFSET + VFS_SIZE] = vfs

    image_path = out_dir / "core2-hci-ble-full.bin"
    image_path.write_bytes(image)
    return image_path


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_marker(path: Path, marker: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and marker in path.read_text(errors="replace"):
            return True
        time.sleep(0.05)
    return False


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def run_attempt(
    args: argparse.Namespace,
    firmware: Path,
    attempt_dir: Path,
) -> dict:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    attempt_image = attempt_dir / "firmware-under-test.bin"
    shutil.copyfile(firmware, attempt_image)
    serial_path = attempt_dir / "serial.log"
    probe_log = attempt_dir / "ble-probe.log"
    qemu_stdout = attempt_dir / "qemu.stdout"
    qemu_stderr = attempt_dir / "qemu.stderr"
    port = free_tcp_port()

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )
    with probe_log.open("wb") as probe_output:
        probe = subprocess.Popen(
            [
                "python3",
                str(BLE_PROBE),
                "--port",
                str(port),
                "--name-prefix",
                "M5-CORE2-HCI",
                "--payload",
                "M5_CORE2_HCI",
                "--subscribe",
                "--expect-notification-prefix",
                "ACK:",
                "--notification-timeout",
                str(args.notification_timeout),
                "--timeout",
                str(args.probe_timeout),
                "--write-delay",
                "1",
                "--linger",
                "1",
            ],
            cwd=ROOT,
            env=env,
            stdout=probe_output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        if not wait_for_marker(probe_log, "BLE_PROBE_READY", 10):
            stop_process(probe)
            raise RuntimeError("Bumble controller did not become ready")

        with qemu_stdout.open("wb") as stdout, qemu_stderr.open("wb") as stderr:
            qemu = subprocess.Popen(
                [
                    str(args.qemu),
                    "-m",
                    "0",
                    "-M",
                    "m5core2",
                    "-drive",
                    f"file={attempt_image},if=mtd,format=raw",
                    "-L",
                    str(args.rom_dir),
                    "-display",
                    "none",
                    "-serial",
                    f"file:{serial_path}",
                    "-chardev",
                    (
                        "socket,id=hci,host=127.0.0.1,"
                        f"port={port},nodelay=on"
                    ),
                    "-serial",
                    "chardev:hci",
                    "-no-reboot",
                ],
                cwd=ROOT,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
        deadline = time.monotonic() + args.timeout
        terminal = "timeout"
        try:
            while time.monotonic() < deadline:
                probe_text = probe_log.read_text(errors="replace")
                serial_text = (
                    serial_path.read_text(errors="replace")
                    if serial_path.exists()
                    else ""
                )
                if "BLE_BUMBLE_PASS" in probe_text:
                    terminal = "probe_pass"
                    break
                if "BLE_BUMBLE_FAIL" in probe_text or "BLE_BUMBLE_ERROR" in probe_text:
                    terminal = "probe_fail"
                    break
                if "Guru Meditation" in serial_text or "Rebooting..." in serial_text:
                    terminal = "guest_crash"
                    break
                if probe.poll() is not None:
                    terminal = "probe_exit"
                    break
                if qemu.poll() is not None:
                    terminal = "qemu_exit"
                    break
                time.sleep(0.1)
        finally:
            stop_process(qemu)
            stop_process(probe)

    serial_markers = read_markers(serial_path, SERIAL_MARKERS)
    probe_markers = read_markers(probe_log, PROBE_MARKERS)
    passed = (
        terminal == "probe_pass"
        and all(serial_markers.values())
        and all(probe_markers.values())
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "terminal": terminal,
        "firmware_sha256_before": sha256(attempt_image),
        "firmware_sha256_after": sha256(attempt_image),
        "serial_markers": serial_markers,
        "probe_markers": probe_markers,
        "serial_sha256": sha256(serial_path),
        "probe_log_sha256": sha256(probe_log),
        "serial_path": display_path(serial_path),
        "probe_log_path": display_path(probe_log),
        "qemu_stderr": qemu_stderr.read_text(errors="replace")[-2000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=PUBLIC_BASE)
    parser.add_argument("--app-build-dir", type=Path, default=DEFAULT_APP_BUILD)
    parser.add_argument("--littlefs", type=Path, default=DEFAULT_LITTLEFS)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument("--out-dir", type=Path, default=Path("/tmp/core2-hci-ble"))
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--probe-timeout", type=float, default=25)
    parser.add_argument("--notification-timeout", type=float, default=10)
    args = parser.parse_args()

    for label, path in (
        ("base image", args.base),
        ("application build", args.app_build_dir),
        ("LittleFS tool", args.littlefs),
        ("QEMU", args.qemu),
        ("ROM directory", args.rom_dir),
    ):
        if not path.exists():
            parser.error(f"{label} does not exist: {path}")
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    config = verify_hci_build(args.app_build_dir, args.base)
    firmware = build_flash_image(
        args.base,
        args.app_build_dir,
        args.littlefs,
        args.out_dir,
    )
    firmware_hash = sha256(firmware)
    attempts = []
    for index in range(1, args.attempts + 1):
        result = run_attempt(args, firmware, args.out_dir / f"attempt-{index}")
        result["attempt"] = index
        attempts.append(result)
        print(
            f"attempt={index} status={result['status']} "
            f"terminal={result['terminal']}"
        )

    passed_attempts = sum(attempt["status"] == "PASS" for attempt in attempts)
    status = "PASS" if passed_attempts == len(attempts) else "FAIL"
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-core2-hci-offload-ble-gatt",
        "status": status,
        "scope": (
            "UIFlow2 NimBLE HCI-UART host and external Bumble controller/link "
            "through the QEMU Core2 UART1 data plane"
        ),
        "firmware": {
            "path": display_path(firmware),
            "sha256": firmware_hash,
            "size": firmware.stat().st_size,
            "public_base": display_path(args.base),
            "public_base_sha256": sha256(args.base),
            "application_bin_sha256": sha256(
                args.app_build_dir / "micropython.bin"
            ),
            "application_elf_sha256": sha256(
                args.app_build_dir / "micropython.elf"
            ),
            "hci_uart_config": config,
        },
        "attempts": attempts,
        "passed_attempts": passed_attempts,
        "total_attempts": len(attempts),
        "gatt": {
            "service": "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
            "subscribe": "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
            "write": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
            "payload": "M5_CORE2_HCI",
            "notification": "ACK:M5_CORE2_HCI",
        },
        "not_claimed": [
            "native ESP32 Bluetooth radio/controller model",
            "RF range, timing, coexistence or performance",
            "BLE pairing, security or production-throughput behavior",
            "real-hardware behavior",
        ],
    }
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"status={status} attempts={passed_attempts}/{len(attempts)}")
    print(f"evidence={evidence_path}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
