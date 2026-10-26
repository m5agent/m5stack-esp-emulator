"""Host-only Scroll planning, source generation and evidence failure controls.

Returned MicroPython is parsed/compiled, never executed by host Python. ZIPs
are synthetic in-memory fixtures, not guest/controller/hardware evidence.
"""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import ast
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

from PIL import Image

import run_live_scroll as runner
from program_revisions import ProgramRevisionStore
from scroll_protocol_probe import PHASES, build_probe_source


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def persisted_revision(snapshot):
    """Use the actual source store in an owned temporary directory only."""
    with tempfile.TemporaryDirectory() as directory:
        store = ProgramRevisionStore(Path(directory))
        metadata = store.create(snapshot)
        return store.source(metadata["revision_id"]), metadata


def fixture():
    """Two complete executions bound to one synthetic session/VM and raw UART."""
    image = io.BytesIO()
    Image.new("RGB", (64, 64), (0x12, 0x34, 0x56)).save(image, format="PNG")
    attachments = [{"id": "external1", "unit_id": "scroll", "port_id": "port-a",
                    "visual_port": "grove", "pins": {"white": 1, "yellow": 2},
                    "initial": {"source-count": 0, "pressed": False}}]
    hashes = {"catalog.json": "a" * 64, "host-ports.json": "b" * 64, "runtime-profiles.json": "c" * 64}
    properties = {"source-count": 117, "pressed": True, "counter": 0, "increments": 0,
                  "direction": 1, "ab-direction": 0, "led-rgb": 0x123456}
    report = {"session_id": "synthetic-scroll-session", "device_id": "cores3", "unit_id": "scroll",
              "runtime": "qemu", "pid": 12345, "firmware_sha256": "f" * 64,
              "worker": {"worker_id": "synthetic-worker", "generation": 7, "lease_active": True},
              "rom_banners": 1, "attachments": attachments, "contract_hashes": hashes,
              "executions": {}, "observations": {}, "final_state": properties,
              "final_frame": {"sha256": runner.sha(image.getvalue()), "size": [64, 64]},
              "vm_nonce": "/m5-scroll-synthetic-fixture"}
    state = {"session_id": report["session_id"], "state": "running", "source": "live",
             "contract_hashes": hashes, "definitions": [{"id": "scroll"}],
             "units": [{**attachments[0], "available": True, "source": "guest-qom", "errors": {}, "properties": properties}]}
    contents = {"frames/current.png": image.getvalue(), "qom/snapshot.json": b'{"nodes":[]}',
                "units/contract.json": canonical({"schema_version": 1, "source_hashes": hashes, "units": {"scroll": {"id": "scroll"}}, "profiles": {"scroll": {}}, "fixtures": {}}),
                "units/runtime.json": canonical({"schema_version": 1, "attachments": attachments}),
                "units/state.json": canonical(state)}
    serial = b"ESP-ROM:synthetic\r\nM5EMU_UART_REPL_READY\r\n\x01\x80\x00"
    submitted = {}
    for index, name in enumerate(("prime", "read")):
        marker = "SCROLL_FIXTURE_" + str(index)
        event = {"kind": "done", "phase": "snapshot-prime" if index == 0 else "snapshot-read"}
        guard = ("import sys\nsys.path.append('/m5-scroll-synthetic-fixture')\n" if index == 0 else
                 "import sys\nassert '/m5-scroll-synthetic-fixture' in sys.path, 'MicroPython VM reset'\n")
        source = guard + "print(" + repr(marker + " " + json.dumps(event)) + ")\n"
        files = {"main.py": source}
        snapshot = {"source_kind": "uiflow2-python", "entrypoint": "main.py", "files": files}
        original, metadata = persisted_revision(snapshot)
        revision = metadata["revision_id"]
        assert revision == runner.sha(canonical(snapshot))
        execution_id = ("1" if index == 0 else "2") * 32
        start = len(serial)
        window = ("__M5_EXEC_" + execution_id + "__:START\r\n" + marker + " " + json.dumps(event) + "\r\n"
                  + "__M5_EXEC_" + execution_id + "__:DONE\r\n").encode()
        program = {"execution_id": execution_id, "revision_id": revision, "source_kind": "uiflow2-python",
                   "pid": report["pid"], "firmware_sha256": report["firmware_sha256"], "state": "completed",
                   "source_sha256": runner.sha(canonical(files)), "source_bytes": len(source.encode()),
                   "execution_mode": "same-guest-uart-repl", "cleanup_mode": "interrupt-only",
                   "serial_offset": start, "next_offset": start + len(window), "acknowledged": True}
        contents["programs/" + execution_id + ".json"] = canonical(program)
        contents["programs/" + revision + "/source.json"] = canonical(original)
        contents["programs/" + revision + "/revision.json"] = canonical(metadata)
        report["executions"][name] = {"session_id": report["session_id"], "program": program}
        report["observations"][name] = {"offset": start, "prefix_sha256": runner.sha(serial.decode("utf8", errors="replace").encode()),
            "marker": marker, "events": [event], "state": properties,
            "serial": {"session_id": report["session_id"], "offset": start, "next_offset": start + len(window), "data": window.decode(), "bytes": len(window)}}
        submitted[name] = source
        serial += window
    contents["serial.log"] = serial
    manifest = {"schema_version": 1, "session": {key: deepcopy(report[key]) for key in
                ("session_id", "device_id", "runtime", "pid", "firmware_sha256", "worker")},
                "device": {"device_id": report["device_id"]}, "units": state, "timeline": []}
    manifest["session"].update(state="running", units=attachments, program=deepcopy(report["executions"]["read"]["program"]))
    manifest["files"] = {path: {"size": len(data), "sha256": runner.sha(data)} for path, data in contents.items()}
    return report, contents, manifest, submitted


