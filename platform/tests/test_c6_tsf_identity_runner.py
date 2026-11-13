"""Final serial must preserve negative controls and reject late guest failures."""
import importlib.util
from pathlib import Path
import unittest
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "c6_tsf_identity_runner", ROOT / "tests/firmware/esp32c6_tsf_identity/run.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class C6ProbeOracleTests(unittest.TestCase):
    def test_preparation_ignores_dirty_board_at_same_head(self):
        spec = importlib.util.spec_from_file_location(
            "c6_probe_prepare", ROOT / "tests/firmware/esp32c6_tsf_identity/prepare.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            board = source / "boards/_jsonfiles/board.json"
            board.parent.mkdir(parents=True)
            board.write_bytes(b"pinned board\n")
            subprocess.run(["git", "add", "boards"], cwd=source, check=True)
            subprocess.run(["git", "-c", "user.name=Probe", "-c", "user.email=probe@example.invalid",
                            "commit", "-qm", "pin"], cwd=source, check=True)
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
            board.write_bytes(b"dirty replacement\n")
            (board.parent / "untracked.h").write_bytes(b"not pinned\n")
            target = Path(temp) / "copied"
            module.copy_git_directory(source, commit, "boards/_jsonfiles", target)
            self.assertEqual((target / "board.json").read_bytes(), b"pinned board\n")
            self.assertFalse((target / "untracked.h").exists())
            self.assertEqual(module.git_bytes(source, commit, "boards/_jsonfiles/board.json"), b"pinned board\n")

    def test_tsf_full_zip_late_failure_and_missing_case(self):
        serial = "ESP-ROM:esp32c6\n" + "".join(
            f"TSF_CASE index={index} result=PASS\n" for index in range(6))
        serial += "TSF_PROBE_DONE passed=6 total=6\n"
        self.assertEqual(RUNNER.validate_serial(serial, "tsf", "after")["passed"], 6)
        for changed in (serial + "ESP-ROM:esp32c6", serial + "Guru Meditation Error",
                        serial.replace("index=5", "index=4"), serial.replace("result=PASS", "result=FAIL", 1)):
            with self.subTest(changed=changed[-70:]), self.assertRaises(AssertionError):
                RUNNER.validate_serial(changed, "tsf", "after")

    def test_identity_reset_and_radio_gap_remain_independent(self):
        one = "ESP-ROM:esp32c6\n"
        for name, value in (("factory", "02123456789a0000"), ("sta", "02123456789a"),
                            ("ieee", "021234fffe56789a")):
            one += f"IDENTITY name={name} rc=0 bytes={value}\n"
        one += "IDENTITY_API result=PASS\nIEEE_ADDRESS set=0 get=0 result=FAIL\nIDENTITY_PROBE_DONE\n"
        self.assertTrue(RUNNER.validate_serial(one + one, "identity", "after", True)["reset_stable"])
        for changed in (one, one + one.replace("02123456789a", "02123456789b"),
                        one + one + "assert failed:", (one + one).replace("get=0", "get=1")):
            with self.subTest(changed=changed[-70:]), self.assertRaises(AssertionError):
                RUNNER.validate_serial(changed, "identity", "after", True)


if __name__ == "__main__":
    unittest.main()
