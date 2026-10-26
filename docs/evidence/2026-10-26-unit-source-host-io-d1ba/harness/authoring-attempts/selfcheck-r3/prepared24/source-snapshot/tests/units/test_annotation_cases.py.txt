"""Offline failure controls for same-guest readout evidence; no live sessions."""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_annotation_cases as runner
from annotation_contract import buzzer_observation


class GuestMarkerTests(unittest.TestCase):
    SENSOR_VECTORS = (
        ("color", {"clear-raw": 42000, "red-raw": 9000, "green-raw": 6000, "blue-raw": 3000},
         "SENSOR_COLOR 9000 6000 3000 42000\n"),
        ("tof", {"distance-mm": 321}, "SENSOR_TOF 321.0000 32.1000\n"),
        ("ncir", {"ambient-c": 17.3, "object-c": 37.1}, "SENSOR_NCIR 17.2900 37.0900\n"),
        ("heart", {"ir-sample": 41000, "red-sample": 36000}, "SENSOR_HEART 41000 36000\n"),
        ("tvoc", {"eco2-ppm": 1250, "tvoc-ppb": 230, "raw-h2": 26000, "raw-ethanol": 31000},
         "SENSOR_TVOC 1250 230 26000 31000\n"),
        ("ultrasonic-i2c", {"distance-mm": 1234.5}, "SENSOR_ULTRASONIC 1234.50 123.45\n"),
    )

    def test_six_sensor_markers_preserve_original_field_order_units_and_tolerances(self):
        for case, values, serial in self.SENSOR_VECTORS:
            with self.subTest(case=case):
                self.assertTrue(runner.guest_marker_matches(case, values, serial))
                self.assertTrue(runner.guest_marker_matches(case, dict(reversed(list(values.items()))), serial))

    def test_wrong_sensor_field_value_or_distance_unit_is_rejected(self):
        for case, values, serial in self.SENSOR_VECTORS:
            with self.subTest(case=case):
                changed = deepcopy(values)
                key = next(iter(changed))
                changed[key] += 100
                self.assertFalse(runner.guest_marker_matches(case, changed, serial))
        self.assertFalse(runner.guest_marker_matches("tof", {"distance-mm": 321}, "SENSOR_TOF 321 321\n"))
        self.assertFalse(runner.guest_marker_matches("ultrasonic-i2c", {"distance-mm": 1234.5},
                                                    "SENSOR_ULTRASONIC 1234.50 1234.50\n"))

    def test_stale_marker_does_not_match_the_fresh_serial_window(self):
        for case, values, serial in self.SENSOR_VECTORS:
            with self.subTest(case=case):
                offset = len(serial)
                captured = serial + "unrelated fresh guest output\n"
                self.assertTrue(runner.guest_marker_matches(case, values, captured))
                self.assertFalse(runner.guest_marker_matches(case, values, captured[offset:]))

    def test_nonfinite_malformed_or_wrong_sensor_marker_is_rejected(self):
        for serial in ("SENSOR_TOF nan 32.1\n", "SENSOR_TOF inf 32.1\n", "SENSOR_TOF 321 32.1 extra\n",
                       "SENSOR_TOF 321\n", "SENSOR_ULTRASONIC 321 32.1\n"):
            with self.subTest(serial=serial):
                self.assertFalse(runner.guest_marker_matches("tof", {"distance-mm": 321}, serial))

    def test_env_field_names_determine_order_and_whole_marker_is_required(self):
        values = {"pressure-pa": 98765.0, "humidity-pct": 67.0, "temperature-c": 31.5}
        self.assertTrue(runner.guest_marker_matches("env-iii", values, "UNIT_ENV 31.5 67.0 98765\r\n"))
        for serial in ("UNIT_ENV 31.5 67.0 98765suffix\n", "UNIT_ENV 31.5 67.0 98765 1\n",
                       "UNIT_ENV -- 67.0 98765\n", "UNIT_ENV 1..2 67.0 98765\n",
                       "UNIT_ENV 31.5 67.0 nan\n", "UNIT_ENV 98765 67.0 31.5\n"):
            with self.subTest(serial=serial):
                self.assertFalse(runner.guest_marker_matches("env-iii", values, serial))

    def test_pir_requires_boolean_input_and_complete_gpio_marker(self):
        self.assertTrue(runner.guest_marker_matches("pir", {"motion": True}, "IO_PIR 1 1 0 0\n"))
        self.assertTrue(runner.guest_marker_matches("pir", {"motion": False}, "IO_PIR 0 2 2 2\n"))
        for values, serial in (({"motion": True}, "IO_PIR 0 1 0 0\n"),
                               ({"motion": 1}, "IO_PIR 1 1 0 0\n"),
                               ({"motion": "true"}, "IO_PIR 1 1 0 0\n"),
                               ({"motion": True}, "IO_PIR 1\n"),
                               ({"motion": True}, "IO_PIR 1 1 0 0 extra\n")):
            with self.subTest(values=values, serial=serial):
                self.assertFalse(runner.guest_marker_matches("pir", values, serial))

    def test_light_uses_adc_oracle_and_independent_digital_field(self):
        for voltage, digital, raw in ((310, False, 6561), (1550, True, 32776), (3100, False, 65535)):
            with self.subTest(voltage=voltage):
                values = {"analog-mv": voltage, "digital-level": digital}
                self.assertTrue(runner.guest_marker_matches("light", values, f"IO_LIGHT {raw} {int(digital)}\n"))
                self.assertFalse(runner.guest_marker_matches("light", values, f"IO_LIGHT {voltage} {int(digital)}\n"))
                self.assertFalse(runner.guest_marker_matches("light", values, f"IO_LIGHT {raw} {int(not digital)}\n"))
        self.assertFalse(runner.guest_marker_matches("light", {"analog-mv": 1550, "digital-level": 1},
                                                    "IO_LIGHT 32776 1\n"))


