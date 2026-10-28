"""Native widget setter/getter, collection and subject fixtures for CoreS3."""
import time
import json
import sys
import M5
import m5ui
import lvgl as lv

_target='lvgl'
_keep=[]


def emit(methods, ok, oracle, **details):
    if isinstance(methods,str):methods=[methods]
    for method in methods:
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':_target,'method':method,'status':'STATE_PASS' if ok else 'FAIL','oracle':oracle,'details':details}))


def settle(ms=100):
    stop=time.ticks_add(time.ticks_ms(),ms)
    while time.ticks_diff(stop,time.ticks_ms())>0:
        M5.update();time.sleep_ms(10)


def group(name,fn):
    global _target
    _target='lvgl.'+name
    try:
        fn()
        print('M5EMU_UI_GROUP_DONE '+json.dumps({'group':name}))
    except Exception as error:
        print('M5EMU_UI_GROUP_ERROR '+json.dumps({'group':name,'error':repr(error)}));sys.print_exception(error)


def fixture(name):
    obj=getattr(lv,name)(page);obj.set_pos(20,40);obj.set_size(260,140);return obj


def pairs(name,entries):
    obj=fixture(name)
    for setter,getter,args,expected in entries:
        getattr(obj,setter)(*args)
        actual=getattr(obj,getter)()
        if hasattr(actual,'to_int'):actual=actual.to_int()
        emit([setter,getter],actual==expected,'native typed setter/getter roundtrip',expected=expected,actual=actual)
    obj.delete()


def arc():
    obj=fixture('arc');obj.set_start_angle(30);obj.set_end_angle(140)
    emit(['set_start_angle','set_end_angle','get_angle_start','get_angle_end'],obj.get_angle_start()==30 and obj.get_angle_end()==140,'native arc endpoints retain degrees')
    obj.set_angles(40,160);obj.set_bg_start_angle(10);obj.set_bg_end_angle(230)
    emit(['set_angles','set_bg_start_angle','set_bg_end_angle','get_bg_angle_start','get_bg_angle_end'],obj.get_angle_start()==40 and obj.get_angle_end()==160 and obj.get_bg_angle_start()==10 and obj.get_bg_angle_end()==230,'foreground and background arcs remain independent')
    obj.set_bg_angles(15,210);obj.set_range(10,90);obj.set_value(60)
    emit(['set_bg_angles','set_range','set_value','get_min_value','get_max_value','get_value'],obj.get_bg_angle_start()==15 and obj.get_bg_angle_end()==210 and obj.get_min_value()==10 and obj.get_max_value()==90 and obj.get_value()==60,'native arc range and value clamp domain')
    obj.delete()
    pairs('arc',[('set_rotation','get_rotation',[45],45),('set_mode','get_mode',[lv.arc.MODE.REVERSE],lv.arc.MODE.REVERSE),('set_knob_offset','get_knob_offset',[6],6)])
    obj=fixture('arc');subject=lv.subject_t();subject.init_int(25);observer=obj.bind_value(subject);subject.set_int(60)
    emit('bind_value',obj.get_value()==60 and observer is not None,'native integer subject updates arc value')
    obj.delete();subject.deinit()


def bars(name):
    cls=getattr(lv,name);obj=fixture(name)
    obj.set_mode(cls.MODE.RANGE);obj.set_range(10,90);obj.set_value(70,False);obj.set_start_value(30,False)
    start=obj.get_start_value() if name=='bar' else obj.get_left_value()
    emit(['set_mode','get_mode','set_range','get_min_value','get_max_value','set_value','get_value','set_start_value','get_start_value' if name=='bar' else 'get_left_value'],obj.get_mode()==cls.MODE.RANGE and obj.get_min_value()==10 and obj.get_max_value()==90 and obj.get_value()==70 and start==30,'range widget retains both endpoints')
    obj.set_orientation(cls.ORIENTATION.VERTICAL)
    emit(['set_orientation','get_orientation'],obj.get_orientation()==cls.ORIENTATION.VERTICAL,'native orientation enum readback')
    obj.set_mode(cls.MODE.SYMMETRICAL);obj.set_range(-100,100)
    emit('is_symmetrical',obj.is_symmetrical() is True,'symmetric mode crosses the native zero point')
    if name=='slider':
        emit('is_dragged',obj.is_dragged() is False,'fresh native slider has no pressed input')
        subject=lv.subject_t();subject.init_int(10);observer=obj.bind_value(subject);subject.set_int(45)
        emit('bind_value',obj.get_value()==45 and observer is not None,'native subject changes slider value')
        obj.delete();subject.deinit()
    else:obj.delete()


