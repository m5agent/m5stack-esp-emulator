from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import bootstrap_browser_runtime as bootstrap
import build_public_site as public


class BrowserBootstrapTests(unittest.TestCase):
    def test_inherited_flags_and_wrappers_cannot_change_reported_compiler_policy(self):
        inherited = {name:"fixture-override" for name in ("CARGO_ENCODED_RUSTFLAGS", "RUSTC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS")}
        with mock.patch.dict(os.environ,inherited):
            environment = bootstrap.build_environment(Path("/tmp/test-runtime-cache"))
        for name in inherited:
            if name != "RUSTFLAGS":
                self.assertNotIn(name,environment)
        self.assertEqual(environment["RUSTFLAGS"],bootstrap.RUST_FLAGS)
        self.assertEqual(environment["CARGO_PROFILE_RELEASE_DEBUG"],"0")
        self.assertEqual(environment["CARGO_PROFILE_RELEASE_STRIP"],"debuginfo")

    def test_provenance_uses_the_built_git_objects_instead_of_mutable_worktree(self):
        source = Path("/does-not-need-a-worktree")
        with mock.patch.object(bootstrap.subprocess,"check_output",return_value=b"pinned-lock") as show, mock.patch.object(bootstrap,"command",return_value="pinned-tree") as tree:
            identity = bootstrap.source_identity(source)
        self.assertEqual(identity["cargo_lock_sha256"],hashlib.sha256(b"pinned-lock").hexdigest())
        self.assertEqual(identity["source_tree"],"pinned-tree")
        show.assert_called_once_with(["git","show",f"{bootstrap.SOURCE_COMMIT}:Cargo.lock"],cwd=source)
        tree.assert_called_once_with("git","rev-parse",f"{bootstrap.SOURCE_COMMIT}^{{tree}}",cwd=source)

    def test_worker_glue_is_exact_reviewed_source_and_has_only_local_imports(self):
        directory = bootstrap.ROOT / "platform/web/vendor/esp32sim"
        source = json.loads((directory / "source.json").read_text())
        self.assertEqual(source["commit"], bootstrap.SOURCE_COMMIT)
        self.assertEqual(source["license"], "MIT")
        self.assertEqual(set(source["files"]), {"worker.js", "jit.mjs", "pacing.mjs", "experiments.mjs", "LICENSE"})
        for name, row in source["files"].items():
            data = (directory / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), row["sha256"])
            self.assertEqual(len(data), row["bytes"])
        worker = (directory / "worker.js").read_text()
        self.assertIn("WebAssembly.instantiate", worker)
        self.assertNotIn("fetch(", worker)
        self.assertNotIn("new WebSocket", worker)

    def test_diagnostic_lane_needs_explicit_export_and_asset_hashes_are_checked(self):
        wasm, rom = b"\0asm\x01\0\0\0", b"unit-test-rom-placeholder"
        digest = hashlib.sha256(rom).hexdigest()
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(bootstrap, "ROM_SHA256", digest):
            root = Path(directory)
            bootstrap.prepare_runtime(root, wasm, rom, {"kind":"downloaded-diagnostic","rebuild_verified":False})
            with self.assertRaisesRegex(ValueError, "requires a source build"):
                public.browser_runtime_files(root)
            manifest, files = public.browser_runtime_files(root, allow_diagnostic=True)
            self.assertFalse(manifest["firmware_bundled"])
            self.assertEqual(files["esp32sim.wasm"], wasm)
            self.assertIn("ROM_LICENSE", files)
            (root / "esp32sim.wasm").write_bytes(wasm + b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256 or size"):
                public.browser_runtime_files(root, allow_diagnostic=True)

    def test_rom_and_wasm_admission_fail_closed_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime"
            with self.assertRaisesRegex(ValueError, "WebAssembly"):
                bootstrap.prepare_runtime(path, b"html instead of wasm", b"bad-rom", {})
            self.assertFalse(path.exists())
            with self.assertRaisesRegex(ValueError, "reviewed ELF"):
                bootstrap.prepare_runtime(path, b"\0asm\x01\0\0\0", b"bad-rom", {})
            self.assertFalse(path.exists())
            with self.assertRaisesRegex(ValueError, "provide --rom"):
                bootstrap.acquire_rom(None)


if __name__ == "__main__":
    unittest.main()
