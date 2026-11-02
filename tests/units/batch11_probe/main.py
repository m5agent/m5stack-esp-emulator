"""Batch-11 guest probes for the seven planned Units with existing models."""
import time, sys
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)
MARKER = "BATCH11_PROBE_READY"
def print(*p): _console.write(" ".join(str(x) for x in p) + "\n")
def wait_ms(ms):
    start=time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        M5.update(); time.sleep_ms(10)
def show(screen,text):
    screen.setCursor(6,42); screen.print(str(text))
print("BATCH11_PROBE_START", CASE)
M5.begin(); screen=M5.Display
if DEVICE_ID=="cores3": screen.setRotation(1)
screen.setBrightness(255); screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB,0xFFFFFF); screen.setTextSize(2); screen.setCursor(6,6)
screen.print("Batch11 Unit: "+CASE)
def make_bus(): return I2C(0,scl=Pin(WHITE),sda=Pin(YELLOW),freq=400000)

if CASE=="glass":
    from unit import GlassUnit
    i2c=make_bus()
    try: print("GLASS_SCAN",i2c.scan())
    except Exception as e: print("GLASS_SCAN_ERROR",repr(e))
    try: glass=GlassUnit(i2c)
    except Exception as e:
        print("GLASS_INIT_ERROR",repr(e)); raise
    print("GLASS_UNIT_TYPE",type(glass).__name__,hasattr(glass,"display"))
    print(MARKER,CASE); wait_ms(300)
    try:
        # Frozen 2.5.4 glass wrapper may return the composed Display directly
        # (newer source exposes GlassUnit.display); accept both forms.
        d = getattr(glass, "display", glass)
        print("GLASS_API", type(d).__name__, hasattr(d,"fillRect"), hasattr(d,"print"), hasattr(glass,"display"))
        d.fillScreen(0)
        d.fillRect(0,0,64,16,1)
        d.setCursor(2,2); d.print("GLASS")
        print("GLASS_DRAWN")
        try:
            direct=M5.addDisplay(i2c,0x3D,{"unit_glass":True})
            print("GLASS_DIRECT_TYPE",type(direct).__name__ if direct else None)
            if direct and direct is not d:
                direct.fillScreen(0); direct.fillRect(0,0,32,8,1); print("GLASS_DIRECT_DRAWN")
        except Exception as e: print("GLASS_DIRECT_ERROR",repr(e))
        show(screen,"glass")
    except Exception as e: print("GLASS_DRAW_ERROR",repr(e))
    wait_ms(300); print("GLASS_END")

elif CASE in ("lorawan-as923","lorawan-eu868"):
    # The frozen ASR650x wrapper creates UART(1, tx, rx) without a baud
    # argument; pre-configure the same pins/baud as the documented
    # model-ordering workaround, then use the official LoRaWANUnit driver.
    from machine import UART as MUART
    _boot=MUART(1, tx=YELLOW, rx=WHITE, baudrate=115200)
    from unit import LoRaWANUnit
    try: unit=LoRaWANUnit(1,(WHITE,YELLOW))
    except Exception as e:
        print("LORAWAN_INIT_ERROR",repr(e)); raise
    print(MARKER,CASE); wait_ms(300)
    try:
        unit.set_work_mode(1); print("LORAWAN_MODE_SENT")
        unit.send_data("HELLO"); print("LORAWAN_SENT")
        show(screen,"lorawan")
    except Exception as e: print("LORAWAN_ERROR",repr(e))
    print("LORAWAN_END")

elif CASE=="rf433t":
    # No public Unit driver: drive the SYNV115 RF_TX line as a GPIO bitstream.
    from machine import Pin
    p=Pin(YELLOW, Pin.OUT)
    print("RF433T_DRIVER machine.Pin-OUT driver-gap")
    print(MARKER,CASE); wait_ms(300)
    try:
        bits=[1,0,1,0,1,0,1,0]
        for b in bits: p.value(b); wait_ms(20)
        print("RF433T_BITS",''.join(str(b) for b in bits))
        show(screen,"rf433t")
    except Exception as e: print("RF433T_ERROR",repr(e))
    wait_ms(200); print("RF433T_END")

elif CASE=="rf433r":
    # No public Unit driver/decoder: sample the SYN531R RF_RX line as GPIO.
    from machine import Pin
    p=Pin(WHITE, Pin.IN)
    print("RF433R_DRIVER machine.Pin-IN driver-gap")
    print(MARKER,CASE); wait_ms(300)
    try:
        for i in range(10):
            print("RF433R_LEVEL",int(p.value())); wait_ms(200)
        show(screen,"rf433r")
    except Exception as e: print("RF433R_ERROR",repr(e))
    print("RF433R_END")

elif CASE=="audioplayer":
    # No public driver/readable N9301 command table: raw UART byte layer only.
    from machine import UART as MUART
    u=MUART(1, tx=YELLOW, rx=WHITE, baudrate=9600, rxbuf=256)
    print("AUDIO_DRIVER raw-UART driver-gap")
    print(MARKER,CASE); wait_ms(300)
    try:
        frame=bytes.fromhex("7e03010203")
        u.write(frame); wait_ms(500)
        data=u.read() or b""
        print("AUDIO_TX",frame.hex()); print("AUDIO_RX",data.hex())
        show(screen,"audioplayer")
    except Exception as e: print("AUDIO_ERROR",repr(e))
    print("AUDIO_END")

elif CASE=="fingerprint2":
    # No public driver/A-K323CP frame table: raw UART byte layer only.
    from machine import UART as MUART
    u=MUART(1, tx=YELLOW, rx=WHITE, baudrate=115200, rxbuf=256)
    print("FINGERPRINT_DRIVER raw-UART driver-gap")
    print(MARKER,CASE); wait_ms(300)
    try:
        frame=bytes.fromhex("ef01ffffffff010003010005")
        u.write(frame); wait_ms(500)
        data=u.read() or b""
        print("FINGERPRINT_TX",frame.hex()); print("FINGERPRINT_RX",data.hex())
        show(screen,"fingerprint2")
    except Exception as e: print("FINGERPRINT_ERROR",repr(e))
    print("FINGERPRINT_END")

else:
    raise ValueError("unknown batch11 case")
while True:
    M5.update(); time.sleep_ms(200)
