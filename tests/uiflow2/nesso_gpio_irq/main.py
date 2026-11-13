"""Original Nesso UIFlow machine.Pin.irq, driven by actual board inputs."""
import M5
import time
import irq_probe as probe

M5.begin()
display = M5.Display
display.fillScreen(0)
display.setTextColor(0xFFFFFF)
display.setTextSize(1)
display.setCursor(4, 18)
display.print("Nesso GPIO IRQ")
probe.setup(3)
checks = []


def marker(stage):
    print("NESSO_GPIO_IRQ_WAIT " + stage)


def wait_for(predicate):
    start = time.ticks_ms()
    while not predicate():
        if time.ticks_diff(time.ticks_ms(), start) > 15000:
            raise RuntimeError("actual board input timed out")
        time.sleep_ms(10)


def observe(name, before, delta, level):
    # Pin/I2C reads only synchronize and observe the external source. The real
    # Pin.irq handler in irq_probe is the sole incrementer of probe.hits.
    time.sleep_ms(100)
    actual = probe.hits
    actual_level = probe.pin.value()
    passed = actual - before == delta and actual_level == level
    checks.append(passed)
    print("NESSO_GPIO_IRQ_CHECK %s pass=%d hits=%d delta=%d expected=%d level=%d" %
          (name, passed, actual, actual - before, delta, actual_level))
    return actual


def press(stage):
    marker(stage)
    wait_for(lambda: probe.pin.value() == 0)


def release(stage):
    marker(stage)
    wait_for(lambda: probe.i2c.readfrom_mem(0x43, 0x0F, 1)[0] & 1)
    probe.acknowledge_source()
    wait_for(lambda: probe.pin.value() == 1)


try:
    print("NESSO_GPIO_IRQ_READY pin=3 hits=%d" % probe.hits)
    before = probe.hits
    probe.disable()
    press("DISABLED_DOWN")
    after = observe("disabled_press", before, 0, 0)
    release("DISABLED_UP")
    observe("disabled_release", after, 0, 1)

    for mode in ("falling", "rising", "both"):
        probe.arm(mode)
        before = probe.hits
        press(mode.upper() + "_DOWN")
        after = observe(mode + "_press", before, 0 if mode == "rising" else 1, 0)
        observe(mode + "_held_quiet", after, 0, 0)
        release(mode.upper() + "_UP")
        observe(mode + "_release", after, 1 if mode in ("rising", "both") else 0, 1)
        probe.disable()

    probe.arm("both")
    before = probe.hits
    press("SHARED_BUTTON_DOWN")
    after = observe("shared_button", before, 1, 0)
    marker("SHARED_TOUCH")
    wait_for(lambda: probe.i2c.readfrom_mem(0x38, 0x02, 1)[0] & 0x0F)
    observe("shared_touch_keeps_low", after, 0, 0)
    probe.acknowledge_source()
    observe("shared_button_ack_keeps_touch", after, 0, 0)
    print("NESSO_GPIO_IRQ_SHARED_ACK_HELD")
    wait_for(lambda: probe.pin.value() == 1)
    released = observe("shared_last_release", after, 1, 1)
    release("SHARED_BUTTON_UP")
    observe("shared_button_release_quiet", released, 0, 1)
    probe.disable()

    passed = all(checks)
    display.fillRect(0, 0, 135, 8, 0x00FF00 if passed else 0xFF0000)
    display.setCursor(4, 45)
    display.print("PASS" if passed else "FAIL")
    print("NESSO_GPIO_IRQ_DONE %s checks=%d passed=%d" %
          ("PASS" if passed else "FAIL", len(checks), sum(checks)))
except Exception as error:
    display.fillRect(0, 0, 135, 8, 0xFF0000)
    print("NESSO_GPIO_IRQ_EXCEPTION", repr(error))
    print("NESSO_GPIO_IRQ_DONE FAIL incomplete")

while True:
    # No M5.update(): it could acknowledge the shared source before the probe.
    time.sleep_ms(100)
