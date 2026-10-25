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

    def test_validated_profiles_match_device_catalog_snapshot(self):
        source = json.loads(
            (ROOT / "devices/catalog.source.json").read_text()
        )
        catalog = {
            device["id"]: device["runtime"].get("validation", {})
            for device in source["devices"]
        }
        for row in self.registry["devices"]:
            if not row["backend"].startswith(("qemu-esp32", "esp-emulator")):
                continue
            validation = row.get("validation", {})
            with self.subTest(device=row["id"]):
                self.assertEqual(
                    validation.get("date"),
                    catalog[row["id"]].get("date"),
                    f"{row['id']}: QEMU profile and device catalog dates differ",
                )
                self.assertEqual(
                    validation.get("status"),
                    catalog[row["id"]].get("status"),
                    f"{row['id']}: QEMU profile and device catalog statuses differ",
                )

    def test_stopwatch_is_reference_ready(self):
        row = next(row for row in self.registry["devices"] if row["id"] == "stopwatch")
        self.assertEqual(row["qemu_status"], "ready")
        self.assertEqual(row["backend"], "qemu-esp32s3")
        state = row["runtime_state"]
        self.assertEqual(state["power"]["path"], "/machine/m5pm1")
        self.assertIn("vbat-mv", state["power"]["properties"])
        self.assertEqual(state["expander"]["path"], "/machine/m5ioe1")
        self.assertIn("pa-enabled", state["expander"]["properties"])
        self.assertEqual(state["imu"]["path"], "/machine/bmi270")
        self.assertIn("accel-z", state["imu"]["properties"])
        self.assertIn("gyro-z", state["imu"]["properties"])

    def test_sticks3_runtime_state_probe(self):
        row = next(row for row in self.registry["devices"] if row["id"] == "sticks3")
        state = row["runtime_state"]
        self.assertEqual(state["power"]["path"], "/machine/m5pm1")
        self.assertIn("vbat-mv", state["power"]["properties"])
        self.assertIn("pa-enabled", state["power"]["properties"])
        self.assertEqual(state["imu"]["path"], "/machine/bmi270")
        self.assertIn("accel-z", state["imu"]["properties"])
        self.assertIn("gyro-z", state["imu"]["properties"])

    def test_cores3_runtime_state_probe(self):
        row = next(row for row in self.registry["devices"] if row["id"] == "cores3")
        state = row["runtime_state"]
        self.assertEqual(state["power"]["path"], "/machine/axp2101")
        self.assertIn("vbat-mv", state["power"]["properties"])
        self.assertIn("speaker-enabled", state["power"]["properties"])
        self.assertEqual(state["imu"]["path"], "/machine/bmi270")
        self.assertIn("accel-z", state["imu"]["properties"])
        self.assertIn("gyro-z", state["imu"]["properties"])

    def test_cardputer_runtime_state_probe(self):
        row = next(
            row for row in self.registry["devices"]
            if row["id"] == "cardputer-adv"
        )
        state = row["runtime_state"]
        self.assertEqual(state["imu"]["path"], "/machine/bmi270")
        self.assertIn("accel-z", state["imu"]["properties"])
        self.assertIn("gyro-z", state["imu"]["properties"])

    def test_atoms3r_runtime_state_probe(self):
        row = next(
            row for row in self.registry["devices"]
            if row["id"] == "atoms3r"
        )
        state = row["runtime_state"]
        self.assertEqual(state["imu"]["path"], "/machine/bmi270")
        self.assertIn("accel-z", state["imu"]["properties"])
        self.assertEqual(state["magnetometer"]["path"], "/machine/bmm150")
        self.assertIn("mag-z", state["magnetometer"]["properties"])
        self.assertEqual(state["led"]["path"], "/machine/lp5562")
        self.assertIn("red-pwm", state["led"]["properties"])

    def test_papercolor_runtime_state_probe(self):
        row = next(
            row for row in self.registry["devices"]
            if row["id"] == "papercolor"
        )
        state = row["runtime_state"]
        self.assertEqual(state["power"]["path"], "/machine/m5pm1")
        self.assertIn("vbat-mv", state["power"]["properties"])
        self.assertEqual(state["sensor"]["path"], "/machine/sht40")
        self.assertIn("temperature-c", state["sensor"]["properties"])
        self.assertIn("humidity-pct", state["sensor"]["properties"])

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

    def test_core2_no_stagger_boundary_is_not_overclaimed(self):
        row = next(
            row
            for row in self.registry["devices"]
            if row["id"] == "core2"
        )
        text = " ".join(
            [
                row["validation"]["concurrency_validation"],
                *row["blockers"],
            ]
        )
        self.assertIn("0008", text)
        self.assertIn("8/8", text)
        self.assertIn("6/6", text)
        self.assertIn("three-instance", text)
        self.assertIn("hli-errors=0", text)
        self.assertIn("36 events", text)
        self.assertIn("9 ACLs", text)
        self.assertIn("more than three instances", text)
        self.assertIn("NOT RUN", text)
        self.assertNotIn("concurrent cold-start safety and sustained", text)

    def test_nesso_visual_validation_is_complete(self):
        row = next(row for row in self.registry["devices"] if row["id"] == "nesso-n1")
        self.assertEqual(
            row["validation"]["status"],
            "display-touch-peripherals-wifi-ble-pass",
        )
        blockers = " ".join(row["blockers"])
        self.assertIn("RUNTIME-01", blockers)
        self.assertIn("fixed", blockers)
        self.assertIn("instruction access fault", blockers)

    def test_tab5_visual_validation_is_complete(self):
        row = next(row for row in self.registry["devices"] if row["id"] == "tab5")
        self.assertEqual(row["qemu_status"], "ready")
        self.assertEqual(row["backend"], "esp-emulator-native")
        self.assertEqual(
            row["validation"]["status"],
            "display-touch-rs485-pass-peripherals-partial",
        )
        self.assertEqual(row["peripheral_status"], "partial")
        blockers = " ".join(row["blockers"])
        self.assertIn("ES8388/ES7210", blockers)
        self.assertNotIn("RS-485", blockers)
        self.assertIn("SC2356", blockers)
        self.assertIn("USB Host", blockers)

    def test_cardputer_zero_declares_backend_blockers(self):
        row = next(
            row for row in self.registry["devices"]
            if row["id"] == "cardputer-zero"
        )
        self.assertEqual(row["qemu_status"], "separate-backend")
        self.assertEqual(row["peripheral_status"], "simulated")
        joined = "\n".join(row["blockers"])
        self.assertNotIn("no BCM2837 ARM64 Linux machine", joined)
        self.assertNotIn("ES8389", joined)
        self.assertNotIn("IP2315", joined)
        self.assertNotIn("GL852G", joined)
        self.assertTrue(
            any("ES8389" in item for item in row["board_work"])
        )
        self.assertTrue(
            any("IP2315" in item for item in row["board_work"])
        )
        self.assertTrue(
            any("GL852G" in item for item in row["board_work"])
        )
        self.assertTrue(
            any("SR9900A" in item for item in row["board_work"])
        )
        self.assertTrue(
            any("IMX219" in item for item in row["board_work"])
        )
        blockers = " ".join(row["blockers"])
        self.assertNotIn("IMX219", blockers)

    def test_nanoc6_peripherals_are_board_isolated(self):
        row = next(
            row for row in self.registry["devices"]
            if row["id"] == "nanoc6"
        )
        self.assertEqual(row["peripheral_status"], "simulated")
        blockers = " ".join(row["blockers"])
        self.assertIn("RUNTIME-02", blockers)
        self.assertIn("Zigbee/802.15.4", blockers)
        self.assertIn("rgb-led", row["peripherals"])
        self.assertIn("gpio-led", row["peripherals"])
        self.assertIn("button", row["peripherals"])
        self.assertIn("ir", row["peripherals"])

    def test_stackchan_peripherals_are_simulated(self):
        row = next(
            row for row in self.registry["devices"]
            if row["id"] == "stackchan"
        )
        self.assertEqual(row["peripheral_status"], "simulated")
        self.assertEqual(row["blockers"], [])
        self.assertIn("pcf8563", row["peripherals"])

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
        qemu_count = sum(
            row["backend"].startswith("qemu-esp32")
            for row in self.registry["devices"]
        )
        summary = self.registry["validation_matrix"]["result"]
        self.assertEqual(qemu_count, 12)
        self.assertIn("12 QEMU-backed ESP32", summary)
        self.assertIn("Tab5 through esp-emu", summary)
        self.assertNotIn("13 QEMU ESP32", summary)


if __name__ == "__main__":
    unittest.main()
