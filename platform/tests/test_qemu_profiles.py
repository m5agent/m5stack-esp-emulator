#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class QemuProfileTest(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads((ROOT / "platform/qemu/profiles.json").read_text())
        self.device_ids = {
            json.loads(p.read_text())["id"]
            for p in (ROOT / "devices").glob("**/device.json")
        }

    def test_registry_covers_every_device(self):
        registry_ids = {row["id"] for row in self.registry["devices"]}
        self.assertEqual(registry_ids, self.device_ids)

    def test_stopwatch_is_reference_ready(self):
        row = next(row for row in self.registry["devices"] if row["id"] == "stopwatch")
        self.assertEqual(row["qemu_status"], "ready")
        self.assertEqual(row["backend"], "qemu-esp32s3")

    def test_s3_hosts_are_ready(self):
        ready = {
            row["id"]
            for row in self.registry["devices"]
            if row["qemu_status"] == "ready"
        }
        self.assertTrue(
            {
                "stopwatch",
                "sticks3",
                "atoms3r",
                "cores3",
                "cardputer-adv",
                "stamplc",
                "stackchan",
                "papercolor",
                "papermono",
            }
            <= ready
        )

    def test_c6_and_core2_hosts_are_ready(self):
        ready = {
            row["id"]
            for row in self.registry["devices"]
            if row["qemu_status"] == "ready"
        }
        self.assertTrue({"nanoc6", "nesso-n1", "core2"} <= ready)

    def test_core2_uses_qemu_rom_esptool(self):
        profile = self.registry["backends"]["qemu-esp32lx6"]
        self.assertEqual(profile["status"], "ready")
        self.assertEqual(profile["flash_transport"], "qemu-rom-esptool")
        matrix = json.loads(
            (ROOT / "tests/uiflow2/device_matrix.json").read_text()
        )
        backend = matrix["backends"]["qemu-esp32lx6"]
        self.assertEqual(backend["qemu_esptool_chip"], "esp32")
        self.assertNotIn("esp_emu_chip", backend)

    def test_nesso_visual_validation_is_complete(self):
        row = next(row for row in self.registry["devices"] if row["id"] == "nesso-n1")
        self.assertEqual(
            row["validation"]["status"], "display-touch-power-io-ir-pass"
        )
        self.assertEqual(row["blockers"], [])

    def test_tab5_visual_validation_is_complete(self):
        row = next(row for row in self.registry["devices"] if row["id"] == "tab5")
        self.assertEqual(row["qemu_status"], "ready")
        self.assertEqual(row["validation"]["status"], "display-touch-pass")
        self.assertEqual(row["blockers"], [])

    def test_validation_matrix_covers_esp32_hosts(self):
        matrix_path = ROOT / self.registry["validation_matrix"]["runner"]
        self.assertTrue(matrix_path.is_file())
        flash_path = ROOT / self.registry["validation_matrix"]["flash_runner"]
        self.assertTrue(flash_path.is_file())
        matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
        matrix_ids = {device["id"] for device in matrix["devices"]}
        esp32_ids = {
            row["id"]
            for row in self.registry["devices"]
            if row["backend"].startswith(("qemu-esp32", "esp-emulator"))
            and row["id"] != "cardputer-zero"
        }
        self.assertEqual(matrix_ids, esp32_ids | {"cardputer-zero"})

    def test_group_counts(self):
        groups = {}
        for row in self.registry["devices"]:
            groups[row["group"]] = groups.get(row["group"], 0) + 1
        self.assertEqual(groups["esp32-s3"], 9)
        self.assertEqual(groups["esp32-c6"], 2)
        self.assertEqual(groups["esp32-p4"], 1)
        self.assertEqual(groups["esp32-lx6"], 1)
        self.assertEqual(groups["linux-arm64"], 1)


if __name__ == "__main__":
    unittest.main()
