"""One UIFlow2 Core2 guest exercising board, WiFi and BLE."""

import M5
import esp32
import gc
import network
import socket
import time
from M5 import *


SSID = "myssid"
HTTP_HOST = "10.0.2.2"
HTTP_PORT = 18089
BLE_NAME = "M5-CORE2-UNIFIED"
PSRAM_BUFFER_BYTES = 1 << 20
PSRAM_CHUNK_BYTES = 4096
PSRAM_INITIAL_SWEEPS_REQUIRED = 3
PSRAM_SWEEP_INTERVAL_MS = 2000
HTTP_RECHECK_INTERVAL_MS = 10000
PUBLIC_RECHECK_INTERVAL_MS = 30000
STRESS_HEARTBEAT_INTERVAL_MS = 10000
PSRAM_PATTERN = bytes([(index * 37 + 11) & 0xFF for index in range(PSRAM_CHUNK_BYTES)])

state = {
    "audio": "init",
    "ble": "init",
    "http": "not-run",
    "imu": "init",
    "ina": "init",
    "mic": "init",
    "power": (0, 0, 0),
    "public": "init",
    "psram": "init",
    "rtc": "init",
    "touch": "init",
    "wifi": "init",
}
log_uart = None
psram_buffer = None
psram_sweeps = 0
psram_next_sweep = 0
http_rechecks = 0
public_rechecks = 0
next_http_recheck = 0
next_public_recheck = 0
next_stress_heartbeat = 0
stress_started = 0


def emit(*parts):
    line = " ".join(str(part) for part in parts)
    if log_uart:
        log_uart.write(line + "\n")
    else:
        print(line)


def draw():
    display = M5.Display
    display.fillScreen(display.COLOR.BLACK)
    display.drawRect(4, 4, 311, 231, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.WHITE, display.COLOR.BLACK)
    display.setTextSize(2)
    display.setCursor(14, 12)
    display.print("Core2 unified")
    display.setTextSize(1)
    lines = (
        "WiFi:%s BLE:%s P:%s" % (
            state["wifi"],
            state["ble"],
            state["psram"],
        ),
        "HTTP:%s TOUCH:%s" % (state["http"], state["touch"]),
        "PMIC:%d BAT:%dmV" % state["power"],
        "IMU:%s RTC:%s" % (state["imu"], state["rtc"]),
        "INA:%s" % state["ina"],
        "SPK:%s MIC:%s" % (state["audio"], state["mic"]),
    )
    for index, line in enumerate(lines):
        display.setCursor(14, 48 + index * 24)
        display.print(line[:48])
    display.fillRect(160, 180, 140, 24, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.WHITE, display.COLOR.BLUE)
    display.setCursor(224, 186)
    display.print("TOUCH")


def probe_http():
    client = socket.socket()
    client.settimeout(10)
    try:
        client.connect((HTTP_HOST, HTTP_PORT))
        client.send(b"GET /unified HTTP/1.0\r\nHost: qemu.test\r\n\r\n")
        response = bytearray()
        while b"UNIFIED_CORE2_OK" not in response and len(response) < 2048:
            chunk = client.recv(512)
            if not chunk:
                break
            response.extend(chunk)
        response = bytes(response)
        emit("UNIFIED_CORE2_HTTP", repr(response))
        if (
            not response.startswith(b"HTTP/")
            or b"200 OK" not in response
            or b"UNIFIED_CORE2_OK" not in response
        ):
            raise RuntimeError("controlled HTTP response is invalid")
        return "pass"
    finally:
        client.close()


def probe_public():
    addresses = socket.getaddrinfo("example.com", 80)
    if not addresses:
        raise RuntimeError("public DNS returned no address")
    address = addresses[0][4][0]
    emit("UNIFIED_CORE2_PUBLIC_DNS", address)
    client = socket.socket()
    client.settimeout(15)
    try:
        client.connect((address, 80))
        client.send(
            b"GET / HTTP/1.0\r\nHost: example.com\r\n"
            b"Connection: close\r\n\r\n"
        )
        response = bytearray()
        while len(response) < 2048:
            chunk = client.recv(512)
            if not chunk:
                break
            response.extend(chunk)
            if b"\r\n\r\n" in response:
                break
        response = bytes(response)
        emit("UNIFIED_CORE2_PUBLIC_HTTP", repr(response[:128]))
        if not response.startswith(b"HTTP/"):
            raise RuntimeError("public HTTP response is invalid")
        emit("UNIFIED_CORE2_PUBLIC_HTTP_PASS")
    finally:
        client.close()


def psram_heap_snapshot():
    return [
        tuple(info)
        for info in esp32.idf_heap_info(esp32.HEAP_DATA)
        if len(info) == 4
    ]


