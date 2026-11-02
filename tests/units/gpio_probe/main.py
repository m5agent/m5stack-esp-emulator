"""Guest probes for the first A-class Unit batch (ssr/earth/hall/reflective-ir/vibrator).

Runs the reference UIFlow2 firmware's frozen original Unit drivers; no host
value is injected into a driver return path. The Device Service captures UART0
markers and QOM state, and injects external fixture values through unit-input.
"""

import time
import sys
import M5
from hardware import UART
from machine import Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

# UIFlow2's print console can be USB CDC. The service captures the guest UART.
_console = UART(0, baudrate=115200, tx=43, rx=44)


def print(*parts):
    _console.write(" ".join(str(part) for part in parts) + "\n")


print("GPIO_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("GPIO Unit: " + CASE)

port = (WHITE, YELLOW)


def show(text):
    screen.fillRect(0, 38, screen.width(), 150, 0xFFFFFF)
    screen.setCursor(6, 42)
    screen.print(str(text))


def wait_ms(duration):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration:
        M5.update()
        time.sleep_ms(10)


def emit_exception(prefix, error):
    """Report a guest driver exception over the captured UART, not USB CDC."""
    import io

    trace = io.StringIO()
    sys.print_exception(error, trace)
    print(prefix, trace.getvalue().replace("\n", " | "))


if CASE == "ssr":
    from unit import SSRUnit

    unit = SSRUnit(port)
    print("GPIO_PROBE_READY", CASE)
    unit.on()
    print("GPIO_SSR_STATE", 1)
    show("on()")
    wait_ms(2500)
    unit.off()
    print("GPIO_SSR_STATE", 0)
    show("off()")
    wait_ms(2500)
    unit.set_state(1)
    print("GPIO_SSR_STATE", 1)
    show("set_state(1)")
    wait_ms(2500)
    unit.off()
    print("GPIO_SSR_STATE", 0)
    show("off()")
    print("GPIO_SSR_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "vibrator":
    from unit import VibratorUnit

    unit = VibratorUnit(port)
    print("GPIO_PROBE_READY", CASE)
    unit.set_freq(4000)
    unit.set_duty(50)
    print("GPIO_VIB_STATE", 4000, 50)
    show("set_duty(50)")
    wait_ms(2500)
    unit.set_duty(25)
    print("GPIO_VIB_STATE", 4000, 25)
    show("set_duty(25)")
    wait_ms(2500)
    unit.turn_off()
    print("GPIO_VIB_STATE", 4000, 0)
    show("turn_off()")
    wait_ms(1500)
    unit.once(freq=2000, duty=60, duration=300)
    print("GPIO_VIB_ONCE", 2000, 60, 300)
    show("once()")
    wait_ms(1500)
    print("GPIO_VIB_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "earth":
    from unit import EarthUnit

    unit = EarthUnit(port)
    print("GPIO_PROBE_READY", CASE)
    print("GPIO_EARTH_LOOP")
    while True:
        try:
            raw = unit.get_analog_value()
            digital = unit.get_digital_value()
            print("GPIO_EARTH", raw, int(digital))
            show("raw=%d d=%d" % (raw, digital))
            try:
                mv = unit.get_voltage_mv()
                humidity = unit.humidity()
                print("GPIO_EARTH_UV", mv, round(humidity, 4))
            except OSError as error:
                print("GPIO_EARTH_UV_UNSUPPORTED", repr(error))
        except Exception as error:
            emit_exception("GPIO_EARTH_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(120)

elif CASE == "reflective-ir":
    from unit import ReflectiveIRUnit

    unit = ReflectiveIRUnit(port)
    events = [0, 0]

    def handle_event(trigger):
        events[trigger] += 1
        print("GPIO_RIR_EVENT", trigger, events[trigger])

    unit.set_callback(lambda unit_arg: handle_event(0), 0)
    unit.set_callback(lambda unit_arg: handle_event(1), 1)
    unit.enable_irq()
    print("GPIO_PROBE_READY", CASE)
    print("GPIO_RIR_LOOP")
    while True:
        try:
            raw = unit.get_analog_value()
            digital = unit.get_digital_value()
            print("GPIO_RIR", raw, int(digital))
            show("raw=%d d=%d" % (raw, digital))
        except Exception as error:
            emit_exception("GPIO_RIR_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(120)

elif CASE == "hall":
    from unit import HallEffectUnit

    unit = HallEffectUnit(port)
    events = {"active": 0, "negative": 0}

    def active_event(unit_arg):
        events["active"] += 1
        print("GPIO_HALL_EVENT", "active", events["active"])

    def negative_event(unit_arg):
        events["negative"] += 1
        print("GPIO_HALL_EVENT", "negative", events["negative"])

    unit.set_callback(active_event, unit.IRQ_ACTIVE)
    unit.set_callback(negative_event, unit.IRQ_NEGATIVE)
    unit.enable_irq()
    print("GPIO_PROBE_READY", CASE)
    print("GPIO_HALL_LOOP")
    while True:
        try:
            status = unit.get_status()
            print("GPIO_HALL", int(status))
            show("status=%d" % status)
        except Exception as error:
            emit_exception("GPIO_HALL_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(120)

else:
    raise ValueError("unknown gpio probe case")
