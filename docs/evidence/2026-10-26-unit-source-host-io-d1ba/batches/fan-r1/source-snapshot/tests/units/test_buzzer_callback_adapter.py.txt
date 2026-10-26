"""Offline Buzzer adapter and timer-window controls; no service or guest runs."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import run_annotation_cases as annotation
import run_io_cases as runner

OFFICIAL_BUZZER_SHA = "a64cd1e918c92b97f3b0cd8c2e451416d0abfda7cd83aaef18883869f2e5c0c3"
REFERENCE_BASE_SHA = "1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264"
REFERENCE_IMAGE_SHA = "d06e243cb5575daacd43cdfe02fe0c45d5ccdd1aa25988b17566696370f8b911"


class CallbackCopyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="m5-buzzer-adapter-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.files = self.root / "files"
        self.copied = self.files / "io_drivers/buzzer.py"
        self.copied.parent.mkdir(parents=True)
        self.original = runner.PROBE / "io_drivers/buzzer.py"
        self.original_bytes = self.original.read_bytes()
        self.assertEqual(hashlib.sha256(self.original_bytes).hexdigest(), OFFICIAL_BUZZER_SHA)
        self.copied.write_bytes(self.original_bytes)
        self.manifest = runner.driver_manifest()

    def test_exact_copy_patch_receipt_and_real_reverse_preserve_vendor(self):
        record = runner.patch_buzzer_callback_copy(self.files, self.manifest)
        self.assertNotEqual(self.copied.read_bytes(), self.original_bytes)
        self.assertEqual(self.original.read_bytes(), self.original_bytes)
        self.assertEqual(record["original_driver_sha256"], OFFICIAL_BUZZER_SHA)
        self.assertEqual(record["patched_driver_sha256"], runner.digest(self.copied))
        self.assertEqual(record["patch_sha256"], runner.digest(runner.BUZZER_CALLBACK_PATCH))
        self.assertIs(record["original_driver_unchanged"], True)
        self.assertIs(record["frozen_modules_modified"], False)
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i",
                        str(runner.BUZZER_CALLBACK_PATCH), "--reverse"],
                       cwd=self.files, check=True, capture_output=True)
        self.assertEqual(self.copied.read_bytes(), self.original_bytes)
        self.assertEqual(self.original.read_bytes(), self.original_bytes)

    def test_drifted_generated_copy_or_manifest_is_rejected_before_patch(self):
        for drift in ("copy", "manifest"):
            with self.subTest(drift=drift):
                self.copied.write_bytes(self.original_bytes)
                manifest = deepcopy(self.manifest)
                if drift == "copy":
                    self.copied.write_bytes(self.original_bytes + b"\n# unrelated change\n")
                else:
                    manifest["buzzer.py"]["sha256"] = "0" * 64
                with patch.object(runner.subprocess, "run") as command:
                    with self.assertRaisesRegex(RuntimeError, "exact pinned official source"):
                        runner.patch_buzzer_callback_copy(self.files, manifest)
                    command.assert_not_called()
                self.assertEqual(self.original.read_bytes(), self.original_bytes)

    def test_drifted_vendor_copy_is_rejected_without_touching_real_vendor(self):
        vendor_probe = self.root / "vendor-probe"
        vendor = vendor_probe / "io_drivers/buzzer.py"
        vendor.parent.mkdir(parents=True)
        vendor.write_bytes(self.original_bytes + b"\n# changed vendor snapshot\n")
        with patch.object(runner, "PROBE", vendor_probe), patch.object(runner.subprocess, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "exact pinned official source"):
                runner.patch_buzzer_callback_copy(self.files, self.manifest)
            command.assert_not_called()
        self.assertEqual(self.original.read_bytes(), self.original_bytes)

    def load_wrapper(self, source):
        calls = []

        class OriginalHaptic:
            def __init__(self, pin, freq):
                self.pin, self.frequency = pin, freq

            def _cb(self):
                calls.append(self)

        package = ModuleType("driver")
        package.__path__ = []
        module = ModuleType("driver.haptic")
        module.Haptic = OriginalHaptic
        namespace = {"__name__": "offline_buzzer_wrapper"}
        with patch.dict(sys.modules, {"driver": package, "driver.haptic": module}):
            exec(compile(source, "offline-buzzer.py", "exec"), namespace)
        return namespace["BuzzerUnit"], OriginalHaptic, calls

    def test_adapter_accepts_timer_or_no_arg_and_calls_original_callback_once(self):
        runner.patch_buzzer_callback_copy(self.files, self.manifest)
        wrapper, original_haptic, calls = self.load_wrapper(self.copied.read_bytes())
        unit = wrapper((1, 2))
        self.assertIsInstance(unit, original_haptic)
        self.assertEqual((unit.pin, unit.frequency), (2, 4000))
        for args in ((), (None,), (object(),)):
            with self.subTest(argc=len(args), timer_none=args == (None,)):
                calls.clear()
                unit._cb(*args)
                self.assertEqual(calls, [unit])

    def test_unpatched_wrapper_keeps_original_callback_arity(self):
        wrapper, original_haptic, calls = self.load_wrapper(self.original_bytes)
        self.assertNotIn("_cb", wrapper.__dict__)
        self.assertIs(wrapper._cb, original_haptic._cb)
        unit = wrapper((1, 2))
        with self.assertRaises(TypeError):
            unit._cb(object())
        self.assertEqual(calls, [])
        unit._cb()
        self.assertEqual(calls, [unit])

    def test_adapter_does_not_swallow_original_callback_failure(self):
        runner.patch_buzzer_callback_copy(self.files, self.manifest)
        wrapper, original_haptic, calls = self.load_wrapper(self.copied.read_bytes())
        unit = wrapper((1, 2))

        def fail(self):
            calls.append(self)
            raise RuntimeError("original callback failed")

        with patch.object(original_haptic, "_cb", fail):
            with self.assertRaisesRegex(RuntimeError, "original callback failed"):
                unit._cb(object())
        self.assertEqual(calls, [unit])


class TimerWindowTests(unittest.TestCase):
    def sample(self, newline="\n"):
        before = newline.join(("IO_PROBE_READY buzzer", "IO_BUZZER_ONCE 2000 50", "timer wait", ""))
        offset = re.search(r"(?m)^IO_BUZZER_ONCE 2000 50\r?$", before).end()
        return before, before + "unrelated guest log" + newline, offset

    def test_natural_zero_requires_the_same_once_anchor_across_both_serial_reads(self):
        for newline in ("\n", "\r\n"):
            before, after, offset = self.sample(newline)
            for frequency in (1960, 2000.0, 2040):
                with self.subTest(newline=repr(newline), frequency=frequency):
                    self.assertIs(runner.buzzer_timer_window(
                        {"frequency-hz": frequency, "duty-pct": 0.0}, before, after, offset), True)

    def test_timer_done_off_next_stage_or_next_cycle_cannot_supply_natural_zero(self):
        before, after, offset = self.sample()
        for event in ("IO_BUZZER_TIMER_DONE", "IO_BUZZER_OFF", "IO_BUZZER 0 1200 0",
                      "IO_BUZZER_ONCE 2000 50"):
            for position in ("before", "after"):
                with self.subTest(event=event, position=position):
                    left = before + event + "\n" if position == "before" else before
                    right = left if position == "before" else after + event + "\n"
                    self.assertIs(runner.buzzer_timer_window(
                        {"frequency-hz": 2000, "duty-pct": 0}, left, right, offset), False)

    def test_serial_reset_missing_anchor_and_invalid_offset_are_rejected(self):
        before, after, offset = self.sample()
        for invalid in (True, None, -1, len(before) + 1, offset + 1):
            with self.subTest(offset=invalid):
                self.assertIs(runner.buzzer_timer_window(
                    {"frequency-hz": 2000, "duty-pct": 0}, before, after, invalid), False)
        for left, right, position in ((before, "IO_BUZZER_ONCE 2000 50\nreset\n", offset),
                                       (before, before[:-1], offset),
                                       ("no once anchor\n", "no once anchor\n", 0),
                                       ("IO_BUZZER_ONCE 2000 50suffix\n", "IO_BUZZER_ONCE 2000 50suffix\n", 0)):
            with self.subTest(before=left, after=right):
                self.assertIs(runner.buzzer_timer_window(
                    {"frequency-hz": 2000, "duty-pct": 0}, left, right, position), False)

    def test_false_string_nonzero_nonfinite_or_wrong_frequency_is_rejected(self):
        before, after, offset = self.sample()
        for frequency, duty in ((2000, False), (2000, True), (2000, "0"), (2000, None),
                                (2000, 25), (2000, float("nan")), (2000, float("inf")),
                                (True, 0), (None, 0), ("2000", 0), (float("nan"), 0),
                                (float("inf"), 0), (1959.9, 0), (2040.1, 0)):
            with self.subTest(frequency=frequency, duty=duty):
                self.assertIs(runner.buzzer_timer_window(
                    {"frequency-hz": frequency, "duty-pct": duty}, before, after, offset), False)

    def test_observer_brackets_qom_with_serial_and_records_exact_hashes(self):
        before, after, offset = self.sample()
        order = []
        serial_reads = iter((before, after))

        class Client:
            def json(self, path):
                order.append("serial")
                return {"data": next(serial_reads)}

        observed = runner.Observations(Client(), "offline-sid", {})
        observed.serial = before
        properties = {"frequency-hz": 2000, "duty-pct": 0}

        def qom():
            order.append("qom")
            return properties

        with patch.object(observed, "properties", side_effect=qom):
            observed.buzzer_timer_zero(timeout=1)
        self.assertEqual(order, ["serial", "qom", "serial"])
        proof = observed.result["buzzer_timer_zero_observation"]
        self.assertEqual(proof["serial_offset"], offset)
        self.assertEqual(proof["before_serial_sha256"], hashlib.sha256(before.encode()).hexdigest())
        self.assertEqual(proof["after_serial_sha256"], hashlib.sha256(after.encode()).hexdigest())
        self.assertIs(proof["before_timer_done_and_manual_output"], True)

    def test_observer_rejects_timer_done_before_or_during_zero_qom_read(self):
        before, after, _ = self.sample()
        for position in ("before", "after"):
            with self.subTest(position=position):
                serials = [before, after + "IO_BUZZER_TIMER_DONE\n"]
                if position == "before":
                    serials[0] += "IO_BUZZER_TIMER_DONE\n"
                client = SimpleNamespace(json=lambda path: {"data": serials.pop(0)})
                observed = runner.Observations(client, "offline-sid", {})
                observed.serial = before
                with patch.object(observed, "properties", return_value={"frequency-hz": 2000, "duty-pct": 0}) as qom:
                    with self.assertRaisesRegex(RuntimeError, "before TIMER_DONE/manual output"):
                        observed.buzzer_timer_zero(timeout=1)
                self.assertEqual(qom.call_count, 0 if position == "before" else 1)
                self.assertNotIn("buzzer_timer_zero_observation", observed.result)


class AdapterRoutingTests(unittest.TestCase):
    def test_annotation_preflight_default_and_explicit_flag_never_contact_service(self):
        for options, expected in ((["--case", "buzzer"], False),
                                  (["--case", "buzzer", "--buzzer-callback-arity-patch"], True)):
            with self.subTest(options=options):
                with patch.object(sys, "argv", ["run_annotation_cases.py", *options]), \
                     redirect_stdout(io.StringIO()) as output, patch.object(annotation, "Client") as client, \
                     patch.object(annotation, "AnnotationClient") as owner, \
                     patch.object(annotation, "AnnotationTransport") as bridge, \
                     patch.object(annotation.subprocess, "Popen") as process:
                    self.assertEqual(annotation.main(), 0)
                result = json.loads(output.getvalue())
                self.assertIs(result["buzzer_callback_arity_patch"], expected)
                self.assertIs(result["api_contacted"], False)
                self.assertEqual(result["sessions_started"], 0)
                for unused in (client, owner, bridge, process):
                    unused.assert_not_called()

    def test_annotation_flag_with_default_all_or_non_buzzer_selection_rejects_before_api(self):
        with tempfile.TemporaryDirectory(prefix="m5-buzzer-cli-") as temporary:
            target = Path(temporary) / "must-not-exist"
            for selection in ([], ["--case", "all"], ["--case", "light"],
                              ["--case", "buzzer", "--case", "light"]):
                with self.subTest(selection=selection):
                    options = ["run_annotation_cases.py", "--buzzer-callback-arity-patch", "--execute",
                               "--out-dir", str(target), "--expected-runtime-sha256", "a" * 64, *selection]
                    with patch.object(sys, "argv", options), redirect_stderr(io.StringIO()), \
                         patch.object(annotation, "Client") as client, \
                         patch.object(annotation, "AnnotationClient") as owner, \
                         patch.object(annotation, "AnnotationTransport") as bridge, \
                         patch.object(annotation.subprocess, "Popen") as process:
                        with self.assertRaises(SystemExit) as stopped:
                            annotation.main()
                    self.assertEqual(stopped.exception.code, 2)
                    self.assertFalse(target.exists())
                    for unused in (client, owner, bridge, process):
                        unused.assert_not_called()

    def test_controller_forwards_opt_in_and_defaults_to_original_driver(self):
        for flag in (False, True):
            with self.subTest(flag=flag), patch.object(runner, "run_case", return_value="offline") as run:
                self.assertEqual(annotation.run_controller(object(), Path("/unused"), "cores3", "buzzer",
                                                           buzzer_callback_arity_patch=flag), "offline")
                self.assertIs(run.call_args.args[1].buzzer_callback_arity_patch, flag)

    def test_real_prepare_keeps_unpatched_image_and_labels_custom_image_separately(self):
        try:
            import littlefs  # noqa: F401
        except ImportError:
            self.skipTest("LittleFS matching this Python interpreter is required for real offline image preparation")
        base = runner.ROOT / "platform/.cache/firmware/cores3/uiflow2.bin"
        if not base.exists() or runner.digest(base) != REFERENCE_BASE_SHA:
            self.skipTest("Historical CoreS3 reference base is not locally available")
        original = (runner.PROBE / "io_drivers/buzzer.py").read_bytes()
        images = []
        with tempfile.TemporaryDirectory(prefix="m5-buzzer-prepare-") as temporary:
            for mode in ("legacy-no-attribute", "explicit-false", "explicit-true"):
                options = SimpleNamespace(out_dir=Path(temporary) / mode, device="cores3", base=None,
                                          ir_callback_root_patch=False)
                if mode != "legacy-no-attribute":
                    options.buzzer_callback_arity_patch = mode == "explicit-true"
                with redirect_stdout(io.StringIO()), patch.object(runner, "Client") as client:
                    _, image, result = runner.prepare(options, "buzzer")
                    client.assert_not_called()
                images.append(image.read_bytes())
                self.assertIs(result["checks"]["packaged_guest_bytes_verified"], True)
                if mode == "explicit-true":
                    self.assertEqual(result["firmware_flavor"], "custom-guest-buzzer-callback-arity-patch")
                    self.assertIn("buzzer_callback_patch", result)
                    self.assertNotEqual(result["firmware_sha256"], REFERENCE_IMAGE_SHA)
                else:
                    self.assertEqual(result["firmware_flavor"], "reference-app-with-original-unit-drivers")
                    self.assertNotIn("buzzer_callback_patch", result)
                    self.assertEqual(result["firmware_sha256"], REFERENCE_IMAGE_SHA)
                    self.assertEqual(result["probe_sha256"]["io_drivers/buzzer.py"], OFFICIAL_BUZZER_SHA)
                self.assertEqual((runner.PROBE / "io_drivers/buzzer.py").read_bytes(), original)
        self.assertEqual(images[0], images[1])
        self.assertNotEqual(images[1], images[2])


if __name__ == "__main__":
    unittest.main()