class AnnotationCoverageTests(unittest.TestCase):
    def good(self, case):
        snapshots = []
        for phase in runner.required_phases(case):
            state = case == "buzzer" and phase != "buzzer-off"
            snapshot = {"phase": phase, "exact_http_controller_dom_alignment": True,
                        "evidence_mode": "state" if state else "full"}
            if not state:
                snapshot.update(readout_gesture={"unit_post_delta": 0, "all_mutation_delta": 0},
                                readout_screenshot=phase + "-readout.png", screenshot=phase + ".png")
            snapshots.append(snapshot)
        session_id = "offline-annotation-sid"
        web = {"session_id": session_id, "annotation_snapshots": snapshots,
               "annotation_terminal": {"live_annotation_fields": 0},
               "posts": [{"at": f"2026-10-26T00:00:{index:02d}.000Z", "method": "POST",
                          "path": f"/api/v1/sessions/{session_id}/unit-input", "status": 200,
                          "request": {"values": {field: value}}}
                         for index, (field, value) in enumerate(runner.expected_posts(case), 1)]}
        if case == "light":
            # Offline fixture of the actual bridge event shape. The first
            # checkbox false is a product no-op, proved by a prior live GET.
            web["readbacks"] = [{"at": "2026-10-26T00:00:00.000Z", "method": "GET",
                                 "path": f"/api/v1/sessions/{session_id}/units", "status": 200,
                                 "response": {"session_id": session_id, "state": "running", "source": "live", "units": [
                                     {"id": "external1", "unit_id": "light", "source": "guest-qom",
                                      "available": True, "properties": {"digital-level": False}}]}}]
        vectors = [{"phase": phase, "guest_observed": True, "serial_offset": index * 100,
                    "fresh_serial_sha256": hashlib.sha256(phase.encode()).hexdigest()}
                   for index, phase in enumerate(runner.required_phases(case))]
        return web, vectors

    def assert_rejected(self, case, web, vectors, check):
        checks = runner.annotation_checks(case, web, vectors)
        self.assertIs(checks[check], False, checks)

    def test_all_twelve_have_complete_positive_coverage(self):
        self.assertEqual(set(runner.CASES), {"env-iii", "relay", "color", "tof", "ncir", "heart", "tvoc",
                                            "ultrasonic-i2c", "pir", "light", "thermal", "buzzer"})
        for case in runner.CASES:
            with self.subTest(case=case):
                self.assertTrue(all(runner.annotation_checks(case, *self.good(case)).values()))

    def test_empty_missing_duplicate_and_unknown_phase_cannot_pass(self):
        for mutation in ("empty", "missing", "duplicate", "unknown"):
            with self.subTest(mutation=mutation):
                web, vectors = self.good("color")
                if mutation == "empty":
                    web["annotation_snapshots"] = []
                elif mutation == "missing":
                    web["annotation_snapshots"].pop()
                elif mutation == "duplicate":
                    web["annotation_snapshots"][1]["phase"] = web["annotation_snapshots"][0]["phase"]
                else:
                    web["annotation_snapshots"][1]["phase"] = "old-unrelated-phase"
                self.assert_rejected("color", web, vectors, "annotation_phase_coverage")

    def test_alignment_must_be_literal_true(self):
        for value in (False, None, 1, "true"):
            with self.subTest(value=value):
                web, vectors = self.good("ncir")
                web["annotation_snapshots"][0]["exact_http_controller_dom_alignment"] = value
                self.assert_rejected("ncir", web, vectors, "annotation_exact_alignment")

    def test_full_phases_require_both_screenshots_and_no_gesture_mutations(self):
        for field, replacement in (("screenshot", ""), ("readout_screenshot", ""),
                                   ("unit_post_delta", 1), ("all_mutation_delta", 1)):
            with self.subTest(field=field):
                web, vectors = self.good("light")
                snapshot = web["annotation_snapshots"][0]
                if field.endswith("delta"):
                    snapshot["readout_gesture"][field] = replacement
                else:
                    snapshot[field] = replacement
                self.assert_rejected("light", web, vectors, "readout_gestures_and_screenshots")

    def test_buzzer_fast_phases_do_not_claim_screenshots_and_off_requires_full(self):
        web, vectors = self.good("buzzer")
        self.assertTrue(all(runner.annotation_checks("buzzer", web, vectors).values()))
        for index, mode in ((0, "full"), (5, "state")):
            with self.subTest(index=index, mode=mode):
                changed = deepcopy(web)
                changed["annotation_snapshots"][index]["evidence_mode"] = mode
                self.assert_rejected("buzzer", changed, vectors, "phase_evidence_modes")

    def test_buzzer_phase_order_cannot_reuse_an_old_zero_before_once(self):
        web, vectors = self.good("buzzer")
        web["annotation_snapshots"][1], web["annotation_snapshots"][4] = \
            web["annotation_snapshots"][4], web["annotation_snapshots"][1]
        self.assert_rejected("buzzer", web, vectors, "annotation_phase_coverage")

    def test_missing_extra_or_altered_original_input_post_is_rejected(self):
        for mutation in ("missing", "extra", "altered", "integer-for-boolean"):
            with self.subTest(mutation=mutation):
                web, vectors = self.good("pir")
                if mutation == "missing":
                    web["posts"].pop()
                elif mutation == "extra":
                    web["posts"].append(deepcopy(web["posts"][-1]))
                elif mutation == "altered":
                    web["posts"][0]["request"]["values"]["motion"] = False
                else:
                    web["posts"][0]["request"]["values"]["motion"] = 1
                self.assert_rejected("pir", web, vectors, "exact_original_product_input_posts")

    def test_output_only_units_cannot_gain_annotation_input_posts(self):
        for case in ("relay", "buzzer"):
            with self.subTest(case=case):
                web, vectors = self.good(case)
                web["posts"] = [{"request": {"values": {"duty-pct": 0}}}]
                self.assert_rejected(case, web, vectors, "exact_original_product_input_posts")

    def test_light_requires_exact_five_posts_with_no_initial_false_checkbox_post(self):
        expected = [("analog-mv", 310), ("analog-mv", 1550), ("digital-level", True),
                    ("analog-mv", 3100), ("digital-level", False)]
        self.assertEqual(runner.expected_posts("light"), expected)
        web, vectors = self.good("light")
        checks = runner.annotation_checks("light", web, vectors)
        self.assertIs(checks["exact_original_product_input_posts"], True)
        self.assertIs(checks["initial_false_digital_input_observed_before_first_post"], True)

    def test_light_missing_initial_false_or_wrong_boolean_cannot_supply_noop_proof(self):
        for mutation in ("missing-readbacks", "empty-readbacks", "missing-field", True, 0, 1, "false", None):
            with self.subTest(mutation=mutation):
                web, vectors = self.good("light")
                if mutation == "missing-readbacks":
                    web.pop("readbacks")
                elif mutation == "empty-readbacks":
                    web["readbacks"] = []
                elif mutation == "missing-field":
                    web["readbacks"][0]["response"]["units"][0]["properties"].pop("digital-level")
                else:
                    web["readbacks"][0]["response"]["units"][0]["properties"]["digital-level"] = mutation
                self.assert_rejected("light", web, vectors,
                                     "initial_false_digital_input_observed_before_first_post")

    def test_light_initial_false_get_needs_timestamp_strictly_before_first_post(self):
        for mutation in ("same-time", "late", "missing-get-time", "empty-get-time", "invalid-get-time",
                         "naive-get-time", "none-get-time", "missing-post-time", "invalid-post-time", "naive-post-time"):
            with self.subTest(mutation=mutation):
                web, vectors = self.good("light")
                event = web["readbacks"][0]
                if mutation == "same-time":
                    event["at"] = web["posts"][0]["at"]
                elif mutation == "late":
                    event["at"] = "2026-10-26T00:00:01.001Z"
                elif mutation == "missing-get-time":
                    event.pop("at")
                elif mutation == "empty-get-time":
                    event["at"] = ""
                elif mutation == "invalid-get-time":
                    event["at"] = "not-a-timestamp"
                elif mutation == "naive-get-time":
                    event["at"] = "2026-10-26T00:00:00.000"
                elif mutation == "none-get-time":
                    event["at"] = None
                elif mutation == "missing-post-time":
                    web["posts"][0].pop("at")
                elif mutation == "invalid-post-time":
                    web["posts"][0]["at"] = "not-a-timestamp"
                else:
                    web["posts"][0]["at"] = "2026-10-26T00:00:01.000"
                self.assert_rejected("light", web, vectors,
                                     "initial_false_digital_input_observed_before_first_post")

    def test_light_initial_false_timestamp_order_uses_aware_instants(self):
        web, vectors = self.good("light")
        web["readbacks"][0]["at"] = "2026-10-26T08:00:00.500+08:00"
        checks = runner.annotation_checks("light", web, vectors)
        self.assertIs(checks["initial_false_digital_input_observed_before_first_post"], True)
        web["readbacks"][0]["at"] = "2026-10-25T23:00:02.000-01:00"
        self.assert_rejected("light", web, vectors,
                             "initial_false_digital_input_observed_before_first_post")

    def test_light_initial_false_get_requires_success_live_source_and_light_guest_qom(self):
        for mutation in ("bad-status", "missing-status", "cached", "missing-live-source",
                         "host-fixture", "missing-guest-qom", "other-unit", "empty-units", "missing-units"):
            with self.subTest(mutation=mutation):
                web, vectors = self.good("light")
                event = web["readbacks"][0]
                response = event["response"]
                if mutation == "bad-status":
                    event["status"] = 500
                elif mutation == "missing-status":
                    event.pop("status")
                elif mutation == "cached":
                    response["source"] = "history"
                elif mutation == "missing-live-source":
                    response.pop("source")
                elif mutation == "host-fixture":
                    response["units"][0]["source"] = "session-frozen-fixture"
                elif mutation == "missing-guest-qom":
                    response["units"][0].pop("source")
                elif mutation == "other-unit":
                    response["units"][0]["unit_id"] = "pir"
                elif mutation == "empty-units":
                    response["units"] = []
                else:
                    response.pop("units")
                self.assert_rejected("light", web, vectors,
                                     "initial_false_digital_input_observed_before_first_post")

    def test_light_initial_false_proof_is_a_real_get_of_the_same_session_units(self):
        for mutation in ("post", "missing-method", "wrong-path", "missing-path", "foreign-session-path"):
            with self.subTest(mutation=mutation):
                web, vectors = self.good("light")
                event = web["readbacks"][0]
                if mutation == "post":
                    event["method"] = "POST"
                elif mutation == "missing-method":
                    event.pop("method")
                elif mutation == "wrong-path":
                    event["path"] = f"/api/v1/sessions/{web['session_id']}/unit-input"
                elif mutation == "missing-path":
                    event.pop("path")
                else:
                    event["path"] = "/api/v1/sessions/unrelated-session/units"
                self.assert_rejected("light", web, vectors,
                                     "initial_false_digital_input_observed_before_first_post")

    def test_light_late_valid_get_cannot_rescue_an_invalid_early_get(self):
        web, vectors = self.good("light")
        late = deepcopy(web["readbacks"][0])
        late["at"] = "2026-10-26T00:00:01.001Z"
        web["readbacks"][0]["response"]["units"][0]["properties"]["digital-level"] = 0
        web["readbacks"].append(late)
        self.assert_rejected("light", web, vectors,
                             "initial_false_digital_input_observed_before_first_post")

    def test_light_initial_false_get_is_running_same_session_and_available_external_instance(self):
        for mutation in ("foreign-response-session", "missing-response-session", "foreign-instance", "missing-instance",
                         "unavailable", "integer-available", "string-available", "missing-available",
                         "not-running", "missing-state", "missing-web-session"):
            with self.subTest(mutation=mutation):
                web, vectors = self.good("light")
                response = web["readbacks"][0]["response"]
                unit = response["units"][0]
                if mutation == "foreign-response-session":
                    response["session_id"] = "unrelated-session"
                elif mutation == "missing-response-session":
                    response.pop("session_id")
                elif mutation == "foreign-instance":
                    unit["id"] = "external2"
                elif mutation == "missing-instance":
                    unit.pop("id")
                elif mutation == "unavailable":
                    unit["available"] = False
                elif mutation == "integer-available":
                    unit["available"] = 1
                elif mutation == "string-available":
                    unit["available"] = "true"
                elif mutation == "missing-available":
                    unit.pop("available")
                elif mutation == "not-running":
                    response["state"] = "stopped"
                elif mutation == "missing-state":
                    response.pop("state")
                else:
                    web.pop("session_id")
                self.assert_rejected("light", web, vectors,
                                     "initial_false_digital_input_observed_before_first_post")

    def test_light_extra_noop_post_and_integer_checkbox_posts_are_rejected(self):
        for mutation in ("extra-initial-false", "integer-true", "integer-false"):
            with self.subTest(mutation=mutation):
                web, vectors = self.good("light")
                if mutation == "extra-initial-false":
                    post = deepcopy(web["posts"][0])
                    post["request"]["values"] = {"digital-level": False}
                    web["posts"].insert(0, post)
                else:
                    index, value = (2, 1) if mutation == "integer-true" else (4, 0)
                    web["posts"][index]["request"]["values"]["digital-level"] = value
                self.assert_rejected("light", web, vectors, "exact_original_product_input_posts")

    def test_fresh_guest_records_need_phase_membership_offset_and_hash(self):
        for mutation in ("missing", "duplicate-phase", "boolean-offset", "missing-hash"):
            with self.subTest(mutation=mutation):
                web, vectors = self.good("thermal")
                if mutation == "missing":
                    vectors.pop()
                elif mutation == "duplicate-phase":
                    vectors[1]["phase"] = vectors[0]["phase"]
                elif mutation == "boolean-offset":
                    vectors[1]["serial_offset"] = False
                else:
                    vectors[1]["fresh_serial_sha256"] = ""
                self.assert_rejected("thermal", web, vectors, "fresh_guest_observations")

    def test_terminal_requires_a_real_zero_field_count(self):
        for value in (None, False, "0", 1):
            with self.subTest(value=value):
                web, vectors = self.good("heart")
                web["annotation_terminal"]["live_annotation_fields"] = value
                self.assert_rejected("heart", web, vectors, "terminal_clears_live_values")


