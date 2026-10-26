from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import sync_visual_models as sync


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1kAAAAASUVORK5CYII="
)


class VisualSnapshotImportTests(unittest.TestCase):
    def test_allowlist_requires_exact_commit_paths_hashes_and_notice(self):
        asset = "src/units/example/official-back.png"
        notice = b"Provider permission for public distribution, not MIT."
        files = {asset: PNG, "THIRD_PARTY_NOTICES.md": notice}
        with mock.patch.object(sync, "REVIEWED_RUNTIME_PNGS", {asset: hashlib.sha256(PNG).hexdigest()}), \
                mock.patch.object(sync, "RASTER_NOTICE_SHA256", hashlib.sha256(notice).hexdigest()):
            sync.reviewed_runtime_assets(sync.RASTER_SOURCE_COMMIT, list(files), files)
            for commit, names, values, message in (
                ("f" * 40, list(files), files, "reviewed commit/allowlist"),
                (sync.RASTER_SOURCE_COMMIT, [*files, "src/units/example/extra.png"], files,
                 "reviewed commit/allowlist"),
                (sync.RASTER_SOURCE_COMMIT, list(files), {**files, asset: PNG + b"changed"},
                 "reviewed Git object"),
                (sync.RASTER_SOURCE_COMMIT, list(files),
                 {**files, "THIRD_PARTY_NOTICES.md": b"changed permission"}, "redistribution notice"),
            ):
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    sync.reviewed_runtime_assets(commit, names, values)

    def test_runtime_assets_cannot_smuggle_other_binary_formats(self):
        asset = "src/units/example/official-back.png"
        files = {asset: b"not-a-png", "THIRD_PARTY_NOTICES.md": b"notice"}
        with mock.patch.object(sync, "REVIEWED_RUNTIME_PNGS", {asset: hashlib.sha256(files[asset]).hexdigest()}), \
                mock.patch.object(sync, "RASTER_NOTICE_SHA256", hashlib.sha256(b"notice").hexdigest()), \
                self.assertRaisesRegex(ValueError, "not a PNG"):
            sync.reviewed_runtime_assets(sync.RASTER_SOURCE_COMMIT, list(files), files)

    def test_static_dynamic_and_url_resources_are_closed_without_execution(self):
        files = {
            "src/index.js": b"import './model.js'; export const load=()=>import('./model.js');",
            "src/model.js": b"import * as THREE from 'three'; throw new Error('must not execute'); "
                            b"new URL('./official.png',import.meta.url);",
            "src/official.png": PNG,
        }
        closure = sync.resource_closure(files)
        self.assertEqual(closure["status"], "closed")
        self.assertEqual(closure["javascript_files"], 2)
        self.assertEqual(closure["runtime_pngs"], 1)
        self.assertEqual(closure["external_dependencies"], ["three"])
        for missing in ("src/model.js", "src/official.png"):
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "absent"):
                sync.resource_closure({name: data for name, data in files.items() if name != missing})

    def test_url_templates_cover_reviewed_assets_and_reject_unused_images(self):
        files = {"src/index.js": b"new URL(`./row-${r+1}.png`,import.meta.url)",
                 "src/row-1.png": PNG, "src/row-2.png": PNG}
        self.assertEqual(sync.resource_closure(files)["runtime_pngs"], 2)
        with self.assertRaisesRegex(ValueError, "lack a reviewed resource reference"):
            sync.resource_closure({**files, "src/unreferenced.png": PNG})

    def test_unreviewed_expressions_and_external_dependencies_fail_closed(self):
        for source, message in (
            (b"import('./missing.js')", "dependency is absent"),
            (b"import('three/addons/unknown.js')", "external visual dependency"),
            (b"import('https://example.test/code.js')", "external visual dependency"),
            (b"import(name)", "dynamic visual import expression"),
            (b"new URL(name,import.meta.url)", "resource URL expression"),
            (b"new URL(`./${functionCall()}.png`,import.meta.url)", "resource template"),
            (b"new URL('../../private.png',import.meta.url)", "escapes the runtime source tree"),
            (b"export {missing} from './missing.js'", "dependency is absent"),
        ):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, message):
                sync.resource_closure({"src/index.js": source})

    def test_syntax_errors_fail_before_writes(self):
        with self.assertRaisesRegex(ValueError, "could not parse"):
            sync.resource_closure({"src/index.js": b"export const broken = ;"})

    def test_snapshot_does_not_read_dirty_worktree_or_export_private_sources(self):
        commit = "a" * 40
        values = {name: b"notice" for name in sync.EXPLICIT_FILES}
        values.update({"package.json": b'{"dependencies":{"three":"0.186.1"}}',
                       "catalog/products.json": b'{"products":[{"id":"shell","category":"unit","name":"Shell","integration":{"moduleExport":"GroveModule"}}]}',
                       "src/index.js": b"export const example=1;", "licenses/upstream-MIT.txt": b"MIT",
                       "docs/research/private.txt": b"excluded", "raw-cad.stl": b"excluded"})

        def git_objects(source, *arguments):
            if arguments[0] == "rev-parse":
                return (commit + "\n").encode()
            if arguments[0] == "ls-tree":
                return ("\n".join(values) + "\n").encode()
            if arguments[0] == "show":
                self.assertTrue(arguments[1].startswith(commit + ":"))
                return values[arguments[1].split(":", 1)[1]]
            self.fail(f"unexpected Git operation: {arguments}")

        with mock.patch.object(sync, "git", side_effect=git_objects):
            files = sync.snapshot(Path("/does-not-exist"), commit)
        self.assertNotIn("docs/research/private.txt", files)
        self.assertNotIn("raw-cad.stl", files)
        self.assertIn("licenses/upstream-MIT.txt", files)
        self.assertIn('"moduleExport": "GroveModule"', files["runtime-index.js"].decode())
        self.assertEqual(json.loads(files["vendor-manifest.json"])["scope"],
                         "visual-only; firmware and electrical behavior belong to Device Service")

    def test_addon_check_requires_inventory_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "vendor"
            destination.mkdir()
            addon = root / "three/addons/geometries/DecalGeometry.js"
            addon.parent.mkdir(parents=True)
            addon.write_bytes(b"reviewed-addon")
            metadata = {"package_integrity": "sha512-reviewed", "addons": {
                "examples/jsm/geometries/DecalGeometry.js": {"destination": str(addon.relative_to(root)),
                    "sha256": hashlib.sha256(addon.read_bytes()).hexdigest()}}, "shared_three_files": {}}
            manifest = destination / "three-addon-manifest.json"
            manifest.write_text(json.dumps(metadata))
            files = {"package-lock.json": json.dumps({"packages": {"node_modules/three": {
                "integrity": "sha512-reviewed"}}}).encode()}
            with mock.patch.object(sync, "ROOT", root), mock.patch.object(sync, "DESTINATION", destination), \
                    mock.patch.object(sync, "THREE_ADDONS", {"examples/jsm/geometries/DecalGeometry.js": addon}):
                sync.three_addon(files, check=True)
                addon.write_bytes(b"tampered-addon")
                with self.assertRaisesRegex(SystemExit, "differs from the pinned package"):
                    sync.three_addon(files, check=True)
                metadata["addons"] = {}
                manifest.write_text(json.dumps(metadata))
                with self.assertRaisesRegex(SystemExit, "inventory differs"):
                    sync.three_addon(files, check=True)

    def test_vendored_snapshot_covers_reviewed_pngs_without_inferring_runtime_admission(self):
        manifest = json.loads((sync.DESTINATION / "vendor-manifest.json").read_text())
        files = {name: (sync.DESTINATION / name).read_bytes() for name in manifest["files"]}
        sync.reviewed_runtime_assets(manifest["source_commit"], list(files), files)
        self.assertEqual(sync.resource_closure(files), manifest["resource_closure"])
        self.assertEqual(set(manifest["runtime_assets"]["files"]), set(sync.REVIEWED_RUNTIME_PNGS))
        for name, entry in manifest["runtime_assets"]["files"].items():
            self.assertEqual(entry["sha256"], hashlib.sha256(files[name]).hexdigest())
            self.assertIn(manifest["source_commit"], entry["source_url"])
        units = json.loads((sync.ROOT / "platform/units/catalog.json").read_text())["units"]
        for visual in ("scroll", "roller485"):
            self.assertIn(visual, manifest["units"])
        self.assertNotIn("roller485", {unit["id"] for unit in units})
        scroll = next(unit for unit in units if unit['id'] == 'scroll')
        self.assertEqual(scroll['model_status'], 'partial')
        self.assertTrue(scroll['protocol']['gaps'])


if __name__ == "__main__":
    unittest.main()
