"""Integer QMP coordinates must reach the exact requested display pixel."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests/uiflow2"))
from run_profile_ui_test import pointer_events


class PointerPixelRoundtripTests(unittest.TestCase):
    def test_all_supported_axis_pixels_survive_qemu_integer_scaling(self):
        # This is the ui/input.c qemu_input_scale_axis contract used by the
        # actual panel controller. The old host floor encoding loses pixels.
        for extent in (1, 135, 170, 240, 320, 466, 480, 600, 720, 800, 960, 1280):
            with self.subTest(extent=extent):
                for pixel in range(extent):
                    x, y = pointer_events(pixel, pixel, (extent, extent))
                    for event in (x, y):
                        absolute = event["data"]["value"]
                        self.assertGreaterEqual(absolute, 0)
                        self.assertLessEqual(absolute, 32767)
                        self.assertEqual(absolute * (extent - 1) // 32767, pixel)

    def test_button_state_and_exact_edge_pixels_are_preserved(self):
        events = pointer_events(319, 0, (320, 240), True)
        self.assertEqual([event["data"]["value"] for event in events[:2]], [32767, 0])
        self.assertEqual(events[2], {"type": "btn", "data": {"down": True, "button": "left"}})


if __name__ == "__main__":
    unittest.main()
