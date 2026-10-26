FONT_NAME = "Montserrat12"
DISPLAY_PROFILES = {
    "atoms3r": {"native": (128, 128), "canvas": (128, 128), "text": (4, 4, 120),
                 "text_size": 0.7, "font_height": 10},
    "sticks3": {"native": (135, 240), "canvas": (135, 240), "text": (4, 4, 127),
                "text_size": 1.0, "font_height": 15},
    "stopwatch": {"native": (466, 466), "canvas": (468, 468), "text": (110, 45, 246),
                  "text_size": 2.0, "font_height": 30},
}


def value_lines(case, value):
    if case == "joystick-v11":
        return ("x %d" % value[0], "y %d" % value[1], "button %d" % value[2])
    if case == "encoder":
        return ("count %d" % value[0], "pressed %d" % value[1])
    if case == "8encoder":
        counts, pressed, switch = value
        return tuple("%d %d" % (index + 1, count) for index, count in enumerate(counts)) + (
            "P " + "".join(str(bit) for bit in pressed), "SW %d" % switch)
    if case == "cardkb":
        return ("key %d" % value,)
    if value is None:
        return ("No card",)
    return ("UID",) + tuple(value[index:index + 10] for index in range(0, len(value), 10))


def worst_value(case):
    return {
        "joystick-v11": (255, 255, 1),
        "encoder": (-32768, 1),
        "8encoder": ([-2147483648] * 8, [1] * 8, 1),
        "cardkb": 255,
        "rfid2": "04010203040506070809",
    }[case]


def checked_layout(device_id, case, font_height, text_width):
    """Use runtime fontHeight/textWidth; never infer a glyph from its name."""
    profile = DISPLAY_PROFILES[device_id]
    if font_height != profile["font_height"]:
        raise RuntimeError("font metrics differ from the explicitly pinned UIFlow2 2.5.3 profile")
    x, y, width = profile["text"]
    combined = device_id + " " + case
    headers = (combined,) if text_width(combined) <= width else (device_id, case)
    lines = value_lines(case, worst_value(case))
    if any(text_width(text) > width for text in headers + lines):
        raise RuntimeError("actual font width exceeds native readout bounds")
    # fontHeight truncates scaled height. One extra pixel covers the fractional
    # font-cell edge and keeps adjacent rows separate (10 -> 11 on Atom).
    line_height = font_height + 1
    body_y = y + len(headers) * line_height + 2
    body_rows = 10 if case == "8encoder" else len(lines)
    bottom = body_y + body_rows * line_height
    native_width, native_height = profile["native"]
    if not (0 <= x < x + width <= native_width and 0 <= y < bottom <= native_height):
        raise RuntimeError("native readout rectangle would be clipped")
    if device_id == "stopwatch":
        # Check native 466px circular geometry, not the larger 468px canvas.
        center, radius = native_width / 2, native_width / 2
        if any((cx - center) ** 2 + (cy - center) ** 2 > radius ** 2
               for cx in (x, x + width) for cy in (y, bottom)):
            raise RuntimeError("readout rectangle leaves the native round display")
    return {"x": x, "y": y, "width": width, "headers": headers, "font_height": font_height,
            "line_height": line_height, "body_y": body_y, "body_rows": body_rows, "bottom": bottom}


def print_checked(screen, layout, text, y):
    if screen.textWidth(text) > layout["width"]:
        raise RuntimeError("actual readout text would wrap or clip")
    screen.setCursor(layout["x"], y)
    screen.print(text)
