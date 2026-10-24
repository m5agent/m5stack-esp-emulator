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
LIVE_COUNTER_NAMES = (
    "h2c-packets",
    "hli-posts",
    "hli-consumed",
    "hli-event-buffers",
    "hli-acl-buffers",
    "hli-c2h-events",
    "hli-c2h-acls",
    "api-h2c-packets",
    "api-h2c-errors",
    "hli-errors",
    "hli-queue-depth",
    "tx-queue-depth",
    "tx-queue-offset",
    "last-tx-errno",
    "tx-retry-count",
    "tx-zero-writes",
    "trace-acl-process",
    "trace-l2cap-rx",
    "trace-l2cap-incomplete",
    "trace-l2cap-chan-found",
    "trace-l2cap-mtu-reject",
    "trace-l2cap-rxfn",
    "trace-att-rx",
    "trace-att-write",
    "trace-att-write-no-rsp",
    "trace-att-find-handle",
    "trace-att-write-handle",
    "trace-python-gatts-on-write",
    "trace-python-irq",
    "trace-python-notify",
    "trace-nimble-gatts-notify",
    "hli-last-descriptor-address",
    "hli-last-descriptor-argument",
    "hli-last-descriptor-callback",
    "meta-queue-depth",
)
FINAL_COUNTER_NAMES = (
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
    *LIVE_COUNTER_NAMES,
    "hli-descriptor-pool-address",
    "malformed-packets",
    "dropped-packets",
    "last-error",
)


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
            line = self.stream.readline()
            if not line:
                raise RuntimeError("QMP connection closed")
            try:
                response = json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeError(
                    f"QMP returned invalid JSON: {line[:200]!r}"
                ) from error
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
    environment["BLE_TRACE_TIMESTAMPS"] = "1"
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


