"""Identify accepted stock representations for 16/32/128-bit Bluetooth UUIDs."""
import json

import bluetooth


for value in (0x1234, 0x12345678, "1234", "12345678", "00001234", b"\x78\x56\x34\x12"):
    row = {"value": repr(value), "status": "PASS"}
    try:
        uuid = bluetooth.UUID(value)
        row["bytes"] = bytes(uuid).hex()
        row["string"] = str(uuid)
    except Exception as error:
        row["status"] = "ERROR"
        row["error"] = repr(error)
    print("BLUETOOTH_UUID " + json.dumps(row))
print("BLUETOOTH_UUID_FORMS_DONE")
