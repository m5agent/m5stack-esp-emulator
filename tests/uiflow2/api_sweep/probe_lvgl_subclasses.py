"""Public label methods must survive an unregistered native list-text subclass."""
import M5,m5ui,lvgl as lv,time,json
M5.begin();m5ui.init()
try:
    page=m5ui.M5Page(bg_c=0x0B1014);page.screen_load();listing=lv.list(page);text=listing.add_text('Section');label=lv.label(page)
    before=text.get_class();is_label=text.has_class(label.get_class())
    try:
        caption=text.get_text();text.set_text('Updated section');actual=text.get_text();ok=is_label and caption=='Section' and actual=='Updated section' and text.get_class()==before
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.list','method':'add_text','status':'STATE_PASS' if ok else 'FAIL','oracle':'private native subclass retains label methods and original native class identity','before':caption,'after':actual}))
    except Exception as error:
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.list','method':'add_text','status':'FAIL','oracle':'private native subclass must retain label methods','error':repr(error),'native_is_label':is_label}))
    print('M5EMU_LVGL_SUBCLASSES_DONE')
    while True:M5.update();time.sleep_ms(20)
finally:m5ui.deinit()
