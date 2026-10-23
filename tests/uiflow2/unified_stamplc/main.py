"""One UIFlow2 guest exercising StamPLC board, WiFi and BLE."""

import M5
import network
import socket
import time
from M5 import *
from stamplc import StamPLC


SSID = "myssid"
HTTP_HOST = "10.0.2.2"
HTTP_PORT = 18088
BLE_NAME = "M5-STAMPLC-UNIFIED"

state = {
    "audio": "init",
    "ble": "init",
    "can": "init",
    "http": "not-run",
    "ina226": "init",
    "inputs": "init",
    "key": 0,
    "lm75": "init",
    "relays": "init",
    "rgb": "init",
    "rs485": "init",
    "rtc": "init",
    "wifi": "init",
}
log_uart = None


def emit(*parts):
    line = " ".join(str(part) for part in parts)
    if log_uart:
        log_uart.write(line + "\n")
    else:
        print(line)


def draw():
    display = M5.Display
    display.fillScreen(display.COLOR.BLACK)
    display.drawRect(3, 3, 233, 129, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.WHITE, display.COLOR.BLACK)
    display.setTextSize(1)
    display.setCursor(9, 8)
    display.print("StamPLC unified")
    lines = (
        "WiFi:%s BLE:%s" % (state["wifi"], state["ble"]),
        "HTTP:%s KEY:%d" % (state["http"], state["key"]),
        "RTC:%s LM75:%s" % (state["rtc"], state["lm75"]),
        "INA:%s RGB:%s" % (state["ina226"], state["rgb"]),
        "RLY:%s IN:%s" % (state["relays"], state["inputs"]),
        "CAN:%s RS485:%s" % (state["can"], state["rs485"]),
        "SPK:%s" % state["audio"],
    )
    for index, line in enumerate(lines):
        display.setCursor(9, 27 + index * 13)
        display.print(line[:36])


def probe_http():
    client = socket.socket()
    client.settimeout(10)
    try:
        client.connect((HTTP_HOST, HTTP_PORT))
        client.send(b"GET /unified HTTP/1.0\r\nHost: qemu.test\r\n\r\n")
        response = bytearray()
        while b"UNIFIED_STAMPLC_OK" not in response and len(response) < 2048:
            chunk = client.recv(512)
            if not chunk:
                break
            response.extend(chunk)
        response = bytes(response)
        emit("UNIFIED_STAMPLC_HTTP", repr(response))
        if (
            not response.startswith(b"HTTP/")
            or b"200 OK" not in response
            or b"UNIFIED_STAMPLC_OK" not in response
        ):
            raise RuntimeError("controlled HTTP response is invalid")
        return "pass"
    finally:
        client.close()


