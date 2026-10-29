#!/usr/bin/env python3
import unittest
from pathlib import Path
import sys
import json
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))
import peripheral_catalog
from peripheral_catalog import validate


class PeripheralCatalogTests(unittest.TestCase):
    def test_catalog_is_complete(self):
        errors, report = validate()
        self.assertEqual(errors, [])
        self.assertGreater(report["models"], 20)
        self.assertEqual(report["devices"], 14)
        self.assertGreater(report["requirements_total"], 50)
        self.assertEqual(
            report["requirements_covered"],
            report["requirements_total"],
        )

    def test_all_statuses_are_known(self):
        _, report = validate()
        known = {"simulated", "partial", "planned", "not-applicable"}
        self.assertTrue(set(report["model_status"]) <= known)
        self.assertTrue(set(report["device_status"]) <= known)

    def test_every_simulated_model_has_board_evidence(self):
        _, report = validate()
        self.assertEqual(
            report["models_with_test_evidence"].get("simulated", 0),
            report["model_status"].get("simulated", 0),
        )

    def test_compatibility_components_are_optional_variants(self):
        catalog = json.loads(
            (ROOT / "platform/peripherals/catalog.json").read_text()
        )
        components = {
            component["id"]: component
            for component in catalog["devices"]["core2"]["components"]
        }
        self.assertTrue(
            components["secure-element-aws-compat"]["compatibility"]
        )
        errors, _ = validate()
        self.assertEqual(errors, [])

    def test_unfinished_devices_declare_component_blockers(self):
        catalog = json.loads(
            (ROOT / "platform/peripherals/catalog.json").read_text()
        )
        tab5 = catalog["devices"]["tab5"]
        cardputer_zero = catalog["devices"]["cardputer-zero"]
        stackchan = catalog["devices"]["stackchan"]
        self.assertEqual(tab5["peripheral_status"], "partial")
        self.assertEqual(cardputer_zero["peripheral_status"], "simulated")
        self.assertEqual(stackchan["peripheral_status"], "simulated")
        self.assertEqual(stackchan["peripheral_blockers"], [])
        tab5_models = {
            blocker["model"] for blocker in tab5["peripheral_blockers"]
        }
        zero_models = {
            blocker["model"]
            for blocker in cardputer_zero["peripheral_blockers"]
        }
        self.assertTrue({"es8388", "es7210", "sc2356"} <= tab5_models)
        self.assertNotIn("rs485", tab5_models)
        self.assertEqual(zero_models, set())
        self.assertNotIn("camera-imx219", zero_models)
        self.assertFalse(
            {
                "keyboard-tca8418",
                "m5ioe1",
                "bmi270",
                "bmm150",
                "rx8130",
                "bq27220",
                "es8389",
                "ip2315",
                "ethernet-sr9900a",
                "linux-bcm2837",
                "ir-tx-rx-bcm2837",
            }
            & zero_models
        )

    def test_incomplete_device_exemptions_are_explicit(self):
        catalog = json.loads(
            (ROOT / "platform/peripherals/catalog.json").read_text()
        )
        allowlist = catalog["completion_policy"][
            "incomplete_device_allowlist"
        ]
        self.assertIn("tab5", allowlist)
        self.assertTrue(allowlist["tab5"]["reason"])
        self.assertRegex(
            allowlist["tab5"]["review_by"],
            r"^\d{4}-\d{2}-\d{2}$",
        )

    def test_unallowlisted_incomplete_device_is_rejected(self):
        catalog = json.loads(
            (ROOT / "platform/peripherals/catalog.json").read_text()
        )
        catalog["completion_policy"]["incomplete_device_allowlist"] = {}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text(json.dumps(catalog))
            with mock.patch.object(
                peripheral_catalog, "PERIPHERALS", path
            ):
                errors, _ = validate()
        self.assertIn(
            "incomplete device tab5: no allowlist exemption; complete every "
            "peripheral before registering the device",
            errors,
        )

    def test_peripheral_templates_are_valid_json(self):
        for name in ("device-template.json", "model-template.json"):
            json.loads((ROOT / "platform/peripherals" / name).read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