def label():
    obj=fixture('label');obj.set_text('Alpha');emit(['set_text','get_text'],obj.get_text()=='Alpha','native label text exact bytes')
    static='Static';_keep.append(static);obj.set_text_static(static);emit('set_text_static',obj.get_text()=='Static','native static text remains rooted')
    obj.set_text('Static');obj.ins_text(6,' label');obj.cut_text(0,7);emit(['ins_text','cut_text'],obj.get_text()=='label','native dynamic-text insertion and deletion operate on character positions')
    obj.set_text_selection_start(1);obj.set_text_selection_end(3);obj.set_recolor(True);obj.set_long_mode(lv.label.LONG_MODE.WRAP)
    emit(['set_text_selection_start','get_text_selection_start','set_text_selection_end','get_text_selection_end','set_recolor','get_recolor','set_long_mode','get_long_mode'],obj.get_text_selection_start()==1 and obj.get_text_selection_end()==3 and obj.get_recolor() and obj.get_long_mode()==lv.label.LONG_MODE.WRAP,'native label selection/recolor/wrap state')
    obj.set_text('ABCD');obj.update_layout();position=lv.point_t();obj.get_letter_pos(0,position)
    index=obj.get_letter_on(position,False);inside=obj.is_char_under_pos(position)
    emit(['get_letter_pos','get_letter_on','is_char_under_pos'],position.x==0 and position.y==0 and index==0 and inside,'first glyph maps to and from the native letter position')
    obj.delete()


def dropdown():
    obj=fixture('dropdown');obj.set_options('Alpha\nBeta\nGamma');obj.set_selected(1,False)
    text=bytearray(32);obj.get_selected_str(text,len(text))
    emit(['set_options','get_options','set_selected','get_selected','get_option_count','get_selected_str','get_option_index'],obj.get_options()=='Alpha\nBeta\nGamma' and obj.get_selected()==1 and obj.get_option_count()==3 and bytes(text).split(b'\0')[0]==b'Beta' and obj.get_option_index('Beta')==1,'native dropdown options/index/selected output buffer agree')
    obj.add_option('Delta',1);emit('add_option',obj.get_option_index('Delta')==1 and obj.get_option_count()==4,'native insertion changes option index and count')
    static='One\nTwo';_keep.append(static);obj.set_options_static(static);emit('set_options_static',obj.get_options()==static,'rooted static option text')
    obj.set_text('Caption');obj.set_dir(lv.DIR.BOTTOM);obj.set_symbol(lv.SYMBOL.DOWN);obj.set_selected_highlight(True)
    emit(['set_text','get_text','set_dir','get_dir','set_symbol','get_symbol','set_selected_highlight','get_selected_highlight'],obj.get_text()=='Caption' and obj.get_dir()==lv.DIR.BOTTOM and obj.get_symbol()==lv.SYMBOL.DOWN and obj.get_selected_highlight(),'native caption/direction/symbol/highlight readback')
    obj.open();opened=obj.is_open();listing=obj.get_list();obj.close();closed=not obj.is_open()
    emit(['open','is_open','get_list','close'],opened and closed and listing is not None,'native popup lifecycle opens a real list and closes it')
    obj.clear_options();emit('clear_options',obj.get_option_count()==0,'native clear removes every option')
    obj.set_options('A\nB\nC');subject=lv.subject_t();subject.init_int(0);observer=obj.bind_value(subject);subject.set_int(2)
    emit('bind_value',obj.get_selected()==2 and observer is not None,'integer subject selects native dropdown option')
    obj.delete();subject.deinit()


