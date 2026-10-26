"""Fixed bytecode provenance and scripted probe receipts; no guest execution."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from mpy_bytecode import validate_bytecode
from guest_console import GuestConsoleError
import uiflow_main_loader as loader
from uiflow_runtime import UIFlowRuntimeError


def verified_capability(nonce="a" * 32):
    return {"schema_version": 1, "status": "verified", "mpy_entrypoint": True, "loader": loader.LOADER,
        "mpy": 6, "small_int_bits": 31, "probe": {
            "kind": loader.PROBE_KIND, "nonce": nonce, "status": "PASS", "owner_restored": True,
            "cleanup_complete": True, "body_entered": True, "owner_before_id": 101, "owner_after_id": 101,
            "canary_sha256": loader.CANARY_SHA256, "source_sha256": loader.CANARY_SOURCE_SHA256,
            "compiler_sha256": loader.CANARY_COMPILER_SHA256, "file_sha256": loader.CANARY_SHA256,
            "file_bytes": len(loader.CANARY_BYTES), "error": None,
            "actual_identity": {"if_main": True, "name": "__main__", "file": loader.PROBE_ROOT + nonce + "/main.mpy",
                "real_main_name": "main", "main_id": 202, "sys_main_id": 202, "import_main_id": 202, "nonce": nonce}}}


class ReplyREPL:
    """Script responses to a fixed canary request; never execute its source."""
    def __init__(self, change=None, output=None):
        self.change, self.output, self.source, self.limit = change, output, None, None
        self.synchronize = mock.Mock(side_effect=lambda callback=None: callback() if callback else None)

    def execute(self, source, *, max_output):
        self.source, self.limit = source, max_output
        marker = re.search(r"__M5_LOADER_([0-9a-f]{32}):", source)
        if marker is None:
            raise AssertionError("missing nonce receipt")
        proof = verified_capability(marker.group(1))
        observed = {key: value for key, value in proof["probe"].items() if key not in {
            "kind", "nonce", "status", "canary_sha256", "source_sha256", "compiler_sha256"}}
        observed.update(mpy=6, small_int_bits=31)
        if self.change:
            self.change(observed)
        output = (marker.group() + json.dumps(observed) + "\r\n").encode()
        return {"stdout": output if self.output is None else self.output}


class MainLoaderTests(unittest.TestCase):
    def probe(self, reply):
        synchronized = mock.Mock()
        console = object()
        with mock.patch.object(loader, "RawREPL", return_value=reply) as factory:
            result = loader.probe_main_loader(console, timeout=7, cancelled=lambda: False, on_synchronized=synchronized)
        factory.assert_called_once()
        self.assertIs(factory.call_args.args[0], console)
        self.assertEqual(factory.call_args.kwargs["timeout"], 7)
        synchronized.assert_called_once_with()
        return result

    def test_fixed_passive_canary_is_real_pure_bytecode_with_auditable_source_and_recipe(self):
        self.assertEqual(hashlib.sha256(loader.CANARY_BYTES).hexdigest(), loader.CANARY_SHA256)
        self.assertEqual(hashlib.sha256(loader.CANARY_SOURCE.encode()).hexdigest(), loader.CANARY_SOURCE_SHA256)
        self.assertEqual(loader.CANARY_BYTES[:4], b"M\x06\x00\x1f")
        validate_bytecode(loader.CANARY_BYTES)
        tree = ast.parse(loader.CANARY_SOURCE)
        self.assertEqual([alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names], ["sys"])
        self.assertNotIn("compile(", loader.CANARY_SOURCE)
        self.assertNotIn("exec(", loader.CANARY_SOURCE)
        self.assertEqual(loader.CANARY_RECIPE["argv"], ["mpy-cross", "-s", "m5-main-loader-canary.py", "-o", "canary.mpy", "canary.py"])

    def test_available_pinned_official_compiler_reproduces_exact_canary_bytes(self):
        compiler = ROOT / ".work/uiflow-package-live-20261026/mpy-cross-78ff170d/micropython/mpy-cross/build/mpy-cross"
        if not compiler.is_file():
            self.skipTest("optional pinned local compiler unavailable; fixed bytes still parsed separately")
        self.assertEqual(hashlib.sha256(compiler.read_bytes()).hexdigest(), loader.CANARY_COMPILER_SHA256)
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "canary.py", Path(directory) / "canary.mpy"
            source.write_text(loader.CANARY_SOURCE)
            subprocess.run([str(compiler), "-s", "m5-main-loader-canary.py", "-o", str(output), str(source)], check=True, capture_output=True, timeout=10)
            self.assertEqual(output.read_bytes(), loader.CANARY_BYTES)

    def test_core_proof_allows_extra_session_identity_without_trusting_it(self):
        proof = verified_capability()
        self.assertTrue(loader.main_loader_verified(proof))
        proof["identity"] = {"not_validated_here": True}
        self.assertTrue(loader.main_loader_verified(proof))
        self.assertIs(loader.require_main_loader(proof), proof)

    def test_boolean_or_missing_and_mutated_proofs_never_admit_a_loader(self):
        for record in (None, True, False, {}, {"mpy_entrypoint": True}):
            self.assertFalse(loader.main_loader_verified(record))
        mutations = [("schema_version", True), ("status", "unsupported"), ("mpy_entrypoint", 1),
                     ("loader", "ordinary-import"), ("mpy", True), ("mpy", 7), ("small_int_bits", True),
                     ("small_int_bits", 32), ("probe.nonce", "A" * 32), ("probe.status", "FAIL"),
                     ("probe.owner_restored", False), ("probe.cleanup_complete", False), ("probe.body_entered", False),
                     ("probe.owner_after_id", 999), ("probe.owner_before_id", True), ("probe.file_bytes", True),
                     ("probe.file_sha256", "0" * 64), ("probe.canary_sha256", "0" * 64),
                     ("probe.source_sha256", "0" * 64), ("probe.compiler_sha256", "0" * 64),
                     ("probe.error", {"type": "ValueError"}), ("probe.actual_identity.if_main", 1),
                     ("probe.actual_identity.name", "main"), ("probe.actual_identity.real_main_name", None),
                     ("probe.actual_identity.file", "/flash/main.mpy"), ("probe.actual_identity.main_id", 101),
                     ("probe.actual_identity.import_main_id", 101), ("probe.actual_identity.nonce", "b" * 32)]
        for path, value in mutations:
            record = verified_capability()
            parent = record
            keys = path.split(".")
            for key in keys[:-1]:
                parent = parent[key]
            parent[keys[-1]] = value
            with self.subTest(path=path, value=value):
                self.assertFalse(loader.main_loader_verified(record))
                with self.assertRaises(UIFlowRuntimeError) as caught:
                    loader.require_main_loader(record)
                self.assertEqual(caught.exception.code, "program_mpy_entrypoint_unsupported")

    def test_probe_uses_real_import_instruction_and_finally_restores_exact_owner(self):
        reply = ReplyREPL()
        result = self.probe(reply)
        self.assertTrue(loader.main_loader_verified(result))
        self.assertEqual(reply.limit, 16384)
        tree = ast.parse(reply.source)
        imports = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__" and len(node.args) == 5]
        self.assertEqual(len(imports), 1)
        self.assertEqual([node.value for node in imports[0].args], ["main", None, None, False, 0])
        self.assertIn("finally:", reply.source)
        self.assertIn("os.chdir(_m5_cap_cwd)", reply.source)
        self.assertIn("sys.modules[_m5_cap_name]=_m5_cap_pair[1]", reply.source)
        self.assertIn("sys.modules.pop(_m5_cap_name,None)", reply.source)
        self.assertNotIn("sys._m5", reply.source)
        self.assertNotIn("machine.reset", reply.source)

    def test_stock_semantics_and_unknown_abi_return_unsupported_only_after_restoration(self):
        def stock(observed):
            observed["actual_identity"].update(if_main=False, name="main", real_main_name=None, sys_main_id=101, import_main_id=101)
        def unknown(observed):
            observed.update(mpy=None, small_int_bits=31, body_entered=False, actual_identity=None, file_sha256=None, file_bytes=None)
        def missing_file(observed):
            observed["actual_identity"].update(file=None)
        for change in (stock, unknown, missing_file):
            with self.subTest(change=change.__name__):
                result = self.probe(ReplyREPL(change))
                self.assertEqual(result["status"], "unsupported")
                self.assertFalse(result["mpy_entrypoint"])
                self.assertEqual(result["probe"]["status"], "FAIL")
                self.assertTrue(result["probe"]["owner_restored"])

    def test_importer_rejection_is_unsupported_but_uncontrolled_error_or_restore_failure_raises(self):
        def incompatible(observed):
            observed.update(body_entered=False, actual_identity=None, error={"type": "ValueError", "message": "incompatible .mpy file"})
        self.assertEqual(self.probe(ReplyREPL(incompatible))["status"], "unsupported")
        for field, value, code in (("owner_restored", False, "program_main_loader_restore_failed"),
                                   ("owner_after_id", 999, "program_main_loader_restore_failed"),
                                   ("cleanup_complete", False, "program_main_loader_restore_failed"),
                                   ("restore_error", {"type": "OSError"}, "program_main_loader_restore_failed"),
                                   ("error", {"type": "RuntimeError"}, "program_main_loader_probe_failed"),
                                   ("error", {"type": "NameError", "message": "unexpected probe bug"}, "program_main_loader_probe_failed")):
            with self.subTest(field=field), self.assertRaises(UIFlowRuntimeError) as caught:
                self.probe(ReplyREPL(lambda observed: observed.update({field: value})))
            self.assertEqual(caught.exception.code, code)

    def test_malformed_or_missing_receipt_cannot_report_capability(self):
        for output in (b"", b"ordinary output", b"\xff", "not bytes", 42):
            with self.subTest(output=output), self.assertRaises(UIFlowRuntimeError) as caught:
                self.probe(ReplyREPL(output=output))
            self.assertEqual(caught.exception.code, "program_main_loader_probe_failed")

    def test_lost_console_never_becomes_a_safe_unsupported_result(self):
        for code, expected in (("console_eof", "program_main_loader_probe_failed"), ("console_cancelled", "program_cancelled")):
            reply = ReplyREPL()
            reply.execute = mock.Mock(side_effect=GuestConsoleError(code, "scripted lost console"))
            with self.subTest(code=code), self.assertRaises(UIFlowRuntimeError) as caught:
                self.probe(reply)
            self.assertEqual(caught.exception.code, expected)


if __name__ == "__main__":
    unittest.main()
