# M5Stack Basic v2.7 (K001-V27) device-local console probe.
#
# Covers the board path in the same virtual guest: ROM/bootloader, M5.begin(),
# board identity, ILI9342C 320x240 display init, A/B/C button GPIO reads,
# the IP5306 register data plane on the G21/G22 bus at 0x75 and the DAC
# speaker path on G25 through I2S0.  The matrix runner injects host key events
# for BtnA/BtnB/BtnC after BASIC27_PROBE_READY and waits for the state markers.
import M5
import time
from M5 import *

print("BASIC27_MAIN_START")
M5.begin()
print("BASIC27_M5_BEGIN_OK")
print("BASIC27_BOARD", M5.getBoard())

display = M5.Display
print("BASIC27_DISPLAY", display.width(), display.height())
display.fillScreen(0x000000)
display.setTextColor(0xFFFFFF, 0x000000)
display.setCursor(4, 8)
display.print("Basic v2.7 probe")
print("BASIC27_DRAW_OK")

pressed = (int(M5.BtnA.isPressed()), int(M5.BtnB.isPressed()),
           int(M5.BtnC.isPressed()))
print("BASIC27_BUTTONS", pressed[0], pressed[1], pressed[2])

try:
    from machine import I2C, Pin

    i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
    print("BASIC27_I2C_SCAN", [hex(addr) for addr in i2c.scan()])

    def reg_read(reg):
        return i2c.readfrom_mem(0x75, reg, 1)[0]

    def reg_write(reg, value):
        i2c.writeto_mem(0x75, reg, bytes([value]))

    sys_ctl0 = reg_read(0x00)
    print("BASIC27_IP5306_SYS", hex(sys_ctl0))
    print("BASIC27_IP5306_CHG_V", hex(reg_read(0x22)))
    print("BASIC27_IP5306_CHG_I", hex(reg_read(0x24)))
    print("BASIC27_IP5306_READ0", hex(reg_read(0x70)))
    print("BASIC27_IP5306_READ1", hex(reg_read(0x71)))
    read4 = reg_read(0x78)
    print("BASIC27_IP5306_READ4", hex(read4))
    # No battery cell is modelled by default, so reg 0x78 is the explicit
    # no-valid-code value 0xff.  The probe only asks the stock M5Unified
    # battery path when a host fixture injected a cell voltage, so it never
    # reports a fabricated percentage for the no-cell state.
    if read4 == 0xff:
        print("BASIC27_IP5306_BATTERY none")
    else:
        print("BASIC27_IP5306_BATTERY cell")
        try:
            print("BASIC27_BATTERY_LEVEL", M5.Power.getBatteryLevel())
        except Exception as exc:
            print("BASIC27_BATTERY_LEVEL error", repr(exc))

    # Power-off request path: clear SYS_CTL0 bit5 (boost enable, the
    # documented "disable" way to stop the rail), read it back and restore.
    # The model only records the request; it does not switch QEMU off.
    reg_write(0x00, sys_ctl0 & ~0x20)
    print("BASIC27_IP5306_BOOST_OFF", (reg_read(0x00) >> 5) & 1)
    reg_write(0x00, sys_ctl0 | 0x20)
    print("BASIC27_IP5306_BOOST_ON", (reg_read(0x00) >> 5) & 1)

    # Charge-voltage request through the stock M5Unified path when exposed.
    try:
        M5.Power.setChargeVoltage(4350)
        print("BASIC27_IP5306_CHG_V_REQ", hex(reg_read(0x22)))
    except Exception as exc:
        print("BASIC27_IP5306_CHG_V_REQ skip", repr(exc))
except Exception as exc:
    print("BASIC27_I2C_ERROR", repr(exc))

try:
    if not Speaker.begin():
        raise RuntimeError("speaker begin failed")
    Speaker.setVolumePercentage(0.6)
    Speaker.tone(440, 900)
    time.sleep_ms(1200)
    print("BASIC27_SPEAKER_RUNNING", int(bool(Speaker.isRunning())))
    Speaker.stop()
    print("BASIC27_SPEAKER_STATUS ok")
except Exception as exc:
    print("BASIC27_SPEAKER_ERROR", repr(exc))

print("BASIC27_PROBE_READY")
last = (pressed[0], pressed[1], pressed[2])
frames = 0
while True:
    M5.update()
    now = (int(M5.BtnA.isPressed()), int(M5.BtnB.isPressed()),
           int(M5.BtnC.isPressed()))
    if now != last:
        print("BASIC27_BUTTON_STATE", now[0], now[1], now[2])
        display.setCursor(4, 28)
        display.print("buttons=%d%d%d" % now)
        last = now
        frames += 1
        print("BASIC27_FRAME_READY", frames)
    time.sleep_ms(20)
