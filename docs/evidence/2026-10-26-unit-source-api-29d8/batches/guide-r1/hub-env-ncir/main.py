import time
import M5
from hardware import UART
from machine import I2C, Pin
from unit import ENVUnit, NCIRUnit

console = UART(0, baudrate=115200, tx=43, rx=44)
M5.begin()
bus = I2C(0, scl=Pin(1), sda=Pin(2), freq=100000)
env = ENVUnit(i2c=bus, type=3)
ncir = NCIRUnit(bus)
screen = M5.Display
screen.setRotation(1)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
console.write("AGENT_UNIT_READY\r\n")
while True:
    M5.update()
    temperature = env.read_temperature()
    humidity = env.read_humidity()
    pressure_pa = env.read_pressure() * 100
    ambient = ncir.get_ambient_temperature()
    target = ncir.get_object_temperature()
    console.write("AGENT_ENV %.2f %.2f %.2f\r\n" % (temperature, humidity, pressure_pa))
    console.write("AGENT_NCIR %.2f %.2f\r\n" % (ambient, target))
    screen.fillRect(0, 0, screen.width(), 180, 0xFFFFFF)
    screen.setCursor(6, 6)
    screen.print("T %.1f C\nRH %.1f %%\nP %.1f Pa\nIR %.1f C" % (temperature, humidity, pressure_pa, target))
    time.sleep_ms(500)
