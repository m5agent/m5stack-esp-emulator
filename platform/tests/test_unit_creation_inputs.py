"""Creation fixtures must fail before live QMP writes, including frozen contracts."""
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from device_service import DeviceSession, ServiceError
from unit_runtime import UnitError, UnitRegistry


class UnitCreationInputTests(unittest.TestCase):
    def test_flashlight_fixture_only_accepts_creation_and_is_frozen(self):
        registry = UnitRegistry()
        self.assertEqual(registry.input_values("flashlight", {"flash-mode": False}), {"flash-mode": False})
        frozen = UnitRegistry(contract=registry.freeze(["flashlight"]))
        for current in (registry, frozen):
            for mode in (True, False):
                with self.subTest(frozen=current is frozen, mode=mode), self.assertRaises(UnitError) as caught:
                    current.input_values("flashlight", {"flash-mode": mode}, live=True)
                self.assertEqual((caught.exception.status, caught.exception.code), (409, "unit_input_creation_only"))
        self.assertEqual(frozen.profiles["flashlight"]["model_completeness"], "partial")
        self.assertEqual(frozen.profiles["flashlight"]["guest_validation"]["hardware"], "NOT RUN")

    def test_either_frozen_catalog_or_runtime_guard_prevents_live_write(self):
        for owner in ("catalog", "profile"):
            registry = UnitRegistry()
            registry.units["flashlight"]["inputs"]["flash-mode"]["creation_only"] = owner == "catalog"
            registry.profiles["flashlight"]["inputs"]["flash-mode"]["creation_only"] = owner == "profile"
            with self.subTest(owner=owner), self.assertRaises(UnitError):
                registry.input_values("flashlight", {"flash-mode": True}, live=True)

    def test_live_rejection_has_no_qmp_or_input_event_side_effect(self):
        registry = UnitRegistry()
        session = SimpleNamespace(
            state="running", units=[{"id": "lamp", "unit_id": "flashlight"}],
            _check_cancelled=mock.Mock(), _unit_registry=lambda: (registry, "frozen"),
            _qmp_call=mock.Mock(), _record_event=mock.Mock(), _lock=threading.RLock(),
        )
        session.validate_unit_input = lambda value: DeviceSession.validate_unit_input(session, value)
        for mode in (True, False):
            with self.subTest(mode=mode), self.assertRaises(ServiceError) as caught:
                DeviceSession.unit_input(session, {"id": "lamp", "values": {"flash-mode": mode}})
            self.assertEqual((caught.exception.status, caught.exception.code), (409, "unit_input_creation_only"))
        session._qmp_call.assert_not_called()
        session._record_event.assert_not_called()


if __name__ == "__main__":
    unittest.main()
