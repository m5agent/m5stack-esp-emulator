"""Exact options and callback/user-data identity regressions for stock/candidate."""
import json,time,sys
import M5,m5ui,lvgl as lv

def emit(target,method,ok,domain,**details):
    print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.'+target,'method':method,'status':'STATE_PASS' if ok else 'FAIL','argument_domain':domain,'details':details}))

def callbacks(target,obj,index_remove):
    baseline=obj.get_event_count();hits=[];data_a={'nonce':'A'};data_b={'nonce':'B'}
    def first(e):hits.append(('first',e.get_user_data().__cast__()['nonce']))
    def second(e):hits.append(('second',e.get_user_data().__cast__()['nonce']))
    a=obj.add_event_cb(first,lv.EVENT.VALUE_CHANGED,data_a);b=obj.add_event_cb(second,lv.EVENT.VALUE_CHANGED,data_a);c=obj.add_event_cb(first,lv.EVENT.VALUE_CHANGED,data_b)
    a=obj.get_event_dsc(baseline);descriptor_identity=a.get_user_data().__cast__() is data_a
    obj.send_event(lv.EVENT.VALUE_CHANGED,None)
    emit(target,'add_event_cb',hits==[('first','A'),('second','A'),('first','B')],'shared-user-data-multiple-callbacks',hits=hits)
    emit('event_dsc_t','get_user_data',descriptor_identity,'caller-dictionary-identity')
    removed=obj.remove_event_cb_with_user_data(first,data_a);hits[:]=[];obj.send_event(lv.EVENT.VALUE_CHANGED,None)
    emit(target,'remove_event_cb_with_user_data',removed==1 and obj.get_event_count()==baseline+2 and hits==[('second','A'),('first','B')],'exact-callback-and-dictionary-identity',removed=removed,hits=hits,count=obj.get_event_count())
    for _ in range(obj.get_event_count()-baseline):getattr(obj,index_remove)(baseline)
    # None data must retain its own original identity and must not remove B.
    def no_data(e):hits.append(('none',e.get_user_data() is None))
    obj.add_event_cb(no_data,lv.EVENT.VALUE_CHANGED,None);obj.add_event_cb(first,lv.EVENT.VALUE_CHANGED,data_b)
    hits[:]=[];obj.send_event(lv.EVENT.VALUE_CHANGED,None);emit('event_t','get_user_data',hits==[('none',True),('first','B')],'none-and-dictionary-caller-data',hits=hits)
    removed=obj.remove_event_cb_with_user_data(no_data,None);hits[:]=[];obj.send_event(lv.EVENT.VALUE_CHANGED,None)
    emit(target,'remove_event_cb_with_user_data',removed==1 and hits==[('first','B')],'none-data-isolated-from-dictionary',removed=removed,hits=hits)
    for _ in range(obj.get_event_count()-baseline):getattr(obj,index_remove)(baseline)
    if target=='obj':
        obj.add_event_cb(first,lv.EVENT.VALUE_CHANGED,data_a);obj.add_event_cb(second,lv.EVENT.VALUE_CHANGED,data_b)
        removed=obj.remove_event_cb(first);hits[:]=[];obj.send_event(lv.EVENT.VALUE_CHANGED,None)
        emit(target,'remove_event_cb',removed and hits==[('second','B')] and obj.get_event_count()==baseline+1,'first-matching-callback-with-other-callback-retained',removed=removed,hits=hits)
        for _ in range(obj.get_event_count()-baseline):getattr(obj,index_remove)(baseline)
    # Calling a missing callback must be a no-op.
    removed=obj.remove_event_cb_with_user_data(first,data_b)
    emit(target,'remove_event_cb_with_user_data',removed==0 and obj.get_event_count()==baseline,'missing-callback-does-not-remove-unrelated',removed=removed)

M5.begin();m5ui.init()
try:
    page=m5ui.M5Page(bg_c=0x0B1014);page.screen_load()
    roller=lv.roller(page);roller.set_options('Alpha\nBeta\nGamma',lv.roller.MODE.NORMAL)
    for text,expected,domain in [('Alpha',0,'earlier-option'),('Gamma',2,'final-option'),('AlphaSuffix',2,'longer-option-must-not-match'),('Missing',2,'missing-option')]:
        roller.set_selected(2,False);found=roller.set_selected_str(text,False)
        emit('roller','set_selected_str',roller.get_selected()==expected and bool(found)==(text in ('Alpha','Gamma')),domain,selected=roller.get_selected(),returned=found)
    for target,obj,remove in [('obj',lv.obj(page),'remove_event'),('display_t',lv.display_create(32,24),'delete_event'),('indev_t',lv.indev_create(),'remove_event')]:
        try:callbacks(target,obj,remove)
        except Exception as e:print('M5EMU_UI_GROUP_ERROR '+json.dumps({'group':target,'error':repr(e)}));sys.print_exception(e)
        obj.delete()
    print('M5EMU_LVGL_CORRECTIONS_DONE')
    while True:M5.update();time.sleep_ms(20)
finally:m5ui.deinit()
