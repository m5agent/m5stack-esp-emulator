"""Failure controls for live-program evidence; no guest, browser or API calls."""
from copy import deepcopy
import io
import json
import sys
import unittest
import zipfile

from PIL import Image

import run_live_unit_batch as runner


def state(group="controls"):
    return deepcopy(runner.GROUPS[group]["initial"])


def line(values, group="controls", version="A"):
    return f"LIVE_BATCH_{version}_{group.upper()}_SAMPLE " + json.dumps(values) + "\r\n"


def evidence_fixture():
    requested = runner.attachments("controls", "port-a")
    expected = state()
    prefix = b"ESP-ROM: boot\r\nM5EMU_UART_REPL_READY\r\n"
    window = line(expected).encode()
    report = {"session_id": "example", "device_id": "cores3", "runtime": "qemu", "pid": 123,
              "firmware_sha256": "a" * 64, "group": "controls", "attachments": requested,
              "expected_frame_size": [2, 2], "initial_rom_banners": 1,
              "phases": [{"version": "A", "inputs": [{"serial_offset_before": len(prefix),
                    "serial_prefix_sha256": runner.sha(prefix), "serial_window": {"data": window.decode(), "next_offset": len(prefix + window)},
                    "expected_all_leaves": expected, "matched_sample": expected}]}],
              "executions": {}}
    png = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(png, "PNG")
    files = {"serial.log": prefix + window, "frames/current.png": png.getvalue(),
             "qom/snapshot.json": b"{}", "units/contract.json": b"{}", "units/state.json": b"{}", "units/runtime.json": b"{}"}
    manifest = {"session": {"state": "running", **{key: report[key] for key in ("session_id", "device_id", "runtime", "pid", "firmware_sha256")}},
                "units": {"units": [{"id": row["id"], "unit_id": row["unit_id"], "available": True} for row in requested]}}
    return report, files, manifest


def bundle(files, manifest):
    manifest = deepcopy(manifest)
    manifest["files"] = {name: {"size": len(data), "sha256": runner.sha(data)} for name, data in files.items()}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in {**files, "manifest.json": json.dumps(manifest).encode()}.items():
            archive.writestr(name, data)
    return stream.getvalue()


