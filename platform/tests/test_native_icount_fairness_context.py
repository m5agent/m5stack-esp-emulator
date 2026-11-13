"""Keep the native source recipe wired to the existing accelerator policy."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NativeFairnessContextTests(unittest.TestCase):
    def test_native_recipe_includes_context_port(self):
        spec = importlib.util.spec_from_file_location(
            "bootstrap_runtime", ROOT / "scripts/bootstrap-unit-runtime.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        patch = "patches/qemu-unit-runtime/0021-native-icount-fairness-context.patch"
        self.assertIn(patch, module.PATCHES)
        text = (ROOT / patch).read_text()
        for marker in ("M5SW_ICOUNT_MAX_PERCPU_NS", "icount_get_max_percpu_ns",
                       "MIN(timeslice, icount_round(max_slice_ns))"):
            self.assertIn(marker, text)
        self.assertNotIn("disable_wdt", text.lower())


if __name__ == "__main__":
    unittest.main()
