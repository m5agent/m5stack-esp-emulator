"""Host-only validation before held-input admission or controller side effects."""
from __future__ import annotations

import copy
import math
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

import device_service
from device_service import DeviceSession, QEMU_INPUT_QCODES, ServiceError
from unit_runtime import UnitRegistry


class DeviceInputValidationTests(unittest.TestCase):
    def setUp(self):
        self.session = object.__new__(DeviceSession)
        self.session.id, self.session.state = "host-only", "running"
        self.session.spec = SimpleNamespace(id="cores3", expected_size=(320, 240))
        self.session._stop_event = threading.Event()
        self.session._lock = threading.RLock()
        self.session._qmp = mock.Mock()
        self.session._qmp_call = mock.Mock(return_value={"return": None})
        self.session._record_event = mock.Mock()
        self.session.unit_state = mock.Mock(return_value={"HOST_ONLY_NOT_GUEST": "readback-requested"})
        self.registry = UnitRegistry()
        self.attach("button")

    def attach(self, unit_id):
        self.session.units = self.registry.attachments("cores3", "qemu", [
            {"id": "fixture-unit", "unit_id": unit_id, "port_id": "port-a"},
        ])
        self.session.unit_contract = self.registry.freeze([unit_id])

    def reject(self, function, command, code="invalid_input"):
        with self.assertRaises(ServiceError) as caught:
            function(command)
        self.assertEqual(caught.exception.code, code)
        self.session._qmp_call.assert_not_called()
        self.session._qmp.cmd.assert_not_called()
        self.session._record_event.assert_not_called()
        return caught.exception

    def test_validation_is_pure_and_returns_detached_normalized_command(self):
        command = {"kind": "key", "key": "a", "action": "DoWn"}
        before = copy.deepcopy(command)
        with mock.patch.object(device_service.time, "sleep", side_effect=AssertionError("validation must not sleep")):
            actual = self.session.validate_input(command)
        self.assertEqual(actual, {"kind": "key", "key": "a", "action": "down", "settle_seconds": 0.02})
        self.assertEqual(command, before)
        self.assertIsNot(actual, command)
        self.session._qmp_call.assert_not_called()
        self.session._qmp.cmd.assert_not_called()
        self.session._record_event.assert_not_called()

    def test_qcodes_cover_key_groups_and_unknown_qcodes_fail_before_qmp(self):
        for key in ("a", "0", "ret", "shift_r", "kp_9", "lang1", "f24", "ac_refresh"):
            self.assertIn(key, QEMU_INPUT_QCODES)
            self.assertEqual(self.session.validate_input({"kind": "key", "key": key})["key"], key)
        for key in ("", "not-a-qemu-key", "a:b", "A", None, [], True):
            with self.subTest(key=key):
                self.reject(self.session.inject, {"kind": "key", "key": key, "action": "down"})

    def test_missing_key_and_bad_action_are_rejected_before_side_effects(self):
        self.reject(self.session.inject, {"kind": "key", "action": "down"})
        for action in ("hold", "", None, 1, []):
            with self.subTest(action=action):
                self.reject(self.session.inject, {"kind": "key", "key": "a", "action": action})

    def test_numeric_legacy_inputs_normalize_before_transport(self):
        self.assertEqual(self.session.validate_input({"kind": "key", "key": 7})["key"], "7")
        normalized = self.session.validate_input({"kind": "longpress", "x": "12", "y": 13.9,
                                                  "hold_seconds": "0.25", "settle_seconds": "0"})
        self.assertEqual(normalized, {"kind": "longpress", "action": "tap", "x": 12, "y": 13,
                                      "hold_seconds": 0.25, "settle_seconds": 0.0})

    def test_nonfinite_negative_and_host_overflow_durations_fail_before_press(self):
        for field in ("hold_seconds", "settle_seconds"):
            for value in (-1, math.nan, math.inf, -math.inf, True, None, "nan", "bogus", 10**1000, threading.TIMEOUT_MAX):
                with self.subTest(field=field, value=str(value)[:50]):
                    self.reject(self.session.inject, {"kind": "longpress", "x": 1, "y": 1, field: value})

    def test_all_coordinates_validate_before_any_drag_press(self):
        for field, value in (("x1", -1), ("y1", 240), ("x2", 320), ("y2", math.inf),
                             ("x2", "invalid"), ("y2", True), ("y2", 10**1000)):
            with self.subTest(field=field, value=str(value)[:50]):
                self.reject(self.session.inject, {"kind": "drag", "x1": 0, "y1": 0, "x2": 10, "y2": 10, field: value})

    def test_valid_inject_reuses_normalized_action_for_real_qmp_helper(self):
        self.session._proc = mock.Mock()
        self.session._proc.poll.return_value = None
        self.session._qmp_call.side_effect = DeviceSession._qmp_call.__get__(self.session)
        with mock.patch.object(device_service.time, "sleep", return_value=None):
            result = self.session.inject({"kind": "key", "key": "a", "action": "DOWN"})
        self.assertEqual(result["input"], "keydown:a")
        self.assertEqual(result["action"], "down")
        events = [{"type": "key", "data": {
            "down": True, "key": {"type": "qcode", "data": "a"},
        }}]
        self.session._qmp_call.assert_called_once_with("input-send-event", events=events)
        self.session._qmp.cmd.assert_called_once_with("input-send-event", events=events)

    def test_nanoc6_gpio_button_keeps_legacy_non_qcode_alias(self):
        self.session.spec.id = "nanoc6"
        result = self.session.inject({"kind": "key", "key": "boot-button", "action": "DOWN"})
        self.assertTrue(result["accepted"])
        self.session._qmp.cmd.assert_not_called()
        self.session._qmp_call.assert_called_once_with("qom-set", path="/machine", property="button-gpio9", value=True)

    def test_key_tap_uses_actual_qmp_helper_with_guest_milliseconds(self):
        self.session._proc = mock.Mock()
        self.session._proc.poll.return_value = None
        self.session._qmp_call.side_effect = DeviceSession._qmp_call.__get__(self.session)
        for hold, milliseconds in ((None, 450), (0.001, 1), ("0.1001", 101), (5, 5000)):
            with self.subTest(hold=hold):
                self.session._qmp.reset_mock()
                self.session._qmp_call.reset_mock()
                payload = {"kind": "key", "key": "a", "settle_seconds": 0}
                if hold is not None:
                    payload["hold_seconds"] = hold
                with mock.patch.object(device_service.time, "sleep") as sleep:
                    result = self.session.inject(payload)
                self.session._qmp.cmd.assert_called_once_with(
                    "send-key", keys=[{"type": "qcode", "data": "a"}],
                    **{"hold-time": milliseconds})
                sleep.assert_called_once_with(0)
                self.assertEqual(result["timing"], {
                    "clock": "virtual", "hold_seconds": 0.45 if hold is None else float(hold),
                    "hold_time_ms": milliseconds, "completion": "queued"})
                self.assertEqual(self.session._record_event.call_args.kwargs["timing"], result["timing"])

    def test_multiple_taps_submit_in_order_without_host_duration_waits(self):
        with mock.patch.object(device_service.time, "sleep") as sleep:
            for key, duration in (("a", 0.1), ("b", 2)):
                self.session.inject({"kind": "key", "key": key, "hold_seconds": duration, "settle_seconds": 0})
        self.assertEqual(self.session._qmp_call.call_args_list, [
            mock.call("send-key", keys=[{"type": "qcode", "data": "a"}], **{"hold-time": 100}),
            mock.call("send-key", keys=[{"type": "qcode", "data": "b"}], **{"hold-time": 2000}),
        ])
        self.assertEqual(sleep.call_args_list, [mock.call(0), mock.call(0)])

    def test_invalid_key_tap_duration_and_duration_on_explicit_edges_fail_closed(self):
        for value in (0, 0.0009, 5.001, -1, math.nan, math.inf, True, None, "bogus", 10**1000):
            with self.subTest(value=str(value)[:50]):
                self.reject(self.session.inject, {"kind": "key", "key": "a", "hold_seconds": value})
        for action in ("down", "up"):
            self.reject(self.session.inject, {"kind": "key", "key": "a", "action": action, "hold_seconds": 0.1})

    def test_managed_preview_default_tap_retains_synchronous_input(self):
        self.session.management_binding = {"owner": "host-fixture"}
        with mock.patch.object(device_service.time, "sleep") as sleep:
            result = self.session.inject({"kind": "key", "key": "a", "settle_seconds": 0})
        self.assertEqual(self.session._qmp_call.call_args_list, [
            mock.call("input-send-event", events=[{"type": "key", "data": {
                "down": down, "key": {"type": "qcode", "data": "a"}}}])
            for down in (True, False)])
        self.assertEqual(sleep.call_args_list, [mock.call(0.45), mock.call(0.45), mock.call(0)])
        self.assertEqual(result["timing"], {"clock": "host", "hold_seconds": 0.45, "completion": "events_sent"})
        self.session._qmp_call.reset_mock()
        self.session._record_event.reset_mock()
        self.reject(self.session.inject, {"kind": "key", "key": "a", "hold_seconds": 0.1}, "unsupported_input")

    def test_nanoc6_default_tap_keeps_gpio_and_rejects_virtual_hold(self):
        self.session.spec.id = "nanoc6"
        with mock.patch.object(device_service.time, "sleep") as sleep:
            result = self.session.inject({"kind": "key", "key": "boot-button", "settle_seconds": 0.2})
        self.assertEqual(self.session._qmp_call.call_args_list, [
            mock.call("qom-set", path="/machine", property="button-gpio9", value=value) for value in (True, False)])
        sleep.assert_called_once_with(0.2)
        self.assertEqual(result["timing"], {"clock": "host", "hold_seconds": 0.2, "completion": "events_sent"})
        self.session._qmp_call.reset_mock()
        self.session._record_event.reset_mock()
        self.reject(self.session.inject, {"kind": "key", "key": "boot-button", "hold_seconds": 0.1}, "unsupported_input")

    def test_timed_tap_obeys_acl_and_running_session_checks(self):
        with mock.patch.object(DeviceSession, "_require_runtime_permission", side_effect=ServiceError("runtime_acl_denied", "input.write denied", 403)):
            error = self.reject(self.session.inject, {"kind": "key", "key": "a"}, "runtime_acl_denied")
        self.assertEqual(error.status, 403)
        self.session.state = "starting"
        self.reject(self.session.inject, {"kind": "key", "key": "a"}, "session_not_running")
        self.session.state = "stopped"
        self.reject(self.session.inject, {"kind": "key", "key": "a"}, "session_stopping")

    def test_failed_qmp_tap_does_not_record_acceptance(self):
        self.session._qmp_call.side_effect = ServiceError("qmp_unconfirmed", "connection lost", 502)
        with self.assertRaises(ServiceError):
            self.session.inject({"kind": "key", "key": "a"})
        self.session._record_event.assert_not_called()

    def test_unit_validation_is_pure_and_reuses_frozen_schema(self):
        command = {"id": "fixture-unit", "values": {"pressed": True}}
        before = copy.deepcopy(command)
        actual = self.session.validate_unit_input(command)
        self.assertEqual(actual, before)
        self.assertIsNot(actual["values"], command["values"])
        self.assertEqual(command, before)
        self.session._qmp_call.assert_not_called()
        self.session.unit_state.assert_not_called()

    def test_unknown_unit_or_field_and_wrong_boolean_type_fail_before_qmp(self):
        self.reject(self.session.unit_input, {"id": "missing", "values": {"pressed": True}}, "unknown_unit_instance")
        for values in ({"pressed": 1}, {"pressed": True, "unknown": 1}, {"pressed": [True]}, None):
            with self.subTest(values=values):
                self.reject(self.session.unit_input, {"id": "fixture-unit", "values": values}, "invalid_unit_input")

    def test_unit_range_failure_checks_complete_payload_before_qmp(self):
        self.attach("scroll")
        self.reject(self.session.unit_input, {"id": "fixture-unit", "values": {"pressed": True, "source-count": 32768}}, "invalid_unit_input")

    def test_invalid_contract_descriptor_fails_before_any_write(self):
        self.session.unit_contract["profiles"]["button"]["inputs"]["pressed"] = {}
        self.reject(self.session.unit_input, {"id": "fixture-unit", "values": {"pressed": True}}, "unit_contract_unavailable")

    def test_valid_unit_input_applies_then_requests_live_readback(self):
        result = self.session.unit_input({"id": "fixture-unit", "values": {"pressed": True}})
        self.assertEqual(result, {"HOST_ONLY_NOT_GUEST": "readback-requested"})
        self.session._qmp_call.assert_called_once_with("qom-set", path="/machine/units/fixture-unit", property="pressed", value=True)
        self.session.unit_state.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
