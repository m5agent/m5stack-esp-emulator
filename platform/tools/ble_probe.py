#!/usr/bin/env python3
"""External BLE observer backed by a Bumble virtual controller."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from ble_runtime_limits import (
    MAX_BLE_RECONNECT_CYCLES,
    MAX_BLE_RECONNECT_DELAY_SECONDS,
)

NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


def emit(marker: str, detail: str = "") -> None:
    suffix = f" {detail}" if detail else ""
    if os.getenv("BLE_TRACE_TIMESTAMPS") == "1":
        suffix += f" t={time.time_ns()}"
    print(f"{marker}{suffix}", flush=True)


def advertisement_name(advertisement: Any) -> str:
    for data_type in (0x09, 0x08):
        value = advertisement.data.get(data_type, b"")
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if value:
            return str(value)
    return ""


def trace_hci_transport(transport: Any) -> None:
    """Trace complete H4 packets in each direction without changing framing."""

    if os.getenv("BLE_HCI_TRACE") != "1":
        return

    original_source = transport.source
    original_sink = transport.sink

    class TracedSource:
        metadata = getattr(original_source, "metadata", None)

        def set_packet_sink(self, sink: Any) -> None:
            class TracedSink:
                def on_packet(self, packet: Any) -> None:
                    emit("BLE_HCI_GUEST_TO_BUMBLE", bytes(packet).hex())
                    sink.on_packet(packet)

            original_source.set_packet_sink(TracedSink())

    class TracedSink:
        def on_packet(self, packet: Any) -> None:
            emit("BLE_HCI_BUMBLE_TO_GUEST", bytes(packet).hex())
            original_sink.on_packet(packet)

    transport.source = TracedSource()
    transport.sink = TracedSink()


def install_controller_compatibility(controller_class: Any, hci_module: Any) -> None:
    """Fill standard controller handlers that this Bumble revision omits."""

    if hasattr(
        controller_class,
        "on_hci_read_remote_version_information_command",
    ):
        return

    def read_remote_version_information(
        controller: Any, command: Any
    ) -> None:
        connection = controller.find_connection_by_handle(
            command.connection_handle
        )
        if connection is None:
            controller._send_hci_command_status(
                hci_module.HCI_ErrorCode.UNKNOWN_CONNECTION_IDENTIFIER_ERROR,
                command.op_code,
            )
            return

        controller._send_hci_command_status(
            hci_module.HCI_Command_Status_Event.PENDING,
            command.op_code,
        )
        controller.send_hci_packet(
            hci_module.HCI_Read_Remote_Version_Information_Complete_Event(
                status=hci_module.HCI_ErrorCode.SUCCESS,
                connection_handle=command.connection_handle,
                version=hci_module.HCI_VERSION_BLUETOOTH_CORE_5_0,
                manufacturer_name=controller.manufacturer_company_identifier,
                subversion=controller.lmp_subversion,
            )
        )

    controller_class.on_hci_read_remote_version_information_command = (
        read_remote_version_information
    )


def install_controller_command_compatibility(
    controller_class: Any, hci_module: Any
) -> None:
    """Handle standard commands with defined no-op/controller semantics."""

    if not hasattr(controller_class, "on_hci_le_set_data_length_command"):

        def set_data_length(controller: Any, command: Any) -> Any:
            connection = controller.find_le_connection_by_handle(
                command.connection_handle
            )
            if connection is None:
                return hci_module.HCI_StatusAndConnectionHandleReturnParameters(
                    status=(
                        hci_module.HCI_ErrorCode.UNKNOWN_CONNECTION_IDENTIFIER_ERROR
                    ),
                    connection_handle=command.connection_handle,
                )
            return hci_module.HCI_StatusAndConnectionHandleReturnParameters(
                status=hci_module.HCI_ErrorCode.SUCCESS,
                connection_handle=command.connection_handle,
            )

        controller_class.on_hci_le_set_data_length_command = set_data_length

    if not hasattr(
        controller_class,
        "on_hci_host_number_of_completed_packets_command",
    ):

        def host_completed_packets(controller: Any, command: Any) -> None:
            # Bluetooth Core Vol 4, Part E, 7.3.35: this command has no
            # command complete or command status response. Sending a status
            # here leaves a stale ACK that corrupts the next HCI transaction.
            return None

        controller_class.on_hci_host_number_of_completed_packets_command = (
            host_completed_packets
        )


async def observe(args: argparse.Namespace) -> int:
    try:
        from bumble import gatt_client as bumble_gatt_client
        from bumble import hci
        from bumble.controller import Controller
        from bumble.device import Device, Peer
        from bumble.host import Host
        from bumble.link import LocalLink
        from bumble.transport import open_transport
    except ImportError as error:
        emit("BLE_BUMBLE_ERROR", f"dependency={error}")
        return 2

    bumble_gatt_client.GATT_REQUEST_TIMEOUT = args.gatt_request_timeout
    emu_transport = await open_transport(f"tcp-server:_:{args.port}")
    trace_hci_transport(emu_transport)
    link = LocalLink()
    emu_controller = Controller(
        "network-lane-emu",
        host_source=emu_transport.source,
        host_sink=emu_transport.sink,
        link=link,
        public_address="00:11:22:33:44:55",
    )
    install_controller_compatibility(Controller, hci)
    install_controller_command_compatibility(Controller, hci)

    def ack_ok(controller: Controller, command: Any) -> Any:
        parameters = hci.HCI_GenericReturnParameters(data=bytes([0]))
        if isinstance(command, hci.HCI_SyncCommand):
            return parameters
        controller.send_hci_packet(
            hci.HCI_Command_Complete_Event(
                num_hci_command_packets=1,
                command_opcode=command.op_code,
                return_parameters=parameters,
            )
        )
        return None

    for method_name in (
        "on_hci_le_set_privacy_mode_command",
        "on_hci_le_clear_resolving_list_command",
        "on_hci_le_add_device_to_resolving_list_command",
        "on_hci_le_remove_device_from_resolving_list_command",
    ):
        if not hasattr(Controller, method_name):
            setattr(Controller, method_name, ack_ok)

    emu_controller.random_address = hci.Address(
        "00:11:22:33:44:55",
        hci.Address.PUBLIC_DEVICE_ADDRESS,
    )

    phone_host = Host()
    phone_controller = Controller(
        "network-lane-phone",
        link=link,
        public_address="AA:BB:CC:DD:EE:FF",
    )
    phone_host.controller = phone_controller
    phone_controller.host = phone_host
    phone = Device(name="Network Lane Observer", host=phone_host)
    await phone.power_on()

    advertisements: asyncio.Queue[Any] = asyncio.Queue()

    def on_advertisement(advertisement: Any) -> None:
        name = advertisement_name(advertisement)
        if not name.startswith(args.name_prefix):
            return
        advertisements.put_nowait((advertisement, name))

    phone.on("advertisement", on_advertisement)
    emit("BLE_PROBE_READY", f"port={args.port}")

    async def find_advertisement() -> tuple[Any, str]:
        while not advertisements.empty():
            advertisements.get_nowait()
        await phone.start_scanning()
        try:
            advertisement, name = await asyncio.wait_for(
                advertisements.get(),
                args.timeout,
            )
        finally:
            await phone.stop_scanning()
        return advertisement, name

    async def exchange(cycle: int) -> Any:
        emit("BLE_BUMBLE_CYCLE_START", str(cycle))
        advertisement, name = await find_advertisement()
        emit("BLE_BUMBLE_FOUND", f"name={name!r} address={advertisement.address}")

        connection = await phone.connect(advertisement.address, timeout=10)
        emit("BLE_BUMBLE_CONNECTED")
        peer = Peer(connection)
        await peer.discover_services()

        target_service = None
        target_characteristics: dict[str, Any] = {}
        for service in peer.services:
            if args.service_uuid.lower() not in str(service.uuid).lower():
                continue
            target_service = service
            await service.discover_characteristics()
            for characteristic in service.characteristics:
                uuid = str(characteristic.uuid).lower()
                if args.rx_uuid.lower() in uuid:
                    target_characteristics["rx"] = characteristic
                elif args.tx_uuid and args.tx_uuid.lower() in uuid:
                    target_characteristics["tx"] = characteristic
            break

        if target_service is None:
            emit("BLE_BUMBLE_FAIL", f"service {args.service_uuid} not found")
            await connection.disconnect()
            return None
        required_characteristics = {"rx"}
        if args.subscribe:
            required_characteristics.add("tx")
        if set(target_characteristics) != required_characteristics:
            emit(
                "BLE_BUMBLE_FAIL",
                f"characteristics missing: found={sorted(target_characteristics)}",
            )
            await connection.disconnect()
            return None

        emit("BLE_BUMBLE_GATT_DISCOVERED", args.service_uuid)
        notification_future: asyncio.Future[bytes] | None = None
        if args.subscribe:
            tx = target_characteristics["tx"]
            await tx.discover_descriptors()
            notification_future = asyncio.get_running_loop().create_future()

            def on_notification(value: bytes) -> None:
                emit("BLE_BUMBLE_NOTIFICATION", value.hex())
                if not notification_future.done():
                    notification_future.set_result(value)

            await tx.subscribe(on_notification)
            emit("BLE_BUMBLE_SUBSCRIBED", args.tx_uuid)

        if args.write_delay > 0:
            await asyncio.sleep(args.write_delay)
        rx = target_characteristics["rx"]
        await rx.write_value(args.payload.encode("utf-8"))
        emit("BLE_BUMBLE_WRITE", args.payload)
        if args.expect_notification_prefix:
            assert notification_future is not None
            try:
                notification = await asyncio.wait_for(
                    notification_future,
                    args.notification_timeout,
                )
            except asyncio.TimeoutError:
                emit("BLE_BUMBLE_FAIL", "notification timeout")
                await connection.disconnect()
                return None
            expected = args.expect_notification_prefix.encode("utf-8")
            if not notification.startswith(expected):
                emit(
                    "BLE_BUMBLE_FAIL",
                    f"notification prefix mismatch: {notification.hex()}",
                )
                await connection.disconnect()
                return None
            emit(
                "BLE_BUMBLE_NOTIFICATION_OK",
                notification.decode(errors="replace"),
            )
        if args.readback:
            value = await rx.read_value()
            emit("BLE_BUMBLE_READBACK", value.hex())
            if value != args.payload.encode("utf-8"):
                emit("BLE_BUMBLE_FAIL", "readback mismatch")
                await connection.disconnect()
                return None
            emit("BLE_BUMBLE_READBACK_OK")
        await asyncio.sleep(1)
        emit("BLE_BUMBLE_CYCLE_PASS", str(cycle))
        return connection

    connection = None
    try:
        for cycle in range(1, args.reconnect_cycles + 1):
            connection = await exchange(cycle)
            if connection is None:
                return 1
            if cycle < args.reconnect_cycles:
                await connection.disconnect()
                connection = None
                emit("BLE_BUMBLE_DISCONNECTED", str(cycle))
                await asyncio.sleep(args.reconnect_delay)
        emit("BLE_BUMBLE_PASS", f"cycles={args.reconnect_cycles}")
        assert connection is not None
        if args.post_pass_trigger is not None:
            trigger = args.post_pass_trigger
            trigger.unlink(missing_ok=True)
            emit("BLE_BUMBLE_POST_PASS_WAIT", str(trigger))
            deadline = time.monotonic() + args.post_pass_trigger_timeout
            while not trigger.is_file():
                if time.monotonic() >= deadline:
                    emit("BLE_BUMBLE_FAIL", "post-pass continuity trigger timeout")
                    await connection.disconnect()
                    connection = None
                    return 1
                await asyncio.sleep(0.1)
            trigger.unlink(missing_ok=True)
            await connection.disconnect()
            connection = None
            emit("BLE_BUMBLE_DISCONNECTED", str(args.reconnect_cycles))
            await asyncio.sleep(args.reconnect_delay)
            connection = await exchange(args.reconnect_cycles + 1)
            if connection is None:
                return 1
            emit(
                "BLE_BUMBLE_CONTINUITY_PASS",
                str(args.reconnect_cycles + 1),
            )
        if args.linger > 0:
            await asyncio.sleep(args.linger)
        await connection.disconnect()
        connection = None
        return 0
    except asyncio.TimeoutError:
        emit("BLE_BUMBLE_FAIL", f"no advertisement matching {args.name_prefix!r}")
        return 1
    finally:
        if connection is not None:
            try:
                await connection.disconnect()
            except Exception as error:  # noqa: BLE001 - preserve the primary result.
                emit("BLE_BUMBLE_DISCONNECT_ERROR", repr(error))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9544)
    parser.add_argument("--name-prefix", default="M5-NETWORK-LANE")
    parser.add_argument("--payload", default="M5_LANE")
    parser.add_argument("--service-uuid", default=NUS_SERVICE_UUID)
    parser.add_argument("--rx-uuid", default=NUS_RX_UUID)
    parser.add_argument("--tx-uuid", default=NUS_TX_UUID)
    parser.add_argument(
        "--subscribe",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--readback", action="store_true")
    parser.add_argument("--expect-notification-prefix")
    parser.add_argument("--gatt-request-timeout", type=float, default=10)
    parser.add_argument("--notification-timeout", type=float, default=10)
    parser.add_argument("--timeout", type=float, default=35)
    parser.add_argument("--write-delay", type=float, default=10)
    parser.add_argument("--linger", type=float, default=15)
    parser.add_argument(
        "--reconnect-cycles",
        type=int,
        default=1,
        help="number of complete GATT transactions in one peer process",
    )
    parser.add_argument(
        "--reconnect-delay",
        type=float,
        default=2,
        help="seconds between peer disconnect and the next scan",
    )
    parser.add_argument(
        "--post-pass-trigger",
        type=Path,
        help="after emitting PASS, wait for this file then run one continuity cycle",
    )
    parser.add_argument(
        "--post-pass-trigger-timeout",
        type=float,
        default=60,
        help="bounded wait for the post-pass continuity trigger",
    )
    args = parser.parse_args()
    if (
        args.reconnect_cycles < 1
        or args.reconnect_cycles > MAX_BLE_RECONNECT_CYCLES
    ):
        parser.error(
            "--reconnect-cycles must be from 1 to "
            f"{MAX_BLE_RECONNECT_CYCLES}"
        )
    if not 0 <= args.reconnect_delay <= MAX_BLE_RECONNECT_DELAY_SECONDS:
        parser.error(
            "--reconnect-delay must be from 0 to "
            f"{MAX_BLE_RECONNECT_DELAY_SECONDS}"
        )
    if args.post_pass_trigger_timeout <= 0:
        parser.error("--post-pass-trigger-timeout must be positive")
    if args.gatt_request_timeout <= 0:
        parser.error("--gatt-request-timeout must be positive")
    try:
        return asyncio.run(observe(args))
    except Exception as error:  # noqa: BLE001 - emit actionable peer failure.
        emit("BLE_BUMBLE_ERROR", repr(error))
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
