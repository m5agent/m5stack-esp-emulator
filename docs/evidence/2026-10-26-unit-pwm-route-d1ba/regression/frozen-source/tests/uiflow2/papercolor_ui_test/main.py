# PaperColor local UI and key test for QEMU
import M5
import time
import machine

count = 0
key_a = machine.Pin(10, mode=machine.Pin.IN, pull=machine.Pin.PULL_UP)


def draw_ui():
    d = M5.Display
    d.fillScreen(d.COLOR.WHITE)
    d.drawRect(6, 6, 387, 587, d.COLOR.BLACK)
    d.setTextColor(d.COLOR.BLACK)
    d.setTextSize(3)
    d.setCursor(26, 30)
    d.print("PaperColor")
    d.setTextSize(1)
    d.setCursor(28, 70)
    d.print("UIFlow2 QEMU 400x600")
    d.setTextColor(d.COLOR.RED)
    d.setTextSize(4)
    d.setCursor(28, 145)
    d.print("keys: %d" % count)
    d.setTextColor(d.COLOR.BLUE)
    d.setTextSize(2)
    d.setCursor(28, 225)
    d.print("Press front key A")
    d.fillRect(50, 450, 300, 80, d.COLOR.GREEN)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(116, 478)
    d.print("COLOR TEST")


def draw_key_state():
    d = M5.Display
    d.fillRect(28, 140, 252, 58, d.COLOR.WHITE)
    d.setTextColor(d.COLOR.RED)
    d.setTextSize(4)
    d.setCursor(28, 145)
    d.print("keys: %d" % count)
    d.fillRect(260, 150, 20, 20, d.COLOR.BLACK)


print("PAPERCOLOR_MAIN_START")
M5.begin()
print("PAPERCOLOR_BOARD", M5.getBoard())
print("PAPERCOLOR_DISPLAY", M5.Display.width(), M5.Display.height())
M5.Display.setRotation(0)
draw_ui()

was = False
while True:
    M5.update()
    pressed = not key_a.value()
    if pressed and not was:
        count += 1
        print("PAPERCOLOR_BTN_A", count)
        draw_key_state()
    was = pressed
    time.sleep(0.05)
