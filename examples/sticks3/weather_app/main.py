"""StickS3 multi-city weather dashboard with animated state feedback."""

import gc
import json
import network
import socket
import time

import M5
from M5 import *


CITIES = (
    {
        "name": "Shenzhen",
        "label": "SZ",
        "latitude": 22.5431,
        "longitude": 114.0579,
    },
    {
        "name": "Shanghai",
        "label": "SH",
        "latitude": 31.2304,
        "longitude": 121.4737,
    },
    {
        "name": "Beijing",
        "label": "BJ",
        "latitude": 39.9042,
        "longitude": 116.4074,
    },
)

WEATHER_HOST = "api.open-meteo.com"
WEATHER_IPV4_FALLBACK = "188.40.99.226"
HTTP_TIMEOUT_SECONDS = 12
REFRESH_INTERVAL_MS = 15 * 60 * 1000
ANIMATION_INTERVAL_MS = 125
WIFI_TIMEOUT_MS = 20 * 1000
WIFI_FALLBACK_SSID = "myssid"

BG = 0x080C10
SURFACE = 0x131B21
SURFACE_ALT = 0x1A242B
LINE = 0x2B3942
TEXT = 0xF4F7F8
MUTED = 0x8FA0AA
ACCENT = 0x39C6E0
SUCCESS = 0x58D49B
WARNING = 0xFFB85A
ERROR = 0xFF6B6B
SUN = 0xFFCF63
CLOUD = 0xC9D2D6
RAIN = 0x4FA9FF

STATE_LOADING = 0
STATE_READY = 1
STATE_ERROR = 2

display = None
screen = None
header_canvas = None
motion_canvas = None
dot_canvas = None
station = None
font_small = None
font_body = None
font_large = None

city_index = 0
state = STATE_LOADING
weather = None
error_text = ""
unit_f = False
last_refresh_ms = None
last_animation_ms = 0
animation_phase = 0


def emit(*parts):
    print("APP", *parts)


def now_ms():
    return time.ticks_ms()


def text_width(canvas, text):
    try:
        return canvas.textWidth(str(text))
    except Exception:
        return len(str(text)) * 6


def draw_text(canvas, text, x, y, font, color, background=BG, align=0):
    canvas.setFont(font)
    canvas.setTextColor(color, background)
    if align < 0:
        canvas.drawRightString(str(text), x, y)
    elif align > 0:
        canvas.drawCenterString(str(text), x, y)
    else:
        canvas.drawString(str(text), x, y)


def draw_centered(canvas, text, y, font, color, background=BG):
    draw_text(canvas, text, 67, y, font, color, background, 1)


def draw_right(canvas, text, x, y, font, color, background=BG):
    draw_text(canvas, text, x, y, font, color, background, -1)


