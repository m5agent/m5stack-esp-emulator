"""Keep declared HTTP audit coverage tied to the actual published contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DeviceApiSweepInventoryTests(unittest.TestCase):
    def test_every_published_operation_has_an_explicit_validation_plan(self):
        contract = ROOT / "docs/device-service.openapi.yaml"
        inventory = json.loads((ROOT / "tests/uiflow2/api_sweep/inventory_api.source.json").read_text())
        # Read only the canonical top-level path/method headings. Schemas and
        # YAML values do not participate, and no optional YAML dependency is
        # required by a clean checkout's ordinary platform tests.
        expected, path, in_paths = set(), None, False
        for line in contract.read_text().splitlines():
            if line == "paths:":
                in_paths = True
                continue
            if in_paths and line and not line.startswith(" "):
                break
            if in_paths:
                route = re.fullmatch(r"  (/\S+):", line)
                method = re.fullmatch(r"    (get|post|delete|put|patch|head|options):", line)
                if route:
                    path = route.group(1)
                elif method:
                    self.assertIsNotNone(path)
                    expected.add(method.group(1).upper() + " " + path)
        actual = {row["operation_id"] for row in inventory["operations"]}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(inventory["operations"]))
        self.assertEqual(inventory["contract_sha256"], hashlib.sha256(contract.read_bytes()).hexdigest())
        cases = {row["case_id"]: row for row in inventory["safe_cases"]}
        self.assertEqual(len(cases), len(inventory["safe_cases"]))
        for operation in inventory["operations"]:
            with self.subTest(operation=operation["operation_id"]):
                self.assertEqual(operation["operation_id"], operation["method"] + " " + operation["path"])
                self.assertIn(operation["phase"], inventory["positive_phase_plans"])
                self.assertTrue(operation["required_fixtures"] or operation["phase"] == "catalog-and-health")
                for case_id in operation["case_ids"]:
                    self.assertEqual(cases[case_id]["operation_id"], operation["operation_id"])
        for case in cases.values():
            self.assertIn(case["operation_id"], actual)
            if case["coverage"] == "positive-read":
                self.assertEqual(case["method"], "GET")
                self.assertEqual(case["expected_status"], [200])
            else:
                self.assertEqual(case["coverage"], "rejection-only")
                self.assertTrue(all(400 <= status < 500 for status in case["expected_status"]))
