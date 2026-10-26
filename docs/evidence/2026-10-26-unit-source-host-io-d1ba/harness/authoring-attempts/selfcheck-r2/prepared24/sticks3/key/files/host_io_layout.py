"""Native host IO text layout; only the drawing scaffold is adapted."""
FONT_NAME = "Montserrat12"
PROFILES = {
    "atoms3r": {"native": (128, 128), "canvas": (128, 128), "rotation": 0,
                 "text": (4, 4, 120), "scale": .7, "font_height": 10},
    "sticks3": {"native": (135, 240), "canvas": (135, 240), "rotation": 0,
                "text": (4, 4, 127), "scale": 1., "font_height": 15},
    "stopwatch": {"native": (466, 466), "canvas": (468, 468), "rotation": 0,
                  "text": (110, 45, 246), "scale": 2., "font_height": 30},
}


def planned_layout(device_id, case):
    profile = PROFILES[device_id]
    x, y, width = profile["text"]
    height = profile["font_height"]
    headers = (device_id, case)
    line_height = height + 1
    body_y = y + len(headers) * line_height + 2
    rows = 8
    bottom = body_y + rows * line_height
    w, h = profile["native"]
    if not (0 <= x < x + width <= w and 0 <= y < bottom <= h):
        raise RuntimeError("IO layout leaves native frame")
    if device_id == "stopwatch":
        c = w / 2
        if any((px-c)**2 + (py-c)**2 > c*c for px in (x, x+width) for py in (y, bottom)):
            raise RuntimeError("IO layout leaves native circle")
    return {"x": x, "y": y, "width": width, "headers": headers,
            "font_height": height, "line_height": line_height, "body_y": body_y,
            "body_rows": rows, "bottom": bottom}


def initialize_display(screen, device_id, case, emit):
    profile = PROFILES[device_id]
    screen.setRotation(profile["rotation"])
    screen.setBrightness(255)
    screen.fillScreen(0xFFFFFF)
    screen.setTextColor(0x0282CB, 0xFFFFFF)
    emit("HOST_IO_DEFAULT_FONT_HEIGHT", screen.fontHeight())
    screen.setFont(screen.FONTS.Montserrat12)
    screen.setTextSize(profile["scale"])
    layout = planned_layout(device_id, case)
    if screen.fontHeight() != layout["font_height"] or (screen.width(), screen.height()) != profile["canvas"]:
        raise RuntimeError("actual IO font or canvas differs from profile")
    for row, text in enumerate(layout["headers"]):
        if screen.textWidth(text) > layout["width"]:
            raise RuntimeError("actual IO header exceeds native frame")
        screen.setCursor(layout["x"], layout["y"] + row * layout["line_height"])
        screen.print(text)
    emit("HOST_IO_FONT", FONT_NAME, profile["scale"], screen.fontHeight())
    emit("HOST_IO_GEOMETRY", screen.width(), screen.height(), profile["rotation"])
    emit("HOST_IO_LAYOUT", layout["x"], layout["y"], layout["width"], layout["body_y"],
         layout["line_height"], layout["body_rows"], layout["bottom"], len(layout["headers"]))
    return layout


def wrap_text(screen, text, width, rows):
    """Measure every character; never truncate a value or fake font metrics."""
    lines, current = [], ""
    for char in str(text):
        if char == "\n" or screen.textWidth(current + char) > width:
            if not current and char != "\n":
                raise RuntimeError("actual IO glyph exceeds available width")
            lines.append(current)
            current = "" if char == "\n" else char
        else:
            current += char
    if current or not lines:
        lines.append(current)
    if len(lines) > rows or any(screen.textWidth(line) > width for line in lines):
        raise RuntimeError("actual IO value exceeds native readout rows")
    return lines


def render_text(screen, layout, value):
    lines = wrap_text(screen, value, layout["width"], layout["body_rows"])
    screen.fillRect(layout["x"], layout["body_y"], layout["width"],
                    layout["body_rows"] * layout["line_height"], 0xFFFFFF)
    for row, line in enumerate(lines):
        screen.setCursor(layout["x"], layout["body_y"] + row * layout["line_height"])
        screen.print(line)