def roller():
    obj=fixture('roller');obj.set_options('Alpha\nBeta\nGamma',lv.roller.MODE.NORMAL);obj.set_selected(1,False);buffer=bytearray(32);obj.get_selected_str(buffer,len(buffer))
    emit(['set_options','get_options','get_option_count','set_selected','get_selected','get_selected_str'],obj.get_options()=='Alpha\nBeta\nGamma' and obj.get_option_count()==3 and obj.get_selected()==1 and bytes(buffer).split(b'\0')[0]==b'Beta','native roller selection and output string buffer')
    result=obj.set_selected_str('Gamma',False)
    emit('set_selected_str',result and obj.get_selected()==2,'native option text selects the final row without trailing delimiter',returned=result,selected=obj.get_selected(),argument_domain='final-option')
    result=obj.set_selected_str('Alpha',False)
    emit('set_selected_str',result and obj.get_selected()==0,'native option text selects an earlier delimited row',returned=result,selected=obj.get_selected(),argument_domain='earlier-option')
    obj.set_visible_row_count(3);obj.update_layout();expected_height=(obj.get_style_text_font(0).line_height+obj.get_style_text_line_space(0))*3+2*obj.get_style_border_width(0);emit('set_visible_row_count',obj.get_height()==expected_height,'three native rows have the documented glyph/spacing/border height',height=obj.get_height(),expected=expected_height)
    subject=lv.subject_t();subject.init_int(0);observer=obj.bind_value(subject);subject.set_int(1);emit('bind_value',obj.get_selected()==1 and observer is not None,'subject selects native roller row')
    obj.delete();subject.deinit()


def textarea():
    obj=fixture('textarea');obj.set_text('AB');obj.set_cursor_pos(2);obj.add_char(ord('C'));obj.add_text('DE');emit(['set_text','set_cursor_pos','get_cursor_pos','add_char','add_text','get_text'],obj.get_text()=='ABCDE' and obj.get_cursor_pos()==5,'native textarea appends a codepoint and string')
    obj.delete_char();obj.set_cursor_pos(1);obj.delete_char_forward();emit(['delete_char','delete_char_forward'],obj.get_text()=='ACD','backward/forward deletion removes the intended characters')
    obj.set_placeholder_text('Placeholder');obj.set_cursor_click_pos(False);obj.set_password_mode(True);obj.set_password_bullet('*');obj.set_one_line(True);obj.set_accepted_chars('0123456789');obj.set_max_length(4);obj.set_text_selection(True);obj.set_password_show_time(400)
    emit(['set_placeholder_text','get_placeholder_text','set_cursor_click_pos','get_cursor_click_pos','set_password_mode','get_password_mode','set_password_bullet','get_password_bullet','set_one_line','get_one_line','set_accepted_chars','get_accepted_chars','set_max_length','get_max_length','set_text_selection','get_text_selection','set_password_show_time','get_password_show_time'],obj.get_placeholder_text()=='Placeholder' and not obj.get_cursor_click_pos() and obj.get_password_mode() and obj.get_password_bullet()=='*' and obj.get_one_line() and obj.get_accepted_chars()=='0123456789' and obj.get_max_length()==4 and obj.get_text_selection() and obj.get_password_show_time()==400,'native textarea configuration typed readbacks')
    obj.set_password_mode(False);obj.set_text('1234');obj.set_cursor_pos(1);char=obj.get_current_char();obj.cursor_right();right=obj.get_cursor_pos();obj.cursor_left();left=obj.get_cursor_pos();obj.clear_selection()
    emit(['get_current_char','cursor_right','cursor_left','clear_selection','text_is_selected','get_label'],char==ord('1') and right==2 and left==1 and not obj.text_is_selected() and obj.get_label().get_text()=='1234','current character is the previous codepoint; cursor motion and actual backing label text agree',character=char,right=right,left=left,text=obj.get_label().get_text())
    obj.delete()


def spinbox():
    obj=fixture('spinbox');obj.set_digit_format(4,2);obj.set_range(-5000,5000);obj.set_value(1250);obj.set_step(10);obj.increment();up=obj.get_value();obj.decrement();down=obj.get_value()
    emit(['set_digit_format','set_range','set_value','get_value','set_step','get_step','increment','decrement'],up==1260 and down==1250 and obj.get_step()==10,'native spinbox raw units increment/decrement by exact step')
    obj.step_next();small=obj.get_step();obj.step_prev();large=obj.get_step();obj.set_rollover(True)
    emit(['step_next','step_prev','set_rollover','get_rollover'],small==1 and large==10 and obj.get_rollover(),'digit step navigation and rollover readback')
    obj.delete()