def largest_heap_index(heaps):
    index = None
    total = 0
    for candidate, heap in enumerate(heaps):
        if heap[0] > total:
            index = candidate
            total = heap[0]
    return index, total


def fill_psram_buffer():
    for offset in range(0, len(psram_buffer), PSRAM_CHUNK_BYTES):
        end = min(offset + PSRAM_CHUNK_BYTES, len(psram_buffer))
        chunk = PSRAM_PATTERN[: end - offset]
        psram_buffer[offset:end] = chunk
        psram_buffer[offset] = offset & 0xFF
        psram_buffer[offset + 1] = (offset >> 8) & 0xFF


def verify_psram_buffer():
    for offset in range(0, len(psram_buffer), PSRAM_CHUNK_BYTES):
        end = min(offset + PSRAM_CHUNK_BYTES, len(psram_buffer))
        expected = PSRAM_PATTERN[2 : end - offset]
        if psram_buffer[offset + 2 : end] != expected:
            raise RuntimeError("PSRAM pattern mismatch at %d" % offset)
        if (
            psram_buffer[offset] != (offset & 0xFF)
            or psram_buffer[offset + 1] != ((offset >> 8) & 0xFF)
        ):
            raise RuntimeError("PSRAM address tag mismatch at %d" % offset)


def probe_psram():
    global psram_buffer
    gc.collect()
    before = psram_heap_snapshot()
    index, total = largest_heap_index(before)
    emit("UNIFIED_CORE2_PSRAM_HEAPS_BEFORE", repr(before))
    if index is None or total < 2 * PSRAM_BUFFER_BYTES:
        raise RuntimeError("no external heap with at least 2 MiB capacity")
    psram_buffer = bytearray(PSRAM_BUFFER_BYTES)
    fill_psram_buffer()
    verify_psram_buffer()
    after = psram_heap_snapshot()
    emit("UNIFIED_CORE2_PSRAM_HEAPS_AFTER", repr(after))
    if index >= len(after):
        raise RuntimeError("external heap disappeared after allocation")
    allocated = before[index][1] - after[index][1]
    emit(
        "UNIFIED_CORE2_PSRAM_ALLOC",
        total,
        len(psram_buffer),
        allocated,
    )
    if allocated < len(psram_buffer):
        raise RuntimeError("1 MiB buffer did not reduce the external heap")
    emit("UNIFIED_CORE2_PSRAM_INIT_PASS")


def poll_psram_sweep():
    global psram_sweeps, psram_next_sweep
    if (
        psram_buffer is None
        or state["psram"] == "fail"
    ):
        return
    now = time.ticks_ms()
    if time.ticks_diff(now, psram_next_sweep) < 0:
        return
    try:
        verify_psram_buffer()
        psram_sweeps += 1
        emit("UNIFIED_CORE2_PSRAM_SWEEP", psram_sweeps)
        if psram_sweeps == PSRAM_INITIAL_SWEEPS_REQUIRED:
            state["psram"] = "pass"
            emit("UNIFIED_CORE2_PSRAM_STRESS_PASS")
            draw()
        psram_next_sweep = time.ticks_add(now, PSRAM_SWEEP_INTERVAL_MS)
    except Exception as error:
        state["psram"] = "fail"
        emit("UNIFIED_CORE2_PSRAM_STRESS_ERROR", repr(error))


def poll_network_rechecks():
    global http_rechecks, public_rechecks
    global next_http_recheck, next_public_recheck

    if state["wifi"] != "pass":
        return
    now = time.ticks_ms()
    if (
        state["http"] == "pass"
        and time.ticks_diff(now, next_http_recheck) >= 0
    ):
        try:
            probe_http()
            http_rechecks += 1
            emit("UNIFIED_CORE2_HTTP_RECHECK_PASS", http_rechecks)
        except Exception as error:
            state["http"] = "fail"
            emit("UNIFIED_CORE2_HTTP_RECHECK_ERROR", repr(error))
        next_http_recheck = time.ticks_add(now, HTTP_RECHECK_INTERVAL_MS)

    if (
        state["public"] == "pass"
        and time.ticks_diff(now, next_public_recheck) >= 0
    ):
        try:
            probe_public()
            public_rechecks += 1
            emit(
                "UNIFIED_CORE2_PUBLIC_RECHECK_PASS",
                public_rechecks,
            )
        except Exception as error:
            state["public"] = "fail"
            emit("UNIFIED_CORE2_PUBLIC_RECHECK_ERROR", repr(error))
        next_public_recheck = time.ticks_add(
            now,
            PUBLIC_RECHECK_INTERVAL_MS,
        )


