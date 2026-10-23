"""Nesso N1 board peripherals and UART1 HCI BLE in one C6 guest."""

import M5
import machine
import time
from M5 import *
from hardware import IR
from lora import SX1262
from machine import Pin, SoftI2C


BLE_NAME = "M5-NESSO-UNIFIED"
EXPECTED_POWER = (100, 4300, 1)
EXPECTED_ACCEL = (0.25, -0.50, 0.75)
EXPECTED_GYRO = (10.0, -20.0, 30.0)

touch_count = 0
last_touch = (-1, -1)
button_seen = False
last_draw = (0, 0, 0)


def draw_state(status):
    display = M5.Display
    display.fillScreen(display.COLOR.BLACK)
    display.drawRect(2, 2, 131, 236, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.WHITE)
    display.setTextSize(2)
    display.setCursor(8, 10)
    display.print("Nesso unified")
    display.setTextSize(1)
    display.setCursor(8, 38)
    display.print("touch=%d button=%d" % (touch_count, int(button_seen)))
    display.setCursor(8, 54)
    display.print("last=%d,%d" % last_touch)
    display.setCursor(8, 72)
    display.print("LoRa/IR/buzz/RGB")
    display.setCursor(8, 90)
    display.print("BLE:%s" % status)
    display.fillRect(18, 150, 99, 54, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.WHITE)
    display.setTextSize(2)
    display.setCursor(42, 168)
    display.print("TOUCH")
    if touch_count:
        display.fillRect(1, 1, 5, 5, display.COLOR.GREEN)


def wait_power(timeout_ms=8000):
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    value = (0, 0, 0)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        value = (
            Power.getBatteryLevel(),
            Power.getBatteryVoltage(),
            1 if Power.isCharging() else 0,
        )
        if value == EXPECTED_POWER:
            return value
        time.sleep_ms(50)
    raise RuntimeError("power timeout %r" % (value,))


def wait_imu(timeout_ms=8000):
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    accel = (0, 0, 0)
    gyro = (0, 0, 0)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        try:
            accel = Imu.getAccel()
            gyro = Imu.getGyro()
        except Exception:
            time.sleep_ms(50)
            continue
        accel_ok = all(
            abs(accel[index] - EXPECTED_ACCEL[index]) < 0.05
            for index in range(3)
        )
        gyro_ok = all(
            abs(gyro[index] - EXPECTED_GYRO[index]) < 1.0
            for index in range(3)
        )
        if accel_ok and gyro_ok:
            return accel, gyro
        time.sleep_ms(50)
    raise RuntimeError("imu timeout %r %r" % (accel, gyro))


print("UNIFIED_NESSO_MAIN")
M5.begin()
print("UNIFIED_NESSO_BOARD", M5.getBoard())
print("UNIFIED_NESSO_DISPLAY", M5.Display.width(), M5.Display.height())
M5.Display.setRotation(0)
M5.Display.setBrightness(255)
draw_state("init")

i2c = SoftI2C(scl=Pin(8), sda=Pin(10), freq=400000)

# External power, radio switch/LNA and SX1262 reset rails.
i2c.writeto_mem(0x44, 0x03, b"\xfb")
i2c.writeto_mem(0x44, 0x07, b"\x00")
i2c.writeto_mem(0x44, 0x05, b"\x04")
i2c.writeto_mem(0x43, 0x03, b"\x1f")
i2c.writeto_mem(0x43, 0x07, b"\x00")
i2c.writeto_mem(0x43, 0x05, b"\x60")
time.sleep_ms(100)
i2c.writeto_mem(0x43, 0x05, b"\xe0")
e1_out = i2c.readfrom_mem(0x44, 0x05, 1)[0]
e0_out = i2c.readfrom_mem(0x43, 0x05, 1)[0]
print("UNIFIED_NESSO_IO_CONFIG_READY", e1_out, e0_out)

level, voltage, charging = wait_power()
print("UNIFIED_NESSO_POWER", level, voltage, charging)

accel, gyro = wait_imu()
print(
    "UNIFIED_NESSO_IMU",
    "%.2f %.2f %.2f" % accel,
    "%.1f %.1f %.1f" % gyro,
)

spi = machine.SoftSPI(
    baudrate=1000000,
    polarity=0,
    phase=0,
    sck=Pin(20),
    mosi=Pin(21),
    miso=Pin(22),
)
radio = SX1262(
    spi=spi,
    cs=Pin(23),
    busy=Pin(19),
    dio1=Pin(15),
    dio3_tcxo_millivolts=3300,
    lora_cfg={
        "freq_khz": 868000,
        "sf": 7,
        "bw": "125",
        "coding_rate": 5,
        "syncword": 0x12,
        "preamble_len": 12,
        "output_power": 10,
    },
)
radio.send("M5LORA")
radio.start_recv()
rx = radio.recv(timeout_ms=2000)
packet = bytes(rx) if rx else b""
if packet != b"M5LORA":
    raise RuntimeError("LoRa loopback mismatch: %r" % packet)
print("UNIFIED_NESSO_LORA", packet.decode())

IR().tx(0x56, 0xA3)
print("UNIFIED_NESSO_IR 0x56 0xA3")

if not Speaker.begin():
    raise RuntimeError("speaker begin failed")
Speaker.setVolume(255)
Speaker.tone(3500, 1200)
time.sleep_ms(100)
if not Speaker.isPlaying():
    raise RuntimeError("buzzer not playing")
print("UNIFIED_NESSO_BUZZER 3500")

from bleuart import BLEUARTServer

server = BLEUARTServer(name=BLE_NAME, verbose=True)


def on_receive():
    payload = bytes(server.read())
    print("UNIFIED_NESSO_BLE_RX", payload)
    server.write(b"ACK:" + payload)
    print("UNIFIED_NESSO_BLE_ACK_SENT")


server.irq(on_receive)
print("UNIFIED_NESSO_BLE_READY")
draw_state("ready")
print("UNIFIED_NESSO_READY")

was_pressed = False
while True:
    M5.update()
    pressed = M5.Touch.getCount() > 0
    if pressed:
        x = M5.Touch.getX()
        y = M5.Touch.getY()
        if not was_pressed:
            touch_count += 1
            last_touch = (x, y)
            print("UNIFIED_NESSO_TOUCH", x, y, touch_count)
    was_pressed = pressed

    if not button_seen:
        irq = i2c.readfrom_mem(0x43, 0x13, 1)[0]
        if irq & 0x01:
            button_seen = True
            print("UNIFIED_NESSO_BUTTON 1")

    state = (touch_count, int(button_seen), last_touch[0])
    if state != last_draw:
        last_draw = state
        draw_state("ready")
    time.sleep_ms(20)
