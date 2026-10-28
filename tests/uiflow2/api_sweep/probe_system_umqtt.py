"""Isolate umqtt imports because a blocking import can stall every later API."""
import json


def emit(api, value):
    print("SYSTEM_API " + json.dumps({
        "api": api,
        "status": "PASS",
        "value": value,
        "oracle": "native module import followed by exact public binary/hex vector",
    }))


import umqtt
emit("umqtt", type(umqtt).__name__)
import umqtt.simple
emit("umqtt.simple", umqtt.simple.hexlify(b"\x00\xab\xff").decode())
print("SYSTEM_UMQTT_DONE")
