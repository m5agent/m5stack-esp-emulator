"""Host validation and publication gates; no guest or caller-code execution.

Real compiler fixtures are shared with the bytecode parser suite. The fake
REPL returns explicit receipts, never evaluates submitted source or pretends
to verify a real guest filesystem. Wire EOF handling has its own suite.
"""
from __future__ import annotations

import ast
import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from test_mpy_bytecode import HELPER, NATIVE
from program_packages import ProgramPackageStore
import uiflow_package_runtime as runtime
from uiflow_runtime import UIFlowRuntimeError


def _snapshot(files):
    directories = set()
    for path in files:
        parent = Path(path).parent
        while str(parent) != ".":
            directories.add(parent.as_posix())
            parent = parent.parent
    return {
        "files": {path: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for path, data in files.items()},
        "directories": sorted(directories),
    }


class _ReplyREPL:
    """Classify finite requests and return fixture receipts without execution."""
    def __init__(self, files, *, existing=False):
        self.sources = []
        self.synchronized = 0
        self.capabilities = {"mpy": 6, "small_int_bits": 31, "existing": existing,
                             "directory_count": 0, "free_bytes": 1024 * 1024 * 1024}
        self.snapshot = _snapshot(files)
        self.revision = "a" * 64
        self.activation = {"cwd": runtime.GUEST_BASE + "/" + self.revision,
                           "removed_modules": ["old.package"]}
        self.short_write = False
        self.inventory_requests = 0
        self.inventory_output_limits = []

    def synchronize(self, callback=None):
        self.synchronized += 1
        if callback:
            callback()

    def execute(self, source, *, max_output):
        self.sources.append(source)
        marker = re.search(r"__M5_PKG_[0-9a-f]{32}:", source)
        if marker is None:
            raise AssertionError("fixture expected an RPC receipt marker")
        tree = ast.parse(source)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self_test_call = next((node for node in calls if isinstance(node.func, ast.Name) and node.func.id in {"exec", "eval", "compile"}), None)
        if self_test_call is not None:
            raise AssertionError("deployment must not start or compile the entrypoint")
        if "getattr(sys.implementation" in source:
            value = self.capabilities
        elif source.startswith("def _m5_pkg_inventory("):
            value = True
        elif any(isinstance(node.func, ast.Name) and node.func.id == "_m5_pkg_inventory" for node in calls):
            self.inventory_requests += 1
            self.inventory_output_limits.append(max_output)
            value = self.snapshot
        elif any(isinstance(node.func, ast.Attribute) and node.func.attr == "chdir" for node in calls):
            value = self.activation
        else:
            encoded = next((node.args[0] for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "a2b_base64"), None)
            if encoded is not None:
                if not isinstance(encoded, ast.Constant) or not isinstance(encoded.value, str):
                    raise AssertionError("file chunks must be inert base64 literals")
                value = len(base64.b64decode(encoded.value, validate=True)) - int(self.short_write)
            else:
                value = True
        # Escape Unicode as a conservative upper bound even though the pinned
        # guest emits UTF-8 directly. Enforce the encoded wire-output limit.
        output = (marker.group() + json.dumps(value, ensure_ascii=True) + "\r\n").encode("utf-8")
        if len(output) > max_output:
            raise UIFlowRuntimeError("program_rpc_output_too_large", "fixture output exceeded its bound")
        return {"stdout": output}

    def operations(self, attribute):
        return [index for index, source in enumerate(self.sources)
                if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                       and node.func.attr == attribute for node in ast.walk(ast.parse(source)))]


