"""Static contracts for the CAN/LoRaWAN lane unlock evidence batch.

These checks never launch QEMU, a Device Service or firmware. They pin the
platform contract that unlocked the CAN/TWAI and LoRaWAN UART byte lanes, the
three committed evidence reports/summary and the honest boundaries:

- `can`/`mini-can` are now `implemented` on cores3 with the QOM contract of the
  batch-7 CAN client model (`frames-observed`/`injected-frames`/`last-frame-hex`/
  `inject-hex`); the frozen release `unit/can.py` wrapper limitation is recorded.
- `lorawan-us915` is `implemented` and asserts only the UART AT byte layer; the
  frozen ASR650x driver / STM32WLE5 product mismatch and US915 RF are NOT RUN.
- The lane unlock needed no new QEMU source patch: the QEMU source state is the
  canonical 35-layer chain through 0154 and patch 0157 is not used.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/2026-11-03-unit-can-lorawan"
CASES = ("can", "mini-can", "lorawan-us915")
CAN_CASES = ("can", "mini-can")
CAN_QOM = {"inject-hex", "frames-observed", "injected-frames", "last-frame-hex"}
LORAWAN_QOM = {"responses-hex", "tx-hex", "frames-sent", "frames-injected"}
CANONICAL_LAST = "0154-unit-batch10-evidence-fixes.patch"
CANONICAL_FIRST = "0120-unit-i2c-dlight-command-mask.patch"


class UnitCanLorawanEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]
        cls.summary = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
        cls.reports = {
            case: json.loads((EVIDENCE / f"report-{case}.json").read_text(encoding="utf-8"))
            for case in CASES
        }

    def test_profiles_are_implemented_on_cores3_with_qom_contract(self):
        for case in CASES:
            unit = self.units[case]
            profile = self.profiles[case]
            self.assertEqual(unit["model_status"], "partial", case)
            self.assertEqual(unit["runtime"]["status"], "implemented", case)
            self.assertEqual(profile["status"], "implemented", case)
            self.assertEqual(profile["hosts"], ["cores3"], case)
            self.assertTrue(profile["blocker"], case)
            self.assertIn("NOT RUN", profile["blocker"], case)
        for case in CAN_CASES:
            self.assertEqual(set(self.units[case]["runtime"]["properties"]), CAN_QOM, case)
            self.assertEqual(self.units[case]["interface"]["bus"], "can", case)
            self.assertEqual(set(self.profiles[case]["state"]), CAN_QOM - {"inject-hex"}, case)
            self.assertEqual(set(self.profiles[case]["inputs"]), {"inject-hex"}, case)
        lorawan = self.units["lorawan-us915"]
        self.assertEqual(set(lorawan["runtime"]["properties"]), LORAWAN_QOM)
        self.assertEqual(set(self.profiles["lorawan-us915"]["state"]), LORAWAN_QOM)
        self.assertEqual(set(self.profiles["lorawan-us915"]["inputs"]), {"responses-hex"})

    def test_evidence_reports_and_hashes_match_profiles(self):
        for case in CASES:
            profile = self.profiles[case]
            evidence = profile["virtual_device_evidence"]
            report_path = ROOT / evidence["report"]
            self.assertTrue(report_path.is_file(), case)
            self.assertEqual(hashlib.sha256(report_path.read_bytes()).hexdigest(),
                             evidence["report_sha256"], case)
            self.assertTrue(evidence["evidence_sha256"], case)
            self.assertTrue(evidence["firmware_sha256"], case)
            self.assertTrue(evidence["runtime_binary_sha256"], case)
            self.assertEqual(evidence["hardware"], "NOT RUN", case)
            self.assertEqual(evidence["live_browser"], "NOT RUN", case)
            patches = evidence["patches"]
            self.assertEqual(len(patches), 35, case)
            self.assertEqual(patches[0], CANONICAL_FIRST, case)
            self.assertEqual(patches[-1], CANONICAL_LAST, case)
            # No parallel evidence-fix patch is needed for this batch.
            self.assertFalse(any(p.startswith(("0155", "0156", "0157", "0158")) for p in patches), case)

    def test_reports_are_pass_and_match_the_observed_lane(self):
        for case in CASES:
            report = self.reports[case]
            self.assertEqual(report["status"], "PASS", case)
            self.assertTrue(all(report["checks"].values()), case)
            self.assertTrue(report["qom_samples"], case)
        for case in CAN_CASES:
            report = self.reports[case]
            observations = report["observations"][case]
            self.assertEqual(observations["frames_observed"], 1, case)
            self.assertEqual(observations["injected_frames"], 1, case)
            self.assertEqual(observations["last_frame_hex"], "123#0102030405060708", case)
            self.assertEqual(observations["guest_recv"], "456#deadbeef", case)
            self.assertEqual(observations["can_state_final"], "6", case)
            self.assertIn("wrapper", observations["wrapper_caveat"], case)
            self.assertIn("NOT RUN", observations["boundary"], case)
        lorawan = self.reports["lorawan-us915"]
        observations = lorawan["observations"]["lorawan-us915"]
        tx_hex = observations["tx_hex"]
        self.assertTrue(tx_hex.startswith("41542b43574f524b4d4f44453d"), tx_hex)  # AT+CWORKMODE=
        self.assertIn("41542b44545258", tx_hex)  # AT+DTRX
        self.assertEqual(observations["frames_sent"], 3)
        self.assertEqual(observations["frames_injected"], 3)
        self.assertIn("byte layer", observations["boundary"])
        self.assertIn("NOT RUN", observations["boundary"])

    def test_summary_has_single_build_and_three_passes(self):
        self.assertEqual(self.summary["validation"], "virtual-device validation")
        self.assertEqual(len(self.summary["cases"]), 3)
        self.assertEqual([case["status"] for case in self.summary["cases"]], ["PASS"] * 3)
        self.assertEqual([case["unit_id"] for case in self.summary["cases"]], list(CASES))
        builds = self.summary["qemu_builds"]
        self.assertEqual(len(builds), 1)
        runtime_sha = next(iter(builds.values()))["runtime_binary_sha256"]
        for case in CASES:
            self.assertEqual(self.reports[case]["runtime_binary_sha256"], runtime_sha, case)
        self.assertIn("no new QEMU source patch", next(iter(builds.values()))["note"])
        self.assertIn("no new QEMU source patch", self.summary["qemu_builds"]["canonical-35-layers"]["note"])

    def test_no_qemu_patch_was_needed(self):
        patches_dir = ROOT / "patches/qemu-m5stack-peripherals"
        for number in ("0155", "0157"):
            self.assertFalse(list(patches_dir.glob(f"{number}-*.patch")), number)
        readme = (patches_dir / "README.md").read_text(encoding="utf-8")
        self.assertIn("0154", readme)
        evidence_readme = (EVIDENCE / "README.md").read_text(encoding="utf-8")
        self.assertIn("不需要新的 QEMU 源码补丁", evidence_readme)
        self.assertIn("PORT.A harness", evidence_readme)

    def test_wrapper_and_product_mismatch_boundaries_are_explicit(self):
        for case in CAN_CASES:
            self.assertIn("wrapper", self.profiles[case]["blocker"].lower(), case)
        self.assertIn("ASR650x", self.profiles["lorawan-us915"]["blocker"])
        self.assertIn("STM32WLE5", self.profiles["lorawan-us915"]["blocker"])
        # Catalog blocker mirrors the profile so the API/UI expose the same boundary.
        for case in CASES:
            self.assertEqual(self.units[case]["blocker"], self.profiles[case]["blocker"], case)
            self.assertEqual(self.units[case]["runtime"]["blocker"], self.profiles[case]["blocker"], case)


if __name__ == "__main__":
    unittest.main()
