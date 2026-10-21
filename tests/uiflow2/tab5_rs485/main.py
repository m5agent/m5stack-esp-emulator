# Tab5 SIT3088 RS-485 probe through the official PWR485 API.
import M5
import machine
import time
from M5 import *


def draw(ok, detail):
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.drawRect(12, 12, d.width() - 24, d.height() - 24, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(5)
    d.setCursor(48, 48)
    d.print("Tab5 RS-485")
    d.setTextSize(3)
    d.setCursor(48, 140)
    d.print(detail[:54])
    d.fillRect(48, 240, 480, 80, d.COLOR.GREEN if ok else d.COLOR.RED)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(4)
    d.setCursor(64, 258)
    d.print("PASS" if ok else "FAIL")


M5.begin()
M5.Display.setRotation(1)
M5.Display.setBrightness(255)
draw(False, "waiting for peer")

request = b"TAB5_RS485_PING"
response = b"TAB5_RS485_PONG"
received = b""
error = None
written = 0

try:
    uart = machine.UART(
        1,
        baudrate=115200,
        tx=20,
        rx=21,
        rts=34,
        mode=machine.UART.MODE_RS485_HALF_DUPLEX,
        rxbuf=256,
        timeout=2000,
    )
    written = uart.write(request)
    deadline = time.ticks_add(time.ticks_ms(), 8000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        chunk = uart.read(64)
        if chunk:
            received += chunk
            if response in received:
                break
        time.sleep_ms(20)
except Exception as exc:
    error = exc

ok = written == len(request) and response in received
if error:
    detail = repr(error)
else:
    detail = "tx=%d rx=%s" % (written, received.hex())
print("TAB5_RS485_TX", written, request.hex())
print("TAB5_RS485_RX", received.hex())
if error:
    print("TAB5_RS485_ERROR", repr(error))
draw(ok, detail)
print("TAB5_RS485_DONE", "PASS" if ok else "FAIL")

touches = 0
was_pressed = False
while True:
    M5.update()
    pressed = M5.Touch.getCount() > 0
    if pressed and not was_pressed:
        touches += 1
        draw(ok, "tx=%d rx=%d touch=%d" % (written, len(received), touches))
        print("TAB5_DRAW_AFTER_TOUCH", touches)
    was_pressed = pressed
    time.sleep_ms(100)