def poll_stress_heartbeat():
    global next_stress_heartbeat
    now = time.ticks_ms()
    if time.ticks_diff(now, next_stress_heartbeat) < 0:
        return
    elapsed = time.ticks_diff(now, stress_started) // 1000
    emit(
        "UNIFIED_CORE2_STRESS_HEARTBEAT",
        elapsed,
        psram_sweeps,
        http_rechecks,
        public_rechecks,
    )
    next_stress_heartbeat = time.ticks_add(
        now,
        STRESS_HEARTBEAT_INTERVAL_MS,
    )


def start_ble_server():
    from bleuart import BLEUARTServer

    # Test-only lifecycle probe; the production BLE server does not
    # automatically re-advertise after a peer disconnect.
    class ReconnectProbeBLEUARTServer(BLEUARTServer):
        def __init__(self, *args, **kwargs):
            self._readvertise_at = None
            super().__init__(*args, **kwargs)

        def _irq(self, event, data):
            if event == 2:
                conn_handle = data[0]
                self._connections.discard(conn_handle)
                self._readvertise_at = time.ticks_add(
                    time.ticks_ms(),
                    500,
                )
                emit("UNIFIED_CORE2_BLE_DISCONNECTED", conn_handle)
                return
            super()._irq(event, data)

        def poll_readvertise(self):
            if self._readvertise_at is None:
                return
            if (
                time.ticks_diff(
                    self._readvertise_at,
                    time.ticks_ms(),
                )
                > 0
            ):
                return
            self._readvertise_at = None
            try:
                self._advertise()
                emit("UNIFIED_CORE2_BLE_READVERTISED")
            except Exception as error:
                emit(
                    "UNIFIED_CORE2_BLE_READVERTISE_ERROR",
                    repr(error),
                )

    server = ReconnectProbeBLEUARTServer(name=BLE_NAME, verbose=True)

    def on_receive():
        payload = bytes(server.read())
        emit("UNIFIED_CORE2_BLE_RX", payload)
        server.write(b"ACK:" + payload)
        emit("UNIFIED_CORE2_BLE_ACK_SENT")

    server.irq(on_receive)
    emit("UNIFIED_CORE2_BLE_READY")
    return server