class AdapterFreshnessTests(unittest.TestCase):
    def client(self, case):
        with patch.dict(runner.os.environ, {"M5_UNIT_WEB_BRIDGE": "0"}), \
             patch.object(runner, "AnnotationTransport"):
            return runner.AnnotationClient("http://127.0.0.1:8787", case, runner.ROOT / ".work/offline-annotation-fixture")

    def test_input_adapter_waits_only_after_prepost_offset(self):
        client = self.client("light")
        old = "IO_LIGHT 32776 1\n"
        fresh = "IO_LIGHT 32776 1\nnew matching sample\n"
        values = {"analog-mv": 1550, "digital-level": True}
        observed = []

        def wait(_client, _sid, predicate, *, offset):
            self.assertEqual(offset, len(old))
            self.assertFalse(predicate(old[offset:]))
            self.assertTrue(predicate(fresh))
            return old + fresh

        with patch.object(client, "serial_now", return_value=old), \
             patch.object(runner.Client, "raw", return_value=b"{}"), \
             patch.object(runner.sensors, "wait_for", side_effect=wait), \
             patch.object(client, "annotation", side_effect=lambda *args: observed.append(args)):
            client.raw("sessions/offline-sid/unit-input", method="POST", payload={"id": "external1", "values": values})
        self.assertEqual(observed, [("offline-sid", "input-1", values)])
        self.assertEqual(client.guest_vectors[0]["fresh_serial_sha256"], hashlib.sha256(fresh.encode()).hexdigest())

    def test_old_buzzer_markers_cannot_fill_timer_and_off_during_stage_zero(self):
        client = self.client("buzzer")
        old = "IO_BUZZER_ONCE 2000 50\nIO_BUZZER_TIMER_DONE\nIO_BUZZER_OFF\nIO_BUZZER 0 1200 0\n"
        observed = []

        def annotate(_sid, phase, _expected):
            observed.append(phase)
            client.observed_phases.add(phase)

        with patch.object(client, "serial_now", return_value=old), patch.object(client, "annotation", side_effect=annotate):
            client.observe_buzzer("offline-sid", json.dumps({"units": [{"properties": {
                "frequency-hz": 1200.192030724916, "duty-pct": 0}}]}).encode())
        self.assertNotIn("buzzer-timer-zero", observed)
        self.assertNotIn("buzzer-off", observed)


