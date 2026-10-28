from __future__ import annotations

import base64
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
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


def load_matrix_runner():
    previous_path = list(sys.path)
    sys.path.insert(0, str(API_SWEEP))
    try:
        spec = importlib.util.spec_from_file_location(
            "api_sweep_m5ui_matrix_runner_for_dimension_test",
            API_SWEEP / "run_m5ui_matrix.py",
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot import run_m5ui_matrix")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = previous_path


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

    def test_matrix_lifecycle_uses_device_dimensions_and_rotation(self):
        runner = load_matrix_runner()
        source = runner.lifecycle_source(468, 468, 3)
        self.assertIn("get_horizontal_resolution()==468", source)
        self.assertIn("M5.Lcd.setRotation(3)", source)
        self.assertNotIn("M5.Lcd.setRotation(0)", source)

    def test_matrix_fixture_materialization_matches_declared_hashes(self):
        runner = load_matrix_runner()
        probe_ui = load_probe()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            fixture_path = runner.fixture_dir(output)
            expected = probe_ui.fixture_files()
            for name, row in expected.items():
                actual = hashlib.sha256((fixture_path / name).read_bytes()).hexdigest()
                self.assertEqual(
                    actual,
                    hashlib.sha256(base64.b64decode(row["data"])).hexdigest(),
                )

    def test_matrix_runner_requires_isolated_output_and_token(self):
        completed = subprocess.run(
            [sys.executable, str(API_SWEEP / "run_m5ui_matrix.py"), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--token-file", completed.stdout)
        self.assertIn("--out-dir", completed.stdout)


if __name__ == "__main__":
    unittest.main()
