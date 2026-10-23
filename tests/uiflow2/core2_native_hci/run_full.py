#!/usr/bin/env python3
"""Run the complete stock Core2 BLE exchange through QEMU native HCI."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QEMU = (
    ROOT
    / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
DEFAULT_ELF = ROOT / ".work/uiflow2-core2-symbols/micropython.elf"
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"
DEVICE_PATH = "/machine/peripheral-anon/device[0]"
BLE_PROBE = ROOT / "platform/tools/ble_probe.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except FileNotFoundError:
        return ""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class QMP:
    def __init__(self, path: Path, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while True:
            if path.exists():
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    sock.connect(str(path))
                    self.sock = sock
                    break
                except OSError:
                    sock.close()
            if time.monotonic() >= deadline:
                raise RuntimeError("QMP socket did not become ready")
            time.sleep(0.02)
        self.stream = self.sock.makefile("rwb", buffering=0)
        greeting = json.loads(self.stream.readline())
        if "QMP" not in greeting:
            raise RuntimeError("invalid QMP greeting")
        self.command("qmp_capabilities")

    def command(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        payload: dict[str, Any] = {"execute": name}
        if arguments is not None:
            payload["arguments"] = arguments
        self.stream.write(json.dumps(payload).encode() + b"\n")
        while True:
            response = json.loads(self.stream.readline())
            if "event" in response:
                continue
            if "error" in response:
                raise RuntimeError(f"QMP {name} failed: {response['error']}")
            return response.get("return")

    def get(self, property_name: str) -> Any:
        return self.command(
            "qom-get",
            {"path": DEVICE_PATH, "property": property_name},
        )

    def close(self) -> None:
        self.stream.close()
        self.sock.close()


def start_ble_probe(
    *,
    port: int,
    log_path: Path,
    name_prefix: str,
    payload: str,
    timeout: float,
) -> tuple[subprocess.Popen, threading.Event]:
    ready = threading.Event()
    environment = os.environ.copy()
    environment["BLE_HCI_TRACE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [
                str(ROOT / ".work/py"),
                environment.get("PYTHONPATH", ""),
            ],
        )
    )
    command = [
        sys.executable,
        str(BLE_PROBE),
        "--port",
        str(port),
        "--name-prefix",
        name_prefix,
        "--payload",
        payload,
        "--timeout",
        f"{max(10, timeout - 5):g}",
        "--write-delay",
        "3",
        "--linger",
        "5",
        "--expect-notification-prefix",
        "ACK:",
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    assert process.stdout is not None
    log = log_path.open("w")

    def collect() -> None:
        for line in process.stdout:
            log.write(line)
            log.flush()
            if "BLE_PROBE_READY" in line:
                ready.set()
        log.close()

    threading.Thread(
        target=collect,
        name="m5-core2-native-hci-ble-log",
        daemon=True,
    ).start()
    return process, ready


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
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--name-prefix", default="M5-CORE2-HCI")
    parser.add_argument("--payload", default="M5_CORE2_NATIVE_PROBE")
    args = parser.parse_args()

    for label, path in (
        ("image", args.image),
        ("QEMU", args.qemu),
        ("ELF", args.elf),
    ):
        if not path.is_file():
            parser.error(f"{label} does not exist: {path}")

    sys.path.insert(0, str(ROOT / "platform/tools"))
    from xtensa_elf_symbols import resolve_symbols

    symbols = resolve_symbols(
        args.elf,
        ["vhci_env_p", "malloc", "esp_cpu_wait_for_intr"],
    )
    out_dir = args.out_dir or Path(
        tempfile.mkdtemp(prefix="m5-core2-native-hci-full-")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    serial = out_dir / "serial.log"
    ble_log = out_dir / "ble-probe.log"
    qmp_path = out_dir / "qmp.sock"
    ble_port = free_port()
    ble_process: subprocess.Popen | None = None
    qemu_process: subprocess.Popen | None = None
    qmp: QMP | None = None
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "m5stack-core2-native-hci-full-sequence",
        "scope": "virtual-device complete HCI/GATT through QEMU native HCI",
        "status": "FAIL",
        "firmware": {
            "file": args.image.name,
            "sha256": sha256(args.image),
            "bytes": args.image.stat().st_size,
        },
        "qemu_sha256": sha256(args.qemu),
        "elf_sha256": sha256(args.elf),
        "symbols": {
            "vhci_env_p": f"0x{symbols['vhci_env_p'].value:08x}",
            "malloc": f"0x{symbols['malloc'].value:08x}",
            "esp_cpu_wait_for_intr": (
                f"0x{symbols['esp_cpu_wait_for_intr'].value:08x}"
            ),
        },
        "checks": {},
    }
    try:
        ble_process, ble_ready = start_ble_probe(
            port=ble_port,
            log_path=ble_log,
            name_prefix=args.name_prefix,
            payload=args.payload,
            timeout=args.timeout,
        )
        if not ble_ready.wait(timeout=10):
            raise RuntimeError("Bumble controller did not become ready")

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
            f"file={args.image},if=mtd,format=raw",
            "-L",
            str(args.rom_dir),
            "-display",
            "none",
            "-d",
            "guest_errors",
            "-serial",
            f"file:{serial}",
            "-no-reboot",
            "-chardev",
            (
                "socket,id=hci,host=127.0.0.1,"
                f"port={ble_port},server=off,nodelay=on"
            ),
            "-device",
            (
                "esp32-native-hci,chardev=hci,"
                f"env-pointer-address=0x{symbols['vhci_env_p'].value:08x},"
                f"c2h-allocator-address=0x{symbols['malloc'].value:08x},"
                "c2h-scratch-size=2048"
            ),
            "-qmp",
            f"unix:{qmp_path},server=on,wait=off",
        ]
        qemu_process = subprocess.Popen(
            command,
            stdout=(out_dir / "qemu.stdout").open("wb"),
            stderr=(out_dir / "qemu.stderr").open("wb"),
        )
        qmp = QMP(qmp_path, min(args.timeout, 30))
        deadline = time.monotonic() + args.timeout
        ble_exited_at: float | None = None
        while time.monotonic() < deadline:
            serial_text = read_text(serial)
            ble_text = read_text(ble_log)
            if (
                "BLE_BUMBLE_PASS" in ble_text
                and "CORE2_HCI_BLE_ACK_SENT" in serial_text
            ):
                break
            if qemu_process.poll() is not None:
                break
            if ble_process.poll() is not None:
                ble_exited_at = ble_exited_at or time.monotonic()
                if time.monotonic() - ble_exited_at >= 3:
                    break
            time.sleep(0.2)
        else:
            result["error"] = "complete HCI/GATT sequence timed out"

        serial_text = read_text(serial)
        ble_text = read_text(ble_log)
        counters = {}
        if qmp is not None:
            for name in (
                "h2c-packets",
                "h2c-bytes",
                "h2c-duplicates",
                "c2h-delivered",
                "c2h-errors",
                "c2h-send-available",
                "c2h-last-status",
                "c2h-last-pc",
                "c2h-observed-pc",
                "c2h-observed-halted",
                "c2h-return-pc",
                "c2h-exit-pc",
                "c2h-steps",
                "c2h-exception-index",
                "rx-queue-depth",
                "tx-queue-depth",
                "malformed-packets",
                "dropped-packets",
                "last-error",
            ):
                try:
                    counters[name] = qmp.get(name)
                except (OSError, RuntimeError) as error:
                    counters[name] = f"unavailable: {error}"
        result["counters"] = counters
        result["checks"] = {
            "ble_controller_ready": "BLE_PROBE_READY" in ble_text,
            "advertisement_found": "BLE_BUMBLE_FOUND" in ble_text,
            "ble_connected": "BLE_BUMBLE_CONNECTED" in ble_text,
            "gatt_discovered": "BLE_BUMBLE_GATT_DISCOVERED" in ble_text,
            "notification_subscribed": "BLE_BUMBLE_SUBSCRIBED" in ble_text,
            "guest_received_write": "CORE2_HCI_BLE_RX" in serial_text,
            "guest_sent_ack": "CORE2_HCI_BLE_ACK_SENT" in serial_text,
            "notification_ack_observed": (
                "BLE_BUMBLE_NOTIFICATION_OK" in ble_text
            ),
            "bumble_pass": "BLE_BUMBLE_PASS" in ble_text,
            "no_callback_errors": counters.get("c2h-errors") == 0,
            "no_malformed_packets": counters.get("malformed-packets") == 0,
            "no_dropped_packets": counters.get("dropped-packets") == 0,
        }
        if all(result["checks"].values()):
            result["status"] = "PASS"
            result.pop("error", None)
        elif "error" not in result:
            result["error"] = "one or more native HCI checks failed"
        result["not_claimed"] = [
            "bit-exact Espressif BT controller/baseband",
            "physical hardware",
        ]
    except Exception as error:
        result["error"] = str(error)
    finally:
        if qmp is not None:
            try:
                qmp.command("quit")
            except (OSError, RuntimeError):
                pass
            qmp.close()
        stop_process(qemu_process)
        stop_process(ble_process)
        result["qemu_exit_code"] = (
            qemu_process.returncode if qemu_process is not None else None
        )
        result["ble_probe_exit_code"] = (
            ble_process.returncode if ble_process is not None else None
        )
        evidence = out_dir / "evidence.json"
        evidence.write_text(
            json.dumps(result, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, indent=2))
        print(f"evidence={evidence}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
