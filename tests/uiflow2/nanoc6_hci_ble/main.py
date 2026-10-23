"""NanoC6 board peripherals and UART1 HCI BLE in one C6 guest."""

import M5
import machine
import time
from hardware import IR, RGB


print("NANOC6_HCI_MAIN")
M5.begin()
print("NANOC6_HCI_BOARD", M5.getBoard())

rgb_power = machine.Pin(19, machine.Pin.OUT)
rgb_power.value(1)
rgb = RGB()
rgb.set_brightness(100)
rgb.set_color(0, 0x00FF00)
print("NANOC6_HCI_RGB 1 00FF00")

blue = machine.Pin(7, machine.Pin.OUT)
blue.value(1)
print("NANOC6_HCI_BLUE 1")

ir = IR()
ir.tx(0x56, 0xA3)
print("NANOC6_HCI_IR 0x56 0xA3")

button = machine.Pin(9, machine.Pin.IN, machine.Pin.PULL_UP)
print("NANOC6_HCI_BUTTON_READY")

from bleuart import BLEUARTServer

server = BLEUARTServer(name="M5-NANOC6-HCI", verbose=True)


def on_receive():
    payload = bytes(server.read())
    print("NANOC6_HCI_BLE_RX", payload)
    server.write(b"ACK:" + payload)
    print("NANOC6_HCI_BLE_ACK_SENT")


server.irq(on_receive)
print("NANOC6_HCI_BLE_READY")
print("NANOC6_HCI_READY")

button_seen = False
while True:
    M5.update()
    value = button.value()
    if not button_seen and value == 0:
        button_seen = True
        print("NANOC6_HCI_BUTTON_PRESS")
    elif button_seen and value == 1:
        button_seen = False
        blue.value(0)
        print("NANOC6_HCI_BUTTON_RELEASE")
        print("NANOC6_HCI_BLUE 0")
    time.sleep_ms(20)
