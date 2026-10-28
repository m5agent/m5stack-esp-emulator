"""Execute the reviewed BLE-UUID32 and Modbus transform candidate modules."""
import bluetooth
import json


def check(api, value):
    print("CORRECTION_API " + json.dumps({
        "api": api,
        "status": "PASS" if value else "FAIL",
        "value": value,
        "oracle": "reviewed candidate source loaded from virtual Flash and compared with independent bytes",
    }))


def load(name, path):
    namespace = {"__name__": "candidate_" + name}
    with open(path, "r") as handle:
        source = handle.read()
    exec(compile(source, path, "exec"), namespace)
    return namespace


payloads = (
    (b"\x03\x03\x0d\x18", "0d18"),
    (b"\x05\x05\x78\x56\x34\x12", "78563412"),
)
for module_name, path in (
    ("bleuart.ble_advertising", "/flash/candidate_ble_advertising.py"),
    ("m5ble.m5ble", "/flash/candidate_m5ble.py"),
):
    module = load(module_name, path)
    for payload, expected in payloads:
        check(
            module_name + ".decode_services." + str(len(payload)),
            [bytes(item).hex() for item in module["decode_services"](payload)] == [expected],
        )


frame = load("modbus.frame", "/flash/candidate_modbus_frame.py")
TCP = frame["ModbusTCPFrame"]
RTU = frame["ModbusRTUFrame"]


def encoded(**kwargs):
    return bytes(RTU.transform_frame(TCP(**kwargs)).get_frame()).hex()


check("modbus.frame.ModbusRTUFrame.transform_frame.request", encoded(
    transaction_id=7, unit_id=1, func_code=3, register=0, length=2
) == "010300000002c40b")
check("modbus.frame.ModbusRTUFrame.transform_frame.response", encoded(
    transaction_id=7, unit_id=1, func_code=3, fr_type="response", data=b"\x10\xe1"
) == "01030210e175cc")
check("modbus.frame.ModbusRTUFrame.transform_frame.error", encoded(
    transaction_id=7, unit_id=1, func_code=0x83, fr_type="response", error_code=2
) == "018302c0f1")
print("SHARED_CORRECTIONS_DONE")