def buttonmatrix():
    obj=fixture('buttonmatrix');mapping=['A','B','\n','C',''];_keep.append(mapping);obj.set_map(mapping);obj.set_selected_button(1)
    emit(['set_map','set_selected_button','get_selected_button','get_button_text'],obj.get_selected_button()==1 and obj.get_button_text(1)=='B','native button map and selected label')
    flag=lv.buttonmatrix.CTRL.CHECKABLE;obj.set_button_ctrl(0,flag);yes=obj.has_button_ctrl(0,flag);obj.clear_button_ctrl(0,flag);no=obj.has_button_ctrl(0,flag)
    obj.set_button_ctrl_all(flag);all_set=all(obj.has_button_ctrl(i,flag) for i in range(3));obj.clear_button_ctrl_all(flag);all_clear=not any(obj.has_button_ctrl(i,flag) for i in range(3));obj.set_one_checked(True)
    emit(['set_button_ctrl','has_button_ctrl','clear_button_ctrl','set_button_ctrl_all','clear_button_ctrl_all','set_one_checked','get_one_checked'],yes and not no and all_set and all_clear and obj.get_one_checked(),'native individual and bulk button controls')
    obj.delete()


def table():
    obj=fixture('table');obj.set_row_count(3);obj.set_column_count(2);obj.set_column_width(0,80);obj.set_cell_value(1,1,'Cell')
    emit(['set_row_count','get_row_count','set_column_count','get_column_count','set_column_width','get_column_width','set_cell_value','get_cell_value'],obj.get_row_count()==3 and obj.get_column_count()==2 and obj.get_column_width(0)==80 and obj.get_cell_value(1,1)=='Cell','native table dimensions and individual cell contents')
    flag=lv.table.CELL_CTRL.MERGE_RIGHT;obj.set_cell_ctrl(0,0,flag);yes=obj.has_cell_ctrl(0,0,flag);obj.clear_cell_ctrl(0,0,flag);no=obj.has_cell_ctrl(0,0,flag)
    emit(['set_cell_ctrl','has_cell_ctrl','clear_cell_ctrl'],yes and not no,'native per-cell control changes and clears')
    obj.delete()


def tabview():
    obj=fixture('tabview');first=obj.add_tab('First');second=obj.add_tab('Second');obj.set_active(1,False)
    emit(['add_tab','get_tab_count','set_active','get_tab_active','get_content','get_tab_bar'],obj.get_tab_count()==2 and obj.get_tab_active()==1 and first.get_parent()==obj.get_content() and second.get_parent()==obj.get_content() and obj.get_tab_bar() is not None,'native tab pages, active index and actual content ownership')
    obj.rename_tab(0,'Renamed');bar=obj.get_tab_bar();label=bar.get_child(0).get_child(0)
    emit('rename_tab',label.get_text()=='Renamed','native tab label changes through rename')
    obj.set_tab_bar_position(lv.DIR.TOP);obj.set_tab_bar_size(30);obj.update_layout()
    emit(['set_tab_bar_position','set_tab_bar_size'],bar.get_height()==30 and bar.get_y()<obj.get_content().get_y(),'native tab bar layout obeys top position and explicit height')
    obj.delete()


def tileview():
    obj=fixture('tileview');a=obj.add_tile(0,0,lv.DIR.RIGHT);b=obj.add_tile(1,0,lv.DIR.LEFT);obj.set_tile_by_index(1,0,False)
    emit(['add_tile','set_tile_by_index','get_tile_active'],obj.get_tile_active()==b,'native tile index selects the actual second tile')
    obj.set_tile(a,False);emit('set_tile',obj.get_tile_active()==a,'native tile pointer returns to the first tile');obj.delete()


