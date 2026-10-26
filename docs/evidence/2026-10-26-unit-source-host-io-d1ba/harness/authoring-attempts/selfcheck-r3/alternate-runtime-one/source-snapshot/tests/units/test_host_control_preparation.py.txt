"""Offline host-control preparation/freshness gates; no service or guest runs."""
from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import prepare_host_controls as preparation
import run_host_control_cases as runner


def digest(data):
    return hashlib.sha256(data).hexdigest()


class PreparationFreshnessTests(unittest.TestCase):
    """Small real source/snapshot trees exercise the production freshness gate."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="m5-host-control-sources-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.prepared = self.root / "prepared"
        self.prepared.mkdir()
        self.names = sorted(runner.REQUIRED_PREPARATION | {
            "platform/units/runtime-profiles.json", "platform/units/host-ports.json",
            "platform/units/catalog.json", "tests/units/controls_probe/control_drivers/encoder.py",
        })
        self.paths = [self.root / name for name in self.names]
        for name, path in zip(self.names, self.paths):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("# current source: " + name + "\n").encode())
        self.refresh()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(runner, "ROOT", self.root))
        self.inventory = self.stack.enter_context(patch.object(preparation, "source_paths", side_effect=lambda: (self.paths, {})))

    def refresh(self):
        frozen = {}
        for name, path in zip(self.names, self.paths):
            raw = path.read_bytes()
            frozen[name] = digest(raw)
            snapshot = self.prepared / "source-snapshot" / (name + ".txt")
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(raw)
        self.report = {"source_sha256": frozen, "cases": []}
        (self.prepared / "readiness.json").write_text(json.dumps(self.report))

    def test_current_profile_hash_is_bound_without_historical_special_case(self):
        profile = self.root / "platform/units/runtime-profiles.json"
        for content in (b'{"current_profile": 1}\n', b'{"current_profile": 2}\n'):
            profile.write_bytes(content)
            self.refresh()
            result = runner.preparation_continuity(self.prepared, self.report)
            self.assertEqual(result["status"], "EXACT_CURRENT_SOURCE_MATCH")
            self.assertEqual(result["allowed_changes"], [])
            self.assertEqual(result["source_sha256"]["platform/units/runtime-profiles.json"], digest(content))

    def test_changed_profile_wiring_driver_or_builder_requires_repreparation(self):
        for name in ("platform/units/runtime-profiles.json", "platform/units/host-ports.json",
                     "tests/units/controls_probe/control_drivers/encoder.py", "tests/uiflow2/esp_flash.py"):
            with self.subTest(source=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b"# changed\n")
                try:
                    with self.assertRaisesRegex(AssertionError, "prepared source changed"):
                        runner.preparation_continuity(self.prepared, self.report)
                finally:
                    path.write_bytes(original)

    def test_changed_snapshot_is_rejected_even_when_current_source_matches(self):
        snapshot = self.prepared / "source-snapshot/platform/units/runtime-profiles.json.txt"
        snapshot.write_bytes(b"tampered snapshot\n")
        with self.assertRaisesRegex(AssertionError, "snapshot missing or changed"):
            runner.preparation_continuity(self.prepared, self.report)

    def test_added_or_removed_dependency_inventory_requires_repreparation(self):
        original = list(self.paths)
        extra = self.root / "tests/units/new_helper.py"
        extra.write_text("# new implementation dependency\n")
        for paths in (original + [extra], original[:-1]):
            with self.subTest(inventory_size=len(paths)):
                self.paths = paths
                with self.assertRaisesRegex(AssertionError, "source inventory changed"):
                    runner.preparation_continuity(self.prepared, self.report)
        self.paths = original

    def test_missing_shared_injection_freeze_is_rejected(self):
        del self.report["source_sha256"]["tests/uiflow2/lib/rtc_probe.py"]
        with self.assertRaisesRegex(AssertionError, "omits a direct packager/common dependency"):
            runner.preparation_continuity(self.prepared, self.report)

    def test_cli_source_drift_is_rejected_before_toolchain_service_or_bridge(self):
        (self.root / "platform/units/runtime-profiles.json").write_text("changed after preparation\n")
        argv = ["run_host_control_cases.py", "--prepared-dir", str(self.prepared)]
        with patch.object(sys, "argv", argv), \
             patch.object(runner, "toolchain_preflight") as toolchain, \
             patch.object(runner, "Client") as client, \
             patch.object(runner, "DeadlineBridge") as bridge:
            with self.assertRaisesRegex(AssertionError, "prepared source changed"):
                runner.main()
        toolchain.assert_not_called()
        client.assert_not_called()
        bridge.assert_not_called()

    def test_execute_requires_parameters_before_prepared_assets_or_service(self):
        for options in ([], ["--out-dir", str(self.root / "new-output")],
                        ["--out-dir", str(self.root / "new-output"), "--expected-runtime-sha256", "invalid"]):
            with self.subTest(options=options):
                argv = ["run_host_control_cases.py", "--prepared-dir", str(self.root / "absent"), "--execute", *options]
                with patch.object(sys, "argv", argv), redirect_stderr(io.StringIO()), \
                     patch.object(runner, "toolchain_preflight") as toolchain, \
                     patch.object(runner, "Client") as client, \
                     patch.object(runner, "DeadlineBridge") as bridge:
                    with self.assertRaises(SystemExit) as stopped:
                        runner.main()
                self.assertEqual(stopped.exception.code, 2)
                toolchain.assert_not_called()
                client.assert_not_called()
                bridge.assert_not_called()
                self.assertFalse((self.root / "new-output").exists())

    def test_post_run_drift_overwrites_preliminary_pass_and_preserves_failed_summary(self):
        directory = self.prepared / "atoms3r/encoder"
        files = directory / "files"
        files.mkdir(parents=True)
        (files / "main.py").write_text("# guest fixture; never executed\n")
        image = directory / "uiflow2-ui-test.bin"
        image.write_bytes(b"image fixture; never executed")
        record = {"device_id": "atoms3r", "unit_id": "encoder", "status": "PREPARED_NOT_EXECUTED", "runtime": "qemu",
                  "attachments": [], "firmware_sha256": digest(image.read_bytes()),
                  "prepared_file_sha256": {"main.py": digest((files / "main.py").read_bytes())},
                  "probe_sha256": {"main.py": digest((files / "main.py").read_bytes())}}
        (directory / "prepared.json").write_text(json.dumps(record))
        self.report.update(schema_version=1, status="PREPARED_NOT_EXECUTED", case_count=1, cases=[record],
                           selection={"devices": ["atoms3r"], "cases": ["encoder"]})
        (self.prepared / "readiness.json").write_text(json.dumps(self.report))
        for name in ("source-before.json", "source-dependencies.json", "toolchain-before.json"):
            (self.prepared / name).write_text("{}\n")
        execution_source = self.root / "execution-only.py"
        for kind, expected_check, expected_error in (
            ("missing-execution-source", "frozen_execution_sources_unchanged", "execution_source_error"),
            ("changed-preparation-source", "preparation_sources_still_exact", "source_error"),
        ):
            with self.subTest(fault=kind):
                execution_source.write_text("# frozen before mocked execution\n")
                output = self.root / ".work" / kind
                profile = self.root / "platform/units/runtime-profiles.json"
                original_profile = profile.read_bytes()

                def simulated_run(_args, row, _prepared, destination):
                    result = {"status": "PASS", "checks": {}, "device_id": row["device_id"], "unit_id": row["unit_id"]}
                    target = destination / row["device_id"] / row["unit_id"]
                    target.mkdir(parents=True)
                    (target / "report.json").write_text(json.dumps(result))
                    if kind == "missing-execution-source":
                        execution_source.unlink()
                    else:
                        profile.write_bytes(original_profile + b"# changed during mocked execution\n")
                    return result

                argv = ["run_host_control_cases.py", "--prepared-dir", str(self.prepared), "--device", "atoms3r",
                        "--case", "encoder", "--execute", "--out-dir", str(output), "--expected-runtime-sha256", "a" * 64]
                try:
                    with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()), \
                         patch.dict(runner.os.environ, {"M5_UNIT_WEB_BRIDGE": "0"}), \
                         patch.object(runner, "toolchain_preflight", return_value=({}, {})), \
                         patch.object(runner, "full_vfs"), patch.object(runner, "display_contract"), \
                         patch.object(runner, "UnitRegistry"), patch.object(runner, "DeadlineBridge") as bridge, \
                         patch.object(runner, "Client") as client, \
                         patch.object(runner, "execution_sources", return_value=[execution_source]), \
                         patch.object(runner, "run_one", side_effect=simulated_run):
                        client.return_value.json.return_value = {"capacity": {"active_sessions": 0}}
                        self.assertEqual(runner.main(), 1)
                    bridge.assert_not_called()
                    result = json.loads((output / "atoms3r/encoder/report.json").read_bytes())
                    self.assertEqual(result["status"], "FAIL")
                    self.assertIs(result["checks"][expected_check], False)
                    self.assertTrue(result[expected_error])
                    self.assertEqual(json.loads((output / "summary.json").read_bytes()), [result])
                finally:
                    profile.write_bytes(original_profile)


class PreparationSourceContractTests(unittest.TestCase):
    def test_dynamic_source_inventory_includes_current_product_and_packaging_dependencies(self):
        paths, metadata = preparation.source_paths()
        names = {path.relative_to(preparation.ROOT).as_posix() for path in paths}
        expected = runner.REQUIRED_PREPARATION | {
            "tests/units/prepare_host_controls.py", "tests/units/run_host_control_cases.py",
            "tests/units/test_host_control_preparation.py", "tests/uiflow2/device_matrix.json",
            "platform/units/runtime-profiles.json", "platform/units/host-ports.json", "platform/units/catalog.json",
            "tests/units/host_controls_probe/font-source.json", "tests/units/host_controls_probe/host_control_program.py",
            "tests/units/host_controls_probe/host_control_layout.py", "platform/tests/unit_web_bridge.mjs",
            "tests/units/controls_probe/control_drivers/source-manifest.json",
        }
        self.assertTrue(expected <= names, sorted(expected - names))
        self.assertFalse(any(name.startswith(".work/") for name in names))
        self.assertIn("tests/uiflow2/lib/rtc_probe.py", metadata["common_guest_sources"])

    def test_official_driver_bytes_match_their_committed_provenance(self):
        directory = preparation.ROOT / "tests/units/controls_probe/control_drivers"
        manifest = json.loads((directory / "source-manifest.json").read_bytes())
        self.assertTrue(manifest)
        for name, record in manifest.items():
            with self.subTest(driver=name):
                self.assertEqual(digest((directory / name).read_bytes()), record["sha256"])

    def test_host_guest_keeps_original_control_initialization_and_sampling_semantics(self):
        original = (preparation.ROOT / "tests/units/controls_probe/main.py").read_text()
        host = (preparation.PROBE / "host_control_program.py").read_text()
        self.assertEqual(preparation.protocol_ast(original), preparation.protocol_ast(host))
        changed = host.replace("unit.get_x_raw()", "unit.get_y_raw()", 1)
        self.assertNotEqual(host, changed)
        self.assertNotEqual(preparation.protocol_ast(original), preparation.protocol_ast(changed))

    def test_reference_layout_uses_actual_partition_table_and_rejects_bad_layouts(self):
        def partition(label, offset, size, subtype=0x81):
            return struct.pack("<HBBII16sI", 0x50AA, 1, subtype, offset, size, label.encode().ljust(16, b"\0"), 0)
        with tempfile.TemporaryDirectory(prefix="m5-control-partition-") as temporary:
            image = Path(temporary) / "reference.bin"
            for entries, expected_error in (
                ([partition("vfs", 0x10000, 0x2000)], None),
                ([partition("vfs", 0x10000, 0x2000), partition("vfs", 0x14000, 0x2000)], "exactly one"),
                ([partition("vfs", 0x10001, 0x2000)], "unaligned"),
                ([partition("vfs", 0x10000, 0x2000), partition("other", 0x11000, 0x2000, 2)], "overlaps"),
                ([partition("vfs", 0x1F000, 0x2000)], "invalid reference"),
            ):
                with self.subTest(error=expected_error):
                    raw = bytearray(b"\xff" * 0x9000)
                    table = b"".join(entries) + b"\xff" * 32
                    raw[0x8000:0x8000 + len(table)] = table
                    image.write_bytes(raw)
                    if expected_error:
                        with self.assertRaisesRegex((AssertionError, RuntimeError), expected_error):
                            preparation.reference_layout(image, 0x20000)
                    else:
                        layout = preparation.reference_layout(image, 0x20000)
                        self.assertEqual((layout["offset"], layout["size"]), (0x10000, 0x2000))
                        self.assertEqual(layout["base_firmware_sha256"], digest(raw))


class PreparedSelectionTests(unittest.TestCase):
    def readiness(self, devices=runner.DEVICES, cases=runner.CASES):
        rows = [{"device_id": device, "unit_id": case, "status": "PREPARED_NOT_EXECUTED", "runtime": "qemu"}
                for device in devices for case in cases]
        return {"schema_version": 1, "status": "PREPARED_NOT_EXECUTED", "case_count": len(rows),
                "selection": {"devices": list(devices), "cases": list(cases)}, "cases": rows}

    def test_exact_full_selection_and_explicit_subset_are_accepted(self):
        readiness = self.readiness()
        self.assertEqual(len(runner.select_cases(readiness)), 15)
        selected = runner.select_cases(readiness, "sticks3", "cardkb")
        self.assertEqual([(row["device_id"], row["unit_id"]) for row in selected], [("sticks3", "cardkb")])

    def test_missing_duplicate_or_unexpected_case_is_rejected_even_with_rehashed_count(self):
        original = self.readiness()
        missing, duplicate, unexpected = (deepcopy(original) for _ in range(3))
        missing["cases"].pop()
        duplicate["cases"][-1] = deepcopy(duplicate["cases"][0])
        unexpected["cases"][-1]["unit_id"] = "button"
        for readiness in (missing, duplicate, unexpected):
            with self.subTest(case_pairs=[(row["device_id"], row["unit_id"]) for row in readiness["cases"]]):
                readiness["case_count"] = len(readiness["cases"])
                with self.assertRaisesRegex(AssertionError, "selection has missing, duplicate or unexpected"):
                    runner.select_cases(readiness)

    def test_partial_preparation_cannot_satisfy_default_all_request(self):
        readiness = self.readiness(("atoms3r",), ("encoder",))
        self.assertEqual(len(runner.select_cases(readiness, "atoms3r", "encoder")), 1)
        with self.assertRaisesRegex(AssertionError, "not completely prepared"):
            runner.select_cases(readiness)

    def test_incomplete_schema_case_count_and_historical_pass_are_rejected(self):
        for location, key, value in (("root", "schema_version", 2), ("root", "status", "PASS"),
                                     ("root", "case_count", True), ("case", "status", "PASS"),
                                     ("case", "runtime", "network")):
            with self.subTest(location=location, field=key, value=value):
                readiness = self.readiness()
                (readiness if location == "root" else readiness["cases"][0])[key] = value
                with self.assertRaises(AssertionError):
                    runner.select_cases(readiness)


class PreparedFilesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="m5-host-control-files-")
        self.addCleanup(temporary.cleanup)
        self.prepared = Path(temporary.name)
        self.directory = self.prepared / "atoms3r/encoder"
        self.files = self.directory / "files"
        self.files.mkdir(parents=True)
        (self.files / "main.py").write_text("# prepared guest\n")
        (self.files / "font-source.json").write_text('{"source":"official"}\n')
        self.image = self.directory / "uiflow2-ui-test.bin"
        self.image.write_bytes(b"image fixture; never executed")
        self.record = {"device_id": "atoms3r", "unit_id": "encoder",
                       "firmware_sha256": digest(self.image.read_bytes()),
                       "prepared_file_sha256": {path.name: digest(path.read_bytes()) for path in self.files.iterdir()},
                       "probe_sha256": {"main.py": digest((self.files / "main.py").read_bytes())}}
        self.commit_record()

    def commit_record(self):
        (self.directory / "prepared.json").write_text(json.dumps(self.record))

    def test_exact_tree_and_image_are_accepted_without_littlefs(self):
        self.assertEqual(runner.validate_prepared_files(self.prepared, self.record), self.image)

    def test_changed_nonpython_file_is_rejected(self):
        (self.files / "font-source.json").write_text('{"source":"changed"}\n')
        with self.assertRaisesRegex(AssertionError, "file tree changed"):
            runner.validate_prepared_files(self.prepared, self.record)

    def test_missing_or_added_guest_file_is_rejected(self):
        original = (self.files / "main.py").read_bytes()
        (self.files / "main.py").unlink()
        with self.assertRaisesRegex(AssertionError, "file tree changed"):
            runner.validate_prepared_files(self.prepared, self.record)
        (self.files / "main.py").write_bytes(original)
        (self.files / "extra.dat").write_bytes(b"unexpected non-Python member")
        with self.assertRaisesRegex(AssertionError, "file tree changed"):
            runner.validate_prepared_files(self.prepared, self.record)

    def test_image_or_case_metadata_drift_is_rejected(self):
        self.image.write_bytes(b"changed image")
        with self.assertRaisesRegex(AssertionError, "firmware bytes differ"):
            runner.validate_prepared_files(self.prepared, self.record)
        self.record["firmware_sha256"] = digest(self.image.read_bytes())
        with self.assertRaisesRegex(AssertionError, "metadata differs from readiness"):
            runner.validate_prepared_files(self.prepared, self.record)

    def test_python_subset_and_aliased_member_are_rejected(self):
        del self.record["probe_sha256"]["main.py"]
        self.commit_record()
        with self.assertRaisesRegex(AssertionError, "Python membership/hash differs"):
            runner.validate_prepared_files(self.prepared, self.record)
        (self.files / "alias.py").symlink_to(self.files / "main.py")
        with self.assertRaisesRegex(AssertionError, "aliased"):
            runner.validate_prepared_files(self.prepared, self.record)


LITTLEFS_AVAILABLE = importlib.util.find_spec("littlefs") is not None


@unittest.skipUnless(LITTLEFS_AVAILABLE, "optional littlefs-python is required for real image packaging")
class RealImagePreparationTests(unittest.TestCase):
    def test_three_host_images_have_exact_vfs_and_unchanged_outside_bytes(self):
        matrix = json.loads((preparation.ROOT / "tests/uiflow2/device_matrix.json").read_bytes())
        devices = {row["id"]: row for row in matrix["devices"]}
        if any(not (preparation.ROOT / devices[device]["base"]).is_file() for device in runner.DEVICES):
            self.skipTest("local reference firmware assets are unavailable")
        hosts = json.loads((preparation.ROOT / "platform/units/host-ports.json").read_bytes())
        work = preparation.ROOT / ".work"
        owned_work = not work.exists()
        work.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="host-control-package-test-", dir=work) as temporary:
                output = Path(temporary)
                for device in runner.DEVICES:
                    with self.subTest(device=device):
                        record = preparation.prepare_one(output, device, "encoder", matrix, hosts, preparation.UnitRegistry())
                        self.assertEqual(record["status"], "PREPARED_NOT_EXECUTED")
                        self.assertEqual(record["guest_execution"], "NOT RUN")
                        self.assertEqual(record["web_execution"], "NOT RUN")
                        self.assertEqual(record["hardware_execution"], "NOT RUN")
                        self.assertEqual(len(record["probe_sha256"]), 17)
                        self.assertEqual(len(record["packaged_full_py_sha256"]), 18)
                        self.assertIn("rtc_probe.py", record["packaged_full_py_sha256"])
                        image = output / device / "encoder/uiflow2-ui-test.bin"
                        self.assertEqual(runner.full_vfs(image, record), record["packaged_full_py_sha256"])
                        raw, base = image.read_bytes(), (preparation.ROOT / devices[device]["base"]).read_bytes()
                        self.assertEqual(len(raw), int(devices[device]["flash_size"], 0))
                        padded = base + b"\xff" * (len(raw) - len(base))
                        start = record["reference_layout"]["offset"]
                        end = start + record["reference_layout"]["size"]
                        self.assertEqual(raw[:start], padded[:start])
                        self.assertEqual(raw[end:], padded[end:])
        finally:
            if owned_work:
                work.rmdir()


if __name__ == "__main__":
    unittest.main()
