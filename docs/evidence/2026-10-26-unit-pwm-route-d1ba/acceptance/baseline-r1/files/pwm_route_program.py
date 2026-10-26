import time
import M5
from machine import Pin, PWM
from probe_logging import emit
from probe_config import PWM_GPIO, PWM_FREQUENCY_HZ, HOLD_MS, HEARTBEAT_MS

M5.begin()
screen = M5.Display
screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("PWM initial route\nNo post-init setter")
pwm = PWM(Pin(PWM_GPIO), freq=PWM_FREQUENCY_HZ, duty_u16=0)
started = time.ticks_ms()
emit("PWMR_READY")
sample = 0
last = started - HEARTBEAT_MS
while time.ticks_diff(time.ticks_ms(), started) < HOLD_MS:
    M5.update()
    current = time.ticks_ms()
    elapsed = time.ticks_diff(current, started)
    if time.ticks_diff(current, last) >= HEARTBEAT_MS:
        frequency = pwm.freq()
        duty = pwm.duty_u16()
        emit("PWMR_HOLD", sample, elapsed, frequency, duty)
        if sample % 4 == 0:
            screen.fillRect(0, 58, 320, 130, 0xFFFFFF)
            screen.setCursor(6, 62)
            screen.print("INIT HOLD\nget %d Hz\nduty_u16 %d\nsample %d" % (frequency, duty, sample))
        sample += 1
        last = current
    time.sleep_ms(10)
emit("PWMR_HOLD_DONE")
while True:
    M5.update()
    time.sleep_ms(50)
