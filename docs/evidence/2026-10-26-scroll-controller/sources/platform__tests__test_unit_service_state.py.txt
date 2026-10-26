"""Service Unit schema/terminal-state contracts; these tests run no guest."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest

from device_service import DeviceSession, ServiceError
from unit_runtime import UnitRegistry


class UnitServiceStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        registry = UnitRegistry()
        self.session = object.__new__(DeviceSession)
        self.session.id = "unit-contract-fixture"
        self.session.state = "running"
        self.session.units = [{"id": "button1", "unit_id": "button", "port_id": "port-a"}]
        self.session.unit_contract = registry.freeze(["button"])
        self.session.unit_state_path = Path(self.tmp.name) / "units-state.json"
        self.session._lock = threading.RLock()
        self.session._stop_event = threading.Event()
        self.session._record_event = lambda *args, **kwargs: None
        self.writes = []
        self.commands = []
        self.pressed = False

        def qmp(command, **arguments):
            self.commands.append(command)
            self.assertEqual(arguments["path"], "/machine/units/button1")
            prop = arguments["property"]
            if command == "qom-set":
                self.writes.append(arguments)
                self.pressed = arguments["value"]
                return {"return": {}}
            self.assertEqual(command, "qom-get")
            return {"return": self.pressed if prop == "pressed" else not self.pressed if prop == "input-level" else 0}

        self.session._qmp_call = qmp

    def test_live_definitions_and_input_use_the_session_contract(self):
        result = self.session.unit_input({"id": "button1", "values": {"pressed": True}})
        self.assertIs(result["units"][0]["properties"]["pressed"], True)
        self.assertEqual(result["definitions"][0]["inputs"]["pressed"]["type"], "boolean")
        self.assertEqual(result["contract_hashes"], self.session.unit_contract["source_hashes"])

    def test_invalid_multi_field_input_performs_no_qom_writes(self):
        with self.assertRaises(ServiceError):
            self.session.unit_input({"id": "button1", "values": {"pressed": True, "input-level": False}})
        self.assertEqual(self.writes, [])

    def test_scroll_compound_inputs_are_rejected_before_either_field_changes(self):
        registry = UnitRegistry()
        # Initial machine construction can set both inputs; live updates have
        # no QMP transaction/rollback when source-count rejects a runtime step.
        self.assertEqual(registry.input_values("scroll", {"source-count": 0, "pressed": False}),
                         {"source-count": 0, "pressed": False})
        self.session.units = [{"id": "button1", "unit_id": "scroll", "port_id": "port-a"}]
        self.session.unit_contract = registry.freeze(["scroll"])
        for values in ({"pressed": True, "source-count": 1}, {"source-count": 1, "pressed": True}):
            with self.subTest(values=values), self.assertRaises(ServiceError) as caught:
                self.session.unit_input({"id": "button1", "values": values})
            self.assertEqual((caught.exception.code, caught.exception.status), ("invalid_unit_input", 400))
            self.assertEqual(self.commands, [])
            self.assertIs(self.pressed, False)

    def test_terminal_legacy_snapshot_receives_frozen_definitions(self):
        self.session.unit_state_path.write_text(json.dumps({"units": [{"id": "button1", "properties": {"pressed": False}}]}))
        self.session.state = "stopped"
        result = self.session.unit_state()
        self.assertEqual(result["source"], "persisted")
        self.assertEqual(result["definitions"][0]["id"], "button")
        self.assertEqual(result["definitions"][0]["runtime"]["state"]["pressed"]["property"], "pressed")
        self.assertIs(result["units"][0]["properties"]["pressed"], False)

    def test_contract_is_available_before_the_first_runtime_snapshot(self):
        from unittest.mock import patch

        for state in ("flashing", "failed", "stopped"):
            with self.subTest(state=state):
                self.session.state = state
                with patch("unit_runtime._load", side_effect=AssertionError("current catalog must not be read")):
                    result = self.session.unit_state()
                self.assertEqual(result["source"], "unavailable")
                self.assertEqual(result["units"], [])
                self.assertEqual(result["contract_status"], "frozen")
                self.assertEqual(result["contract_hashes"], self.session.unit_contract["source_hashes"])
                self.assertEqual(result["definitions"][0]["id"], "button")
                self.assertEqual(self.commands, [])

    def test_unrecorded_or_invalid_contract_never_reads_current_catalog_or_writes(self):
        from unittest.mock import patch

        for contract, expected in ((None, "unrecorded"), ({}, "invalid"), ({"schema_version": 9}, "invalid")):
            with self.subTest(expected=expected):
                self.session.unit_contract = contract
                self.session.unit_state_path.write_text(json.dumps({"units": [{"id": "button1", "properties": {"pressed": True}}]}))
                with patch("unit_runtime._load", side_effect=AssertionError("current catalog must not be read")):
                    state = self.session.unit_state()
                    self.assertEqual(state["contract_status"], expected)
                    self.assertEqual(state["definitions"], [])
                    self.assertEqual(state["contract_hashes"], {})
                    self.assertIs(state["units"][0]["properties"]["pressed"], True)
                    with self.assertRaises(ServiceError) as caught:
                        self.session.unit_input({"id": "button1", "values": {"pressed": False}})
                    self.assertEqual(caught.exception.code, "unit_contract_unavailable")
                self.assertEqual(self.commands, [])

    def test_controller_rejection_is_a_conflict_but_transport_failure_is_unavailable(self):
        from unittest.mock import Mock
        from run_profile_ui_test import QMPCommandError

        self.session._proc = Mock()
        self.session._proc.poll.return_value = None
        connection = Mock()
        self.session._qmp = connection
        connection.cmd.side_effect = QMPCommandError("Unit RX exceeds the UART FIFO's current free capacity")
        with self.assertRaises(ServiceError) as caught:
            DeviceSession._qmp_call(self.session, "qom-set", path="/machine/units/uart1", property="rx-hex", value="00")
        self.assertEqual((caught.exception.code, caught.exception.status), ("unit_input_rejected", 409))
        connection.close.assert_not_called()
        self.assertIs(self.session._qmp, connection)
        connection.cmd.side_effect = OSError("connection failed")
        with self.assertRaises(ServiceError) as caught:
            DeviceSession._qmp_call(self.session, "qom-set", path="/machine/units/uart1", property="rx-hex", value="00")
        self.assertEqual((caught.exception.code, caught.exception.status), ("qmp_error", 503))
        connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