def bundle(contents, manifest, *, add=None):
    stream = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        warnings.simplefilter("ignore", UserWarning)
        for name, content in contents.items():
            archive.writestr(name, content)
        archive.writestr("manifest.json", canonical(manifest))
        if add:
            archive.writestr(*add)
    return stream.getvalue()


def reindex(contents, manifest):
    manifest["files"] = {path: {"size": len(data), "sha256": runner.sha(data)} for path, data in contents.items()}


class ScrollPlanTests(unittest.TestCase):
    def test_plan_never_constructs_client_calls_http_runs_or_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "uncreated"
            plans = [([], runner.DEVICES[0])] + [(["--device", device, "--api", "http://invalid.test", "--out-dir", str(target)], device) for device in runner.DEVICES]
            for args, device in plans:
                output = io.StringIO()
                with self.subTest(device=device), mock.patch.object(runner, "ProbeClient", side_effect=AssertionError("client")), \
                     mock.patch.object(runner, "run", side_effect=AssertionError("execution")), \
                     mock.patch("urllib.request.urlopen", side_effect=AssertionError("HTTP")), \
                     mock.patch.object(Path, "mkdir", side_effect=AssertionError("write")), redirect_stdout(output):
                    runner.main(args)
                plan = json.loads(output.getvalue())
                self.assertEqual(plan["status"], "PLANNED_NOT_EXECUTED")
                self.assertEqual(plan["controller_execution"], "NOT RUN")
                self.assertEqual(plan["hardware_validation"], "NOT RUN")
                self.assertFalse(target.exists())

    def test_execution_requires_runtime_hash_and_new_output(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "new"
            valid = ["--execute", "--out-dir", str(target), "--expected-runtime-sha256", "a" * 64]
            variants = [["--execute"], ["--execute", "--out-dir", str(target)],
                        ["--execute", "--expected-runtime-sha256", "a" * 64],
                        ["--execute", "--out-dir", temp, "--expected-runtime-sha256", "a" * 64],
                        ["--execute", "--out-dir", str(target), "--expected-runtime-sha256", "A" * 64]]
            for args in variants:
                with self.subTest(args=args), mock.patch.object(runner, "run", side_effect=AssertionError("execution")), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    runner.main(args)
            with mock.patch.object(runner, "run") as execute:
                runner.main(valid)
                execute.assert_called_once()
            self.assertFalse(target.exists())

    def test_all_generated_phases_parse_without_host_guest_execution(self):
        for phase in PHASES:
            options = {}
            if phase == "driver-live":
                options.update(expected_counter=-7, expected_increment=-7, expected_direction=1, ab_direction=1, source_count=7)
            if phase == "snapshot-read":
                options.update(reads=(4,), expected_hex=("00000005",))
            with self.subTest(phase=phase), mock.patch.object(runner, "ProbeClient", side_effect=AssertionError("client")):
                source = build_probe_source({"white": 1, "yellow": 2}, phase, **options)
                tree = ast.parse(source)
                compile(tree, "<not-executed-Scroll-guest>", "exec")
                self.assertIn("from unit import ScrollUnit", source)
                calls = [node.func.id for statement in tree.body if not isinstance(statement, ast.FunctionDef)
                         for node in ast.walk(statement) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
                if phase == "snapshot-read":
                    self.assertFalse(set(calls) & {"ScrollUnit", "_write", "_register", "_counter"})
                if phase == "snapshot-prime":
                    self.assertEqual(calls.count("_write"), 1)
                    self.assertNotIn("ScrollUnit", calls)

    def test_generator_rejects_unbound_reads_and_unsafe_inputs(self):
        for options in ({"phase": "unknown"}, {"phase": "driver-live"}, {"phase": "snapshot-read"},
                        {"phase": "snapshot-prime", "reads": (4,), "expected_hex": ("00",)},
                        {"phase": "registers", "source_count": 32768}, {"phase": "registers", "address": 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                build_probe_source({"white": 1, "yellow": 2}, **options)

    def test_events_only_accept_complete_marker_lines(self):
        good = 'SCROLL_FIXTURE {"kind":"done"}\r\n'
        self.assertEqual(runner.events(good, "SCROLL_FIXTURE"), [{"kind": "done"}])
        for bad in (good.rstrip(), "prefix " + good, good.replace("SCROLL_FIXTURE", "OTHER"), "SCROLL_FIXTURE []\n", "SCROLL_FIXTURE broken\n"):
            self.assertEqual(runner.events(bad, "SCROLL_FIXTURE"), [])


class ScrollEvidenceTests(unittest.TestCase):
    def test_valid_synthetic_zip_binds_raw_uart_credit_bytes_and_sources(self):
        report, contents, manifest, submitted = fixture()
        result = runner.validate_bundle(bundle(contents, manifest), report, submitted)
        self.assertEqual(result["members"], len(contents) + 1)

    def test_manifest_identity_member_index_hash_and_safe_paths(self):
        for mutate in (
            lambda c, m: m["session"].update(session_id="another-session"),
            lambda c, m: m["session"].update(device_id="atoms3r"),
            lambda c, m: m["session"]["worker"].update(generation=99),
            lambda c, m: m["device"].update(device_id="another-device"),
            lambda c, m: m["files"]["serial.log"].update(sha256="0" * 64),
            lambda c, m: m["files"]["serial.log"].update(size=1),
            lambda c, m: m["files"].pop("qom/snapshot.json"),
            lambda c, m: c.update({"../unsafe": b"fixture"}),
        ):
            report, contents, manifest, submitted = fixture()
            mutate(contents, manifest)
            if "../unsafe" in contents:
                reindex(contents, manifest)
            with self.subTest(mutate=mutate), self.assertRaises(RuntimeError):
                runner.validate_bundle(bundle(contents, manifest), report, submitted)

    def test_zip_duplicate_and_symlink_members_are_rejected(self):
        for symlink in (False, True):
            report, contents, manifest, submitted = fixture()
            extra = "serial.log"
            if symlink:
                extra = zipfile.ZipInfo("synthetic-link")
                extra.create_system = 3
                extra.external_attr = (stat.S_IFLNK | 0o777) << 16
                manifest["files"]["synthetic-link"] = {"size": len(b"fixture"), "sha256": runner.sha(b"fixture")}
            with self.subTest(symlink=symlink), self.assertRaises(RuntimeError):
                runner.validate_bundle(bundle(contents, manifest, add=(extra, b"fixture")), report, submitted)

    def test_internal_execution_and_revision_ids_must_match_path_and_report(self):
        for field in ("execution_id", "revision_id"):
            report, contents, manifest, submitted = fixture()
            program = report["executions"]["prime"]["program"]
            path = "programs/" + program["execution_id"] + ".json"
            saved = json.loads(contents[path]); saved[field] = "0" * len(saved[field]); contents[path] = canonical(saved)
            reindex(contents, manifest)
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                runner.validate_bundle(bundle(contents, manifest), report, submitted)

    def test_frozen_attachment_contract_and_live_unit_identity_are_bound(self):
        for mode in ("attachment", "contract", "unit-session", "unit-unavailable", "latest-execution"):
            report, contents, manifest, submitted = fixture()
            if mode == "attachment":
                runtime = json.loads(contents["units/runtime.json"])
                runtime["attachments"][0]["pins"]["white"] = 48
                contents["units/runtime.json"] = canonical(runtime)
            elif mode == "contract":
                contract = json.loads(contents["units/contract.json"])
                contract["source_hashes"]["catalog.json"] = "9" * 64
                contents["units/contract.json"] = canonical(contract)
            elif mode == "latest-execution":
                manifest["session"]["program"]["execution_id"] = "9" * 32
            else:
                state = json.loads(contents["units/state.json"])
                if mode == "unit-session":
                    state["session_id"] = "another-session"
                else:
                    state["units"][0]["available"] = False
                contents["units/state.json"] = canonical(state)
                manifest["units"] = state
            reindex(contents, manifest)
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                runner.validate_bundle(bundle(contents, manifest), report, submitted)

    def test_revision_metadata_file_bytes_cannot_disagree_with_source(self):
        report, contents, manifest, submitted = fixture()
        revision = report["executions"]["prime"]["program"]["revision_id"]
        path = "programs/" + revision + "/revision.json"
        metadata = json.loads(contents[path]); metadata["files"][0]["sha256"] = "0" * 64
        contents[path] = canonical(metadata)
        reindex(contents, manifest)
        with self.assertRaises(RuntimeError):
            runner.validate_bundle(bundle(contents, manifest), report, submitted)

    def test_negative_boolean_reversed_and_out_of_range_offsets_are_rejected(self):
        for mode in ("negative", "bool", "reversed", "past-end", "different-prefix-start"):
            report, contents, manifest, submitted = fixture()
            observation = report["observations"]["read"]; window = observation["serial"]; raw = contents["serial.log"]
            if mode == "negative":
                window["offset"] -= len(raw); observation["offset"] = window["offset"]
            elif mode == "bool":
                window["offset"] = True; observation["offset"] = True
            elif mode == "reversed":
                window["offset"], window["next_offset"] = window["next_offset"], window["offset"]
                observation["offset"] = window["offset"]
            elif mode == "past-end":
                window["next_offset"] = len(raw) + 100
            else:
                observation["offset"] -= 1
            # Rebind the claimed content/hashes to the malicious Python slice:
            # an implementation checking slice equality alone is insufficient.
            window["data"] = raw[window["offset"]:window["next_offset"]].decode("utf8", errors="replace")
            observation["prefix_sha256"] = runner.sha(raw[:observation["offset"]].decode("utf8", errors="replace").encode())
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                runner.validate_bundle(bundle(contents, manifest), report, submitted)

    def test_start_done_markers_must_be_bound_to_the_execution(self):
        report, contents, manifest, submitted = fixture()
        execution_id = report["executions"]["read"]["program"]["execution_id"]
        contents["serial.log"] = contents["serial.log"].replace(execution_id.encode(), b"9" * len(execution_id))
        observation = report["observations"]["read"]; window = observation["serial"]; raw = contents["serial.log"]
        window["data"] = raw[window["offset"]:window["next_offset"]].decode("utf8", errors="replace")
        reindex(contents, manifest)
        with self.assertRaises(RuntimeError):
            runner.validate_bundle(bundle(contents, manifest), report, submitted)

    def test_corrupted_original_source_is_not_accepted_with_a_new_member_hash(self):
        report, contents, manifest, submitted = fixture()
        revision = report["executions"]["read"]["program"]["revision_id"]
        path = "programs/" + revision + "/source.json"
        original = json.loads(contents[path]); original["files"]["main.py"] += "print('changed')\n"; contents[path] = canonical(original)
        reindex(contents, manifest)
        with self.assertRaises(RuntimeError):
            runner.validate_bundle(bundle(contents, manifest), report, submitted)


if __name__ == "__main__":
    unittest.main()
