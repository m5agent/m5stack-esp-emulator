"""Finite cold-boot baseline shared by StopWatch, StickS3 and Core2 sweeps."""
import json
import os
import sys


def emit(kind, **fields):
    payload = dict(fields)
    payload["kind"] = kind
    print("M5EMU_BOARD_BASELINE " + json.dumps(payload, separators=(",", ":")))


emit("RUNTIME", version=sys.version, platform=sys.platform, uname=list(os.uname()))
for name in (
    "M5",
    "M5UI",
    "m5ui",
    "ui",
    "lvgl",
    "m5ui.port",
    "m5ui.page",
):
    try:
        module = __import__(name, None, None, ["*"])
        emit("IMPORT", path=name, status="PRESENT", module_type=type(module).__name__)
    except Exception as error:
        emit("IMPORT", path=name, status="ABSENT", error=repr(error))

try:
    import M5

    M5.begin()
    board = M5.getBoard()
    width, height = M5.Display.width(), M5.Display.height()
    emit(
        "DISPLAY",
        status="PASS" if width > 0 and height > 0 else "FAIL",
        board=board,
        width=width,
        height=height,
        display_type=type(M5.Display).__name__,
    )
except Exception as error:
    emit("DISPLAY", status="ERROR", error=repr(error))

print("M5EMU_BOARD_BASELINE_DONE")
