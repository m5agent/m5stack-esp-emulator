import time
import M5
from hardware import UART
from machine import Pin
from unit import ButtonUnit

console = UART(0, baudrate=115200, tx=43, rx=44)
M5.begin()
button = ButtonUnit((1, 2), True, type=2)
signal = Pin(1, Pin.IN, Pin.PULL_UP)
screen = M5.Display
screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Agent Button")
console.write("AGENT_UNIT_READY\r\n")
previous = None
while True:
    M5.update()
    pressed = signal.value() == 0
    if pressed != previous:
        console.write("AGENT_BUTTON pressed=%d\r\n" % int(pressed))
        screen.fillRect(0, 38, screen.width(), 80, 0xFFFFFF)
        screen.setCursor(6, 42)
        screen.print("PRESSED" if pressed else "RELEASED")
        previous = pressed
    time.sleep_ms(100)
