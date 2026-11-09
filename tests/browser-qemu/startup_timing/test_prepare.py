"""Small source/path contracts only. No browser, guest, runtime asset or build."""

from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("startup_timing_prepare", HERE / "prepare.py")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


class StartupTimingPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = (Path(self.temp.name) / "repo with spaces").resolve()
        target = self.repo / "platform/tests"
        target.mkdir(parents=True)
        for name in ("test_public_qemu_headless_guest.mjs", "test_public_qemu_board_guest.mjs",
                     "public_qemu_artifacts.mjs", "public_qemu_worker_targets.mjs"):
            (target / name).write_bytes((prepare.REPO / "platform/tests" / name).read_bytes())

    def test_original_controls_and_call_through_hooks_survive_relocation(self):
        receipt = prepare.prepare(self.repo, Path(".work/observers"))
        self.assertEqual(receipt["status"], "PREPARED_NOT_EXECUTED")
        self.assertEqual(receipt["guest_execution"], "NOT RUN")
        self.assertEqual(receipt["basis_commit"], "b57e68a81045b739570c0add72878a0ab5620c56")
        self.assertEqual([r["expected_same_case_guest_checks"] for r in receipt["runners"]], [15, 26])
        bodies = []
        for row in receipt["runners"]:
            generated = (self.repo / ".work/observers" / row["generated_name"]).read_text()
            basis = (self.repo / ".work/observers" / f"{row['kind']}-basis.mjs").read_text()
            self.assertEqual(prepare.sha256(basis.encode()), row["basis_sha256"])
            self.assertEqual(prepare.controls(generated), prepare.controls(basis))
            self.assertIn((self.repo / "platform/tests/public_qemu_artifacts.mjs").as_uri(), generated)
            self.assertIn(json.dumps(str(self.repo)), generated)
            self.assertNotIn("@REPO_", generated)
            self.assertIn("return state.call(this,status)", generated)
            self.assertIn("return receive.call(this,data,...rest)", generated)
            self.assertIn("compile.call(this,bytes,options)", generated)
            bodies.append(prepare.observer(generated))
        self.assertEqual(bodies[0], bodies[1])
        for row in receipt["artifacts"]:
            data = (self.repo / ".work/observers" / row["path"]).read_bytes()
            self.assertEqual((len(data), prepare.sha256(data)), (row["bytes"], row["sha256"]))

    def test_output_cannot_escape_work_or_replace_work_itself(self):
        for output in (Path("outside"), Path(".work"), Path(".work/../../escape")):
            with self.subTest(output=output), self.assertRaises(ValueError):
                prepare.prepare(self.repo, output)
        self.assertFalse((self.repo / ".work").exists())

    def test_existing_directory_and_file_are_preserved(self):
        parent = self.repo / ".work"
        parent.mkdir()
        for name, directory in (("existing-dir", True), ("existing-file", False)):
            path = parent / name
            if directory:
                path.mkdir()
                sentinel = path / "sentinel"
            else:
                sentinel = path
            sentinel.write_text("preserve me")
            with self.assertRaises(FileExistsError):
                prepare.prepare(self.repo, path)
            self.assertEqual(sentinel.read_text(), "preserve me")

    def test_symlink_output_and_parent_are_rejected(self):
        work = self.repo / ".work"
        work.mkdir()
        outside = self.repo / "outside"
        outside.mkdir()
        (work / "link").symlink_to(outside, target_is_directory=True)
        for output in (work / "link", work / "link/nested"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                prepare.prepare(self.repo, output)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_work_is_rejected(self):
        outside = self.repo / "outside"
        outside.mkdir()
        (self.repo / ".work").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            prepare.prepare(self.repo, Path(".work/new"))
        self.assertEqual(list(outside.iterdir()), [])

    def test_source_drift_fails_before_creating_output(self):
        original = prepare.read_basis

        def drift(commit, path):
            return original(commit, path).replace("assert.ok(ok,name)", "assert.ok(true,name)")

        with patch.object(prepare, "read_basis", drift), self.assertRaisesRegex(ValueError, "fixed basis changed"):
            prepare.prepare(self.repo, Path(".work/new"))
        self.assertFalse((self.repo / ".work").exists())

    def test_current_runner_changes_do_not_affect_historical_preparation(self):
        path = self.repo / "platform/tests/test_public_qemu_board_guest.mjs"
        path.write_text("current board runner has different controller cases\n")
        receipt = prepare.prepare(self.repo, Path(".work/new"))
        expected = next(row["basis_sha256"] for row in receipt["runners"] if row["kind"] == "board")
        frozen = (self.repo / ".work/new/board-basis.mjs").read_bytes()
        self.assertEqual(prepare.sha256(frozen), expected)
        self.assertNotEqual(frozen, path.read_bytes())

    def test_unrecognized_reference_fails_before_creating_output(self):
        reference = self.repo / "references"
        reference.mkdir()
        (reference / "runtime75-headless-startup.mjs").write_text("unverified reference")
        with self.assertRaisesRegex(ValueError, "not the recorded executed"):
            prepare.prepare(self.repo, Path(".work/new"), reference)
        self.assertFalse((self.repo / ".work").exists())

    def test_identity_gate_keeps_fixed_profile_and_cleanup_requirements(self):
        prepare.prepare(self.repo, Path(".work/new"))
        wrapper = (self.repo / ".work/new/runtime75-fixed-preflight.mjs").read_text()
        for original in ("M5_EXPECT_WASM_SHA256", "profile.clockDivisor,1", "icountShift:5",
                         "result.checks.length,device==='atom-matrix'?15:26",
                         "result.worker_targets.after_removal.live.length,0",
                         "cleanup.engineOwnership.engineFallbackTerminations,0"):
            self.assertIn(original, wrapper)

    def test_repository_normalization_cannot_hide_an_extra_statement(self):
        receipt = prepare.prepare(self.repo, Path(".work/new"))
        for row in receipt["runners"]:
            source = (self.repo / ".work/new" / row["generated_name"]).read_text()
            binding = "const repo=" + json.dumps(str(self.repo)) + ";"
            evil = source.replace(binding, binding + " extraCall();", 1)
            with self.subTest(kind=row["kind"]), self.assertRaisesRegex(ValueError, "only one"):
                prepare.normalized(evil)
        wrapper = (self.repo / ".work/new/runtime75-fixed-preflight.mjs").read_text()
        binding = "const here=dirname(fileURLToPath(import.meta.url)),repo=" + json.dumps(str(self.repo)) + ";"
        with self.assertRaisesRegex(ValueError, "only one"):
            prepare.normalized(wrapper.replace(binding, binding + " extraCall();", 1), wrapper=True)


if __name__ == "__main__":
    unittest.main()
