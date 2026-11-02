"""Batch-10 a-class guest probes (dcssr/puzzle/dof6/dof9/dof10/asr)."""
import time, sys
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)
MARKER = "BATCH10_PROBE_READY"
def print(*p): _console.write(" ".join(str(x) for x in p) + "\n")
def exc(prefix, e):
    import io
    t=io.StringIO(); sys.print_exception(e,t); print(prefix, t.getvalue().replace("\n"," | "))
def wait_ms(ms):
    start=time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        M5.update(); time.sleep_ms(10)
def show(screen,text):
    screen.setCursor(6,42); screen.print(str(text))
print("BATCH10_PROBE_START", CASE)
M5.begin(); screen=M5.Display
if DEVICE_ID=="cores3": screen.setRotation(1)
screen.setBrightness(255); screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB,0xFFFFFF); screen.setTextSize(2); screen.setCursor(6,6)
screen.print("Batch10 Unit: "+CASE)
def make_bus(): return I2C(0,scl=Pin(WHITE),sda=Pin(YELLOW),freq=100000)

if CASE=="dcssr":
    from unit import DCSSRUnit
    try: unit=DCSSRUnit(make_bus())
    except Exception as e: exc("I2C_DCSSR_INIT_ERROR",e); raise
    print(MARKER,CASE); wait_ms(300)
    try:
        unit.on(); print("I2C_DCSSR_ON",unit.value())
        unit.off(); print("I2C_DCSSR_OFF",unit.value())
        unit.on(); print("I2C_DCSSR_ON2",unit.value())
        unit.fill_color(0x112233); print("I2C_DCSSR_RGB")
        print("I2C_DCSSR_FW",unit.get_firmware_version())
        show(screen,"dcssr")
    except Exception as e: exc("I2C_DCSSR_ERROR",e)
    print("I2C_DCSSR_END")

elif CASE=="puzzle":
    # Public UIFlow2 has no unit/puzzle.py; generic RGBUnit/SK6812 is the
    # executable reference path (explicit driver-gap, 64 LEDs).
    from unit import RGBUnit
    try: unit=RGBUnit((WHITE,YELLOW),64)
    except Exception as e: exc("GPIO_PUZZLE_INIT_ERROR",e); raise
    print("GPIO_PUZZLE_DRIVER generic-SK6812-64")
    print(MARKER,CASE); wait_ms(300)
    try:
        unit.fill_color(0x112233); print("GPIO_PUZZLE_WRITTEN")
        show(screen,"puzzle 64")
    except Exception as e: exc("GPIO_PUZZLE_ERROR",e)
    wait_ms(300); print("GPIO_PUZZLE_END")

elif CASE in ("dof6","dof9","dof10"):
    # No Unit-specific DoF driver exists; the frozen generic BMI270 driver
    # exercises the modeled BMI270 subset only. BMM350/SPA06 are NOT modeled.
    from driver.bmi270_bmm150 import BMI270
    try: imu=BMI270(make_bus(), address=0x68)
    except Exception as e: exc("I2C_IMU_INIT_ERROR",e); raise
    print(MARKER,CASE); wait_ms(300)
    try:
        print("I2C_IMU_ACCEL",imu.accel())
        print("I2C_IMU_GYRO",imu.gyro())
        print("I2C_IMU_TEMP",imu.temperature())
        print("I2C_IMU_BLOCKED", "bmm350" if CASE=="dof9" else ("bmm350,spa06" if CASE=="dof10" else ""))
        show(screen,CASE)
    except Exception as e: exc("I2C_IMU_ERROR",e)
    print("I2C_IMU_END")

elif CASE=="asr":
    # No public unit/asr.py driver; page documents AA55 frames. Send the
    # version command (0x45) as a byte-layer frame and read the fixture reply.
    from machine import UART as MUART
    try: uart=MUART(1,tx=YELLOW,rx=WHITE,baudrate=115200,rxbuf=256)
    except Exception as e: exc("UART_ASR_INIT_ERROR",e); raise
    print(MARKER,CASE); wait_ms(300)
    try:
        frame=bytes([0xAA,0x55,0x45,0x55,0xAA])
        uart.write(frame); wait_ms(500)
        data=uart.read() or b""
        print("UART_ASR_TX",frame.hex())
        print("UART_ASR_RX",data.hex())
        show(screen,"asr")
    except Exception as e: exc("UART_ASR_ERROR",e)
    print("UART_ASR_END")
else:
    raise ValueError("unknown case")
while True:
    M5.update(); time.sleep_ms(200)