class InventoryValidationTests(unittest.TestCase):
    def setUp(self):
        self.files = {"main.py": b"pass\n", "pkg/driver.mpy": HELPER,
                      "pkg/sub/data.bin": b"\x00\xff", "assets/空文件": b""}
        self.snapshot = _snapshot(self.files)

    def rejects(self, value):
        with self.assertRaises(UIFlowRuntimeError) as caught:
            runtime._verify_inventory(self.files, value)
        self.assertEqual(caught.exception.code, "program_package_integrity")

    def test_complete_snapshot_accepts_exact_bytes_and_unordered_directory_receipts(self):
        self.snapshot["directories"].reverse()
        self.assertEqual(runtime._verify_inventory(self.files, self.snapshot), self.snapshot["files"])

    def test_snapshot_envelope_and_collection_types_fail_closed(self):
        for value in (None, [], {}, {"files": {}}, {"directories": []}, {**self.snapshot, "extra": True}):
            with self.subTest(value=value):
                self.rejects(value)
        for field, values in (("files", (None, [], "files")), ("directories", (None, {}, (), "pkg", [1], [[]]))):
            for value in values:
                with self.subTest(field=field, value=value):
                    self.rejects({**self.snapshot, field: value})

    def test_missing_extra_and_case_changed_file_paths_are_rejected(self):
        for change in ("missing", "extra", "case"):
            altered = copy.deepcopy(self.snapshot)
            row = altered["files"].pop("main.py")
            if change == "extra":
                altered["files"].update({"main.py": row, "unlisted": row})
            elif change == "case":
                altered["files"]["MAIN.py"] = row
            self.rejects(altered)

    def test_wrong_sizes_hashes_and_row_types_cannot_confirm_a_file(self):
        good = self.snapshot["files"]["main.py"]
        rows = (None, [], {}, {"size": good["size"]}, {"sha256": good["sha256"]},
                {**good, "size": -1}, {**good, "size": good["size"] + 1},
                {**good, "size": str(good["size"])}, {**good, "size": float(good["size"])},
                {**good, "sha256": "0" * 64}, {**good, "sha256": good["sha256"].upper()},
                {**good, "sha256": None})
        for row in rows:
            with self.subTest(row=row):
                altered = copy.deepcopy(self.snapshot)
                altered["files"]["main.py"] = row
                self.rejects(altered)
        altered = copy.deepcopy(self.snapshot)
        altered["files"]["assets/空文件"]["size"] = False
        self.rejects(altered)

    def test_missing_duplicate_case_alias_and_extra_empty_directories_are_rejected(self):
        for directories in ([], ["pkg", "assets"], self.snapshot["directories"] + ["pkg"],
                            self.snapshot["directories"] + ["unlisted-empty"],
                            ["PKG" if path == "pkg" else path for path in self.snapshot["directories"]]):
            with self.subTest(directories=directories):
                self.rejects({**self.snapshot, "directories": directories})


class MPYAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.capabilities = {"mpy": (0x2b << 8) | 6, "small_int_bits": 31}

    def rejects(self, data, code, *, capabilities=None):
        with self.assertRaises(UIFlowRuntimeError) as caught:
            runtime.validate_mpy({"helper.mpy": data}, self.capabilities if capabilities is None else capabilities)
        self.assertEqual(caught.exception.code, code)

    def test_real_official_helper_is_validated_without_importing_or_executing_it(self):
        with mock.patch.object(runtime, "validate_bytecode", wraps=runtime.validate_bytecode) as inspect:
            runtime.validate_mpy({"helper.mpy": HELPER}, self.capabilities)
        inspect.assert_called_once_with(HELPER)

    def test_python_and_resources_do_not_require_mpy_capabilities(self):
        runtime.validate_mpy({"main.py": b"raise AssertionError('never executed')", "asset.bin": b"M\xff"}, {})
        runtime.validate_mpy({"nested/HELPER.MPY": HELPER}, self.capabilities)

    def test_missing_boolean_or_unadmitted_guest_capabilities_are_explicit(self):
        for capabilities in ({}, {"mpy": 6}, {"mpy": True, "small_int_bits": 31},
                             {"mpy": 6, "small_int_bits": True}, {"mpy": "6", "small_int_bits": 31},
                             {"mpy": 6, "small_int_bits": 30}, {"mpy": 6, "small_int_bits": 32}):
            with self.subTest(capabilities=capabilities):
                self.rejects(HELPER, "program_mpy_capability_unknown", capabilities=capabilities)

    def test_major_and_small_int_requirements_are_compared_to_the_guest(self):
        self.rejects(HELPER, "program_mpy_incompatible", capabilities={"mpy": 7, "small_int_bits": 31})
        self.rejects(HELPER[:1] + b"\x07" + HELPER[2:], "program_mpy_incompatible")
        self.rejects(HELPER[:3] + b"\x20" + HELPER[4:], "program_mpy_incompatible")

    def test_native_headers_are_rejected_before_import(self):
        self.rejects(NATIVE, "program_mpy_native_unsupported")
        for feature in (1, 4, 0x80):
            with self.subTest(feature=feature):
                self.rejects(HELPER[:2] + bytes([feature]) + HELPER[3:], "program_mpy_native_unsupported")

    def test_forged_native_headers_still_reach_the_real_container_parser(self):
        disguised = bytearray(NATIVE)
        disguised[2] = 0
        self.rejects(bytes(disguised), "program_mpy_invalid")
        disguised[33] = 1  # Hide the native function-table constant as None too.
        self.rejects(bytes(disguised), "program_mpy_invalid")

    def test_invalid_magic_truncation_and_trailing_data_do_not_pass_a_header_only_gate(self):
        for data in (b"", b"M\x06\x00", b"X\x06\x00\x1f", HELPER[:4], HELPER[:-1], HELPER + b"\x00"):
            with self.subTest(length=len(data)):
                self.rejects(data, "program_mpy_invalid")


