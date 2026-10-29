"""Distribution and provenance checks; never builds or executes a guest."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("qemu_builder_test", ROOT / "scripts/qemu-wasm-build/build.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class RuntimeDistributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.lock = builder.load_lock()

    def manifest(self):
        data = {}
        for key, name in builder.ASSET_NAMES.items():
            payload = b"\0asm\x01\0\0\0" if key == "wasm" else key.encode()
            if key == "source":
                buffer = io.BytesIO()
                with tarfile.open(fileobj=buffer, mode="w:xz") as package:
                    for filename in ["build.py", "sources.lock.json"]:
                        content = (builder.RECIPE / filename).read_bytes()
                        info = tarfile.TarInfo("scripts/qemu-wasm-build/" + filename); info.size = len(content)
                        package.addfile(info, io.BytesIO(content))
                payload = buffer.getvalue()
            (self.root / name).write_bytes(payload)
            data[key] = {"path": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        value = {"schema_version": 1, "kind": builder.RUNTIME_KIND, "engine": "qemu-wasm",
                 "source": {"commit": self.lock["qemu"]["commit"], "patches": self.lock["patches"], "patched_files_sha256": self.lock["patched_files"]},
                 "build": {"kind": "source-build", "all_objects_rebuilt": True, "lock_sha256": builder.sha(builder.LOCK_PATH), "recipe_sha256": builder.sha(builder.RECIPE / "build.py"), "emscripten": "3.1.50", "link_audit": builder.audit_link_arguments(["emcc", *self.lock["link_flags"]], self.lock["link_flags"])}, "profiles": ["cores3"],
                 "execution_profile": {"id": "cores3-wasm-vm-div8", "clock_divisor": 8, "scope": "offline-lvgl-pir"},
                 "compiled_profiles": self.lock["compiled_profiles"], "frame_transport": self.lock["frame_transport"],
                 "assets": data, "required_rom": self.lock["required_rom"], "firmware_bundled": False}
        self.write(value)
        return value

    def write(self, value): (self.root / "runtime.json").write_text(json.dumps(value))

    def test_fixed_patch_order_and_runtime_source_boundary(self):
        native_count = self.lock["native_patch_count"]
        self.assertEqual(native_count, 44)
        self.assertEqual(len(self.lock["patches"]), native_count + 15)
        for name in ["m5atoms3.c", "m5atoms3lite.c", "m5stickc.c", "m5stickcplus2.c", "m5dial.c", "m5atomclassic.c", "m5_rmt_classic.c"]:
            self.assertIn("hw/m5stopwatch/" + name, self.lock["patched_files"])
        self.assertTrue(self.lock["patches"][30]["path"].endswith("0064-esp32-intmatrix-pending-irq-remap.patch"))
        self.assertEqual([Path(row["path"]).name.split("-")[0] for row in self.lock["patches"][31:native_count]], ["0085", "0086", "0087", "0088", "0089", "0008", "0090", "0091", "0092", "0087", "0093", "0094", "0095"])
        suffix = [Path(row["path"]).name.split("-")[0] for row in self.lock["patches"][native_count:]]
        self.assertEqual(suffix, ["0001", "0004", "0005", "0006", "0009", "0010", "0008", "0011", "0012", "0013", "0014", "0015", "0016", "0017", "0018"])
        self.assertFalse(self.lock["required_rom"]["bundled"])
        self.assertIsNone(self.lock["required_rom"]["path"])

    def test_native_partition_rejects_nonintegers_and_misclassified_layers(self):
        target = self.root / "scripts/qemu-wasm-build/sources.lock.json"
        target.parent.mkdir(parents=True)
        native_count = self.lock["native_patch_count"]
        for count in [True, "36", 0, -1, native_count - 1, native_count + 1, len(self.lock["patches"])]:
            with self.subTest(count=count):
                value = copy.deepcopy(self.lock)
                value["native_patch_count"] = count
                target.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "unsupported QEMU source lock"):
                    builder.load_lock(self.root)

    def test_exact_allowlist_returns_source_and_no_rom(self):
        self.manifest()
        _, files = builder.runtime_files(self.root)
        self.assertEqual(set(files), {"runtime.json", *builder.ASSET_NAMES.values()})
        self.assertIn("corresponding-source.tar.xz", files)
        self.assertNotIn("esp32s3_rev0_rom.bin", files)

    def test_asset_tampering_and_symlink_rejected(self):
        self.manifest()
        path = self.root / builder.ASSET_NAMES["wasm"]
        path.write_bytes(b"\0asm\x01\0\0\0tamper")
        with self.assertRaisesRegex(ValueError, "hash/size"): builder.runtime_files(self.root)
        self.manifest(); path.unlink(); path.symlink_to(self.root / "NOTICE")
        with self.assertRaisesRegex(ValueError, "unsafe"): builder.runtime_files(self.root)

    def test_frozen_archive_binds_its_recipe_without_requiring_current_recipe(self):
        value = self.manifest()
        frozen_recipe = b"# frozen previous build recipe\n" + (builder.RECIPE / "build.py").read_bytes()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:xz") as package:
            for filename, content in [("build.py", frozen_recipe), ("sources.lock.json", builder.LOCK_PATH.read_bytes())]:
                info = tarfile.TarInfo("scripts/qemu-wasm-build/" + filename)
                info.size = len(content)
                package.addfile(info, io.BytesIO(content))
        payload = buffer.getvalue()
        (self.root / builder.ASSET_NAMES["source"]).write_bytes(payload)
        value["assets"]["source"].update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        value["build"]["recipe_sha256"] = hashlib.sha256(frozen_recipe).hexdigest()
        self.write(value)
        builder.runtime_files(self.root)
        value["build"]["recipe_sha256"] = builder.sha(builder.RECIPE / "build.py")
        self.write(value)
        with self.assertRaisesRegex(ValueError, "archived build recipe/lock hash mismatch"):
            builder.runtime_files(self.root)

    def test_manifest_source_and_distribution_fail_closed(self):
        value = self.manifest()
        mutations = []
        for change in [lambda v: v["source"].update(commit="0" * 40),
                       lambda v: v["source"]["patches"].reverse(),
                       lambda v: v.update(firmware_bundled=True),
                       lambda v: v["required_rom"].update(bundled=True),
                       lambda v: v["build"].update(all_objects_rebuilt=1),
                       lambda v: v["build"].update(lock_sha256="0" * 64),
                       lambda v: v["build"].update(recipe_sha256="0" * 64),
                       lambda v: v["build"].pop("link_audit"),
                       lambda v: v["build"]["link_audit"].update(verified=1),
                       lambda v: v["build"]["link_audit"].update(source="configure-input"),
                       lambda v: v["build"]["link_audit"]["required_flags"].reverse(),
                       lambda v: v["build"]["link_audit"]["effective"].update(STACK_SIZE="5MB"),
                       lambda v: v["build"]["link_audit"].update(argv_sha256="short"),
                       lambda v: v["source"].update(patched_files_sha256={}),
                       lambda v: v.update(compiled_profiles=[]),
                       lambda v: v["frame_transport"].update(kind="unknown"),
                       lambda v: v["execution_profile"].update(clock_divisor=1),
                       lambda v: v["assets"]["wasm"].update(path="../escape.wasm"),
                       lambda v: v["assets"].pop("source")]:
            mutated = copy.deepcopy(value); change(mutated); mutations.append(mutated)
        for mutated in mutations:
            self.write(mutated)
            with self.assertRaises(ValueError): builder.runtime_files(self.root)

    def test_audit_checks_actual_link_settings_and_conflicts(self):
        flags = self.lock["link_flags"]
        argv = ["emcc", "-o", "qemu-system-xtensa.js", *flags]
        audit = builder.audit_link_arguments(argv, flags)
        self.assertIs(audit["verified"], True)
        self.assertEqual(audit["effective"]["STACK_SIZE"], "64KB")
        self.assertEqual(audit["source"], "ninja-link-command")
        self.assertEqual(audit["argv_sha256"], hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest())
        for expected in flags:
            with self.subTest(missing=expected):
                with self.assertRaisesRegex(ValueError, "effective QEMU link setting mismatch"):
                    builder.audit_link_arguments([arg for arg in argv if arg != expected], flags)
            with self.subTest(conflicting=expected):
                setting = expected.split("=", 1)[0]
                with self.assertRaisesRegex(ValueError, "effective QEMU link setting mismatch"):
                    builder.audit_link_arguments([*argv, setting + "=incorrect"], flags)

    def test_incremental_requires_opt_in_and_reviewed_artifact_pins(self):
        value = self.manifest(); value["build"]["all_objects_rebuilt"] = False; self.write(value)
        with self.assertRaisesRegex(ValueError, "full source build"): builder.runtime_files(self.root)
        with self.assertRaisesRegex(ValueError, "historical incremental reference is incompatible"):
            builder.runtime_files(self.root, allow_incremental=True)
        compatible = copy.deepcopy(self.lock)
        compatible["reference_runtime"]["source_lock_compatible"] = True
        with mock.patch.object(builder, "load_lock", return_value=compatible):
            with self.assertRaisesRegex(ValueError, "reference receipt"):
                builder.runtime_files(self.root, allow_incremental=True)
            value["build"]["reference_build_receipt_sha256"] = self.lock["reference_runtime"]["build_receipt_sha256"]
            self.write(value)
            with self.assertRaisesRegex(ValueError, "reference artifact"):
                builder.runtime_files(self.root, allow_incremental=True)

    def test_owned_cache_and_source_location_guards(self):
        (self.root / "unrelated.txt").write_text("retain")
        with self.assertRaisesRegex(ValueError, "unowned"): builder.Builder(self.root)
        for path in [ROOT, ROOT / "platform/tmp", ROOT / "scripts/tmp", ROOT.parent]:
            with self.assertRaises(ValueError): builder.safe_directory(path)
        self.assertEqual((self.root / "unrelated.txt").read_text(), "retain")

    def test_tar_traversal_does_not_escape_destination(self):
        path = self.root / "bad.tar"
        with tarfile.open(path, "w") as package:
            info = tarfile.TarInfo("../outside.txt"); info.size = 1
            package.addfile(info, io.BytesIO(b"x"))
        with self.assertRaises(tarfile.FilterError): builder.extract_archive(path, self.root / "destination")
        self.assertFalse((self.root / "outside.txt").exists())

    def test_source_package_excludes_all_opaque_bios_forms(self):
        for name in ["pc-bios/esp32s3_rev0_rom.bin", "pc-bios/edk2-arm-code.fd.bz2", "pc-bios/openbios-sparc64", "pc-bios/skiboot.lid", "pc-bios/u-boot.e500", "tests/qemu-iotests/sample_images/grub_mbr.raw.bz2", "tests/qemu-iotests/sample_images/README", "tests/qemu-iotests/sample_images/relative-link"]:
            self.assertFalse(builder.source_member_allowed(Path(name)), name)
        for extension in ["bin", "rom", "elf", "img", "fd", "efi", "raw", "qcow", "qcow2", "qed", "vdi", "vmdk", "vhd", "vhdx", "iso", "dsk", "dtb"]:
            for compression in ["", ".bz2", ".gz", ".xz", ".zst", ".lz4", ".lzma", ".zip", ".z", ".gz.xz"]:
                name = f"tests/fixture.{extension}{compression}"
                self.assertFalse(builder.source_member_allowed(Path(name)), name)
        for name in ["pc-bios/README", "pc-bios/COPYING", "pc-bios/meson.build", "pc-bios/bamboo.dts", "pc-bios/s390-ccw/main.c", "hw/xtensa/esp32s3.c"]:
            self.assertTrue(builder.source_member_allowed(Path(name)), name)
        self.assertTrue(builder.source_member_allowed(Path("tests/fixture.c.gz")))


if __name__ == "__main__": unittest.main()
