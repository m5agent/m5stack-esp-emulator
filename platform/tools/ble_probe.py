#!/usr/bin/env python3
"""External BLE observer backed by a Bumble virtual controller."""
from __future__ import annotations

import argparse
import asyncio
import sys
import traceback
from typing import Any


NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


def emit(marker: str, detail: str = "") -> None:
    suffix = f" {detail}" if detail else ""
    print(f"{marker}{suffix}", flush=True)


def advertisement_name(advertisement: Any) -> str:
    for data_type in (0x09, 0x08):
        value = advertisement.data.get(data_type, b"")
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if value:
            return str(value)
    return ""


async def observe(args: argparse.Namespace) -> int:
    try:
        from bumble import hci
        from bumble.controller import Controller
        from bumble.device import Device, Peer
        from bumble.host import Host
        from bumble.link import LocalLink
        from bumble.transport import open_transport
    except ImportError as error:
        emit("BLE_BUMBLE_ERROR", f"dependency={error}")
        return 2

    emu_transport = await open_transport(f"tcp-server:_:{args.port}")
    link = LocalLink()
    emu_controller = Controller(
        "network-lane-emu",
        host_source=emu_transport.source,
        host_sink=emu_transport.sink,
        link=link,
        public_address="00:11:22:33:44:55",
    )

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

    found = asyncio.get_running_loop().create_future()

    def on_advertisement(advertisement: Any) -> None:
        if found.done():
            return
        name = advertisement_name(advertisement)
        if not name.startswith(args.name_prefix):
            return
        found.set_result((advertisement, name))

    phone.on("advertisement", on_advertisement)
    emit("BLE_PROBE_READY", f"port={args.port}")
    await phone.start_scanning()

    try:
        advertisement, name = await asyncio.wait_for(found, args.timeout)
    except asyncio.TimeoutError:
        await phone.stop_scanning()
        emit("BLE_BUMBLE_FAIL", f"no advertisement matching {args.name_prefix!r}")
        return 1
    await phone.stop_scanning()
    emit("BLE_BUMBLE_FOUND", f"name={name!r} address={advertisement.address}")

    connection = await phone.connect(advertisement.address, timeout=10)
    emit("BLE_BUMBLE_CONNECTED")
    peer = Peer(connection)
    await peer.discover_services()

    target_service = None
    target_characteristics: dict[str, Any] = {}
    for service in peer.services:
        if NUS_SERVICE_UUID not in str(service.uuid).lower():
            continue
        target_service = service
        await service.discover_characteristics()
        for characteristic in service.characteristics:
            uuid = str(characteristic.uuid).lower()
            if NUS_RX_UUID in uuid:
                target_characteristics["rx"] = characteristic
            elif NUS_TX_UUID in uuid:
                target_characteristics["tx"] = characteristic
        break

    if target_service is None:
        emit("BLE_BUMBLE_FAIL", f"NUS service {NUS_SERVICE_UUID} not found")
        await connection.disconnect()
        return 1
    if set(target_characteristics) != {"rx", "tx"}:
        emit(
            "BLE_BUMBLE_FAIL",
            f"NUS characteristics missing: found={sorted(target_characteristics)}",
        )
        await connection.disconnect()
        return 1

    emit("BLE_BUMBLE_GATT_DISCOVERED", NUS_SERVICE_UUID)
    tx = target_characteristics["tx"]
    await tx.discover_descriptors()
    await tx.subscribe()
    emit("BLE_BUMBLE_SUBSCRIBED", NUS_TX_UUID)

    if args.write_delay > 0:
        await asyncio.sleep(args.write_delay)
    rx = target_characteristics["rx"]
    await rx.write_value(args.payload.encode("utf-8"))
    emit("BLE_BUMBLE_WRITE", args.payload)
    await asyncio.sleep(1)
    emit("BLE_BUMBLE_PASS")
    if args.linger > 0:
        await asyncio.sleep(args.linger)
    await connection.disconnect()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9544)
    parser.add_argument("--name-prefix", default="M5-NETWORK-LANE")
    parser.add_argument("--payload", default="M5_LANE")
    parser.add_argument("--timeout", type=float, default=35)
    parser.add_argument("--write-delay", type=float, default=10)
    parser.add_argument("--linger", type=float, default=15)
    args = parser.parse_args()
    try:
        return asyncio.run(observe(args))
    except Exception as error:  # Keep the parent runner's evidence actionable.
        emit("BLE_BUMBLE_ERROR", repr(error))
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