class BuzzerObservationTests(unittest.TestCase):
    def test_actual_quantized_register_values_match_their_current_guest_phase(self):
        for phase, marker, frequency, duty in (
            ("buzzer-0", "IO_BUZZER 0 1200 0", 1200.192030724916, 0),
            ("buzzer-1", "IO_BUZZER 1 2400 25", 2399.2322456813818, 24.98779296875),
            ("buzzer-2", "IO_BUZZER 2 3600 75", 3602.3054755043227, 74.98779296875),
            ("buzzer-once", "IO_BUZZER_ONCE 2000 50", 2000.0, 50.0),
            ("buzzer-off", "IO_BUZZER_OFF", 2000.0, 0.0),
        ):
            with self.subTest(phase=phase):
                observation = buzzer_observation(phase, {"frequency-hz": frequency, "duty-pct": duty}, marker + "\n", 0)
                self.assertIsNotNone(observation)
                self.assertEqual(observation["marker"], marker)
                self.assertEqual(observation["marker_end"], len(marker))

    def test_old_phase_marker_before_offset_or_followed_by_new_phase_cannot_pass(self):
        marker = "IO_BUZZER 1 2400 25\n"
        properties = {"frequency-hz": 2399.2322456813818, "duty-pct": 24.98779296875}
        self.assertIsNone(buzzer_observation("buzzer-1", properties, marker, len(marker)))
        for newer in ("IO_BUZZER 2 3600 75\n", "IO_BUZZER_ONCE 2000 50\n", "IO_BUZZER_TIMER_DONE\n", "IO_BUZZER_OFF\n"):
            with self.subTest(newer=newer):
                self.assertIsNone(buzzer_observation("buzzer-1", properties, marker + newer, 0))

    def test_timer_zero_is_between_once_and_manual_events_at_the_once_frequency(self):
        marker = "IO_BUZZER_ONCE 2000 50"
        serial, offset = marker + "\n", len(marker)
        properties = {"frequency-hz": 2000.0, "duty-pct": 0.0}
        observation = buzzer_observation("buzzer-timer-zero", properties, serial, offset)
        self.assertIsNotNone(observation)
        self.assertIs(observation["before_timer_done_and_manual_output"], True)
        for suffix in ("IO_BUZZER_TIMER_DONE\n", "IO_BUZZER_OFF\n", "IO_BUZZER 0 1200 0\n"):
            with self.subTest(suffix=suffix):
                self.assertIsNone(buzzer_observation("buzzer-timer-zero", properties, serial + suffix, offset))
        self.assertIsNone(buzzer_observation("buzzer-timer-zero", properties, "unrelated\n", 0))
        self.assertIsNone(buzzer_observation("buzzer-timer-zero", properties, serial, offset + 1))
        self.assertIsNone(buzzer_observation("buzzer-timer-zero", {"frequency-hz": 1200, "duty-pct": 0}, serial, offset))
        self.assertIsNone(buzzer_observation("buzzer-timer-zero", {"frequency-hz": 2000, "duty-pct": 25}, serial, offset))

    def test_nonfinite_boolean_wrong_frequency_or_wrong_duty_is_rejected(self):
        for frequency, duty in ((float("nan"), 25), (2400, float("inf")), (True, 25), (2400, False),
                                (1200, 25), (2400, 75)):
            with self.subTest(frequency=frequency, duty=duty):
                self.assertIsNone(buzzer_observation("buzzer-1", {"frequency-hz": frequency, "duty-pct": duty},
                                                     "IO_BUZZER 1 2400 25\n", 0))


