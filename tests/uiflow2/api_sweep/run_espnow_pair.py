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


LIFECYCLE_SOURCE = r'''
import M5
import espnow
import json
import network
import time

ROLE = __ROLE__
PEER_MAC = b"\x02\x00\x00\x00\x00\x43"
PMK = __PMK__
LMK = __LMK__


def emit(kind, **values):
    values["kind"] = kind
    print("ESPNOW_LIFECYCLE_" + json.dumps(values, separators=(",", ":")))


def receive(timeout_ms):
    slot = [None, bytearray(250)]
    count = node.recvinto(slot, timeout_ms)
    if not count:
        return None, b""
    return bytes(slot[0]), bytes(slot[1][:count])


def wait_for_marker(tag, expected, timeout_ms):
    own = tag + b":" + ROLE.encode()
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    matched_at = None
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        try:
            node.send(PEER_MAC, own, False)
        except OSError:
            time.sleep_ms(100)
            continue
        for _ in range(3):
            source, payload = receive(100)
            if source == PEER_MAC and payload == expected:
                if matched_at is None:
                    matched_at = time.ticks_ms()
        if (
            matched_at is not None
            and time.ticks_diff(time.ticks_ms(), matched_at) >= 1500
        ):
            return True
    return matched_at is not None


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
node.set_pmk(PMK)
node.add_peer(PEER_MAC, lmk=LMK, channel=0, ifidx=0, encrypt=True)
initial_count = list(node.peer_count())
emit(
    "RESULT",
    role=ROLE,
    api="external_peer_registration",
    status="PASS" if initial_count == [1, 1] else "FAIL",
    peer_count=initial_count,
    encryption=True,
)
emit("READY", role=ROLE)

other_role = "B" if ROLE == "A" else "A"
pre_synced = wait_for_marker(b"PRE", b"PRE:" + other_role.encode(), 12000)

node.del_peer(PEER_MAC)
deleted_count = list(node.peer_count())
get_peer_not_found = False
try:
    node.get_peer(PEER_MAC)
except OSError:
    get_peer_not_found = True
send_rejected = False
try:
    node.send(PEER_MAC, b"AFTER_DELETE", False)
except OSError:
    send_rejected = True

time.sleep_ms(600)
node.add_peer(PEER_MAC, lmk=LMK, channel=0, ifidx=0, encrypt=True)
readded_count = list(node.peer_count())
node.mod_peer(PEER_MAC, lmk=LMK, channel=0, ifidx=0, encrypt=True)
peer_info = node.get_peer(PEER_MAC)
modified = (
    bytes(peer_info[0]) == PEER_MAC
    and bool(peer_info[4])
)
post_resumed = wait_for_marker(
    b"POST", b"POST:" + other_role.encode(), 12000
)

passed = (
    initial_count == [1, 1]
    and pre_synced
    and deleted_count == [0, 0]
    and get_peer_not_found
    and send_rejected
    and readded_count == [1, 1]
    and modified
    and post_resumed
)
emit(
    "RESULT",
    role=ROLE,
    api="external_peer_lifecycle",
    status="PASS" if passed else "FAIL",
    initial_count=initial_count,
    pre_synced=pre_synced,
    deleted_count=deleted_count,
    get_peer_not_found=get_peer_not_found,
    send_rejected=send_rejected,
    readded_count=readded_count,
    modified=modified,
    post_resumed=post_resumed,
)
emit("DONE", role=ROLE)
print("ESPNOW_LIFECYCLE_DONE " + ROLE)
node.active(False)
'''


