# Tab5 UIFlow2 peripheral probe through the real P4 I2C controller.
import M5
import machine
import time

touches = 0
results = []
charge_input = -1
charging_value = None
charge_enable = -1
battery_voltage = -1
battery_current = 0
battery_level = -1


def draw_ui():
    d = M5.Display
    width = d.width()
    height = d.height()
    d.fillScreen(d.COLOR.BLACK)
    d.drawRect(8, 8, width - 16, height - 16, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(5)
    d.setCursor(40, 38)
    d.print("Tab5 peripherals")
    d.setTextSize(2)
    y = 120
    for line in results[:7]:
        d.setCursor(40, y)
        d.print(line)
        y += 30
    if charge_input >= 0:
        d.setCursor(40, y + 12)
        d.print("CHG in:%02X api:%s en:%d" % (
            charge_input, charging_value, charge_enable,
        ))
        d.setCursor(40, y + 46)
        d.print("BAT %dmV %dmA %d%%" % (
            battery_voltage, battery_current, battery_level,
        ))
    d.setTextColor(d.COLOR.GREEN)
    d.setTextSize(4)
    d.setCursor(40, 430)
    d.print("touches: %d" % touches)
    d.fillRect(850, 500, 300, 120, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(4)
    d.setCursor(915, 548)
    d.print("TAP")


def read_byte(i2c, address, register):
    return i2c.readfrom_mem(address, register, 1)[0]


def read_word_be(i2c, address, register):
    raw = i2c.readfrom_mem(address, register, 2)
    return (raw[0] << 8) | raw[1]


def write_byte(i2c, address, register, value):
    i2c.writeto_mem(address, register, bytes((value,)))


print("TAB5_PERIPHERAL_MAIN_START")

i2c = None
port = 1
try:
    i2c = machine.I2C(1, scl=machine.Pin(32), sda=machine.Pin(31), freq=400000)
except Exception as error:
    print("TAB5_I2C_PORT1_ERROR", repr(error))
    try:
        port = 0
        i2c = machine.I2C(0, scl=machine.Pin(32), sda=machine.Pin(31), freq=400000)
    except Exception as second_error:
        print("TAB5_I2C_PORT0_ERROR", repr(second_error))

if i2c is not None:
    scan = i2c.scan()
    print("TAB5_I2C_PORT", port)
    print("TAB5_I2C_SCAN", scan)
    results.append("I2C port %d devices %s" % (port, scan))
    try:
        bmi_id = read_byte(i2c, 0x68, 0x00)
        print("TAB5_BMI270_CHIP_ID=0x%02X" % bmi_id)
        results.append("BMI270 ID 0x%02X" % bmi_id)
    except Exception as error:
        print("TAB5_BMI270_ERROR", repr(error))
    try:
        ina_id = read_word_be(i2c, 0x41, 0xFE)
        print("TAB5_INA226_MANUFACTURER_ID=0x%04X" % ina_id)
        results.append("INA226 MFG 0x%04X" % ina_id)
        i2c.writeto_mem(0x41, 0x05, b"\x12\x34")
        calibration = i2c.readfrom_mem(0x41, 0x05, 2)
        calibration_value = (calibration[0] << 8) | calibration[1]
        print("TAB5_INA226_CALIBRATION=0x%04X" % calibration_value)
        results.append("INA226 CAL 0x%04X" % calibration_value)
    except Exception as error:
        print("TAB5_INA226_ERROR", repr(error))
    for address, label in ((0x43, "PI4IOE1"), (0x44, "PI4IOE2")):
        try:
            chip_id = read_byte(i2c, address, 0x01)
            print("TAB5_%s_CHIP_ID=0x%02X" % (label, chip_id))
            results.append("%s ID 0x%02X" % (label, chip_id))
            original = read_byte(i2c, address, 0x05)
            write_byte(i2c, address, 0x05, 0x55)
            writeback = read_byte(i2c, address, 0x05)
            write_byte(i2c, address, 0x05, original)
            print("TAB5_%s_WRITEBACK=0x%02X" % (label, writeback))
            results.append("%s WB 0x%02X" % (label, writeback))
        except Exception as error:
            print("TAB5_%s_ERROR" % label, repr(error))
    try:
        i2c.writeto_mem(0x32, 0x10, b"\x57\x30\x12\x03\x21\x10\x26")
        rtc = i2c.readfrom_mem(0x32, 0x10, 7)
        rtc_hex = "".join("%02X" % value for value in rtc)
        print("TAB5_RX8130_TIME=%s" % rtc_hex)
        results.append("RX8130 %s" % rtc_hex)
    except Exception as error:
        print("TAB5_RX8130_ERROR", repr(error))
    try:
        rtc_api = machine.RTC()
        rtc_target = (2026, 10, 22, 4, 12, 34, 56, 0)
        rtc_api.datetime(rtc_target)
        rtc_value = rtc_api.datetime()[:7]
        print("TAB5_SYSTEM_RTC_API", rtc_value)
    except Exception as error:
        print("TAB5_RTC_API_ERROR", repr(error))
    try:
        battery_voltage = M5.Power.getBatteryVoltage()
        battery_current = M5.Power.getBatteryCurrent()
        battery_level = M5.Power.getBatteryLevel()
        print("TAB5_BATTERY", battery_voltage, battery_current, battery_level)
        results.append("battery %d %d %d" % (
            battery_voltage, battery_current, battery_level,
        ))
        charge_input = read_byte(i2c, 0x44, 0x0F)
        print("TAB5_CHARGE_INPUT=0x%02X" % charge_input)
        charging_value = M5.Power.isCharging()
        print("TAB5_CHARGING", charging_value)
        results.append("charging %s" % charging_value)
        M5.Power.setChargeCurrent(500)
        charge_enable = (read_byte(i2c, 0x44, 0x05) >> 7) & 1
        print("TAB5_CHARGE_ENABLE", charge_enable)
        results.append("charge_enable %d" % charge_enable)
    except Exception as error:
        print("TAB5_CHARGER_ERROR", repr(error))
else:
    results.append("I2C init failed")

M5.begin()
M5.Display.setRotation(1)
M5.Display.setBrightness(255)

if not results:
    results.append("No I2C results")
draw_ui()
print("TAB5_UI_DRAWN", M5.Display.width(), M5.Display.height())

was_pressed = False
while True:
    M5.update()
    pressed = M5.Touch.getCount() > 0
    if pressed and not was_pressed:
        x = M5.Touch.getX()
        y = M5.Touch.getY()
        print("TAB5_TOUCH", x, y)
        touches += 1
        if 850 <= x <= 1150 and 500 <= y <= 620:
            print("TAB5_TAP_BUTTON", touches)
        draw_ui()
        print("TAB5_DRAW_AFTER_TOUCH", touches)
    was_pressed = pressed
    time.sleep(0.02)
