#!/usr/bin/env python3
"""Exercise stock Core2 H2C and optional VHCI C2H callback delivery."""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from qemu_accel import core2_accel_args  # noqa: E402

DEFAULT_QEMU = (
    ROOT
    / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
DEFAULT_ELF = ROOT / ".work/uiflow2-core2-symbols/micropython.elf"
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"
DEVICE_PATH = "/machine/peripheral-anon/device[0]"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class QMP:
    def __init__(self, path: Path, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while True:
            if path.exists():
                sock = socket.socket(
                    socket.AF_UNIX, socket.SOCK_STREAM
                )
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
        if "QMP" not in json.loads(self.stream.readline()):
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
        self.stream.write(
            json.dumps(payload).encode("utf-8") + b"\n"
        )
        while True:
            response = json.loads(self.stream.readline())
            if "event" in response:
                continue
            if "error" in response:
                raise RuntimeError(
                    f"QMP {name} failed: {response['error']}"
                )
            return response.get("return")

    def get(self, property_name: str) -> Any:
        return self.command(
            "qom-get",
            {"path": DEVICE_PATH, "property": property_name},
        )

    def close(self) -> None:
        self.stream.close()
        self.sock.close()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_qmp_value(
    qmp: QMP,
    property_name: str,
    predicate,
    timeout: float,
) -> Any:
    deadline = time.monotonic() + timeout
    while True:
        value = qmp.get(property_name)
        if predicate(value):
            return value
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"timeout waiting for {property_name}: {value!r}"
            )
        time.sleep(0.02)


def read_h4_packet(peer: socket.socket, timeout: float) -> bytes:
    peer.settimeout(0.2)
    data = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            chunk = peer.recv(4096)
        except TimeoutError:
            chunk = b""
        if chunk:
            data.extend(chunk)
            if len(data) >= 4:
                expected = 4 + data[3]
                if len(data) >= expected:
                    return bytes(data[:expected])
        time.sleep(0.02)
    raise RuntimeError(
        f"timeout waiting for H4 command: {bytes(data).hex()}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument(
        "--env-pointer-address",
        default="0x3ffcc0a4",
    )
    parser.add_argument(
        "--c2h-scratch-address",
        help="Guest buffer used to deliver controller-to-host packets",
    )
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument(
        "--enable-c2h",
        action="store_true",
        help="Deliver C2H packets through the registered firmware callback",
    )
    parser.add_argument(
        "--c2h-allocator-address",
        help="Guest malloc-compatible symbol used for the C2H buffer",
    )
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    c2h_enabled = bool(args.enable_c2h or args.c2h_scratch_address)
    allocator_address = (
        int(args.c2h_allocator_address, 0)
        if args.c2h_allocator_address
        else 0
    )
    if c2h_enabled and not args.c2h_scratch_address and not allocator_address:
        if not args.elf.is_file():
            parser.error(f"ELF does not exist: {args.elf}")
        sys.path.insert(0, str(ROOT / "platform/tools"))
        from xtensa_elf_symbols import resolve_symbols

        allocator_address = resolve_symbols(
            args.elf, ["malloc"]
        )["malloc"].value
    for label, path in (
        ("image", args.image),
        ("QEMU", args.qemu),
    ):
        if not path.is_file():
            parser.error(f"{label} does not exist: {path}")
    out_dir = args.out_dir or Path(
        tempfile.mkdtemp(prefix="m5-core2-guest-h2c-")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    serial = out_dir / "serial.log"
    qmp_path = out_dir / "qmp.sock"
    port = free_port()
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(1)
    listener.settimeout(args.timeout)
    hci_device = (
        "esp32-native-hci,chardev=hci,"
        f"env-pointer-address={args.env_pointer_address}"
    )
    if args.c2h_scratch_address:
        hci_device += f",c2h-scratch-address={args.c2h_scratch_address}"
    elif allocator_address:
        hci_device += (
            f",c2h-allocator-address=0x{allocator_address:08x}"
            ",c2h-scratch-size=2048"
        )
    command = [
        str(args.qemu),
        "-snapshot",
        *core2_accel_args(),
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
        "-serial",
        f"file:{serial}",
        "-no-reboot",
        "-chardev",
        (
            "socket,id=hci,host=127.0.0.1,"
            f"port={port},server=off,nodelay=on"
        ),
        "-device",
        hci_device,
        "-qmp",
        f"unix:{qmp_path},server=on,wait=off",
    ]
    process = subprocess.Popen(
        command,
        stdout=(out_dir / "qemu.stdout").open("wb"),
        stderr=(out_dir / "qemu.stderr").open("wb"),
    )
    peer: socket.socket | None = None
    qmp: QMP | None = None
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": (
            "m5stack-core2-native-hci-c2h-delivery"
            if c2h_enabled
            else "m5stack-core2-guest-h2c-capture"
        ),
        "scope": (
            "virtual-device H2C and C2H callback transport"
            if c2h_enabled
            else "virtual-device guest-to-QEMU transport"
        ),
        "status": "FAIL",
        "firmware": {
            "file": args.image.name,
            "sha256": sha256(args.image),
            "bytes": args.image.stat().st_size,
        },
        "qemu_sha256": sha256(args.qemu),
        "checks": {},
    }
    try:
        peer, _ = listener.accept()
        qmp = QMP(qmp_path, args.timeout)
        packet = read_h4_packet(peer, args.timeout)
        packets = wait_qmp_value(
            qmp,
            "h2c-packets",
            lambda value: value >= 1,
            args.timeout,
        )
        byte_count = qmp.get("h2c-bytes")
        result.update(
            {
                "packet": packet.hex(),
                "h2c_packets": packets,
                "h2c_bytes": byte_count,
                "checks": {
                    "stock_hci_reset_captured": (
                        packet == bytes.fromhex("01030c00")
                    ),
                    "qom_h2c_packet_count": packets == 1,
                    "qom_h2c_byte_count": byte_count == len(packet),
                    "peer_received_packet": len(packet) == 4,
                },
            }
        )
        if c2h_enabled:
            peer.sendall(bytes.fromhex("040e0401030c00"))
            next_packet = read_h4_packet(peer, args.timeout)
            delivered = wait_qmp_value(
                qmp,
                "c2h-delivered",
                lambda value: value >= 1,
                args.timeout,
            )
            packets_after_c2h = wait_qmp_value(
                qmp,
                "h2c-packets",
                lambda value: value >= 2,
                args.timeout,
            )
            send_available = qmp.get("c2h-send-available")
            callback_errors = qmp.get("c2h-errors")
            callback_status = qmp.get("c2h-last-status")
            result.update(
                {
                    "next_packet": next_packet.hex(),
                    "c2h_delivered": delivered,
                    "h2c_packets_after_c2h": packets_after_c2h,
                    "c2h_send_available": send_available,
                    "c2h_errors": callback_errors,
                    "c2h_last_status": callback_status,
                }
            )
            result["checks"].update(
                {
                    "reset_complete_delivered": delivered >= 1,
                    "guest_command_progressed": (
                        next_packet[0] == 0x01 and next_packet != packet
                    ),
                    "qom_callback_status_zero": callback_status == 0,
                    "qom_callback_no_errors": callback_errors == 0,
                    "qom_send_available_called": send_available >= 1,
                }
            )
        if not all(result["checks"].values()):
            raise RuntimeError(f"capture checks failed: {result['checks']}")
        result["status"] = "PASS"
        result["not_claimed"] = [
            "complete HCI command sequence",
            "BLE connection or GATT",
            "bit-exact controller/baseband",
            "physical hardware",
        ]
    except Exception as error:
        result["error"] = str(error)
        if qmp is not None:
            result["diagnostics"] = {}
            for property_name in (
                "rx-queue-depth",
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
                "last-error",
            ):
                try:
                    result["diagnostics"][property_name] = qmp.get(
                        property_name
                    )
                except (OSError, RuntimeError) as diagnostic_error:
                    result["diagnostics"][property_name] = (
                        f"unavailable: {diagnostic_error}"
                    )
        raise
    finally:
        if peer is not None:
            peer.close()
        listener.close()
        if qmp is not None:
            try:
                qmp.command("quit")
            except (OSError, RuntimeError):
                pass
            qmp.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        result["qemu_exit_code"] = process.returncode
        if process.returncode != 0:
            result["status"] = "FAIL"
            result["checks"]["qemu_clean_exit"] = False
        else:
            result["checks"]["qemu_clean_exit"] = True
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
