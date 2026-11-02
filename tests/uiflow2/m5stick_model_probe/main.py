# Device-local model fixture for the M5Stick (K016) machine.
#
# This runs on the generic classic-ESP32 UIFlow2 image (Atom Lite build) only to
# exercise the m5stick board models through the guest controllers: the shared
# G21/G22 I2C bus (MPU9250 0x68, IP5306 0x75) and the GPIO35 custom button.
# It is NOT the M5Stick factory firmware and does not claim UIFlow2 support for
# this board; the factory-firmware boot path is documented separately.
import time
from machine import I2C, Pin

print("M5STICK_PROBE_START")
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
print("M5STICK_I2C_SCAN", [hex(addr) for addr in i2c.scan()])
print("M5STICK_MPU_WHO", hex(i2c.readfrom_mem(0x68, 0x75, 1)[0]))
raw = i2c.readfrom_mem(0x68, 0x3B, 6)
print("M5STICK_MPU_ACCEL_HEX", raw.hex())
print("M5STICK_IP5306_SYS", hex(i2c.readfrom_mem(0x75, 0x00, 1)[0]))
print("M5STICK_IP5306_READ4", hex(i2c.readfrom_mem(0x75, 0x78, 1)[0]))

button = Pin(35, Pin.IN)
state = button.value()
print("M5STICK_BUTTON", state)
print("M5STICK_PROBE_READY")

last_button = state
last_accel = None
while True:
    value = button.value()
    if value != last_button:
        print("M5STICK_BUTTON_STATE", value)
        last_button = value
    accel = i2c.readfrom_mem(0x68, 0x3B, 2)
    ax = int.from_bytes(accel, "big", True)
    if last_accel is None or abs(ax - last_accel) > 100:
        print("M5STICK_MPU_ACCEL_X", ax)
        last_accel = ax
    time.sleep_ms(20)
