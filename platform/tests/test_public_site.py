from __future__ import annotations

import gzip
import json
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import build_public_site as public


class PublicSiteTests(unittest.TestCase):
    def test_cc1101_official_sources_require_pinned_patch_and_exact_workbench(self):
        workbench = json.loads((public.ROOT / "platform/web/uiflow-workbench-profiles.json").read_text())
        preview = {"path": "patches/qemu-wasm-probe/0045-cardputer-adv-cc1101-peer.patch",
                   "sha256": "feeae444d6f29dce4780b366759d66a727a850f22daf12012e37c31ba80381a2"}
        runtime = {"source": {"patches": [preview]}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "input"
            source_folder = Path("tests/browser-qemu/uiflow_workbench")
            (root / source_folder).mkdir(parents=True)
            output = Path(directory) / "output"
            for role in ("tx", "rx"):
                filename = f"cc1101_cap_rf_{role}_example.py"
                shutil.copyfile(public.ROOT / source_folder / filename, root / source_folder / filename)
            for disabled, profiles in (
                ({}, workbench),
                ({"source": {"patches": [preview, preview]}}, workbench),
                (runtime, {"profiles": [row for row in workbench["profiles"] if row["deviceId"] != "cardputer-adv"]}),
            ):
                self.assertEqual(public.stage_qemu_cc1101_examples(root, output, disabled, profiles), {})
                self.assertFalse(output.exists())
            examples = public.stage_qemu_cc1101_examples(root, output, runtime, workbench)
            self.assertEqual(set(examples), {"rx", "tx"})
            self.assertEqual(set(path.name for path in output.rglob("*.py")),
                             {"cc1101_cap_rf_rx_example.py", "cc1101_cap_rf_tx_example.py"})
            for role, row in examples.items():
                actual = (output / row["path"]).read_bytes()
                self.assertEqual(actual, (public.ROOT / source_folder / f"cc1101_cap_rf_{role}_example.py").read_bytes())
                self.assertEqual(hashlib.sha256(actual).hexdigest(), row["sha256"])
                self.assertEqual(len(actual), row["bytes"])
            (root / source_folder / "cc1101_cap_rf_rx_example.py").write_text("pass")
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                public.stage_qemu_cc1101_examples(root, output, runtime, workbench)

    def test_sx1262_exports_four_original_examples_only_with_its_locked_patch(self):
        workbench = json.loads((public.ROOT / "platform/web/uiflow-workbench-profiles.json").read_text())
        peer = {"path": "patches/qemu-wasm-probe/0046-cardputer-adv-sx1262-cap-peer.patch",
                "sha256": "0c7b037ed3e95102c8d588d042767a0d61591946323f21a9f87a8e02f0c90238"}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            off = {"source": {"patches": [{**peer, "sha256": "0" * 64}]}}
            self.assertEqual(public.stage_qemu_sx1262_examples(public.ROOT, output, off, workbench), {})
            self.assertFalse(output.exists())
            runtime = {"source": {"patches": [peer]}}
            examples = public.stage_qemu_sx1262_examples(public.ROOT, output, runtime, workbench)
            self.assertEqual(set(examples), {"lora1262-rf-tx", "lora1262-rf-rx", "lora868-rf-tx", "lora868-rf-rx"})
            for row in examples.values():
                actual = (output / row["path"]).read_bytes()
                original = public.ROOT / "tests/browser-qemu/uiflow_workbench" / Path(row["path"]).name
                self.assertEqual(actual, original.read_bytes())
                self.assertEqual(len(actual), row["bytes"])
                self.assertEqual(hashlib.sha256(actual).hexdigest(), row["sha256"])

    def test_epd_quality_patterns_match_pinned_fixture_sources(self):
        subprocess.run([sys.executable, str(public.ROOT / "tests/browser-qemu/board_display/epd_oracle.py"), "--check"],
                       check=True, capture_output=True, text=True)

    def test_littlefs_named_wallclock_variant_is_complete_and_source_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_names = ["littlefs.mjs", "littlefs.wasm", "LICENSE.littlefs", "LICENSE.composer", "LICENSE.emscripten",
                          "LICENSE.musl", "fixture/boot.py", "fixture/main.py", "source.zip"]
            rows = {}
            for name in base_names:
                raw = name.encode()
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                rows[name] = {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            contract = json.loads((public.ROOT / "tests/browser-qemu/cores3_lvgl_wallclock/contract.json").read_text())
            identity = contract["identity"]
            source_assets = {}
            for name in identity["files"]:
                path = f"fixtures/cores3-lvgl-wallclock/{name}"
                raw = (public.ROOT / "tests/browser-qemu/cores3_lvgl_wallclock" / name).read_bytes()
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                key = "wallclock." + name
                rows[key] = {"path": path, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                source_assets[name] = key
            variant = {"id": contract["fixture"], "clock_divisor": 1, "scheduler_candidate": "sdk-python-single-schedule-v1",
                       "source_sha256": identity["source_sha256"], "source_files": identity["files"], "source_assets": source_assets,
                       "vfs": {"offset": 11141120, "size": 4980736},
                       **{key: {name: identity[key][name] for name in ("size", "sha256")}
                          for key in ("raw_base", "normalized_base", "composed_firmware")}}
            manifest = {"schema_version": 1, "kind": "m5stack-browser-littlefs", "source": {"commit": "6cb4e86540eca0d9ba62500a298385c9d863c8be"},
                        "build": {"kind": "source-build"}, "firmware_bundled": False, "rom_bundled": False,
                        "assets": rows, "fixtures": {contract["fixture"]: variant}}
            def save():
                (root / "manifest.json").write_text(json.dumps(manifest))
            save()
            self.assertEqual(len(public.littlefs_runtime_files(root)), len(base_names) + 3 + 1)
            variant["clock_divisor"] = 8
            save()
            with self.assertRaisesRegex(ValueError, "variant identity"):
                public.littlefs_runtime_files(root)
            variant["clock_divisor"] = 1
            row = rows.pop("wallclock.main.py")
            save()
            with self.assertRaisesRegex(ValueError, "source asset"):
                public.littlefs_runtime_files(root)
            rows["wallclock.main.py"] = row
            manifest["fixtures"]["unknown"] = variant
            save()
            with self.assertRaisesRegex(ValueError, "unknown"):
                public.littlefs_runtime_files(root)

    def test_qemu_board_availability_does_not_inherit_public_admission(self):
        registry = json.loads((public.ROOT / "platform/web/qemu-browser-profiles.json").read_text())
        # Admission policy is tested with an isolated registry so subsequent
        # evidence-backed promotions cannot silently change this negative case.
        for row in registry["profiles"]:
            row["admission"] = "public" if row["deviceId"] == "cores3" else "candidate"
        source_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, source_root)
        registry_path = source_root / "platform/web/qemu-browser-profiles.json"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(json.dumps(registry))
        runtime = {"source": registry["source"], "profiles": ["cores3"], "compiled_profiles": [row["deviceId"] for row in registry["profiles"]]}
        selected, browser = public.qemu_site_profiles(source_root, runtime)
        self.assertEqual([row["deviceId"] for row in selected["profiles"]], ["cores3"])
        self.assertEqual([row["id"] for row in browser["devices"]], ["cores3"])
        promoted = json.loads(json.dumps(registry))
        next(row for row in promoted["profiles"] if row["deviceId"] == "atoms3r")["admission"] = "public"
        registry_path.write_text(json.dumps(promoted))
        admitted, _ = public.qemu_site_profiles(source_root, runtime)
        self.assertEqual({row["deviceId"] for row in admitted["profiles"]}, {"cores3", "atoms3r"}, "public registry entries must also be compiled")
        runtime_without_atom = {**runtime, "compiled_profiles": ["cores3"]}
        admitted, _ = public.qemu_site_profiles(source_root, runtime_without_atom)
        self.assertEqual([row["deviceId"] for row in admitted["profiles"]], ["cores3"])
        registry_path.write_text(json.dumps(registry))
        selected, browser = public.qemu_site_profiles(source_root, runtime, ("atoms3r",))
        self.assertEqual({row["deviceId"] for row in selected["profiles"]}, {"cores3", "atoms3r"})
        self.assertEqual(next(row["browser"]["status"] for row in browser["devices"] if row["id"] == "atoms3r"), "candidate")
        for requested in (("nanoc6",), ("cores3",), ("atoms3r", "atoms3r")):
            with self.subTest(requested=requested), self.assertRaises(ValueError):
                public.qemu_site_profiles(source_root, runtime, requested)
        runtime["compiled_profiles"] = ["cores3"]
        with self.assertRaisesRegex(ValueError, "not available"):
            public.qemu_site_profiles(source_root, runtime, ("atoms3r",))
        self.assertNotIn("--qemu-candidate-profile", (public.ROOT / ".github/workflows/public-site.yml").read_text())

    def test_littlefs_export_requires_source_pin_hashes_and_all_licenses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ["littlefs.mjs", "littlefs.wasm", "LICENSE.littlefs", "LICENSE.composer",
                     "LICENSE.emscripten", "LICENSE.musl", "fixture/boot.py", "fixture/main.py", "source.zip"]
            rows = {}
            for name in names:
                path = root / name
                path.parent.mkdir(exist_ok=True)
                data = ("reviewed-source-fixture:" + name).encode()
                path.write_bytes(data)
                rows[name] = {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            manifest = {"schema_version": 1, "kind": "m5stack-browser-littlefs", "source": {"commit": "6cb4e86540eca0d9ba62500a298385c9d863c8be"},
                        "build": {"kind": "source-build"}, "firmware_bundled": False, "rom_bundled": False, "assets": rows}
            def save():
                (root / "manifest.json").write_text(json.dumps(manifest))
            save()
            self.assertEqual(set(public.littlefs_runtime_files(root)), set(names) | {"manifest.json"})
            with self.assertRaisesRegex(ValueError, "sized-partition"):
                public.littlefs_runtime_files(root, require_sized_mount=True)
            manifest["partition_mount"] = {"export": "_m5_lfs_mount_sized"}
            save()
            self.assertEqual(set(public.littlefs_runtime_files(root, require_sized_mount=True)), set(names) | {"manifest.json"})
            license_row = rows.pop("LICENSE.musl")
            save()
            with self.assertRaisesRegex(ValueError, "incomplete"):
                public.littlefs_runtime_files(root)
            rows["LICENSE.musl"] = license_row
            (root / "littlefs.wasm").write_bytes(b"tampered")
            save()
            with self.assertRaisesRegex(ValueError, "hash or size"):
                public.littlefs_runtime_files(root)
            manifest["source"]["commit"] = "0" * 40
            save()
            with self.assertRaisesRegex(ValueError, "manifest mismatch"):
                public.littlefs_runtime_files(root)

    def fixture(self, root: Path) -> None:
        files = {
            "platform/web/index.html": '<script type="module" src="/platform/web/public.js"></script>',
            "platform/web/public.js": "export const url='/devices/catalog.json';",
            "platform/web/vendor/m5stack-models/catalog/products.json": '{"products":[{"id":"pir","category":"unit"}]}',
            "devices/catalog.json": '{"devices":[]}',
            "devices/group/core/device.json": '{"shell":{"reference_image":"/platform/web/photo.png"}}',
            "platform/units/catalog.json": '{"units":[]}',
            "platform/units/host-ports.json": '{"hosts":[]}',
            "platform/units/runtime-profiles.json": '{"units":{}}',
            "platform/web/private.bin": 'not-public',
            "platform/web/observatory.html": 'local-only-observer',
            "platform/web/observatory-scene.js": 'local-only-scene',
            "platform/web/.private": 'not-public',
            ".work/token": 'not-public',
        }
        for name, value in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)

    def test_export_is_reproducible_prefix_safe_and_has_no_firmware(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            self.fixture(root)
            output = Path(directory) / "site"
            first = public.build_site(root, output, base_path="/sim/", service_url="https://service.example.test/api/v1")
            self.assertEqual(public.build_site(root, output, base_path="/sim/", service_url="https://service.example.test/api/v1"), first)
            self.assertIn('src="/sim/platform/web/public.js"', (output / "index.html").read_text())
            self.assertIn("/sim/devices/catalog.json", (output / "platform/web/public.js").read_text())
            self.assertEqual(json.loads((output / "site-config.json").read_text())["service_url"], "https://service.example.test")
            self.assertFalse(first["firmware_bundled"])
            self.assertFalse((output / "platform/web/private.bin").exists())
            self.assertFalse((output / "platform/web/observatory.html").exists())
            self.assertFalse((output / "platform/web/observatory-scene.js").exists())
            self.assertFalse((output / ".work").exists())
            self.assertTrue((output / ".nojekyll").is_file())

    def test_export_workbench_example_keeps_the_exact_source_for_selected_cores3(self):
        source_path = "tests/browser-qemu/uiflow_workbench/cores3_display_example.py"
        asset_path = "platform/runtime/qemu-probe/fixture/cores3_display_example.py"
        workbench_path = "platform/web/uiflow-workbench-profiles.json"
        source_bytes = (public.ROOT / source_path).read_bytes()
        source_sha = "03869b2d115675642900d900a9bc9c442a75a92b99db05883948876a22cbfe3d"
        self.assertEqual(len(source_bytes), 1729)
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), source_sha)
        example = {
            "id": "cores3-display", "deviceId": "cores3", "version": "2.5.5",
            "baseUrl": "https://example.test/base.bin", "baseSHA256": "a" * 64,
            "baseBytes": 16773120, "baseFileCount": 17, "firmwareSHA256": "b" * 64,
            "source": {"path": source_path, "bytes": 1729, "sha256": source_sha},
        }
        with tempfile.TemporaryDirectory() as directory:
            root, output = (Path(directory) / name for name in ("source", "site"))
            self.fixture(root)
            source = root / source_path
            source.parent.mkdir(parents=True)
            source.write_bytes(source_bytes)
            (source.parent / "unreviewed.py").write_text("print('excluded')\n")
            (root / "platform/web/unreviewed.py").write_text("print('excluded')\n")
            workbench = root / workbench_path
            old = {"profiles": [{"deviceId": "cores3"}, {"deviceId": "cardputer-adv"}]}
            workbench.write_bytes(public.encode_json(old))
            runtime = {"engine": "qemu-wasm", "build": {"kind": "source-build"}}
            registry = {
                "profiles": [{"deviceId": "cores3", "admission": "public"}],
            }
            with (patch.object(public, "qemu_runtime_files", return_value=(runtime, {})),
                  patch.object(public, "qemu_site_profiles", return_value=(registry, {}))):
                public.build_site(root, output, qemu_runtime=root)
                self.assertNotIn("examples", json.loads((output / workbench_path).read_bytes()))
                workbench.write_bytes(public.encode_json({**old, "examples": [example]}))
                manifest = public.build_site(root, output, qemu_runtime=root)
                exported = json.loads((output / workbench_path).read_bytes())
                self.assertEqual(exported, {"profiles": [{"deviceId": "cores3"}], "examples": [example]})
                self.assertEqual((output / asset_path).read_bytes(), source_bytes)
                self.assertIn({"path": asset_path, "bytes": 1729, "sha256": source_sha}, manifest["assets"])
                self.assertFalse(any(row["path"].endswith(("unreviewed.py", ".bin")) for row in manifest["assets"]))
                self.assertFalse(manifest["firmware_bundled"])

                for untrusted_path in ("../outside.py", "tests/browser-qemu/uiflow_workbench/unreviewed.py"):
                    invalid = {**example, "source": {**example["source"], "path": untrusted_path}}
                    workbench.write_bytes(public.encode_json({**old, "examples": [invalid]}))
                    with self.subTest(path=untrusted_path), self.assertRaisesRegex(ValueError, "example source"):
                        public.build_site(root, output, qemu_runtime=root)
                workbench.write_bytes(public.encode_json({**old, "examples": [example]}))
                source.write_bytes(b"x" + source_bytes[1:])
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    public.build_site(root, output, qemu_runtime=root)
                self.assertEqual((output / asset_path).read_bytes(), source_bytes)

                registry["profiles"] = [{"deviceId": "cardputer-adv", "admission": "public"}]
                public.build_site(root, output, qemu_runtime=root)
                self.assertEqual(json.loads((output / workbench_path).read_bytes()), {
                    "profiles": [{"deviceId": "cardputer-adv"}], "examples": [],
                })
                self.assertFalse((output / asset_path).exists())

    def test_cores3_audio_requires_explicit_preview_and_both_runtime_patches(self):
        with tempfile.TemporaryDirectory() as directory:
            root, output = (Path(directory) / name for name in ("source", "site"))
            self.fixture(root)
            (root / "platform/web/uiflow-workbench-profiles.json").write_bytes(public.encode_json({"profiles": []}))
            with self.assertRaisesRegex(ValueError, "primary QEMU runtime"):
                public.build_site(root, output, qemu_cores3_audio=True)
            patches = []
            runtime = {"engine": "qemu-wasm", "build": {"kind": "source-build"}, "source": {"patches": patches}}
            registry = {"profiles": [{"deviceId": "cores3", "admission": "public"}]}
            for index, name in enumerate(("cores3-i2s-tx-descriptor-pacing", "cores3-i2s-web-pcm-stream"), 45):
                patches.append({"path": f"patches/qemu-wasm-probe/{index:04d}-{name}.patch", "sha256": "a" * 64})
            with (patch.object(public, "qemu_runtime_files", return_value=(runtime, {})),
                  patch.object(public, "qemu_site_profiles", return_value=(registry, {}))):
                manifest = public.build_site(root, output, qemu_runtime=root)
                self.assertTrue(manifest["publication_eligible"])
                self.assertNotIn("browser_cores3_audio", json.loads((output / "site-config.json").read_text()))
                manifest = public.build_site(root, output, qemu_runtime=root, qemu_cores3_audio=True)
                config = json.loads((output / "site-config.json").read_text())
                self.assertIs(config["browser_cores3_audio"], True)
                self.assertFalse(manifest["publication_eligible"])
                self.assertFalse(config["publication_eligible"])
                patches.pop()
                with self.assertRaisesRegex(ValueError, "pacing and streaming"):
                    public.build_site(root, output, qemu_runtime=root, qemu_cores3_audio=True)

    def test_export_qemu_sd_media_is_pinned_deduplicated_and_optional(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            root, media, output = (work / name for name in ("source", "media", "site"))
            self.fixture(root)
            media.mkdir()
            raw = b"M5Stack documentation SD fixture".ljust(512, b"\0")
            raw_sha = hashlib.sha256(raw).hexdigest()
            for name in ("first.img", "second.img"):
                (media / name).write_bytes(raw)
            bindings = [
                {"device": "cores3", "firmware_sha256": "a" * 64, "image": "first.img",
                 "bytes": len(raw), "sha256": raw_sha},
                {"device": "cardputer-adv", "firmware_sha256": "b" * 64, "image": "second.img",
                 "bytes": len(raw), "sha256": raw_sha},
            ]
            manifest = media / "manifest.json"
            manifest.write_bytes(public.encode_json({"schema_version": 1, "examples": bindings}))
            # Keep the actual registry selection path while using a tiny source-build stub.
            qemu_source = {"commit": "a" * 40}
            qemu_profiles = []
            for row in bindings:
                device = row["device"]
                qemu_profiles.append({
                    "deviceId": device, "board": device, "admission": "public", "clockDivisor": 8,
                    "target": "xtensa-softmmu", "limitations": [],
                    "reference": {"name": device, "url": "", "sha256": row["firmware_sha256"]},
                })
            (root / "platform/web/qemu-browser-profiles.json").write_bytes(public.encode_json({
                "schema_version": 1, "engine": "qemu-wasm", "target": "xtensa-softmmu",
                "source": qemu_source, "profiles": qemu_profiles,
            }))
            (root / "platform/web/uiflow-workbench-profiles.json").write_text('{"profiles":[]}')
            runtime = {
                "engine": "qemu-wasm", "source": qemu_source, "build": {"kind": "source-build"},
                "compiled_profiles": [row["deviceId"] for row in qemu_profiles],
            }
            with self.assertRaisesRegex(ValueError, "requires the primary QEMU runtime"):
                public.build_site(root, output, qemu_sd_media=media)
            with patch.object(public, "qemu_runtime_files", return_value=(runtime, {"runtime.json": b"{}"})):
                default = public.build_site(root, output, qemu_runtime=work)
                baseline_config = (output / "site-config.json").read_bytes()
                self.assertNotIn("browser_sd_examples", json.loads(baseline_config))
                seeded = public.build_site(root, output, qemu_runtime=work, qemu_sd_media=media)
                config = json.loads((output / "site-config.json").read_bytes())
                self.assertEqual(config, json.loads((output / "platform/web/site-config.json").read_bytes()))
                image = f"platform/runtime/qemu/sd-media/{raw_sha}.img.gz"
                compressed = (output / image).read_bytes()
                self.assertEqual(gzip.decompress(compressed), raw)
                self.assertEqual(compressed[:8], b"\x1f\x8b\x08\x00\x00\x00\x00\x00")
                compressed_identity = {
                    "gzip_bytes": len(compressed), "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
                }
                self.assertEqual(config.pop("browser_sd_examples"), [
                    {**{key: value for key, value in row.items() if key != "image"}, **compressed_identity}
                    for row in reversed(bindings)
                ])
                self.assertEqual(config, json.loads(baseline_config))
                self.assertTrue(seeded["publication_eligible"])
                self.assertFalse(seeded["firmware_bundled"])
                added = {row["path"] for row in seeded["assets"]} - {row["path"] for row in default["assets"]}
                self.assertEqual(added, {image})
                self.assertIn({
                    "path": image, "bytes": compressed_identity["gzip_bytes"],
                    "sha256": compressed_identity["gzip_sha256"],
                }, seeded["assets"])

                manifest.write_bytes(public.encode_json({
                    "schema_version": 1, "examples": list(reversed(bindings)),
                }))
                self.assertEqual(public.build_site(root, output, qemu_runtime=work, qemu_sd_media=media), seeded)
                (media / "first.img").write_bytes(b"changed".ljust(512, b"\0"))
                with self.assertRaisesRegex(ValueError, "SHA-256 or size mismatch"):
                    public.build_site(root, output, qemu_runtime=work, qemu_sd_media=media)
                self.assertEqual(json.loads((output / public.MANIFEST_NAME).read_bytes()), seeded)
                self.assertEqual(public.build_site(root, output, qemu_runtime=work), default)
                self.assertFalse((output / image).exists())

    def test_qemu_sd_media_rejects_unadmitted_invalid_and_symlink_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            media, runtime = work / "media", work / "runtime"
            media.mkdir()
            raw = hashlib.shake_256(b"deterministic incompressible fixture").digest(512)
            row = {
                "device": "cores3", "firmware_sha256": "a" * 64, "image": "card.img",
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            }
            good = {"schema_version": 1, "examples": [row]}
            manifest = media / "manifest.json"
            image = media / "card.img"
            image.write_bytes(raw)
            registry = {"profiles": [
                {"deviceId": "cores3", "admission": "public"},
                {"deviceId": "cardputer-adv", "admission": "candidate"},
                {"deviceId": "core2", "admission": "public"},
            ]}
            invalid = [
                ({**good, "extra": None}, "manifest"),
                ({**good, "schema_version": True}, "manifest"),
                ({**good, "examples": []}, "empty examples"),
                ({**good, "examples": [row, row]}, "duplicate device and firmware"),
            ]
            for change, error in (
                ({"other": True}, "fields"), ({"device": "cardputer-adv"}, "admitted"),
                ({"device": "core2"}, "admitted"), ({"device": []}, "admitted"),
                ({"firmware_sha256": "short"}, "SHA-256"), ({"sha256": "A" * 64}, "SHA-256"),
                ({"image": "../card.img"}, "bare"), ({"image": "child\\card.img"}, "bare"),
                ({"image": "C:card.img"}, "bare"), ({"image": "card.txt"}, "bare"),
                ({"bytes": True}, "multiple of 512"), ({"bytes": 513}, "multiple of 512"),
                ({"bytes": 64 * 1024 * 1024 + 512}, "64 MiB"), ({"bytes": 1024}, "size mismatch"),
            ):
                invalid.append(({**good, "examples": [{**row, **change}]}, error))
            for index, (content, error) in enumerate(invalid):
                with self.subTest(content=content), self.assertRaisesRegex(ValueError, error):
                    manifest.write_bytes(public.encode_json(content))
                    target = work / f"invalid-{index}"
                    target.mkdir()
                    public.stage_qemu_sd_media(media, target, registry)

            manifest.write_text('{"schema_version":1,"schema_version":1,"examples":[]}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON field"):
                public.stage_qemu_sd_media(media, runtime, registry)
            manifest.write_bytes(public.encode_json(good))
            oversized_target = work / "oversized"
            oversized_target.mkdir()
            with patch.object(public, "QEMU_SD_MEDIA_MAX_BYTES", 512):
                with self.assertRaisesRegex(ValueError, "gzip exceeds"):
                    public.stage_qemu_sd_media(media, oversized_target, registry)
            runtime.mkdir()
            linked = work / "link"
            linked.symlink_to(media, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlinks"):
                public.stage_qemu_sd_media(linked, runtime, registry)
            manifest.rename(work / "manifest.json")
            manifest.symlink_to(work / "manifest.json")
            with self.assertRaisesRegex(ValueError, "symlinks"):
                public.stage_qemu_sd_media(media, runtime, registry)
            manifest.unlink()
            (work / "manifest.json").rename(manifest)
            image.rename(work / "card.img")
            image.symlink_to(work / "card.img")
            with self.assertRaisesRegex(ValueError, "missing or a symlink"):
                public.stage_qemu_sd_media(media, runtime, registry)

    def test_refuses_unowned_destination_and_symlink_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            self.fixture(root)
            output = Path(directory) / "site"
            output.mkdir()
            (output / "user-work.txt").write_text("preserve")
            with self.assertRaisesRegex(ValueError, "not owned"):
                public.build_site(root, output)
            self.assertEqual((output / "user-work.txt").read_text(), "preserve")
            with self.assertRaisesRegex(ValueError, "separate export"):
                public.build_site(root, root / "platform/web/export")
            (root / "platform/web/external.js").symlink_to(output / "user-work.txt")
            with self.assertRaisesRegex(ValueError, "symlink"):
                public.build_site(root, Path(directory) / "safe-export")

    def test_rejects_unsafe_publish_configuration(self):
        for prefix in ("https://other/", "/../", "/repo/../../", "/repo?key=x", "/%2e%2e/"):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                public.normalize_base_path(prefix)
        for endpoint in ("http://example.test", "https://user:secret@example.test", "https://example.test?token=x", "https://example.test/#token"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                public.normalize_service_url(endpoint)

    def test_pages_publication_requires_explicit_main_dispatch(self):
        workflow = (public.ROOT / ".github/workflows/public-site.yml").read_text()
        trigger, jobs_text = workflow.split("\njobs:\n", 1)
        self.assertRegex(trigger, r"(?m)^on:\n  workflow_dispatch:\n")
        self.assertNotRegex(trigger, r"(?m)^  (?:push|pull_request|schedule|workflow_run|repository_dispatch):")
        publish = re.search(r"(?ms)^      publish:\n(.*?)(?=^      [a-z_]+:|\Z)", trigger).group(1)
        self.assertRegex(publish, r"(?m)^        type: boolean$")
        self.assertRegex(publish, r"(?m)^        default: false$")
        reuse = re.search(r"(?ms)^      reuse_verified_runtimes:\n(.*?)(?=^      [a-z_]+:|\Z)", trigger).group(1)
        self.assertRegex(reuse, r"(?m)^        type: boolean$")
        self.assertRegex(reuse, r"(?m)^        default: false$")
        self.assertNotIn("pages: write", trigger)
        self.assertNotIn("id-token: write", trigger)
        self.assertRegex(trigger, r"(?m)^concurrency:\n  group: public-simulator-pages-\$\{\{ github.repository \}\}\n  cancel-in-progress: false$")

        jobs = dict(re.findall(r"(?ms)^  ([a-z_]+):\n(.*?)(?=^  [a-z_]+:\n|\Z)", jobs_text))
        self.assertEqual(set(jobs), {"build_runtimes", "build", "deploy"})
        runtimes, build, deploy = jobs["build_runtimes"], jobs["build"], jobs["deploy"]
        gate = "if: ${{ inputs.publish && github.ref == 'refs/heads/main' }}"
        self.assertIn("    runs-on: macos-15\n", runtimes)
        self.assertIn("        target: [xtensa-softmmu, riscv32-softmmu]\n", runtimes)
        self.assertIn("          brew install autoconf automake libtool bison flex ninja pkg-config xz\n", runtimes)
        self.assertNotIn("--reuse-dependencies", runtimes)
        self.assertNotIn("--reference-runtime", runtimes)
        self.assertNotIn("--sdk-dir", runtimes)
        self.assertIn("      actions: read\n", runtimes)
        self.assertIn("      - name: Import the pinned prior runtime for this target\n"
                      "        if: ${{ inputs.reuse_verified_runtimes }}\n", runtimes)
        for step in ("Install native source build tools", "Fetch pinned upstream release archives"):
            self.assertIn(f"      - name: {step}\n        if: ${{{{ !inputs.reuse_verified_runtimes }}}}\n", runtimes)
        self.assertEqual(runtimes.count("if: ${{ !inputs.reuse_verified_runtimes && matrix.target"), 5)
        self.assertNotIn("pages: write", runtimes)
        self.assertNotIn("id-token: write", runtimes)
        self.assertIn("    needs: build_runtimes\n", build)
        self.assertIn("    runs-on: macos-15\n", build)
        for artifact, path in (("xtensa", ".work"), ("c61", ".work/qemu-c61-runtime")):
            name = f"          name: qemu-staging-{artifact}-${{{{ github.run_attempt }}}}\n"
            self.assertIn(name, runtimes)
            self.assertIn(
                "        uses: actions/download-artifact@v4\n        with:\n"
                + name + f"          path: {path}\n", build,
            )
        self.assertNotIn("run-id:", build)
        self.assertNotIn("github-token:", build)
        self.assertIn("          M5_WASM_GPU: hardware\n", build)
        self.assertIn("          M5_WASM_CHROME: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\n", build)
        self.assertIn('          M5_QEMU_READY_TIMEOUT_MS: "600000"\n', build)
        self.assertIn('          M5_QEMU_GATE_REQUIRE_ALL: "1"\n', build)
        self.assertIn('          M5_QEMU_GATE_WORKERS: "1"\n', build)
        self.assertIn("          M5_QEMU_GATE_PHASE: all\n", build)
        self.assertIn('          M5_QEMU_GATE_DEVICES: ""\n', build)
        guest_runner = (public.ROOT / "platform/tests/test_public_qemu_guest.mjs").read_text()
        self.assertIn("const chromeExecutable=process.env.M5_WASM_CHROME||process.env.M5_CHROME", guest_runner)
        self.assertRegex(deploy, r"^    " + re.escape(gate) + r"\n")
        self.assertIn("    needs: build\n", deploy)
        self.assertIn("    permissions:\n      pages: write\n      id-token: write\n", deploy)
        self.assertIn("    environment:\n      name: github-pages\n      url: ${{ steps.deployment.outputs.page_url }}\n", deploy)
        self.assertIn("id: deployment\n", deploy)
        self.assertIn("uses: actions/deploy-pages@v4\n", deploy)
        self.assertIn("artifact_name: github-pages\n", deploy)
        self.assertNotIn("pages: write", build)
        self.assertNotIn("id-token: write", build)
        self.assertIn("uses: actions/upload-artifact@v4\n", build)
        self.assertIn("name: public-simulator-site-preview\n", build)
        self.assertIn("include-hidden-files: true\n", build)
        pages_upload = re.search(r"(?ms)^      - name: Upload Pages deployment artifact\n(.*?)(?=^      - |\Z)", build).group(1)
        self.assertIn("        " + gate + "\n", pages_upload)
        self.assertIn("uses: actions/upload-pages-artifact@v3\n", pages_upload)
        self.assertIn("name: github-pages\n", pages_upload)
        self.assertIn("path: .work/public-site\n", pages_upload)
        self.assertNotIn("actions/configure-pages", workflow)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser module contracts")
    def test_browser_url_and_firmware_contracts(self):
        result = subprocess.run(["node", "--experimental-default-type=module", str(Path(__file__).with_name("test_public_config.mjs"))], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser module contracts")
    def test_browser_runtime_contracts(self):
        for contract in ("test_public_browser_runtime.mjs", "test_public_qemu_audio.mjs"):
            with self.subTest(contract=contract):
                result = subprocess.run(["node", "--experimental-default-type=module", str(Path(__file__).with_name(contract))],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
