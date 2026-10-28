"""The M5UI execution denominator must include methods, not only constructors."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/uiflow2/api_sweep"))
from run_m5ui_documented import documented_targets, lifecycle_source, widget_source


class M5UIDocumentedTests(unittest.TestCase):
    def test_all_official_method_slots_have_executable_or_explicit_mismatch_recipe(self):
        inventory = json.loads((ROOT / "tests/uiflow2/api_sweep/inventory_ui.source.json").read_text())
        targets = documented_targets(inventory)
        self.assertEqual(len(targets), 28)
        self.assertEqual(sum(map(len, targets.values())), 505)
        for target, methods in targets.items():
            with self.subTest(target=target):
                source = widget_source(target, methods)
                compile(source, target, "exec")
                self.assertNotIn("No behavior-specific recipe yet", source)
                self.assertIn("method_count=" + str(len(methods)), source)
                for method in methods:
                    self.assertIn("method=" + repr(method), source)

    def test_documentation_mismatch_is_never_promoted_to_state_pass(self):
        for target, method in (("M5Msgbox", "set_text"), ("M5Win", "get_text"), ("M5Roller", "event")):
            source = widget_source(target, [method])
            self.assertIn("status='DOCUMENTATION_MISMATCH'", source)
            self.assertIn("runtime_member_type", source)
            self.assertNotIn("status='STATE_PASS'", source)
            self.assertNotIn("obj." + method + "(", source)
        compile(lifecycle_source(), "lifecycle", "exec")


if __name__ == "__main__":
    unittest.main()
