"""Distribution and provenance checks; never builds or executes a guest."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("qemu_builder_test", ROOT / "scripts/qemu-wasm-build/build.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class RuntimeDistributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
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

    def test_transient_archive_download_retries_and_verifies_pinned_bytes(self):
        url = "https://example.com/dependency.tar.xz"
        output = self.root / "dependency.tar.xz"
        data = b"pinned archive"
        upstream_timeout = HTTPError(url, 504, "Gateway Timeout", {}, None)

        class Interrupted(io.BytesIO):
            def read(self, size):
                if self.tell():
                    raise ConnectionResetError("archive interrupted")
                return super().read(size)

        with (mock.patch.object(builder.urllib.request, "urlopen",
                                side_effect=[upstream_timeout, Interrupted(b"partial"), io.BytesIO(data)]) as request,
              mock.patch.object(builder.time, "sleep") as sleep):
            self.assertEqual(builder.acquire(url, output, hashlib.sha256(data).hexdigest()), output)
        self.assertEqual([call.args[0].full_url for call in request.call_args_list], [url] * 3)
        self.assertEqual(sleep.call_args_list, [mock.call(2), mock.call(4)])
        self.assertEqual(output.read_bytes(), data)
        self.assertEqual(list(self.root.glob("*.part")), [])

    def test_archive_download_rejects_permanent_errors_and_unpinned_bytes(self):
        url = "https://example.com/dependency.tar.xz"
        output = self.root / "dependency.tar.xz"
        for response, message in (
            (HTTPError(url, 404, "Not Found", {}, None), r"dependency.tar.xz: HTTP Error 404"),
            (io.BytesIO(b"unpinned archive"), "download SHA256 mismatch"),
        ):
            with (self.subTest(message=message),
                  mock.patch.object(builder.urllib.request, "urlopen", side_effect=[response]) as request,
                  mock.patch.object(builder.time, "sleep") as sleep):
                with self.assertRaisesRegex(ValueError, message):
                    builder.acquire(url, output, "a" * 64)
                request.assert_called_once()
                sleep.assert_not_called()
                self.assertFalse(output.exists())
                self.assertEqual(list(self.root.glob("*.part")), [])

    def test_archive_download_exhausts_transient_retries(self):
        url = "https://example.com/dependency.tar.xz"
        output = self.root / "dependency.tar.xz"
        errors = [HTTPError(url, 504, "Gateway Timeout", {}, None) for _ in range(3)]
        with (mock.patch.object(builder.urllib.request, "urlopen", side_effect=errors) as request,
              mock.patch.object(builder.time, "sleep")):
            with self.assertRaisesRegex(ValueError, r"dependency.tar.xz: HTTP Error 504"):
                builder.acquire(url, output, "a" * 64)
        self.assertEqual(request.call_count, 3)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob("*.part")), [])

    def owned_builder(self):
        sdk = self.root / "sdk"
        (sdk / "upstream/emscripten").mkdir(parents=True, exist_ok=True)
        (sdk / "upstream/emscripten/emscripten-version.txt").write_text('"3.1.50"')
        (sdk / ".emscripten").write_text("# isolated test config\n")
        value = builder.Builder(self.root / "cache", sdk=sdk)
        (value.venv / "bin").mkdir(parents=True)
        (value.venv / "bin/python").touch()
        value.run = mock.Mock(return_value="")
        return value

    def staged_glib(self, stage):
        installed = stage / "usr"
        values = {"lib/libglib-2.0.a": b"!<arch>\n/usr/share/locale\0/usr/lib\0",
                  "include/glib-2.0/glib.h": b"/* public GLib header */\n",
                  "lib/glib-2.0/include/glibconfig.h": b"#define GLIB_SIZEOF_VOID_P 4\n",
                  "lib/pkgconfig/glib-2.0.pc": b"prefix=/usr\nlibdir=${prefix}/lib\nincludedir=${prefix}/include\nName: GLib\nDescription: staged test\nVersion: 2.84.0\nLibs: -L${libdir} -lglib-2.0\nCflags: -I${includedir}/glib-2.0 -I${libdir}/glib-2.0/include\n"}
        for name, data in values.items():
            path = installed / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        return values

    def test_native_c_and_cpp_prefix_mapping_preserves_assertions(self):
        compilers = [shutil.which("cc"), shutil.which("c++")]
        if not all(compilers): self.skipTest("native C/C++ compilers unavailable")
        project = self.root / "private project"
        roots = {"project": project, "cache": project / "owned cache",
                 "sdk": project / "owned cache/sdk", "dependencies": project / "prior dependencies"}
        headers = []
        for name, path in roots.items():
            path.mkdir(parents=True, exist_ok=True)
            header = path / (name + ".h")
            header.write_text(f"static const char *file_{name} = __FILE__;\n")
            headers.append('#include "' + str(header) + '"\n')
        source = project / "contract.c"
        source.write_text('#include <stdio.h>\n#include <assert.h>\n' + ''.join(headers)
                          + 'int main(int argc, char **argv) { (void)argv; '
                          + ''.join(f'puts(file_{name}); ' for name in roots)
                          + 'if (argc > 1) assert(argc == 1); return 0; }\n')
        flags = builder.source_prefix_flags(roots)
        self.assertEqual(shlex.split(shlex.join(flags)), flags)
        for compiler in compilers:
            with self.subTest(compiler=Path(compiler).name):
                binary = self.root / "path-contract"
                language = "c++" if compiler == compilers[1] else "c"
                subprocess.run([compiler, "-x", language, str(source), "-o", str(binary)], check=True, capture_output=True)
                old = subprocess.run(["producer-path-contract"], executable=binary, capture_output=True, check=True)
                with self.assertRaisesRegex(ValueError, "private build path"):
                    builder.require_public_bytes(old.stdout, list(roots.values()), "unmapped-control")
                subprocess.run([compiler, "-x", language, *flags, str(source), "-o", str(binary)], check=True, capture_output=True)
                new = subprocess.run(["producer-path-contract"], executable=binary, capture_output=True, check=True)
                for name in roots:
                    self.assertIn((builder.PATH_POLICY["public_source_roots"][name] + '/' + name + '.h').encode(), new.stdout)
                builder.require_public_bytes(new.stdout + binary.read_bytes(), list(roots.values()), "mapped-control")
                assertion = subprocess.run(["producer-path-contract", "assert"], executable=binary, capture_output=True)
                self.assertNotEqual(assertion.returncode, 0)
                self.assertIn(b"argc == 1", assertion.stderr)
                # Darwin's assert.h uses __FILE_NAME__; glibc uses __FILE__.
                # Both must still abort and identify the same expression/file.
                self.assertIn(b"contract.c", assertion.stderr)
                builder.require_public_bytes(assertion.stderr, list(roots.values()), "preserved-assertion")

    def test_tools_and_qemu_configure_propagate_c_and_cpp_prefix_maps(self):
        value = self.owned_builder()
        env = value.tools()
        for key in ["CFLAGS", "CXXFLAGS"]:
            self.assertTrue(set(value.prefix_flags()).issubset(shlex.split(env[key])))
            self.assertNotIn("-DNDEBUG", shlex.split(env[key]))
        value.verify_source = mock.Mock()
        cross = value.source / "configs/meson/emscripten.txt"
        cross.parent.mkdir(parents=True)
        cross.write_text("c_args = ['-pthread']\nc_link_args = ['-pthread']\ncpp_link_args = ['-pthread']\n")
        value.build.mkdir()
        for key in ["javascript", "wasm", "worker"]:
            (value.build / builder.ASSET_NAMES[key]).write_bytes(b"\0asm\x01\0\0\0" if key == "wasm" else key.encode())
        value.run.side_effect = lambda *args, **kwargs: builder.write_json(value.cache / "commands.json", []) or ""
        link = shlex.join(["emcc", *value.lock["link_flags"]])
        with mock.patch.object(builder.subprocess, "check_output", return_value=link):
            report = value.compile(env)
        configure = next(list(map(str, call.args[0])) for call in value.run.call_args_list if str(call.args[0][0]).endswith("/configure"))
        for key in ["c", "cpp"]:
            option = next(arg for arg in configure if arg.startswith(f"-D{key}_args="))
            actual = builder.ast.literal_eval(option.split("=", 1)[1])
            self.assertTrue(set(value.prefix_flags()).issubset(actual))
        self.assertEqual(report["path_policy"], builder.PATH_POLICY)
        self.assertNotIn(str(value.cache), json.dumps(report))

    def test_glib_staging_preserves_payload_and_relocates_only_pkg_config(self):
        stage, target = self.root / "stage", self.root / "target"
        values = self.staged_glib(stage)
        builder.install_staged_glib(stage, target)
        for name, data in values.items():
            self.assertEqual((stage / "usr" / name).read_bytes(), data)
            if not name.endswith(".pc"): self.assertEqual((target / name).read_bytes(), data)
        pc = (target / "lib/pkgconfig/glib-2.0.pc").read_text()
        self.assertIn("prefix=" + str(target) + "\n", pc)
        self.assertIn("libdir=${prefix}/lib\n", pc)
        command = shutil.which("pkg-config") or shutil.which("pkgconf")
        if command:
            env = {**os.environ, "PKG_CONFIG_PATH": "", "PKG_CONFIG_LIBDIR": str(target / "lib/pkgconfig")}
            for variable, suffix in [("libdir", "lib"), ("includedir", "include")]:
                result = subprocess.check_output([command, "--variable=" + variable, "glib-2.0"], env=env, text=True).strip()
                self.assertEqual(result, str(target / suffix))
        builder.install_staged_glib(stage, target)
        (stage / "usr/lib/pkgconfig/glib-2.0.pc").write_text(pc)
        with self.assertRaisesRegex(ValueError, "unexpected staged pkg-config prefix"):
            builder.install_staged_glib(stage, target)
        (stage / "usr/include/glib-2.0/glib.h").unlink()
        with self.assertRaisesRegex(ValueError, "incomplete staged GLib"):
            builder.install_staged_glib(stage, target)

    def test_dependency_reuse_requires_public_path_producer_policy(self):
        previous = self.root / "previous"
        previous.mkdir()
        builder.write_json(previous / builder.OWNER, {"lock_sha256": builder.sha(builder.LOCK_PATH)})
        builder.write_json(previous / "dependencies.json", {"lock_sha256": builder.sha(builder.LOCK_PATH), "files": {}})
        with self.assertRaisesRegex(ValueError, "lacks the public producer path policy"):
            builder.Builder(self.root / "new-cache", reuse_dependencies=previous)
        receipt = {"lock_sha256": builder.sha(builder.LOCK_PATH), "files": {}, "path_policy": builder.PATH_POLICY}
        builder.write_json(previous / "dependencies.json", receipt)
        value = builder.Builder(self.root / "new-cache", reuse_dependencies=previous)
        self.assertEqual(value.prefix, previous / "target")
        self.assertIn("dependencies", value.path_roots())
        stale = copy.deepcopy(receipt); stale["path_policy"]["version"] = 0
        builder.write_json(previous / "dependencies.json", stale)
        with self.assertRaisesRegex(ValueError, "lock/path policy mismatch"):
            value.dependencies({})

    def test_dependency_plan_keeps_glib_logical_paths_out_of_host_prefix(self):
        value = self.owned_builder()
        env = value.tools()
        value.downloads_all = mock.Mock()
        value.downloads.mkdir()
        for row in value.lock["archives"]:
            if row["name"].startswith("pcre2"):
                (value.downloads / row["filename"]).write_bytes(b"reviewed-download-fixture")
        sources = {}
        for name in ["pkgconf", "zlib", "libffi", "pixman", "glib", "libgpg-error", "libgcrypt"]:
            source = value.cache / "deps-source" / name
            (source / "subprojects").mkdir(parents=True)
            sources[name] = source
        value.dep_source = lambda name: sources[name]
        (value.native / "bin").mkdir(parents=True)
        (value.native / "bin/pkgconf").touch()
        (value.prefix / "lib").mkdir(parents=True)
        for name in ["libz.a", "libffi.a", "libpixman-1.a", "libglib-2.0.a", "libpcre2-8.a", "libgpg-error.a", "libgcrypt.a", "libresolv.a"]:
            (value.prefix / "lib" / name).write_bytes(b"static-contract-fixture")
        glib_build = value.cache / "deps-build/glib"
        glib_build.mkdir(parents=True)
        (glib_build / "config.h").write_text("#define HAVE_POSIX_SPAWN 1\n#define HAVE_PTHREAD_GETNAME_NP 1\n")
        def execute(args, **kwargs):
            args = list(map(str, args))
            if args[1:2] == ["install"] and str(glib_build) in args:
                self.assertEqual(args[-2], "--destdir")
                self.staged_glib(Path(args[-1]))
            return ""
        value.run.side_effect = execute
        with mock.patch.object(builder.subprocess, "check_output", return_value="test-build-triplet"):
            value.dependencies(env)
        setup = next(list(map(str, call.args[0])) for call in value.run.call_args_list
                     if len(call.args[0]) > 2 and str(call.args[0][1]) == "setup" and str(glib_build) in map(str, call.args[0]))
        self.assertIn("--prefix=/usr", setup)
        self.assertIn("--libdir=lib", setup)
        self.assertNotIn("--prefix=" + str(value.prefix), setup)
        cross = (value.cache / "deps-cross.ini").read_text()
        for language in ["c", "cpp"]:
            line = next(line for line in cross.splitlines() if line.startswith(language + "_args="))
            self.assertTrue(set(value.prefix_flags()).issubset(builder.ast.literal_eval(line.split("=", 1)[1])))
        receipt = json.loads((value.cache / "dependencies.json").read_text())
        self.assertEqual(receipt["path_policy"], builder.PATH_POLICY)
        self.assertNotIn(str(value.cache), json.dumps(receipt))
        self.assertIn(b"/usr/share/locale\0/usr/lib", (value.prefix / "lib/libglib-2.0.a").read_bytes())
        self.assertIn("prefix=" + str(value.prefix) + "\n", (value.prefix / "lib/pkgconfig/glib-2.0.pc").read_text())

    def test_distributable_path_guard_checks_binary_and_source_bytes(self):
        value = self.owned_builder()
        for root in [*value.path_roots().values(), Path.home()]:
            with self.subTest(root_role="private-root"):
                with self.assertRaisesRegex(ValueError, "private build path") as error:
                    value.require_public(b"\0asm\x01\0\0\0" + str(root).encode() + b"/source.c\0", "fixture.wasm")
                self.assertNotIn(str(root), str(error.exception))
        value.require_public(b"\0asm\x01\0\0\0/m5stack-build/cache/qemu/source.c\0/usr/share/locale\0/usr/lib", "public.wasm")
        value.source.mkdir()
        value.sdk.mkdir(exist_ok=True)
        (value.cache / "unsupported-resolver.c").write_text("/* supported packaging fixture */\n")
        value.verify_source = mock.Mock()
        value.lock = {"archives": [], "patches": [], "dependency_patches": []}
        (value.source / "fixture.c").write_text("const char *source = __FILE__;\n")
        archive = self.root / "public-source.tar.xz"
        value.source_bundle(archive)
        with tarfile.open(archive) as package:
            self.assertEqual(package.extractfile("qemu/fixture.c").read(), b"const char *source = __FILE__;\n")
        (value.source / "fixture.c").write_text(str(value.cache) + "/private-source.c")
        with self.assertRaisesRegex(ValueError, "private build path in distributable: qemu/fixture.c"):
            value.source_bundle(self.root / "private-source.tar.xz")

    def test_fixed_patch_order_and_runtime_source_boundary(self):
        native_count = self.lock["native_patch_count"]
        self.assertEqual(native_count, 49)
        self.assertEqual(len(self.lock["patched_files"]), 165)
        self.assertIn("tcg/tci.c", self.lock["patched_files"])
        self.assertIn("tcg/tci-wasm-call.h", self.lock["patched_files"])
        for name in ["m5atoms3.c", "m5atoms3lite.c", "m5stickc.c", "m5stickcplus2.c", "m5dial.c", "m5atomclassic.c", "m5_rmt_classic.c"]:
            self.assertIn("hw/m5stopwatch/" + name, self.lock["patched_files"])
        self.assertTrue(self.lock["patches"][30]["path"].endswith("0064-esp32-intmatrix-pending-irq-remap.patch"))
        self.assertEqual([Path(row["path"]).name.split("-")[0] for row in self.lock["patches"][31:native_count]], ["0096", "0097", "0098", "0099", "0100", "0014", "0101", "0102", "0103", "0087", "0104", "0105", "0106", "0107", "0108", "0109", "0165", "0166"])
        suffix = [Path(row["path"]).name.split("-")[0] for row in self.lock["patches"][native_count:]]
        self.assertEqual(suffix, ["0001", "0004", "0005", "0006", "0009", "0010", "0008", "0011", "0012", "0013", "0014", "0015", "0016", "0017", "0018", "0019", "0020", "0021", "0022", "0023", "0024", "0025", "0026", "0027", "0028", "0029", "0030", "0032", "0033", "0034", "0037", "0038"])
        self.assertEqual(self.lock["patched_files"]["hw/misc/esp32s3_cache.c"],
                         "4db4329a453f99444add015bb8b8cf90b6232897e71e9c15078db51c68397e8a")
        self.assertEqual(self.lock["patched_files"]["util/coroutine-wasm.c"],
                         "93a0857d7213ce5325bf4367028408a2a3ca19d72628ba285e257aa1c746eb1b")
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
        self.assertEqual(audit["effective"]["optimization"], "O3")
        self.assertIs(audit["effective"]["emit_symbol_map"], True)
        self.assertEqual(audit["source"], "ninja-link-command")
        self.assertEqual(audit["argv_sha256"], hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest())
        for expected in flags:
            with self.subTest(missing=expected):
                with self.assertRaisesRegex(ValueError, "effective QEMU link setting mismatch"):
                    builder.audit_link_arguments([arg for arg in argv if arg != expected], flags)
            with self.subTest(conflicting=expected):
                setting = expected.split("=", 1)[0]
                with self.assertRaisesRegex(ValueError, "effective QEMU link setting mismatch"):
                    builder.audit_link_arguments([*argv, "-O0" if expected == "-O3" else setting + "=incorrect"], flags)

        with self.assertRaisesRegex(ValueError, "effective QEMU link setting mismatch"):
            builder.audit_link_arguments([*argv, "--emit-symbol-map"], flags)

    def test_profiling_symbol_sidecar_is_not_a_runtime_export(self):
        self.manifest()
        (self.root / "qemu-system-xtensa.js.symbols").write_text("0:profiling_only\n")
        _, files = builder.runtime_files(self.root)
        self.assertNotIn("qemu-system-xtensa.js.symbols", files)
        self.assertNotIn("symbols", builder.ASSET_NAMES)

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
