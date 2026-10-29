#!/usr/bin/env python3
"""Run a two-guest ESP-NOW exchange through the controller bridge."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import select
import socket
import sys
import threading
import time
from types import SimpleNamespace
import zipfile


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_guest  # noqa: E402


PAIR_SOURCE = r'''
import M5
import espnow
import json
import network
import time

ROLE = __ROLE__
PEER_MAC = b"\x02\x00\x00\x00\x00\x43"
PEER_PAYLOAD = ("PAIR_PLAINTEXT:" + ROLE).encode()
EXPECTED_PAYLOAD = ("PAIR_PLAINTEXT:" + ("B" if ROLE == "A" else "A")).encode()
PMK = __PMK__
LMK = __LMK__


def emit(kind, **values):
    values["kind"] = kind
    print("ESPNOW_PAIR_" + json.dumps(values, separators=(",", ":")))


def receive(node, timeout_ms):
    slot = [None, bytearray(250)]
    count = node.recvinto(slot, timeout_ms)
    if not count:
        return None, b""
    return bytes(slot[0]), bytes(slot[1][:count])


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    deadline = time.ticks_add(time.ticks_ms(), 5000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        if any(row[0] == b"myssid" for row in wlan.scan()):
            break
        time.sleep_ms(100)
    else:
        raise RuntimeError("fixture AP absent")
    wlan.connect("myssid")
    deadline = time.ticks_add(time.ticks_ms(), 40000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        if wlan.isconnected() and wlan.status() == 1010:
            return wlan
        time.sleep_ms(100)
    raise RuntimeError("guest DHCP timed out")


M5.begin()
connect_wifi()
node = espnow.ESPNow()
node.active(True)
node.config(rxbuf=4096, timeout_ms=100)
if __ENCRYPT__:
    node.set_pmk(PMK)
    node.add_peer(PEER_MAC, lmk=LMK, channel=0, ifidx=0, encrypt=True)
else:
    node.add_peer(PEER_MAC, channel=0, ifidx=0, encrypt=False)
peer_count = list(node.peer_count())
expected_peer_count = [1, 1] if __ENCRYPT__ else [1, 0]
if peer_count != expected_peer_count:
    emit("RESULT", role=ROLE, api="external_peer_registration", status="FAIL",
         peer_count=peer_count, encryption=__ENCRYPT__)
    raise RuntimeError("external peer registration failed")
emit("RESULT", role=ROLE, api="external_peer_registration", status="PASS",
     peer_count=peer_count, encryption=__ENCRYPT__)
emit("READY", role=ROLE)

received = False
rx_packets = 0
source_matches = 0
payload_matches = 0
last_payload_len = 0
deadline = time.ticks_add(time.ticks_ms(), 12000)
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    try:
        node.send(PEER_MAC, PEER_PAYLOAD, False)
    except OSError:
        pass
    for _ in range(3):
        source, payload = receive(node, 100)
        if source is None:
            continue
        rx_packets += 1
        source_matches += int(source == PEER_MAC)
        payload_matches += int(payload == EXPECTED_PAYLOAD)
        last_payload_len = len(payload)
        if source == PEER_MAC and payload == EXPECTED_PAYLOAD:
            received = True

emit(
    "RESULT",
    role=ROLE,
    api="external_payload",
    status="PASS" if received else "EXPECTED_DROP",
    received=received,
    rx_packets=rx_packets,
    source_matches=source_matches,
    payload_matches=payload_matches,
    last_payload_len=last_payload_len,
    encryption=__ENCRYPT__,
    expected_payload_sha256=__EXPECTED_HASH__,
)
emit("DONE", role=ROLE)
print("ESPNOW_PAIR_DONE " + ROLE)
node.active(False)
'''


def save(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def free_udp_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
    finally:
        probe.close()


def port_pair() -> tuple[int, int]:
    first = free_udp_port()
    while True:
        second = free_udp_port()
        if second != first:
            return first, second


def distinct_ports(count: int) -> tuple[int, ...]:
    ports: list[int] = []
    while len(ports) < count:
        candidate = free_udp_port()
        if candidate not in ports:
            ports.append(candidate)
    return tuple(ports)


class ReplayProxy:
    """Forward one ESP-NOW frame twice to exercise receiver PN rejection."""

    def __init__(
        self,
        *,
        left_service_port: int,
        right_service_port: int,
        left_proxy_port: int,
        right_proxy_port: int,
    ) -> None:
        address = "127.0.0.1"
        self._left_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._right_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._left_socket.bind((address, left_proxy_port))
        self._right_socket.bind((address, right_proxy_port))
        self._left_service = (address, left_service_port)
        self._right_service = (address, right_service_port)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._forwarded = {"left_to_right": 0, "right_to_left": 0}
        self._replay_sent = False
        self._errors: list[str] = []

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._left_socket.close()
        self._right_socket.close()

    def summary(self) -> dict:
        return {
            "forwarded": dict(self._forwarded),
            "replay_sent": self._replay_sent,
            "errors": list(self._errors),
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                readable, _, _ = select.select(
                    [self._left_socket, self._right_socket],
                    [],
                    [],
                    0.1,
                )
            except (OSError, ValueError) as error:
                self._errors.append(type(error).__name__)
                return
            for source in readable:
                if self._stop.is_set():
                    return
                try:
                    data, _ = source.recvfrom(65535)
                except OSError as error:
                    self._errors.append(type(error).__name__)
                    return
                if source is self._left_socket:
                    self._forwarded["left_to_right"] += 1
                    self._right_socket.sendto(data, self._right_service)
                    if (
                        not self._replay_sent
                        and self._forwarded["left_to_right"] >= 2
                        and self._forwarded["right_to_left"] > 0
                    ):
                        time.sleep(0.05)
                        self._right_socket.sendto(data, self._right_service)
                        self._replay_sent = True
                else:
                    self._forwarded["right_to_left"] += 1
                    self._left_socket.sendto(data, self._left_service)


def wifi_profile(device: str) -> str:
    return {
        "sticks3": "uiflow2-sticks3-wifi",
        "stopwatch": "generic-observe",
        "core2": "core2-openmac",
    }.get(device, "generic-observe")


def parse_pair_records(serial: str) -> list[dict]:
    records = []
    for line in serial.splitlines():
        if not line.startswith("ESPNOW_PAIR_"):
            continue
        try:
            records.append(json.loads(line.removeprefix("ESPNOW_PAIR_")))
        except (TypeError, ValueError):
            continue
    return records


def trace_summary(evidence: Path) -> dict:
    if not evidence.is_file():
        return {"tx": 0, "rx": 0, "replay_drops": 0, "sha256": None}
    with zipfile.ZipFile(evidence) as archive:
        try:
            raw = archive.read("qemu.stderr")
        except KeyError:
            raw = b""
    text = raw.decode(errors="replace")
    return {
        "tx": text.count("[espnow-peer] TX "),
        "rx": text.count("[espnow-peer] RX "),
        "replay_drops": text.count(
            "[espnow-peer] RX drop: CCMP PN replay"
        ),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def run_one(
    *,
    api: str,
    token_file: Path,
    device: str,
    role: str,
    local_port: int,
    remote_port: int,
    output: Path,
    encrypt: bool,
    pmk: bytes,
    lmk: bytes,
) -> dict:
    source = (
        PAIR_SOURCE.replace("__ROLE__", repr(role))
        .replace("__PMK__", repr(pmk))
        .replace("__LMK__", repr(lmk))
        .replace("__ENCRYPT__", repr(encrypt))
        .replace(
            "__EXPECTED_HASH__",
            repr(
                hashlib.sha256(
                    ("PAIR_PLAINTEXT:" + ("B" if role == "A" else "A")).encode()
                ).hexdigest()
            ),
        )
    )
    source_path = output.parent / ("pair-" + role + ".py")
    source_path.write_text(source, encoding="utf-8")
    runtime_env = {
        "M5SW_ESPNOW_PEER_LOCAL_PORT": str(local_port),
        "M5SW_ESPNOW_PEER_REMOTE_PORT": str(remote_port),
        "M5SW_ESPNOW_PEER_TRACE": "1",
    }
    if encrypt:
        runtime_env.update({
            "M5SW_ESPNOW_PEER_PMK": pmk.hex(),
            "M5SW_ESPNOW_PEER_LMK": lmk.hex(),
        })
    args = SimpleNamespace(
        api=api,
        token_file=token_file,
        device=device,
        runtime="qemu-wifi",
        timeout=120,
        source=source_path,
        out_dir=output,
        done_marker="ESPNOW_PAIR_DONE " + role,
        network={
            "profile": wifi_profile(device),
            "http_fixture": False,
            "capture_pcap": False,
            "attempts": 1,
            "expected_markers": [],
        },
        runtime_env=runtime_env,
        prepare_timeout=600,
        ready_timeout=180,
        keep_session=False,
        program_transport=None,
        uart_repl_bootstrap=None,
        units=None,
        base_image=None,
        expected_base_sha256=None,
        firmware_lane=None,
        append_code=None,
    )
    code = run_guest.run(args)
    report_path = output / "report.json"
    report = (
        json.loads(report_path.read_text(encoding="utf-8"))
        if report_path.is_file()
        else {}
    )
    serial_path = output / "serial.txt"
    serial = (
        serial_path.read_text(errors="replace") if serial_path.is_file() else ""
    )
    records = parse_pair_records(serial)
    return {
        "role": role,
        "device": device,
        "returncode": code,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "session_id": report.get("session_id"),
        "firmware_sha256": report.get("firmware_sha256"),
        "runtime_binary_sha256": report.get("runtime_binary_sha256"),
        "evidence_sha256": report.get("evidence_sha256"),
        "cleanup": report.get("cleanup"),
        "records": records,
        "trace": trace_summary(output / "evidence.zip"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument(
        "--scenario",
        choices=(
            "plaintext",
            "encrypted",
            "wrong-lmk",
            "wrong-pmk",
            "replay",
        ),
        required=True,
    )
    parser.add_argument("--left-device", default="stopwatch")
    parser.add_argument("--right-device", default="sticks3")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    encrypt = args.scenario != "plaintext"
    keys = {
        "stopwatch": (
            b"0123456789abcdef",
            b"fedcba9876543210",
        ),
        "sticks3": (
            b"0123456789abcdef",
            b"fedcba9876543210",
        ),
        "core2": (
            b"0123456789abcdef",
            b"fedcba9876543210",
        ),
    }
    if args.scenario == "wrong-lmk":
        _, right_lmk = keys[args.right_device]
        keys[args.right_device] = (
            b"0123456789abcdef",
            bytes(value ^ 0xff for value in right_lmk),
        )
    elif args.scenario == "wrong-pmk":
        right_pmk, right_lmk = keys[args.right_device]
        keys[args.right_device] = (
            bytes(value ^ 0xff for value in right_pmk),
            right_lmk,
        )
    left_pmk, left_lmk = keys[args.left_device]
    right_pmk, right_lmk = keys[args.right_device]
    replay_proxy = None
    left_proxy_port = None
    right_proxy_port = None
    if args.scenario == "replay":
        (
            left_port,
            right_port,
            left_proxy_port,
            right_proxy_port,
        ) = distinct_ports(4)
        replay_proxy = ReplayProxy(
            left_service_port=left_port,
            right_service_port=right_port,
            left_proxy_port=left_proxy_port,
            right_proxy_port=right_proxy_port,
        )
    else:
        left_port, right_port = port_pair()
    left_remote_port = left_proxy_port or right_port
    right_remote_port = right_proxy_port or left_port
    jobs = (
        dict(
            api=args.api,
            token_file=args.token_file,
            device=args.left_device,
            role="A",
            local_port=left_port,
            remote_port=left_remote_port,
            output=output / "role-a",
            encrypt=encrypt,
            pmk=left_pmk,
            lmk=left_lmk,
        ),
        dict(
            api=args.api,
            token_file=args.token_file,
            device=args.right_device,
            role="B",
            local_port=right_port,
            remote_port=right_remote_port,
            output=output / "role-b",
            encrypt=encrypt,
            pmk=right_pmk,
            lmk=right_lmk,
        ),
    )
    if replay_proxy:
        replay_proxy.start()
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run_one, **job) for job in jobs]
            results = [future.result() for future in futures]
    finally:
        if replay_proxy:
            replay_proxy.close()
    proxy_stats = replay_proxy.summary() if replay_proxy else None

    delivery_results = [
        row
        for result in results
        for row in result["records"]
        if row.get("kind") == "RESULT"
        and row.get("api") == "external_payload"
    ]
    cleanup_ok = all(
        result["cleanup"]
        and result["cleanup"].get("terminal_state") == "stopped"
        and result["cleanup"].get("runtime_pid_gone") is True
        for result in results
    )
    bridge_traffic_ok = all(
        result["trace"]["tx"] > 0 and result["trace"]["rx"] > 0
        for result in results
    )
    registration_results = [
        row
        for result in results
        for row in result["records"]
        if row.get("kind") == "RESULT"
        and row.get("api") == "external_peer_registration"
    ]
    expected_drop = args.scenario == "wrong-lmk"
    delivery_ok = (
        all(
            row.get("status") == "EXPECTED_DROP"
            and row.get("received") is False
            and row.get("rx_packets") == 0
            for row in delivery_results
        )
        if expected_drop
        else all(row.get("status") == "PASS" for row in delivery_results)
    )
    replay_ok = (
        args.scenario != "replay"
        or (
            proxy_stats is not None
            and proxy_stats["replay_sent"] is True
            and not proxy_stats["errors"]
            and any(
                result["trace"]["replay_drops"] > 0
                for result in results
            )
        )
    )
    status_ok = (
        len(registration_results) == 2
        and all(row.get("status") == "PASS" for row in registration_results)
        and len(delivery_results) == 2
        and delivery_ok
        and all(row.get("encryption") is encrypt for row in delivery_results)
        and all(result["returncode"] == 0 for result in results)
        and cleanup_ok
        and bridge_traffic_ok
        and replay_ok
    )
    summary = {
        "schema_version": 1,
        "validation": "virtual-device validation",
        "hardware_validation": "NOT RUN",
        "scenario": args.scenario,
        "encryption": encrypt,
        "status": "PASS" if status_ok else "FAIL",
        "bridge": {
            "transport": (
                "IPv4 loopback UDP replay proxy"
                if args.scenario == "replay"
                else "IPv4 loopback UDP action-frame bridge"
            ),
            "left_local_port": left_port,
            "right_local_port": right_port,
            "bridge_traffic_ok": bridge_traffic_ok,
            **({"replay_proxy": proxy_stats} if proxy_stats else {}),
        },
        "results": results,
    }
    save(output / "summary.json", summary)
    print(json.dumps({
        "status": summary["status"],
        "scenario": args.scenario,
        "results": [
            {
                "role": row["role"],
                "device": row["device"],
                "session_id": row["session_id"],
                "status": next(
                    (
                        record.get("status")
                        for record in row["records"]
                        if record.get("api") == "external_payload"
                    ),
                    None,
                ),
                "trace": row["trace"],
            }
            for row in results
        ],
        "summary": str(output / "summary.json"),
    }, indent=2))
    return 0 if status_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