class EntryRoutingTests(unittest.TestCase):
    def test_default_all_and_repeated_case_preflight_never_construct_service_or_transport(self):
        for options, expected in (([], ["env-iii", "relay"]), (["--case", "all"], list(runner.CASES)),
                                  (["--case", "light", "--case", "light"], ["light"])):
            with self.subTest(options=options):
                with patch.object(sys, "argv", ["run_annotation_cases.py", *options]), redirect_stdout(io.StringIO()) as output, \
                     patch.object(runner, "Client") as client, patch.object(runner, "AnnotationClient") as annotation, \
                     patch.object(runner, "AnnotationTransport") as transport, patch.object(runner.subprocess, "Popen") as child:
                    self.assertEqual(runner.main(), 0)
                value = json.loads(output.getvalue())
                self.assertEqual(value["cases"], expected)
                self.assertIs(value["api_contacted"], False)
                self.assertEqual(value["sessions_started"], 0)
                client.assert_not_called()
                annotation.assert_not_called()
                transport.assert_not_called()
                child.assert_not_called()

    def test_execute_missing_or_bad_runtime_pin_rejects_before_service_and_output(self):
        with tempfile.TemporaryDirectory(prefix="m5-annotation-args-") as temporary:
            target = Path(temporary) / "not-created"
            for options in ([], ["--out-dir", str(target)],
                            ["--out-dir", str(target), "--expected-runtime-sha256", "bad"]):
                with self.subTest(options=options):
                    with patch.object(sys, "argv", ["run_annotation_cases.py", "--execute", *options]), \
                         redirect_stderr(io.StringIO()), patch.object(runner, "Client") as client, \
                         patch.object(runner, "AnnotationClient") as annotation, \
                         patch.object(runner, "AnnotationTransport") as transport:
                        with self.assertRaises(SystemExit) as stopped:
                            runner.main()
                    self.assertEqual(stopped.exception.code, 2)
                    self.assertFalse(target.exists())
                    client.assert_not_called()
                    annotation.assert_not_called()
                    transport.assert_not_called()

    def test_each_case_delegates_to_the_existing_guest_runner_with_original_mode(self):
        for case in runner.CASES:
            with self.subTest(case=case):
                with patch.object(runner.sensors, "run_case", return_value="sensor") as sensor, \
                     patch.object(runner.io_cases, "run_case", return_value="io") as io_runner, \
                     patch.object(runner, "run_case", return_value="service") as service:
                    result = runner.run_controller(object(), runner.ROOT / ".work/unused-offline-fixture", "cores3", case)
                expected = sensor if case in runner.SENSOR_CASES or case == "thermal" else \
                    io_runner if case in {"pir", "light", "buzzer"} else service
                expected.assert_called_once()
                self.assertEqual(result, expected.return_value)
                for other in (sensor, io_runner, service):
                    if other is not expected:
                        other.assert_not_called()
                options = expected.call_args.args[1]
                self.assertIs(options.prepare_only, False)
                self.assertIs(options.thermal_no_fixture, False)
                self.assertIs(options.ir_callback_root_patch, False)


if __name__ == "__main__":
    unittest.main()
