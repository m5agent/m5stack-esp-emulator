#!/usr/bin/env python3
"""Exercise a StickS3 monitor fixture through a dedicated Device Service."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import struct
import sys
import time
import zipfile
import zlib
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "platform/tools"))
from device_service_qemu_wifi import (  # noqa: E402
    STICKS3_MONITOR_SSID as SSID,
    STICKS3_RAW_RX_PROPERTY,
    STICKS3_RAW_TX_PROPERTY,
    STICKS3_RAW_TX_WINDOW_PROPERTY,
    parse_sticks3_wifi_monitor,
)
from user_firmware_matrix import HttpError, request_bytes, request_json  # noqa: E402

STOCK_SHA = "50425b34eb8b4f2b3dea7c85753e37f649c995bfae72b6189e4454077d686246"
SCAN = re.compile(r"SCAN Done: ID: \d+, Status: (\d+), Results: (\d+)")
RX_MARKER = f"MONITOR_RX beacon ssid={SSID} ch=1 rssi=-25 len=81"
DMA_PATH = re.compile(
    r"RX frame type=0 subtype=8 len=81 .*\n"
    r".*RX DMA descriptor=.* length=129 .*\n"
    r".*IRQ raw \|= 01004000 -> 01004000\n"
    r".*IRQ read .* -> 01004000\n"
    r".*IRQ clear 01004000 raw=01004000"
)
TX_PATH = re.compile(
    r"TX DMA outlink=[4-9a-f][0-9a-f]{7}\n"
    r".*TX frame type=0 subtype=4 len=47 .*\n"
    r".*IRQ raw \|= 00000080 -> 00000080\n"
    r".*IRQ read .* -> 00000080\n"
    r".*IRQ clear 00000080 raw=00000080"
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def observe_probe(serial: str, trace: str, enabled: bool) -> dict:
    markers = [line for line in serial.splitlines() if line.startswith("MONITOR_")]
    expected = ["MONITOR_DISABLED matched=0", "MONITOR_ENABLED"]
    result = {}
    if enabled:
        if len(markers) != 6 or not markers[3].startswith("MONITOR_MPDU "):
            raise RuntimeError("guest MPDU capture missing")
        mpdu = bytes.fromhex(markers.pop(3).removeprefix("MONITOR_MPDU "))
        ssid_ie = bytes((0, len(SSID))) + SSID.encode("ascii")
        if len(mpdu) != 81 or mpdu[0] != 0x80 or mpdu[36:36 + len(ssid_ie)] != ssid_ie:
            raise RuntimeError("unexpected guest beacon bytes")
        if not DMA_PATH.search(trace):
            raise RuntimeError("beacon RX DMA and guest IRQ clear not observed")
        tx_path = TX_PATH.search(trace)
        if not tx_path or "RX frame type=0 subtype=5 len=75" not in trace[tx_path.end():]:
            raise RuntimeError("raw probe-request TX DMA, IRQ or virtual AP response missing")
        expected += [RX_MARKER, "MONITOR_TX probe-request len=43", "MONITOR_RESULT PASS"]
        result = {
            "mpdu_sha256": digest(mpdu), "mpdu_bytes": len(mpdu), "dma_bytes": 129,
            "irq_assert_and_guest_clear": True,
            "tx_probe_request": {"api_bytes": 43, "descriptor_frame_bytes": 47,
                                 "irq_assert_and_guest_clear": True, "virtual_ap_reply_bytes": 75},
        }
    else:
        if "TX DMA outlink=" in trace:
            raise RuntimeError("negative probe unexpectedly sent a frame")
        expected.append("MONITOR_RESULT NO_BEACON")
    if markers != expected:
        raise RuntimeError(f"unexpected probe markers: {markers!r}")
    return result | {"guest_markers": markers}


def observe_stock(serial: str, stdout: str, enabled: bool) -> dict:
    scans = [(int(status), int(count)) for status, count in SCAN.findall(serial)[:2]]
    ap_names = set(re.findall(r"QEMU: sending beacon for AP ([^\r\n]+)", stdout))
    if scans != [(0, int(enabled))] * 2 or ap_names != ({SSID} if enabled else set()):
        raise RuntimeError(f"unexpected stock scan results: {scans!r}")
    return {"scan_counts": [count for _, count in scans], "scan_status": [status for status, _ in scans],
            "virtual_ap_names": sorted(ap_names)}


def run(args: argparse.Namespace, mode: str, firmware: dict, call, read_bytes) -> dict:
    enabled = mode == "beacon"
    out = args.out_dir / mode
    out.mkdir()
    payload = {
        "device_id": "sticks3", "runtime": "qemu", "firmware_id": firmware["firmware_id"],
        "wifi_monitor_fixture": mode, "ttl_seconds": 180,
    }
    created = call("/sessions", method="POST", payload=payload)
    path = f"/sessions/{created['session_id']}"
    try:
        deadline = time.monotonic() + 55
        while time.monotonic() < deadline:
            session = call(path)
            if session["state"] == "failed":
                raise RuntimeError(f"fixture startup failed: {session['error']}")
            serial = call(path + "/serial")["data"]
            complete = len(SCAN.findall(serial)) >= 2 if args.stock else "MONITOR_RESULT " in serial
            if session["state"] == "running" and complete:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError(f"firmware did not finish fixture checks: {out}")
        (out / "serial.log").write_text(serial, encoding="utf-8")
        expected_fixture = parse_sticks3_wifi_monitor(payload) | {"status": "FIXTURE_READY"}
        if session["network"] != expected_fixture:
            raise RuntimeError("normalized fixture identity mismatch")
        if session["firmware_sha256"] != firmware["sha256"]:
            raise RuntimeError("boot Flash identity mismatch")
        frame = read_bytes(path + "/frame.png") if args.stock else None
        evidence = read_bytes(path + "/evidence")
        (out / "evidence.zip").write_bytes(evidence)
        with zipfile.ZipFile(io.BytesIO(evidence)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            trace = archive.read("qemu.stderr").decode(errors="replace")
            stdout = archive.read("qemu.stdout").decode(errors="replace")
        receipt = [event for event in manifest["timeline"]
                   if event["event"] == "wifi_monitor_fixture_verified"]
        if (manifest["session"]["network"] != expected_fixture or len(receipt) != 1
                or receipt[0]["fixture_sha256"] != expected_fixture["fixture_sha256"]
                or receipt[0]["host_backends"] != 0 or receipt[0]["radio_enabled"] is not enabled):
            raise RuntimeError("evidence fixture identity mismatch")
        if ("hub 0 is not connected to host network" not in trace
                or ("RX DMA descriptor=" in trace) is not enabled
                or re.search(r"TX frame type=0 subtype=(10|12)\b", trace)):
            raise RuntimeError(f"unexpected Wi-Fi controller observation: {out}")
        if args.stock:
            result = observe_stock(serial, stdout, enabled)
            if not frame.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("invalid stock framebuffer capture")
            (out / "frame.png").write_bytes(frame)
            result["frame_sha256"] = digest(frame)
        else:
            result = observe_probe(serial, trace, enabled)
    finally:
        call(path + "?purge=0", method="DELETE")
    if call(path)["state"] != "stopped":
        raise RuntimeError("Device Service session did not stop")
    return result | {
        "fixture": session["network"], "rx_dma_observed": enabled, "user_inputs": 0,
        "evidence_zip_sha256": digest(evidence), "serial_sha256": digest(serial.encode()),
        "guest_stopped_retained_history": True,
    }


def raw_mpdu(kind: str) -> bytes:
    source = bytes.fromhex("020000005503")
    fc = 0xd0 if kind == "action" else 0x88
    header = struct.pack("<HH6s6s6sH", fc, 0, b"\xff" * 6, source, source, 0x1230)
    if kind == "action":
        body = b"\x7f\x02\x00\x00m5-raw-lab"
    else:
        body = bytes.fromhex("0000aaaa0300000088b5") + b"m5-qos-lab"
    frame = header + body
    return frame + struct.pack("<I", zlib.crc32(frame))


def run_raw(args: argparse.Namespace, kind: str, firmware: dict, call, read_bytes) -> dict:
    out = args.out_dir / f"raw-{kind}"
    out.mkdir()
    inject = kind != "no-injection"
    payload = {
        "device_id": "sticks3", "runtime": "qemu", "firmware_id": firmware["firmware_id"],
        "wifi_monitor_fixture": "raw", "ttl_seconds": 180,
    }
    created = call("/sessions", method="POST", payload=payload)
    path = f"/sessions/{created['session_id']}"

    def wait_marker(marker, sample=None):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            session = call(path)
            if session["state"] == "failed":
                raise RuntimeError(f"raw fixture startup failed: {session['error']}")
            serial = call(path + "/serial")["data"]
            if sample:
                sample()
            if session["state"] == "running" and marker in serial:
                return session, serial
            time.sleep(0.035)
        raise RuntimeError(f"missing guest marker {marker!r}: {out}")

    try:
        session, _ = wait_marker("MONITOR_ENABLED")
        config = parse_sticks3_wifi_monitor(payload) | {"status": "FIXTURE_READY"}
        network = dict(session["network"])
        qom_path = network.pop("raw_qom_path")
        if network != config or session["firmware_sha256"] != firmware["sha256"]:
            raise RuntimeError("raw fixture or boot Flash identity mismatch")
        qom_read = path + f"/qom?path={qom_path}&property="
        window_path = qom_read + STICKS3_RAW_TX_WINDOW_PROPERTY
        captures = {}
        def read_window():
            rows = call(window_path)["value"].splitlines()
            sequences = []
            for row in rows:
                sequence, tx_hex = row.split(":", 1)
                n = int(sequence)
                tx = bytes.fromhex(tx_hex)
                if n in captures and captures[n] != tx:
                    raise RuntimeError(f"capture changed for TX sequence {n}")
                captures[n] = tx
                sequences.append(n)
            if sequences and sequences != list(range(sequences[0], sequences[0] + len(rows))):
                raise RuntimeError("TX capture window is out of order")
            return sequences

        if call(qom_read + STICKS3_RAW_TX_PROPERTY)["value"] != "0:" or read_window():
            raise RuntimeError("unexpected capture before sending the fixture")
        packet = raw_mpdu(kind) if inject else b""
        if inject:
            body = {"path": qom_path, "property": STICKS3_RAW_RX_PROPERTY}
            invalid = packet[:-1] + bytes((packet[-1] ^ 1,))
            protected = bytes((packet[0], packet[1] | 0x40)) + packet[2:-4]
            protected += struct.pack("<I", zlib.crc32(protected))
            for negative in (invalid, protected):
                try:
                    call(path + "/qom", method="POST", payload=body | {"value": negative.hex()})
                except HttpError as error:
                    if error.status != 409 or error.payload["error"]["code"] != "wifi_monitor_mpdu_rejected":
                        raise
                else:
                    raise RuntimeError("wrong-FCS or protected-frame control was accepted")
            call(path + "/qom", method="POST", payload=body | {"value": packet.hex()})
        marker = "MONITOR_RESULT PASS" if inject else "MONITOR_RESULT NO_BEACON"
        _, serial = wait_marker(marker, sample=read_window)
        retained = read_window()
        latest = call(qom_read + STICKS3_RAW_TX_PROPERTY)["value"]
        (out / "serial.log").write_text(serial, encoding="utf-8")
        evidence = read_bytes(path + "/evidence")
        (out / "evidence.zip").write_bytes(evidence)
        with zipfile.ZipFile(io.BytesIO(evidence)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            trace = archive.read("qemu.stderr").decode(errors="replace")
            stdout = archive.read("qemu.stdout").decode(errors="replace")
            qom_snapshot = archive.read("qom/snapshot.json")
        if (manifest["session"]["network"] != session["network"]
                or "hub 0 is not connected to host network" not in trace
                or "QEMU: sending beacon" in stdout or "TX frame type=" in trace
                or any(name.encode() in qom_snapshot
                       for name in (STICKS3_RAW_TX_PROPERTY, STICKS3_RAW_TX_WINDOW_PROPERTY))):
            raise RuntimeError("raw fixture isolation or evidence mismatch")
        events = [event for event in manifest["timeline"]
                  if event.get("property") == STICKS3_RAW_RX_PROPERTY]
        if inject:
            captured = re.search(r"^MONITOR_MPDU ([0-9a-f]+)", serial, re.MULTILINE)
            expected_body = bytes((0, len(SSID))) + SSID.encode("ascii") + bytes.fromhex("010182")
            if (f"MONITOR_RX {kind} ch=1 rssi=-42 len={len(packet)}" not in serial
                    or not captured or bytes.fromhex(captured[1]) != packet
                    or "MONITOR_TX burst count=12 len=49" not in serial
                    or sorted(captures) != list(range(1, 13)) or retained != list(range(5, 13))
                    or latest != f"12:{captures[12].hex()}"
                    or not re.search(rf"RX DMA descriptor=.* length={len(packet) + 48} ", trace)
                    or "IRQ clear 01004000 raw=01004000" not in trace
                    or trace.count("IRQ clear 00000080 raw=00000080") != 12
                    or len(events) != 1 or events[0].get("mpdu_sha256") != digest(packet)
                    or "value" in events[0]):
                raise RuntimeError(f"MPDU, capture window or IRQ mismatch: {out}")
            for n, tx in captures.items():
                if (len(tx) != 53 or tx[0] != 0x40 or tx[24:43] != expected_body
                        or tx[43:49] != bytes((221, 4, 2, 0, 0, n))
                        or tx[-4:] != bytes.fromhex("efbeadde")):
                    raise RuntimeError(f"unexpected guest TX frame for capture {n}")
            (out / "tx-captures.json").write_text(
                json.dumps({n: tx.hex() for n, tx in captures.items()}, indent=2) + "\n",
                encoding="utf-8",
            )
            call(path + "/reset", method="POST", payload={})
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if (call(qom_read + STICKS3_RAW_TX_PROPERTY)["value"] == "0:"
                        and call(window_path)["value"] == ""):
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError("controller reset retained a stale TX capture")
        elif captures or latest != "0:" or events or "RX DMA descriptor=" in trace or "TX DMA outlink=" in trace:
            raise RuntimeError("raw no-injection control observed traffic")
    finally:
        call(path + "?purge=0", method="DELETE")
    stopped = call(path)
    if stopped["state"] != "stopped" or stopped["flash_retained"]:
        raise RuntimeError("Device Service session did not release its guest Flash")
    return {
        "fixture_sha256": config["fixture_sha256"],
        "host_backends": 0,
        "guest_markers": [line for line in serial.splitlines()
                          if line.startswith("MONITOR_") and not line.startswith("MONITOR_MPDU ")],
        "rx_mpdu_sha256": digest(packet) if inject else None,
        "rx_mpdu_bytes": len(packet),
        "tx_mpdu_sha256_by_sequence": {n: digest(tx) for n, tx in captures.items()},
        "tx_mpdu_bytes": len(captures[12]) if inject else 0,
        "retained_tx_sequences": retained,
        "reset_cleared_capture": inject,
        "invalid_fcs_and_protected_rejected": inject,
        "evidence_zip_sha256": digest(evidence),
        "serial_sha256": digest(serial.encode()),
        "guest_stopped_retained_history": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--stock", action="store_true", help="verify exact M5Gotchi v0.7 scans")
    mode.add_argument("--raw", action="store_true", help="verify byte-exact raw RX and controller TX capture")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    service = urlsplit(args.service)
    if (service.scheme != "http" or service.hostname != "127.0.0.1"
            or service.netloc != f"127.0.0.1:{service.port}"
            or service.port in (None, 8787, 8830) or service.path not in ("", "/")
            or service.query or service.fragment):
        parser.error("use a dedicated non-reserved loopback Device Service")
    binary = args.firmware.read_bytes()
    if args.stock and digest(binary) != STOCK_SHA:
        parser.error("expected exact public M5Gotchi v0.7 firmware")
    if not args.stock and (len(binary) != 8 * 1024 * 1024 or binary[0] != 0xE9):
        parser.error("expected padded 8 MiB ESP-IDF probe image")
    args.out_dir.mkdir(mode=0o700, parents=True)
    prefix = f"{args.service.rstrip('/')}/api/v1"
    auth = {"Authorization": f"Bearer {args.token_file.read_text().strip()}"}

    def call(path, **kwargs):
        return request_json(prefix + path, headers=auth, timeout=20, **kwargs)

    def read_bytes(path):
        return request_bytes(prefix + path, headers=auth, timeout=20)[0]

    artifact = request_json(
        prefix + "/artifacts", method="POST", body=binary, timeout=20,
        headers={**auth, "Content-Type": "application/octet-stream",
                 "X-Artifact-Name": args.firmware.name},
    )
    firmware = call("/firmware", method="POST", payload={
        "device_id": "sticks3", "kind": "merged", "artifact_id": artifact["artifact_id"],
    })
    boot_sha = digest(binary + b"\xff" * (8 * 1024 * 1024 - len(binary)))
    if artifact["sha256"] != digest(binary) or firmware["sha256"] != boot_sha:
        raise RuntimeError("uploaded or normalized Flash SHA mismatch")
    if args.raw:
        cases = {kind: run_raw(args, kind, firmware, call, read_bytes)
                 for kind in ("action", "qos", "no-injection")}
    else:
        cases = {label: run(args, label, firmware, call, read_bytes)
                 for label in ("beacon", "no-beacon")}
    summary = {
        "device": "sticks3", "runtime": "qemu", "firmware_sha256": digest(binary),
        "boot_flash_sha256": boot_sha, "cases": cases, "result": "PASS",
    }
    result = json.dumps(summary, indent=2) + "\n"
    (args.out_dir / "result.json").write_text(result, encoding="utf-8")
    print(result, end="")


if __name__ == "__main__":
    main()
