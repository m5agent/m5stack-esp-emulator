FONT_NAME = "Montserrat12"
PROFILES = {
    "atoms3r": {"native": (128, 128), "canvas": (128, 128), "rotation": 0,
                 "text": (4, 4, 120), "scale": 0.7, "font_height": 10},
    "sticks3": {"native": (135, 240), "canvas": (135, 240), "rotation": 0,
                "text": (4, 4, 127), "scale": 1.0, "font_height": 15},
    "stopwatch": {"native": (466, 466), "canvas": (468, 468), "rotation": 0,
                  "text": (110, 45, 246), "scale": 2.0, "font_height": 30},
}


def value_lines(case, values):
    if case == "color":
        return tuple("%s %d" % (name, value) for name, value in zip(("R", "G", "B", "C"), values))
    if case in ("tof", "ultrasonic-i2c"):
        return ("mm %.3f" % values[0], "cm %.3f" % values[1])
    if case == "ncir":
        return ("Amb %.4f C" % values[0], "Obj %.4f C" % values[1])
    if case == "heart":
        return ("IR %d" % values[0], "Red %d" % values[1])
    if case == "tvoc":
        return ("eCO2 %d ppm" % values[0], "TVOC %d ppb" % values[1],
                "H2 %d" % values[2], "Eth %d" % values[3])
    raise ValueError("unsupported sensor layout")


def worst_values(case):
    return {"color": (65535, 65535, 65535, 65535), "tof": (2000, 200),
            "ncir": (-40, -70), "heart": (65535, 65535),
            "tvoc": (60000, 60000, 65535, 65535), "ultrasonic-i2c": (4500, 450)}[case]


def planned_layout(device_id, case):
    profile = PROFILES[device_id]
    x, y, width = profile["text"]
    height = profile["font_height"]
    headers = (device_id, case)
    line_height = height + 1
    body_y = y + len(headers) * line_height + 2
    rows = len(value_lines(case, worst_values(case)))
    bottom = body_y + rows * line_height
    native_width, native_height = profile["native"]
    if not (0 <= x < x + width <= native_width and 0 <= y < bottom <= native_height):
        raise RuntimeError("sensor layout leaves native display")
    if device_id == "stopwatch":
        center = native_width / 2
        if any((cx - center) ** 2 + (cy - center) ** 2 > center ** 2
               for cx in (x, x + width) for cy in (y, bottom)):
            raise RuntimeError("sensor layout leaves native circle")
    return {"x": x, "y": y, "width": width, "headers": headers,
            "font_height": height, "line_height": line_height,
            "body_y": body_y, "body_rows": rows, "bottom": bottom}


def print_checked(screen, layout, text, y):
    if screen.textWidth(text) > layout["width"]:
        raise RuntimeError("actual sensor readout would wrap or clip")
    screen.setCursor(layout["x"], y)
    screen.print(text)


def initialize_display(screen, device_id, case, emit):
    profile = PROFILES[device_id]
    screen.setRotation(profile["rotation"])
    screen.setBrightness(255)
    screen.fillScreen(0xFFFFFF)
    screen.setTextColor(0x0282CB, 0xFFFFFF)
    emit("HOST_SENSOR_DEFAULT_FONT_HEIGHT", screen.fontHeight())
    screen.setFont(screen.FONTS.Montserrat12)
    screen.setTextSize(profile["scale"])
    layout = planned_layout(device_id, case)
    if screen.fontHeight() != layout["font_height"]:
        raise RuntimeError("actual font height differs from the explicit profile")
    if (screen.width(), screen.height()) != profile["canvas"]:
        raise RuntimeError("actual sensor canvas differs from host profile")
    guard_lines = layout["headers"] + value_lines(case, worst_values(case))
    if case == "ncir":
        guard_lines += value_lines(case, (125, 380))
    for text in guard_lines:
        if screen.textWidth(text) > layout["width"]:
            raise RuntimeError("actual font width exceeds native sensor readout")
    emit("HOST_SENSOR_FONT", FONT_NAME, profile["scale"], screen.fontHeight())
    emit("HOST_SENSOR_GEOMETRY", screen.width(), screen.height(), profile["rotation"])
    emit("HOST_SENSOR_LAYOUT", layout["x"], layout["y"], layout["width"], layout["body_y"],
         layout["line_height"], layout["body_rows"], layout["bottom"], len(layout["headers"]))
    for row, text in enumerate(layout["headers"]):
        print_checked(screen, layout, text, layout["y"] + row * layout["line_height"])
    return layout


def render_values(screen, layout, case, values):
    lines = value_lines(case, values)
    if len(lines) != layout["body_rows"]:
        raise RuntimeError("sensor readout row count changed")
    screen.fillRect(layout["x"], layout["body_y"], layout["width"],
                    layout["body_rows"] * layout["line_height"], 0xFFFFFF)
    for row, text in enumerate(lines):
        print_checked(screen, layout, text, layout["body_y"] + row * layout["line_height"])
