from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import build_public_site as public


class PublicSiteTests(unittest.TestCase):
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
            "platform/web/private.bin": 'not-public',
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
            self.assertFalse((output / ".work").exists())
            self.assertTrue((output / ".nojekyll").is_file())

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
        self.assertNotIn("pages: write", trigger)
        self.assertNotIn("id-token: write", trigger)
        self.assertRegex(trigger, r"(?m)^concurrency:\n  group: public-simulator-pages-\$\{\{ github.repository \}\}\n  cancel-in-progress: false$")

        jobs = dict(re.findall(r"(?ms)^  ([a-z_]+):\n(.*?)(?=^  [a-z_]+:\n|\Z)", jobs_text))
        self.assertEqual(set(jobs), {"build", "deploy"})
        build, deploy = jobs["build"], jobs["deploy"]
        gate = "if: ${{ inputs.publish && github.ref == 'refs/heads/main' }}"
        self.assertIn("    runs-on: macos-14\n", build)
        self.assertIn("          brew install autoconf automake libtool bison flex ninja pkg-config xz\n", build)
        self.assertIn("          M5_WASM_GPU: hardware\n", build)
        self.assertIn("          M5_WASM_CHROME: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\n", build)
        self.assertIn('          M5_QEMU_READY_TIMEOUT_MS: "360000"\n', build)
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
        result = subprocess.run(["node", "--experimental-default-type=module", str(Path(__file__).with_name("test_public_browser_runtime.mjs"))], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
