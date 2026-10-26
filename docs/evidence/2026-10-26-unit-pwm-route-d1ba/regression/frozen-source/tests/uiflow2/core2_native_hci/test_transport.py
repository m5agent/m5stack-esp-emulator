#!/usr/bin/env python3
"""Validate the QEMU esp32-native-hci chardev transport."""
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
DEVICE_PATH = "/machine/peripheral-anon/device[0]"


class QMP:
    def __init__(self, path: Path, timeout: float = 10) -> None:
        deadline = time.monotonic() + timeout
        while not path.exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("QMP socket did not appear")
            time.sleep(0.02)
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.connect(str(path))
        self.stream = self.socket.makefile("rwb", buffering=0)
        greeting = self._read()
        if "QMP" not in greeting:
            raise RuntimeError(f"invalid QMP greeting: {greeting!r}")
        self.command("qmp_capabilities")

    def _read(self) -> dict[str, Any]:
        line = self.stream.readline()
        if not line:
            raise RuntimeError("QMP connection closed")
        return json.loads(line)

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
            response = self._read()
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
        self.socket.close()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_value(
    qmp: QMP,
    property_name: str,
    expected: Any,
    timeout: float = 5,
) -> Any:
    deadline = time.monotonic() + timeout
    while True:
        value = qmp.get(property_name)
        if value == expected:
            return value
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"{property_name}: expected {expected!r}, got {value!r}"
            )
        time.sleep(0.02)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    if not args.qemu.is_file():
        parser.error(f"QEMU binary does not exist: {args.qemu}")
    out_dir = args.out_dir or Path(
        tempfile.mkdtemp(prefix="m5-core2-native-hci-")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    flash = out_dir / "blank-flash.bin"
    with flash.open("wb") as output:
        output.truncate(16 * 1024 * 1024)
    qmp_path = out_dir / "qmp.sock"
    port = free_port()
    command = [
        str(args.qemu),
        "-S",
        "-display",
        "none",
        "-M",
        "m5core2",
        "-drive",
        f"file={flash},if=mtd,format=raw",
        "-serial",
        "none",
        "-chardev",
        (
            "socket,id=hci,host=127.0.0.1,"
            f"port={port},server=on,wait=off,nodelay=on"
        ),
        "-device",
        "esp32-native-hci,chardev=hci",
        "-qmp",
        f"unix:{qmp_path},server=on,wait=off",
    ]
    process = subprocess.Popen(
        command,
        stdout=(out_dir / "qemu.stdout").open("wb"),
        stderr=(out_dir / "qemu.stderr").open("wb"),
    )
    qmp: QMP | None = None
    peer: socket.socket | None = None
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "m5stack-core2-native-hci-transport",
        "scope": "virtual-device transport-only",
        "status": "FAIL",
        "qemu": str(args.qemu),
        "checks": {},
    }
    try:
        qmp = QMP(qmp_path)
        deadline = time.monotonic() + 10
        while True:
            try:
                peer = socket.create_connection(
                    ("127.0.0.1", port),
                    timeout=0.2,
                )
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("chardev client did not connect")
                time.sleep(0.02)
        wait_value(qmp, "peer-opened", 1)
        peer.sendall(bytes.fromhex("040e0401030c00"))
        peer.sendall(bytes.fromhex("02010002"))
        peer.sendall(bytes.fromhex("00010203"))
        wait_value(qmp, "rx-packets", 2)
        wait_value(qmp, "rx-bytes", 15)
        wait_value(qmp, "rx-queue-depth", 2)
        result["checks"] = {
            "peer_opened": qmp.get("peer-opened") == 1,
            "event_and_fragmented_acl_packets": qmp.get("rx-packets") == 2,
            "rx_bytes": qmp.get("rx-bytes") == 15,
            "rx_queue_depth": qmp.get("rx-queue-depth") == 2,
            "no_malformed_packet": qmp.get("malformed-packets") == 0,
        }
        event = bytes.fromhex("040e0401030c00")
        for _ in range(31):
            peer.sendall(event)
        wait_value(qmp, "rx-queue-depth", 32)
        wait_value(qmp, "rx-packets", 32)
        wait_value(qmp, "dropped-packets", 1)
        result["checks"].update(
            {
                "bounded_queue_depth": qmp.get("rx-queue-depth") == 32,
                "accepted_packets_before_overflow": (
                    qmp.get("rx-packets") == 32
                ),
                "overflow_packet_dropped": (
                    qmp.get("dropped-packets") == 1
                ),
                "queue_full_error": qmp.get("last-error") == 2,
            }
        )
        peer.close()
        peer = None
        wait_value(qmp, "peer-closed", 1)
        result["checks"]["peer_closed"] = True
        result["status"] = "PASS"
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        if peer is not None:
            peer.close()
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
