"""Private radio links for paired native esp32sim leases."""

from contextlib import ExitStack
from dataclasses import dataclass
import json
import os
import re
import select
import socket
import threading
import time

from device_service_errors import ServiceError


PAIR_MODES = {
    "cap-lora1262": "cardputer-adv",
    "cap-lora868": "cardputer-adv",
    "cap-cc1101": "cardputer-adv",
    "papermono-lora": "papermono",
    "nesso-lora": "nesso-n1",
    "nanoc6-thread": "nanoc6",
    "nanoc6-zigbee": "nanoc6",
}
COOJA_MODES = frozenset({"nanoc6-thread", "nanoc6-zigbee"})
SLICE_NS = 100_000
MAX_REPLY_BYTES = 256 << 10
MAX_TRACE_BYTES = 4 << 20


def parse_pair(payload):
    if set(payload) - {"mode", "firmware_ids", "ttl_seconds"}:
        raise ServiceError("invalid_radio_pair", "Provide mode, two firmware_ids and optional ttl_seconds", 400)
    mode, firmware_ids = payload.get("mode"), payload.get("firmware_ids")
    if not isinstance(mode, str) or mode not in PAIR_MODES:
        raise ServiceError("invalid_radio_pair", "Choose a supported radio pair mode", 400)
    if (not isinstance(firmware_ids, list) or len(firmware_ids) != 2
            or not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                       for value in firmware_ids)):
        raise ServiceError("invalid_radio_pair", "Provide exactly two stored SHA-256 firmware IDs", 400)
    if "ttl_seconds" in payload and (type(payload["ttl_seconds"]) is not int or payload["ttl_seconds"] < 30):
        raise ServiceError("invalid_ttl", "ttl_seconds must be an integer >= 30", 400)
    return mode, firmware_ids


def allocate_loopback_ports():
    with ExitStack() as stack:
        sockets = [stack.enter_context(socket.socket()) for _ in range(2)]
        for sock in sockets:
            sock.bind(("127.0.0.1", 0))
        return tuple(sock.getsockname()[1] for sock in sockets)


@dataclass(frozen=True)
class RadioSlot:
    mode: str
    index: int
    ports: tuple[int, int] | None
    medium: "CoojaPair | None"

    def arguments(self):
        if self.medium is not None:
            return ["--cooja", "--console", "both"]
        local, remote = self.ports[::1 if self.index == 0 else -1]
        link = f"{local}:{remote}"
        if self.mode == "papermono-lora":
            return ["--lora-peer", link]
        if self.mode == "nesso-lora":
            return ["--cap-peer", link]
        return ["--cap", self.mode.removeprefix("cap-"), "--cap-peer", link]


class CoojaPair:
    """Schedule two C6 controller models on one virtual 802.15.4 channel.

    The CLI owns the guest and the transceiver. This broker advances time and
    forwards complete frames emitted by the emulated transceiver to its peer.
    """

    def __init__(self):
        self.trace_path = None
        self._lock = threading.Lock()
        self._end = threading.Event()
        self._nodes = {}

    def attach(self, index, process, on_log, on_failure):
        with self._lock:
            if self._end.is_set():
                raise ServiceError("radio_pair_closed", "The peer lease is closed", 409)
            self._nodes[index] = (process, on_log, on_failure)
            if len(self._nodes) == 2:
                threading.Thread(target=self._run, name="esp32sim-cooja-pair", daemon=True).start()

    def close(self):
        self._end.set()

    def _exchange(self, process, payload):
        process.stdin.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
        process.stdin.flush()
        line = bytearray()
        deadline = time.monotonic() + 10
        while not self._end.is_set() and time.monotonic() < deadline:
            if not select.select([process.stdout], [], [], 0.1)[0]:
                continue
            chunk = os.read(process.stdout.fileno(), 64 << 10)
            line.extend(chunk)
            if not chunk or len(line) > MAX_REPLY_BYTES:
                break
            if line.endswith(b"\n"):
                reply = json.loads(line)
                if reply["type"] == "done":
                    return reply
                break
        raise RuntimeError("C6 peer did not return a bounded step reply")

    def _run(self):
        nodes = [self._nodes[index] for index in range(2)]
        try:
            with self.trace_path.open("wb") as trace:
                self._schedule(nodes, trace)
        except (RuntimeError, OSError, ValueError, KeyError, TypeError) as error:
            if not self._end.is_set():
                for _, _, on_failure in nodes:
                    on_failure(RuntimeError(f"802.15.4 peer transport failed: {error}"))
        finally:
            self._end.set()

    def _schedule(self, nodes, trace):
        now = [0, 0]
        stalls = [0, 0]
        channels = [None, None]
        pending = [[], []]
        for index, (process, _, _) in enumerate(nodes):
            self._exchange(process, {
                "type": "hello", "id": index + 1, "seed": 1,
                "args": {"observe_leds": True},
            })
        wall_start = time.monotonic_ns()
        while not self._end.is_set():
            index = 0 if now[0] <= now[1] else 1
            peer = 1 - index
            process, on_log, _ = nodes[index]
            horizon = now[index] + SLICE_NS
            remaining = wall_start + now[index] - time.monotonic_ns()
            if remaining > 1_000_000 and self._end.wait(remaining / 1e9):
                break
            due = [event for event in pending[index] if event["t"] <= horizon]
            pending[index] = [event for event in pending[index] if event["t"] > horizon]
            reply = self._exchange(process, {"type": "step", "t": horizon, "in": due})
            if type(reply["t"]) is not int or not now[index] <= reply["t"] <= horizon:
                raise RuntimeError("C6 peer returned an invalid guest timestamp")
            stalls[index] = stalls[index] + 1 if reply["t"] == now[index] else 0
            if stalls[index] >= 100:
                raise RuntimeError("C6 peer stopped advancing guest time")
            now[index] = reply["t"]
            for event in reply["out"]:
                event_type = event["type"]
                if event_type == "log":
                    on_log(f"{event['t'] / 1e9:.6f} {event['line']}\n".encode())
                    continue
                if trace.tell() < MAX_TRACE_BYTES:
                    # Store controller events and timing. Guest frame contents
                    # remain in the guest and do not bypass the serial ACL.
                    trace.write(json.dumps({
                        "node": index, **{key: value for key, value in event.items() if key != "frame"},
                    }, separators=(",", ":")).encode() + b"\n")
                    trace.flush()
                if "ch" in event:
                    channels[index] = event["ch"]
                if event_type == "tx" and channels[peer] == event["ch"]:
                    pending[peer].append({"type": "rx", "t": event["t"], "frame": event["frame"],
                                          "rssi": -55, "lqi": 255})
