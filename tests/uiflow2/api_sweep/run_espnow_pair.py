#!/usr/bin/env python3
"""Run a two-guest ESP-NOW exchange through the controller bridge."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
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


ESPNOW_PEER_WIRE_HEADER_SIZE = 8


PAIR_SOURCE = r'''
import M5
import espnow
import json
import network
import time

ROLE = __ROLE__
PEER_MAC = b"\x02\x00\x00\x00\x00\x43"
PEER_CHANNEL = __PEER_CHANNEL__
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
wlan = connect_wifi()
if PEER_CHANNEL != 1:
    wlan.disconnect()
    wlan.active(False)
    wlan.active(True)
    wlan.config(channel=PEER_CHANNEL)
node = espnow.ESPNow()
node.active(True)
node.config(rxbuf=4096, timeout_ms=100)
if __ENCRYPT__:
    node.set_pmk(PMK)
    node.add_peer(
        PEER_MAC, lmk=LMK, channel=PEER_CHANNEL, ifidx=0, encrypt=True
    )
else:
    node.add_peer(PEER_MAC, channel=PEER_CHANNEL, ifidx=0, encrypt=False)
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
tx_attempts = 0
tx_errors = 0
source_matches = 0
payload_matches = 0
last_payload_len = 0
deadline = time.ticks_add(time.ticks_ms(), 12000)
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    try:
        node.send(PEER_MAC, PEER_PAYLOAD, False)
        tx_attempts += 1
    except OSError:
        tx_errors += 1
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
    tx_attempts=tx_attempts,
    tx_errors=tx_errors,
    peer_channel=PEER_CHANNEL,
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


SOAK_SOURCE = r'''
import M5
import espnow
import json
import network
import time

ROLE = __ROLE__
PEER_ROLE = "B" if ROLE == "A" else "A"
PEER_MAC = b"\x02\x00\x00\x00\x00\x43"
EXPECTED_PREFIX = ("SOAK:" + PEER_ROLE + ":").encode()
SOAK_SECONDS = __SOAK_SECONDS__
PMK = __PMK__
LMK = __LMK__


def emit(kind, **values):
    values["kind"] = kind
    print("ESPNOW_SOAK_" + json.dumps(values, separators=(",", ":")))


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
node.set_pmk(PMK)
node.add_peer(PEER_MAC, lmk=LMK, channel=1, ifidx=0, encrypt=True)
peer_count = list(node.peer_count())
registered = peer_count == [1, 1]
emit(
    "RESULT",
    role=ROLE,
    api="external_peer_registration",
    status="PASS" if registered else "FAIL",
    peer_count=peer_count,
    encryption=True,
)
if not registered:
    raise RuntimeError("soak peer registration failed")
emit("READY", role=ROLE)

tx_count = 0
rx_count = 0
payload_matches = 0
duplicate_payloads = 0
unexpected_sources = 0
tx_errors = 0
seen = {}
sequence = 0
deadline = time.ticks_add(time.ticks_ms(), SOAK_SECONDS * 1000)
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    try:
        node.send(
            PEER_MAC,
            ("SOAK:" + ROLE + ":" + str(sequence)).encode(),
            False,
        )
        tx_count += 1
    except OSError:
        tx_errors += 1
    sequence += 1
    for _ in range(4):
        source, payload = receive(node, 100)
        if source is None:
            break
        rx_count += 1
        if source != PEER_MAC:
            unexpected_sources += 1
            continue
        if not payload.startswith(EXPECTED_PREFIX):
            continue
        try:
            received_sequence = int(payload[len(EXPECTED_PREFIX):])
        except ValueError:
            continue
        if received_sequence in seen:
            duplicate_payloads += 1
        else:
            seen[received_sequence] = 1
            payload_matches += 1
    time.sleep_ms(10)

minimum = SOAK_SECONDS * 2
passed = (
    tx_count >= minimum
    and payload_matches >= minimum
    and duplicate_payloads == 0
    and unexpected_sources == 0
    and tx_errors == 0
)
emit(
    "RESULT",
    role=ROLE,
    api="external_soak",
    status="PASS" if passed else "FAIL",
    duration_seconds=SOAK_SECONDS,
    peer_count=peer_count,
    tx_count=tx_count,
    rx_count=rx_count,
    payload_matches=payload_matches,
    duplicate_payloads=duplicate_payloads,
    unexpected_sources=unexpected_sources,
    tx_errors=tx_errors,
)
emit("DONE", role=ROLE)
print("ESPNOW_SOAK_DONE " + ROLE)
node.active(False)
'''


GUEST_KEY_PN_REKEY_SOURCE = r'''
import M5
import espnow
import json
import network
import time

ROLE = __ROLE__
PEER_ROLE = "B" if ROLE == "A" else "A"
PEER_MAC = b"\x02\x00\x00\x00\x00\x43"
PMK = __PMK__
LMK = __LMK__
ROTATED_LMK = __ROTATED_LMK__


def emit(kind, **values):
    values["kind"] = kind
    print("ESPNOW_FABRIC_" + json.dumps(values, separators=(",", ":")))


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
node.set_pmk(PMK)
node.add_peer(PEER_MAC, lmk=LMK, channel=0, ifidx=0, encrypt=True)
peer_count = list(node.peer_count())
registered = peer_count == [1, 1]
emit(
    "RESULT",
    role=ROLE,
    api="fabric_pn_registration",
    status="PASS" if registered else "FAIL",
    peer_count=peer_count,
)
if not registered:
    raise RuntimeError("PN peer registration failed")

time.sleep_ms(3000)
barrier = False
deadline = time.ticks_add(time.ticks_ms(), 30000)
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    node.send(PEER_MAC, ("BARRIER:" + ROLE).encode(), False)
    for _ in range(5):
        source, payload = receive(node, 100)
        if source is None:
            break
        if source == PEER_MAC and payload == (
            "BARRIER:" + PEER_ROLE
        ).encode():
            barrier = True
            break
    if barrier:
        break
emit(
    "RESULT",
    role=ROLE,
    api="fabric_pn_barrier",
    status="PASS" if barrier else "FAIL",
)
if not barrier:
    raise RuntimeError("PN readiness barrier failed")

for _ in range(128):
    node.send(PEER_MAC, ("BURN:" + ROLE).encode(), False)
time.sleep_ms(1000)

rekey_ok = False
try:
    node.mod_peer(
        PEER_MAC,
        lmk=ROTATED_LMK,
        channel=0,
        ifidx=0,
        encrypt=True,
    )
    peer_info = node.get_peer(PEER_MAC)
    rekey_ok = (
        bytes(peer_info[0]) == PEER_MAC
        and bool(peer_info[4])
    )
except OSError:
    rekey_ok = False
emit(
    "RESULT",
    role=ROLE,
    api="fabric_pn_rekey",
    status="PASS" if rekey_ok else "FAIL",
)
if not rekey_ok:
    raise RuntimeError("PN rekey failed")

payload_matches = 0
expected = ("POST_FABRIC:" + PEER_ROLE + ":" + ROLE).encode()
deadline = time.ticks_add(time.ticks_ms(), 15000)
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    node.send(PEER_MAC, ("POST_READY:" + ROLE).encode(), False)
    node.send(
        PEER_MAC,
        ("POST_FABRIC:" + ROLE + ":" + PEER_ROLE).encode(),
        False,
    )
    for _ in range(3):
        source, payload = receive(node, 100)
        if source == PEER_MAC and payload == expected:
            payload_matches += 1
emit(
    "RESULT",
    role=ROLE,
    api="fabric_pn_post",
    status="PASS" if payload_matches else "FAIL",
    payload_matches={PEER_ROLE: payload_matches},
)
emit("DONE", role=ROLE)
print("ESPNOW_FABRIC_DONE " + ROLE)
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
ROTATED_LMK = __ROTATED_LMK__


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
node.mod_peer(PEER_MAC, lmk=ROTATED_LMK, channel=0, ifidx=0, encrypt=True)
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


THREE_PEER_SOURCE = r'''
import M5
import espnow
import json
import network
import time

ROLE = __ROLE__
PEER_MACS = __PEER_MACS__
PEER_LMKS = __PEER_LMKS__
PMK = __PMK__


def emit(kind, **values):
    values["kind"] = kind
    print("ESPNOW_FABRIC_" + json.dumps(values, separators=(",", ":")))


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
node.set_pmk(PMK)
for peer_role, peer_mac in PEER_MACS.items():
    node.add_peer(
        peer_mac,
        lmk=PEER_LMKS[peer_role],
        channel=0,
        ifidx=0,
        encrypt=True,
    )

peer_count = list(node.peer_count())
registered = (
    peer_count == [len(PEER_MACS), len(PEER_MACS)]
    and all(
        bytes(node.get_peer(peer_mac)[0]) == peer_mac
        and bool(node.get_peer(peer_mac)[4])
        for peer_mac in PEER_MACS.values()
    )
)
emit(
    "RESULT",
    role=ROLE,
    api="fabric_peer_registration",
    status="PASS" if registered else "FAIL",
    peer_count=peer_count,
    peer_roles=sorted(PEER_MACS),
)
if not registered:
    raise RuntimeError("fabric peer registration failed")
emit("READY", role=ROLE)

expected = {
    peer_role: ("FABRIC:" + peer_role + ":" + ROLE).encode()
    for peer_role in PEER_MACS
}
source_roles = {
    peer_mac: peer_role for peer_role, peer_mac in PEER_MACS.items()
}
ready_peers = set()
payload_matches = {peer_role: 0 for peer_role in PEER_MACS}
source_matches = {peer_role: 0 for peer_role in PEER_MACS}
last_payload_len = 0
deadline = time.ticks_add(time.ticks_ms(), 24000)

while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    for peer_role, peer_mac in PEER_MACS.items():
        node.send(peer_mac, ("READY:" + ROLE).encode(), False)
        node.send(
            peer_mac,
            ("FABRIC:" + ROLE + ":" + peer_role).encode(),
            False,
        )
    for _ in range(10):
        source, payload = receive(node, 100)
        if source is None:
            break
        peer_role = source_roles.get(source)
        if peer_role is None:
            continue
        source_matches[peer_role] += 1
        if payload.startswith(b"READY:"):
            ready_peers.add(peer_role)
        elif payload == expected[peer_role]:
            payload_matches[peer_role] += 1
            last_payload_len = len(payload)

ready_ok = len(ready_peers) == len(PEER_MACS)
emit(
    "RESULT",
    role=ROLE,
    api="fabric_ready",
    status="PASS" if ready_ok else "FAIL",
    ready_peers=sorted(ready_peers),
)
passed = all(payload_matches[peer_role] for peer_role in PEER_MACS)
emit(
    "RESULT",
    role=ROLE,
    api="fabric_payload",
    status="PASS" if passed else "FAIL",
    peer_roles=sorted(PEER_MACS),
    source_matches=source_matches,
    payload_matches=payload_matches,
    last_payload_len=last_payload_len,
)
emit("DONE", role=ROLE)
print("ESPNOW_FABRIC_DONE " + ROLE)
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


class ReorderProxy:
    """Swap two authenticated frames after both peer directions are active."""

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
        self._held: bytes | None = None
        self._reordered = False
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
            "reordered": self._reordered,
            "held_frame_released": self._held is None,
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
                    if (
                        not self._reordered
                        and self._forwarded["right_to_left"] > 0
                    ):
                        if self._held is None:
                            self._held = data
                            continue
                        self._right_socket.sendto(data, self._right_service)
                        time.sleep(0.05)
                        self._right_socket.sendto(
                            self._held, self._right_service
                        )
                        self._held = None
                        self._reordered = True
                    else:
                        self._right_socket.sendto(data, self._right_service)
                else:
                    self._forwarded["right_to_left"] += 1
                    self._left_socket.sendto(data, self._left_service)


class LossProxy:
    """Drop a bounded left-to-right burst and forward later retries."""

    def __init__(
        self,
        *,
        left_service_port: int,
        right_service_port: int,
        left_proxy_port: int,
        right_proxy_port: int,
        drop_count: int = 2,
    ) -> None:
        address = "127.0.0.1"
        self._left_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._right_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._left_socket.bind((address, left_proxy_port))
        self._right_socket.bind((address, right_proxy_port))
        self._left_service = (address, left_service_port)
        self._right_service = (address, right_service_port)
        self._drop_count = drop_count
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._received = {"left_to_right": 0, "right_to_left": 0}
        self._forwarded = {"left_to_right": 0, "right_to_left": 0}
        self._dropped = {"left_to_right": 0, "right_to_left": 0}
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
            "received": dict(self._received),
            "forwarded": dict(self._forwarded),
            "dropped": dict(self._dropped),
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
                    self._received["left_to_right"] += 1
                    if (
                        self._received["right_to_left"] > 0
                        and self._dropped["left_to_right"]
                        < self._drop_count
                    ):
                        self._dropped["left_to_right"] += 1
                        continue
                    self._forwarded["left_to_right"] += 1
                    self._right_socket.sendto(data, self._right_service)
                else:
                    self._received["right_to_left"] += 1
                    self._forwarded["right_to_left"] += 1
                    self._left_socket.sendto(data, self._left_service)


class PeerFabric:
    """Route real action frames between three controller endpoints."""

    def __init__(
        self,
        *,
        roles: dict[str, dict],
        broker_port: int,
        duplicate_once: bool,
    ) -> None:
        self._address = ("127.0.0.1", broker_port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(self._address)
        self._role_by_port = {
            role: row["local_port"] for role, row in roles.items()
        }
        self._port_to_role = {
            row["local_port"]: role for role, row in roles.items()
        }
        self._mac_by_role = {
            role: bytes(row["mac"]) for role, row in roles.items()
        }
        self._role_by_mac = {
            bytes(row["mac"]): role for role, row in roles.items()
        }
        self._forwarded = {
            role: {
                target: 0 for target in roles if target != role
            }
            for role in roles
        }
        self._seen: set[str] = set()
        self._duplicate_once = duplicate_once
        self._duplicate_sent = False
        self._errors: list[str] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._socket.close()

    def summary(self) -> dict:
        return {
            "forwarded": self._forwarded,
            "seen_roles": sorted(self._seen),
            "duplicate_sent": self._duplicate_sent,
            "errors": list(self._errors),
        }

    def _run(self) -> None:
        broadcast = b"\xff" * 6
        while not self._stop.is_set():
            try:
                readable, _, _ = select.select(
                    [self._socket], [], [], 0.1
                )
            except (OSError, ValueError) as error:
                self._errors.append(type(error).__name__)
                return
            if not readable:
                continue
            try:
                data, source = self._socket.recvfrom(65535)
            except OSError as error:
                self._errors.append(type(error).__name__)
                return
            source_role = self._port_to_role.get(source[1])
            if (
                source_role is None
                or len(data)
                < ESPNOW_PEER_WIRE_HEADER_SIZE + 24
            ):
                self._errors.append("invalid_source")
                continue
            self._seen.add(source_role)

            wire = bytearray(data)
            frame = wire[ESPNOW_PEER_WIRE_HEADER_SIZE:]
            receiver = bytes(frame[4:10])
            source_mac = self._mac_by_role[source_role]
            frame[10:16] = source_mac
            frame[16:22] = source_mac
            wire[
                ESPNOW_PEER_WIRE_HEADER_SIZE:
                ESPNOW_PEER_WIRE_HEADER_SIZE + 22
            ] = frame[:22]
            if receiver == broadcast:
                target_roles = [
                    role for role in self._role_by_port if role != source_role
                ]
            else:
                target_role = self._role_by_mac.get(receiver)
                target_roles = [target_role] if target_role else []
            if not target_roles:
                self._errors.append("unknown_destination")
                continue

            for target_role in target_roles:
                self._socket.sendto(
                    wire,
                    ("127.0.0.1", self._role_by_port[target_role]),
                )
                self._forwarded[source_role][target_role] += 1
                if (
                    self._duplicate_once
                    and not self._duplicate_sent
                    and source_role == "A"
                    and target_role == "B"
                    and len(self._seen) == len(self._role_by_port)
                ):
                    time.sleep(0.05)
                    self._socket.sendto(
                        wire,
                        ("127.0.0.1", self._role_by_port[target_role]),
                    )
                    self._duplicate_sent = True


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


def parse_soak_records(serial: str) -> list[dict]:
    records = []
    for line in serial.splitlines():
        if not line.startswith("ESPNOW_SOAK_"):
            continue
        try:
            records.append(json.loads(line.removeprefix("ESPNOW_SOAK_")))
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


def parse_fabric_records(serial: str) -> list[dict]:
    records = []
    for line in serial.splitlines():
        if not line.startswith("ESPNOW_FABRIC_"):
            continue
        try:
            records.append(
                json.loads(line.removeprefix("ESPNOW_FABRIC_"))
            )
        except (TypeError, ValueError):
            continue
    return records


def trace_summary(evidence: Path) -> dict:
    if not evidence.is_file():
        return {
            "tx": 0,
            "rx": 0,
            "replay_drops": 0,
            "guest_key_ready": 0,
            "guest_key_cleared": 0,
            "pn_exhaustions": 0,
            "channel_drops": 0,
            "tx_channel_rates": [],
            "delivered_channel_rates": [],
            "sha256": None,
        }
    with zipfile.ZipFile(evidence) as archive:
        try:
            raw = archive.read("qemu.stderr")
        except KeyError:
            raw = b""
    text = raw.decode(errors="replace")
    tx_channel_rates = sorted({
        (int(match.group(1)), int(match.group(2)))
        for match in re.finditer(
            r"\[espnow-peer\] TX .*?channel=(\d+) rate=(\d+)",
            text,
        )
    })
    delivered_channel_rates = sorted({
        (int(match.group(1)), int(match.group(2)))
        for match in re.finditer(
            r"\[espnow-peer\] delivered channel=(\d+) rate=(\d+)",
            text,
        )
    })
    return {
        "tx": text.count("[espnow-peer] TX "),
        "rx": text.count("[espnow-peer] RX "),
        "replay_drops": text.count(
            "[espnow-peer] RX drop: CCMP PN replay"
        ),
        "guest_key_ready": text.count(
            "[espnow-peer] guest-key state=ready"
        ),
        "guest_key_cleared": text.count(
            "[espnow-peer] guest-key state=cleared"
        ),
        "pn_exhaustions": text.count(
            "[espnow-peer] TX drop: CCMP PN exhausted"
        ),
        "channel_drops": text.count(
            "[espnow-peer] RX drop: channel mismatch"
        ),
        "tx_channel_rates": [
            {"channel": channel, "rate": rate}
            for channel, rate in tx_channel_rates
        ],
        "delivered_channel_rates": [
            {"channel": channel, "rate": rate}
            for channel, rate in delivered_channel_rates
        ],
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


FABRIC_SCENARIOS = frozenset({
    "fabric",
    "fabric-replay",
    "fabric-per-peer-key",
    "fabric-per-peer-key-negative",
})


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
    guest_key: bool,
    pmk: bytes,
    lmk: bytes,
    rotated_lmk: bytes,
    peer_macs: dict[str, bytes] | None = None,
    peer_lmks: dict[str, bytes] | None = None,
    public_mac: bytes | None = None,
    peer_channel: int = 1,
    tx_rate: int = 11,
    soak_seconds: int = 60,
) -> dict:
    if scenario == "soak":
        source_template = SOAK_SOURCE
        done_marker = "ESPNOW_SOAK_DONE " + role
    elif scenario in {
        "guest-key-pn-rekey",
        "guest-key-pn-stale-rekey",
    }:
        source_template = GUEST_KEY_PN_REKEY_SOURCE
        done_marker = "ESPNOW_FABRIC_DONE " + role
    elif scenario in {"lifecycle", "guest-key-rotation"}:
        source_template = LIFECYCLE_SOURCE
        done_marker = "ESPNOW_LIFECYCLE_DONE " + role
    elif scenario == "lifecycle-m5espnow":
        source_template = M5ESPNOW_LIFECYCLE_SOURCE
        done_marker = "ESPNOW_M5_LIFECYCLE_DONE " + role
    elif scenario in FABRIC_SCENARIOS:
        source_template = THREE_PEER_SOURCE
        done_marker = "ESPNOW_FABRIC_DONE " + role
    else:
        source_template = PAIR_SOURCE
        done_marker = "ESPNOW_PAIR_DONE " + role
    source = (
        source_template.replace("__ROLE__", repr(role))
        .replace("__PMK__", repr(pmk))
        .replace("__LMK__", repr(lmk))
        .replace("__ROTATED_LMK__", repr(rotated_lmk))
        .replace("__PEER_MACS__", repr(peer_macs or {}))
        .replace("__PEER_LMKS__", repr(peer_lmks or {}))
        .replace("__PEER_CHANNEL__", repr(peer_channel))
        .replace("__SOAK_SECONDS__", str(soak_seconds))
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
        "M5SW_ESPNOW_PEER_CHANNEL": str(peer_channel),
        "M5SW_ESPNOW_PEER_LOCAL_PORT": str(local_port),
        "M5SW_ESPNOW_PEER_REMOTE_PORT": str(remote_port),
        "M5SW_ESPNOW_PEER_TRACE": "1",
        "M5SW_ESPNOW_PEER_TX_RATE": str(tx_rate),
    }
    if scenario in FABRIC_SCENARIOS:
        runtime_env["M5SW_ESPNOW_PEER_FABRIC"] = "1"
    if public_mac is not None:
        runtime_env["M5SW_ESPNOW_PEER_PUBLIC_MAC"] = public_mac.hex()
    if scenario in {
        "guest-key-pn-rekey",
        "guest-key-pn-stale-rekey",
    }:
        runtime_env["M5SW_ESPNOW_PEER_TX_PN_START"] = "281474976710591"
    if encrypt and not guest_key:
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
    if scenario == "soak":
        records = parse_soak_records(serial)
    elif scenario in {"lifecycle", "guest-key-rotation"}:
        records = parse_lifecycle_records(serial)
    elif scenario == "lifecycle-m5espnow":
        records = parse_m5espnow_lifecycle_records(serial)
    elif scenario in FABRIC_SCENARIOS or scenario in {
        "guest-key-pn-rekey",
        "guest-key-pn-stale-rekey",
    }:
        records = parse_fabric_records(serial)
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


def run_fabric_mode(args: argparse.Namespace, output: Path) -> int:
    devices = {
        "A": args.left_device,
        "B": args.right_device,
        "C": args.third_device,
    }
    macs = {
        "A": bytes.fromhex("02000000010a"),
        "B": bytes.fromhex("02000000010b"),
        "C": bytes.fromhex("02000000010c"),
    }
    broker_port, *role_ports = distinct_ports(4)
    roles = {
        role: {
            "device": device,
            "local_port": role_ports[index],
            "mac": macs[role],
        }
        for index, (role, device) in enumerate(devices.items())
    }
    pmk = b"0123456789abcdef"
    shared_lmk = b"fedcba9876543210"
    pair_lmks = {
        frozenset(("A", "B")): bytes.fromhex(
            "101112131415161718191a1b1c1d1e1f"
        ),
        frozenset(("A", "C")): bytes.fromhex(
            "202122232425262728292a2b2c2d2e2f"
        ),
        frozenset(("B", "C")): bytes.fromhex(
            "303132333435363738393a3b3c3d3e3f"
        ),
    }
    per_peer_key = args.scenario in {
        "fabric-per-peer-key",
        "fabric-per-peer-key-negative",
    }
    expected_links = {
        "A-B": True,
        "A-C": True,
        "B-C": True,
    }
    if args.scenario == "fabric-per-peer-key-negative":
        expected_links["A-B"] = False

    def link_name(left: str, right: str) -> str:
        return "-".join(sorted((left, right)))

    role_lmks = {}
    for role in roles:
        role_lmks[role] = {
            peer_role: (
                pair_lmks[frozenset((role, peer_role))]
                if per_peer_key
                else shared_lmk
            )
            for peer_role in roles
            if peer_role != role
        }
    if args.scenario == "fabric-per-peer-key-negative":
        role_lmks["B"]["A"] = pair_lmks[frozenset(("B", "C"))]

    duplicate_once = args.scenario == "fabric-replay"
    broker = PeerFabric(
        roles=roles,
        broker_port=broker_port,
        duplicate_once=duplicate_once,
    )
    jobs = []
    for role, row in roles.items():
        jobs.append(
            dict(
                api=args.api,
                token_file=args.token_file,
                device=row["device"],
                role=role,
                local_port=row["local_port"],
                remote_port=broker_port,
                output=output / ("role-" + role.lower()),
                scenario=args.scenario,
                encrypt=True,
                guest_key=True,
                pmk=pmk,
                lmk=shared_lmk,
                rotated_lmk=shared_lmk,
                peer_macs={
                    peer_role: macs[peer_role]
                    for peer_role in roles
                    if peer_role != role
                },
                peer_lmks=role_lmks[role],
                public_mac=macs[role],
            )
        )

    broker.start()
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(run_one, **job) for job in jobs
            ]
            results = [future.result() for future in futures]
    finally:
        broker.close()
    broker_stats = broker.summary()

    registration_results = {
        row["role"]: next(
            (
                record
                for record in row["records"]
                if record.get("api") == "fabric_peer_registration"
            ),
            {},
        )
        for row in results
    }
    ready_results = {
        row["role"]: next(
            (
                record
                for record in row["records"]
                if record.get("api") == "fabric_ready"
            ),
            {},
        )
        for row in results
    }
    payload_results = {
        row["role"]: next(
            (
                record
                for record in row["records"]
                if record.get("api") == "fabric_payload"
            ),
            {},
        )
        for row in results
    }
    cleanup_ok = all(
        result["cleanup"]
        and result["cleanup"].get("terminal_state") == "stopped"
        and result["cleanup"].get("runtime_pid_gone") is True
        and result["cleanup"].get("history_preserved") is True
        for result in results
    )
    registration_ok = all(
        row.get("status") == "PASS"
        and row.get("peer_count") == [2, 2]
        for row in registration_results.values()
    )
    def peer_expected(role: str, peer: str) -> bool:
        return expected_links[link_name(role, peer)]

    ready_ok = all(
        sorted(row.get("ready_peers", []))
        == sorted(
            peer
            for peer in set(roles) - {role}
            if peer_expected(role, peer)
        )
        for role, row in ready_results.items()
    )
    payload_ok = all(
        sorted(
            payload_results[role].get("payload_matches", {})
        ) == sorted(set(roles) - {role})
        and sorted(
            payload_results[role].get("source_matches", {})
        ) == sorted(set(roles) - {role})
        and all(
            (
                payload_results[role]
                .get("payload_matches", {})
                .get(peer, 0)
                > 0
            )
            == peer_expected(role, peer)
            and (
                payload_results[role]
                .get("source_matches", {})
                .get(peer, 0)
                > 0
            )
            == peer_expected(role, peer)
            for peer in set(roles) - {role}
        )
        for role in roles
    )
    guest_key_ok = all(
        result["trace"]["guest_key_ready"] >= 2 for result in results
    )
    traffic_ok = all(
        result["trace"]["tx"] > 0 and result["trace"]["rx"] > 0
        for result in results
    )
    results_by_role = {result["role"]: result for result in results}
    if duplicate_once:
        replay_ok = (
            broker_stats["duplicate_sent"]
            and results_by_role["B"]["trace"]["replay_drops"] == 1
            and all(
                result["trace"]["replay_drops"] == 0
                for role, result in results_by_role.items()
                if role != "B"
            )
        )
    else:
        replay_ok = all(
            result["trace"]["replay_drops"] == 0 for result in results
        )
    status_ok = (
        len(results) == 3
        and all(result["returncode"] == 0 for result in results)
        and cleanup_ok
        and registration_ok
        and ready_ok
        and payload_ok
        and guest_key_ok
        and traffic_ok
        and not broker_stats["errors"]
        and all(
            all(counts.values())
            for counts in broker_stats["forwarded"].values()
        )
        and replay_ok
    )
    summary = {
        "schema_version": 1,
        "validation": "virtual-device validation",
        "hardware_validation": "NOT RUN",
        "scenario": args.scenario,
        "encryption": True,
        "key_source": "guest-controller-key-store",
        "key_scope": (
            "pairwise LMK; role B/A intentionally cross-wired"
            if args.scenario == "fabric-per-peer-key-negative"
            else (
                "pairwise LMK"
                if per_peer_key
                else "shared LMK"
            )
        ),
        "expected_links": expected_links,
        "status": "PASS" if status_ok else "FAIL",
        "bridge": {
            "transport": "IPv4 loopback UDP three-guest fabric broker",
            "broker_port": broker_port,
            **broker_stats,
        },
        "roles": {
            role: {
                **{
                    key: value
                    for key, value in row.items()
                    if key != "mac"
                }
            }
            for role, row in roles.items()
        },
        "results": results,
    }
    save(output / "summary.json", summary)
    print(json.dumps({
        "status": summary["status"],
        "scenario": args.scenario,
        "roles": {
            row["role"]: {
                "device": row["device"],
                "returncode": row["returncode"],
                "guest_key_ready": row["trace"]["guest_key_ready"],
                "replay_drops": row["trace"]["replay_drops"],
                "payload": payload_results[row["role"]].get("status"),
                "pn_exhaustions": row["trace"]["pn_exhaustions"],
            }
            for row in results
        },
        "broker": broker_stats,
        "summary": str(output / "summary.json"),
    }, indent=2))
    return 0 if status_ok else 1


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
            "reorder",
            "loss-retry",
            "channel-match",
            "channel-mismatch",
            "rate-mixed",
            "soak",
            "guest-key",
            "guest-key-wrong-lmk",
            "guest-key-rotation",
            "fabric",
            "fabric-replay",
            "fabric-per-peer-key",
            "fabric-per-peer-key-negative",
            "guest-key-pn-rekey",
            "guest-key-pn-stale-rekey",
            "lifecycle",
            "lifecycle-m5espnow",
        ),
        required=True,
    )
    parser.add_argument("--left-device", default="stopwatch")
    parser.add_argument("--right-device", default="sticks3")
    parser.add_argument("--third-device", default="core2")
    parser.add_argument("--soak-seconds", type=int, default=60)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if not 1 <= args.soak_seconds <= 600:
        parser.error("--soak-seconds must be between 1 and 600")
    if args.scenario in FABRIC_SCENARIOS:
        return run_fabric_mode(args, output)
    encrypt = args.scenario != "plaintext"
    guest_key = args.scenario in {
        "guest-key",
        "guest-key-wrong-lmk",
        "guest-key-rotation",
        "loss-retry",
        "channel-match",
        "channel-mismatch",
        "rate-mixed",
        "soak",
        "guest-key-pn-rekey",
        "guest-key-pn-stale-rekey",
    } | FABRIC_SCENARIOS
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
    if args.scenario in {"wrong-lmk", "guest-key-wrong-lmk"}:
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
    rotated_lmk = (
        b"fedcba9876543210"
        if args.scenario == "guest-key-pn-stale-rekey"
        else b"fedcba9876543211"
    )
    left_pmk, left_lmk = keys[args.left_device]
    right_pmk, right_lmk = keys[args.right_device]
    peer_channels = {"A": 1, "B": 1}
    peer_rates = {"A": 11, "B": 11}
    if args.scenario in {"channel-match", "rate-mixed"}:
        peer_channels = {"A": 6, "B": 6}
    elif args.scenario == "channel-mismatch":
        peer_channels = {"A": 1, "B": 6}
    if args.scenario == "rate-mixed":
        peer_rates = {"A": 11, "B": 24}
    replay_proxy = None
    reorder_proxy = None
    loss_proxy = None
    left_proxy_port = None
    right_proxy_port = None
    if args.scenario in {"replay", "reorder", "loss-retry"}:
        (
            left_port,
            right_port,
            left_proxy_port,
            right_proxy_port,
        ) = distinct_ports(4)
        proxy_class = (
            ReplayProxy
            if args.scenario == "replay"
            else ReorderProxy
            if args.scenario == "reorder"
            else LossProxy
        )
        proxy = proxy_class(
            left_service_port=left_port,
            right_service_port=right_port,
            left_proxy_port=left_proxy_port,
            right_proxy_port=right_proxy_port,
        )
        if args.scenario == "replay":
            replay_proxy = proxy
        elif args.scenario == "reorder":
            reorder_proxy = proxy
        else:
            loss_proxy = proxy
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
            guest_key=guest_key,
            pmk=left_pmk,
            lmk=left_lmk,
            rotated_lmk=rotated_lmk,
            peer_channel=peer_channels["A"],
            tx_rate=peer_rates["A"],
            soak_seconds=args.soak_seconds,
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
            guest_key=guest_key,
            pmk=right_pmk,
            lmk=right_lmk,
            rotated_lmk=rotated_lmk,
            peer_channel=peer_channels["B"],
            tx_rate=peer_rates["B"],
            soak_seconds=args.soak_seconds,
        ),
    )
    test_proxy = replay_proxy or reorder_proxy or loss_proxy
    if test_proxy:
        test_proxy.start()
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run_one, **job) for job in jobs]
            results = [future.result() for future in futures]
    finally:
        if test_proxy:
            test_proxy.close()
    proxy_stats = test_proxy.summary() if test_proxy else None

    delivery_results = [
        row
        for result in results
        for row in result["records"]
        if row.get("kind") == "RESULT"
        and row.get("api") == "external_payload"
    ]
    delivery_by_role = {
        row.get("role"): row for row in delivery_results
    }
    trace_by_role = {
        result["role"]: result["trace"] for result in results
    }
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
    pair_registration_api = (
        "fabric_pn_registration"
        if args.scenario in {
            "guest-key-pn-rekey",
            "guest-key-pn-stale-rekey",
        }
        else "external_peer_registration"
    )
    registration_results = [
        row
        for result in results
        for row in result["records"]
        if row.get("kind") == "RESULT"
        and row.get("api") == pair_registration_api
    ]
    soak_results = [
        row
        for result in results
        for row in result["records"]
        if row.get("kind") == "RESULT"
        and row.get("api") == "external_soak"
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
    pn_barrier_results = [
        row
        for result in results
        for row in result["records"]
        if row.get("kind") == "RESULT"
        and row.get("api") == "fabric_pn_barrier"
    ]
    pn_rekey_results = [
        row
        for result in results
        for row in result["records"]
        if row.get("kind") == "RESULT"
        and row.get("api") == "fabric_pn_rekey"
    ]
    pn_post_results = [
        row
        for result in results
        for row in result["records"]
        if row.get("kind") == "RESULT"
        and row.get("api") == "fabric_pn_post"
    ]
    expected_drop = args.scenario in {
        "wrong-lmk",
        "guest-key-wrong-lmk",
        "channel-mismatch",
    }
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
    native_lifecycle = args.scenario in {
        "lifecycle",
        "guest-key-rotation",
    }
    lifecycle_ok = (
        not native_lifecycle
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
    pn_rekey = args.scenario in {
        "guest-key-pn-rekey",
        "guest-key-pn-stale-rekey",
    }
    pn_stale_rekey = args.scenario == "guest-key-pn-stale-rekey"
    pn_rekey_ok = (
        not pn_rekey
        or (
            len(pn_barrier_results) == 2
            and len(pn_rekey_results) == 2
            and len(pn_post_results) == 2
            and all(
                row.get("status") == "PASS"
                for row in pn_barrier_results
            )
            and all(
                row.get("status") == "PASS"
                for row in pn_rekey_results
            )
            and (
                all(
                    row.get("status") == "FAIL"
                    and not any(
                        row.get("payload_matches", {}).values()
                    )
                    for row in pn_post_results
                )
                if pn_stale_rekey
                else all(
                    row.get("status") == "PASS"
                    and all(
                        row.get("payload_matches", {}).values()
                    )
                    for row in pn_post_results
                )
            )
            and all(
                result["trace"]["pn_exhaustions"] > 0
                for result in results
            )
            and all(
                result["trace"]["replay_drops"] == 0
                for result in results
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
    reorder_ok = (
        args.scenario != "reorder"
        or (
            proxy_stats is not None
            and proxy_stats["reordered"] is True
            and proxy_stats["held_frame_released"] is True
            and not proxy_stats["errors"]
            and all(
                result["trace"]["replay_drops"] == 0
                for result in results
            )
        )
    )
    loss_retry_ok = (
        args.scenario != "loss-retry"
        or (
            proxy_stats is not None
            and proxy_stats["dropped"]["left_to_right"] == 2
            and proxy_stats["forwarded"]["left_to_right"] > 0
            and proxy_stats["forwarded"]["right_to_left"] > 0
            and not proxy_stats["errors"]
            and all(
                delivery_by_role.get(role, {}).get("status") == "PASS"
                and delivery_by_role[role].get("tx_attempts", 0) > 2
                and delivery_by_role[role].get("tx_errors") == 0
                for role in ("A", "B")
            )
        )
    )
    soak_ok = (
        args.scenario != "soak"
        or (
            len(soak_results) == 2
            and all(
                row.get("status") == "PASS"
                and row.get("duration_seconds") == args.soak_seconds
                and row.get("tx_count", 0) >= args.soak_seconds * 2
                and row.get("payload_matches", 0)
                >= args.soak_seconds * 2
                and row.get("duplicate_payloads") == 0
                and row.get("unexpected_sources") == 0
                and row.get("tx_errors") == 0
                for row in soak_results
            )
        )
    )
    channel_match_ok = (
        args.scenario != "channel-match"
        or (
            all(
                delivery_by_role.get(role, {}).get("status") == "PASS"
                and delivery_by_role[role].get("peer_channel") == 6
                for role in ("A", "B")
            )
            and all(
                {"channel": 6, "rate": 11}
                in trace_by_role[role]["tx_channel_rates"]
                for role in ("A", "B")
            )
            and all(
                {"channel": 6, "rate": 11}
                in trace_by_role[role]["delivered_channel_rates"]
                for role in ("A", "B")
            )
        )
    )
    channel_mismatch_ok = (
        args.scenario != "channel-mismatch"
        or (
            len(delivery_results) == 2
            and all(
                row.get("status") == "EXPECTED_DROP"
                and row.get("received") is False
                and row.get("rx_packets") == 0
                for row in delivery_results
            )
            and all(
                delivery_by_role[role].get("peer_channel")
                == peer_channels[role]
                and trace_by_role[role]["channel_drops"] > 0
                and trace_by_role[role]["delivered_channel_rates"] == []
                for role in ("A", "B")
            )
        )
    )
    rate_mixed_ok = (
        args.scenario != "rate-mixed"
        or (
            all(
                delivery_by_role.get(role, {}).get("status") == "PASS"
                for role in ("A", "B")
            )
            and all(
                {
                    "channel": peer_channels[role],
                    "rate": peer_rates[role],
                }
                in trace_by_role[role]["tx_channel_rates"]
                for role in ("A", "B")
            )
            and {
                "channel": 6,
                "rate": peer_rates["B"],
            } in trace_by_role["A"]["delivered_channel_rates"]
            and {
                "channel": 6,
                "rate": peer_rates["A"],
            } in trace_by_role["B"]["delivered_channel_rates"]
        )
    )
    guest_key_ok = (
        not guest_key
        or all(
            result["trace"]["guest_key_ready"]
            >= (
                1
                if args.scenario == "guest-key-pn-stale-rekey"
                else 2
                if args.scenario in {
                    "guest-key-rotation",
                    "guest-key-pn-rekey",
                }
                else 1
            )
            for result in results
        )
    )
    proxy_key = {
        "replay": "replay_proxy",
        "reorder": "reorder_proxy",
        "loss-retry": "loss_proxy",
    }.get(args.scenario)
    proxy_transport = {
        "replay": "IPv4 loopback UDP replay proxy",
        "reorder": "IPv4 loopback UDP reorder proxy",
        "loss-retry": "IPv4 loopback UDP loss/retry proxy",
    }.get(
        args.scenario,
        "IPv4 loopback UDP action-frame bridge",
    )
    status_ok = (
        len(registration_results) == 2
        and all(row.get("status") == "PASS" for row in registration_results)
        and (
            (
                native_lifecycle
                and lifecycle_ok
            )
            or (
                args.scenario == "lifecycle-m5espnow"
                and m5espnow_lifecycle_ok
            )
            or (
                pn_rekey
                and pn_rekey_ok
            )
            or (
                args.scenario == "soak"
                and soak_ok
            )
            or (
                args.scenario
                not in {
                    "lifecycle",
                    "lifecycle-m5espnow",
                    "guest-key-rotation",
                    "guest-key-pn-rekey",
                    "guest-key-pn-stale-rekey",
                    "soak",
                }
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
        and reorder_ok
        and loss_retry_ok
        and channel_match_ok
        and channel_mismatch_ok
        and rate_mixed_ok
        and soak_ok
        and guest_key_ok
    )
    summary = {
        "schema_version": 1,
        "validation": "virtual-device validation",
        "hardware_validation": "NOT RUN",
        "scenario": args.scenario,
        **(
            {"soak_seconds": args.soak_seconds}
            if args.scenario == "soak"
            else {}
        ),
        "encryption": encrypt,
        "key_source": (
            "guest-controller-key-store"
            if guest_key
            else ("runtime-env-fixture" if encrypt else "none")
        ),
        "key_scope": (
            (
                "same guest LMK rejected after CCMP PN exhaustion"
                if pn_stale_rekey
                else "new guest LMK resumes after CCMP PN exhaustion"
            )
            if pn_rekey
            else None
        ),
        "status": "PASS" if status_ok else "FAIL",
        "bridge": {
            "transport": proxy_transport,
            "left_local_port": left_port,
            "right_local_port": right_port,
            "peer_channels": peer_channels,
            "peer_rates_mbps": peer_rates,
            "bridge_traffic_ok": bridge_traffic_ok,
            "guest_key_ok": guest_key_ok,
            **(
                {proxy_key: proxy_stats}
                if proxy_stats and proxy_key
                else {}
            ),
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
                            if native_lifecycle
                            else (
                                "external_peer_lifecycle_m5espnow"
                                if args.scenario == "lifecycle-m5espnow"
                                else (
                                    "external_soak"
                                    if args.scenario == "soak"
                                    else "external_payload"
                                )
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
