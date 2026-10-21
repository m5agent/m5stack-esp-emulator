#!/usr/bin/env python3
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))
from peripheral_catalog import validate


class PeripheralCatalogTests(unittest.TestCase):
    def test_catalog_is_complete(self):
        errors, report = validate()
        self.assertEqual(errors, [])
        self.assertGreater(report["models"], 20)
        self.assertEqual(report["devices"], 14)

    def test_all_statuses_are_known(self):
        _, report = validate()
        known = {"simulated", "partial", "planned", "not-applicable"}
        self.assertTrue(set(report["model_status"]) <= known)
        self.assertTrue(set(report["device_status"]) <= known)


if __name__ == "__main__":
    unittest.main(verbosity=2)
