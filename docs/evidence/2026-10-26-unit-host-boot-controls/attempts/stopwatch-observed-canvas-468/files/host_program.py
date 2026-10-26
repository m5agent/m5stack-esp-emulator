import time
import M5
from machine import I2C, Pin
from probe_config import (
    CASE, DEVICE_ID, WHITE, YELLOW, ROTATION, FRAME_WIDTH, FRAME_HEIGHT,
    TEXT_X, TEXT_Y, TEXT_WIDTH, INTERNAL_SDA, INTERNAL_SCL,
    INTERNAL_CONTROLLER, EXTERNAL_CONTROLLER,
)
from probe_logging import emit

emit("HOST_PROBE_START", DEVICE_ID, CASE)
M5.begin()
screen = M5.Display
screen.setRotation(ROTATION)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(1 if FRAME_WIDTH < 200 else 2)
emit("HOST_GEOMETRY", screen.width(), screen.height(), ROTATION)
emit("HOST_BOARD", M5.getBoard())
if (screen.width(), screen.height()) != (FRAME_WIDTH, FRAME_HEIGHT):
    raise RuntimeError("host display geometry differs from the explicit profile")
screen.setCursor(TEXT_X, TEXT_Y)
screen.print(DEVICE_ID + "\n" + CASE)

# Explicit physical buses: a real BMI270 CHIP_ID read is repeated after each
# external operation. No register is preloaded or changed by this probe.
internal = I2C(INTERNAL_CONTROLLER, scl=Pin(INTERNAL_SCL),
               sda=Pin(INTERNAL_SDA), freq=100000)
internal_reads = 0


def check_internal(phase):
    global internal_reads
    identity = internal.readfrom_mem(0x68, 0x00, 1)[0]
    internal_reads += 1
    emit("HOST_INTERNAL", phase, identity, internal_reads)
    if identity != 0x24:
        raise RuntimeError("onboard BMI270 identity disappeared or leaked from another bus")


check_internal("before")
if CASE == "button":
    from unit import ButtonUnit
    unit = ButtonUnit((WHITE, YELLOW), True, type=2)
    unit.count_reset()
elif CASE == "relay":
    from unit import RelayUnit
    unit = RelayUnit((WHITE, YELLOW))
elif CASE == "env-iii":
    from unit import ENVUnit
    external = I2C(EXTERNAL_CONTROLLER, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)
    addresses = sorted(external.scan())
    emit("HOST_EXTERNAL_SCAN", *addresses)
    if addresses != [0x44, 0x70]:
        raise RuntimeError("external bus must expose only the two ENV III chips")
    unit = ENVUnit(i2c=external, type=3)
elif CASE != "boot-control":
    raise ValueError("unknown host integration case")
check_internal("after_init")
emit("HOST_PROBE_READY", DEVICE_ID, CASE)
last_value = None
last_report = time.ticks_ms() - 2000
sequence = 0
while True:
    M5.update()
    if CASE == "button":
        unit.tick(None)
        value = (unit.pin.value(), unit.count_value)
        marker = "HOST_BUTTON %d %d" % value
    elif CASE == "relay":
        if sequence % 2:
            unit.off()
        else:
            unit.on()
        value = int(bool(unit.get_status()))
        marker = "HOST_RELAY %d" % value
    elif CASE == "env-iii":
        value = (unit.read_temperature(), unit.read_humidity(), unit.read_pressure() * 100)
        marker = "HOST_ENV %.3f %.3f %.3f" % value
    else:
        value = "boot control"
        marker = "HOST_BOOT_CONTROL"
    if value != last_value or time.ticks_diff(time.ticks_ms(), last_report) >= 1500:
        emit(marker)
        screen.fillRect(TEXT_X, TEXT_Y + 36, TEXT_WIDTH, 80, 0xFFFFFF)
        screen.setCursor(TEXT_X, TEXT_Y + 36)
        screen.print(str(value))
        last_value = value
        last_report = time.ticks_ms()
    check_internal("loop")
    sequence += 1
    time.sleep_ms(1500 if CASE == "relay" else 250)
