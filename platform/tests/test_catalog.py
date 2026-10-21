#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "sticks3", "cores3", "stopwatch", "cardputer-adv", "cardputer-zero",
    "papermono", "core2", "papercolor", "nanoc6", "stackchan", "tab5",
    "atoms3r", "nesso-n1", "stamplc",
}


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = json.loads((ROOT / "devices" / "catalog.source.json").read_text())
        cls.catalog = json.loads((ROOT / "devices" / "catalog.json").read_text())

    def test_expected_devices_are_unique(self) -> None:
        ids = [device["id"] for device in self.source["devices"]]
        self.assertEqual(EXPECTED, set(ids))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(self.catalog["devices"]), len(EXPECTED))

    def test_device_files_exist(self) -> None:
        for entry in self.catalog["devices"]:
            path = ROOT / "devices" / entry["path"]
            self.assertTrue((path / "device.json").is_file(), path)
            self.assertTrue((path / "firmware.json").is_file(), path)
            self.assertTrue((path / "README.md").is_file(), path)
            self.assertTrue((path / "index.html").is_file(), path)

    def test_required_profile_fields(self) -> None:
        for device in self.source["devices"]:
            for key in ("id", "name", "group", "category", "hardware", "shell", "runtime", "uiflow2"):
                self.assertIn(key, device)
            self.assertIn(device["runtime"]["status"], {"reference-ready", "boot-capable", "backend-required"})
            self.assertIn(device["shell"]["preset"], {
                "watch-round", "stick", "core", "cardputer", "paper", "tab",
                "atom", "robot", "industrial", "console-only",
            })

    def test_runtime_contract(self) -> None:
        by_id = {device["id"]: device for device in self.source["devices"]}
        self.assertEqual("reference-ready", by_id["stopwatch"]["runtime"]["status"])
        self.assertEqual("reference-ready", by_id["core2"]["runtime"]["status"])
        self.assertEqual("reference-ready", by_id["nesso-n1"]["runtime"]["status"])
        self.assertEqual("qemu-esp32s3", by_id["sticks3"]["runtime"]["backend"])
        self.assertEqual(
            "display-touch-pass",
            by_id["nesso-n1"]["runtime"]["validation"]["status"],
        )
        self.assertEqual("backend-required", by_id["cardputer-zero"]["runtime"]["status"])
        self.assertFalse(by_id["cardputer-zero"]["uiflow2"]["supported"])
        self.assertIsNone(by_id["nanoc6"]["hardware"]["display"])
        for device in self.source["devices"]:
            if device["runtime"]["status"] == "boot-capable":
                self.assertIn(device["runtime"]["chip"], {"esp32s3", "esp32c6", "esp32p4"})

    def test_uiflow_firmware_urls_are_public_https(self) -> None:
        for device in self.source["devices"]:
            firmware = device["uiflow2"].get("firmware")
            if firmware:
                self.assertTrue(firmware["download_url"].startswith("https://m5burner-cdn.m5stack.com/"))
                self.assertTrue(firmware["firmware_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
