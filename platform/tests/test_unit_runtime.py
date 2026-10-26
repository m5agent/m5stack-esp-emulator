from __future__ import annotations

import copy
import hashlib
import json
import math
import unittest
import zipfile

from unit_runtime import UnitError, UnitRegistry, scalar_value
from _unit_host_control_evidence import CONTROL_WEB_CONTRACT, verify_control_web_evidence
from _unit_host_sensor_evidence import SENSOR_WEB_CONTRACT, verify_sensor_web_evidence


class UnitRuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.registry = UnitRegistry()

    def test_full_visual_batch_has_explicit_runtime_boundaries(self):
        inventory = self.registry.inventory()
        self.assertEqual(len(inventory["units"]), 30)
        self.assertEqual(len(inventory["hosts"]), 14)
        for unit in inventory["units"]:
            self.assertIsInstance(unit["inputs"], dict)
            self.assertIsInstance(unit["outputs"], dict)
            self.assertEqual(unit["model_status"], unit["runtime"]["status"])
            self.assertEqual(unit["blocker"], unit["runtime"].get("blocker", ""))
            self.assertEqual(unit["research_snapshot"]["model_status"],
                             self.registry.units[unit["id"]].get("model_status"))
            if unit["runtime"]["status"] != "validated":
                self.assertTrue(unit["runtime"].get("blocker"), unit["id"])

    def test_unknown_and_unimplemented_units_cannot_create_fake_attachments(self):
        with self.assertRaises(UnitError) as caught:
            self.registry.attachments("cores3", "qemu", [{
                "id": "external", "unit_id": "not-a-product", "port_id": "port-a",
            }])
        self.assertEqual(caught.exception.code, "unknown_unit")
        self.registry.profiles["pir"]["status"] = "planned"
        with self.assertRaises(UnitError) as caught:
            self.registry.attachments("cores3", "qemu", [{
                "id": "external", "unit_id": "pir", "port_id": "port-a",
            }])
        self.assertEqual(caught.exception.code, "runtime_model_gap")

    def test_scroll_physical_source_is_distinct_from_read_only_logical_counter(self):
        unit = self.registry.unit("scroll")
        self.assertEqual(unit["interface"]["address_7bit"], [0x40])
        self.assertEqual(self.registry.input_values("scroll", {"source-count": -32768, "pressed": True}),
                         {"source-count": -32768, "pressed": True})
        self.assertEqual(self.registry.input_values("scroll", {"source-count": 32767}), {"source-count": 32767})
        for values in ({"source-count": -32769}, {"source-count": 32768}, {"source-count": True},
                       {"counter": 1}, {"increments": 1}, {"led-rgb": 0x123456}, {"ab-direction": 1}):
            with self.subTest(values=values), self.assertRaises(UnitError):
                self.registry.input_values("scroll", values)
        frozen = self.registry.freeze(["scroll"])
        self.assertEqual(frozen["profiles"]["scroll"]["state"]["counter"], {"property": "counter"})
        self.assertEqual(frozen["units"]["scroll"]["outputs"]["counter"]["minimum"], -(2**31))

    def test_scroll_program_evidence_binds_each_host_without_inheriting_web_pass(self):
        import sys
        from unittest import mock

        root = self.registry.root.parents[1]
        with mock.patch.object(sys, 'path', [str(root / 'tests/units'), *sys.path]):
            from run_live_scroll import validate_bundle
        profile = self.registry.profiles['scroll']
        self.assertEqual(profile['model_completeness'], 'partial')
        self.assertNotIn('host_validation', profile)  # Existing full host/Web contract is distinct.
        self.assertEqual(set(profile['program_validation']), {'cores3', 'atoms3r', 'sticks3', 'stopwatch'})
        for host, validation in profile['program_validation'].items():
            with self.subTest(host=host):
                self.assertEqual(validation['evidence_contract'], 'same-guest-scroll-protocol-v1')
                self.assertEqual(validation['hardware'], 'NOT RUN')
                self.assertEqual(validation['live_browser'], 'PASS' if host == 'cores3' else 'NOT RUN')
                path = root / validation['report']
                raw = path.read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), validation['report_sha256'])
                report = json.loads(raw)
                self.assertEqual(report['status'], 'PASS')
                for key in ('device_id', 'runtime', 'session_id', 'firmware_sha256'):
                    self.assertEqual(report[key], validation[key])
                self.assertEqual(report['device_id'], host)
                self.assertEqual(len(report['executions']), 22)
                self.assertEqual(report['worker']['generation'], validation['worker_generation'])
                for key in ('runtime_provenance', 'final_runtime_provenance'):
                    proof = report[key]
                    self.assertEqual((proof['status'], proof['method'], proof['pid']),
                                     ('PASS', validation['runtime_proof_kind'], report['pid']))
                    self.assertEqual(proof['session_id'], report['session_id'])
                    self.assertEqual(proof['expected_binary_sha256'], validation['runtime_binary_sha256'])
                    self.assertEqual(proof['observed_binary_sha256'], validation['runtime_binary_sha256'])
                data = (path.parent / 'evidence.zip').read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), validation['evidence_sha256'])
                with zipfile.ZipFile(path.parent / 'evidence.zip') as archive:
                    submitted = {name: json.loads(archive.read('programs/' + execution['program']['revision_id'] + '/source.json'))['files']['main.py']
                                 for name, execution in report['executions'].items()}
                validate_bundle(data, report, submitted)
                self.assertEqual(report['cleanup'], {'history_retained': True, 'flash_retained': False, 'last_frame_available': True})
                if host == 'cores3':
                    web_raw = (root / validation['live_browser_report']).read_bytes()
                    self.assertEqual(hashlib.sha256(web_raw).hexdigest(), validation['live_browser_report_sha256'])
                    web = json.loads(web_raw)
                    self.assertEqual((web['status'], web['device_id'], web['unit_id']), ('PASS', host, 'scroll'))
                    self.assertEqual(web['firmware_sha256'], report['firmware_sha256'])

    def test_attachment_caller_cannot_select_pins_or_qom_paths(self):
        for override in ({"pins": {"yellow": 0}}, {"qom_path": "/machine"}):
            with self.assertRaises(UnitError) as caught:
                self.registry.attachments("cores3", "qemu", [{
                    "id": "external", "unit_id": "button", "port_id": "port-a", **override,
                }])
            self.assertEqual(caught.exception.code, "invalid_units")

    def test_input_type_range_and_nonfinite_values_fail_closed(self):
        schema = {"type": "number", "minimum": -40, "maximum": 125}
        for value in (True, "24", None, math.nan, math.inf, -math.inf, 126, -41, 10**1000):
            with self.subTest(value=repr(value)[:40]), self.assertRaises(UnitError):
                scalar_value(value, schema, "temperature-c")
        self.assertEqual(scalar_value(24.5, schema, "temperature-c"), 24.5)
        with self.assertRaises(UnitError):
            scalar_value(1, {"type": "boolean"}, "pressed")

    def test_readback_is_queried_from_controller_not_echoed_initial_state(self):
        attachments = [{
            "id": "button1", "unit_id": "button", "port_id": "port-a",
            "initial": {"pressed": True},
        }]
        calls = []
        def read(path, prop):
            calls.append((path, prop))
            return {"pressed": False, "input-level": 1}.get(prop, 0)
        result = self.registry.state(attachments, read)
        self.assertIs(result[0]["properties"]["pressed"], False)
        self.assertEqual(calls, [
            ("/machine/units/button1", "pressed"),
            ("/machine/units/button1", "transactions"),
            ("/machine/units/button1", "read-bytes"),
            ("/machine/units/button1", "written-bytes"),
            ("/machine/units/button1", "input-events"),
            ("/machine/units/button1", "output-transitions"),
            ("/machine/units/button1", "input-level"),
        ])
        self.assertTrue(result[0]["available"])
        self.assertIs(attachments[0]["initial"]["pressed"], True)

    def test_qom_failure_stays_unavailable_and_preserves_reason(self):
        def read(path, prop):
            raise RuntimeError("model absent")
        result = self.registry.state([{"id": "relay1", "unit_id": "relay"}], read)
        self.assertFalse(result[0]["available"])
        self.assertEqual(result[0]["properties"], {})
        self.assertIn("model absent", result[0]["errors"]["output-level"])

    def test_confirmed_accessory_pin_table_is_not_a_mounted_connector(self):
        registry = copy.deepcopy(self.registry)
        registry.profiles["relay"].update(status="implemented", hosts=["cores3"])
        with self.assertRaises(UnitError) as caught:
            registry.attachments("cores3", "qemu", [{
                "id": "relay1", "unit_id": "relay", "port_id": "port-b",
            }])
        self.assertEqual(caught.exception.code, "unit_port_not_supported")

    def test_hub_children_share_real_pins_and_resolve_parent_first(self):
        attachments = self.registry.attachments("cores3", "qemu", [
            {"id": "env", "unit_id": "env-iii", "parent_id": "hub1", "port_id": "grove-1"},
            {"id": "ncir", "unit_id": "ncir", "parent_id": "hub1", "port_id": "grove-2"},
            {"id": "hub1", "unit_id": "hub", "port_id": "port-a"},
        ])
        self.assertEqual([row["id"] for row in attachments], ["hub1", "env", "ncir"])
        self.assertEqual(attachments[1]["pins"], attachments[0]["pins"])
        self.assertEqual(attachments[1]["visual_port"], "grove/grove-1")

    def test_hub_rejects_cycles_address_conflicts_and_gpio_contention(self):
        cases = [
            ([{"id": "hub1", "unit_id": "hub", "parent_id": "hub2", "port_id": "grove-1"},
              {"id": "hub2", "unit_id": "hub", "parent_id": "hub1", "port_id": "grove-1"}], "invalid_unit_topology"),
            ([{"id": "a", "unit_id": "ncir"}, {"id": "b", "unit_id": "ncir"}], "unit_address_conflict"),
            ([{"id": "a", "unit_id": "button"}, {"id": "b", "unit_id": "relay"}], "unit_bus_conflict"),
        ]
        for leaves, code in cases:
            if code != "invalid_unit_topology":
                leaves = [{"id": "hub1", "unit_id": "hub", "port_id": "port-a"}] + [
                    {**row, "parent_id": "hub1", "port_id": f"grove-{index + 1}"}
                    for index, row in enumerate(leaves)
                ]
            with self.subTest(code=code), self.assertRaises(UnitError) as caught:
                self.registry.attachments("cores3", "qemu", leaves)
            self.assertEqual(caught.exception.code, code)

    def test_session_contract_preserves_schema_after_catalog_changes(self):
        contract = self.registry.freeze(["button"])
        self.registry.units["button"]["inputs"]["pressed"]["type"] = "integer"
        self.registry.profiles["button"]["state"]["pressed"]["property"] = "different-model"
        frozen = UnitRegistry(contract=contract)
        self.assertEqual(frozen.input_values("button", {"pressed": True}), {"pressed": True})
        self.assertEqual(frozen.profiles["button"]["state"]["pressed"]["property"], "pressed")

    def test_adc_fixture_bytes_and_hash_are_frozen_with_the_unit_contract(self):
        contract = self.registry.freeze(["angle"])
        fixture = contract["fixtures"]["esp32s3-adc"]
        self.assertEqual(hashlib.sha256(fixture["raw_utf8"].encode()).hexdigest(), fixture["sha256"])
        self.assertEqual(contract["source_hashes"]["fixtures/esp32s3-adc-calibration.json"], fixture["sha256"])
        self.assertEqual(json.loads(fixture["raw_utf8"])["kind"], "synthetic-virtual-device-calibration")
        restored = UnitRegistry(contract=contract)
        self.assertEqual(restored.fixtures, contract["fixtures"])

    def test_host_pass_metadata_binds_exact_device_firmware_and_direct_runtime_evidence(self):
        root = self.registry.root.parents[1]

        def pinned_json(path, expected_sha256):
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_sha256, str(path))
            return json.loads(raw)

        checked = []
        for unit_id, profile in self.registry.profiles.items():
            for host_id, validation in profile.get("host_validation", {}).items():
                if validation["status"] != "PASS":
                    continue
                with self.subTest(unit=unit_id, host=host_id):
                    self.assertIn(host_id, self.registry.hosts)
                    self.assertIn(host_id, profile["hosts"])
                    self.assertEqual(validation["device_id"], host_id)
                    report_path = (root / validation["report"]).resolve()
                    report = pinned_json(report_path, validation["report_sha256"])
                    self.assertEqual(report["status"], "PASS")
                    self.assertEqual(report["unit_id"], unit_id)
                    for field in ("device_id", "runtime", "session_id", "firmware_sha256",
                                  "firmware_flavor", "evidence_sha256"):
                        self.assertEqual(report[field], validation[field], field)

                    proof = report["runtime_provenance"]
                    self.assertEqual(validation["runtime_proof_kind"], "direct-pid")
                    self.assertEqual(proof["kind"], validation["runtime_proof_kind"])
                    self.assertEqual(proof["status"], "VERIFIED")
                    for field in ("session_id", "firmware_sha256", "runtime_binary_sha256",
                                  "worker_generation"):
                        self.assertEqual(proof[field], validation[field], field)
                    self.assertIs(type(proof["observed_pid"]), int)
                    self.assertGreater(proof["observed_pid"], 0)
                    evidence_contract = validation.get("evidence_contract", "host-probe-dual-observer-v1")
                    if evidence_contract == CONTROL_WEB_CONTRACT:
                        verify_control_web_evidence(root, report_path, report, validation)
                    elif evidence_contract == SENSOR_WEB_CONTRACT:
                        verify_sensor_web_evidence(root, report_path, report, validation)
                    else:
                        self.assertEqual(evidence_contract, "host-probe-dual-observer-v1")
                        independent = report["host_runtime_provenance"]
                        self.assertEqual(independent["status"], "PASS")
                        self.assertEqual(independent["session_id"], validation["session_id"])
                        self.assertEqual(independent["pid"], proof["observed_pid"])
                        for field in ("expected_binary_sha256", "observed_binary_sha256"):
                            self.assertEqual(independent[field], validation["runtime_binary_sha256"])
                    evidence_path = (report_path.parent / report["evidence"]).resolve()
                    self.assertEqual(hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                                     validation["evidence_sha256"])
                    self.assertEqual(report["artifact_sha256"][report["evidence"]],
                                     validation["evidence_sha256"])
                    with zipfile.ZipFile(evidence_path) as archive:
                        session = json.loads(archive.read("manifest.json"))["session"]
                    for field in ("device_id", "runtime", "session_id", "firmware_sha256"):
                        self.assertEqual(session[field], validation[field], field)
                    self.assertEqual(session["state"], "running")
                    self.assertEqual(session["pid"], proof["observed_pid"])
                    self.assertEqual(session["worker"]["worker_id"], proof["worker_id"])
                    self.assertEqual(session["worker"]["generation"], validation["worker_generation"])
                    if evidence_contract == "host-probe-dual-observer-v1":
                        self.assertEqual({row["unit_id"] for row in report["attachments"]}, {unit_id})
                    self.assertEqual({row["unit_id"] for row in session["units"]}, {unit_id})

                    selection = pinned_json(root / validation["batch_selection"],
                                            validation["batch_selection_sha256"])
                    self.assertEqual(selection["device_id"], host_id)
                    self.assertEqual(selection["runtime"], validation["runtime"])
                    self.assertEqual(selection["expected_runtime_binary_sha256"],
                                     validation["runtime_binary_sha256"])
                    rows = [row for row in selection["cases"] if row["unit_id"] == unit_id]
                    self.assertEqual(len(rows), 1)
                    for layer in ("guest_controller", "live_browser"):
                        selected = rows[0][layer]
                        self.assertEqual((root / selected["report"]).resolve(), report_path)
                        self.assertEqual(selected["report_sha256"], validation["report_sha256"])
                        self.assertEqual((root / selected["evidence"]).resolve(), evidence_path)
                        self.assertEqual(selected["expected_firmware_flavor"],
                                         validation["firmware_flavor"])
                        selected_proof = selected["runtime_proof"]
                        self.assertEqual(selected_proof["kind"], "direct-pid")
                        self.assertEqual((root / selected_proof["path"]).resolve(), report_path)
                        self.assertEqual(selected_proof["report_pointer"], "/runtime_provenance")
                    checked.append((unit_id, host_id))
        self.assertTrue(checked, "no host-local PASS metadata was checked")


if __name__ == "__main__":
    unittest.main()
