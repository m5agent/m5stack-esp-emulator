"""Cardputer-ADV Widgets module: native state and independent display pixels."""
import json
import time
import M5
from M5 import Widgets


def record(method, ok, value, oracle):
    print("M5EMU_UI_RESULT " + json.dumps({
        "api_target": "M5.Widgets", "method": method,
        "status": "STATE_PASS" if ok else "FAIL", "value": value, "oracle": oracle,
    }))


try:
    M5.begin()
    rotations = []
    for rotation in (0, 1):
        Widgets.setRotation(rotation)
        rotations.append([M5.Lcd.getRotation(), M5.Lcd.width(), M5.Lcd.height()])
    record("setRotation", rotations == [[0, 135, 240], [1, 240, 135]], rotations,
           "actual native display rotation and portrait/landscape dimensions; no physical orientation claim")
    brightness = []
    for value in (32, 192):
        Widgets.setBrightness(value)
        brightness.append(M5.Lcd.getBrightness())
    record("setBrightness", brightness == [32, 192], brightness,
           "actual native display brightness readback; physical backlight intensity is outside this oracle")
    Widgets.fillScreen(0x38B8C8)
    for _ in range(20):
        M5.update()
        time.sleep_ms(20)
    print("M5EMU_UI_RESULT " + json.dumps({
        "api_target": "M5.Widgets", "method": "fillScreen", "status": "CALL_OK",
        "oracle": "actual Widgets fill called; requested color is checked in the separate framebuffer oracle",
    }))
    print("M5EMU_UI_FRAME_ORACLE " + json.dumps({
        "api_target": "M5.Widgets", "method": "fillScreen", "tolerance": 8,
        "oracle": {"kind": "pixels", "points": [[5, 5, 0x38B8C8], [120, 67, 0x38B8C8], [234, 129, 0x38B8C8]]},
    }))
except Exception as error:
    print("M5EMU_UI_RESULT " + json.dumps({
        "api_target": "M5.Widgets", "method": "module_fixture", "status": "FIXTURE_ERROR",
        "error": repr(error),
    }))
print("WIDGETS_MODULE_CARDPUTER_DONE")
