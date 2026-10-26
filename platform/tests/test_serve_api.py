#!/usr/bin/env python3
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))
from serve import Handler


class ServePeripheralApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get_json(self, path: str):
        with urlopen(self.base + path, timeout=5) as response:
            return json.load(response)

    def test_stackchan_inventory_is_complete(self):
        row = self.get_json("/api/peripherals/stackchan")
        self.assertTrue(row["complete"])
        self.assertEqual(row["peripheral_status"], "simulated")
        self.assertEqual(len(row["components"]), 20)
        self.assertIn(
            "stackchan-peripherals",
            row["runtime_cases"]["matrix"],
        )

    def test_tab5_inventory_preserves_blockers(self):
        row = self.get_json("/api/peripherals/tab5")
        self.assertFalse(row["complete"])
        self.assertIn("sc2356", row["blocked_models"])
        self.assertIn("es8388", row["blocked_models"])
        self.assertNotIn("rs485", row["blocked_models"])
        self.assertEqual(
            row["completion_exemption"]["review_by"],
            "2026-12-31",
        )
        self.assertIn(
            "tab5-hosted-peripherals",
            row["runtime_cases"]["external"],
        )

    def test_all_peripherals_inventory(self):
        payload = self.get_json("/api/peripherals")
        self.assertEqual(len(payload["devices"]), 14)
        self.assertEqual(payload["runtime_coverage"]["covered_models"], 60)
        self.assertEqual(
            sum(row["complete"] for row in payload["devices"]),
            13,
        )

    def test_runtime_interfaces_api(self):
        payload = self.get_json("/api/peripheral-interfaces")
        self.assertEqual(payload["model_count"], 65)
        bmi270 = payload["models"]["bmi270"]
        self.assertTrue(bmi270["interfaces"])
        self.assertIn("sticks3-peripherals", bmi270["evidence_cases"])

    def test_single_model_runtime_interfaces_api(self):
        payload = self.get_json("/api/peripheral-interfaces/bmi270")
        self.assertEqual(payload["kind"], "imu")
        self.assertTrue(payload["interfaces"])

    def test_external_unit_inventory_is_separate_from_board_models(self):
        payload = self.get_json("/api/v1/units?device_id=cores3")
        self.assertEqual(len(payload["units"]), 29)
        self.assertEqual([host["device_id"] for host in payload["hosts"]], ["cores3"])
        port = next(port for port in payload["hosts"][0]["ports"] if port["id"] == "port-a")
        self.assertEqual(port["pins"], {"yellow": 2, "white": 1})
        self.assertEqual(port["visual_port"], "grove")

    def test_unit_protocol_description_does_not_claim_guest_execution(self):
        payload = self.get_json("/api/v1/units/env-iii")
        self.assertEqual(payload["interface"]["address_7bit"], [0x44, 0x70])
        self.assertIn(payload["runtime"]["status"], {"developing", "implemented", "validated"})
        if payload["runtime"]["status"] != "validated":
            self.assertTrue(payload["runtime"]["blocker"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
