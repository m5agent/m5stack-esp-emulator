from __future__ import annotations

import copy
import hashlib
import json
import math
import unittest

from unit_runtime import UnitError, UnitRegistry, scalar_value
from _unit_host_control_evidence import CONTROL_WEB_CONTRACT
from _unit_host_sensor_evidence import SENSOR_WEB_CONTRACT


class UnitRuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.registry = UnitRegistry()

    def test_full_visual_batch_has_explicit_runtime_boundaries(self):
        inventory = self.registry.inventory()
        self.assertEqual(len(inventory["units"]), 34)
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

    def test_host_filtered_inventory_exposes_actual_port_admission(self):
        cores3 = {unit["id"]: unit for unit in self.registry.inventory("cores3")["units"]}
        env = cores3["env-iii"]["host_admission"]
        self.assertTrue(env["admitted"])
        self.assertEqual(env["port_ids"], ["port-a"])
        ports = {port["port_id"]: port for port in env["ports"]}
        self.assertEqual(ports["port-b"]["error"]["code"], "unit_port_not_supported")
        self.assertIn("accessory", ports["port-c"]["error"]["message"])
        self.assertEqual(cores3["8servos"]["host_admission"]["port_ids"], ["port-a", "port-b"])
        cardputer = self.registry.inventory("cardputer-adv")
        for unit in cardputer["units"]:
            with self.subTest(unit=unit["id"]):
                self.assertFalse(unit["host_admission"]["admitted"])
                self.assertEqual(unit["host_admission"]["port_ids"], [])
                self.assertEqual(unit["host_admission"]["ports"][0]["error"]["code"], "runtime_model_gap")
        self.assertNotIn("host_admission", self.registry.inventory()["units"][0])
        self.assertNotIn("host_admission", self.registry.unit("env-iii"))

    def test_host_admission_does_not_promote_planned_runtime(self):
        self.registry.profiles["env-iii"]["status"] = "planned"
        self.registry.profiles["env-iii"]["blocker"] = "missing controller"
        env = next(unit for unit in self.registry.inventory("cores3")["units"] if unit["id"] == "env-iii")
        self.assertFalse(env["host_admission"]["admitted"])
        self.assertEqual(env["host_admission"]["ports"][0]["error"], {
            "code": "runtime_model_gap", "message": "missing controller",
        })

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

    def test_scroll_program_metadata_preserves_exact_host_and_external_evidence_scope(self):
        profile = self.registry.profiles["scroll"]
        self.assertEqual(profile["model_completeness"], "partial")
        self.assertNotIn("host_validation", profile)
        self.assertEqual(set(profile["program_validation"]), {"cores3", "atoms3r", "sticks3", "stopwatch"})
        for host, validation in profile["program_validation"].items():
            with self.subTest(host=host):
                self.assert_external_validation(validation, host)
                self.assertEqual(validation["evidence_contract"], "same-guest-scroll-protocol-v1")
                self.assertEqual(validation["live_browser"], "PASS" if host == "cores3" else "NOT RUN")
                for field in ("firmware_sha256", "report_sha256", "evidence_sha256"):
                    self.assert_sha256(validation[field])
                self.assert_sha256(validation["session_id_sha256"])
                self.assertEqual(validation["runtime_proof_kind"], "macOS-proc_pidpath")
                self.assert_historical_path(validation["report"])
                if host == "cores3":
                    self.assert_historical_path(validation["live_browser_report"])
                    self.assert_sha256(validation["live_browser_report_sha256"])

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
                "id": "relay1", "unit_id": "relay", "port_id": "port-c",
            }])
        self.assertEqual(caught.exception.code, "unit_port_not_supported")

    def test_issue_unit_routes_and_controller_models_are_admitted(self):
        hat = self.registry.attachments("sticks3", "qemu", [{
            "id": "servo", "unit_id": "servo8-hat", "port_id": "hat",
        }])
        self.assertEqual(hat[0]["pins"], {"yellow": 8, "white": 0})
        servo = self.registry.attachments("cores3", "qemu", [{
            "id": "servo", "unit_id": "8servos", "port_id": "port-b",
        }])
        self.assertEqual(servo[0]["pins"], {"yellow": 9, "white": 8})
        sticks = self.registry.attachments("cores3", "qemu", [
            {"id": "hub", "unit_id": "hub", "port_id": "port-a"},
            {"id": "stick-a", "unit_id": "joystick2", "parent_id": "hub", "port_id": "grove-1"},
            {
                "id": "stick-b", "unit_id": "joystick2", "parent_id": "hub",
                "port_id": "grove-2", "initial": {"i2c-address": 0x64},
            },
        ])
        self.assertEqual([row["initial"].get("i2c-address") for row in sticks[1:]], [None, 0x64])
        nfc = self.registry.attachments("cores3", "qemu", [{
            "id": "nfc", "unit_id": "nfc", "port_id": "port-a",
        }])
        self.assertEqual(nfc[0]["pins"], {"yellow": 2, "white": 1})
        with self.assertRaises(UnitError) as caught:
            self.registry.attachments("cores3", "qemu", [{
                "id": "color", "unit_id": "color", "port_id": "port-b",
            }])
        self.assertEqual(caught.exception.code, "unit_port_not_supported")
        with self.assertRaises(UnitError) as caught:
            self.registry.attachments("sticks3", "qemu", [{
                "id": "env", "unit_id": "env-iii", "port_id": "hat",
            }])
        self.assertEqual(caught.exception.code, "unit_port_not_supported")
        with self.assertRaises(UnitError) as caught:
            self.registry.attachments("cores3", "qemu", [
                {"id": "hub", "unit_id": "hub", "port_id": "port-a"},
                {"id": "stick-a", "unit_id": "joystick2", "parent_id": "hub", "port_id": "grove-1"},
                {"id": "stick-b", "unit_id": "joystick2", "parent_id": "hub", "port_id": "grove-2"},
            ])
        self.assertEqual(caught.exception.code, "unit_address_conflict")

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

    def test_explicit_historical_verifier_fails_when_archives_are_absent(self):
        import subprocess
        import sys
        import tempfile
        root = self.registry.root.parents[1]
        with tempfile.TemporaryDirectory(prefix="m5-missing-unit-evidence-") as temporary:
            result = subprocess.run([
                sys.executable, str(root / "tests/units/verify_historical_runtime_evidence.py"),
                "--evidence-root", temporary, "--suite", "scroll",
            ], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertIn("FileNotFoundError", result.stderr)
        self.assertIn("FAILED", result.stderr)

    def assert_sha256(self, value):
        self.assertIsInstance(value, str)
        self.assertRegex(value, r"^[a-f0-9]{64}$")

    def assert_historical_path(self, value):
        from pathlib import PurePosixPath
        self.assertIsInstance(value, str)
        path = PurePosixPath(value)
        self.assertTrue(value.startswith("docs/evidence/"), value)
        self.assertFalse(path.is_absolute(), value)
        self.assertNotIn("..", path.parts)
        self.assertNotIn("\\", value)
        self.assertEqual(path.as_posix(), value)
        self.assertFalse(any(ord(char) < 32 for char in value))

    def assert_external_validation(self, validation, host):
        # A pinned historical label is an auditable reference, never a current
        # execution result. The opt-in verifier checks the raw byte bindings.
        self.assertEqual(validation["evidence_storage"], "external")
        self.assertEqual(validation["validation_scope"], "historical-exact-runtime")
        commit = validation["evidence_commit"]
        self.assertRegex(commit, r"^[a-f0-9]{40}$")
        self.assertTrue(validation["archive_url"].startswith(
            f"https://github.com/m5agent/m5stack-esp-emulator/blob/{commit}/docs/evidence/") or
            validation["archive_url"].startswith(
            f"https://github.com/m5agent/m5stack-esp-emulator/tree/{commit}/docs/evidence/"))
        self.assertEqual(validation["device_id"], host)
        self.assertIn(host, self.registry.hosts)
        self.assertEqual(validation["runtime"], "qemu")
        self.assertEqual(validation["hardware"], "NOT RUN")
        self.assert_sha256(validation["runtime_binary_sha256"])

    def test_public_runtime_metadata_omits_raw_session_and_host_process_identifiers(self):
        def check(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    self.assertNotIn(key, {"session_id", "pid", "worker_generation"})
                    if key == "session_id_sha256":
                        self.assert_sha256(child)
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(self.registry.profiles)

    def test_all_guest_and_program_pass_labels_are_explicit_historical_references(self):
        checked = []
        for unit_id, profile in self.registry.profiles.items():
            guest = profile.get("guest_validation")
            records = ([guest] if guest else []) + list(profile.get("program_validation", {}).values())
            for validation in records:
                if validation.get("status") != "PASS":
                    continue
                with self.subTest(unit=unit_id, device=validation.get("device_id")):
                    self.assert_external_validation(validation, validation["device_id"])
                    if "report" in validation:
                        self.assert_historical_path(validation["report"])
                        self.assert_sha256(validation["report_sha256"])
                    for case in validation.get("cases", []):
                        self.assertEqual(case["device_id"], validation["device_id"])
                        self.assert_historical_path(case["report"])
                        self.assert_sha256(case["report_sha256"])
                        self.assertEqual(case["evidence_commit"], validation["evidence_commit"])
                        self.assertEqual(case["evidence_storage"], "external")
                        self.assertEqual(case["validation_scope"], "historical-exact-runtime")
                    checked.append((unit_id, validation["device_id"]))
        self.assertTrue(checked)

    def test_host_pass_metadata_binds_exact_identity_and_external_archive_references(self):
        checked = []
        for unit_id, profile in self.registry.profiles.items():
            for host_id, validation in profile.get("host_validation", {}).items():
                if validation["status"] != "PASS":
                    self.assertEqual(validation["status"], "NOT RUN")
                    self.assertTrue(validation.get("blocker"))
                    continue
                with self.subTest(unit=unit_id, host=host_id):
                    self.assert_external_validation(validation, host_id)
                    self.assertIn(host_id, profile["hosts"])
                    self.assert_sha256(validation["session_id_sha256"])
                    self.assertTrue(validation["firmware_flavor"])
                    self.assertEqual(validation["runtime_proof_kind"], "direct-pid")
                    self.assertEqual(validation["guest_controller"], "PASS")
                    self.assertEqual(validation["live_browser"], "PASS")
                    contract = validation.get("evidence_contract", "host-probe-dual-observer-v1")
                    self.assertIn(contract, {CONTROL_WEB_CONTRACT, SENSOR_WEB_CONTRACT, "host-probe-dual-observer-v1"})
                    for key in ("firmware_sha256", "report_sha256", "evidence_sha256", "batch_selection_sha256"):
                        self.assert_sha256(validation[key])
                    for key in ("report", "batch_selection"):
                        self.assert_historical_path(validation[key])
                    if contract in {CONTROL_WEB_CONTRACT, SENSOR_WEB_CONTRACT}:
                        self.assert_historical_path(validation["normalization_receipt"])
                        self.assert_sha256(validation["normalization_receipt_sha256"])
                    checked.append((unit_id, host_id))
        self.assertTrue(checked, "no host-local historical PASS references were checked")


if __name__ == "__main__":
    unittest.main()
