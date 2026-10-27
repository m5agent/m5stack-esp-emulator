# Cardputer-ADV local UI and keyboard test for QEMU
import M5
import time
import machine
from hardware import KeyboardI2C

i2c = machine.I2C(1, scl=machine.Pin(9), sda=machine.Pin(8), freq=400000)
intr = machine.Pin(11, mode=machine.Pin.IN, pull=None)
keyboard = KeyboardI2C(i2c, intr_pin=intr, mode=KeyboardI2C.ASCII_MODE)
count = 0


def draw_ui():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.drawRect(3, 3, 233, 128, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(12, 12)
    d.print("Cardputer-ADV")
    d.setTextColor(d.COLOR.GREEN)
    d.setCursor(12, 48)
    d.print("keys: %d" % count)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(1)
    d.setCursor(12, 85)
    d.print("Press any key")
    d.fillRect(12, 102, 216, 22, d.COLOR.BLUE)
    d.setCursor(65, 108)
    d.print("KEYBOARD TEST")
    if count:
        d.fillRect(1, 1, 4, 4, d.COLOR.GREEN)


print("CARDPUTER_ADV_MAIN_START")
M5.begin()
print("CARDPUTER_ADV_BOARD", M5.getBoard())
print("CARDPUTER_ADV_DISPLAY", M5.Display.width(), M5.Display.height())
M5.Display.setBrightness(255)
draw_ui()

while True:
    M5.update()
    # GPIO matrix interrupts are not modelled yet; poll the TCA8418 event
    # queue through the same handler used by the hardware IRQ path.
    keyboard._irq_handler(intr)
    while keyboard._keyevents:
        keyevent = keyboard._keyevents.pop(0)
        count += 1
        print("CARDPUTER_ADV_KEY", keyevent.keycode, count)
        draw_ui()
    time.sleep(0.02)
