"""Source identity and C6 context-port checks; no local runtime cache required."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("c6_bootstrap", ROOT / "scripts/bootstrap-c6-runtime.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def additions(path):
    return [line[1:] for line in path.read_text().splitlines()
            if line.startswith("+") and not line.startswith("+++")]


class C6BootstrapTests(unittest.TestCase):
    def test_wifi_context_port_keeps_exact_added_controller_source(self):
        original = ROOT / "patches/qemu-m5stack-peripherals/0025-esp32c6-wifi-mac.patch"
        context = ROOT / "patches/qemu-esp32c6-uiflow2-adapters/0007-wifi-context.patch"
        self.assertEqual(additions(original), additions(context))
        self.assertIn("hw/misc/esp32c6_wifi.c", bootstrap.source_files())
        self.assertTrue(all("\t" not in name for name in bootstrap.source_files()))

    def test_unowned_directory_is_not_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            marker = source / "keep.txt"
            marker.write_text("user source")
            with patch.object(bootstrap, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "unowned"):
                    bootstrap.prepare_source(source)
                run.assert_not_called()
            self.assertEqual(marker.read_text(), "user source")

    def test_target_is_c6_and_patch_paths_are_valid(self):
        self.assertEqual(bootstrap.QEMU_COMMIT, "febae182e132e4055529be423a818225ebddaa3a")
        self.assertEqual(len(set(bootstrap.PATCHES)), len(bootstrap.PATCHES))
        for path in bootstrap.PATCHES:
            self.assertTrue((ROOT / path).is_file(), path)
            self.assertNotIn("wasm", path)
