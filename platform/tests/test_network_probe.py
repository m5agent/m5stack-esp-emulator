#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/uiflow2/network_probe/run_test.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("uiflow2_network_probe", RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {RUNNER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NetworkProbeProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load_runner()

    def test_reused_image_uses_recorded_base_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base.bin"
            image = root / "uiflow2-ui-test.bin"
            base.write_bytes(b"official-base")
            image.write_bytes(b"probe-image")
            device = {
                "id": "sticks3",
                "vfs_offset": "0x641000",
                "vfs_size": "0x1BE000",
                "flash_size": "0x800000",
            }
            recorded_base_hash = self.runner.sha256(base)
            self.runner.write_build_provenance(image, base, device)

            base.write_bytes(b"replaced-base")
            provenance = self.runner.load_build_provenance(image, "sticks3")

            self.assertEqual(provenance["base_sha256"], recorded_base_hash)
            self.assertNotEqual(provenance["base_sha256"], self.runner.sha256(base))

    def test_reused_image_rejects_missing_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "uiflow2-ui-test.bin"
            image.write_bytes(b"probe-image")

            with self.assertRaisesRegex(RuntimeError, "requires build provenance"):
                self.runner.load_build_provenance(image, "sticks3")

    def test_reused_image_rejects_changed_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base.bin"
            image = root / "uiflow2-ui-test.bin"
            base.write_bytes(b"official-base")
            image.write_bytes(b"probe-image")
            device = {
                "id": "sticks3",
                "vfs_offset": "0x641000",
                "vfs_size": "0x1BE000",
                "flash_size": "0x800000",
            }
            self.runner.write_build_provenance(image, base, device)
            image.write_bytes(b"different-image")

            with self.assertRaisesRegex(RuntimeError, "image hash mismatch"):
                self.runner.load_build_provenance(image, "sticks3")

    def test_provenance_sidecar_is_stable_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base.bin"
            image = root / "uiflow2-ui-test.bin"
            base.write_bytes(b"official-base")
            image.write_bytes(b"probe-image")
            device = {
                "id": "nanoc6",
                "vfs_offset": "0x371000",
                "vfs_size": "0x8D000",
                "flash_size": "0x400000",
            }
            self.runner.write_build_provenance(image, base, device)
            sidecar = self.runner.provenance_path(image)
            payload = json.loads(sidecar.read_text())

            self.assertEqual(payload["device_id"], "nanoc6")
            self.assertEqual(payload["image_sha256"], self.runner.sha256(image))


if __name__ == "__main__":
    unittest.main(verbosity=2)
