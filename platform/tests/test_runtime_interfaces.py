#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))
from runtime_interfaces import build_interfaces


class RuntimeInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = build_interfaces()

    def test_every_simulated_model_has_an_interface(self):
        models = self.payload["models"]
        simulated = {
            model_id
            for model_id, model in models.items()
            if model["status"] == "simulated"
        }
        missing = sorted(
            model_id for model_id in simulated
            if not models[model_id]["interfaces"]
        )
        self.assertEqual(missing, [])

    def test_bmi270_exposes_qom_inputs(self):
        model = self.payload["models"]["bmi270"]
        properties = {
            item["property"]
            for item in model["interfaces"]
            if item["adapter"] == "qmp-qom"
            and item["direction"] == "input"
        }
        self.assertTrue(
            {"accel-x", "accel-y", "accel-z", "gyro-x", "gyro-y", "gyro-z"}
            <= properties
        )

    def test_audio_exposes_pcm_input_and_output(self):
        speaker_directions = {
            item["direction"]
            for item in self.payload["models"]["es8311"]["interfaces"]
            if item.get("format") == "pcm-s16le"
        }
        microphone_directions = {
            item["direction"]
            for item in self.payload["models"]["es7210"]["interfaces"]
            if item.get("format") == "pcm-s16le"
        }
        self.assertIn("output", speaker_directions)
        self.assertIn("input", microphone_directions)

    def test_interfaces_are_json_serializable(self):
        encoded = json.dumps(self.payload)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["model_count"], 65)
        self.assertEqual(decoded["device_count"], 14)

    def test_device_case_groups_are_resolved(self):
        stackchan = self.payload["devices"]["stackchan"]
        self.assertEqual(len(stackchan["matrix"]), 8)
        self.assertEqual(
            {case["machine"] for case in stackchan["matrix"]},
            {"m5stackchan"},
        )
        self.assertEqual(len(self.payload["devices"]["tab5"]["external"]), 3)
        self.assertIn(
            "stackchan-peripherals",
            stackchan["case_models"],
        )

    def test_model_interfaces_include_all_device_local_cases(self):
        cases = {
            item["case"]
            for item in self.payload["models"]["pcf8563"]["interfaces"]
        }
        self.assertTrue(
            {
                "cores3-peripherals",
                "stackchan-peripherals",
                "core2-peripherals",
            }
            <= cases
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
