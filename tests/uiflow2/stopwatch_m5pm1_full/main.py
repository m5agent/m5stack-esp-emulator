import M5
import time
from M5 import *
from machine import I2C, Pin


M5.begin()
log_uart = None
try:
    from hardware import UART
    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    pass


def emit(*parts):
    if log_uart:
        log_uart.write(" ".join(str(part) for part in parts) + "\n")


d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(45, 70)
d.print("StopWatch M5PM1 full")

ok = False
detail = "init"
try:
    from m5pm1 import M5PM1
    i2c = I2C(1, scl=Pin(48), sda=Pin(47), freq=100000)
    pmic = M5PM1(i2c, addr=0x6E)
    cfg_before = pmic.read_reg(0x49)
    pmic.disable_single_click_reset()
    cfg_after = pmic.read_reg(0x49)
    emit("STOPWATCH_M5PM1_BUTTON_CFG", hex(cfg_before), hex(cfg_after),
         "irq", hex(pmic.get_irq_status("button")),
         "status", hex(pmic.read_reg(0x48)))
    if cfg_after != cfg_before | 1:
        raise RuntimeError("PM1 single-click IRQ mode readback mismatch")
    info = pmic.get_device_info()
    uid = pmic.get_uid()

    pmic.enable_charging()
    pmic.enable_dcdc()
    pmic.enable_ldo()
    pmic.enable_boost()
    power_cfg = pmic.get_power_config()
    pmic.set_battery_low_voltage_threshold_mv(3200)
    lvp = pmic.get_battery_low_voltage_threshold_mv()

    pmic.set_pin_mode(0, pmic.GPIO_MODE_OUT)
    pmic.set_pin_drive(0, pmic.DRIVE_PUSH_PULL)
    pmic.set_pin_value(0, 1)
    gp0 = pmic.read_pin(0)
    pmic.set_pin_mode(1, pmic.GPIO_MODE_IN)
    pmic.set_pin_pull(1, pmic.GPIO_PULL_UP)

    pmic.set_pwm_frequency(1000)
    pmic.set_pwm_duty_u12(0, 2048)
    pmic.enable_pwm(0)
    pwm_freq = pmic.get_pwm_frequency()
    pwm_duty = pmic.get_pwm_duty_u12(0)

    pmic.set_neopixel_count(2)
    pmic.set_neopixel_color(0, 0xFF0000)
    pmic.set_neopixel_color(1, 0x00FF00)
    neo0 = pmic.read_reg16(0x60)
    neo1 = pmic.read_reg16(0x62)

    pmic.set_i2c_sleep_timeout_s(3)
    i2c_sleep = pmic.get_i2c_sleep_timeout_s()
    pmic.set_i2c_frequency(400000)
    i2c_freq = pmic.get_i2c_frequency()
    pmic.enable_watchdog(5)
    pmic.feed_watchdog()
    wdt = pmic.get_watchdog_countdown_s()
    pmic.disable_watchdog()
    pmic.set_timer(30, pmic.TIMER_ACTION_FLAG)
    timer_cfg = pmic.read_reg(0x3C)
    pmic.clear_timer()
    pmic.write_rtc_ram(0, b"M5PM1")
    rtc_ram = pmic.read_rtc_ram(0, 5)

    emit("STOPWATCH_M5PM1_READY")
    while not BtnA.wasPressed():
        M5.update()
        time.sleep_ms(10)
    # M5.update consumes the same PM1 IRQ through BtnPWR. Poll the driver
    # directly here so the data-plane assertion observes its actual flag.
    deadline = time.ticks_add(time.ticks_ms(), 8000)
    while not pmic.get_irq_status("button") & 0x01:
        if time.ticks_diff(time.ticks_ms(), deadline) >= 0:
            raise RuntimeError("PM1 button IRQ timeout cfg=%02x irq=%02x status=%02x" % (
                pmic.read_reg(0x49), pmic.get_irq_status("button"),
                pmic.read_reg(0x48)))
        time.sleep_ms(10)
    gp1 = pmic.read_pin(1)
    gpio_irq = pmic.get_irq_status("gpio")
    button_irq = pmic.get_irq_status("button")
    button_event = pmic.read_button_event()
    wake = pmic.get_wake_source()
    adc1 = pmic.read_adc_raw(1)
    adc2 = pmic.read_adc_raw(2)
    temp = pmic.read_temperature_raw()

    detail = "g=%d%d irq=%02x adc=%d,%d" % (
        gp0, gp1, gpio_irq, adc1, adc2,
    )
    emit("STOPWATCH_M5PM1_FIELDS", {
        "info": info, "uid_len": len(uid), "power_cfg": power_cfg,
        "lvp": lvp, "gp0": gp0, "gp1": gp1, "gpio_irq": gpio_irq,
        "pwm_freq": pwm_freq, "pwm_duty": pwm_duty, "neo0": neo0,
        "neo1": neo1, "i2c_sleep": i2c_sleep, "i2c_freq": i2c_freq,
        "wdt": wdt, "timer_cfg": timer_cfg, "rtc_ram": rtc_ram,
        "wake": wake, "button_irq": button_irq, "button_event": button_event,
        "adc1": adc1, "adc2": adc2, "temp": temp,
    })
    if (info[0] != 0x50 or len(uid) != 12
            or power_cfg & 0x0F != 0x0F or abs(lvp - 3200) > 4
            or gp0 != 1 or gp1 != 0 or gpio_irq & 0x02 == 0
            or pwm_freq != 1000 or pwm_duty != 2048
            or neo0 != 0xF800 or neo1 != 0x07E0
            or i2c_sleep != 3 or i2c_freq != 400000 or wdt != 5
            or timer_cfg != 0x09 or rtc_ram != b"M5PM1"
            or wake & 0x04 == 0 or button_irq & 0x01 == 0
            or not button_event or adc1 == 0 or adc2 == 0 or temp == 0):
        raise RuntimeError(detail)
    ok = True
except Exception as exc:
    detail = repr(exc)[:64]
    emit("STOPWATCH_M5PM1_ERROR", repr(exc))

d.fillRect(0, 0, 466, 10, d.COLOR.GREEN if ok else d.COLOR.RED)
d.setCursor(42, 140)
d.print(detail)
d.setCursor(42, 180)
d.print("PASS" if ok else "FAIL")
emit("STOPWATCH_M5PM1_DONE", "PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
