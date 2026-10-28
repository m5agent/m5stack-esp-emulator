"""Exercise the documented RGB565 byte-length contract on a real guest.

Set RAWBUF_EXPECT_VALIDATION=True only for the explicitly corrected firmware.
The matching preimage runs the same valid writes; invalid lengths are skipped
there because its missing bounds checks can read beyond the guest buffer.
"""
import json
import time
import M5


def emit(kind, **values):
    values["api_target"] = "M5.Display"
    print("M5EMU_UI_" + kind + " " + json.dumps(values))


M5.begin()
M5.Display.fillScreen(0x0B1014)
M5.Display.setTextColor(0xFFFFFF)
M5.Display.drawString("RGB565 byte-length contract", 8, 8)
raw_be = bytearray([0xF8, 0x00] * 256)
raw_le = bytearray([0x00, 0xF8] * 256)
M5.Display.drawRawBuf(raw_be, 40, 60, 16, 16, len(raw_be), False)
M5.Display.drawRawBuf(raw_le, 70, 60, 16, 16, len(raw_le), True)
M5.Display.drawRawBuf(raw_be, 100, 60, 16, 16, 256, False)
emit("FRAME_ORACLE", method="drawRawBuf", argument_domain="full-byte-length-big-endian", oracle={"kind": "pixels", "points": [[42, 62, 0xFF0000], [52, 72, 0xFF0000]]}, tolerance=8)
emit("FRAME_ORACLE", method="drawRawBuf", argument_domain="full-byte-length-swap", oracle={"kind": "pixels", "points": [[72, 62, 0xFF0000], [82, 72, 0xFF0000]]}, tolerance=8)
emit("FRAME_ORACLE", method="drawRawBuf", argument_domain="partial-byte-length", oracle={"kind": "pixels", "points": [[102, 62, 0xFF0000], [102, 72, 0x0B1014]]}, tolerance=8)
if globals().get("RAWBUF_EXPECT_VALIDATION", False):
    invalid = [(16, 16, -1), (16, 16, 1), (16, 16, len(raw_be) + 2), (0, 16, 2), (16, -1, 2), (8, 8, 512)]
    for w, h, length in invalid:
        try:
            M5.Display.drawRawBuf(raw_be, 150, 60, w, h, length, False)
        except ValueError:
            emit("RESULT", method="drawRawBuf", argument_domain="invalid-bounds", status="STATE_PASS", width=w, height=h, byte_length=length, oracle="ValueError before display transaction")
        except Exception as error:
            emit("RESULT", method="drawRawBuf", argument_domain="invalid-bounds", status="FAIL", error=repr(error))
        else:
            emit("RESULT", method="drawRawBuf", argument_domain="invalid-bounds", status="FAIL", reason="invalid buffer/window was accepted")
    emit("FRAME_ORACLE", method="drawRawBuf", argument_domain="invalid-does-not-draw", oracle={"kind": "pixels", "points": [[150, 60, 0x0B1014], [155, 65, 0x0B1014]]}, tolerance=8)
else:
    emit("RESULT", method="drawRawBuf", argument_domain="invalid-bounds", status="NOT_RUN", reason="preimage lacks the bounds guard; unsafe reads are not needed to reproduce the valid-input bug")
for _ in range(30):
    M5.update()
    time.sleep_ms(20)
print("RAWBUF_CORRECTION_DONE")
