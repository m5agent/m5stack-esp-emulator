"""Host-only setup boundary controls. These mocks do not execute firmware."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests/browser-qemu/uiflow_workbench/button_observer.py"


class PublicPM1ButtonFixtureTests(TestCase):
    def execute_setup(self, *, before=0x2A, after=0x2D, before4a=0, after4a=0,
                      board=1, expected_board=1, setup=True, module=True, window=500):
        calls = []
        values = iter([before, before4a, after, after4a])

        class Bus:
            def __init__(self, ident, **pins):
                calls.append(("bus", ident, pins))

            def readfrom_mem(self, addr, reg, size):
                calls.append(("read", addr, reg, size))
                return bytes((next(values),))

        class PM1:
            BUTTON_TIMING_CLICK = 0

            def __init__(self, bus, *, addr):
                calls.append(("driver", addr))

            def disable_single_click_reset(self):
                calls.append(("disable_single_click_reset",))

            def set_button_timing(self, event, duration):
                calls.append(("set_button_timing", event, duration))

        # Execute the actual observer's initialization up to the button loop.
        # Bus responses are explicit test inputs; no replacement driver event
        # or guest-output claim is constructed from these mocks.
        tree = ast.parse(SOURCE.read_text())
        prefix = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "buttons" for t in node.targets):
                break
            prefix.append(node)
        modules = {"M5": SimpleNamespace(begin=lambda: calls.append(("begin",)), getBoard=lambda: board,
                                          BOARD=SimpleNamespace(M5StopWatch=expected_board)),
                   "machine": SimpleNamespace(I2C=Bus, Pin=lambda pin: pin),
                   "driver": SimpleNamespace()}
        modules["driver.m5pm1"] = SimpleNamespace(M5PM1=PM1) if module else None
        scope = {"BUTTON_PM1_SETUP": {"board": "M5StopWatch", "i2c": 1, "scl": 48, "sda": 47,
                                      "addr": 0x6E, "click_window_ms": window} if setup else {}}
        with patch.dict(sys.modules, modules):
            exec(compile(ast.Module(body=prefix, type_ignores=[]), str(SOURCE), "exec"), scope)
        return scope["pmic_setup"], calls

    def test_public_api_and_real_readback_are_required(self):
        result, calls = self.execute_setup()
        self.assertTrue(result["applied"])
        self.assertEqual((result["cfg49_before"], result["cfg49_after"]), (0x2A, 0x2D))
        self.assertEqual(calls[1], ("bus", 1, {"scl": 48, "sda": 47, "freq": 100000}))
        self.assertIn(("disable_single_click_reset",), calls)
        self.assertIn(("set_button_timing", 0, 500), calls)
        self.assertEqual([row[2] for row in calls if row[0] == "read"], [0x49, 0x4A, 0x49, 0x4A])

    def test_wrong_mode_or_changed_unrelated_bits_fail_closed(self):
        for kwargs in ({"after": 0x2B}, {"after": 0xAD}, {"after4a": 1}, {"board": 2}, {"window": 1000}):
            with self.subTest(kwargs=kwargs), self.assertRaises(AssertionError):
                self.execute_setup(**kwargs)

    def test_missing_official_module_has_no_fallback(self):
        with self.assertRaises(ImportError):
            self.execute_setup(module=False)

    def test_unregistered_boards_do_not_touch_pm1(self):
        result, calls = self.execute_setup(setup=False, module=False)
        self.assertEqual(result, {})
        self.assertEqual(calls, [("begin",)])


if __name__ == "__main__":
    main()