class PackagePublicationTests(unittest.TestCase):
    def setUp(self):
        self.files = {"main.py": b"print('never host executed')\n", "pkg/helper.mpy": HELPER,
                      "assets/data.bin": b"\x00\xff" * 2300, "assets/empty": b""}
        self.revision = {"revision_id": "a" * 64}
        self.console = object()

    def deploy(self, wire, progress=None):
        synchronized = mock.Mock()
        with mock.patch.object(runtime, "RawREPL", return_value=wire) as factory:
            result = runtime.deploy_package(self.console, self.files, self.revision, timeout=120,
                                            cancelled=lambda: False, on_synchronized=synchronized,
                                            on_progress=progress)
        factory.assert_called_once()
        self.assertEqual(factory.call_args.args, (self.console,))
        self.assertEqual(factory.call_args.kwargs["timeout"], 120)
        synchronized.assert_called_once_with()
        return result

    def rejects(self, wire, code):
        with self.assertRaises(UIFlowRuntimeError) as caught:
            self.deploy(wire)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(wire.operations("chdir"), [])

    def test_new_package_is_verified_then_published_then_activated(self):
        wire = _ReplyREPL(self.files)
        progress = []
        receipt = self.deploy(wire, progress.append)
        self.assertEqual(receipt["phase"], "activated")
        self.assertFalse(receipt["reused"])
        self.assertEqual(receipt["inventory"], _snapshot(self.files)["files"])
        self.assertEqual(receipt["removed_modules"], ["old.package"])
        self.assertEqual(wire.inventory_requests, 1)
        publish, activate = wire.operations("rename"), wire.operations("chdir")
        self.assertEqual(len(publish), 1)
        self.assertEqual(len(activate), 1)
        self.assertLess(publish[0], activate[0])
        phases = [value["phase"] for value in progress]
        self.assertLess(phases.index("verified"), phases.index("published"))
        self.assertLess(phases.index("published"), phases.index("activated"))
        self.assertEqual(next(value for value in reversed(progress) if value["phase"] == "writing")["written_bytes"], sum(map(len, self.files.values())))

    def test_binary_entrypoint_is_explicitly_rejected_before_guest_access(self):
        self.files = {"main.mpy": HELPER}
        self.revision["entrypoint"] = "main.mpy"
        wire = _ReplyREPL(self.files)
        with mock.patch.object(runtime, "RawREPL", return_value=wire) as factory:
            with self.assertRaises(UIFlowRuntimeError) as caught:
                runtime.deploy_package(self.console, self.files, self.revision, timeout=120,
                                       cancelled=lambda: False)
        self.assertEqual(caught.exception.code, "program_mpy_entrypoint_unsupported")
        factory.assert_not_called()
        self.assertEqual(wire.synchronized, 0)
        self.assertEqual(wire.sources, [])

    def test_reused_package_is_verified_again_without_writes_or_rename(self):
        wire = _ReplyREPL(self.files, existing=True)
        wire.capabilities.update(free_bytes=0, directory_count=runtime.MAX_GUEST_PACKAGES)
        receipt = self.deploy(wire)
        self.assertTrue(receipt["reused"])
        self.assertEqual(wire.inventory_requests, 1)
        self.assertEqual(wire.operations("write"), [])
        self.assertEqual(wire.operations("rename"), [])
        self.assertEqual(len(wire.operations("chdir")), 1)

    def test_maximum_legal_path_shape_has_a_bounded_inventory_above_64_kib(self):
        for label, prefix in (("quotes", '"' * 176), ("unicode", "\u00a0" * 88)):
            payload = {"files": {"main.py": {"encoding": "utf8", "data": "pass\n"}}}
            for index in range(63):
                # Eight components and 192 UTF-8 bytes; unique first-level
                # directories make nearly every ancestor close to the limit.
                path = f"{index:02d}" + prefix + "/a/b/c/d/e/f/g"
                self.assertEqual(len(path.encode("utf-8")), 192)
                self.assertEqual(len(path.split("/")), 8)
                payload["files"][path] = {"encoding": "utf8", "data": ""}
            with tempfile.TemporaryDirectory() as directory:
                store = ProgramPackageStore(Path(directory))
                revision = store.create(payload)
                self.files = store.read_files(revision["revision_id"])
            snapshot = _snapshot(self.files)
            size = len(json.dumps(snapshot, ensure_ascii=True).encode("utf-8"))
            self.assertGreater(size, 256 * 1024 if label == "unicode" else 65536)
            self.assertLess(size, 512 * 1024)
            self.assertEqual(len(self.files), 64)
            self.assertEqual(len(snapshot["directories"]), 63 * 7)
            for existing in (False, True):
                with self.subTest(paths=label, existing=existing):
                    wire = _ReplyREPL(self.files, existing=existing)
                    receipt = self.deploy(wire)
                    self.assertEqual(receipt["inventory"], snapshot["files"])
                    self.assertEqual(wire.inventory_output_limits, [512 * 1024])

    def test_corrupt_new_and_reused_snapshots_never_publish_or_activate(self):
        for existing in (False, True):
            for corruption in ("bytes", "empty-directory"):
                with self.subTest(existing=existing, corruption=corruption):
                    wire = _ReplyREPL(self.files, existing=existing)
                    if corruption == "bytes":
                        wire.snapshot["files"]["main.py"]["sha256"] = "0" * 64
                    else:
                        wire.snapshot["directories"].append("extra-empty")
                    self.rejects(wire, "program_package_integrity")
                    self.assertEqual(wire.operations("rename"), [])

    def test_short_write_never_reads_back_publishes_or_activates(self):
        wire = _ReplyREPL(self.files)
        wire.short_write = True
        self.rejects(wire, "program_package_short_write")
        self.assertEqual(wire.inventory_requests, 0)
        self.assertEqual(wire.operations("rename"), [])

    def test_directory_and_space_quotas_fail_before_file_writes(self):
        for fields, code in (({"directory_count": runtime.MAX_GUEST_PACKAGES}, "program_package_guest_quota"),
                             ({"directory_count": True}, "program_package_guest_quota"),
                             ({"free_bytes": 0}, "program_package_no_space"),
                             ({"free_bytes": True}, "program_package_no_space")):
            with self.subTest(fields=fields):
                wire = _ReplyREPL(self.files)
                wire.capabilities.update(fields)
                self.rejects(wire, code)
                self.assertEqual(wire.operations("write"), [])
                self.assertEqual(wire.operations("rename"), [])

    def test_invalid_mpy_never_reaches_file_write_or_activation(self):
        self.files["pkg/helper.mpy"] = NATIVE[:2] + b"\x00" + NATIVE[3:]
        wire = _ReplyREPL(self.files)
        self.rejects(wire, "program_mpy_invalid")
        self.assertEqual(wire.operations("write"), [])
        self.assertEqual(wire.operations("rename"), [])

    def test_lost_activation_receipt_never_claims_activated_after_publication(self):
        wire = _ReplyREPL(self.files)
        wire.activation["cwd"] = "/unexpected/cwd"
        progress = []
        with self.assertRaises(UIFlowRuntimeError) as caught:
            self.deploy(wire, progress.append)
        self.assertEqual(caught.exception.code, "program_package_activation_unconfirmed")
        self.assertEqual(len(wire.operations("rename")), 1)
        self.assertEqual(len(wire.operations("chdir")), 1)
        self.assertEqual(progress[-1]["phase"], "published")


if __name__ == "__main__":
    unittest.main(verbosity=2)
