"""Application object data must preserve Python identity and delete fencing."""
import json,gc
import lvgl as lv

def emit(target,method,ok,domain,**details):
    print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.'+target,'method':method,'status':'STATE_PASS' if ok else 'FAIL','argument_domain':domain,'details':details}))

lv.init();display=lv.display_create(64,48);screen=display.get_screen_active();obj=lv.obj(screen);group=lv.group_create();group.add_obj(obj);lv.group_focus_obj(obj)
original_binding=obj.get_user_data();app={'nonce':'application'};callback_data={'nonce':'callback'};seen=[]
def callback(event):
    seen.append((event.get_target_obj(),event.get_current_target_obj(),event.get_user_data().__cast__()))
obj.add_event_cb(callback,lv.EVENT.CLICKED,callback_data)
obj.set_user_data(app);actual=obj.get_user_data().__cast__();emit('obj','set_user_data',actual is app,'application-dictionary-roundtrip');emit('obj','get_user_data',actual is app,'application-dictionary-roundtrip')
obj.send_event(lv.EVENT.CLICKED,None);target,current,data=seen[-1]
emit('event_t','get_target_obj',target is obj,'object-user-data-must-not-replace-binding',actual_type=type(target).__name__)
emit('event_t','get_current_target_obj',current is obj,'object-user-data-must-not-replace-binding',actual_type=type(current).__name__)
emit('event_t','get_user_data',data is callback_data,'callback-data-independent-of-object-data')
focused=group.get_focused();identity_safe=focused is obj
emit('group_t','get_focused',identity_safe,'object-user-data-must-not-replace-binding',actual_type=type(focused).__name__)
# Restore the original slot in the preimage before any native delete callback.
# This preserves a safe negative observation instead of corrupting a dict at delete.
if not identity_safe:obj.set_user_data(original_binding)
else:
    obj.set_user_data(None);emit('obj','get_user_data',obj.get_user_data() is None,'explicit-none-preserves-binding');emit('group_t','get_focused',group.get_focused() is obj,'none-data-preserves-binding')
    obj.set_user_data({'nonce':'rooted-until-delete'});gc.collect();emit('obj','get_user_data',obj.get_user_data().__cast__()['nonce']=='rooted-until-delete','gc-roots-application-data')
    seen[:]=[];obj.send_event(lv.EVENT.CLICKED,None);emit('obj','add_event_cb',seen==[(obj,obj,callback_data)],'callback-and-application-data-remain-independent-after-gc')
    removed=obj.remove_event_cb(callback);seen[:]=[];obj.send_event(lv.EVENT.CLICKED,None);emit('obj','remove_event_cb',removed and not seen,'callback-removal-identity-survives-application-data')
original_screen_binding=screen.get_user_data();screen.set_user_data({'nonce':'screen'});active=display.get_screen_active();screen_safe=active is screen
emit('display_t','get_screen_active',screen_safe,'screen-user-data-must-not-replace-binding',actual_type=type(active).__name__)
if not screen_safe:screen.set_user_data(original_screen_binding)
else:screen.set_user_data(None)
count=screen.get_child_count();obj.delete();emit('obj','delete',screen.get_child_count()==count-1,'userdata-object-delete-unlinks-native-child')
try:obj.get_width();invalid=False
except lv.LvReferenceError:invalid=True
emit('obj','delete',invalid,'deleted-python-wrapper-is-invalidated')
group.delete();display.delete();lv.deinit();print('LVGL_OBJECT_USER_DATA_DONE')
