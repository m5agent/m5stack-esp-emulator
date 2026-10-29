import M5
import time

print("STICKCPLUS2_MAIN_START")
M5.begin()
print("STICKCPLUS2_M5_BEGIN_OK")
print("STICKCPLUS2_BOARD", M5.getBoard())
M5.Display.setRotation(0)
M5.Display.setBrightness(255)
print("STICKCPLUS2_DISPLAY", M5.Display.width(), M5.Display.height())

display = M5.Display
display.fillScreen(0x000000)
display.drawRect(0, 0, 135, 240, 0x00FFFF)
display.fillRect(8, 40, 35, 20, 0xFF0000)
display.fillRect(50, 40, 35, 20, 0x00FF00)
display.fillRect(92, 40, 35, 20, 0x0000FF)
display.setTextColor(0xFFFFFF)
display.setTextSize(1)
display.setCursor(8, 12)
display.print("StickC Plus2")
display.setCursor(8, 80)
display.print("A / B / PWR")

buttons = (M5.BtnA, M5.BtnB, M5.BtnPWR)
labels = ("A", "B", "PWR")
colors = (0x00FF00, 0x0000FF, 0xFFFFFF)
was_pressed = [False, False, False]
counts = [0, 0, 0]
print("STICKCPLUS2_FRAME_READY")

while True:
    M5.update()
    for index in range(3):
        pressed = buttons[index].isPressed()
        if pressed and not was_pressed[index]:
            counts[index] += 1
            print("STICKCPLUS2_BTN_%s" % labels[index], counts[index])
            display.fillRect(8 + 42 * index, 110, 35, 35, colors[index])
            if index == 0:
                display.fillRect(1, 1, 5, 5, 0x00FF00)
        was_pressed[index] = pressed
    time.sleep_ms(20)
