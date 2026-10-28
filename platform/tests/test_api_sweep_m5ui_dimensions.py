from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
API_SWEEP = ROOT / "tests/uiflow2/api_sweep"


def load_probe():
    spec = importlib.util.spec_from_file_location(
        "api_sweep_probe_ui_for_dimension_test",
        API_SWEEP / "probe_ui.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import probe_ui")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApiSweepM5uiDimensionTest(unittest.TestCase):
    def test_display_size_oracle_uses_requested_api_dimensions(self):
        probe_ui = load_probe()
        source = probe_ui.build_m5ui_program(
            "M5Label",
            ["get_display_size"],
            "dimension-test",
            width=468,
            height=468,
            rotation=3,
        )
        self.assertIn("tuple(result)==(468,468)", source)
        self.assertNotIn("tuple(result)==(320,240)", source)
        self.assertIn("M5.Lcd.setRotation(3)", source)
        self.assertNotIn("M5.Lcd.setRotation(0)", source)

    def test_display_size_oracle_rejects_invalid_dimensions(self):
        probe_ui = load_probe()
        with self.assertRaises(ValueError):
            probe_ui.build_m5ui_program(
                "M5Label",
                ["get_display_size"],
                "dimension-test",
                width=0,
                height=240,
            )

    def test_rotation_rejects_invalid_value(self):
        probe_ui = load_probe()
        with self.assertRaises(ValueError):
            probe_ui.build_m5ui_program(
                "M5Label",
                [],
                "rotation-test",
                rotation=4,
            )


if __name__ == "__main__":
    unittest.main()
