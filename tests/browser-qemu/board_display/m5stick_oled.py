import time
from machine import Pin, SPI

# K016 SH1107 over the board's actual SPI and control pins.
spi = SPI(2, baudrate=1000000, sck=Pin(18), mosi=Pin(23), miso=Pin(19))
cs = Pin(14, Pin.OUT, value=1)
dc = Pin(27, Pin.OUT)
reset = Pin(33, Pin.OUT, value=0)
button = Pin(35, Pin.IN)
reset(1)


def draw(pattern):
    cs(0)
    dc(0)
    spi.write(bytes([0xaf, 0xb0, 0x00, 0x10]))
    dc(1)
    spi.write(bytes([pattern]) * 64)
    cs(1)


draw(0x81)
print("M5STICK_OLED_READY")
previous = button.value()
while True:
    sample = button.value()
    if sample != previous:
        draw(0xff if sample == 0 else 0x81)
        print("M5STICK_OLED_BUTTON", sample)
        previous = sample
    time.sleep_ms(20)
