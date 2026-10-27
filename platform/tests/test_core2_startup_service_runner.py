"""Acceptance false-positive and lifecycle guards; no cached firmware or QEMU."""
from __future__ import annotations

import ast
from http.server import ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

from serve import Handler

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("core2_startup_service_runner", ROOT / "tests/firmware/core2_startup/run_service_test.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def firmware(version="V2.5.3"):
    data = bytearray(b"\xff" * 0x14000)
    descriptor = bytearray(256)
    struct.pack_into("<I", descriptor, 0, 0xABCD5432)
    encoded = version.encode()
    descriptor[16:16 + len(encoded)] = encoded
    header = bytearray(24)
    header[0:2] = bytes((0xE9, 1))
    app = bytes(header) + struct.pack("<II", 0x3F400020, len(descriptor)) + descriptor
    data[0x10000:0x10000 + len(app)] = app
    entries = bytearray()
    for kind, subtype, offset, size, label in ((0, 0, 0x10000, 0x2000, b"factory"), (1, 0x81, 0x12000, 0x1000, b"vfs")):
        entry = bytearray(32)
        struct.pack_into("<HBBII", entry, 0, 0x50AA, kind, subtype, offset, size)
        entry[12:12 + len(label)] = label
        entries.extend(entry)
    data[0x8000:0x8000 + len(entries)] = entries
    return bytes(data), runner.sha(app)


def bundle(session, serial="V2.5.3\nCORE2_STARTUP_BOOT\nCORE2_STARTUP:display:READY\nCORE2_STARTUP:display:DONE\n"):
    files = {"serial.log": serial.encode(), "frames/current.png": b"test-image"}
    manifest = {"session": session, "files": {name: {"size": len(data), "sha256": runner.sha(data)} for name, data in files.items()}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr("manifest.json", json.dumps(manifest))
    return output.getvalue()


class Core2StartupRunnerTests(unittest.TestCase):
    def test_legacy_version_is_rejected_even_with_its_own_hash_pin(self):
        data, app = firmware("v1.15.4")
        with self.assertRaisesRegex(RuntimeError, "not UIFlow2"):
            runner.firmware_identity(data, runner.sha(data), app)

    def test_version_string_alone_cannot_replace_application_identity(self):
        data, app = firmware()
        tampered = bytearray(data)
        tampered[0x10100] ^= 1
        with self.assertRaisesRegex(RuntimeError, "segments SHA256"):
            runner.firmware_identity(bytes(tampered), runner.sha(tampered), app)
        identity = runner.firmware_identity(data, runner.sha(data), app)
        self.assertEqual(identity["application"]["sha256"], app)
        self.assertEqual(identity["vfs"]["offset"], 0x12000)

    def test_reset_after_done_remains_failure(self):
        serial = "V2.5.3\nCORE2_STARTUP:display:READY\nCORE2_STARTUP:display:DONE\nTG1WDT_SYS_RESET\n"
        checks = runner.serial_checks(serial, "display")
        self.assertTrue(checks["done_marker"])
        self.assertFalse(checks["no_traceback_wdt_or_error"])
        self.assertFalse(runner.serial_checks(serial.replace("V2.5.3", "V1.15.4"), "display")["uiflow2_version"])

    def test_network_requires_bounded_error_before_accepting_done(self):
        serial = "\n".join(("V2.5.3", "CORE2_STARTUP_BOOT", "CORE2_STARTUP:network:ACTIVE True elapsed_ms 12",
            "CORE2_STARTUP:network:CONNECTED False", "CORE2_STARTUP:network:NTP_ERROR OSError(118) elapsed_ms 1001",
            "CORE2_STARTUP:network:READY", "CORE2_STARTUP:network:DONE", ""))
        self.assertTrue(all(runner.serial_checks(serial, "network").values()))
        self.assertFalse(runner.serial_checks(serial.replace("elapsed_ms 1001", "elapsed_ms 5001"), "network")["bounded_network_transport_error"])
        self.assertFalse(runner.serial_checks(serial.replace("CONNECTED False", "CONNECTED True"), "network")["disconnected_reported"])

    def test_evidence_cannot_be_reused_from_another_session(self):
        session = {"session_id": "first", "device_id": "core2", "runtime": "qemu", "firmware_sha256": "a" * 64, "pid": 123, "state": "running"}
        evidence = bundle(session)
        self.assertTrue(runner.validate_bundle(evidence, session)[0]["before_stop"])
        with self.assertRaisesRegex(RuntimeError, "another guest"):
            runner.validate_bundle(evidence, {**session, "session_id": "second"})

    def test_live_booting_negative_control_is_still_before_stop(self):
        session = {"session_id": "first", "device_id": "core2", "runtime": "qemu", "firmware_sha256": "a" * 64, "pid": 123, "state": "booting"}
        metadata = runner.validate_bundle(bundle(session), session)[0]
        self.assertTrue(metadata["before_stop"])
        self.assertEqual(metadata["session_state"], "booting")
        session["state"] = "stopped"
        self.assertFalse(runner.validate_bundle(bundle(session), session)[0]["before_stop"])

    def test_second_software_boot_cannot_pass_with_fresh_done_markers(self):
        serial = "V2.5.3\nCORE2_STARTUP_BOOT\nCORE2_STARTUP:display:READY\nCORE2_STARTUP:display:DONE\n"
        self.assertTrue(all(runner.serial_checks(serial, "display").values()))
        self.assertFalse(runner.serial_checks(serial + "CORE2_STARTUP_BOOT\n", "display")["single_boot"])

    def test_lvgl_equal_foreground_counts_reject_torn_rows_and_outside_label(self):
        from PIL import Image
        glyphs = {(12 + letter * 10 + x, 24 + y) for letter in range(8) for x in range(6) for y in range(14)
                  if x in {0, 5} or y in {0, 13}}
        variants = {"label": glyphs, "torn_row": {(12 + index, 24) for index in range(len(glyphs))},
                    "outside_label": {(x - 12, y) for x, y in glyphs}}
        metrics = {}
        for name, points in variants.items():
            image = Image.new("RGB", (320, 240), (16, 20, 24))
            for point in points:
                image.putpixel(point, (255, 255, 255))
            encoded = io.BytesIO()
            image.save(encoded, format="PNG")
            checks, metrics[name] = runner.frame_checks(encoded.getvalue(), "lvgl")
            self.assertEqual(all(checks.values()), name == "label", name)
        self.assertEqual({result["foreground_pixels"] for result in metrics.values()}, {len(glyphs)})

    def test_qom_collection_uses_actual_http_handler_contract(self):
        session = SimpleNamespace(
            qom_snapshot=mock.Mock(return_value={"nodes": {"memory": {"value": 8 << 20}}}),
            qom_list=mock.Mock(return_value={"properties": [{"name": "device[7]", "type": "child<misc.esp32_wifi>"}]}),
            qom_get=mock.Mock(return_value={"value": False}),
        )

        class LocalHandler(Handler):
            service = SimpleNamespace(get_session=lambda _id: session)
            api_token = previous_api_token = None

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            api = runner.Api(f"http://127.0.0.1:{server.server_port}")
            snapshot, radio = runner.collect_qom(api, "sessions/fixture", offline=True)
            self.assertTrue(snapshot["nodes"])
            self.assertIs(radio["value"], False)
            session.qom_snapshot.assert_called_once_with(path="/machine", depth=2, max_nodes=500)
            session.qom_list.assert_called_once_with("/machine/unattached")
            session.qom_get.assert_called_once_with("/machine/unattached/device[7]", "radio-enabled")
            with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
                api.json("sessions/fixture/qom-snapshot?depth=2&max_nodes=500")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_history_cannot_pass_with_retained_flash_live_pid_or_changed_frame(self):
        session = {"session_id": "fixture", "pid": 123}
        history = {"state": "stopped", "pid": None, "flash_retained": False}
        serial = "V2.5.3\nCORE2_STARTUP_BOOT\nCORE2_STARTUP:display:READY\nCORE2_STARTUP:display:DONE\n"
        api = SimpleNamespace(json=lambda path: {"data": serial + ">>> "} if "/serial?" in path else history,
                              raw=lambda path: b"exact frame")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(runner, "process_identity", return_value={"exists": False}) as identity:
            def check():
                with mock.patch.object(runner, "frame_checks", return_value=({"application_frame": True}, {})):
                    return runner.retained_history(api, "sessions/fixture", session, b"exact frame", serial, Path(tmp), "display")[0]
            self.assertTrue(all(check().values()))
            history["pid"] = session["pid"]
            self.assertTrue(all(check().values()))
            history["flash_retained"] = True
            self.assertFalse(check()["flash_released"])
            history["flash_retained"] = False
            identity.return_value = {"exists": True}
            self.assertFalse(check()["runtime_pid_gone"])
            identity.return_value = {"exists": False}
            api.raw = lambda path: b"different frame"
            self.assertFalse(check()["history_frame_exact"])
            api.raw = lambda path: b"exact frame"
            api.json = lambda path: {"data": serial + "Interrupt wdt timeout\n"} if "/serial?" in path else history
            self.assertTrue(check()["history_serial_retained"])
            self.assertFalse(check()["history_no_traceback_wdt_or_error"])
            self.assertFalse(all(check().values()))

    def test_runtime_identity_uses_nested_worker_and_real_process_token(self):
        session = {"session_id": "fixture", "state": "running", "pid": 123,
                   "worker": {"worker_id": "fixture-worker", "generation": 42, "lease_active": True}}
        identity = {"exists": True, "start_token": "fixed-real-process-token"}
        api = SimpleNamespace(json=lambda path: session)
        with tempfile.TemporaryDirectory() as tmp:
            executable, receipt = Path(tmp) / "qemu", Path(tmp) / "receipt.json"
            executable.write_bytes(b"runtime")
            receipt.write_text('{"files":{},"patches":{}}')
            with mock.patch.object(runner, "runtime_executable", return_value=executable), mock.patch.object(runner, "process_identity", return_value=identity) as probe:
                result = runner.runtime_provenance(api, session, runner.sha(b"runtime"), receipt)
                self.assertEqual(result["worker_generation"], 42)
                self.assertEqual(result["process_start_token"], "fixed-real-process-token")
                probe.side_effect = [identity, {"exists": True, "start_token": "reused-pid-new-process"}]
                with self.assertRaisesRegex(RuntimeError, "ownership changed"):
                    runner.runtime_provenance(api, session, runner.sha(b"runtime"), receipt)

    def test_api_failure_still_requests_evidence_before_retained_stop(self):
        session = {"session_id": "first", "device_id": "core2", "runtime": "qemu", "firmware_sha256": "a" * 64, "pid": 123, "state": "booting"}
        calls = []

        class Api:
            def json(self, path, method="GET", **kwargs):
                calls.append((method, path))
                if path == "artifacts":
                    return {"artifact_id": "artifact"}
                if path == "firmware":
                    return {"firmware_id": "firmware", "sha256": "a" * 64}
                stopped = any(method == "DELETE" for method, _ in calls)
                if "/serial?" in path and not stopped:
                    raise RuntimeError("injected read failure")
                if "/serial?" in path:
                    return {"data": "V2.5.3\n"}
                if method == "DELETE":
                    return {**session, "state": "stopped", "pid": None, "flash_retained": False}
                if calls and any(method == "DELETE" for method, _ in calls):
                    return {**session, "state": "stopped", "pid": None, "flash_retained": False}
                return session

            def raw(self, path):
                calls.append(("GET", path))
                return b"test-image" if path.endswith("frame.png") else bundle(session)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "fixture.bin"
            image.write_bytes(b"image")
            args = SimpleNamespace(out_dir=root / "results", timeout=10, runtime="qemu")
            with mock.patch.object(runner, "prepare", return_value=(image, {"firmware_sha256": "a" * 64})), mock.patch.object(runner, "png_metrics", return_value={"width": 320, "height": 240, "unique_colors": 2}), mock.patch.object(runner, "process_identity", return_value={"exists": False}), mock.patch("builtins.print"):
                result = runner.run_case(Api(), args, "display")
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("injected read failure", result["error"])
            self.assertTrue(result["checks"]["stopped_with_history"])
            self.assertLess(calls.index(("GET", "sessions/first/evidence")), calls.index(("DELETE", "sessions/first?purge=0&retain_flash=0")))
            self.assertEqual(sum(method == "DELETE" for method, _ in calls), 1)

    def test_cold_build_cannot_drop_equal_deadline_timer_fix(self):
        tree = ast.parse((ROOT / "scripts/bootstrap-unit-runtime.py").read_text())
        patches = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "PATCHES" for target in node.targets))
        timer = "patches/qemu-m5stack-peripherals/0034-xtensa-ccompare-equal-deadline.patch"
        compatibility = "patches/qemu-unit-runtime/0002-wifi-radio-lifecycle-compat.patch"
        peripheral = "patches/qemu-m5stack-peripherals/0033-unit-runtime-core-and-routing.patch"
        self.assertLess(patches.index(compatibility), patches.index(timer))
        self.assertLess(patches.index(timer), patches.index(peripheral))


if __name__ == "__main__":
    unittest.main()