def main():
    global log_uart

    from hardware import CAN, PWR485, UART as HardwareUART
    from machine import I2C, Pin
    from driver.ina226 import INA226
    from rtc_probe import check_rx8130

    M5.begin()
    log_uart = HardwareUART(0, baudrate=115200, tx=43, rx=44)
    emit("UNIFIED_STAMPLC_MAIN")
    emit("UNIFIED_STAMPLC_BOARD", M5.getBoard())
    emit(
        "UNIFIED_STAMPLC_DISPLAY",
        M5.Display.width(),
        M5.Display.height(),
    )
    M5.Display.setRotation(0)

    i2c = I2C(1, scl=Pin(15), sda=Pin(13), freq=400000)
    plc = StamPLC(i2c=i2c)
    emit("UNIFIED_STAMPLC_IO_CONFIG_READY")
    time.sleep_ms(500)

    try:
        plc.relay[1].on()
        plc.relay[2].off()
        if not plc.relay[1].value() or plc.relay[2].value():
            raise RuntimeError("relay readback mismatch")
        state["relays"] = "pass"
        emit("UNIFIED_STAMPLC_RELAYS", 1, 0)
    except Exception as error:
        state["relays"] = "fail"
        emit("UNIFIED_STAMPLC_RELAYS_ERROR", repr(error))

    try:
        inputs = tuple(plc.input[index].value() for index in range(1, 9))
        emit("UNIFIED_STAMPLC_INPUTS", *inputs)
        if inputs != (1, 1, 1, 1, 1, 1, 1, 1):
            raise RuntimeError("digital input state mismatch")
        state["inputs"] = "pass"
    except Exception as error:
        state["inputs"] = "fail"
        emit("UNIFIED_STAMPLC_INPUTS_ERROR", repr(error))

    try:
        plc.led.red.on()
        plc.led.green.on()
        plc.led.blue.off()
        rgb = (
            plc.led.red.value(),
            plc.led.green.value(),
            plc.led.blue.value(),
        )
        emit("UNIFIED_STAMPLC_RGB", *(int(value) for value in rgb))
        if rgb != (1, 1, 0):
            raise RuntimeError("RGB readback mismatch")
        state["rgb"] = "pass"
    except Exception as error:
        state["rgb"] = "fail"
        emit("UNIFIED_STAMPLC_RGB_ERROR", repr(error))

    try:
        raw = i2c.readfrom_mem(0x48, 0x00, 2)
        value = (raw[0] << 8) | raw[1]
        temperature = (value >> 5) / 8.0
        emit("UNIFIED_STAMPLC_LM75", "%.1f" % temperature, raw.hex())
        if abs(temperature - 37.5) > 0.01:
            raise RuntimeError("LM75 temperature mismatch")
        state["lm75"] = "pass"
    except Exception as error:
        state["lm75"] = "fail"
        emit("UNIFIED_STAMPLC_LM75_ERROR", repr(error))

    try:
        monitor = INA226(i2c, 0x40, shunt_resistor=0.08)
        monitor.configure(
            avg=INA226.CFG_AVGMODE_16SAMPLES,
            vbus_conv_time=INA226.CFG_VBUSCT_8244us,
            vshunt_conv_time=INA226.CFG_VSHUNTCT_8244us,
            mode=INA226.CFG_MODE_SANDBVOLT_CONTINUOUS,
        )
        monitor.calibrate(cal_value=0x0800)
        emit(
            "UNIFIED_STAMPLC_INA226",
            "%.2f" % monitor.read_bus_voltage(),
            "%.2f" % monitor.read_current(),
            "%.2f" % monitor.read_power(),
        )
        state["ina226"] = "pass"
    except Exception as error:
        state["ina226"] = "fail"
        emit("UNIFIED_STAMPLC_INA226_ERROR", repr(error))

    try:
        rtc = check_rx8130(i2c)
        emit("UNIFIED_STAMPLC_RTC", *rtc)
        state["rtc"] = "pass"
    except Exception as error:
        state["rtc"] = "fail"
        emit("UNIFIED_STAMPLC_RTC_ERROR", repr(error))

    try:
        can = CAN(
            id=0,
            port=(43, 42),
            mode=CAN.NO_ACKNOWLEDGE,
            baudrate=125000,
        )
        payload = b"M5CAN!"
        can.send(payload, 0x123)
        deadline = time.ticks_add(time.ticks_ms(), 2000)
        while (
            not can.any(0)
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(10)
        message = can.recv(0, timeout=1000)
        received = bytes(message[4])
        can.deinit()
        emit("UNIFIED_STAMPLC_CAN", hex(message[0]), received)
        if message[0] != 0x123 or received != payload:
            raise RuntimeError("CAN loopback mismatch")
        state["can"] = "pass"
    except Exception as error:
        state["can"] = "fail"
        emit("UNIFIED_STAMPLC_CAN_ERROR", repr(error))

    try:
        rs485 = PWR485(
            2,
            baudrate=115200,
            bits=8,
            parity=None,
            stop=1,
            tx=0,
            rx=39,
            rts=46,
            mode=PWR485.MODE_RS485_HALF_DUPLEX,
        )
        payload = b"M5RS485"
        rs485.write(payload)
        deadline = time.ticks_add(time.ticks_ms(), 2000)
        while (
            not rs485.any()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(10)
        received = rs485.read()
        emit("UNIFIED_STAMPLC_RS485", received)
        if received != payload:
            raise RuntimeError("RS485 loopback mismatch")
        state["rs485"] = "pass"
    except Exception as error:
        state["rs485"] = "fail"
        emit("UNIFIED_STAMPLC_RS485_ERROR", repr(error))

    try:
        if not Speaker.begin():
            raise RuntimeError("speaker begin failed")
        Speaker.setVolume(255)
        Speaker.tone(3500, 1000)
        time.sleep_ms(500)
        if not Speaker.isRunning():
            raise RuntimeError("buzzer stopped unexpectedly")
        state["audio"] = "pass"
        emit("UNIFIED_STAMPLC_AUDIO_PASS")
    except Exception as error:
        state["audio"] = "fail"
        emit("UNIFIED_STAMPLC_AUDIO_ERROR", repr(error))

    draw()

    try:
        station = network.WLAN(network.STA_IF)
        station.active(True)
        networks = station.scan()
        emit("UNIFIED_STAMPLC_WIFI_SCAN", len(networks))
        emit("UNIFIED_STAMPLC_WIFI_SCAN_RESULTS", repr(networks))
        error = station.connect(SSID)
        emit("UNIFIED_STAMPLC_WIFI_CONNECT_RETURNED", error)
        deadline = time.ticks_add(time.ticks_ms(), 20000)
        while (
            not station.isconnected()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(250)
        if not station.isconnected():
            raise RuntimeError("WiFi association timed out")
        address = station.ifconfig()[0]
        emit("UNIFIED_STAMPLC_WIFI_CONNECTED", address)
        state["wifi"] = "pass"
    except Exception as error:
        state["wifi"] = "fail"
        emit("UNIFIED_STAMPLC_WIFI_ERROR", repr(error))

    if state["wifi"] == "pass":
        try:
            state["http"] = probe_http()
            emit("UNIFIED_STAMPLC_HTTP_PASS")
        except Exception as error:
            state["http"] = "fail"
            emit("UNIFIED_STAMPLC_HTTP_ERROR", repr(error))

    try:
        from bleuart import BLEUARTServer

        server = BLEUARTServer(name=BLE_NAME, verbose=True)

        def on_receive():
            payload = bytes(server.read())
            emit("UNIFIED_STAMPLC_BLE_RX", payload)
            server.write(b"ACK:" + payload)
            emit("UNIFIED_STAMPLC_BLE_ACK_SENT")

        server.irq(on_receive)
        state["ble"] = "pass"
        emit("UNIFIED_STAMPLC_BLE_READY")
    except Exception as error:
        state["ble"] = "fail"
        emit("UNIFIED_STAMPLC_BLE_ERROR", repr(error))

    if state["audio"] == "pass":
        try:
            Speaker.tone(3500, 15000)
            time.sleep_ms(100)
            if not Speaker.isRunning():
                raise RuntimeError("buzzer hold stopped unexpectedly")
            emit("UNIFIED_STAMPLC_AUDIO_HOLD")
        except Exception as error:
            state["audio"] = "fail"
            emit("UNIFIED_STAMPLC_AUDIO_HOLD_ERROR", repr(error))

    draw()
    emit("UNIFIED_STAMPLC_READY")
    while True:
        M5.update()
        if BtnA.wasPressed():
            state["key"] += 1
            plc.relay[1].toggle()
            emit(
                "UNIFIED_STAMPLC_KEY",
                state["key"],
                int(plc.relay[1].value()),
            )
            draw()
        time.sleep_ms(20)


main()
