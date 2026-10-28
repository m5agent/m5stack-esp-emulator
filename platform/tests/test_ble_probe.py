from __future__ import annotations

import sys
import io
import asyncio
import contextlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from ble_probe import install_controller_command_compatibility, main, serve_peripheral


class BleProbeCompatibilityTests(unittest.TestCase):
    def test_peripheral_cli_rejects_unsupported_workloads_before_startup(self):
        for arguments in (("--role", "invalid"), ("--role", "peripheral", "--reconnect-cycles", "2"),
                          ("--role", "peripheral", "--post-pass-trigger", "/tmp/owned-trigger")):
            with self.subTest(arguments=arguments), mock.patch.object(sys,"argv",["ble_probe.py",*arguments]), mock.patch("ble_probe.asyncio.run") as dispatch, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    main()
                self.assertEqual(caught.exception.code,2)
                dispatch.assert_not_called()

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


class BlePeripheralLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def run_exchange(self, workload):
        """Run the real fixture with an in-memory ATT transport and CCCDs."""
        class Characteristic:
            NOTIFY, READ, WRITE = 1, 2, 4
            EVENT_SUBSCRIPTION = "subscription"

            def __init__(self, uuid, properties, permissions, value):
                self.value = value
                self.listeners = {}

            def on(self, event, callback):
                self.listeners[event] = callback

        class Connection:
            def __init__(self, device, handle):
                self.device, self.handle = device, handle
                self.listeners = {}

            def on(self, event, callback):
                self.listeners[event] = callback

            async def disconnect(self):
                if self.device.connections.get(self.handle) is self:
                    del self.device.connections[self.handle]
                self.device.cccds.pop(self, None)
                self.listeners["disconnection"](0)

        class Device:
            def __init__(self):
                self.connections, self.cccds = {}, {}
                self.notifications, self.notification_requests = [], []
                self.before_notification = None
                self.advertising_stopped = False

            def add_service(self, service):
                self.tx, self.rx = service.characteristics

            def on(self, event, callback):
                self.on_connection = callback

            def connect(self, handle):
                connection = Connection(self, handle)
                self.connections[handle] = connection
                self.on_connection(connection)
                return connection

            def subscribe(self, bearer, notify):
                self.cccds[bearer] = notify
                self.tx.listeners["subscription"](bearer, notify, False)

            async def notify_subscriber(self, bearer, characteristic, value):
                self.notification_requests.append(bearer)
                if self.before_notification is not None:
                    await self.before_notification()
                # Independent transport oracle: Bumble skips retired or
                # unsubscribed recipients without returning a delivery result.
                if self.connections.get(bearer.handle) is bearer and self.cccds.get(bearer):
                    self.notifications.append((bearer.handle, bytes(value)))

            async def notify_subscribers(self, characteristic, value):
                # Keep broadcast behavior available so the pre-fix fixture
                # reproduces its false PASS and wrong-recipient notification.
                for bearer in tuple(self.cccds):
                    if self.cccds[bearer]:
                        await self.notify_subscriber(bearer, characteristic, value)

            async def start_advertising(self, **kwargs):
                self.workload = asyncio.create_task(workload(self))

            async def stop_advertising(self):
                self.advertising_stopped = True

        modules = {
            "bumble.core": SimpleNamespace(UUID=lambda value: SimpleNamespace(to_pdu_bytes=lambda: bytes(16))),
            "bumble.gatt": SimpleNamespace(
                Characteristic=Characteristic,
                CharacteristicValue=lambda **callbacks: SimpleNamespace(**callbacks),
                Service=lambda uuid, characteristics: SimpleNamespace(characteristics=characteristics),
            ),
        }
        args = SimpleNamespace(
            payload="payload", tx_uuid="tx", rx_uuid="rx", service_uuid="service",
            port=0, timeout=0.5, linger=0,
        )
        device, output = Device(), io.StringIO()
        with mock.patch.dict(sys.modules, modules), contextlib.redirect_stdout(output):
            result = await serve_peripheral(device, args)
            await device.workload
        self.assertTrue(device.advertising_stopped)
        self.assertEqual(device.connections, {})
        return result, output.getvalue(), device

    def assert_failed_without_notification(self, result, output, device):
        self.assertEqual(result, 1)
        self.assertIn("BLE_PERIPHERAL_FAIL", output)
        self.assertNotIn("BLE_PERIPHERAL_PASS", output)
        self.assertNotIn("BLE_PERIPHERAL_NOTIFICATION_SENT", output)
        self.assertEqual(device.notifications, [])

    async def test_unsubscribed_writer_cannot_reuse_earlier_subscription(self):
        async def workload(device):
            writer = device.connect(1)
            device.subscribe(writer, True)
            device.subscribe(writer, False)
            await device.rx.value.write(writer, b"payload")

        result, output, device = await self.run_exchange(workload)
        self.assert_failed_without_notification(result, output, device)
        self.assertEqual(device.notification_requests, [])

    async def test_another_connection_subscription_does_not_authorize_writer(self):
        async def workload(device):
            subscriber = device.connect(1)
            device.subscribe(subscriber, True)
            writer = device.connect(2)
            await device.rx.value.write(writer, b"payload")

        result, output, device = await self.run_exchange(workload)
        self.assert_failed_without_notification(result, output, device)
        self.assertEqual(device.notification_requests, [])

    async def test_disconnection_invalidates_writer_and_reused_handle(self):
        for boundary in ("before-write", "during-notification", "reused-handle"):
            with self.subTest(boundary=boundary):
                async def workload(device):
                    writer = device.connect(1)
                    device.subscribe(writer, True)
                    if boundary == "during-notification":
                        device.before_notification = writer.disconnect
                    else:
                        await writer.disconnect()
                        if boundary == "reused-handle":
                            writer = device.connect(1)
                    await device.rx.value.write(writer, b"payload")

                result, output, device = await self.run_exchange(workload)
                self.assert_failed_without_notification(result, output, device)

    async def test_valid_subscription_notifies_only_the_writer(self):
        async def workload(device):
            other = device.connect(1)
            device.subscribe(other, True)
            writer = device.connect(2)
            device.subscribe(writer, True)
            await device.rx.value.write(writer, b"payload")

        result, output, device = await self.run_exchange(workload)
        self.assertEqual(result, 0)
        self.assertIn("BLE_PERIPHERAL_PASS", output)
        self.assertIn("BLE_PERIPHERAL_NOTIFICATION_SENT", output)
        self.assertNotIn("BLE_PERIPHERAL_FAIL", output)
        self.assertEqual(device.notifications, [(2, b"ACK:payload")])
        self.assertEqual([bearer.handle for bearer in device.notification_requests], [2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
