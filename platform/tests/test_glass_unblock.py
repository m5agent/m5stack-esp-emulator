"""Static contracts for the task-75 glass unblock root-cause fix."""
from __future__ import annotations
import hashlib, json, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "docs/evidence/2026-11-03-glass-unblock"
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0157-unit-glass-m5gfx-protocol.patch"

class GlassUnblockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text())
        cls.units = {u["id"]: u for u in cls.catalog["units"]}
        cls.profiles = json.loads((ROOT / "platform/units/runtime-profiles.json").read_text())["units"]

    def test_patch_implements_custom_m5gfx_protocol(self):
        text = PATCH.read_text()
        for token in ("glass_reg", "0x90", "0xb0", "0xfe", "glass_pages", "M5GFX"):
            self.assertIn(token, text)
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text()
        self.assertIn("0157-unit-glass-m5gfx-protocol.patch", readme)

    def test_glass_profile_is_implemented_with_new_evidence(self):
        unit, profile = self.units["glass"], self.profiles["glass"]
        self.assertEqual(unit["model_status"], "partial")
        self.assertEqual(unit["runtime"]["status"], "implemented")
        self.assertEqual(profile["status"], "implemented")
        self.assertEqual(profile["hosts"], ["cores3"])
        ev = profile["virtual_device_evidence"]
        report = ROOT / ev["report"]
        self.assertTrue(report.is_file())
        self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(), ev["report_sha256"])
        data = json.loads(report.read_text())
        self.assertEqual(data["status"], "PASS")
        self.assertIn("0157-unit-glass-m5gfx-protocol.patch", ev["patches"])
        self.assertGreater(data["observations"]["glass"]["qom"]["commands"], 0)
        self.assertGreater(data["observations"]["glass"]["qom"]["data-bytes"], 0)
        self.assertGreater(data["observations"]["glass"]["qom"]["pages"], 0)

    def test_protocol_contract_no_longer_claims_ssd1309(self):
        summary = self.units["glass"]["protocol"]["summary"]
        self.assertIn("M5UnitGLASS", summary)
        self.assertIn("REG_INDEX", summary)
        self.assertNotIn("control byte 0x00", summary)
        self.assertEqual(self.units["glass"]["runtime"]["properties"]["pages"]["type"], "integer")

if __name__ == "__main__":
    unittest.main()
