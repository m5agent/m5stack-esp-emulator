from host_control_layout import DISPLAY_PROFILES, FONT_NAME, checked_layout, print_checked, value_lines
DISPLAY_PROFILES["cores3"] = {"native": (320, 240), "canvas": (320, 240), "text": (6, 6, 308), "text_size": 1.0, "font_height": 15}

def prepare_display(screen, case, emit):
    screen.setRotation(1)
    screen.setBrightness(255)
    screen.fillScreen(0xFFFFFF)
    screen.setTextColor(0x0282CB, 0xFFFFFF)
    screen.setFont(screen.FONTS.Montserrat12)
    screen.setTextSize(1.0)
    layout = checked_layout("cores3", case, screen.fontHeight(), screen.textWidth)
    emit("SOURCE_CONTROL_GEOMETRY", screen.width(), screen.height(), 1)
    emit("SOURCE_CONTROL_FONT", FONT_NAME, 1.0, screen.fontHeight())
    emit("SOURCE_CONTROL_LAYOUT", layout["x"], layout["y"], layout["width"], layout["body_y"], layout["line_height"], layout["body_rows"], layout["bottom"], len(layout["headers"]))
    if (screen.width(), screen.height()) != (320, 240):
        raise RuntimeError("CoreS3 native display geometry differs")
    for index, text in enumerate(layout["headers"]):
        print_checked(screen, layout, text, layout["y"] + index * layout["line_height"])
    return layout

def draw_display(screen, layout, case, value):
    lines = value_lines(case, value)
    if len(lines) > layout["body_rows"]:
        raise RuntimeError("Unit readout exceeds native display rows")
    screen.fillRect(layout["x"], layout["body_y"], layout["width"], layout["body_rows"] * layout["line_height"], 0xFFFFFF)
    for index, text in enumerate(lines):
        print_checked(screen, layout, text, layout["body_y"] + index * layout["line_height"])
