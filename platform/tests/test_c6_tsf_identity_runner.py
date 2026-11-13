"""Final serial must preserve negative controls and reject late guest failures."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "c6_tsf_identity_runner", ROOT / "tests/firmware/esp32c6_tsf_identity/run.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class C6ProbeOracleTests(unittest.TestCase):
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
