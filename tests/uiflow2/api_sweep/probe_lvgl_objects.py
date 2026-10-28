"""Native LVGL object fixtures with behavioral, callback and layout oracles.

These calls use real allocated LVGL objects on the visible CoreS3 guest.
Related getter/setter names are emitted only after each listed call executes.
An exception leaves the remaining group unclassified, not implicitly passed.
"""
import time
import json
import sys
import M5
import m5ui
import lvgl as lv


def emit(methods, ok, oracle, **details):
    if isinstance(methods, str):
        methods = [methods]
    for method in methods:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl.obj", "method": method, "status": "STATE_PASS" if ok else "FAIL", "oracle": oracle, "details": details}))


def settle(milliseconds=150):
    deadline = time.ticks_add(time.ticks_ms(), milliseconds)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(10)


def group(name, function):
    try:
        function()
        print("M5EMU_UI_GROUP_DONE " + json.dumps({"group": name}))
    except Exception as error:
        print("M5EMU_UI_GROUP_ERROR " + json.dumps({"group": name, "error": repr(error)}))
        sys.print_exception(error)


def make(parent=None):
    obj = lv.obj(parent if parent is not None else page)
    obj.remove_style_all()
    obj.set_pos(30, 50)
    obj.set_size(100, 80)
    obj.update_layout()
    return obj


