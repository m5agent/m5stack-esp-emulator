import M5
import sys
import time

try:
    print("CORE2_STARTUP:lvgl:BEGIN")
    M5.begin()
    import lvgl as lv
    import m5ui
    m5ui.init()
    print("CORE2_STARTUP:lvgl:INIT_READY")
    page = m5ui.M5Page(bg_c=0x101418)
    label = m5ui.M5Label("Core2 LVGL first frame", x=12, y=24,
                        text_c=0xFFFFFF, bg_c=0x101418,
                        font=lv.font_montserrat_18, parent=page)
    page.screen_load()
    print("CORE2_STARTUP:lvgl:READY")
    for step in range(150):
        M5.update()
        time.sleep_ms(20)
    print("CORE2_STARTUP:lvgl:DONE")
except Exception as error:
    print("CORE2_STARTUP:lvgl:ERROR")
    sys.print_exception(error)
    raise
