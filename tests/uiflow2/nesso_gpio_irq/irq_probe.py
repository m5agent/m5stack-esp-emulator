"""Real machine.Pin.irq callback probe; invoke helpers from the same guest REPL."""
from machine import Pin, SoftI2C
import time

pin = None
i2c = None
hits = 0
last_level = -1


def _handler(source):
    # Only the firmware's GPIO ISR scheduler calls this. Never call it from
    # the harness, source polling, or a timer.
    global hits, last_level
    hits += 1
    last_level = source.value()


def setup(number=3):
    global pin, i2c, hits, last_level
    if number not in (3, 9):
        raise ValueError("probe supports Nesso GPIO3 or NanoC6 GPIO9")
    if pin is not None:
        pin.irq(handler=None)
    hits = 0
    last_level = -1
    i2c = None
    if number == 3:
        i2c = SoftI2C(scl=Pin(8), sda=Pin(10), freq=100000)
        i2c.writeto_mem(0x43, 0x03, b"\x00")
        i2c.writeto_mem(0x43, 0x09, b"\x03")
        i2c.writeto_mem(0x43, 0x11, b"\x00")
        i2c.readfrom_mem(0x43, 0x13, 1)
    pin = Pin(number, Pin.IN, Pin.PULL_UP)
    pin.irq(handler=None)
    snapshot("READY")


def arm(trigger="falling"):
    modes = {"falling": Pin.IRQ_FALLING, "rising": Pin.IRQ_RISING,
             "both": Pin.IRQ_FALLING | Pin.IRQ_RISING}
    pin.irq(handler=_handler, trigger=modes[trigger])
    snapshot("ARMED_" + trigger)


def disable():
    pin.irq(handler=None)
    snapshot("DISABLED")


def acknowledge_source():
    if i2c is None:
        raise ValueError("GPIO9 requires external button release")
    status = i2c.readfrom_mem(0x43, 0x13, 1)[0]
    print("C6_PIN_SOURCE_ACK status=%02x" % status)
    return status


def snapshot(stage="SNAPSHOT", settle_ms=30):
    # Give MicroPython's scheduled real ISR callback a bounded opportunity to
    # run. Reading a pin here never invokes or increments the callback.
    time.sleep_ms(settle_ms)
    result = (hits, pin.value(), last_level)
    print("C6_PIN_IRQ stage=%s hits=%d level=%d last=%d" % ((stage,) + result))
    return result
