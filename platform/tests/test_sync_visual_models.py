from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest import mock

import sync_visual_models as sync


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1kAAAAASUVORK5CYII="
)


class VisualSnapshotImportTests(unittest.TestCase):
    def upstream_viewer(self):
        row = sync.REVIEWED_LOCAL_RUNTIME_PATCHES[0]
        patch = (sync.ROOT / row["patch"]).read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / row["target"]
            target.parent.mkdir(parents=True)
            target.write_bytes((sync.DESTINATION / row["target"]).read_bytes())
            result = subprocess.run(["git", "apply", "--reverse", "-"], input=patch,
                                    cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            upstream = target.read_bytes()
        self.assertEqual(hashlib.sha256(upstream).hexdigest(), row["upstream_sha256"])
        return row, upstream, patch

    def test_local_runtime_layer_preserves_exact_upstream_and_effective_identities(self):
        row, upstream, _ = self.upstream_viewer()
        files = {row["target"]: upstream}
        receipts = sync.apply_local_runtime_patches(files, sync.PINNED_COMMIT)
        self.assertEqual(files[row["target"]], (sync.DESTINATION / row["target"]).read_bytes())
        self.assertEqual(receipts[0]["upstream"]["sha256"], row["upstream_sha256"])
        self.assertEqual(receipts[0]["effective"]["sha256"], row["effective_sha256"])
        self.assertIn(b"#fitAfterResize", files[row["target"]])
        self.assertIn(b"pauseRendering()", files[row["target"]])
        self.assertIn(b"resumeRendering()", files[row["target"]])
        self.assertNotEqual(receipts[0]["upstream"]["sha256"], receipts[0]["effective"]["sha256"])
        self.assertEqual(set(files), {row["target"]})

    def test_local_runtime_patch_rejects_source_patch_target_and_result_drift(self):
        row, upstream, patch = self.upstream_viewer()
        with self.assertRaisesRegex(ValueError, "upstream commit"):
            sync.apply_local_runtime_patches({row["target"]: upstream}, "f" * 40)
        for files in ({}, {row["target"]: upstream + b"dirty"},
                      {row["target"]: (sync.DESTINATION / row["target"]).read_bytes()}):
            with self.assertRaisesRegex(ValueError, "upstream preimage"):
                sync.apply_local_runtime_patches(files, sync.PINNED_COMMIT)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / row["patch"]
            path.parent.mkdir(parents=True)
            for data, metadata, message in (
                (patch + b"tampered", row, "reviewed hash"),
                (patch.replace(row["target"].encode(), b"src/core/Unreviewed.js"),
                 {**row, "patch_sha256": hashlib.sha256(patch.replace(row["target"].encode(), b"src/core/Unreviewed.js")).hexdigest()},
                 "unreviewed target"),
                (patch, {**row, "effective_sha256": "0" * 64}, "effective file"),
            ):
                path.write_bytes(data)
                files = {row["target"]: upstream}
                with self.subTest(message=message), mock.patch.object(sync, "ROOT", root), \
                        mock.patch.object(sync, "REVIEWED_LOCAL_RUNTIME_PATCHES", (metadata,)), \
                        self.assertRaisesRegex(ValueError, message):
                    sync.apply_local_runtime_patches(files, sync.PINNED_COMMIT)
                self.assertEqual(files, {row["target"]: upstream}, "failed review cannot replace source bytes")
            path.unlink()
            path.symlink_to(sync.ROOT / row["patch"])
            with mock.patch.object(sync, "ROOT", root), self.assertRaisesRegex(ValueError, "symlink"):
                sync.apply_local_runtime_patches({row["target"]: upstream}, sync.PINNED_COMMIT)

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

    def test_unmounted_artwork_is_hash_checked_without_relaxing_resource_closure(self):
        mounted, excluded = "src/example/panel.png", "src/example/unmounted.png"
        files = {mounted: PNG, "THIRD_PARTY_NOTICES.md": b"notice"}
        unmounted = {excluded: PNG}
        with mock.patch.object(sync, "REVIEWED_RUNTIME_PNGS", {mounted: hashlib.sha256(PNG).hexdigest()}), \
                mock.patch.object(sync, "REVIEWED_UNMOUNTED_PNGS", {excluded: hashlib.sha256(PNG).hexdigest()}), \
                mock.patch.object(sync, "RASTER_NOTICE_SHA256", hashlib.sha256(b"notice").hexdigest()):
            sync.reviewed_runtime_assets(sync.RASTER_SOURCE_COMMIT, [*files, excluded], files, unmounted)
            for names, ignored, message in (
                ([*files, excluded], {excluded: PNG + b"changed"}, "reviewed Git object"),
                ([*files, excluded], {"src/example/unknown.png": PNG}, "unmounted runtime PNGs"),
                ([*files, excluded], {}, "reviewed commit/allowlist"),
                ([*files, excluded, "src/example/unknown.png"], unmounted, "reviewed commit/allowlist"),
            ):
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    sync.reviewed_runtime_assets(sync.RASTER_SOURCE_COMMIT, names, files, ignored)
        with self.assertRaisesRegex(ValueError, "lack a reviewed resource reference"):
            sync.resource_closure({"src/index.js": b"export const shell=1;", excluded: PNG})

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

        with mock.patch.object(sync, "git", side_effect=git_objects), \
                mock.patch.object(sync, "REVIEWED_LOCAL_RUNTIME_PATCHES", ()), \
                mock.patch.object(sync, "REVIEWED_GUIDE_FILES", {}), \
                mock.patch.object(sync, "REVIEWED_RUNTIME_LICENSES", {}), \
                mock.patch.object(sync, "REVIEWED_UNMOUNTED_PNGS", {}):
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


    def test_guide_allowlist_requires_exact_commit_paths_and_hashes(self):
        path = "docs/reviewed.md"
        body = b"Public visual guide."
        files = {path: body}
        with mock.patch.object(sync, "REVIEWED_GUIDE_FILES", {path: hashlib.sha256(body).hexdigest()}):
            sync.reviewed_guide_texts(sync.GUIDE_SOURCE_COMMIT, list(files), files)
            for commit, names, values, message in (
                ("f" * 40, list(files), files, "reviewed commit/allowlist"),
                (sync.GUIDE_SOURCE_COMMIT, [], files, "reviewed commit/allowlist"),
                (sync.GUIDE_SOURCE_COMMIT, list(files), {path: body + b"changed"}, "reviewed Git object"),
                (sync.GUIDE_SOURCE_COMMIT, list(files), {}, "reviewed Git object"),
            ):
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    sync.reviewed_guide_texts(commit, names, values)

    def test_guide_text_policy_rejects_credentials_identifiers_and_nontext(self):
        examples = (
            (b"-----BEGIN " + b"PRIVATE KEY-----", "private key"),
            (("sk-" + "x" * 24).encode(), "provider credential"),
            (("api_key=" + repr("example-credential")).encode(), "credential assignment"),
            (":".join(["02", "00", "00", "00", "00", "01"]).encode(), "MAC address"),
            (("/Users/" + "example/private.txt").encode(), "private user path"),
            (("http://" + "10.0.0.1/private").encode(), "private/authenticated URL"),
            (("https://" + "example:password@example.test/").encode(), "private/authenticated URL"),
            (b"binary\x00payload", "binary/control data"),
            (b"\xff", "not UTF-8 text"),
        )
        path = "docs/reviewed.md"
        for body, message in examples:
            with self.subTest(message=message), \
                    mock.patch.object(sync, "REVIEWED_GUIDE_FILES", {path: hashlib.sha256(body).hexdigest()}), \
                    self.assertRaisesRegex(ValueError, message):
                sync.reviewed_guide_texts(sync.GUIDE_SOURCE_COMMIT, [path], {path: body})
        body = b"Public development preview: http://127.0.0.1:5173/"
        with mock.patch.object(sync, "REVIEWED_GUIDE_FILES", {path: hashlib.sha256(body).hexdigest()}):
            sync.reviewed_guide_texts(sync.GUIDE_SOURCE_COMMIT, [path], {path: body})
        for path, body, message in (
            ("docs/reviewed.png", PNG, "not an allowed public text path"),
            ("artifacts/reviewed.json", b"not json", "not valid JSON"),
        ):
            with self.subTest(message=message), \
                    mock.patch.object(sync, "REVIEWED_GUIDE_FILES", {path: hashlib.sha256(body).hexdigest()}), \
                    self.assertRaisesRegex(ValueError, message):
                sync.reviewed_guide_texts(sync.GUIDE_SOURCE_COMMIT, [path], {path: body})

    def test_guide_relative_links_close_and_unknown_or_unreferenced_texts_fail(self):
        path = "artifacts/reviewed.json"
        body = b'{"status":"fixture"}'
        guides = {path: hashlib.sha256(body).hexdigest()}
        files = {name: b"No relative links." for name in sync.GUIDE_ENTRY_FILES}
        files.update({path: body, "docs/AGENT-INTEGRATION.md":
                      b'[evidence](../artifacts/reviewed.json) [code](../src/example.js) '
                      b'[external](https://example.test/) ![remote-example](unbundled-image.png)',
                      "src/example.js": b"throw new Error('not executed');"})
        with mock.patch.object(sync, "REVIEWED_GUIDE_FILES", guides):
            closure = sync.guide_resource_closure(files)
            self.assertEqual(closure["status"], "closed")
            self.assertEqual(closure["reviewed_additional_files"], 1)
            self.assertEqual(closure["referenced_files"], len(sync.GUIDE_ENTRY_FILES) + 2)
            with self.assertRaisesRegex(ValueError, "reference is absent"):
                sync.guide_resource_closure({**files, "docs/AGENT-INTEGRATION.md": b'[unknown](unreviewed.md)'})
            with self.assertRaisesRegex(ValueError, "unreviewed visual guide link expression"):
                sync.guide_resource_closure({**files, "docs/AGENT-INTEGRATION.md": b'[unknown](unreviewed file.md)'})
            with self.assertRaisesRegex(ValueError, "lack a root-guide reference"):
                sync.guide_resource_closure({**files, "docs/AGENT-INTEGRATION.md": b"No links."})
            with self.assertRaisesRegex(ValueError, "entry/reference is absent"):
                sync.guide_resource_closure({name: value for name, value in files.items() if name != "docs/INTEGRATION.md"})

    def test_vendored_snapshot_covers_reviewed_pngs_without_inferring_runtime_admission(self):
        manifest = json.loads((sync.DESTINATION / "vendor-manifest.json").read_text())
        files = {name: (sync.DESTINATION / name).read_bytes() for name in manifest["files"]}
        sync.reviewed_runtime_assets(manifest["source_commit"], list(files), files)
        sync.reviewed_guide_texts(manifest["documentation_source_commit"], list(files), files)
        self.assertEqual(sync.guide_resource_closure(files), manifest["documentation_closure"])
        self.assertEqual(set(manifest["reviewed_guide_texts"]), set(sync.REVIEWED_GUIDE_FILES))
        self.assertIn("historical preparation baseline", manifest["source_manifest_scope"])
        self.assertIn("effective vendored bytes", manifest["file_hash_scope"])
        self.assertEqual(manifest["upstream_resource_closure"], manifest["resource_closure"])
        self.assertEqual(len(manifest["local_runtime_patches"]), 1)
        for layer in manifest["local_runtime_patches"]:
            target = layer["target"]
            self.assertEqual(layer["effective"], manifest["files"][target])
            self.assertNotEqual(layer["upstream"]["sha256"], layer["effective"]["sha256"])
            self.assertEqual(layer["patch_sha256"], hashlib.sha256((sync.ROOT / layer["patch"]).read_bytes()).hexdigest())
        for name, entry in manifest["reviewed_guide_texts"].items():
            self.assertEqual(entry["sha256"], hashlib.sha256(files[name]).hexdigest())
            self.assertIn(manifest["documentation_source_commit"], entry["source_url"])
        self.assertEqual(sync.resource_closure(files), manifest["resource_closure"])
        runtime_devices = {item["id"] for item in json.loads(sync.RUNTIME_DEVICE_CATALOG.read_text())["devices"]}
        self.assertEqual(set(manifest["visual_only_controllers"]), set(manifest["controllers"]) - runtime_devices)
        self.assertEqual(set(manifest["runtime_assets"]["files"]), set(sync.REVIEWED_RUNTIME_PNGS))
        self.assertEqual(set(manifest["excluded_runtime_assets"]), set(sync.REVIEWED_UNMOUNTED_PNGS))
        for name, expected in sync.REVIEWED_UNMOUNTED_PNGS.items():
            self.assertEqual(manifest["excluded_runtime_assets"][name]["sha256"], expected)
            self.assertNotIn(name, manifest["files"])
            self.assertFalse((sync.DESTINATION / name).exists())
        for name, expected in sync.REVIEWED_RUNTIME_LICENSES.items():
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(), expected)
            self.assertIn(b"Copyright (c) 2021 M5Stack", files[name])
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

    def test_expanded_host_models_and_runtime_inventory_are_separately_pinned(self):
        manifest = json.loads((sync.DESTINATION / "vendor-manifest.json").read_text())
        self.assertEqual(manifest["source_commit"], "4879ab51eb8bb11ce024e670ae6880529e3d0f42")
        self.assertEqual(manifest["source_commit"], sync.PINNED_COMMIT)
        self.assertEqual(manifest["documentation_source_commit"],
                         "3681a6482aff96501d44659ba5a1603246f1fe1f")
        families = {
            "atom-lite", "atom-matrix", "atom-matrix-v11", "atom-echo", "atom-echos3r", "atomu",
            "atoms3", "atoms3-lite", "atoms3u", "atoms3r", "atoms3r-cam", "atoms3r-ext", "atoms3r-m12",
            "atoms3r-ai-chatbot", "atoms3r-cam-ai-chatbot", "atoms3r-m12-volcengine-kit",
            "m5stick", "stickv", "stickc", "stickc-plus", "stickc-plus-se", "stickc-plus2", "stickt2", "sticks3",
        }
        added = families - {"atom-lite", "atom-matrix", "atoms3-lite", "atoms3r", "sticks3"}
        added |= {"dial", "basic-v27"}
        self.assertTrue(families <= set(manifest["controllers"]))
        runtime_devices = {item["id"] for item in json.loads(sync.RUNTIME_DEVICE_CATALOG.read_text())["devices"]}
        self.assertEqual(added & set(manifest["visual_only_controllers"]), added - runtime_devices,
                         "Visual-only inventory follows explicit runtime records, never model stage or firmware PASS")
        products = json.loads((sync.DESTINATION / "catalog/products.json").read_text())["products"]
        by_id = {product["id"]: product for product in products}
        for identity in added:
            self.assertEqual(by_id[identity]["stage"], "modeled")
            self.assertEqual(by_id[identity]["category"], "controller")
            self.assertIn(by_id[identity]["entry"], manifest["files"])


if __name__ == "__main__":
    unittest.main()