def read_qom_counters(
    qmp: QMP,
    names: tuple[str, ...],
) -> dict[str, Any]:
    counters: dict[str, Any] = {}
    for name in names:
        try:
            counters[name] = qmp.get(name)
        except (OSError, RuntimeError) as error:
            counters[name] = f"unavailable: {error}"
    return counters


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--name-prefix", default="M5-CORE2-HCI")
    parser.add_argument("--payload", default="M5_CORE2_PROBE")
    parser.add_argument(
        "--hli-c2h",
        action="store_true",
        help=(
            "experimental: deliver events/ACL through firmware HLI using "
            "QEMU properties not present in the committed patch series"
        ),
    )
    args = parser.parse_args()

    for label, path in (
        ("image", args.image),
        ("QEMU", args.qemu),
        ("ELF", args.elf),
    ):
        if not path.is_file():
            parser.error(f"{label} does not exist: {path}")

    sys.path.insert(0, str(ROOT / "platform/tools"))
    from xtensa_elf_symbols import (
        core2_native_hci_device_args,
        resolve_symbols,
    )

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
        "hli_c2h": args.hli_c2h,
        "att_pdu_bytes": len(args.payload.encode("utf-8")) + 3,
        "default_att_mtu": 23,
    }
    if args.hli_c2h:
        result["experimental_runtime_requirements"] = [
            "local QEMU HLI/API-boundary hooks",
            "matching stock firmware and ELF",
            "external Bumble controller/peer",
        ]
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

        if args.hli_c2h:
            hci_device = core2_native_hci_device_args(args.elf)
        else:
            hci_device = (
                "esp32-native-hci,chardev=hci,"
                f"env-pointer-address=0x{symbols['vhci_env_p'].value:08x},"
                f"c2h-allocator-address=0x{symbols['malloc'].value:08x},"
                "c2h-scratch-size=2048"
            )
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
            hci_device,
            "-qmp",
            f"unix:{qmp_path},server=on,wait=off",
        ]
        qemu_environment = os.environ.copy()
        if args.hli_c2h:
            qemu_environment["M5_NATIVE_HCI_TRACE"] = "1"
        qemu_process = subprocess.Popen(
            command,
            env=qemu_environment,
            stdout=(out_dir / "qemu.stdout").open("wb"),
            stderr=(out_dir / "qemu.stderr").open("wb"),
        )
        result["hci_device"] = hci_device
        qmp = QMP(qmp_path, min(args.timeout, 30))
        deadline = time.monotonic() + args.timeout
        ble_exited_at: float | None = None
        last_counter_poll = 0.0
        live_counters: dict[str, Any] = {}
        ble_failure_counters: dict[str, Any] = {}
        ble_failure_recorded = False
        while time.monotonic() < deadline:
            serial_text = read_text(serial)
            ble_text = read_text(ble_log)
            if "BLE_BUMBLE_FAIL" in ble_text and not ble_failure_recorded:
                ble_failure_recorded = True
                ble_failure_counters = read_qom_counters(
                    qmp,
                    LIVE_COUNTER_NAMES,
                )
            if (
                qmp is not None
                and time.monotonic() - last_counter_poll >= 0.2
            ):
                last_counter_poll = time.monotonic()
                live_counters.update(
                    read_qom_counters(qmp, LIVE_COUNTER_NAMES)
                )
            if (
                "BLE_BUMBLE_PASS" in ble_text
                and "CORE2_HCI_BLE_ACK_SENT" in serial_text
            ):
                try:
                    ble_process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    pass
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
        counters: dict[str, Any] = {}
        if qmp is not None:
            counters = read_qom_counters(qmp, FINAL_COUNTER_NAMES)
        result["counters"] = counters
        result["live_counters"] = live_counters
        if "BLE_BUMBLE_PASS" in ble_text:
            result["post_sequence_teardown"] = {
                "api_h2c_errors": counters.get("api-h2c-errors"),
                "last_error": counters.get("last-error"),
                "note": (
                    "Errors observed after BLE_BUMBLE_PASS may be caused by "
                    "closing the HCI peer and are not sequence gates."
                ),
            }
        if args.hli_c2h:
            trace_lines = [
                line
                for line in read_text(out_dir / "qemu.stderr").splitlines()
                if "esp32-native-hci-trace" in line
            ]
            result["guest_trace_events"] = trace_lines[-256:]
        if ble_failure_counters:
            result["ble_failure_counters"] = ble_failure_counters
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
            "payload_fits_default_att_mtu": (
                result["att_pdu_bytes"] <= result["default_att_mtu"]
            ),
            "no_callback_errors": counters.get("c2h-errors") == 0,
            "no_malformed_packets": counters.get("malformed-packets") == 0,
            "no_dropped_packets": counters.get("dropped-packets") == 0,
        }
        if args.hli_c2h:
            def positive(name: str) -> bool:
                value = counters.get(name)
                return isinstance(value, (int, float)) and value > 0

            def zero(name: str) -> bool:
                return counters.get(name) == 0

            result["checks"].update(
                {
                    "hli_event_delivered": positive("hli-c2h-events"),
                    "hli_acl_delivered": positive("hli-c2h-acls"),
                    "hli_no_errors": zero("hli-errors"),
                    "hli_queue_empty": zero("hli-queue-depth"),
                    "hli_meta_queue_empty": zero("meta-queue-depth"),
                    "api_h2c_bypass_used": positive("api-h2c-packets"),
                    "api_h2c_no_errors_before_peer_failure": (
                        not ble_failure_counters
                        or ble_failure_counters.get("api-h2c-errors") == 0
                    ),
                }
            )
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
        detail = str(error)
        qemu_stderr = read_text(out_dir / "qemu.stderr").strip()
        if qemu_process is not None and qemu_process.poll() is not None:
            if qemu_stderr:
                detail += (
                    f"; QEMU stderr: {qemu_stderr.splitlines()[-1][-400:]}"
                )
        result["error"] = detail
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
