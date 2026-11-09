"""HID over GATT input observation on an existing Bumble HCI link."""
from __future__ import annotations

import asyncio
import hashlib


def input_report_lengths(report_map: bytes) -> dict[int, int]:
    """Return the payload length for each Input Report ID, excluding the ID."""
    if not 1 <= len(report_map) <= 512:
        raise ValueError("invalid HID Report Map size")
    offset = report_id = size = count = 0
    stack = []
    bits: dict[int, int] = {}
    while offset < len(report_map):
        prefix = report_map[offset]
        offset += 1
        if prefix == 0xFE:
            if offset + 2 > len(report_map):
                raise ValueError("truncated HID long item header")
            offset += 2 + report_map[offset]
            if offset > len(report_map):
                raise ValueError("truncated HID long item")
            continue
        width = (0, 1, 2, 4)[prefix & 3]
        if offset + width > len(report_map):
            raise ValueError("truncated HID short item")
        value = int.from_bytes(report_map[offset:offset + width], "little")
        offset += width
        item = prefix & 0xFC
        if item == 0x74:  # Global Report Size
            size = value
        elif item == 0x84:  # Global Report ID
            if not 1 <= value <= 255:
                raise ValueError("invalid HID Report ID")
            report_id = value
        elif item == 0x94:  # Global Report Count
            count = value
        elif item == 0xA4:  # Global Push
            stack.append((report_id, size, count))
        elif item == 0xB4:  # Global Pop
            if not stack:
                raise ValueError("unbalanced HID global Pop")
            report_id, size, count = stack.pop()
        elif item == 0x80:  # Main Input, including constant padding bits.
            if not size or not count:
                raise ValueError("HID Input requires nonzero Report Size and Count")
            bits[report_id] = bits.get(report_id, 0) + size * count
            if bits[report_id] > 512 * 8:
                raise ValueError("HID Input report exceeds 512 bytes")
    if stack or not bits or (0 in bits and len(bits) > 1):
        raise ValueError("invalid HID Input report layout")
    return {report_id: (length + 7) // 8 for report_id, length in bits.items()}


async def observe_hid_input(connection, args, emit) -> int:
    """Discover HOGP Reports and count valid notifications from this connection."""
    from bumble import att, gatt
    from bumble.device import Peer

    security_errors = {
        att.ATT_INSUFFICIENT_AUTHENTICATION_ERROR,
        att.ATT_INSUFFICIENT_ENCRYPTION_ERROR,
        att.ATT_INSUFFICIENT_ENCRYPTION_KEY_SIZE_ERROR,
    }
    pairing_attempted = False

    async def pair() -> None:
        nonlocal pairing_attempted
        pairing_attempted = True
        emit("BLE_HID_PAIRING_STARTED")
        await asyncio.wait_for(connection.pair(), args.gatt_request_timeout)
        if not connection.is_encrypted:
            raise RuntimeError("SMP finished without link encryption")
        keys = await connection.device.keystore.get(str(connection.peer_address))
        emit("BLE_HID_PAIRING_COMPLETE", f"encrypted=true bond_keys_retained={str(keys is not None).lower()}")

    async def access(operation):
        try:
            return await operation()
        except att.ATT_Error as error:
            if (
                args.hid_pairing != "auto" or pairing_attempted
                or error.error_code not in security_errors
            ):
                raise
            await pair()
            return await operation()

    if args.hid_pairing == "always":
        await pair()

    peer = Peer(connection)
    services = await access(peer.discover_services)
    hid_services = [
        service for service in services
        if service.uuid == gatt.GATT_HUMAN_INTERFACE_DEVICE_SERVICE
    ]
    if not hid_services:
        raise ValueError("HID service 0x1812 was not discovered")

    reports = []
    for service in hid_services:
        emit("BLE_HID_SERVICE_DISCOVERED", f"uuid=1812 att_handle=0x{service.handle:04x}")
        characteristics = await access(service.discover_characteristics)
        report_maps = [
            characteristic for characteristic in characteristics
            if characteristic.uuid == gatt.GATT_REPORT_MAP_CHARACTERISTIC
        ]
        if len(report_maps) != 1:
            raise ValueError("HID service must expose exactly one Report Map")
        report_map = await access(report_maps[0].read_value)
        lengths = input_report_lengths(report_map)
        emit("BLE_HID_REPORT_MAP", f"length={len(report_map)} sha256={hashlib.sha256(report_map).hexdigest()}")
        for characteristic in characteristics:
            if characteristic.uuid != gatt.GATT_REPORT_CHARACTERISTIC:
                continue
            await access(characteristic.discover_descriptors)
            reference = characteristic.get_descriptor(gatt.GATT_REPORT_REFERENCE_DESCRIPTOR)
            if reference is None:
                raise ValueError("HID Report characteristic is missing its Report Reference")
            value = await access(reference.read_value)
            if len(value) != 2 or value[1] not in (1, 2, 3):
                raise ValueError("invalid HID Report Reference")
            report_id, report_type = value
            if report_type != 1:
                continue
            if report_id not in lengths:
                raise ValueError(f"HID Input Report ID {report_id} is absent from its Report Map")
            if not characteristic.properties & gatt.Characteristic.Properties.NOTIFY:
                raise ValueError("HID Input Report characteristic does not support notification")
            if characteristic.get_descriptor(gatt.GATT_CLIENT_CHARACTERISTIC_CONFIGURATION_DESCRIPTOR) is None:
                raise ValueError("HID Input Report characteristic is missing its CCCD")
            reports.append((characteristic, report_id, lengths[report_id]))
    if not reports:
        raise ValueError("no notifiable HID Input Report characteristic was discovered")

    completion = asyncio.get_running_loop().create_future()
    count = 0

    def observer(handle: int, report_id: int, length: int):
        def notification(value: bytes) -> None:
            nonlocal count
            if completion.done():
                return
            if len(value) != length:
                completion.set_exception(ValueError(
                    f"HID Input Report ID {report_id} has {len(value)} bytes; expected {length}"
                ))
                return
            count += 1
            emit(
                "BLE_HID_REPORT",
                f"uuid=2a4d att_handle=0x{handle:04x} report_id={report_id} "
                f"length={len(value)} payload_hex={value[:64].hex()}",
            )
            if count >= args.hid_min_reports:
                completion.set_result(None)
        return notification

    try:
        for characteristic, report_id, length in reports:
            handle = characteristic.handle
            callback = observer(handle, report_id, length)
            await access(lambda: characteristic.subscribe(callback, prefer_notify=True))
            emit("BLE_HID_SUBSCRIBED", f"uuid=2a4d att_handle=0x{handle:04x} report_id={report_id}")
        await asyncio.wait_for(completion, args.notification_timeout)
    except asyncio.TimeoutError as error:
        raise TimeoutError(f"HID notification timeout after {count} valid reports") from error
    finally:
        if not completion.done():
            completion.cancel()
        elif not completion.cancelled():
            completion.exception()
    return count
