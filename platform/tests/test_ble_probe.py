from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from ble_probe import install_controller_command_compatibility


class BleProbeCompatibilityTests(unittest.TestCase):
    def test_host_completed_packets_has_no_hci_response(self):
        class Controller:
            def __init__(self):
                self.responses = []

            def _send_hci_command_status(self, status, opcode):
                self.responses.append((status, opcode))

        hci = SimpleNamespace(
            HCI_StatusAndConnectionHandleReturnParameters=object,
            HCI_ErrorCode=SimpleNamespace(
                SUCCESS=0,
                UNKNOWN_CONNECTION_IDENTIFIER_ERROR=2,
            ),
        )
        install_controller_command_compatibility(Controller, hci)
        controller = Controller()
        command = SimpleNamespace(op_code=0x0C35)

        result = controller.on_hci_host_number_of_completed_packets_command(command)

        self.assertIsNone(result)
        self.assertEqual(controller.responses, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