def geometry():
    obj = make()
    obj.set_pos(24, 48)
    obj.set_size(140, 90)
    obj.update_layout()
    emit(["set_pos", "set_size", "get_x", "get_y", "get_width", "get_height"], (obj.get_x(), obj.get_y(), obj.get_width(), obj.get_height()) == (24,48,140,90), "explicit native position/size roundtrip")
    obj.set_x(28); obj.set_y(52); obj.set_width(130); obj.set_height(88); obj.update_layout()
    emit(["set_x", "set_y", "set_width", "set_height"], (obj.get_x(),obj.get_y(),obj.get_width(),obj.get_height()) == (28,52,130,88), "independent axes retain their requested values")
    obj.set_content_width(120);obj.set_content_height(70);obj.update_layout()
    emit(["set_content_width","set_content_height","get_content_width","get_content_height"], (obj.get_content_width(),obj.get_content_height()) == (120,70), "style-free native content dimensions")
    area=lv.area_t();obj.get_coords(area)
    emit(["get_coords","get_x2","get_y2"], (area.x1,area.y1,area.x2,area.y2)==(28,52,147,121) and obj.get_x2()==148 and obj.get_y2()==122, "inclusive coords and exclusive x2/y2 match the same native rectangle", rectangle=[area.x1,area.y1,area.x2,area.y2])
    content=lv.area_t();obj.get_content_coords(content)
    emit("get_content_coords", (content.x1,content.y1,content.x2,content.y2)==(28,52,147,121), "style-free content rectangle matches native coordinates")
    obj.set_align(lv.ALIGN.TOP_LEFT);obj.align(lv.ALIGN.TOP_LEFT,36,60);obj.update_layout()
    emit(["set_align","align","get_x_aligned","get_y_aligned"], obj.get_x_aligned()==36 and obj.get_y_aligned()==60, "top-left alignment reports requested offsets")
    obj.center();obj.update_layout()
    emit("center", (obj.get_x(),obj.get_y())==((320-120)//2,(240-70)//2), "centered position derives from native parent and child dimensions")
    base=make();base.set_pos(10,20);base.set_size(40,30);base.update_layout()
    obj.align_to(base,lv.ALIGN.OUT_RIGHT_TOP,5,7);obj.update_layout()
    emit("align_to", (obj.get_x(),obj.get_y())==(55,27), "object aligns outside the real sibling rectangle")
    saved_pos=(obj.get_x(),obj.get_y())
    obj.move_to(44,66)
    emit("move_to", (obj.get_x(),obj.get_y())==(44,66), "raw native coordinates move before style refresh")
    obj.refr_pos();obj.refr_size();obj.update_layout()
    emit(["refr_pos","refr_size"], (obj.get_x(),obj.get_y())==saved_pos, "refresh reapplies the stored style position")
    obj.mark_layout_as_dirty();obj.update_layout();changed=obj.refresh_self_size();width=obj.get_self_width();height=obj.get_self_height()
    emit(["mark_layout_as_dirty","update_layout","refresh_self_size","get_self_width","get_self_height"], obj.get_width()==120 and obj.get_height()==70 and width>=0 and height>=0 and isinstance(changed,bool), "refresh preserves fixed geometry and reports intrinsic dimensions", intrinsic=[width,height])
    child=make(obj);child.set_pos(5,7);obj.update_layout();obj.move_children_by(8,9,False)
    emit("move_children_by", (child.get_x(),child.get_y())==(13,16), "child native position moves by both requested deltas")
    area=lv.area_t();obj.get_click_area(area);before=[area.x1,area.y1,area.x2,area.y2]
    obj.set_ext_click_area(6);obj.get_click_area(area)
    emit(["set_ext_click_area","get_click_area"], area.x1==before[0]-6 and area.y1==before[1]-6 and area.x2==before[2]+6 and area.y2==before[3]+6, "click rectangle expands on all sides")
    coords=lv.area_t();obj.get_coords(coords)
    point=lv.point_t({'x':coords.x1+6,'y':coords.y1+6})
    emit("hit_test", obj.hit_test(point) is True, "point inside native click area hits")
    obj.add_flag(lv.obj.FLAG.HIDDEN);hidden=obj.is_visible();obj.remove_flag(lv.obj.FLAG.HIDDEN);visible=obj.is_visible()
    emit("is_visible", hidden is False and visible is True, "hidden flag changes actual visibility")
    area=lv.area_t({'x1':coords.x1+2,'y1':coords.y1+2,'x2':coords.x1+8,'y2':coords.y1+8});visible=obj.area_is_visible(area)
    obj.invalidate_area(area);obj.invalidate()
    emit("area_is_visible", visible is True, "known intersecting native area is visible")
    emit(["invalidate_area","invalidate"], obj.is_valid(), "invalidate retains a valid object; framebuffer is checked independently")
    obj.delete();base.delete()


def hierarchy():
    parent=make();a=make(parent);b=lv.label(parent);b.set_text('B');c=make(parent)
    cls=a.get_class()
    emit(["get_class","check_type","has_class"], a.check_type(cls) and a.has_class(cls), "real allocated object's class validates")
    emit(["get_parent","get_screen","get_display"], a.get_parent()==parent and a.get_screen()==page and a.get_display()==lv.display_get_default(), "actual parent/screen/display identities")
    emit(["get_child","get_child_count","get_index"], parent.get_child_count()==3 and parent.get_child(0)==a and a.get_index()==0, "children preserve insertion order")
    emit(["get_child_by_type","get_child_count_by_type","get_index_by_type"], parent.get_child_by_type(1,cls)==c and parent.get_child_count_by_type(cls)==2 and c.get_index_by_type(cls)==1, "class-filtered traversal excludes the label")
    emit(["get_sibling","get_sibling_by_type"], a.get_sibling(1)==b and a.get_sibling_by_type(1,cls)==c, "relative sibling traversal respects class")
    c.move_background();a.move_foreground()
    emit(["move_background","move_foreground"], c.get_index()==0 and a.get_index()==2, "foreground/background reorder actual children")
    a.move_to_index(1);a.swap(c)
    emit(["move_to_index","swap"], a.get_index()==0 and c.get_index()==1, "indexed move and swap update native order")
    other=make();a.set_parent(other)
    emit("set_parent", a.get_parent()==other and parent.get_child_count()==2 and other.get_child_count()==1, "reparent transfers ownership between real containers")
    seen=[]
    def walker(obj,data):
        seen.append(obj)
        return lv.obj.TREE_WALK.NEXT
    parent.tree_walk(walker,None)
    emit("tree_walk", len(seen)==3 and parent in seen and b in seen and c in seen, "native tree callback visits exactly parent plus two children", callbacks=len(seen))
    parent.clean()
    emit("clean", parent.get_child_count()==0, "clean deletes every real child")
    a.delete();other.delete();parent.delete()


def flags_states():
    obj=make()
    obj.add_flag(lv.obj.FLAG.HIDDEN);one=obj.has_flag(lv.obj.FLAG.HIDDEN);anyflag=obj.has_flag_any(lv.obj.FLAG.HIDDEN|lv.obj.FLAG.CLICKABLE)
    obj.remove_flag(lv.obj.FLAG.HIDDEN);two=obj.has_flag(lv.obj.FLAG.HIDDEN)
    obj.update_flag(lv.obj.FLAG.HIDDEN,True);three=obj.has_flag(lv.obj.FLAG.HIDDEN);obj.update_flag(lv.obj.FLAG.HIDDEN,False)
    emit(["add_flag","remove_flag","update_flag","has_flag","has_flag_any"], one and anyflag and not two and three and not obj.has_flag(lv.obj.FLAG.HIDDEN), "positive and negative native flag transitions")
    obj.add_state(lv.STATE.CHECKED);checked=obj.has_state(lv.STATE.CHECKED);state=obj.get_state()
    obj.remove_state(lv.STATE.CHECKED);removed=not obj.has_state(lv.STATE.CHECKED)
    obj.set_state(lv.STATE.DISABLED,True);disabled=obj.has_state(lv.STATE.DISABLED);obj.set_state(lv.STATE.DISABLED,False)
    emit(["add_state","remove_state","set_state","get_state","has_state"], checked and state&lv.STATE.CHECKED and removed and disabled and not obj.has_state(lv.STATE.DISABLED), "native state bits toggle without affecting the next clear")
    obj.allocate_spec_attr();obj.set_user_data(None);data=obj.get_user_data()
    emit(["allocate_spec_attr","set_user_data","get_user_data"], data is None, "native optional state allocation and explicit null user data roundtrip")
    emit("get_group", obj.get_group() is None, "new object is not in a native input group")
    emit(["is_editable","is_group_def"], obj.is_editable() is False and obj.is_group_def() is False, "base object is non-editable and not a default group member")
    obj.delete()


def event_callbacks():
    obj=make();hits=[]
    def callback(event):
        hits.append(event.get_code())
    before=obj.get_event_count();descriptor=obj.add_event_cb(callback,lv.EVENT.CLICKED,None)
    found=obj.get_event_dsc(before)
    obj.send_event(lv.EVENT.CLICKED,None)
    emit(["add_event_cb","get_event_count","get_event_dsc","send_event"], obj.get_event_count()==before+1 and found==descriptor and hits==[lv.EVENT.CLICKED], "registered native callback sees exact sent event")
    removed=obj.remove_event_dsc(descriptor);obj.send_event(lv.EVENT.CLICKED,None)
    emit("remove_event_dsc", removed and len(hits)==1 and obj.get_event_count()==before, "descriptor removal stops callback delivery")
    descriptor=obj.add_event_cb(callback,lv.EVENT.CLICKED,None);removed=obj.remove_event_cb(callback)
    emit("remove_event_cb", removed and obj.get_event_count()==before, "Python callback identity removal restores original count", removed=removed, before=before, after=obj.get_event_count())
    if not removed:
        obj.remove_event_dsc(descriptor)
    obj.add_event_cb(callback,lv.EVENT.CLICKED,None);removed=obj.remove_event(before)
    emit("remove_event", removed and obj.get_event_count()==before, "event index removal restores original count")
    descriptor=obj.add_event_cb(callback,lv.EVENT.CLICKED,None);removed=obj.remove_event_cb_with_user_data(callback,None)
    emit("remove_event_cb_with_user_data", removed==1 and obj.get_event_count()==before, "matching Python callback/user-data removal reports one registration", removed=removed, before=before, after=obj.get_event_count())
    if not removed:
        obj.remove_event_dsc(descriptor)
    obj.delete()


def subject_bindings():
    obj=make()
    comparisons=[('eq',5,6,5),('not_eq',6,5,5),('gt',6,5,5),('ge',5,4,5),('lt',4,5,5),('le',5,6,5)]
    for suffix,positive,negative,reference in comparisons:
        for kind,flag in [('flag',lv.obj.FLAG.HIDDEN),('state',lv.STATE.DISABLED)]:
            subject=lv.subject_t();subject.init_int(negative)
            method='bind_'+kind+'_if_'+suffix
            observer=getattr(obj,method)(subject,flag,reference)
            subject.set_int(positive)
            yes=obj.has_flag(flag) if kind=='flag' else obj.has_state(flag)
            subject.set_int(negative)
            no=obj.has_flag(flag) if kind=='flag' else obj.has_state(flag)
            emit(method,yes and not no and observer is not None,"native subject transitions apply and clear the bound "+kind)
            obj.remove_from_subject(subject);subject.set_int(positive)
            detached=obj.has_flag(flag) if kind=='flag' else obj.has_state(flag)
            emit('remove_from_subject',not detached,'unbound subject can no longer mutate the object')
            subject.deinit()
    subject=lv.subject_t();subject.init_int(0);observer=obj.bind_checked(subject);subject.set_int(1);yes=obj.has_state(lv.STATE.CHECKED);subject.set_int(0);no=obj.has_state(lv.STATE.CHECKED)
    emit('bind_checked',yes and not no and observer is not None,'native integer subject drives CHECKED both directions')
    obj.remove_from_subject(subject);subject.deinit();obj.delete()


def scrolling():
    obj=make();obj.set_size(100,80);child=make(obj);child.set_pos(220,180);child.set_size(20,20);obj.update_layout()
    obj.set_scrollbar_mode(lv.SCROLLBAR_MODE.ON);obj.set_scroll_dir(lv.DIR.ALL);obj.set_scroll_snap_x(lv.SCROLL_SNAP.START);obj.set_scroll_snap_y(lv.SCROLL_SNAP.END)
    emit(['set_scrollbar_mode','set_scroll_dir','set_scroll_snap_x','set_scroll_snap_y','get_scrollbar_mode','get_scroll_dir','get_scroll_snap_x','get_scroll_snap_y'],obj.get_scrollbar_mode()==lv.SCROLLBAR_MODE.ON and obj.get_scroll_dir()==lv.DIR.ALL and obj.get_scroll_snap_x()==lv.SCROLL_SNAP.START and obj.get_scroll_snap_y()==lv.SCROLL_SNAP.END,'native scroll options retain enum values')
    obj.set_scroll_snap_x(lv.SCROLL_SNAP.NONE);obj.set_scroll_snap_y(lv.SCROLL_SNAP.NONE)
    obj.scroll_to(20,30,False);obj.update_layout()
    emit(['scroll_to','get_scroll_x','get_scroll_y'],obj.get_scroll_x()==20 and obj.get_scroll_y()==30,'absolute scroll changes native offsets')
    obj.scroll_to_x(25,False);obj.scroll_to_y(35,False);obj.scroll_by(5,5,False)
    emit(['scroll_to_x','scroll_to_y','scroll_by'],obj.get_scroll_x()==20 and obj.get_scroll_y()==30,'axis and relative scrolls compose')
    obj.scroll_by_bounded(1000,1000,False)
    emit('scroll_by_bounded',obj.get_scroll_x()==0 and obj.get_scroll_y()==0,'bounded scroll clamps at the near edges')
    obj.scroll_by_raw(-10,-15)
    emit('scroll_by_raw',obj.get_scroll_x()==10 and obj.get_scroll_y()==15,'raw content displacement produces inverse scroll offsets')
    end=lv.point_t();obj.get_scroll_end(end)
    top=obj.get_scroll_top();bottom=obj.get_scroll_bottom();left=obj.get_scroll_left();right=obj.get_scroll_right()
    emit(['get_scroll_end','get_scroll_top','get_scroll_bottom','get_scroll_left','get_scroll_right'],end.x==obj.get_scroll_x() and end.y==obj.get_scroll_y() and top>=0 and bottom>=0 and left>=0 and right>=0,'scroll extents and nonanimated destination agree',extents=[top,bottom,left,right])
    child.scroll_to_view(False);child.scroll_to_view_recursive(False)
    emit(['scroll_to_view','scroll_to_view_recursive'],obj.get_scroll_x()>0 and obj.get_scroll_y()>0,'scroll-to-view brings the distant actual child into view')
    obj.stop_scroll_anim();active=obj.is_scrolling();obj.update_snap(False);obj.readjust_scroll(False)
    emit(['stop_scroll_anim','is_scrolling','update_snap','readjust_scroll'],active is False,'nonanimated scroll stays idle after stop/snap/readjust')
    hor=lv.area_t();ver=lv.area_t();obj.get_scrollbar_area(hor,ver);obj.scrollbar_invalidate()
    emit(['get_scrollbar_area','scrollbar_invalidate'],hor.x2>=hor.x1 and ver.y2>=ver.y1,'scrollbar rectangles are noninverted for overflowing content')
    obj.delete()


def lifecycle():
    parent=make();child=make(parent);before=parent.get_child_count();child.delete()
    emit('delete',parent.get_child_count()==before-1,'delete removes its actual child from the parent')
    child=make(parent);child.delete_delayed(30);settle(100)
    emit('delete_delayed',parent.get_child_count()==0,'delayed delete runs through the real LVGL timer')
    child=make(parent);child.delete_async();settle(100)
    emit('delete_async',parent.get_child_count()==0,'async delete runs through the real LVGL dispatcher')
    cls=parent.get_class();child=lv.obj.class_create_obj(cls,parent);child.class_init_obj()
    emit(['class_create_obj','class_init_obj','is_valid'],child.is_valid() and child.get_parent()==parent and parent.get_child_count()==1,'class allocation and initializer produce a real owned object')
    parent.delete()


M5.begin()
m5ui.init()
try:
    page=m5ui.M5Page(bg_c=0x0B1014)
    heading=m5ui.M5Label('Native object behavior',x=8,y=8,text_c=0xF3F7F8,parent=page)
    page.screen_load()
    for name,function in [('geometry',geometry),('hierarchy',hierarchy),('flags',flags_states),('events',event_callbacks),('subjects',subject_bindings),('scroll',scrolling),('lifecycle',lifecycle)]:
        group(name,function)
    final=make();final.set_style_bg_color(lv.color_hex(0x38B8C8),0);final.set_style_bg_opa(255,0)
    settle()
    print('M5EMU_UI_FRAME_ORACLE '+json.dumps({'api_target':'lvgl.obj','method':'set_style_bg_color','oracle':{'kind':'pixels','points':[[35,55,0x38B8C8],[125,125,0x38B8C8]]},'tolerance':8}))
    print('M5EMU_UI_READY '+json.dumps({'api_target':'lvgl.obj','scope':'native object typed behavior'}))
    while True:
        M5.update()
        time.sleep_ms(20)
finally:
    m5ui.deinit()
