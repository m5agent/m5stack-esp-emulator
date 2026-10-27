#!/usr/bin/env python3
"""Opt-in, read-only verification of the externally retained Unit run archives.

Ordinary platform CI checks metadata and synthetic adversarial contracts without
requiring historical execution artifacts. This command verifies the original
reports, immutable ZIPs, source snapshots and direct runtime bindings. It fails
if any selected artifact or baseline Git object is absent or differs; it never
contacts Device Service, downloads evidence or runs guest firmware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "platform/tools"), str(ROOT / "platform/tests"), str(ROOT / "tests/units")]
from unit_runtime import UnitRegistry
from _unit_host_control_evidence import CONTROL_WEB_CONTRACT, verify_control_web_evidence
from _unit_host_sensor_evidence import SENSOR_WEB_CONTRACT, verify_sensor_web_evidence


class HistoricalRuntimeEvidenceTests(unittest.TestCase):
    evidence_root: Path

    def setUp(self):
        # The selected metadata is the current source contract. Artifact paths
        # resolve only under the explicitly supplied historical checkout.
        self.registry = UnitRegistry()

    def test_scroll_program_evidence_binds_each_host_without_inheriting_web_pass(self):
        import sys
        from unittest import mock

        root = self.evidence_root
        with mock.patch.object(sys, 'path', [str(ROOT / 'tests/units'), *sys.path]):
            from run_live_scroll import validate_bundle
        profile = self.registry.profiles['scroll']
        self.assertEqual(profile['model_completeness'], 'partial')
        self.assertNotIn('host_validation', profile)  # Existing full host/Web contract is distinct.
        self.assertEqual(set(profile['program_validation']), {'cores3', 'atoms3r', 'sticks3', 'stopwatch'})
        for host, validation in profile['program_validation'].items():
            with self.subTest(host=host):
                self.assertEqual(validation['evidence_contract'], 'same-guest-scroll-protocol-v1')
                self.assertEqual(validation['hardware'], 'NOT RUN')
                self.assertEqual(validation['live_browser'], 'PASS' if host == 'cores3' else 'NOT RUN')
                path = root / validation['report']
                raw = path.read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), validation['report_sha256'])
                report = json.loads(raw)
                self.assertEqual(report['status'], 'PASS')
                for key in ('device_id', 'runtime', 'firmware_sha256'):
                    self.assertEqual(report[key], validation[key])
                self.assertEqual(report['device_id'], host)
                self.assertEqual(len(report['executions']), 22)
                self.assertEqual(hashlib.sha256(report['session_id'].encode('utf-8')).hexdigest(), validation['session_id_sha256'])
                self.assertIs(type(report['worker']['generation']), int)
                self.assertGreater(report['worker']['generation'], 0)
                for key in ('runtime_provenance', 'final_runtime_provenance'):
                    proof = report[key]
                    self.assertEqual((proof['status'], proof['method'], proof['pid']),
                                     ('PASS', validation['runtime_proof_kind'], report['pid']))
                    self.assertEqual(proof['session_id'], report['session_id'])
                    self.assertEqual(proof['expected_binary_sha256'], validation['runtime_binary_sha256'])
                    self.assertEqual(proof['observed_binary_sha256'], validation['runtime_binary_sha256'])
                data = (path.parent / 'evidence.zip').read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), validation['evidence_sha256'])
                with zipfile.ZipFile(path.parent / 'evidence.zip') as archive:
                    submitted = {name: json.loads(archive.read('programs/' + execution['program']['revision_id'] + '/source.json'))['files']['main.py']
                                 for name, execution in report['executions'].items()}
                validate_bundle(data, report, submitted)
                self.assertEqual(report['cleanup'], {'history_retained': True, 'flash_retained': False, 'last_frame_available': True})
                if host == 'cores3':
                    web_raw = (root / validation['live_browser_report']).read_bytes()
                    self.assertEqual(hashlib.sha256(web_raw).hexdigest(), validation['live_browser_report_sha256'])
                    web = json.loads(web_raw)
                    self.assertEqual((web['status'], web['device_id'], web['unit_id']), ('PASS', host, 'scroll'))
                    self.assertEqual(web['firmware_sha256'], report['firmware_sha256'])


    def test_host_pass_metadata_binds_exact_device_firmware_and_direct_runtime_evidence(self):
        root = self.evidence_root

        def pinned_json(path, expected_sha256):
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_sha256, str(path))
            return json.loads(raw)

        checked = []
        for unit_id, profile in self.registry.profiles.items():
            for host_id, validation in profile.get("host_validation", {}).items():
                if validation["status"] != "PASS":
                    continue
                with self.subTest(unit=unit_id, host=host_id):
                    self.assertIn(host_id, self.registry.hosts)
                    self.assertIn(host_id, profile["hosts"])
                    self.assertEqual(validation["device_id"], host_id)
                    report_path = (root / validation["report"]).resolve()
                    report = pinned_json(report_path, validation["report_sha256"])
                    self.assertEqual(report["status"], "PASS")
                    self.assertEqual(report["unit_id"], unit_id)
                    for field in ("device_id", "runtime", "firmware_sha256",
                                  "firmware_flavor", "evidence_sha256"):
                        self.assertEqual(report[field], validation[field], field)

                    proof = report["runtime_provenance"]
                    self.assertEqual(validation["runtime_proof_kind"], "direct-pid")
                    self.assertEqual(proof["kind"], validation["runtime_proof_kind"])
                    self.assertEqual(proof["status"], "VERIFIED")
                    self.assertEqual(hashlib.sha256(report["session_id"].encode("utf-8")).hexdigest(),
                                     validation["session_id_sha256"])
                    self.assertEqual(proof["session_id"], report["session_id"])
                    for field in ("firmware_sha256", "runtime_binary_sha256"):
                        self.assertEqual(proof[field], validation[field], field)
                    self.assertIs(type(proof["worker_generation"]), int)
                    self.assertGreater(proof["worker_generation"], 0)
                    # Legacy strict validators also bind the raw session and
                    # worker fields across the pinned report/ZIP/browser data.
                    # These values remain local to this explicit verification.
                    raw_validation = {**validation, "session_id": report["session_id"],
                                      "worker_generation": proof["worker_generation"]}
                    self.assertIs(type(proof["observed_pid"]), int)
                    self.assertGreater(proof["observed_pid"], 0)
                    evidence_contract = validation.get("evidence_contract", "host-probe-dual-observer-v1")
                    if evidence_contract == CONTROL_WEB_CONTRACT:
                        verify_control_web_evidence(root, report_path, report, raw_validation)
                    elif evidence_contract == SENSOR_WEB_CONTRACT:
                        verify_sensor_web_evidence(root, report_path, report, raw_validation)
                    else:
                        self.assertEqual(evidence_contract, "host-probe-dual-observer-v1")
                        independent = report["host_runtime_provenance"]
                        self.assertEqual(independent["status"], "PASS")
                        self.assertEqual(independent["session_id"], report["session_id"])
                        self.assertEqual(independent["pid"], proof["observed_pid"])
                        for field in ("expected_binary_sha256", "observed_binary_sha256"):
                            self.assertEqual(independent[field], validation["runtime_binary_sha256"])
                    evidence_path = (report_path.parent / report["evidence"]).resolve()
                    self.assertEqual(hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                                     validation["evidence_sha256"])
                    self.assertEqual(report["artifact_sha256"][report["evidence"]],
                                     validation["evidence_sha256"])
                    with zipfile.ZipFile(evidence_path) as archive:
                        session = json.loads(archive.read("manifest.json"))["session"]
                    for field in ("device_id", "runtime", "firmware_sha256"):
                        self.assertEqual(session[field], validation[field], field)
                    self.assertEqual(session["session_id"], report["session_id"])
                    self.assertEqual(session["state"], "running")
                    self.assertEqual(session["pid"], proof["observed_pid"])
                    self.assertEqual(session["worker"]["worker_id"], proof["worker_id"])
                    self.assertEqual(session["worker"]["generation"], proof["worker_generation"])
                    if evidence_contract == "host-probe-dual-observer-v1":
                        self.assertEqual({row["unit_id"] for row in report["attachments"]}, {unit_id})
                    self.assertEqual({row["unit_id"] for row in session["units"]}, {unit_id})

                    selection = pinned_json(root / validation["batch_selection"],
                                            validation["batch_selection_sha256"])
                    self.assertEqual(selection["device_id"], host_id)
                    self.assertEqual(selection["runtime"], validation["runtime"])
                    self.assertEqual(selection["expected_runtime_binary_sha256"],
                                     validation["runtime_binary_sha256"])
                    rows = [row for row in selection["cases"] if row["unit_id"] == unit_id]
                    self.assertEqual(len(rows), 1)
                    for layer in ("guest_controller", "live_browser"):
                        selected = rows[0][layer]
                        self.assertEqual((root / selected["report"]).resolve(), report_path)
                        self.assertEqual(selected["report_sha256"], validation["report_sha256"])
                        self.assertEqual((root / selected["evidence"]).resolve(), evidence_path)
                        self.assertEqual(selected["expected_firmware_flavor"],
                                         validation["firmware_flavor"])
                        selected_proof = selected["runtime_proof"]
                        self.assertEqual(selected_proof["kind"], "direct-pid")
                        self.assertEqual((root / selected_proof["path"]).resolve(), report_path)
                        self.assertEqual(selected_proof["report_pointer"], "/runtime_provenance")
                    checked.append((unit_id, host_id))
        self.assertTrue(checked, "no host-local PASS metadata was checked")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True,
                        help="Complete historical checkout containing the selected docs/evidence archives and baseline Git objects")
    parser.add_argument("--suite", choices=("all", "hosts", "scroll"), default="all")
    args = parser.parse_args()
    root = args.evidence_root.resolve()
    if not root.is_dir():
        parser.error("evidence root must be an existing directory")
    HistoricalRuntimeEvidenceTests.evidence_root = root
    names = {
        "hosts": "test_host_pass_metadata_binds_exact_device_firmware_and_direct_runtime_evidence",
        "scroll": "test_scroll_program_evidence_binds_each_host_without_inheriting_web_pass",
    }
    suite = (unittest.defaultTestLoader.loadTestsFromTestCase(HistoricalRuntimeEvidenceTests)
             if args.suite == "all" else unittest.TestSuite([HistoricalRuntimeEvidenceTests(names[args.suite])]))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