class LiveBatchTests(unittest.TestCase):
    def test_finite_completion_reads_the_program_scanner_instead_of_cached_session(self):
        class Client:
            paths = []

            def json(self, path):
                self.paths.append(path)
                return {"program": {"execution_id": "finite", "state": "completed"}}

        client = Client()
        self.assertTrue(runner.completed_execution(client, "sessions/selected", "finite"))
        self.assertEqual(client.paths, ["sessions/selected/program"])
        with self.assertRaises(RuntimeError):
            runner.completed_execution(client, "sessions/selected", "other")

    def test_each_group_is_admitted_shared_i2c_topology_on_all_four_hosts(self):
        sys.path.insert(0, str(runner.ROOT / "platform/tools"))
        from unit_runtime import UnitRegistry
        registry = UnitRegistry()
        for device in runner.DEVICES:
            port = next(row for row in registry.hosts[device]["ports"] if row.get("physical_presence") == "main-device")
            for group in runner.GROUPS:
                with self.subTest(device=device, group=group):
                    resolved = registry.attachments(device, "qemu", runner.attachments(group, port["id"]))
                    self.assertEqual(len(resolved), 4)
                    self.assertEqual({tuple(row["pins"].items()) for row in resolved}, {tuple(port["pins"].items())})

    def test_plan_sources_compile_and_import_original_unit_classes(self):
        for group, spec in runner.GROUPS.items():
            for version in "AB":
                source = runner.program_source(group, version, "nonce", {"white": 11, "yellow": 10})
                compile(source, "guest-source", "exec")
                self.assertIn(spec["imports"], source)
                self.assertIn("scl=Pin(11), sda=Pin(10)", source)
                self.assertNotIn("control_drivers", source)
                self.assertNotIn("sensor_drivers", source)
        self.assertNotEqual(runner.led_expectations("A"), runner.led_expectations("B"))

    def test_complete_sample_passes_but_other_phase_and_incomplete_lines_fail(self):
        expected = state()
        self.assertEqual(runner.matching_sample(line(expected), "controls", "A", expected), expected)
        for text in (line(expected, version="B"), line(expected).rstrip(), "prefix " + line(expected)):
            with self.subTest(text=text):
                self.assertIsNone(runner.matching_sample(text, "controls", "A", expected))

    def test_no_bool_integer_nan_or_missing_child_aliases(self):
        expected = state()
        changes = [lambda x: x["encoder"].update(pressed=0), lambda x: x["encoder"].update(counter=False),
                   lambda x: x["joystick"].update({"x-raw": float("nan")}), lambda x: x.pop("eight"),
                   lambda x: x["eight"].update(counters=[0] * 7)]
        for change in changes:
            observed = deepcopy(expected)
            change(observed)
            self.assertIsNone(runner.matching_sample(line(observed), "controls", "A", expected))

    def test_sensor_quantization_is_bounded_and_every_field_is_required(self):
        expected = state("sensors")
        observed = deepcopy(expected)
        observed["env"]["pressure-pa"] += 1.4
        observed["ncir"]["ambient-c"] -= .02
        self.assertIsNotNone(runner.matching_sample(line(observed, "sensors"), "sensors", "A", expected))
        observed["env"]["pressure-pa"] += .2
        self.assertIsNone(runner.matching_sample(line(observed, "sensors"), "sensors", "A", expected))

    def test_cross_session_duplicate_or_unavailable_qom_rejected(self):
        requested = runner.attachments("sensors", "port-a")
        response = {"session_id": "selected", "source": "live", "units": [
            {"id": row["id"], "unit_id": row["unit_id"], "available": True, "source": "guest-qom", "properties": {}} for row in requested]}
        self.assertEqual(len(runner.live_units(response, "selected", requested)), 4)
        for change in (lambda x: x.update(session_id="other"), lambda x: x["units"].append(x["units"][0]),
                       lambda x: x["units"][1].update(available=False), lambda x: x.update(source="history")):
            altered = deepcopy(response)
            change(altered)
            with self.assertRaises(RuntimeError):
                runner.live_units(altered, "selected", requested)

    def test_archive_complete_and_fresh_offset_accepted(self):
        report, files, manifest = evidence_fixture()
        self.assertTrue(runner.validate_bundle(bundle(files, manifest), report, {})["member_index_verified"])

    def test_old_identical_marker_cannot_satisfy_new_zip_offset(self):
        report, files, manifest = evidence_fixture()
        row = report["phases"][0]["inputs"][0]
        old = files["serial.log"]
        files["serial.log"] += b"new input happened; no new sample\r\n"
        row["serial_offset_before"] = len(old)
        row["serial_prefix_sha256"] = runner.sha(old)
        row["serial_window"]["next_offset"] = len(files["serial.log"])
        with self.assertRaisesRegex(RuntimeError, "ZIP serial offset"):
            runner.validate_bundle(bundle(files, manifest), report, {})

    def test_binary_uart_credit_bytes_use_raw_offsets_and_api_utf8_representation(self):
        report, files, manifest = evidence_fixture()
        row = report["phases"][0]["inputs"][0]
        split = row["serial_offset_before"]
        prefix = files["serial.log"][:split] + b"R\x01\x80\x00"
        window = files["serial.log"][split:]
        files["serial.log"] = prefix + window
        row["serial_offset_before"] = len(prefix)
        row["serial_prefix_sha256"] = runner.sha(prefix.decode("utf-8", errors="replace").encode())
        row["serial_window"]["next_offset"] = len(files["serial.log"])
        self.assertTrue(runner.validate_bundle(bundle(files, manifest), report, {})["member_index_verified"])
        row["serial_offset_before"] -= 1
        with self.assertRaises(RuntimeError):
            runner.validate_bundle(bundle(files, manifest), report, {})

    def test_wrong_guest_id_or_missing_child_or_reboot_rejected(self):
        for kind in ("pid", "child", "reboot", "source"):
            report, files, manifest = evidence_fixture()
            if kind == "pid":
                manifest["session"]["pid"] += 1
            elif kind == "child":
                manifest["units"]["units"].pop()
            elif kind == "reboot":
                files["serial.log"] += b"M5EMU_UART_REPL_READY\r\n"
            else:
                execution = {"execution_id": "run", "revision_id": "rev", "pid": 123, "firmware_sha256": "a" * 64}
                report["executions"]["a"] = {"program": execution}
                files["programs/run.json"] = json.dumps({**execution, "state": "interrupted", "interruption_confirmed": True}).encode()
                files["programs/rev/source.json"] = json.dumps({"entrypoint": "main.py", "files": {"main.py": "old"}}).encode()
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                runner.validate_bundle(bundle(files, manifest), report, {"a": "new"})


if __name__ == "__main__":
    unittest.main()
