#!/usr/bin/env python3
"""Capture the first stock Core2 H2C packet without a GDB bridge."""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QEMU = (
    ROOT
    / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"
DEVICE_PATH = "/machine/peripheral-anon/device[0]"


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
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
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
        "-serial",
        f"file:{serial}",
        "-no-reboot",
        "-chardev",
        (
            "socket,id=hci,host=127.0.0.1,"
            f"port={port},server=off,nodelay=on"
        ),
        "-device",
        (
            "esp32-native-hci,chardev=hci,"
            f"env-pointer-address={args.env_pointer_address}"
        ),
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
        "kind": "m5stack-core2-guest-h2c-capture",
        "scope": "virtual-device guest-to-QEMU transport",
        "status": "FAIL",
        "firmware": {
            "path": str(args.image),
            "bytes": args.image.stat().st_size,
        },
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
        if not all(result["checks"].values()):
            raise RuntimeError(f"capture checks failed: {result['checks']}")
        result["status"] = "PASS"
    except Exception as error:
        result["error"] = str(error)
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
