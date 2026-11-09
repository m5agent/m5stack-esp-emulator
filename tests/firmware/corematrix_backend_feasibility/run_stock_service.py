#!/usr/bin/env python3
"""Check the pinned CoreMatrix UIFlow2 image through isolated Device Service."""

from __future__ import annotations

import argparse
from dataclasses import replace
from functools import partial
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import threading
import time
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from PIL import Image

from run_service import ROOT, ProbeService, QuietHandler, make_spec
import device_service
from device_service import DeviceService
from serve import ServiceHTTPServer
from run_stock import FIRMWARE_SHA256, FIRMWARE_SIZE, FLASH_SIZE, ROM_SHA256, sha256


class StockService(ProbeService):
    def create_session(self, payload, *, _management_binding=None):
        if (payload.get("device_id") != "corematrix"
                or payload.get("runtime", "qemu") != "qemu"
                or set(payload) - {"device_id", "runtime"}):
            return super().create_session(payload, _management_binding=_management_binding)
        return DeviceService.create_session(self, {
            **payload, "program_transport": "uart-repl",
            "ready_marker": "Type \"help()\" for more information.",
        }, _management_binding=_management_binding)


def matrix_pixels(png: bytes) -> set[tuple[int, int]]:
    with Image.open(io.BytesIO(png)) as source:
        image = source.convert("RGB")
        assert image.size == (16, 16)
        colors = list(image.getdata())
        assert all(red == green == blue for red, green, blue in colors)
        return {(i % 16, i // 16) for i, color in enumerate(colors) if any(color)}


def validate(base: str, token: str, output: Path, reference_sha: str) -> dict:
    def request(path, payload=None, *, binary=False):
        headers = {"Authorization": f"Bearer {token}"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        with urlopen(Request(base + path, data=data, headers=headers), timeout=35) as response:
            body = response.read()
            return body if binary else json.loads(body)

    try:
        request("/sessions", {"device_id": "corematrix", "firmware_id": FIRMWARE_SHA256})
    except HTTPError as error:
        assert error.code == 409
        assert json.loads(error.read())["error"]["code"] == "reference_only_diagnostic"
    else:
        raise AssertionError("Isolated stock runner admitted a caller-selected firmware")

    session = request("/sessions", {"device_id": "corematrix", "runtime": "qemu"})
    assert session["firmware_sha256"] == reference_sha
    session_id = session["session_id"]
    path = f"/sessions/{session_id}"
    execution_id = None
    serial_offset = 0
    boot_markers = (
        "V2.5.4", "WiFi initialized", "SSID: Not Found",
        "M5Stack CoreMatrix with ESP32-C61HR8", ">>>",
    )
    usb_payload = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 6
    cross = {(x + dx, 3 + step + dy)
             for step in range(0, 10, 2)
             for x in (3 + step, 11 - step)
             for dx in (0, 1) for dy in (0, 1)}

    def wait_serial(markers, *, timeout=20):
        nonlocal serial_offset
        transcript = ""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = request(path + f"/serial?offset={serial_offset}")
            serial_offset = response["next_offset"]
            transcript += response["data"]
            if all(marker in transcript for marker in markers):
                return transcript
            time.sleep(0.05)
        raise AssertionError(f"Stock console did not reach {markers!r}")

    def frame(name, expected):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            png = request(path + "/frame.png", binary=True)
            if matrix_pixels(png) == expected:
                (output / f"{name}.png").write_bytes(png)
                return {"sha256": hashlib.sha256(png).hexdigest(),
                        "width": 16, "height": 16, "lit_pixels": len(expected)}
            time.sleep(0.05)
        raise AssertionError(f"Frame never matched {name} pixel oracle")

    def program(source, marker):
        nonlocal execution_id
        response = request(path + "/program", {
            "source": source, "expected_execution_id": execution_id,
            "timeout_seconds": 12,
        })
        program_record = response["program"]
        assert program_record["firmware_sha256"] == reference_sha
        execution_id = program_record["execution_id"]
        transcript = wait_serial([marker])
        assert request(path + "/program")["program"]["state"] == "completed"
        return next(line for line in transcript.splitlines() if line.startswith(marker))

    try:
        wait_serial(boot_markers)
        boot_frame = frame("stock-cross", cross)
        board = program(
            "import M5; print('CM_BOARD', M5.getBoard(), M5.Lcd.width(), M5.Lcd.height())",
            "CM_BOARD 152 16 16",
        )
        heap = program(
            "import esp32; print('CM_HEAP', sum(region[0] for region in esp32.idf_heap_info(esp32.HEAP_DATA)))",
            "CM_HEAP ",
        )
        long_line = "CM_LONG " + usb_payload
        assert program(
            "print('CM_LONG', '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ' * 6)",
            long_line,
        ) == long_line
        program("import M5; M5.Lcd.clear(0); M5.Lcd.fillRect(1,2,4,3,0xffffff); print('CM_DRAW')", "CM_DRAW")
        drawn = frame("stock-program", {(x, y) for x in range(1, 5) for y in range(2, 5)})
        cases = []
        for key, action, keys in (
            (None, None, (False, False, False)),
            ("a", "down", (True, False, False)),
            ("a", "up", (False, False, False)),
            ("b", "down", (False, True, False)),
            ("b", "up", (False, False, False)),
            ("c", "down", (False, False, True)),
            ("a", "down", (True, False, True)),
            ("c", "up", (True, False, False)),
            ("a", "up", (False, False, False)),
        ):
            if key:
                input_reply = request(path + "/input", {
                    "kind": "key", "key": key, "action": action, "settle_seconds": 0.04,
                })
                assert input_reply["accepted"]
            marker = "CM_BUTTONS " + " ".join(str(value) for value in keys)
            program("import M5; M5.update(); print('CM_BUTTONS', M5.BtnA.isPressed(), M5.BtnB.isPressed(), M5.BtnC.isPressed())", marker)
            pm1 = request(path + "/device-state")["components"]["pm1"]["properties"]["gpio-input-bits"]
            expected_pm1 = 31 ^ sum(1 << index for index, value in enumerate(keys) if value)
            assert pm1 == expected_pm1
            cases.append({"key": key, "action": action, "marker": marker, "pm1_gpio": pm1})
        evidence = request(path + "/evidence", binary=True)
        with ZipFile(io.BytesIO(evidence)) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            assert manifest["session"]["firmware_sha256"] == reference_sha
            assert b"CM_BOARD 152 16 16" in bundle.read("serial.log")
            assert long_line.encode() in bundle.read("serial.log")
            assert bundle.read("frames/current.png")
            assert bundle.read("qom/snapshot.json")
        (output / "session-evidence.zip").write_bytes(evidence)
    finally:
        stopped = request(path + "/stop", {"purge": False})

    assert stopped["state"] == request(path)["state"] == "stopped"
    events = {event["event"] for event in request(path + "/events")["events"]}
    assert {"evidence_bundle", "worker_lease_released", "flash_released"} <= events
    return {
        "session_id_sha256": hashlib.sha256(session_id.encode()).hexdigest(),
        "boot_markers": boot_markers, "board_marker": board, "heap_marker": heap,
        "usb_tx": {"payload_bytes": len(usb_payload),
                   "payload_sha256": hashlib.sha256(usb_payload.encode()).hexdigest(),
                   "next_program_completed": True},
        "boot_frame": boot_frame, "program_frame": drawn, "cases": cases,
        "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
        "stock_only_admission": True, "stop_state": stopped["state"],
        "lease_released": True, "flash_released": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--rom-dir", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    qemu = args.qemu.resolve(strict=True)
    rom_dir = args.rom_dir.resolve(strict=True)
    if sha256(rom_dir / "esp32c61-rom.bin") != ROM_SHA256:
        parser.error("ROM must match the pinned upstream ESP32-C61 ROM")
    if args.firmware.stat().st_size != FIRMWARE_SIZE or sha256(args.firmware) != FIRMWARE_SHA256:
        parser.error("firmware must match the pinned CoreMatrix UIFlow2 v2.5.4 image")

    output = args.out_dir.resolve()
    output.mkdir(parents=True)
    reference = output / "stock-flash.bin"
    reference.write_bytes(args.firmware.read_bytes() + b"\xff" * (FLASH_SIZE - FIRMWARE_SIZE))
    spec = replace(make_spec(qemu, rom_dir, reference), qemu_console_index=3)
    token = secrets.token_urlsafe(32)
    with patch.object(device_service, "load_device_specs", return_value={spec.id: spec}):
        service = StockService(state_dir=output / "state", api_token=token,
                               max_sessions=1, max_per_device=1)
    service.raw_matrix = {"devices": [{"id": spec.id, "backend": spec.backend}]}
    QuietHandler.service = service
    QuietHandler.api_token = token
    with ServiceHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT))) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with (
                patch.dict(os.environ, {"M5_SERVICE_FLASH_MODE": "host-image"}),
                patch.object(device_service, "LIVE_PROGRAM_DEVICES",
                             {*device_service.LIVE_PROGRAM_DEVICES, spec.id}),
            ):
                result = validate(f"http://127.0.0.1:{server.server_port}/api/v1", token,
                                  output, sha256(reference))
        finally:
            service.close_all()
            server.shutdown()
            thread.join()
    summary = {
        "validation": "virtual-device validation", "board": "CoreMatrix C158",
        "machine": spec.machine, "runtime_sha256": sha256(qemu), "rom_sha256": ROM_SHA256,
        "firmware_sha256": FIRMWARE_SHA256, "padded_flash_sha256": sha256(reference), **result,
    }
    (output / "stock-service-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
