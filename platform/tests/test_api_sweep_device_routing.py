"""API sweep runners use the inventory geometry for every supported board."""
import importlib.util
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
API_SWEEP = ROOT / "tests/uiflow2/api_sweep"
sys.path.insert(0, str(API_SWEEP))


def load(name):
    spec = importlib.util.spec_from_file_location(name, API_SWEEP / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApiSweepDeviceRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guest = load("run_guest")
        cls.ui = load("run_ui_live")

    def test_new_boards_are_admitted_by_cold_runners(self):
        self.assertEqual(
            self.guest.DEVICE_CHOICES,
            ("cores3", "cardputer-adv", "stopwatch", "sticks3", "core2"),
        )

    def test_native_uart_bases_do_not_duplicate_the_repl_terminal(self):
        for device in ("stopwatch", "sticks3"):
            with self.subTest(device=device):
                bootstrap = self.guest.live_boot(device, "native")
                self.assertNotIn("os.dupterm", bootstrap)
                self.assertIn("_uiflow_run_main = True", bootstrap)
        self.assertIn("os.dupterm", self.guest.live_boot("sticks3", "dupterm"))
        self.assertIn("os.dupterm", self.guest.live_boot("sticks3"))

    def test_ui_geometry_comes_from_device_inventory(self):
        self.assertEqual(self.ui.display_dimensions("stopwatch"), (466, 466))
        self.assertEqual(self.ui.api_dimensions("stopwatch"), (468, 468))
        self.assertEqual(self.ui.api_dimensions("sticks3"), (135, 240))
        self.assertEqual(self.ui.api_dimensions("core2"), (320, 240))
        self.assertEqual(self.ui.ui_rotation("core2"), 1)

    def test_display_oracles_adapt_to_narrow_and_circular_glass(self):
        probe_ui = load("probe_ui")
        for width, height in ((135, 240), (320, 240), (466, 466)):
            for method in probe_ui.DISPLAY_RECIPES:
                with self.subTest(method=method, size=(width, height)):
                    source = probe_ui.build_display_program(
                        method, f"geometry-{width}-{method}", width=width, height=height
                    )
                    compile(source, f"<{method}>", "exec")
                    _, _, frame = probe_ui.display_recipe_for(method, width, height)
                    for point in (frame or {}).get("points", []):
                        x, y = point[:2]
                        self.assertTrue(0 <= x < width and 0 <= y < height)
                        if width == height:
                            self.assertLessEqual(
                                math.hypot(x - width / 2, y - height / 2), width / 2
                            )

    def test_unknown_geometry_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown device"):
            self.ui.display_dimensions("not-a-device")


if __name__ == "__main__":
    unittest.main()