def lists():
    obj=fixture('list');text=obj.add_text('Section');button=obj.add_button(None,'Button');original=obj.get_button_text(button);obj.set_button_text(button,'Updated')
    emit(['add_text','add_button','get_button_text','set_button_text'],lv.label.get_text(text)=='Section' and original=='Button' and obj.get_button_text(button)=='Updated','native list children and button text mutation');obj.delete()


def keyboard():
    text=lv.textarea(page);obj=fixture('keyboard');obj.set_textarea(text);obj.set_mode(lv.keyboard.MODE.TEXT_UPPER);obj.set_popovers(True)
    emit(['set_textarea','get_textarea','set_mode','get_mode','set_popovers','get_popovers'],obj.get_textarea()==text and obj.get_mode()==lv.keyboard.MODE.TEXT_UPPER and obj.get_popovers(),'native keyboard keeps its actual target and settings')
    selected=obj.get_selected_button();first=obj.get_button_text(0)
    emit(['get_selected_button','get_button_text'],selected==0xFFFF and first=='1#','fresh native uppercase keyboard starts unselected and exposes its documented first key',selected=selected,first=first)
    obj.delete();text.delete()


def led():
    obj=fixture('led');obj.set_color(lv.color_hex(0x38B8C8));obj.set_brightness(128);brightness=obj.get_brightness();obj.on();on=obj.get_brightness();obj.off();off=obj.get_brightness();obj.toggle();toggle=obj.get_brightness()
    emit(['set_brightness','get_brightness','on','off','toggle'],brightness==128 and on==255 and off==80 and toggle==255,'native LED 80..255 documented brightness transitions',brightness=brightness,on=on,off=off,toggle=toggle)
    obj.set_pos(220,160);obj.set_size(40,40);obj.set_style_radius(0,0);obj.set_style_border_width(0,0);obj.set_style_shadow_width(0,0);obj.set_style_bg_grad_dir(lv.GRAD_DIR.NONE,0);settle()
    print('M5EMU_UI_FRAME_ORACLE '+json.dumps({'api_target':'lvgl.led','method':'set_color','oracle':{'kind':'pixels','points':[[240,180,0x38B8C8]]}}))
    _keep.append(obj)


def line():
    obj=fixture('line');points=[{'x':10,'y':20},{'x':100,'y':80}];_keep.append(points);obj.set_points(points,2);obj.set_y_invert(True)
    emit(['set_points','get_point_count','is_point_array_mutable','set_y_invert','get_y_invert'],obj.get_point_count()==2 and obj.is_point_array_mutable() is False and obj.get_y_invert(),'native line count, immutable-buffer mode and y-axis inversion')
    obj.delete()


def checkbox():
    obj=fixture('checkbox');obj.set_text('Checkbox');text=obj.get_text();static='Static checkbox';_keep.append(static);obj.set_text_static(static)
    emit(['set_text','set_text_static','get_text'],text=='Checkbox' and obj.get_text()==static,'native checkbox dynamic and rooted static captions');obj.delete()


M5.begin();m5ui.init()
try:
    page=m5ui.M5Page(bg_c=0x0B1014);heading=m5ui.M5Label('Native widget behavior',x=8,y=8,text_c=0xF3F7F8,parent=page);page.screen_load()
    for name,fn in [('arc',arc),('bar',lambda:bars('bar')),('slider',lambda:bars('slider')),('label',label),('dropdown',dropdown),('roller',roller),('textarea',textarea),('spinbox',spinbox),('buttonmatrix',buttonmatrix),('table',table),('tabview',tabview),('tileview',tileview),('list',lists),('keyboard',keyboard),('led',led),('line',line),('checkbox',checkbox)]:group(name,fn)
    final=lv.label(page);final.set_text('Native widgets complete');final.set_pos(20,80);final.set_style_text_color(lv.color_hex(0xF3F7F8),0);final.move_foreground();settle()
    print('M5EMU_UI_FRAME_ORACLE '+json.dumps({'api_target':'lvgl.label','method':'set_text','oracle':{'kind':'text','text':'Native widgets complete','box':[20,70,310,120]},'tolerance':8}))
    print('M5EMU_UI_READY '+json.dumps({'scope':'native widget typed fixtures'}))
    while True:M5.update();time.sleep_ms(20)
finally:m5ui.deinit()
