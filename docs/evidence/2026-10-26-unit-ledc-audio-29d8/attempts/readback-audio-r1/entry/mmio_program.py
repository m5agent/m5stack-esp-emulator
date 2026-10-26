import time
import M5
from machine import Pin, PWM, UART, mem32

console = UART(0, baudrate=115200, tx=43, rx=44)


def emit(*parts):
    console.write(" ".join(str(part) for part in parts) + "\r\n")


def pause(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        M5.update()
        time.sleep_ms(10)


M5.begin()
screen = M5.Display
screen.setRotation(1)
screen.setFont(screen.FONTS.Montserrat12)
screen.setTextSize(1)
screen.setBrightness(255)
pwm = PWM(Pin(2), freq=2000, duty_u16=0)
emit("LEDC_DIAG_READY")
phases = (("zero", 0), ("quarter", 16384), ("half", 32768),
          ("three_quarters", 49152), ("full", 65535), ("off", 0))
for phase, (label, requested) in enumerate(phases):
    pwm.duty_u16(requested)
    pause(300)
    emit("LEDC_DIAG_PHASE", phase, label, requested)
    for sample in range(10):
        getter = pwm.duty_u16()
        route = mem32[0x6000455C]
        emit("LEDC_DIAG_SAMPLE", phase, sample, requested, getter, route, repr(pwm))
        emit("LEDC_DIAG_GLOBAL", phase, sample, mem32[0x600190D0])
        for timer in range(4):
            emit("LEDC_DIAG_TIMER", phase, sample, timer, mem32[0x600190A0 + timer * 8])
        for channel in range(8):
            address = 0x60019000 + channel * 0x14
            emit("LEDC_DIAG_RAW", phase, sample, channel,
                 mem32[address], mem32[address + 4], mem32[address + 8],
                 mem32[address + 12], mem32[address + 16])
        screen.fillScreen(0xFFFFFF)
        screen.setTextColor(0x0282CB, 0xFFFFFF)
        screen.setCursor(6, 6)
        screen.print("LEDC MMIO diagnostic\n" + label + "\nrequested " + str(requested) +
                     "\ngetter " + str(getter) + "\nGPIO2 route " + str(route))
        pause(700)
emit("LEDC_DIAG_DONE")
while True:
    M5.update()
    time.sleep_ms(50)
