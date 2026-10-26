import time
import M5
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW
from probe_logging import emit

emit("IO_PROBE_START", CASE)
M5.begin()
screen = M5.Display
screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("IO Unit: " + CASE)


def show(text):
    screen.fillRect(0, 40, 320, 180, 0xFFFFFF)
    screen.setCursor(6, 44)
    screen.print(str(text))


def wait_ms(duration):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration:
        M5.update()
        time.sleep_ms(10)


port = (WHITE, YELLOW)
pir_callbacks = [0, 0]
dual_clicks = [0, 0]
ir_callbacks = 0


def pir_active(unit):
    pir_callbacks[1] += 1
    emit("IO_PIR_CALLBACK", 1, pir_callbacks[1])


def pir_negative(unit):
    pir_callbacks[0] += 1
    emit("IO_PIR_CALLBACK", 0, pir_callbacks[0])


def blue_clicked(state):
    dual_clicks[0] += 1
    emit("IO_DUAL_CLICK", *dual_clicks)


def red_clicked(state):
    dual_clicks[1] += 1
    emit("IO_DUAL_CLICK", *dual_clicks)


def ir_received(data, address, control):
    global ir_callbacks
    ir_callbacks += 1
    emit("IO_IR_RX", data, address, control, ir_callbacks)


if CASE == "pir":
    from io_drivers.pir import PIRUnit
    unit = PIRUnit(port)
    unit.set_callback(pir_active, unit.IRQ_ACTIVE)
    unit.set_callback(pir_negative, unit.IRQ_NEGATIVE)
    unit.enable_irq()
    phase = 0
    disabled_high = False
elif CASE == "dual-button":
    from io_drivers.dual_button import DualButtonUnit
    blue, red = DualButtonUnit(port)
    blue.setCallback(blue.CB_TYPE.WAS_CLICKED, blue_clicked)
    red.setCallback(red.CB_TYPE.WAS_CLICKED, red_clicked)
elif CASE == "limit":
    from io_drivers.limit import LIMITUnit
    from io_drivers.button import ButtonUnit
    emit("IO_LIMIT_BUTTON_ALIAS", int(ButtonUnit is LIMITUnit))
    unit = LIMITUnit(port, True, type=2)
    unit.count_reset()
    reset_done = False
elif CASE == "key":
    from io_drivers.key import KeyUnit
    unit = KeyUnit(port)
    unit.set_brightness(100)
    unit.set_color(0x2468AC)
elif CASE == "rgb":
    from io_drivers.rgb import RGBUnit
    from driver.neopixel.sk6812 import SK6812
    unit = RGBUnit(port, 3)
    unit.set_brightness(100)
    short = SK6812(YELLOW, 1)
    short.set_brightness(100)
elif CASE == "angle":
    from io_drivers.angle import AngleUnit
    unit = AngleUnit(port)
elif CASE == "light":
    from io_drivers.light import LightUnit
    unit = LightUnit(port)
elif CASE == "fan":
    from io_drivers.fan import FanUnit
    unit = FanUnit(port)
elif CASE == "buzzer":
    from io_drivers.buzzer import BuzzerUnit
    unit = BuzzerUnit(port)
elif CASE == "ir":
    from io_drivers.ir import IRUnit, _HAS_RMT_IR_CMODULE
    if not _HAS_RMT_IR_CMODULE:
        raise RuntimeError("native rmt_ir module required; Python fallback is not this test")
    import gc
    gc.disable()
    emit("IO_IR_GC_DISABLED", int(not gc.isenabled()))
    unit = IRUnit(port)
    unit.rx_cb(ir_received)
    unit.tx(0x12, 0x34)
    emit("IO_IR_NATIVE", 1)
    emit("IO_IR_TX", 0x12, 0x34)
    from machine import mem32
    emit("IO_IR_CLOCK", hex(mem32[0x600160C0]))
    for channel in range(4):
        emit("IO_IR_REG", channel, hex(mem32[0x60016020 + channel * 4]),
             hex(mem32[0x600160A0 + channel * 4]),
             hex(mem32[0x60016800 + channel * 48 * 4]))
    ir_packed_done = False
    ir_user_sent_at = time.ticks_ms()
    ir_debug_read = False
elif CASE == "rs485":
    from io_drivers.rs485 import RS485Unit
    unit = RS485Unit(1, port=port, baudrate=9600, bits=8, parity=None, stop=1,
                     timeout=0, timeout_char=0, rxbuf=256)
    initial = b"guest-to-peer\x00\x7f\xff"
    emit("IO_RS485_TX", unit.write(initial), initial.hex())
elif CASE == "hub":
    # A passive HUB has no driver or address. These are three real drivers on
    # one physical I2C bus, wired through the attachment tree by the service.
    from unit import ENVUnit, NCIRUnit, TVOCUnit
    bus = I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)
    addresses = sorted(bus.scan())
    emit("IO_HUB_SCAN", *addresses)
    if addresses != [0x44, 0x58, 0x5A, 0x70]:
        raise RuntimeError("passive HUB must expose exactly its child chip addresses")
    env = ENVUnit(i2c=bus, type=3)
    ncir = NCIRUnit(bus)
    tvoc = TVOCUnit(bus)
else:
    raise ValueError("unknown IO Unit probe")

