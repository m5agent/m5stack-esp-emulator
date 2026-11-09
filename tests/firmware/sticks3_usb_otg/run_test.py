#!/usr/bin/env python3
"""Exercise the original Bit Pirate StickS3 image through a virtual USB host."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import time
import urllib.parse
import urllib.request

FLASH_SHA = "b892cfb72ef2c9f895da9cb2ddb3eb489a194f990decc95fad8092518c1cdf6e"
MENU_SHA = "93d00bb47faee5fca0c5ca6713278ca62ef45ac98177e95eb011c5e974e33e79"
SERIAL_SELECTION_SHA = "abb7bbf051e82d05e72c0ab88bffc9819ea4c5ecf28c99359dec53c4358900ec"
USB = "/machine/soc/usb-otg"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Probe:
    def __init__(self, url: str, token: str):
        self.url = url
        self.headers = {"Authorization": f"Bearer {token}"}
        self.transcript: list[tuple[str, str]] = []

    def request(self, route: str = "", body: dict | None = None, *, raw=False):
        headers = self.headers.copy()
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        request = urllib.request.Request(self.url + route, data, headers)
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read()
        return payload if raw else json.loads(payload)

    def state(self, prop: str) -> str:
        query = urllib.parse.urlencode({"path": USB, "property": prop})
        return self.request(f"/qom?{query}")["value"]

    def packet(self, command: str, expected: str, timeout: float = 4) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.request("/qom", {"path": USB, "property": "host-packet", "value": command})
            response = self.state("host-response")
            self.transcript.append((command, response))
            if response.startswith(expected):
                return response
            if response not in {"DETACHED", "NAK"}:
                raise RuntimeError(f"USB packet {command!r} returned {response!r}")
            time.sleep(0.04)
        raise TimeoutError(f"USB packet {command!r} did not return {expected!r}")

    def setup(self, request_type: int, request: int, value: int, index: int, length: int):
        data = struct.pack("<BBHHH", request_type, request, value, index, length)
        self.packet(f"setup {data.hex()}", "ACK")

    def read(self, request_type: int, request: int, value: int, index: int, length: int) -> bytes:
        self.setup(request_type, request, value, index, length)
        data = bytearray()
        while len(data) < length:
            packet = bytes.fromhex(self.packet("in 0", "DATA:")[5:])
            data.extend(packet)
            if len(packet) < 64:
                break
        self.packet("out 0", "ACK")
        return bytes(data)

    def write(self, request_type: int, request: int, value: int, index: int, data=b""):
        self.setup(request_type, request, value, index, len(data))
        if data:
            self.packet(f"out 0 {data.hex()}", "ACK")
        assert self.packet("in 0", "DATA:") == "DATA:", "Expected zero-length status"

    def wait_frame(self, expected: str):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if digest(self.request("/frame.png", raw=True)) == expected:
                return
            time.sleep(0.1)
        raise TimeoutError("Expected terminal-selection frame did not appear")


def run(probe: Probe) -> dict:
    session = probe.request()
    assert session["device_id"] == "sticks3" and session["runtime"] == "qemu"
    assert session["firmware_sha256"] == FLASH_SHA
    probe.packet("reset", "ACK", 20)
    assert probe.state("host-state") == "attached address=0 mode=fifo"
    device = probe.read(0x80, 6, 0x0100, 0, 18)
    assert len(device) == 18 and device[8:12] == bytes.fromhex("3a300210")
    probe.write(0, 5, 7, 0)
    assert probe.state("host-state") == "attached address=7 mode=fifo"

    header = probe.read(0x80, 6, 0x0200, 0, 9)
    assert len(header) == 9 and header[0:2] == b"\x09\x02"
    total = int.from_bytes(header[2:4], "little")
    assert total == 130
    configuration = probe.read(0x80, 6, 0x0200, 0, total)
    assert len(configuration) == total
    probe.write(0, 9, configuration[5], 0)
    assert probe.read(0x80, 8, 0, 0, 1) == bytes([configuration[5]])

    # The pinned configuration contains HID interface 1 and CDC ACM interface 2.
    report = probe.read(0x81, 6, 0x2200, 1, 245)
    assert len(report) == 245
    initial = probe.read(0xA1, 0x21, 0, 2, 7)
    assert initial == struct.pack("<IBBB", 115200, 0, 0, 8)
    alternate = struct.pack("<IBBB", 57600, 0, 0, 8)
    probe.write(0x21, 0x20, 0, 2, alternate)
    assert probe.read(0xA1, 0x21, 0, 2, 7) == alternate
    probe.write(0x21, 0x20, 0, 2, initial)
    assert probe.read(0xA1, 0x21, 0, 2, 7) == initial
    probe.write(0x21, 0x22, 3, 2)  # DTR and RTS

    probe.wait_frame(MENU_SHA)
    probe.request("/input", {"kind": "key", "key": "b", "action": "tap",
                             "hold_seconds": 0.18, "settle_seconds": 0.4})
    probe.wait_frame(SERIAL_SELECTION_SHA)
    probe.request("/input", {"kind": "key", "key": "a", "action": "tap",
                             "hold_seconds": 0.18, "settle_seconds": 0.4})
    probe.packet("out 3 0d0a", "ACK")  # Empty input line. No application command.
    incoming = bytearray()
    for _ in range(12):
        response = probe.packet("in 4", "DATA:")
        incoming.extend(bytes.fromhex(response[5:]))
        if b"HIZ>" in incoming:
            break
    assert b"Press any key to start" in incoming and b"HIZ>" in incoming
    serial = probe.request("/serial")["data"]
    assert "tinyusb_driver_install(): Can't initialize the TinyUSB stack" not in serial
    return {
        "device_descriptor_sha256": digest(device),
        "configuration_descriptor_sha256": digest(configuration),
        "hid_report_descriptor_sha256": digest(report),
        "cdc_line_coding": [115200, 57600, 115200],
        "bulk_out_ep3": "CRLF ACK",
        "bulk_in_ep4_bytes": len(incoming),
        "bulk_in_ep4_sha256": digest(incoming),
        "guest_markers": ["Press any key to start", "HIZ>"],
        "serial_sha256": digest(serial.encode()),
        "transaction_sha256": digest(json.dumps(probe.transcript).encode()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True, help="Owned Device Service URL including /api/v1")
    parser.add_argument("--session", required=True, help="Running session of the pinned merged firmware")
    parser.add_argument("--token-file", required=True, type=Path)
    args = parser.parse_args()
    parsed = urllib.parse.urlsplit(args.api)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port in (None, 8787, 8830):
        parser.error("use an isolated loopback Device Service port")
    url = f"{args.api.rstrip('/')}/sessions/{urllib.parse.quote(args.session, safe='')}"
    probe = Probe(url, args.token_file.read_text().strip())
    print(json.dumps(run(probe), indent=2))


if __name__ == "__main__":
    main()