def main():
    global log_uart, psram_next_sweep
    global next_http_recheck, next_public_recheck
    global next_stress_heartbeat, stress_started

    from machine import I2C, Pin
    from rtc_probe import check_pcf8563

    M5.begin()
    emit("UNIFIED_CORE2_MAIN")
    emit("UNIFIED_CORE2_BOARD", M5.getBoard())
    emit(
        "UNIFIED_CORE2_DISPLAY",
        M5.Display.width(),
        M5.Display.height(),
    )
    emit("UNIFIED_CORE2_IO_CONFIG_READY")
    time.sleep_ms(1500)

    try:
        probe_psram()
        state["psram"] = "alloc"
    except Exception as error:
        state["psram"] = "fail"
        emit("UNIFIED_CORE2_PSRAM_ERROR", repr(error))

    try:
        state["power"] = (
            Power.getType(),
            Power.getBatteryVoltage(),
        )
        emit("UNIFIED_CORE2_POWER", *state["power"])
    except Exception as error:
        emit("UNIFIED_CORE2_POWER_ERROR", repr(error))

    try:
        imu_type = Imu.getType()
        accel = Imu.getAccel()
        gyro = Imu.getGyro()
        state["imu"] = "pass"
        emit("UNIFIED_CORE2_IMU", imu_type)
        emit("UNIFIED_CORE2_ACCEL", *accel)
        emit("UNIFIED_CORE2_GYRO", *gyro)
    except Exception as error:
        state["imu"] = "fail"
        emit("UNIFIED_CORE2_IMU_ERROR", repr(error))

    try:
        rtc = check_pcf8563(
            I2C(1, scl=Pin(22), sda=Pin(21), freq=100000)
        )
        state["rtc"] = "pass"
        emit("UNIFIED_CORE2_RTC", *rtc)
    except Exception as error:
        state["rtc"] = "fail"
        emit("UNIFIED_CORE2_RTC_ERROR", repr(error))

    try:
        i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
        chip_id = int.from_bytes(i2c.readfrom_mem(0x40, 0xFF, 2), "big")
        bus_raw = int.from_bytes(i2c.readfrom_mem(0x40, 0x02, 2), "big")
        shunt_raw = int.from_bytes(i2c.readfrom_mem(0x40, 0x01, 2), "big")
        emit("UNIFIED_CORE2_INA3221", hex(chip_id), bus_raw, shunt_raw)
        if chip_id != 0x3220 or bus_raw != 600 or shunt_raw != 60:
            raise RuntimeError("INA3221 register mismatch")
        state["ina"] = "pass"
    except Exception as error:
        state["ina"] = "fail"
        emit("UNIFIED_CORE2_INA3221_ERROR", repr(error))

    try:
        if not Mic.begin():
            raise RuntimeError("mic begin failed")
        samples = bytearray(6400)
        if not Mic.record(samples, 16000, False):
            raise RuntimeError("mic record failed")
        deadline = time.ticks_add(time.ticks_ms(), 2500)
        while (
            Mic.isRecording()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(20)
        Mic.end()
        nonzero = sum(1 for value in samples if value)
        peak = max(samples) - min(samples)
        emit("UNIFIED_CORE2_MIC", nonzero, peak)
        if nonzero < 100 or peak < 10:
            raise RuntimeError("mic samples are silent")
        state["mic"] = "pass"
    except Exception as error:
        state["mic"] = "fail"
        emit("UNIFIED_CORE2_MIC_ERROR", repr(error))

    try:
        if not Speaker.begin():
            raise RuntimeError("speaker begin failed")
        Speaker.setVolumePercentage(0.6)
        Speaker.tone(440, 1000)
        time.sleep_ms(500)
        if not Speaker.isRunning():
            raise RuntimeError("speaker stopped unexpectedly")
        state["audio"] = "pass"
        emit("UNIFIED_CORE2_AUDIO_PASS")
    except Exception as error:
        state["audio"] = "fail"
        emit("UNIFIED_CORE2_AUDIO_ERROR", repr(error))

    draw()

    server = None
    try:
        server = start_ble_server()
        state["ble"] = "pass"
    except Exception as error:
        state["ble"] = "fail"
        emit("UNIFIED_CORE2_BLE_ERROR", repr(error))

    try:
        station = network.WLAN(network.STA_IF)
        station.active(True)
        networks = station.scan()
        emit("UNIFIED_CORE2_WIFI_SCAN", len(networks))
        emit("UNIFIED_CORE2_WIFI_SCAN_RESULTS", repr(networks))
        error = station.connect(SSID)
        emit("UNIFIED_CORE2_WIFI_CONNECT_RETURNED", error)
        deadline = time.ticks_add(time.ticks_ms(), 20000)
        while (
            not station.isconnected()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(250)
        if not station.isconnected():
            raise RuntimeError("WiFi association timed out")
        address = station.ifconfig()[0]
        emit("UNIFIED_CORE2_WIFI_CONNECTED", address)
        state["wifi"] = "pass"
    except Exception as error:
        state["wifi"] = "fail"
        emit("UNIFIED_CORE2_WIFI_ERROR", repr(error))

    if state["wifi"] == "pass":
        try:
            state["http"] = probe_http()
            emit("UNIFIED_CORE2_HTTP_PASS")
        except Exception as error:
            state["http"] = "fail"
            emit("UNIFIED_CORE2_HTTP_ERROR", repr(error))
        try:
            probe_public()
            state["public"] = "pass"
        except Exception as error:
            state["public"] = "fail"
            emit("UNIFIED_CORE2_PUBLIC_HTTP_ERROR", repr(error))

    if state["audio"] == "pass":
        try:
            Speaker.tone(440, 15000)
            time.sleep_ms(100)
            if not Speaker.isRunning():
                raise RuntimeError("speaker hold stopped unexpectedly")
            emit("UNIFIED_CORE2_AUDIO_HOLD")
        except Exception as error:
            state["audio"] = "fail"
            emit("UNIFIED_CORE2_AUDIO_HOLD_ERROR", repr(error))

    draw()
    emit("UNIFIED_CORE2_READY")
    stress_started = time.ticks_ms()
    psram_next_sweep = time.ticks_add(
        stress_started,
        PSRAM_SWEEP_INTERVAL_MS,
    )
    next_http_recheck = time.ticks_add(
        stress_started,
        HTTP_RECHECK_INTERVAL_MS,
    )
    next_public_recheck = time.ticks_add(
        stress_started,
        PUBLIC_RECHECK_INTERVAL_MS,
    )
    next_stress_heartbeat = time.ticks_add(
        stress_started,
        STRESS_HEARTBEAT_INTERVAL_MS,
    )
    touch_seen = False
    while True:
        M5.update()
        poll_psram_sweep()
        poll_network_rechecks()
        poll_stress_heartbeat()
        if state["ble"] == "pass":
            server.poll_readvertise()
        if M5.Touch.getCount() > 0 and not touch_seen:
            touch_seen = True
            state["touch"] = "pass"
            emit(
                "UNIFIED_CORE2_TOUCH",
                M5.Touch.getX(),
                M5.Touch.getY(),
            )
            display = M5.Display
            display.fillRect(6, 6, 308, 24, display.COLOR.GREEN)
            display.setTextColor(display.COLOR.BLACK, display.COLOR.GREEN)
            display.setTextSize(2)
            display.setCursor(90, 12)
            display.print("TOUCH PASS")
        time.sleep_ms(20)


main()
