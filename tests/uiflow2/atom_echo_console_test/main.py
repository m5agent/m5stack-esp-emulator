# M5Stack Atom Echo / Atom Voice (C008-C) device-local console probe.
#
# Covers the same virtual guest path: ROM/bootloader, M5.begin(), board
# identity 142, the single SK6812 on GPIO27 through RMT, the user button on
# GPIO39 driven by QMP key injection, the Grove I2C bus on G26/G32, the
# NS4168 I2S speaker data plane (host PCM captured at the I2S1 DMA boundary)
# and the SPM1423 PDM microphone RX path with a host-injected PCM fixture on
# I2S0.  Atom Echo has no on-board I2C codec: the scan reports the bus as-is
# and the probe records that no 0x18 ES8311 device is present.  Analog
# audio, acoustics, IR and Grove Unit protocols are not claimed here.
import M5
import time
from M5 import *

print("ATOMECHO_MAIN_START")
M5.begin()
print("ATOMECHO_M5_BEGIN_OK")
print("ATOMECHO_BOARD", M5.getBoard())

try:
    from machine import I2C, Pin

    # M5Unified uses GPIO32/GPIO26 as the external (Grove) I2C pair on this
    # board and GPIO21/GPIO25 as the internal pair.
    scan = []
    i2c = I2C(0, scl=Pin(32), sda=Pin(26), freq=100000)
    scan = i2c.scan()
    print("ATOMECHO_I2C_SCAN", [hex(addr) for addr in scan])
    print("ATOMECHO_ES8311", "present" if 0x18 in scan else "absent")
except Exception as exc:
    print("ATOMECHO_I2C_ERROR", repr(exc))

try:
    from hardware import RGB

    rgb = RGB(io=27, n=1, type="WS2812")
    rgb.set_brightness(100)
    rgb.fill_color(0x204060)
    print("ATOMECHO_RGB", 1, "204060")
except Exception as exc:
    rgb = None
    print("ATOMECHO_RGB_ERROR", repr(exc))

try:
    began = M5.Speaker.begin()
    print("ATOMECHO_SPEAKER_BEGIN", began)
    M5.Speaker.setVolumePercentage(0.6)
    M5.Speaker.tone(440, 1000)
    time.sleep_ms(300)
    print("ATOMECHO_SPEAKER_RUNNING", int(M5.Speaker.isRunning()))
    time.sleep_ms(500)
    print("ATOMECHO_SPEAKER_STATUS", "ok")
except Exception as exc:
    print("ATOMECHO_SPEAKER_STATUS", "error", repr(exc))

try:
    # The RX PCM fixture is injected by the matrix runner; the guest reads it
    # only through the real ESP32 I2S0 PDM RX DMA path.
    began = M5.Mic.begin()
    print("ATOMECHO_MIC_BEGIN", began)
    buffer = bytearray(6400)
    recorded = M5.Mic.record(buffer, 16000, False)
    print("ATOMECHO_MIC_RECORD", recorded)
    deadline = time.ticks_add(time.ticks_ms(), 2000)
    while M5.Mic.isRecording() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        time.sleep_ms(20)
    M5.Mic.end()
    nonzero = sum(1 for value in buffer if value)
    peak = max(buffer) - min(buffer)
    print("ATOMECHO_MIC_PCM", nonzero, peak)
    print(
        "ATOMECHO_MIC_STATUS",
        "ok" if nonzero > 100 and peak > 10 else "silent",
    )
except Exception as exc:
    print("ATOMECHO_MIC_STATUS", "error", repr(exc))

print("ATOMECHO_PROBE_READY")
last = None
count = 0
deadline = time.ticks_add(time.ticks_ms(), 6000)
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    M5.update()
    pressed = int(M5.BtnA.isPressed())
    if pressed != last:
        if pressed:
            count += 1
        print("ATOMECHO_BUTTON_STATE", pressed, count)
        if rgb is not None:
            rgb.fill_color(0x40A020 if pressed else 0x204060)
            print("ATOMECHO_RGB", 1, "40A020" if pressed else "204060")
        last = pressed
    time.sleep_ms(20)
print("ATOMECHO_PROBE_DONE")
