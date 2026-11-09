#!/usr/bin/env python3
"""Run the reference-only C61 probe through an isolated Device Service."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

import device_service
from device_service import DeviceService, ServiceError
from device_service_specs import DeviceSpec
from firmware_analysis import analyze_firmware
from serve import Handler, ServiceHTTPServer

from run_stock import FIRMWARE_SHA256, FLASH_SIZE, ROM_SHA256, sha256


class ProbeService(DeviceService):
    def create_session(self, payload, *, _management_binding=None):
        if (payload.get("device_id") != "corematrix"
                or payload.get("runtime", "qemu") != "qemu"
                or set(payload) - {"device_id", "runtime"}):
            raise ServiceError(
                "reference_only_diagnostic", "Only the pinned CoreMatrix IDF probe is enabled", 409
            )
        return super().create_session(payload, _management_binding=_management_binding)


class QuietHandler(Handler):
    def log_message(self, fmt, *args):
        pass


def compose_reference(build_dir: Path, output: Path) -> None:
    args = json.loads((build_dir / "flasher_args.json").read_text())
    if args["extra_esptool_args"]["chip"] != "esp32c61":
        raise ValueError("Probe build must target ESP32-C61")
    if args["flash_settings"]["flash_size"] != "16MB":
        raise ValueError("Probe build must declare 16 MiB flash")
    flash = bytearray(b"\xff" * FLASH_SIZE)
    last_end = 0
    for address, filename in sorted(
            args["flash_files"].items(), key=lambda item: int(item[0], 0)):
        start = int(address, 0)
        path = (build_dir / filename).resolve(strict=True)
        if not path.is_relative_to(build_dir):
            raise ValueError("Probe build segment escapes build directory")
        segment = path.read_bytes()
        end = start + len(segment)
        if start < last_end or end > len(flash):
            raise ValueError("Probe build segment overlaps or exceeds flash")
        flash[start:end] = segment
        last_end = end
    output.write_bytes(flash)
    analysis = analyze_firmware(output, expected_chip_id_value=0x0014)
    if (not analysis["valid"]
            or (analysis.get("app_descriptor") or {}).get("project_name") != "corematrix_i2c_probe"):
        raise ValueError("The diagnostic only executes the CoreMatrix IDF probe build")


def make_spec(qemu: Path, rom_dir: Path, reference: Path) -> DeviceSpec:
    return DeviceSpec(
        id="corematrix", name="CoreMatrix C158 diagnostic", group="esp32-c61",
        soc="ESP32-C61HR8", sku="C158", device_codes=[], backend="qemu-esp32c61",
        machine="esp32c61,m5corematrix=on", flash_size=FLASH_SIZE,
        display={"driver": "TM1680", "width": 16, "height": 16, "touch": False},
        peripherals=["button"], reference_path=reference, qemu=qemu,
        rom_dir=rom_dir, efuse_driver="none", memory=None, env={}, mode="ui",
        expected_size=(16, 16), supported=True, flash_emulator=None,
        service_kind="qemu", emulator=None, elf=None, rom=None, efuse=None,
        c6_firmware=None, peripheral_status="partial", network_chip=None,
        network_profiles=[], network_console="auto", network_status="not-supported",
        warnings=["Reference-only diagnostic. No PSRAM, WiFi or arbitrary firmware."],
        state_probes={"pm1": {"path": "/machine/m5pm1", "properties": ["gpio-input-bits"]}},
        reason=None,
    )


def validate_session(base: str, token: str, output: Path, reference_sha: str) -> dict:
    def request(path, payload=None, *, binary=False):
        headers = {"Authorization": f"Bearer {token}"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        with urlopen(Request(base + path, data=data, headers=headers), timeout=15) as response:
            body = response.read()
            return body if binary else json.loads(body)

    try:
        request("/sessions", {"device_id": "corematrix", "firmware_id": FIRMWARE_SHA256})
    except HTTPError as error:
        rejection = json.loads(error.read())
        if error.code != 409 or rejection["error"]["code"] != "reference_only_diagnostic":
            raise
    else:
        raise RuntimeError("Diagnostic allowed an uploaded firmware session")

    session = request("/sessions", {"device_id": "corematrix", "runtime": "qemu"})
    if session["firmware_sha256"] != reference_sha:
        raise RuntimeError("Session firmware differs from the composed probe")
    session_id = session["session_id"]
    path = f"/sessions/{session_id}"
    serial_offset = 0
    transcript = ""
    cases = []
    previous = 0x1f
    # A and C are also held simultaneously. Release each independently.
    keys = [(None, None, 0x1f), ("a", "down", 0x1e), ("a", "up", 0x1f),
            ("b", "down", 0x1d), ("b", "up", 0x1f), ("c", "down", 0x1b),
            ("a", "down", 0x1a), ("c", "up", 0x1e), ("a", "up", 0x1f)]
    try:
        for index, (key, action, mask) in enumerate(keys):
            if key is not None:
                reply = request(path + "/input", {
                    "kind": "key", "key": key, "action": action, "settle_seconds": 0.02,
                })
                if not reply["accepted"]:
                    raise RuntimeError("Device Service declined the input")
            marker = f"CM_FRAME keys={mask:02x} irq={(previous ^ mask):02x}"
            deadline = time.monotonic() + 15
            incoming = ""
            while time.monotonic() < deadline:
                snapshot = request(path)
                if snapshot["state"] in {"failed", "stopped"}:
                    raise RuntimeError(
                        f"Guest became {snapshot['state']} before {marker}: {snapshot.get('error')}"
                    )
                read = request(path + f"/serial?offset={serial_offset}")
                serial_offset = read["next_offset"]
                incoming += read["data"]
                if snapshot["state"] == "running" and marker in incoming:
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError(f"Guest did not produce {marker}")
            transcript += incoming
            state = request(path + "/device-state")
            if state["components"]["pm1"]["properties"]["gpio-input-bits"] != mask:
                raise RuntimeError("Guest serial and PM1 input observation disagree")

            png = request(path + "/frame.png", binary=True)
            image = Image.open(io.BytesIO(png)).convert("RGB")
            if image.size != (16, 16) or set(image.getdata()) != {(0, 0, 0), (255, 255, 255)}:
                raise RuntimeError("TM1680 did not render a 16×16 black/white frame")
            actual = {(x, y) for y in range(16) for x in range(16)
                      if image.getpixel((x, y)) == (255, 255, 255)}
            expected = {(0, 0), (15, 15)}
            expected.update((2 + 5 * i, 1 + 3 * i) for i in range(3) if not mask & (1 << i))
            if actual != expected:
                raise RuntimeError(f"TM1680 pixel mismatch: {actual} != {expected}")
            (output / f"frame-{index}.png").write_bytes(png)
            cases.append({"key": key, "action": action, "gpio_input_bits": mask,
                          "marker": marker, "lit_xy": sorted(actual),
                          "frame_sha256": hashlib.sha256(png).hexdigest()})
            previous = mask
        if "CM_IDS PM1=2050 IOE=1234 OFF_NACK=1" not in transcript:
            raise RuntimeError("Did not observe the rail-gated TM1680 NACK and board I2C IDs")
        evidence = request(path + "/evidence", binary=True)
        with ZipFile(io.BytesIO(evidence)) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            if (manifest["session"]["firmware_sha256"] != reference_sha
                    or b"CM_FRAME keys=1f" not in bundle.read("serial.log")
                    or not bundle.read("frames/current.png")
                    or not bundle.read("qom/snapshot.json")):
                raise RuntimeError("Live evidence bundle did not preserve the session observations")
        (output / "session-evidence.zip").write_bytes(evidence)
    finally:
        stopped = request(path + "/stop", {"purge": False})
    if stopped["state"] != "stopped" or request(path)["state"] != "stopped":
        raise RuntimeError("Device Service did not retain stopped session history")
    events = request(path + "/events")["events"]
    observed = [event["event"] for event in events]
    if not {"evidence_bundle", "worker_lease_released", "flash_released"} <= set(observed):
        raise RuntimeError("Diagnostic evidence or cleanup events are absent")
    return {"cases": cases, "stop_state": stopped["state"],
            "uploaded_firmware_rejected": True, "lease_released": True, "flash_released": True,
            "session_id_sha256": hashlib.sha256(session_id.encode()).hexdigest(),
            "evidence_sha256": hashlib.sha256(evidence).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--rom-dir", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    qemu = args.qemu.resolve(strict=True)
    rom_dir = args.rom_dir.resolve(strict=True)
    if sha256(rom_dir / "esp32c61-rom.bin") != ROM_SHA256:
        parser.error("ROM must match the pinned upstream ESP32-C61 ROM")
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    reference = output / "probe-flash.bin"
    compose_reference(args.build_dir.resolve(strict=True), reference)
    spec = make_spec(qemu, rom_dir, reference)
    token = secrets.token_urlsafe(32)
    with patch.object(device_service, "load_device_specs", return_value={spec.id: spec}):
        service = ProbeService(state_dir=output / "state", api_token=token,
                               max_sessions=1, max_per_device=1)
    service.raw_matrix = {"devices": [{"id": spec.id, "backend": spec.backend}]}
    QuietHandler.service = service
    QuietHandler.api_token = token
    with ServiceHTTPServer(("127.0.0.1", 0), QuietHandler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {"M5_SERVICE_FLASH_MODE": "host-image"}):
                result = validate_session(
                    f"http://127.0.0.1:{server.server_port}/api/v1", token, output,
                    sha256(reference),
                )
        finally:
            service.close_all()
            server.shutdown()
            thread.join()
    summary = {"validation": "virtual-device validation", "board": "CoreMatrix C158",
               "machine": spec.machine, "runtime_sha256": sha256(qemu),
               "rom_sha256": ROM_SHA256, "firmware_sha256": sha256(reference), **result}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
