"""Offline failure controls for the package runner; no service or guest calls."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from email.message import Message
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


def stored_envelope(files):
    sys.path.insert(0, str(runner.ROOT / "platform/tools"))
    from program_packages import ProgramPackageStore
    with tempfile.TemporaryDirectory() as temp:
        store = ProgramPackageStore(Path(temp))
        metadata = store.create(runner.checkpoint_payload(files))
        source = store.source(metadata["revision_id"])
    return {"revision": metadata, "limits": deepcopy(runner.CHECKPOINT_LIMITS)}, source


def reference_evidence_fixture():
    report, contents, manifest, original = evidence_fixture()
    contents = {name: data for name, data in contents.items() if not name.startswith("programs/")}
    packages = {version: {**original["c"], "config.json": runner.canonical({"version": version}) + b"\n"}
                for version in runner.VERSIONS}
    report.update(revision_references=True, checkpoints={}, executions={})
    for version, files in packages.items():
        envelope, _ = stored_envelope(files)
        report["checkpoints"][version] = envelope
    names = ["finite", "a", "b", "syntax", "b-recovery", "mpy-major", "mpy-smallint", "extra-directory",
             "extra-directory-integrity", "tamper", "integrity", "c-recovery"]
    references = {"a": "A", "b": "B", "b-recovery": "B", "c-recovery": "C"}
    completed = {"finite", "extra-directory", "tamper"}
    failed = {"syntax", "mpy-major", "mpy-smallint", "extra-directory-integrity", "integrity"}
    submitted, previous = {}, None
    for index, name in enumerate(names):
        execution_id = f"fixture-{index:02d}"
        if name in completed:
            source = "print(" + repr(name) + ")\n"
            checkpoint_id = runner.sha(source.encode())
            program = {"execution_id": execution_id, "revision_id": checkpoint_id, "pid": report["pid"],
                       "firmware_sha256": report["firmware_sha256"], "state": "completed"}
            contents[f"programs/{checkpoint_id}/source.json"] = json.dumps({"entrypoint": "main.py", "files": {"main.py": source}}).encode()
            result = {"program": program, "expected_history_state": "completed", "activated": False}
            submitted[name] = source
        else:
            version = references.get(name, "B")
            files = packages[version]
            envelope = report["checkpoints"][version]
            checkpoint_id = envelope["revision"]["revision_id"]
            _, source = stored_envelope(files)
            state = "failed" if name in failed else "running" if name == "c-recovery" else "interrupted"
            program = {"execution_id": execution_id, "revision_id": checkpoint_id, "pid": report["pid"],
                       "firmware_sha256": report["firmware_sha256"], "source_sha256": envelope["revision"]["source_sha256"],
                       "total_file_bytes": envelope["revision"]["total_file_bytes"], "file_count": len(files),
                       "source_kind": "uiflow2-package", "state": state, "interruption_confirmed": state == "interrupted",
                       "deployment": {"phase": "activated", "inventory": runner.file_inventory(files),
                                      "package_path": runner.GUEST_BASE + "/" + checkpoint_id, "reused": name == "b-recovery"}}
            result = {"program": program, "expected_history_state": state, "activated": name in references,
                      "reused": name == "b-recovery"}
            if name in references:
                result["submission"] = {"mode": "revision-reference", "checkpoint_version": version,
                                        "previous_execution_id": previous, "request": runner.reference_payload(checkpoint_id, previous)}
            contents[f"programs/{checkpoint_id}/source.json"] = json.dumps(source).encode()
            contents[f"programs/{checkpoint_id}/revision.json"] = json.dumps(envelope["revision"]).encode()
            contents.update({f"programs/{checkpoint_id}/files/{path}": data for path, data in files.items()})
            submitted[name] = files
        report["executions"][name] = result
        contents[f"programs/{execution_id}.json"] = json.dumps(program).encode()
        previous = execution_id
    return report, contents, manifest, submitted


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

    def test_reference_plan_is_offline_and_execute_keeps_explicit_gates(self):
        for flags in (["--revision-references"], ["--plan", "--revision-references"]):
            output = io.StringIO()
            with mock.patch.object(runner, "RevisionProbeClient", side_effect=AssertionError("service call")), \
                 mock.patch.object(runner.subprocess, "run", side_effect=AssertionError("compiler call")), \
                 mock.patch.object(runner, "run", side_effect=AssertionError("execution")), redirect_stdout(output):
                runner.main(flags)
            plan = json.loads(output.getvalue())
            self.assertTrue(plan["revision_references"])
            self.assertEqual(plan["checkpoints_before_session"], ["A", "B", "C"])
            self.assertEqual(plan["expected_executions"], 12)
            self.assertEqual(plan["valid_execution_fields"], ["revision_id", "expected_execution_id", "timeout_seconds"])
        for flags in (["--execute", "--revision-references"], ["--plan", "--execute", "--revision-references"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                runner.main(flags)
            self.assertEqual(error.exception.code, 2)

    def test_checkpoint_contract_and_reference_requests_use_independent_store_identity(self):
        files = {"main.py": b"print('checkpoint fixture')\n", "config.json": '{"中文":true}\n'.encode(),
                 "helper.mpy": b"M\x06\x00\x1f-fixture-not-executable"}
        envelope, _ = stored_envelope(files)
        self.assertEqual(set(runner.checkpoint_payload(files)), {"source_kind", "entrypoint", "files"})
        self.assertEqual(runner.validate_checkpoint(envelope, files), envelope["revision"])
        payload, submission = runner.submission_payload(files, "previous", {"A": envelope})
        self.assertEqual(payload, runner.reference_payload(runner.revision_id(files), "previous"))
        self.assertEqual(set(payload), {"revision_id", "expected_execution_id", "timeout_seconds"})
        self.assertEqual(submission["mode"], "revision-reference")
        self.assertEqual(submission["checkpoint_version"], "A")
        legacy, marker = runner.submission_payload(files, None)
        self.assertEqual(legacy, runner.package_payload(files, None))
        self.assertIsNone(marker)
        changed = {**files, "main.py": b"def broken(:\n"}
        payload, submission = runner.submission_payload(changed, "previous", {"A": envelope})
        self.assertIn("files", payload)
        self.assertEqual(submission["mode"], "legacy-files")
        payload, submission = runner.submission_payload("print('finite')\n", None, {"A": envelope})
        self.assertEqual(set(payload), {"source", "expected_execution_id", "timeout_seconds"})
        self.assertEqual(submission["mode"], "legacy-source")
        for change in (
            lambda value: value["revision"].update(revision_id="0" * 64),
            lambda value: value["revision"].update(source_sha256="0" * 64),
            lambda value: value["revision"]["files"][0].update(size=True),
            lambda value: value["revision"].update(created_at="2026-10-26T12:00:00"),
            lambda value: value["limits"].update(gc_enabled=0),
            lambda value: value.update(unexpected=True),
        ):
            altered = deepcopy(envelope)
            change(altered)
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                runner.validate_checkpoint(altered, files)

    def test_registration_repeats_post_and_get_without_mutating_created_at_or_limits(self):
        packages = {version: {"main.py": b"print('checkpoint fixture')\n", "config.json": runner.canonical({"version": version})}
                    for version in runner.VERSIONS}
        envelopes = {runner.revision_id(files): stored_envelope(files)[0] for files in packages.values()}
        class Client:
            def __init__(self, alter=None):
                self.requests, self.alter = [], alter
            def json(self, path, method="GET", payload=None):
                checkpoint_id = runner.revision_id({name: value["data"].encode() if value["encoding"] == "utf8" else runner.base64.b64decode(value["data"])
                    for name, value in payload["files"].items()}) if method == "POST" else path.rsplit("/", 1)[1]
                self.requests.append({"path": path, "method": method, "payload": payload, "status": 201 if method == "POST" else 200})
                result = deepcopy(envelopes[checkpoint_id])
                if self.alter and len(self.requests) == 2:
                    result["revision"]["created_at"] = "2026-10-27T00:00:00+00:00"
                return result
        with tempfile.TemporaryDirectory() as temp:
            client = Client()
            checkpoints = runner.register_checkpoints(client, packages, Path(temp))
            self.assertEqual(set(checkpoints), set(runner.VERSIONS))
            self.assertEqual([row["method"] for row in client.requests], ["POST", "POST", "GET"] * 3)
            self.assertTrue(all(set(row["payload"]) == {"source_kind", "entrypoint", "files"}
                                for row in client.requests if row["method"] == "POST"))
            with self.assertRaisesRegex(RuntimeError, "created_at or limits changed"):
                runner.register_checkpoints(Client(alter=True), packages, Path(temp))

    def test_reference_http_recording_keeps_all_routes_full_repeated_headers_and_error_bytes(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(runner.os.environ, {"M5_UNIT_WEB_BRIDGE": "0"}):
            client = runner.RevisionProbeClient("http://127.0.0.1:8787", Path(temp))
            response = mock.MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = b'{"revision":{}}'
            response.status = 201
            response.headers = Message()
            pairs = [["Content-Type", "application/json"], ["Set-Cookie", "fixture-one"],
                     ["Set-Cookie", "fixture-two"], ["X-Trace", "fixture-trace"]]
            for key, value in pairs:
                response.headers[key] = value
            for path, method, payload in (("program-revisions", "POST", {"fixture": True}),
                                          ("health", "GET", None), ("sessions/fixture/serial?offset=0", "GET", None),
                                          ("sessions/fixture/evidence", "GET", None), ("sessions/fixture?purge=0", "DELETE", None)):
                with mock.patch.object(runner.urllib.request, "urlopen", return_value=response), \
                     mock.patch.object(runner.ProbeClient, "raw", side_effect=AssertionError("unrecorded delegate")):
                    self.assertEqual(client.json(path, method, payload), {"revision": {}})
                self.assertEqual(client.requests[-1]["status"], 201)
                self.assertEqual(client.requests[-1]["response_headers"], pairs)
                self.assertEqual((Path(temp) / f"{len(client.requests) - 1:04d}.response").read_bytes(), b'{"revision":{}}')
            raw = b'{"error":{"code":"unknown_program_package"}}'
            error = urllib.error.HTTPError("http://127.0.0.1/fixture", 404, "Not Found", response.headers, io.BytesIO(raw))
            with mock.patch.object(runner.urllib.request, "urlopen", side_effect=error), self.assertRaises(RuntimeError) as caught:
                client.json("program-revisions/" + "0" * 64)
            self.assertEqual(runner.decode_rejection(caught.exception)["status"], 404)
            self.assertEqual(client.requests[-1]["status"], 404)
            self.assertEqual(client.requests[-1]["response_headers"], pairs)
            self.assertEqual((Path(temp) / "0005.response").read_bytes(), raw)
            self.assertEqual(json.loads((Path(temp) / "http.json").read_text())[-1]["response_sha256"], runner.sha(raw))
            with mock.patch.object(runner.urllib.request, "urlopen", side_effect=urllib.error.URLError("fixture transport failure")), \
                 self.assertRaises(urllib.error.URLError):
                client.json("health")
            self.assertEqual(client.requests[-1]["error"]["type"], "URLError")
            self.assertNotIn("status", client.requests[-1])

    def test_reference_direct_http_mode_rejects_explicit_web_bridge_before_execution(self):
        with mock.patch.dict(runner.os.environ, {"M5_UNIT_WEB_BRIDGE": "1"}), \
             mock.patch.object(runner.ProbeClient, "__init__", side_effect=AssertionError("bridge import")), \
             self.assertRaisesRegex(RuntimeError, "cannot be combined"):
            runner.RevisionProbeClient("http://127.0.0.1:8787", Path("unused"))

    def test_public_reference_zip_requires_exact_checkpoint_metadata_and_twelve_executions(self):
        report, contents, manifest, sources = reference_evidence_fixture()
        result = runner.validate_bundle(bundle(contents, manifest), report, sources)
        self.assertTrue(result["public_checkpoints_and_reference_execution_set_verified"])
        for kind in ("extra-execution", "created-at", "mixed-request", "source-hash", "missing-version"):
            altered_report, altered_contents = deepcopy(report), deepcopy(contents)
            if kind == "extra-execution":
                altered_contents["programs/unexpected.json"] = b"{}"
            elif kind == "created-at":
                altered_report["checkpoints"]["A"]["revision"]["created_at"] = "2026-10-27T00:00:00+00:00"
            elif kind == "mixed-request":
                altered_report["executions"]["a"]["submission"]["request"]["files"] = {}
            elif kind == "source-hash":
                altered_report["executions"]["a"]["program"]["source_sha256"] = "0" * 64
            else:
                altered_report["executions"]["a"].pop("submission")
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                runner.validate_bundle(bundle(altered_contents, manifest), altered_report, sources)

    def test_execute_requires_all_explicit_gates_and_new_output(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            compiler = directory / "compiler"
            compiler.write_text("fixture compiler must never run\n")
            compiler.chmod(0o755)
            valid = ["--execute", "--out-dir", str(directory / "new"), "--expected-runtime-sha256", "a" * 64, "--mpy-cross", str(compiler)]
            for mode in ([], ["--revision-references"]):
                for omitted in ("--out-dir", "--expected-runtime-sha256", "--mpy-cross"):
                    args = valid[:] + mode
                    at = args.index(omitted)
                    del args[at:at + 2]
                    with self.subTest(mode=mode, omitted=omitted), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                        runner.main(args)
                    self.assertEqual(error.exception.code, 2)
            with mock.patch.object(runner, "run") as execute:
                runner.main(valid)
                execute.assert_called_once()
            invalid = valid[:]
            invalid[invalid.index("--out-dir") + 1] = str(directory)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                runner.main(invalid)
            with mock.patch.dict(runner.os.environ, {"M5_UNIT_WEB_BRIDGE": "1"}), \
                 mock.patch.object(runner, "run", side_effect=AssertionError("execution")), \
                 redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                runner.main(valid + ["--revision-references"])
            self.assertEqual(error.exception.code, 2)
            self.assertFalse((directory / "new").exists())

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