def draw_header(canvas, city_name, status, status_color, background=BG):
    canvas.fillScreen(background)
    canvas.fillRect(0, 0, 135, 2, ACCENT)
    draw_text(canvas, city_name, 10, 9, font_body, TEXT, background)
    draw_text(canvas, status, 10, 32, font_small, MUTED, background)

    radius = 3 if (animation_phase // 4) & 1 else 2
    canvas.drawCircle(117, 14, 6, LINE)
    canvas.fillCircle(117, 14, radius, status_color)
    canvas.drawLine(8, 51, 126, 51, LINE)


def weather_name(code):
    if code == 0:
        return "CLEAR"
    if code in (1, 2):
        return "PART CLOUDY"
    if code == 3:
        return "CLOUDY"
    if code in (45, 48):
        return "FOG"
    if 51 <= code <= 57:
        return "DRIZZLE"
    if 61 <= code <= 67:
        return "RAIN"
    if 71 <= code <= 77:
        return "SNOW"
    if 80 <= code <= 82:
        return "SHOWERS"
    if 95 <= code <= 99:
        return "STORM"
    return "WEATHER"


def unit_label():
    return "F" if unit_f else "C"


def converted(value):
    return value * 9.0 / 5.0 + 32.0 if unit_f else value


def draw_sun(canvas, cx, cy, pulse):
    radius = 9 + pulse
    canvas.fillCircle(cx, cy, radius, SUN)
    outer = 21 + pulse
    inner = 15
    canvas.drawLine(cx - outer, cy, cx - inner, cy, SUN)
    canvas.drawLine(cx + inner, cy, cx + outer, cy, SUN)
    canvas.drawLine(cx, cy - outer, cx, cy - inner, SUN)
    canvas.drawLine(cx, cy + inner, cx, cy + outer, SUN)
    canvas.drawLine(cx - 14, cy - 14, cx - 10, cy - 10, SUN)
    canvas.drawLine(cx + 10, cy - 10, cx + 14, cy - 14, SUN)
    canvas.drawLine(cx - 14, cy + 14, cx - 10, cy + 10, SUN)
    canvas.drawLine(cx + 10, cy + 10, cx + 14, cy + 14, SUN)


def draw_cloud(canvas, cx, cy, drift=0):
    cx += drift
    canvas.fillCircle(cx - 11, cy, 7, CLOUD)
    canvas.fillCircle(cx, cy - 5, 10, CLOUD)
    canvas.fillCircle(cx + 12, cy, 8, CLOUD)
    canvas.fillRoundRect(cx - 18, cy, 37, 10, 5, CLOUD)


def draw_weather_icon(canvas, code, is_day, phase):
    canvas.fillScreen(BG)
    pulse = (phase + 1) % 3
    drift = (-2, 0, 2, 0)[phase % 4]

    if code == 0:
        if is_day:
            draw_sun(canvas, 28, 27, pulse)
        else:
            canvas.fillCircle(29, 27, 13, CLOUD)
            canvas.fillCircle(36, 22, 13, BG)
        return

    if code in (1, 2):
        draw_sun(canvas, 20, 20, pulse)
        draw_cloud(canvas, 31, 31, drift)
        return

    if code == 3:
        draw_cloud(canvas, 28, 25, drift)
        return

    draw_cloud(canvas, 28, 21, drift)
    if 71 <= code <= 77 or 85 <= code <= 86:
        for x in (19, 29, 39):
            canvas.drawLine(x - 2, 39, x + 2, 39, CLOUD)
            canvas.drawLine(x, 37, x, 41, CLOUD)
    elif 95 <= code <= 99:
        canvas.drawLine(31, 35, 25, 44, SUN)
        canvas.drawLine(25, 44, 30, 44, SUN)
        canvas.drawLine(30, 44, 25, 51, SUN)
    else:
        offset = (phase * 3) % 9
        for index, x in enumerate((19, 29, 39)):
            y = 37 + ((offset + index * 3) % 9)
            canvas.drawLine(x, y, x - 2, y + 5, RAIN)


def draw_loading_spinner(phase):
    points = (
        (28, 5),
        (41, 12),
        (48, 28),
        (41, 44),
        (28, 51),
        (15, 44),
        (8, 28),
        (15, 12),
    )
    motion_canvas.fillScreen(BG)
    for index, point in enumerate(points):
        distance = (index - phase) % 8
        color = ACCENT if distance == 0 else 0x23313A if distance < 4 else 0x151F25
        motion_canvas.fillCircle(point[0], point[1], 3 if distance == 0 else 2, color)
    motion_canvas.push(39, 77)


def draw_loading_page():
    draw_header(
        screen,
        CITIES[city_index]["name"],
        "UPDATING",
        ACCENT,
    )
    draw_centered(screen, "CONNECTING", 139, font_body, TEXT)
    draw_centered(screen, "OPEN-METEO", 158, font_small, MUTED)
    draw_action_bar()
    screen.push(0, 0)
    draw_loading_spinner(animation_phase)


def draw_error_page():
    draw_header(screen, CITIES[city_index]["name"], "OFFLINE", ERROR)
    screen.drawCircle(67, 91, 26, LINE)
    screen.drawCircle(67, 91, 25, LINE)
    draw_cloud(screen, 67, 86)
    screen.drawLine(60, 111, 74, 111, ERROR)
    draw_centered(screen, "NO WEATHER DATA", 132, font_body, ERROR)
    draw_centered(screen, error_text[:20], 154, font_small, MUTED)
    draw_action_bar()
    screen.push(0, 0)


def draw_action_bar():
    screen.fillRoundRect(8, 213, 56, 21, 7, SURFACE_ALT)
    screen.fillRoundRect(71, 213, 56, 21, 7, SURFACE_ALT)
    screen.setFont(font_small)
    screen.setTextColor(TEXT, SURFACE_ALT)
    screen.drawCenterString("A  CITY", 36, 218)
    screen.drawCenterString("B  C/F", 99, 218)


def draw_temperature(canvas, value):
    number = "%d" % int(round(value))
    draw_text(canvas, number, 9, 61, font_large, TEXT)
    number_width = text_width(canvas, number)
    unit_x = min(69, 11 + number_width)
    canvas.drawCircle(unit_x + 2, 66, 2, TEXT)
    draw_text(
        canvas,
        unit_label(),
        unit_x + 5,
        82,
        font_small,
        MUTED,
    )


def draw_metric_card(x, label, value):
    screen.fillRoundRect(x, 148, 57, 31, 6, SURFACE)
    draw_text(screen, label, x + 7, 153, font_small, MUTED, SURFACE)
    draw_text(screen, value, x + 7, 166, font_body, TEXT, SURFACE)


def draw_range(data):
    low = converted(data["low"])
    high = converted(data["high"])
    current = converted(data["temperature"])
    span = high - low
    ratio = 0.5 if abs(span) < 0.1 else (current - low) / span
    ratio = max(0.0, min(1.0, ratio))
    x1 = 28
    x2 = 107
    dot_x = int(x1 + (x2 - x1) * ratio)

    draw_text(screen, "TODAY RANGE", 9, 185, font_small, MUTED)
    draw_text(screen, "%d" % int(round(low)), 9, 198, font_small, MUTED)
    draw_right(
        screen,
        "%d" % int(round(high)),
        126,
        198,
        font_small,
        MUTED,
    )
    screen.drawLine(x1, 204, x2, 204, LINE)
    screen.drawLine(x1, 204, dot_x, 204, ACCENT)
    screen.drawCircle(dot_x, 204, 5, BG)
    screen.fillCircle(dot_x, 204, 3, ACCENT)


def draw_ready_page():
    data = weather
    draw_header(screen, CITIES[city_index]["name"], "LIVE WEATHER", SUCCESS)
    draw_temperature(screen, converted(data["temperature"]))
    draw_text(screen, weather_name(data["code"]), 9, 104, font_body, ACCENT)
    draw_text(
        screen,
        "FEELS %d%s" % (
            int(round(converted(data["apparent"]))),
            unit_label(),
        ),
        9,
        126,
        font_small,
        MUTED,
    )

    draw_metric_card(8, "HUM", "%d%%" % int(round(data["humidity"])))
    draw_metric_card(70, "WIND", "%.0f" % data["wind"])
    draw_range(data)
    draw_action_bar()
    screen.push(0, 0)


def draw_page():
    if state == STATE_READY and weather is not None:
        screen.fillScreen(BG)
        draw_ready_page()
        animate_weather()
    elif state == STATE_ERROR:
        draw_error_page()
    else:
        draw_loading_page()
    animate_status_dot()


def animate_weather():
    if state != STATE_READY or weather is None:
        return
    draw_weather_icon(
        motion_canvas,
        weather["code"],
        weather["is_day"],
        animation_phase,
    )
    motion_canvas.push(77, 61)


def animate_status_dot():
    color = ERROR if state == STATE_ERROR else ACCENT if state == STATE_LOADING else SUCCESS
    dot_canvas.fillScreen(BG)
    dot_canvas.fillRect(0, 0, 18, 2, ACCENT)
    radius = 3 if (animation_phase // 4) & 1 else 2
    dot_canvas.drawCircle(9, 14, 7, LINE)
    dot_canvas.fillCircle(9, 14, radius, color)
    dot_canvas.push(108, 0)


def animate():
    global animation_phase
    animation_phase = (animation_phase + 1) & 15
    if state == STATE_READY:
        animate_weather()
    elif state == STATE_LOADING:
        draw_loading_spinner(animation_phase & 7)
    animate_status_dot()


def animate_to_loading():
    global animation_phase
    for _ in range(4):
        M5.update()
        animation_phase = (animation_phase + 1) & 7
        draw_loading_spinner(animation_phase)
        animate_status_dot()
        time.sleep_ms(70)


def animate_city_change(old_name, new_name):
    global animation_phase
    for index in range(1, 9):
        progress = index / 8.0
        eased = 1.0 - (1.0 - progress) * (1.0 - progress)
        header_canvas.fillScreen(BG)
        header_canvas.fillRect(0, 0, 135, 2, ACCENT)
        old_x = 10 - int(110 * eased)
        new_x = 145 - int(135 * eased)
        draw_text(header_canvas, old_name, old_x, 9, font_body, TEXT)
        draw_text(header_canvas, new_name, new_x, 9, font_body, TEXT)
        draw_text(
            header_canvas,
            "SWITCHING CITY",
            10,
            32,
            font_small,
            ACCENT,
        )
        header_canvas.drawLine(8, 51, 126, 51, LINE)
        header_canvas.push(0, 0)
        animation_phase = (animation_phase + 1) & 7
        time.sleep_ms(34)


def connect_wifi():
    global station
    station = network.WLAN(network.STA_IF)
    station.active(True)
    started = now_ms()
    while not station.isconnected() and time.ticks_diff(now_ms(), started) < 1200:
        M5.update()
        animate_to_loading()

    if not station.isconnected():
        try:
            station.connect(WIFI_FALLBACK_SSID)
        except Exception as error:
            emit("WIFI_CONNECT_ERROR", repr(error))

        deadline = time.ticks_add(now_ms(), WIFI_TIMEOUT_MS)
        while not station.isconnected():
            M5.update()
            animate_to_loading()
            if time.ticks_diff(deadline, now_ms()) <= 0:
                raise RuntimeError("WiFi timeout")
            time.sleep_ms(80)

    emit("WIFI_CONNECTED", station.ifconfig()[0])


def weather_path(city):
    return (
        "/v1/forecast"
        "?latitude=%.4f&longitude=%.4f"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        "is_day,weather_code,wind_speed_10m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min"
        "&timezone=auto&forecast_days=1"
    ) % (city["latitude"], city["longitude"])


def http_get(path, ipv4=None):
    address = None
    if ipv4:
        address = (ipv4, 80)
        emit("DNS_FALLBACK", WEATHER_HOST, ipv4)
    else:
        for info in socket.getaddrinfo(WEATHER_HOST, 80):
            if info[0] == socket.AF_INET:
                address = info[-1]
                emit("DNS_OK", WEATHER_HOST, address[0])
                break
    if address is None:
        raise RuntimeError("DNS failed")

    sock = socket.socket()
    sock.settimeout(HTTP_TIMEOUT_SECONDS)
    try:
        sock.connect(address)
        request = (
            "GET %s HTTP/1.0\r\n"
            "Host: %s\r\n"
            "Accept: application/json\r\n"
            "Connection: close\r\n\r\n"
        ) % (path, WEATHER_HOST)
        sock.send(request.encode())
        chunks = []
        total = 0
        while True:
            block = sock.recv(1024)
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > 32768:
                raise RuntimeError("Response too large")
        response = b"".join(chunks)
    finally:
        sock.close()

    split = response.find(b"\r\n\r\n")
    if split < 0:
        raise RuntimeError("Invalid HTTP")
    header = response[:split].decode()
    body = response[split + 4 :]
    status = int(header.split("\r\n", 1)[0].split(" ")[1])
    emit("HTTP", status, len(body))
    if status != 200:
        raise RuntimeError("HTTP %d" % status)
    return body


def fetch_weather(city):
    try:
        body = http_get(weather_path(city))
    except OSError as error:
        emit("DNS_RETRY", repr(error))
        body = http_get(weather_path(city), WEATHER_IPV4_FALLBACK)

    payload = json.loads(body.decode())
    current = payload["current"]
    daily = payload["daily"]
    data = {
        "temperature": float(current["temperature_2m"]),
        "humidity": float(current["relative_humidity_2m"]),
        "apparent": float(current["apparent_temperature"]),
        "wind": float(current["wind_speed_10m"]),
        "is_day": int(current["is_day"]),
        "code": int(current["weather_code"]),
        "high": float(daily["temperature_2m_max"][0]),
        "low": float(daily["temperature_2m_min"][0]),
    }
    emit(
        "WEATHER_OK",
        city["name"],
        "temp=%.1f" % data["temperature"],
        "hum=%.0f" % data["humidity"],
        "code=%d" % data["code"],
    )
    return data


def refresh_weather():
    global state, weather, error_text, last_refresh_ms
    city = CITIES[city_index]
    state = STATE_LOADING
    weather = None
    error_text = ""
    emit("CITY", city["name"])
    draw_page()
    animate_to_loading()

    try:
        connect_wifi()
        weather = fetch_weather(city)
        state = STATE_READY
        draw_page()
        emit("READY", city["name"])
    except Exception as error:
        error_text = str(error)
        state = STATE_ERROR
        draw_page()
        emit("WEATHER_ERROR", city["name"], repr(error))
    finally:
        last_refresh_ms = now_ms()
        gc.collect()


def next_city():
    global city_index
    previous = CITIES[city_index]["name"]
    city_index = (city_index + 1) % len(CITIES)
    current = CITIES[city_index]["name"]
    emit("BUTTON_A", previous, "->", current)
    animate_city_change(previous, current)
    refresh_weather()


def toggle_unit():
    global unit_f
    unit_f = not unit_f
    emit("BUTTON_B", "F" if unit_f else "C")
    if state == STATE_READY:
        draw_page()


def setup():
    global display, screen, header_canvas, motion_canvas, dot_canvas
    global font_small, font_body, font_large

    M5.begin()
    display = M5.Display
    display.setRotation(0)
    display.setBrightness(255)

    font_small = Widgets.FONTS.DejaVu12
    font_body = Widgets.FONTS.DejaVu18
    font_large = Widgets.FONTS.DejaVu40

    screen = M5.Lcd.newCanvas(135, 240, 16, True)
    header_canvas = M5.Lcd.newCanvas(135, 56, 16, True)
    motion_canvas = M5.Lcd.newCanvas(56, 56, 16, True)
    dot_canvas = M5.Lcd.newCanvas(18, 18, 16, True)

    emit("START", display.width(), display.height())
    refresh_weather()


def loop():
    global last_animation_ms

    M5.update()
    if BtnA.wasClicked() and state != STATE_LOADING:
        next_city()
    if BtnB.wasClicked():
        toggle_unit()

    now = now_ms()
    if time.ticks_diff(now, last_animation_ms) >= ANIMATION_INTERVAL_MS:
        last_animation_ms = now
        animate()

    if (
        state == STATE_READY
        and last_refresh_ms is not None
        and time.ticks_diff(now, last_refresh_ms) >= REFRESH_INTERVAL_MS
    ):
        refresh_weather()

    time.sleep_ms(10)


try:
    setup()
    while True:
        loop()
except Exception as error:
    emit("FATAL", repr(error))
