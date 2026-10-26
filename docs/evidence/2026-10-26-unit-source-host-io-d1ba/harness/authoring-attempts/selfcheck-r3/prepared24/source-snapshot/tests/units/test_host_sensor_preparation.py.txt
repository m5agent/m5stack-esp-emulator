"""Offline host-sensor preparation/freshness gates; no service or guest runs."""
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
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import prepare_host_sensors as preparation
import run_host_sensor_cases as runner


def digest(data):
    return hashlib.sha256(data).hexdigest()


class PreparationFreshnessTests(unittest.TestCase):
    """Small real source/snapshot trees exercise the production freshness gate."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="m5-host-sensor-sources-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.prepared = self.root / "prepared"
        self.prepared.mkdir()
        self.names = sorted(runner.REQUIRED_PREPARATION | {
            "platform/units/runtime-profiles.json", "platform/units/host-ports.json",
            "platform/units/catalog.json", "tests/units/sensors_probe/sensor_drivers/tcs3472.py",
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
                     "tests/units/sensors_probe/sensor_drivers/tcs3472.py", "tests/uiflow2/esp_flash.py"):
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
        argv = ["run_host_sensor_cases.py", "--prepared-dir", str(self.prepared)]
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
                argv = ["run_host_sensor_cases.py", "--prepared-dir", str(self.root / "absent"), "--execute", *options]
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
        directory = self.prepared / "atoms3r/color"
        files = directory / "files"
        files.mkdir(parents=True)
        (files / "main.py").write_text("# guest fixture; never executed\n")
        image = directory / "uiflow2-ui-test.bin"
        image.write_bytes(b"image fixture; never executed")
        record = {"device_id": "atoms3r", "unit_id": "color", "status": "PREPARED_NOT_EXECUTED", "runtime": "qemu",
                  "attachments": [], "firmware_sha256": digest(image.read_bytes()),
                  "prepared_file_sha256": {"main.py": digest((files / "main.py").read_bytes())},
                  "probe_sha256": {"main.py": digest((files / "main.py").read_bytes())}}
        (directory / "prepared.json").write_text(json.dumps(record))
        self.report.update(schema_version=1, status="PREPARED_NOT_EXECUTED", case_count=1, cases=[record],
                           selection={"devices": ["atoms3r"], "cases": ["color"]}, protocol_audit={}, toolchain={})
        (self.prepared / "readiness.json").write_text(json.dumps(self.report))
        for name in ("source-dependencies.json", "toolchain-before.json", "protocol-audit.json"):
            (self.prepared / name).write_text("{}\n")
        (self.prepared / "source-before.json").write_text(json.dumps(self.report["source_sha256"]))
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

                argv = ["run_host_sensor_cases.py", "--prepared-dir", str(self.prepared), "--device", "atoms3r",
                        "--case", "color", "--execute", "--out-dir", str(output), "--expected-runtime-sha256", "a" * 64]
                try:
                    with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()), \
                         patch.dict(runner.os.environ, {"M5_UNIT_WEB_BRIDGE": "0"}), \
                         patch.object(runner, "toolchain_preflight", return_value=({}, {})), \
                         patch.object(runner, "full_vfs"), patch.object(runner, "display_contract"), \
                         patch.object(runner, "verify_reference_image"), \
                         patch.object(preparation, "protocol_audit", return_value=({}, "", "")), \
                         patch.object(runner, "UnitRegistry"), patch.object(runner, "DeadlineBridge") as bridge, \
                         patch.object(runner, "Client") as client, \
                         patch.object(runner, "execution_sources", return_value=[execution_source]), \
                         patch.object(runner, "run_one", side_effect=simulated_run):
                        client.return_value.json.return_value = {"capacity": {"active_sessions": 0}}
                        self.assertEqual(runner.main(), 1)
                    bridge.assert_not_called()
                    result = json.loads((output / "atoms3r/color/report.json").read_bytes())
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
            "tests/units/prepare_host_sensors.py", "tests/units/run_host_sensor_cases.py",
            "tests/units/test_host_sensor_preparation.py", "tests/uiflow2/device_matrix.json",
            "platform/units/runtime-profiles.json", "platform/units/host-ports.json", "platform/units/catalog.json",
            "tests/units/host_sensors_probe/font-source.json", "tests/units/host_sensors_probe/sensor_probe.py",
            "tests/units/host_sensors_probe/host_sensor_layout.py", "platform/tests/unit_web_bridge.mjs",
            "tests/units/sensors_probe/sensor_drivers/source-manifest.json",
        }
        self.assertTrue(expected <= names, sorted(expected - names))
        self.assertFalse(any(name.startswith(".work/") for name in names))
        self.assertIn("tests/uiflow2/lib/rtc_probe.py", metadata["shared_current_dependencies"]["common_guest_sources"])

    def test_official_driver_bytes_match_their_committed_provenance(self):
        directory = preparation.ROOT / "tests/units/sensors_probe/sensor_drivers"
        manifest = json.loads((directory / "source-manifest.json").read_bytes())
        self.assertTrue(manifest)
        for name, record in manifest.items():
            with self.subTest(driver=name):
                self.assertEqual(digest((directory / name).read_bytes()), record["sha256"])

    def test_host_guest_keeps_original_sensor_helpers_init_negatives_and_sampling_bytes(self):
        audit, original, host = preparation.protocol_audit()
        self.assertEqual(audit['official_driver_count'], 9)
        self.assertEqual(len(audit['original_helpers_and_protocol_segments']), 10)
        self.assertNotEqual(original, host)
        with tempfile.TemporaryDirectory(prefix='m5-host-sensor-protocol-') as temporary:
            guest = Path(temporary)
            for path in preparation.GUEST.glob('*.py'):
                (guest / path.name).write_bytes(path.read_bytes())
            probe = guest / 'sensor_probe.py'
            probe.write_text(host.replace('unit.get_color_raw()', 'unit.get_color_changed()', 1))
            with patch.object(preparation, 'GUEST', guest):
                with self.assertRaises(AssertionError):
                    preparation.protocol_audit()

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
        self.assertEqual(len(runner.select_cases(readiness)), 18)
        selected = runner.select_cases(readiness, "sticks3", "tvoc")
        self.assertEqual([(row["device_id"], row["unit_id"]) for row in selected], [("sticks3", "tvoc")])

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
        readiness = self.readiness(("atoms3r",), ("color",))
        self.assertEqual(len(runner.select_cases(readiness, "atoms3r", "color")), 1)
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
        temporary = tempfile.TemporaryDirectory(prefix="m5-host-sensor-files-")
        self.addCleanup(temporary.cleanup)
        self.prepared = Path(temporary.name)
        self.directory = self.prepared / "atoms3r/color"
        self.files = self.directory / "files"
        self.files.mkdir(parents=True)
        (self.files / "main.py").write_text("# prepared guest\n")
        (self.files / "font-source.json").write_text('{"source":"official"}\n')
        self.image = self.directory / "uiflow2-ui-test.bin"
        self.image.write_bytes(b"image fixture; never executed")
        self.record = {"device_id": "atoms3r", "unit_id": "color",
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

    def test_cli_config_or_image_drift_fails_before_any_api(self):
        config = self.files / 'probe_config.py'
        config.write_text('CASE = "color"\nINTERNAL_CONTROLLER = 1\n')
        self.record.update(status='PREPARED_NOT_EXECUTED', runtime='qemu', attachments=[])
        self.record['prepared_file_sha256']['probe_config.py'] = digest(config.read_bytes())
        self.record['probe_sha256']['probe_config.py'] = digest(config.read_bytes())
        self.commit_record()
        readiness = {'schema_version': 1, 'status': 'PREPARED_NOT_EXECUTED', 'case_count': 1,
                     'selection': {'devices': ['atoms3r'], 'cases': ['color']}, 'cases': [self.record],
                     'source_sha256': {}, 'toolchain': {}, 'protocol_audit': {}}
        for name, data in (('readiness.json', readiness), ('source-before.json', {}),
                           ('source-dependencies.json', {}), ('toolchain-before.json', {}), ('protocol-audit.json', {})):
            (self.prepared / name).write_text(json.dumps(data))
        for fault in ('config', 'image'):
            target = config if fault == 'config' else self.image
            original = target.read_bytes()
            target.write_bytes(original + b'# changed after preparation\n')
            try:
                with self.subTest(fault=fault), ExitStack() as stack:
                    stack.enter_context(patch.object(sys, 'argv', ['run_host_sensor_cases.py', '--prepared-dir',
                        str(self.prepared), '--device', 'atoms3r', '--case', 'color', '--execute',
                        '--out-dir', str(self.prepared / 'must-not-exist'), '--expected-runtime-sha256', 'a' * 64]))
                    stack.enter_context(patch.object(runner, 'preparation_continuity', return_value={'status': 'EXACT_CURRENT_SOURCE_MATCH'}))
                    stack.enter_context(patch.object(runner, 'toolchain_preflight', return_value=({}, {})))
                    stack.enter_context(patch.object(preparation, 'source_paths', return_value=([], {})))
                    stack.enter_context(patch.object(preparation, 'protocol_audit', return_value=({}, '', '')))
                    client = stack.enter_context(patch.object(runner, 'Client'))
                    bridge = stack.enter_context(patch.object(runner, 'DeadlineBridge'))
                    with self.assertRaisesRegex(AssertionError, 'file tree changed|firmware bytes differ'):
                        runner.main()
                    client.assert_not_called()
                    bridge.assert_not_called()
                    self.assertFalse((self.prepared / 'must-not-exist').exists())
            finally:
                target.write_bytes(original)


class ExecutionBoundaryTests(unittest.TestCase):
    def test_sensor_modules_have_private_preparation_globals_and_original_execution_code(self):
        import run_sensor_cases as shared
        original_probe, original_builder = shared.PROBE, shared.build_control_image
        first, second = runner.load_sensor_runner(), runner.load_sensor_runner()
        first.PROBE = Path('/offline-test-private-source')
        first.build_control_image = object()
        self.assertEqual(shared.PROBE, original_probe)
        self.assertIs(shared.build_control_image, original_builder)
        self.assertEqual(second.PROBE, original_probe)
        self.assertIs(second.build_control_image, original_builder)
        self.assertEqual(first.run_case.__code__.co_code, shared.run_case.__code__.co_code)
        self.assertIs(first.run_case.__globals__, first.__dict__)

    def test_toolchain_drift_is_rejected_before_service_construction(self):
        with patch.object(preparation, 'freeze_toolchain', return_value=({}, {'changed': True})), \
             patch.object(runner, 'Client') as client, patch.object(runner, 'DeadlineBridge') as bridge:
            with self.assertRaisesRegex(AssertionError, 'toolchain changed'):
                runner.toolchain_preflight({'toolchain': {'changed': False}})
        client.assert_not_called()
        bridge.assert_not_called()

    def test_default_cli_and_blocked_execute_contact_no_api_or_child_process(self):
        # This negative is independent of the production admission inventory.
        # Remove only this fixture's host grant, retaining real valid wiring so
        # an accidental admission cannot be hidden by an invalid port error.
        blocked_registry = preparation.UnitRegistry()
        blocked_registry.profiles = deepcopy(blocked_registry.profiles)
        blocked_registry.profiles['color']['hosts'] = [host for host in
            blocked_registry.profiles['color']['hosts'] if host != 'atoms3r']
        port = next(port for port in blocked_registry.hosts['atoms3r']['ports']
                    if port.get('visual_port') == 'grove' and port.get('wiring_status') == 'confirmed'
                    and port.get('physical_presence') == 'main-device')
        readiness = PreparedSelectionTests().readiness(('atoms3r',), ('color',))
        row = readiness['cases'][0]
        row['attachments'] = [{'id': 'external1', 'unit_id': 'color', 'port_id': port['id'],
                               'initial': preparation.SENSOR_CASES['color']['initial']}]
        with self.assertRaises(preparation.UnitError) as rejected:
            blocked_registry.attachments('atoms3r', 'qemu', row['attachments'])
        self.assertEqual((rejected.exception.code, rejected.exception.status), ('runtime_model_gap', 409))
        readiness.update(source_sha256={}, toolchain={}, protocol_audit={})
        with tempfile.TemporaryDirectory(prefix='m5-host-sensor-cli-') as temporary:
            prepared = Path(temporary)
            for name, data in (('readiness.json', readiness), ('source-before.json', {}),
                               ('source-dependencies.json', {}), ('toolchain-before.json', {}), ('protocol-audit.json', {})):
                (prepared / name).write_text(json.dumps(data))
            for execute in (False, True):
                with self.subTest(execute=execute), ExitStack() as stack:
                    argv = ['run_host_sensor_cases.py', '--prepared-dir', str(prepared),
                            '--device', 'atoms3r', '--case', 'color']
                    if execute:
                        argv += ['--execute', '--out-dir', str(prepared / 'must-not-exist'),
                                 '--expected-runtime-sha256', 'a' * 64]
                    stack.enter_context(patch.object(sys, 'argv', argv))
                    stack.enter_context(patch.object(runner, 'preparation_continuity', return_value={'status': 'EXACT_CURRENT_SOURCE_MATCH'}))
                    stack.enter_context(patch.object(runner, 'toolchain_preflight', return_value=({}, {})))
                    stack.enter_context(patch.object(preparation, 'source_paths', return_value=([], {})))
                    stack.enter_context(patch.object(preparation, 'protocol_audit', return_value=({}, '', '')))
                    stack.enter_context(patch.object(runner, 'validate_prepared_files'))
                    stack.enter_context(patch.object(runner, 'full_vfs'))
                    stack.enter_context(patch.object(runner, 'verify_reference_image'))
                    stack.enter_context(patch.object(runner, 'display_contract'))
                    stack.enter_context(patch.object(runner, 'UnitRegistry', return_value=blocked_registry))
                    client = stack.enter_context(patch.object(runner, 'Client'))
                    bridge = stack.enter_context(patch.object(runner, 'DeadlineBridge'))
                    http = stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('unexpected HTTP')))
                    socket = stack.enter_context(patch('socket.socket.connect', side_effect=AssertionError('unexpected socket')))
                    child = stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('unexpected process')))
                    output = stack.enter_context(redirect_stdout(io.StringIO()))
                    if execute:
                        with self.assertRaisesRegex(AssertionError, 'not admitted'):
                            runner.main()
                    else:
                        self.assertEqual(runner.main(), 0)
                        report = json.loads(output.getvalue())
                        self.assertIs(report['api_contacted'], False)
                        self.assertEqual(report['sessions_started'], 0)
                        self.assertEqual(report['blocked_admission'][0]['code'], 'runtime_model_gap')
                    for guard in (client, bridge, http, socket, child):
                        guard.assert_not_called()
                    self.assertFalse((prepared / 'must-not-exist').exists())


class SensorWiringAdmissionTests(unittest.TestCase):
    def test_six_sensors_use_only_confirmed_main_device_grove_wiring(self):
        registry = preparation.UnitRegistry()
        expected = {'atoms3r': {'yellow': 2, 'white': 1}, 'sticks3': {'yellow': 9, 'white': 10},
                    'stopwatch': {'yellow': 10, 'white': 11}}
        for case in runner.CASES:
            self.assertEqual(registry.profiles[case]['status'], 'implemented')
            self.assertEqual(set(registry.profiles[case]['hosts']), {'cores3', *runner.DEVICES})
            for host in runner.DEVICES:
                with self.subTest(unit=case, device=host):
                    ports = [port for port in registry.hosts[host]['ports'] if port.get('visual_port') == 'grove'
                             and port.get('wiring_status') == 'confirmed' and port.get('physical_presence') == 'main-device']
                    self.assertEqual(len(ports), 1)
                    attachment = {'id': 'external1', 'unit_id': case, 'port_id': ports[0]['id'],
                                  'initial': preparation.SENSOR_CASES[case]['initial']}
                    resolved = registry.attachments(host, 'qemu', [attachment])
                    self.assertEqual(len(resolved), 1)
                    self.assertEqual(resolved[0]['pins'], expected[host])
                    self.assertEqual(resolved[0]['initial'], attachment['initial'])
                    self.assertEqual(resolved[0]['visual_port'], 'grove')
                    profile = preparation.HOSTS[host]
                    self.assertFalse(set(expected[host].values()) & {profile['internal_sda'], profile['internal_scl'], 43, 44})
                    # A wiring resolution does not contain execution evidence.
                    self.assertNotIn('status', resolved[0])
                    self.assertNotIn('available', resolved[0])
                    self.assertNotIn('source', resolved[0])

    def test_other_registered_hosts_remain_unadmitted_and_unknown_hosts_fail_closed(self):
        registry = preparation.UnitRegistry()
        for case in runner.CASES:
            for host, port, code in (('core2', 'port-a', 'runtime_model_gap'),
                                     ('cardputer-adv', 'custom', 'runtime_model_gap'),
                                     ('unregistered-test-host', 'custom', 'units_not_supported')):
                with self.subTest(unit=case, device=host):
                    with self.assertRaises(preparation.UnitError) as rejected:
                        registry.attachments(host, 'qemu', [{'id': 'external1', 'unit_id': case, 'port_id': port}])
                    self.assertEqual((rejected.exception.code, rejected.exception.status), (code, 409))

    def test_admitted_hosts_reject_unknown_ports_unattached_accessories_and_other_runtimes(self):
        registry = preparation.UnitRegistry()
        for case in runner.CASES:
            for host, port, runtime, code in (
                ('atoms3r', 'port-a', 'qemu', 'unit_port_not_supported'),
                ('sticks3', 'missing-test-port', 'qemu', 'unit_port_not_supported'),
                ('stopwatch', 'custom', 'qemu', 'unit_port_not_supported'),
                ('cores3', 'port-b', 'qemu', 'unit_port_not_supported'),
                ('cores3', 'port-c', 'qemu', 'unit_port_not_supported'),
                ('atoms3r', 'custom', 'network', 'units_not_supported'),
            ):
                with self.subTest(unit=case, device=host, port=port, runtime=runtime):
                    with self.assertRaises(preparation.UnitError) as rejected:
                        registry.attachments(host, runtime, [{'id': 'external1', 'unit_id': case, 'port_id': port}])
                    self.assertEqual((rejected.exception.code, rejected.exception.status), (code, 409))


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
            with tempfile.TemporaryDirectory(prefix="host-sensor-package-test-", dir=work) as temporary:
                output = Path(temporary)
                for device in runner.DEVICES:
                    with self.subTest(device=device):
                        record = preparation.prepare_one(output, device, "color", matrix, hosts, preparation.UnitRegistry())
                        self.assertEqual(record["status"], "PREPARED_NOT_EXECUTED")
                        self.assertEqual(record["guest_execution"], "NOT RUN")
                        self.assertEqual(record["web_execution"], "NOT RUN")
                        self.assertEqual(record["hardware_execution"], "NOT RUN")
                        self.assertEqual(len(record["probe_sha256"]), 16)
                        self.assertEqual(len(record["packaged_full_py_sha256"]), 17)
                        self.assertIn("rtc_probe.py", record["packaged_full_py_sha256"])
                        image = output / device / "color/uiflow2-ui-test.bin"
                        self.assertEqual(runner.full_vfs(image, record), record["packaged_full_py_sha256"])
                        raw, base = image.read_bytes(), (preparation.ROOT / devices[device]["base"]).read_bytes()
                        self.assertEqual(len(raw), int(devices[device]["flash_size"], 0))
                        padded = base + b"\xff" * (len(raw) - len(base))
                        start = record["reference_layout"]["offset"]
                        end = start + record["reference_layout"]["size"]
                        self.assertEqual(raw[:start], padded[:start])
                        self.assertEqual(raw[end:], padded[end:])
                        self.assertEqual(record['admission'], {'status': 'ADMITTED', 'validation': 'NOT RUN'})
                        runner.verify_reference_image(image, record)
                        runner.display_contract(record)
                        # Execute only the original preparation boundary against
                        # a fake client that refuses upload. No guest/API starts.
                        execution = output / 'adapter' / device
                        sensor, adapter = runner.sensor_adapter(output, record, execution)
                        host = next(row for row in hosts['hosts'] if row['device_id'] == device)
                        class OfflineClient:
                            def json(self, path, **_options):
                                if path == 'units?device_id=' + device:
                                    return {'hosts': [host]}
                                raise RuntimeError('offline upload sentinel')
                        with redirect_stdout(io.StringIO()):
                            result = sensor.run_case(OfflineClient(), SimpleNamespace(device=device,
                                out_dir=execution / 'controller', base=None, build_only=False,
                                thermal_no_fixture=False), 'color')
                        self.assertEqual(result['status'], 'FAIL')
                        self.assertIn('offline upload sentinel', result['error'])
                        adapter.bind_result(result)
                        self.assertEqual(adapter.report['status'], 'VERIFIED')
                        self.assertNotEqual(result['probe_sha256']['probe_config.py'], record['probe_sha256']['probe_config.py'])
                        self.assertEqual(result['packaged_python_sha256'], record['probe_sha256'])
                        self.assertEqual(adapter.report['restored_probe_sha256'], record['probe_sha256'])
                        # A rehashed config drift must fail against current
                        # host wiring, even if tree/image metadata is rewritten.
                        config = image.parent / 'files/probe_config.py'
                        original_config = config.read_bytes()
                        config.write_bytes(original_config.replace(b'INTERNAL_CONTROLLER = 1', b'INTERNAL_CONTROLLER = 0'))
                        with self.assertRaisesRegex(AssertionError, 'configuration differs'):
                            runner.verify_reference_image(image, record)
                        config.write_bytes(original_config)
                        # Add a non-Python VFS member and recompute image SHA:
                        # the complete whitelist must still reject it.
                        import littlefs
                        original_image = image.read_bytes()
                        size = record['reference_layout']['size']
                        filesystem = littlefs.LittleFS(context=littlefs.UserContext(buffer=bytearray(original_image[start:end])),
                            block_size=4096, block_count=size // 4096, read_size=128, prog_size=32,
                            lookahead_size=128, block_cycles=100, mount=False)
                        filesystem.mount()
                        with filesystem.open('/unexpected.dat', 'wb') as stream:
                            stream.write(b'unknown non-Python member')
                        filesystem.unmount()
                        mutated = original_image[:start] + bytes(filesystem.context.buffer) + original_image[end:]
                        image.write_bytes(mutated)
                        changed = deepcopy(record)
                        changed['firmware_sha256'] = digest(mutated)
                        with self.assertRaisesRegex(AssertionError, 'VFS contains'):
                            runner.full_vfs(image, changed)
                        changed['packaged_full_py_sha256']['unexpected.dat'] = digest(b'unknown non-Python member')
                        with self.assertRaisesRegex(AssertionError, 'whitelist differs'):
                            runner.full_vfs(image, changed)
                        image.write_bytes(original_image)
        finally:
            if owned_work:
                work.rmdir()


if __name__ == "__main__":
    unittest.main()
