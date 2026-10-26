"""Offline failure controls for the package runner; no service or guest calls."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.error
import zipfile

from PIL import Image

import run_live_package as runner


def png(color=(0, 0, 255), size=(64, 64)):
    image = Image.new("RGB", size, (0, 0, 0))
    image.paste(color, (8, 8, 32, 32))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def evidence_fixture():
    files = {"main.py": b"print('fixture only')\n", "config.json": b'{"version":"C"}\n',
             "helper.mpy": b"M\x06\x00\x1f-fixture-not-executable", "lib/__init__.py": b"VALUE=303\n",
             "lib/logic.py": b"VALUE=7\n", "assets/pixel.png": png(size=(64, 64))}
    revision = runner.revision_id(files)
    program = {"execution_id": "fixture-execution", "revision_id": revision, "pid": 123, "firmware_sha256": "f" * 64, "source_kind": "uiflow2-package",
               "state": "running", "deployment": {"phase": "activated", "inventory": runner.file_inventory(files),
               "package_path": runner.GUEST_BASE + "/" + revision, "reused": False}}
    unit = {"session_id": "fixture-session", "source": "live", "units": [
        {"id": "external1", "unit_id": "pir", "available": True, "source": "guest-qom", "properties": {"motion": False}}]}
    prefix = b"ESP-ROM:fixture\r\nM5EMU_UART_REPL_READY\r\n\x01\x80\x00"
    sample = runner.expected_sample("C", "pir", 0)
    window = ("LIVE_PACKAGE_SAMPLE " + json.dumps(sample) + "\r\n").encode()
    report = {"session_id": "fixture-session", "device_id": "cores3", "runtime": "qemu", "pid": 123,
              "firmware_sha256": "f" * 64, "unit_id": "pir", "initial_rom_banners": 1, "expected_frame_size": [64, 64],
              "executions": {"c": {"program": program, "expected_history_state": "running", "activated": True, "reused": False}},
              "serial_observations": [{"offset": len(prefix), "prefix_sha256": runner.sha(prefix.decode("utf-8", errors="replace").encode()),
                  "window": {"data": window.decode(), "next_offset": len(prefix + window)},
                  "line_prefix": "LIVE_PACKAGE_SAMPLE ", "expected": sample}]}
    source = runner.package_payload(files, None)
    for value in source["files"].values():
        if value["encoding"] == "utf8":
            value["encoding"] = "base64"
            value["data"] = runner.base64.b64encode(value["data"].encode()).decode()
    contents = {"serial.log": prefix + window, "frames/current.png": png(), "qom/snapshot.json": b"{}",
        "units/contract.json": b"{}", "units/state.json": json.dumps(unit).encode(), "units/runtime.json": b"{}",
        "programs/fixture-execution.json": json.dumps(program).encode(),
        f"programs/{revision}/source.json": json.dumps({key: source[key] for key in ("entrypoint", "files")}, ensure_ascii=False).encode()}
    sys.path.insert(0, str(runner.ROOT / "platform/tools"))
    from program_packages import ProgramPackageStore
    with tempfile.TemporaryDirectory() as temp:
        store = ProgramPackageStore(Path(temp))
        metadata = store.create({key: source[key] for key in ("entrypoint", "files")})
        contents[f"programs/{revision}/source.json"] = json.dumps(store.source(revision)).encode()
        contents[f"programs/{revision}/revision.json"] = json.dumps(metadata).encode()
    contents.update({f"programs/{revision}/files/{path}": data for path, data in files.items()})
    manifest = {"session": {"state": "running", **{key: report[key] for key in ("session_id", "device_id", "runtime", "pid", "firmware_sha256")}}, "units": unit}
    return report, contents, manifest, {"c": files}


def bundle(contents, manifest):
    manifest = deepcopy(manifest)
    manifest["files"] = {path: {"size": len(data), "sha256": runner.sha(data)} for path, data in contents.items()}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in contents.items():
            archive.writestr(path, data)
        archive.writestr("manifest.json", json.dumps(manifest))
    return stream.getvalue()


class LivePackageTests(unittest.TestCase):
    def test_default_only_plans_without_api_compiler_or_output_mutation(self):
        output = io.StringIO()
        with mock.patch.object(runner, "ProbeClient", side_effect=AssertionError("service call")), \
             mock.patch.object(runner.subprocess, "run", side_effect=AssertionError("compiler call")), \
             mock.patch.object(runner, "run", side_effect=AssertionError("execution")), redirect_stdout(output):
            runner.main([])
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["status"], "PLANNED_NOT_EXECUTED")
        self.assertEqual(plan["package_directories"], 4)
        self.assertEqual(plan["guest_directory_limit"], 64)

    def test_execute_requires_all_explicit_gates_and_new_output(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            compiler = directory / "compiler"
            compiler.write_text("fixture compiler must never run\n")
            compiler.chmod(0o755)
            valid = ["--execute", "--out-dir", str(directory / "new"), "--expected-runtime-sha256", "a" * 64, "--mpy-cross", str(compiler)]
            for omitted in ("--out-dir", "--expected-runtime-sha256", "--mpy-cross"):
                args = valid[:]
                at = args.index(omitted)
                del args[at:at + 2]
                with self.subTest(omitted=omitted), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    runner.main(args)
                self.assertEqual(error.exception.code, 2)
            with mock.patch.object(runner, "run") as execute:
                runner.main(valid)
                execute.assert_called_once()
            invalid = valid[:]
            invalid[invalid.index("--out-dir") + 1] = str(directory)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                runner.main(invalid)

    def test_source_uses_original_driver_files_mpy_and_no_host_execution(self):
        for unit, driver in (("pir", "PIRUnit"), ("relay", "RelayUnit")):
            source = runner.main_source("nonce", {"white": 1, "yellow": 2}, unit)
            compile(source, "main.py", "exec")
            self.assertIn("import helper", source)
            self.assertIn("from lib import logic", source)
            self.assertIn("with open('assets/pixel.png', 'rb') as stream:", source)
            self.assertIn("screen.drawImage(stream.read(), (screen.width() - 24) // 2, (screen.height() - 24) // 2 - 24)", source)
            self.assertIn(f"from unit import {driver}", source)
            self.assertIn("managed_paths == [cwd]", source)
            self.assertIn("'old_only' not in sys.modules", source)
            self.assertIn("M5.update()", source)
            self.assertNotIn("exec(", source)

    def test_package_variants_share_main_but_change_binary_config_library_and_image(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            compiler = directory / "compiler"
            compiler.write_bytes(b"fake executable fixture")
            compiler.chmod(0o755)
            def fake_compile(_compiler, destination, version):
                destination.mkdir()
                return b"M\x06\x00\x1f" + version.encode(), {"fixture": version}
            with mock.patch.object(runner, "compile_helper", side_effect=fake_compile), \
                 mock.patch.object(runner.subprocess, "run", return_value=SimpleNamespace(stdout=b"fixture-version", stderr=b"")):
                packages, receipt = runner.build_packages(compiler, directory / "packages", "nonce", {"white": 1, "yellow": 2}, "pir")
            self.assertEqual(len({files["main.py"] for files in packages.values()}), 1)
            for field in ("helper.mpy", "config.json", "lib/__init__.py", "lib/logic.py", "namespace_lib/state.py", "assets/pixel.png"):
                self.assertEqual(len({files[field] for files in packages.values()}), 3, field)
            self.assertIn("old_only.py", packages["A"])
            self.assertNotIn("old_only.py", packages["B"])
            self.assertEqual(set(receipt["helpers"]), {"A", "B", "C"})
            with Image.open(io.BytesIO(packages["A"]["assets/pixel.png"])) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, runner.IMAGE_SIZE)

    def test_byte_identity_matches_actual_immutable_package_store(self):
        sys.path.insert(0, str(runner.ROOT / "platform/tools"))
        from program_packages import ProgramPackageStore
        files = {"main.py": b"print('fixture')\n", "config.json": '{"中文":true}\n'.encode(), "helper.mpy": b"M\x06\x00\x1f-fixture"}
        with tempfile.TemporaryDirectory() as temp:
            store = ProgramPackageStore(Path(temp))
            payload = runner.package_payload(files, None)
            metadata = store.create({key: payload[key] for key in ("entrypoint", "files")})
            self.assertEqual(metadata["revision_id"], runner.revision_id(files))
            self.assertEqual(store.read_files(metadata["revision_id"]), files)

    def test_samples_require_full_line_correct_phase_and_exact_bool_integer_types(self):
        expected = runner.expected_sample("B", "pir", 1)
        prefix = "LIVE_PACKAGE_SAMPLE "
        good = prefix + json.dumps(expected) + "\r\n"
        self.assertEqual(runner.matching_json_line(good, prefix, expected), expected)
        for text in (good.rstrip(), "prefix " + good, good.replace('"B"', '"A"'), good.replace('"value": 1', '"value": true')):
            self.assertIsNone(runner.matching_json_line(text, prefix, expected))

    def test_png_oracle_rejects_black_wrong_asset_color_or_geometry(self):
        self.assertEqual(runner.frame_observation(png(), [64, 64], "C")["asset_color_pixels"], 576)
        for data, shape, version in ((png(), [64, 64], "B"), (png((0, 0, 0)), [64, 64], "C"), (png(), [128, 128], "C")):
            with self.assertRaises(RuntimeError):
                runner.frame_observation(data, shape, version)

    def test_qom_must_be_selected_live_available_attachment(self):
        report, _, manifest, _ = evidence_fixture()
        response = manifest["units"]
        self.assertIs(runner.live_unit(response, report["session_id"], "pir")["motion"], False)
        for change in (lambda x: x.update(session_id="other"), lambda x: x.update(source="persisted"),
                       lambda x: x["units"][0].update(available=False), lambda x: x["units"].append(x["units"][0]),
                       lambda x: x["units"][0].update(unit_id="relay")):
            value = deepcopy(response)
            change(value)
            with self.assertRaises(RuntimeError):
                runner.live_unit(value, report["session_id"], "pir")

    def test_structured_http_rejection_does_not_swallow_network_errors(self):
        payload = {"error": {"code": "program_mpy_incompatible", "execution_id": "fixture"}}
        cause = urllib.error.HTTPError("http://127.0.0.1/fixture", 409, "Conflict", {}, io.BytesIO())
        error = RuntimeError("POST sessions/fixture/program: HTTP 409 " + json.dumps(payload))
        error.__cause__ = cause
        self.assertEqual(runner.decode_rejection(error), {"status": 409, "response": payload})
        with self.assertRaisesRegex(RuntimeError, "transport unavailable"):
            runner.decode_rejection(RuntimeError("transport unavailable"))

    def test_complete_zip_binds_original_bytes_guest_inventory_and_raw_offsets(self):
        report, contents, manifest, sources = evidence_fixture()
        self.assertTrue(runner.validate_bundle(bundle(contents, manifest), report, sources)["serial_byte_offsets_verified"])

    def test_zip_original_bytes_and_inventory_have_independent_failure_controls(self):
        for kind in ("raw-file", "source", "inventory", "identity", "reuse", "state"):
            report, contents, manifest, sources = evidence_fixture()
            revision = report["executions"]["c"]["program"]["revision_id"]
            if kind == "raw-file":
                contents[f"programs/{revision}/files/config.json"] += b" "
            elif kind == "source":
                path = f"programs/{revision}/source.json"
                source = json.loads(contents[path])
                source["files"]["helper.mpy"]["data"] = runner.base64.b64encode(b"wrong original bytes").decode()
                contents[path] = json.dumps(source).encode()
            else:
                path = "programs/fixture-execution.json"
                history = json.loads(contents[path])
                if kind == "inventory":
                    history["deployment"]["inventory"]["helper.mpy"]["sha256"] = "0" * 64
                elif kind == "identity":
                    history["pid"] += 1
                elif kind == "reuse":
                    history["deployment"]["reused"] = True
                else:
                    history["state"] = "completed"
                contents[path] = json.dumps(history).encode()
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                runner.validate_bundle(bundle(contents, manifest), report, sources)

    def test_old_sample_offset_and_rejected_app_markers_fail_closed(self):
        report, contents, manifest, sources = evidence_fixture()
        raw = contents["serial.log"]
        contents["serial.log"] += b"no fresh sample\r\n"
        row = report["serial_observations"][0]
        row.update(offset=len(raw), prefix_sha256=runner.sha(raw.decode("utf-8", errors="replace").encode()),
                   window={"data": "no fresh sample\r\n", "next_offset": len(contents["serial.log"])})
        with self.assertRaisesRegex(RuntimeError, "fresh guest sample"):
            runner.validate_bundle(bundle(contents, manifest), report, sources)
        report, contents, manifest, sources = evidence_fixture()
        report["serial_observations"][0]["forbidden"] = ["LIVE_PACKAGE_SAMPLE "]
        with self.assertRaisesRegex(RuntimeError, "rejected package executed"):
            runner.validate_bundle(bundle(contents, manifest), report, sources)

    def test_zip_index_and_cross_session_negative_controls(self):
        report, contents, manifest, sources = evidence_fixture()
        manifest["session"]["session_id"] = "another-session"
        with self.assertRaisesRegex(RuntimeError, "guest identity"):
            runner.validate_bundle(bundle(contents, manifest), report, sources)
        report, contents, manifest, sources = evidence_fixture()
        contents["../escape"] = b"fixture"
        with self.assertRaisesRegex(RuntimeError, "unsafe ZIP"):
            runner.validate_bundle(bundle(contents, manifest), report, sources)


if __name__ == "__main__":
    unittest.main()
