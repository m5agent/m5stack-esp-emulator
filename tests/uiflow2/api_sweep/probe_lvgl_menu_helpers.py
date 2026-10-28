"""Cross-object menu-page helper regression, using actual visible title labels."""
import json,time
import M5,m5ui,lvgl as lv
M5.begin();m5ui.init()
try:
    page=m5ui.M5Page(bg_c=0x0B1014);page.screen_load()
    menu=lv.menu(page);menu.set_size(260,180);first=lv.menu_page(menu,'First');menu.set_page(first)
    static='Static title'
    for method,text in [('set_page_title','Renamed'),('set_page_title_static',static)]:
        try:
            getattr(lv.menu,method)(first,text);menu.set_page(first)
            title=menu.get_main_header().get_child(1).get_text()
            print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.menu','method':method,'status':'STATE_PASS' if title==text else 'FAIL','actual':title,'oracle':'class namespace helper accepts the actual menu page and changes the real header label'}))
        except Exception as error:
            print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.menu','method':method,'status':'FAIL','error':repr(error),'oracle':'class namespace helper accepts actual menu_page argument'}))
    print('LVGL_MENU_HELPERS_DONE')
    while True:M5.update();time.sleep_ms(20)
finally:m5ui.deinit()
