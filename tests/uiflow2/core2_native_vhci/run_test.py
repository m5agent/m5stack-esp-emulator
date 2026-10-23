#!/usr/bin/env python3
"""Bridge stock Core2 VHCI traffic to an external Bumble controller/peer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROBE_DIR = Path(__file__).resolve().parent
FILES_DIR = ROOT / "tests/uiflow2/core2_hci_ble"
PROFILE_RUNNER = ROOT / "tests/uiflow2/run_profile_ui_test.py"
BLE_PROBE = ROOT / "platform/tools/ble_probe.py"
NATIVE_BRIDGE_GDB = (
    ROOT / "tests/uiflow2/core2_radio_probe/native_vhci_bridge.gdb"
)
NATIVE_BRIDGE_PY = (
    ROOT / "tests/uiflow2/core2_radio_probe/native_vhci_bridge.py"
)
DEFAULT_BASE = ROOT / "platform/.cache/firmware/core2/uiflow2.bin"
DEFAULT_ELF = ROOT / ".work/uiflow2-core2-symbols/micropython.elf"
DEFAULT_QEMU = (
    ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"

SERIAL_MARKERS = (
    "CORE2_HCI_BOOT",
    "CORE2_HCI_MAIN_START",
    "CORE2_HCI_BLE_READY",
    "CORE2_HCI_BLE_RX",
    "CORE2_HCI_BLE_ACK_SENT",
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
BRIDGE_MARKERS = (
    "NATIVE_VHCI_BRIDGE_READY",
    "NATIVE_VHCI_H2C",
    "NATIVE_VHCI_C2H",
    "NATIVE_VHCI_H2C 0201",
    "NATIVE_VHCI_C2H 0201",
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


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_text(path: Path) -> str:
    return path.read_text(errors="replace") if path.exists() else ""


def read_markers(path: Path, markers: tuple[str, ...]) -> dict[str, bool]:
    text = read_text(path)
    return {marker: marker in text for marker in markers}


def wait_for_marker(path: Path, marker: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker in read_text(path):
            return True
        time.sleep(0.05)
    return False


def default_gdb() -> Path:
    explicit = os.environ.get("M5_XTENSA_GDB")
    if explicit:
        return Path(explicit)
    installed = Path.home() / ".espressif/tools/xtensa-esp-elf-gdb"
    candidates = sorted(
        installed.glob("*/xtensa-esp-elf-gdb/bin/xtensa-esp32-elf-gdb")
    )
    if candidates:
        return candidates[-1]
    return Path("xtensa-esp32-elf-gdb")


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait(timeout=3)


def build_image(args: argparse.Namespace) -> Path:
    out_dir = args.out_dir / "image"
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "python3",
        str(PROFILE_RUNNER),
        "--base",
        str(args.base),
        "--machine",
        "m5core2",
        "--files-dir",
        str(FILES_DIR),
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
    subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=90)
    image = out_dir / "uiflow2-ui-test.bin"
    if not image.is_file():
        raise RuntimeError(f"image builder did not create {image}")
    return image


def run_attempt(
    args: argparse.Namespace,
    firmware: Path,
    attempt_dir: Path,
) -> dict:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    attempt_image = attempt_dir / "firmware-under-test.bin"
    shutil.copyfile(firmware, attempt_image)
    serial_path = attempt_dir / "serial.log"
    peer_log = attempt_dir / "ble-probe.log"
    bridge_log = attempt_dir / "native-vhci-gdb.log"
    qemu_stdout = attempt_dir / "qemu.stdout"
    qemu_stderr = attempt_dir / "qemu.stderr"
    hci_port = free_tcp_port()
    gdb_port = free_tcp_port()

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )
    env["BLE_HCI_TRACE"] = "1"
    env["M5_NATIVE_BT_ELF"] = str(args.elf.resolve())
    probe: subprocess.Popen | None = None
    qemu: subprocess.Popen | None = None
    gdb: subprocess.Popen | None = None
    terminal = "timeout"
    with (
        peer_log.open("wb") as peer_output,
        bridge_log.open("wb") as bridge_output,
        qemu_stdout.open("wb") as qemu_out,
        qemu_stderr.open("wb") as qemu_err,
    ):
        probe = subprocess.Popen(
            [
                "python3",
                str(BLE_PROBE),
                "--port",
                str(hci_port),
                "--name-prefix",
                "M5-CORE2-HCI",
                "--payload",
                "M5_CORE2_PROBE",
                "--subscribe",
                "--expect-notification-prefix",
                "ACK:",
                "--notification-timeout",
                str(args.notification_timeout),
                "--timeout",
                str(args.peer_timeout),
                "--write-delay",
                "2",
                "--linger",
                "5",
            ],
            cwd=ROOT,
            env=env,
            stdout=peer_output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        if not wait_for_marker(peer_log, "BLE_PROBE_READY", 10):
            terminal = "probe_not_ready"
        else:
            qemu = subprocess.Popen(
                [
                    str(args.qemu),
                    "-S",
                    "-gdb",
                    f"tcp::{gdb_port}",
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
                    f"file={attempt_image},if=mtd,format=raw",
                    "-L",
                    str(args.rom_dir),
                    "-display",
                    "none",
                    "-serial",
                    f"file:{serial_path}",
                    "-no-reboot",
                ],
                cwd=ROOT,
                stdout=qemu_out,
                stderr=qemu_err,
                start_new_session=True,
            )
            bridge_env = env.copy()
            bridge_env["M5_NATIVE_BT_HCI_PORT"] = str(hci_port)
            bridge_env["M5_NATIVE_GDB_PORT"] = str(gdb_port)
            gdb = subprocess.Popen(
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

            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                peer_text = read_text(peer_log)
                serial_text = read_text(serial_path)
                bridge_text = read_text(bridge_log)
                if "BLE_BUMBLE_PASS" in peer_text:
                    terminal = "peer_pass"
                    break
                if any(
                    marker in peer_text
                    for marker in (
                        "BLE_BUMBLE_FAIL",
                        "BLE_BUMBLE_ERROR",
                        "Traceback",
                    )
                ):
                    terminal = "peer_fail"
                    break
                if "Guru Meditation" in serial_text or "Rebooting..." in serial_text:
                    terminal = "guest_crash"
                    break
                if "NATIVE_VHCI_PARSE_ERROR" in bridge_text:
                    terminal = "bridge_parse_error"
                    break
                if "Fatal signal:" in bridge_text:
                    terminal = "gdb_abort"
                    break
                if probe.poll() is not None:
                    terminal = "probe_exit"
                    break
                if qemu.poll() is not None:
                    terminal = "qemu_exit"
                    break
                if gdb.poll() is not None:
                    terminal = "gdb_exit"
                    break
                time.sleep(0.1)

    stop_process(gdb)
    stop_process(qemu)
    stop_process(probe)

    serial_markers = read_markers(serial_path, SERIAL_MARKERS)
    peer_markers = read_markers(peer_log, PEER_MARKERS)
    bridge_markers = read_markers(bridge_log, BRIDGE_MARKERS)
    passed = (
        terminal == "peer_pass"
        and all(serial_markers.values())
        and all(peer_markers.values())
        and all(bridge_markers.values())
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "terminal": terminal,
        "firmware_sha256_before": sha256(attempt_image),
        "firmware_sha256_after": sha256(attempt_image),
        "serial_markers": serial_markers,
        "peer_markers": peer_markers,
        "bridge_markers": bridge_markers,
        "serial_sha256": sha256(serial_path),
        "peer_log_sha256": sha256(peer_log),
        "bridge_log_sha256": sha256(bridge_log),
        "serial_path": display_path(serial_path),
        "peer_log_path": display_path(peer_log),
        "bridge_log_path": display_path(bridge_log),
        "qemu_stderr": read_text(qemu_stderr)[-2000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--gdb", type=Path, default=default_gdb())
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/core2-native-vhci"),
    )
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=75)
    parser.add_argument("--peer-timeout", type=float, default=60)
    parser.add_argument("--notification-timeout", type=float, default=20)
    args = parser.parse_args()
    for label, path in (
        ("base image", args.base),
        ("ELF", args.elf),
        ("QEMU", args.qemu),
        ("GDB", args.gdb),
        ("ROM directory", args.rom_dir),
    ):
        if not path.exists():
            parser.error(f"{label} does not exist: {path}")
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    firmware = build_image(args)
    attempts = []
    for index in range(1, args.attempts + 1):
        result = run_attempt(
            args,
            firmware,
            args.out_dir / f"attempt-{index}",
        )
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
        "kind": "m5stack-core2-native-vhci-ble-gatt",
        "status": status,
        "scope": (
            "stock UIFlow2 built-in-controller build using the native ESP32 "
            "VHCI host API, with QEMU GDB bridging HCI to an external Bumble "
            "controller and peer"
        ),
        "firmware": {
            "path": display_path(firmware),
            "sha256": sha256(firmware),
            "size": firmware.stat().st_size,
            "public_base": display_path(args.base),
            "public_base_sha256": sha256(args.base),
            "elf": display_path(args.elf),
            "elf_sha256": sha256(args.elf),
            "uses_stock_internal_controller_build": True,
        },
        "runtime": {
            "qemu": display_path(args.qemu),
            "qemu_sha256": sha256(args.qemu),
            "gdb": display_path(args.gdb),
            "gdb_bridge": display_path(NATIVE_BRIDGE_PY),
            "gdb_bridge_sha256": sha256(NATIVE_BRIDGE_PY),
            "controller_boundary": "ESP32 VHCI host API",
            "external_controller": "Bumble",
        },
        "attempts": attempts,
        "passed_attempts": passed_attempts,
        "total_attempts": len(attempts),
        "gatt": {
            "service": "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
            "subscribe": "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
            "write": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
            "payload": "M5_CORE2_PROBE",
            "notification": "ACK:M5_CORE2_PROBE",
        },
        "not_claimed": [
            "bit-exact Espressif BT baseband/controller internal execution",
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
