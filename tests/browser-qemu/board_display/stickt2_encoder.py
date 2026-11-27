import time
from machine import I2C, Pin, SPI

bus = I2C(0, scl=Pin(22), sda=Pin(21))
spi = SPI(2, baudrate=10000000, sck=Pin(13), miso=Pin(14), mosi=Pin(15))
cs = Pin(5, Pin.OUT, value=1)
dc = Pin(23, Pin.OUT)
reset = Pin(18, Pin.OUT, value=0)
buttons = [Pin(37, Pin.IN), Pin(39, Pin.IN)]
reset(1)


def write(command, data=b""):
    cs(0)
    dc(0)
    spi.write(bytes([command]))
    if data:
        dc(1)
        spi.write(data)
    cs(1)


def draw(color):
    write(0x2a, bytes([0, 52, 0, 67]))
    write(0x2b, bytes([0, 40, 0, 55]))
    write(0x2c, color * 256)


write(0x11)
write(0x29)
draw(b"\xf8\x00")
print("STICKT2_BROWSER_READY")
previous = 0, 0, 1, 1
while True:
    step = int.from_bytes(bus.readfrom_mem(0x30, 0, 2), "big")
    if step >= 0x8000:
        step -= 0x10000
    state = (step, bus.readfrom_mem(0x30, 0x10, 1)[0], buttons[0].value(), buttons[1].value())
    if state != previous:
        draw(b"\x07\xe0" if state != (0, 0, 1, 1) else b"\xf8\x00")
        print("STICKT2_BROWSER_INPUT", *state)
        previous = state
    time.sleep_ms(20)