emit("IO_PROBE_READY", CASE)
previous = None
last_report = time.ticks_ms() - 2000
while True:
    M5.update()
    if CASE == "rgb":
        unit.fill_color(0x112233)
        unit.set_color(1, 0x445566)
        unit.set_color(2, 0x778899)
        emit("IO_RGB_FULL", 1)
        show("GRB: 112233/445566/778899")
        wait_ms(4000)
        short.fill_color(0xFFFFFF)
        emit("IO_RGB_SHORT", 1)
        show("1 pixel sent to 3 pixel chain")
        wait_ms(4000)
        unit.fill_color(0xA1B2C3)
        unit.set_color(1, 0x010203)
        unit.set_color(2, 0x040506)
        emit("IO_RGB_FULL", 2)
        show("GRB: a1b2c3/010203/040506")
        wait_ms(4000)
        continue
    if CASE == "fan":
        for stage, frequency, speed in ((0, 1000, 0), (1, 1000, 25), (2, 1500, 100)):
            unit.set_pwm_freq(frequency)
            unit.set_speed_ctrl(speed)
            emit("IO_FAN", stage, frequency, speed)
            show("%d Hz / speed %d" % (frequency, speed))
            wait_ms(4000)
        continue
    if CASE == "buzzer":
        for stage, frequency, duty in ((0, 1200, 0), (1, 2400, 25), (2, 3600, 75)):
            unit.set_freq(frequency)
            unit.set_duty(duty)
            emit("IO_BUZZER", stage, frequency, duty)
            show("%d Hz / duty %d%%" % (frequency, duty))
            wait_ms(4000)
        unit.once(freq=2000, duty=50, duration=2000)
        emit("IO_BUZZER_ONCE", 2000, 50)
        wait_ms(3000)
        emit("IO_BUZZER_TIMER_DONE")
        unit.set_duty(25)
        wait_ms(500)
        unit.turn_off()
        emit("IO_BUZZER_OFF")
        wait_ms(4000)
        continue
    if CASE == "pir":
        level = int(unit.get_status())
        if phase == 0 and min(pir_callbacks) >= 1 and level == 0:
            unit.disable_irq()
            phase = 1
            emit("IO_PIR_DISABLED", *pir_callbacks)
        elif phase == 1:
            if level:
                disabled_high = True
            elif disabled_high:
                emit("IO_PIR_DISABLED_DONE", *pir_callbacks)
                unit.enable_irq()
                phase = 2
                emit("IO_PIR_REENABLED")
        value = (level, pir_callbacks[1], pir_callbacks[0], phase)
        marker = "IO_PIR %d %d %d %d" % value
    elif CASE == "dual-button":
        blue.tick(None)
        red.tick(None)
        value = (blue._pin.value(), red._pin.value(), dual_clicks[0], dual_clicks[1])
        marker = "IO_DUAL %d %d %d %d" % value
    elif CASE == "limit":
        unit.tick(None)
        value = (unit.pin.value(), unit.count_value)
        marker = "IO_LIMIT %d %d" % value
        if not reset_done and unit.count_value >= 3:
            emit(marker)
            unit.count_reset()
            reset_done = True
            emit("IO_LIMIT_COUNT_RESET", unit.count_value)
    elif CASE == "key":
        unit.tick(None)
        value = unit.get_key_state()
        if value != previous:
            unit.set_brightness(50 if value == 0 else 100)
            unit.set_color(0x2468AC)
        marker = "IO_KEY_RAW %d" % value
    elif CASE == "angle":
        value = (unit.get_value(), unit.get_voltage(), unit._adc.read_uv())
        marker = "IO_ANGLE %d %.6f %d" % value
    elif CASE == "light":
        value = (unit.get_analog_value(), unit.get_digital_value())
        marker = "IO_LIGHT %d %d" % value
    elif CASE == "ir":
        if not ir_packed_done and time.ticks_diff(time.ticks_ms(), ir_user_sent_at) >= 5000:
            # This is explicitly the native uint16 API, separate from the
            # unchanged public wrapper which clamps both arguments to uint8.
            unit._rmt_ir_instance.send(0xED12, 0xCB34)
            ir_packed_done = True
            emit("IO_IR_NATIVE_PACKED", 0xED12, 0xCB34)
        value = ir_callbacks
        marker = "IO_IR_HEARTBEAT %d" % value
    elif CASE == "rs485":
        available = unit.any()
        if available:
            emit("IO_RS485_ANY", available)
            data = unit.read(available)
            if data:
                emit("IO_RS485_RX", data.hex())
                reply = b"echo:" + data
                emit("IO_RS485_ECHO", unit.write(reply), reply.hex())
        value = "UART1 9600 / UART0 log"
        marker = "IO_RS485_HEARTBEAT"
    else:
        value = (env.read_temperature(), env.read_humidity(), env.read_pressure() * 100,
                 ncir.get_ambient_temperature(), ncir.get_object_temperature()) + tuple(tvoc.measure_iaq())
        marker = "IO_HUB %.3f %.3f %.3f %.3f %.3f %d %d" % value
    if value != previous or time.ticks_diff(time.ticks_ms(), last_report) >= 1500:
        emit(marker)
        if CASE == "ir":
            emit("IO_IR_RX_REG", hex(mem32[0x60016030]), hex(mem32[0x60016034]),
                 hex(mem32[0x60016060]), hex(mem32[0x60016070]),
                 hex(mem32[0x60016074]), hex(mem32[0x60016078]))
            emit("IO_IR_RX_MEM32", hex(mem32[0x60016B00]), hex(mem32[0x60016B84]))
            emit("IO_IR_NATIVE_STATE", unit._rmt_ir_instance.get_address(),
                 unit._rmt_ir_instance.get_command(), int(unit._rmt_ir_instance.is_repeat()))
            if not ir_debug_read and (mem32[0x60016060] & 0x3FF) >= 226:
                emit("IO_IR_RX_WORDS", *[hex(mem32[0x60016B00 + index * 4] & 0xFFFFFFFF) for index in range(34)])
                ir_debug_read = True
        show(value)
        previous = value
        last_report = time.ticks_ms()
    time.sleep_ms(1000 if CASE == "hub" else 10)