M5ESPNOW_LIFECYCLE_SOURCE = r'''
import M5
from m5espnow import M5ESPNow
import json
import network
import time

ROLE = __ROLE__
PEER_MAC = b"\x02\x00\x00\x00\x00\x43"
PEER_MAC_HEX = "020000000043"
PMK = __PMK__
LMK = __LMK__


def emit(kind, **values):
    values["kind"] = kind
    print("ESPNOW_M5_LIFECYCLE_" + json.dumps(values, separators=(",", ":")))


def receive(timeout_ms):
    mac, payload = node.recv_data(timeout_ms)
    if mac is None:
        return None, b""
    return bytes(mac), bytes(payload)


def wait_for_marker(tag, expected, timeout_ms):
    own = tag + b":" + ROLE.encode()
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    matched_at = None
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        node.send_data(1, own)
        for _ in range(3):
            source, payload = receive(100)
            if source == PEER_MAC and payload == expected:
                if matched_at is None:
                    matched_at = time.ticks_ms()
        if (
            matched_at is not None
            and time.ticks_diff(time.ticks_ms(), matched_at) >= 1500
        ):
            return True
    return matched_at is not None


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
node = M5ESPNow(0)
node.set_pmk_encrypt(PMK)
node.set_add_peer(PEER_MAC_HEX, 1, 0, True, LMK)
initial_count = list(node.peer_count())
initial_peers = list(node.get_peer_list(1))
registration_ok = (
    initial_count == [1, 1]
    and PEER_MAC_HEX.upper() in [value.upper() for value in initial_peers]
)
emit(
    "RESULT",
    role=ROLE,
    api="external_peer_registration",
    status="PASS" if registration_ok else "FAIL",
    peer_count=initial_count,
    encryption=True,
    wrapper="m5espnow",
)
emit("READY", role=ROLE)

other_role = "B" if ROLE == "A" else "A"
pre_synced = wait_for_marker(b"PRE", b"PRE:" + other_role.encode(), 12000)

node.set_delete_peer(1)
deleted_count = list(node.peer_count())
deleted_peers = list(node.get_peer_list(1))
send_after_delete_noop = True
try:
    node.send_data(1, b"AFTER_DELETE")
except OSError:
    send_after_delete_noop = False

time.sleep_ms(600)
node.set_add_peer(PEER_MAC_HEX, 1, 0, True, LMK)
readded_count = list(node.peer_count())
readded_peers = list(node.get_peer_list(1))
peer_list_restored = (
    readded_count == [1, 1]
    and PEER_MAC_HEX.upper() in [value.upper() for value in readded_peers]
)
post_resumed = wait_for_marker(
    b"POST", b"POST:" + other_role.encode(), 12000
)

passed = (
    registration_ok
    and pre_synced
    and deleted_count == [0, 0]
    and deleted_peers == []
    and send_after_delete_noop
    and peer_list_restored
    and post_resumed
)
emit(
    "RESULT",
    role=ROLE,
    api="external_peer_lifecycle_m5espnow",
    status="PASS" if passed else "FAIL",
    initial_count=initial_count,
    pre_synced=pre_synced,
    deleted_count=deleted_count,
    deleted_peer_list_empty=deleted_peers == [],
    send_after_delete_noop=send_after_delete_noop,
    readded_count=readded_count,
    peer_list_restored=peer_list_restored,
    post_resumed=post_resumed,
)
emit("DONE", role=ROLE)
print("ESPNOW_M5_LIFECYCLE_DONE " + ROLE)
node.deinit()
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


def parse_lifecycle_records(serial: str) -> list[dict]:
    records = []
    for line in serial.splitlines():
        if not line.startswith("ESPNOW_LIFECYCLE_"):
            continue
        try:
            records.append(
                json.loads(line.removeprefix("ESPNOW_LIFECYCLE_"))
            )
        except (TypeError, ValueError):
            continue
    return records


def parse_m5espnow_lifecycle_records(serial: str) -> list[dict]:
    records = []
    for line in serial.splitlines():
        if not line.startswith("ESPNOW_M5_LIFECYCLE_"):
            continue
        try:
            records.append(
                json.loads(line.removeprefix("ESPNOW_M5_LIFECYCLE_"))
            )
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
    scenario: str,
    encrypt: bool,
    pmk: bytes,
    lmk: bytes,
) -> dict:
    if scenario == "lifecycle":
        source_template = LIFECYCLE_SOURCE
        done_marker = "ESPNOW_LIFECYCLE_DONE " + role
    elif scenario == "lifecycle-m5espnow":
        source_template = M5ESPNOW_LIFECYCLE_SOURCE
        done_marker = "ESPNOW_M5_LIFECYCLE_DONE " + role
    else:
        source_template = PAIR_SOURCE
        done_marker = "ESPNOW_PAIR_DONE " + role
    source = (
        source_template.replace("__ROLE__", repr(role))
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
        done_marker=done_marker,
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
    if scenario == "lifecycle":
        records = parse_lifecycle_records(serial)
    elif scenario == "lifecycle-m5espnow":
        records = parse_m5espnow_lifecycle_records(serial)
    else:
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
            "lifecycle",
            "lifecycle-m5espnow",
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
            scenario=args.scenario,
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
            scenario=args.scenario,
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
    lifecycle_results = [
        row
        for result in results
        for row in result["records"]
        if row.get("kind") == "RESULT"
        and row.get("api") == "external_peer_lifecycle"
    ]
    m5espnow_lifecycle_results = [
        row
        for result in results
        for row in result["records"]
        if row.get("kind") == "RESULT"
        and row.get("api") == "external_peer_lifecycle_m5espnow"
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
    lifecycle_ok = (
        args.scenario != "lifecycle"
        or (
            len(lifecycle_results) == 2
            and all(
                row.get("status") == "PASS"
                and row.get("initial_count") == [1, 1]
                and row.get("pre_synced") is True
                and row.get("deleted_count") == [0, 0]
                and row.get("get_peer_not_found") is True
                and row.get("send_rejected") is True
                and row.get("readded_count") == [1, 1]
                and row.get("modified") is True
                and row.get("post_resumed") is True
                for row in lifecycle_results
            )
        )
    )
    m5espnow_lifecycle_ok = (
        args.scenario != "lifecycle-m5espnow"
        or (
            len(m5espnow_lifecycle_results) == 2
            and all(
                row.get("status") == "PASS"
                and row.get("initial_count") == [1, 1]
                and row.get("pre_synced") is True
                and row.get("deleted_count") == [0, 0]
                and row.get("deleted_peer_list_empty") is True
                and row.get("send_after_delete_noop") is True
                and row.get("readded_count") == [1, 1]
                and row.get("peer_list_restored") is True
                and row.get("post_resumed") is True
                for row in m5espnow_lifecycle_results
            )
        )
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
        and (
            (
                args.scenario == "lifecycle"
                and lifecycle_ok
            )
            or (
                args.scenario == "lifecycle-m5espnow"
                and m5espnow_lifecycle_ok
            )
            or (
                args.scenario not in {"lifecycle", "lifecycle-m5espnow"}
                and len(delivery_results) == 2
                and delivery_ok
                and all(
                    row.get("encryption") is encrypt
                    for row in delivery_results
                )
            )
        )
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
                        if record.get("api")
                        == (
                            "external_peer_lifecycle"
                            if args.scenario == "lifecycle"
                            else (
                                "external_peer_lifecycle_m5espnow"
                                if args.scenario == "lifecycle-m5espnow"
                                else "external_payload"
                            )
                        )
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
