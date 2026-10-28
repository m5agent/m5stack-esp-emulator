"""Additional native widget fixtures using actual typed resources and state."""
import time,json,sys,struct,array,uctypes
import M5,m5ui,lvgl as lv
_target='lvgl';_keep=[]
def emit(methods,ok,oracle,**details):
    if isinstance(methods,str):methods=[methods]
    for method in methods:print('M5EMU_UI_RESULT '+json.dumps({'api_target':_target,'method':method,'status':'STATE_PASS' if ok else 'FAIL','oracle':oracle,'details':details}))
def group(name,fn):
    global _target
    _target='lvgl.'+name
    try:fn();print('M5EMU_UI_GROUP_DONE '+json.dumps({'group':name}))
    except Exception as error:print('M5EMU_UI_GROUP_ERROR '+json.dumps({'group':name,'error':repr(error)}));sys.print_exception(error)
def settle(ms=120):
    stop=time.ticks_add(time.ticks_ms(),ms)
    while time.ticks_diff(stop,time.ticks_ms())>0:M5.update();time.sleep_ms(10)
def fixture(name):
    obj=getattr(lv,name)(page);obj.set_pos(20,40);obj.set_size(220,160);return obj
def raw_image():
    raw=bytearray(b'\x00\xf8'*64);dsc=lv.image_dsc_t({'header':{'magic':0x19,'cf':lv.COLOR_FORMAT.RGB565,'w':8,'h':8,'stride':16},'data_size':len(raw),'data':raw});_keep.extend([raw,dsc]);return dsc

def image():
    obj=fixture('image');src=raw_image();obj.set_src(src);got=lv.image_dsc_t.__cast__(obj.get_src())
    emit(['set_src','get_src'],got.header.w==8 and got.header.h==8 and got.data_size==128,'native source descriptor retains dimensions and byte length')
    for setter,getter,value in [('set_offset_x','get_offset_x',3),('set_offset_y','get_offset_y',5),('set_rotation','get_rotation',450),('set_scale_x','get_scale_x',320),('set_scale_y','get_scale_y',384),('set_blend_mode','get_blend_mode',lv.BLEND_MODE.ADDITIVE),('set_antialias','get_antialias',False),('set_inner_align','get_inner_align',lv.image.ALIGN.CENTER)]:
        getattr(obj,setter)(value);actual=getattr(obj,getter)();emit([setter,getter],actual==value,'native typed image setting roundtrip',expected=value,actual=actual)
    obj.set_scale(300);emit(['set_scale','get_scale'],obj.get_scale()==300 and obj.get_scale_x()==300 and obj.get_scale_y()==300,'uniform image scale changes both axes')
    obj.set_pivot(3,6);point=lv.point_t();obj.get_pivot(point);emit(['set_pivot','get_pivot'],point.x==3 and point.y==6,'native image pivot output structure')
    obj.set_bitmap_map_src(src);got=lv.image_dsc_t.__cast__(obj.get_bitmap_map_src());emit(['set_bitmap_map_src','get_bitmap_map_src'],got.header.w==8 and got.data_size==128,'native bitmap map retains the image descriptor');obj.delete()

def animimg():
    obj=fixture('animimg');sources=[raw_image(),raw_image()];_keep.append(sources);obj.set_src(sources,2);obj.set_duration(120);obj.set_repeat_count(2);animation=obj.get_anim()
    emit(['set_src','get_src_count','set_duration','get_duration','set_repeat_count','get_repeat_count','get_anim'],obj.get_src_count()==2 and obj.get_duration()==120 and obj.get_repeat_count()==2 and animation.duration==120,'native animation stores two rooted source descriptors and requested timing')
    obj.start();settle(30);emit('start',lv.anim_count_running()>=1,'real image animation enters the LVGL scheduler');obj.delete()

def imagebutton():
    obj=fixture('imagebutton');src=raw_image();state=lv.imagebutton.STATE.RELEASED;obj.set_src(state,src,src,src);obj.set_state(lv.imagebutton.STATE.PRESSED)
    valid=True
    for method in ['get_src_left','get_src_middle','get_src_right']:
        dsc=lv.image_dsc_t.__cast__(getattr(obj,method)(state));valid=valid and dsc.header.w==8 and dsc.data_size==128
    emit(['set_src','get_src_left','get_src_middle','get_src_right'],valid,'three native image-button slots return the actual rooted image descriptor')
    emit('set_state',obj.has_state(lv.STATE.PRESSED),'native imagebutton pressed state reaches object state');obj.delete()

def calendar():
    obj=fixture('calendar');obj.set_today_date(2026,10,27);obj.set_month_shown(2027,2);today=obj.get_today_date();shown=obj.get_showed_date()
    emit(['set_today_date','get_today_date','set_month_shown','get_showed_date'],(today.year,today.month,today.day)==(2026,10,27) and (shown.year,shown.month)==(2027,2),'native calendar today and shown month remain independent')
    dates=[lv.calendar_date_t({'year':2027,'month':2,'day':3}),lv.calendar_date_t({'year':2027,'month':2,'day':9})];_keep.append(dates);obj.set_highlighted_dates(dates,2);actual=obj.get_highlighted_dates()
    emit(['set_highlighted_dates','get_highlighted_dates','get_highlighted_dates_num'],obj.get_highlighted_dates_num()==2 and struct.unpack('HbbHbb',actual.__dereference__(8))==(2027,2,3,2027,2,9),'native highlighted array keeps both exact dates')
    names=[b'Su\0',b'Mo\0',b'Tu\0',b'We\0',b'Th\0',b'Fr\0',b'Sa\0'];pointers=bytearray(b''.join(struct.pack('I',uctypes.addressof(name)) for name in names));_keep.extend([names,pointers]);obj.set_day_names(lv.C_Pointer.__cast__(pointers));buttons=obj.get_btnmatrix();emit(['set_day_names','get_btnmatrix'],buttons.get_button_text(0)=='Su' and buttons.get_button_text(6)=='Sa','native day labels reach underlying actual button matrix')
    date=lv.calendar_date_t();result=obj.get_pressed_date(date);emit('get_pressed_date',result==lv.RESULT.INVALID,'unpressed native calendar returns INVALID without inventing a date');obj.delete()

def chart():
    obj=fixture('chart');obj.set_type(lv.chart.TYPE.LINE);obj.set_point_count(3);obj.set_axis_range(lv.chart.AXIS.PRIMARY_Y,0,100);obj.set_update_mode(lv.chart.UPDATE_MODE.CIRCULAR);obj.set_div_line_count(3,4)
    emit(['set_type','get_type','set_point_count','get_point_count'],obj.get_type()==lv.chart.TYPE.LINE and obj.get_point_count()==3,'native chart type and sample count')
    series=obj.add_series(lv.color_hex(0x123456),lv.chart.AXIS.PRIMARY_Y);other=obj.add_series(lv.color_hex(0xABCDEF),lv.chart.AXIS.PRIMARY_Y)
    emit(['add_series','get_series_next'],obj.get_series_next(None)==series and obj.get_series_next(series)==other and obj.get_series_next(other) is None,'native series traversal returns exact two-series chain')
    obj.set_series_color(series,lv.color_hex(0xAA5533));emit(['set_series_color','get_series_color'],obj.get_series_color(series).to_int()==0xAA5533,'native series color roundtrip')
    def values():return list(struct.unpack('3i',obj.get_series_y_array(series).__dereference__(12)))
    obj.set_all_values(series,10);emit(['set_all_values','get_series_y_array'],values()==[10,10,10],'native chart Y buffer contains each filled value',values=values())
    obj.set_series_value_by_id(series,1,40);emit('set_series_value_by_id',values()==[10,40,10],'native indexed Y update changes exactly one entry')
    obj.set_series_values(series,[20,40,60],3);emit('set_series_values',values()==[20,40,60],'native bulk Y update keeps requested sequence')
    obj.set_x_start_point(series,1);emit(['set_x_start_point','get_x_start_point'],obj.get_x_start_point(series)==1,'native circular buffer start offset')
    obj.set_next_value(series,70);emit(['set_next_value','set_update_mode'],values()==[20,70,60] and obj.get_x_start_point(series)==2,'circular update changes the current entry and advances index')
    obj.set_x_start_point(series,0);obj.update_layout();a=lv.point_t();b=lv.point_t();obj.get_point_pos_by_id(series,0,a);obj.get_point_pos_by_id(series,2,b)
    emit(['set_axis_range','get_point_pos_by_id'],a.x<b.x and a.y>b.y,'real plotted point coordinates obey X order and Y range',a=[a.x,a.y],b=[b.x,b.y])
    cursor=obj.add_cursor(lv.color_hex(0xFF0000),lv.DIR.ALL);p=lv.point_t({'x':20,'y':30});obj.set_cursor_pos(cursor,p);actual=obj.get_cursor_point(cursor)
    emit(['add_cursor','set_cursor_pos','get_cursor_point'],actual.x==20 and actual.y==30,'native cursor position output structure')
    obj.set_cursor_point(cursor,series,1);settle();actual=obj.get_cursor_point(cursor);expect=lv.point_t();obj.get_point_pos_by_id(series,1,expect)
    emit('set_cursor_point',cursor.point_id==1 and not cursor.pos_set and cursor.ser==series,'native chart cursor binds actual series sample for rendering',point_id=cursor.point_id,pos_set=cursor.pos_set)
    emit('get_pressed_point',obj.get_pressed_point()==0x7FFFFFFF,'fresh native chart has no pressed sample')
    obj.hide_series(other,True);emit('hide_series',other.hidden,'native hide changes the series hidden bit');obj.remove_series(other);emit('remove_series',obj.get_series_next(series) is None,'native removal unlinks second series')
    print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.chart','method':'set_div_line_count','status':'CALL_OK','oracle':'native grid-line counts supplied; independent rendering count oracle pending'}))
    obj.refresh();emit('refresh',values()==[20,70,60],'refresh preserves actual sampled data')
    ext=array.array('i',[5,15,25]);_keep.append(ext);obj.set_series_ext_y_array(series,ext);emit('set_series_ext_y_array',values()==[5,15,25],'rooted external Y buffer is adopted exactly')
    obj.set_type(lv.chart.TYPE.SCATTER);obj.set_series_values2(series,[10,20,30],[30,40,50],3)
    def xs():return list(struct.unpack('3i',obj.get_series_x_array(series).__dereference__(12)))
    emit(['set_series_values2','get_series_x_array'],xs()==[10,20,30] and values()==[30,40,50],'scatter native buffers retain paired X/Y values')
    obj.set_series_value_by_id2(series,1,35,65);emit('set_series_value_by_id2',xs()[1]==35 and values()[1]==65,'scatter indexed update changes matched X/Y sample')
    obj.set_x_start_point(series,0);obj.set_next_value2(series,45,75);emit('set_next_value2',xs()[0]==45 and values()[0]==75,'scatter circular next update changes paired sample')
    extx=array.array('i',[7,17,27]);_keep.append(extx);obj.set_series_ext_x_array(series,extx);emit('set_series_ext_x_array',xs()==[7,17,27],'native external X buffer adopted exactly')
    obj.set_type(lv.chart.TYPE.BAR);obj.update_layout();offset=obj.get_first_point_center_offset();emit('get_first_point_center_offset',offset>0 and offset<obj.get_content_width()//3,'bar center lies inside the first native sample slot',offset=offset);obj.delete()

def msgbox():
    obj=fixture('msgbox');title=obj.add_title('Title');text=obj.add_text('Body');header=obj.add_header_button(lv.SYMBOL.OK);footer=obj.add_footer_button('Confirm');close=obj.add_close_button()
    emit(['add_title','get_title','add_text','get_content','add_header_button','get_header','add_footer_button','get_footer','add_close_button'],title==obj.get_title() and title.get_text()=='Title' and text.get_text()=='Body' and text.get_parent()==obj.get_content() and header.get_parent()==obj.get_header() and footer.get_parent()==obj.get_footer() and close.get_parent()==obj.get_header(),'native message-box controls have correct actual containers and content')
    parent=obj.get_parent();before=parent.get_child_count();obj.close();emit('close',parent.get_child_count()==before-1,'native close synchronously removes one message box')
    obj=fixture('msgbox');before=page.get_child_count();obj.close_async();settle();emit('close_async',page.get_child_count()==before-1,'native deferred close removes the message box on the event loop')

def win():
    obj=fixture('win');title=obj.add_title('Window');button=obj.add_button(lv.SYMBOL.CLOSE,30);obj.update_layout()
    emit(['add_title','add_button','get_header','get_content'],title.get_text()=='Window' and title.get_parent()==obj.get_header() and button.get_parent()==obj.get_header() and button.get_width()==30 and obj.get_content().get_parent()==obj,'native window header controls, width and content ownership');obj.delete()

def small():
    global _target
    _target='lvgl.switch';obj=fixture('switch');obj.set_orientation(lv.switch.ORIENTATION.VERTICAL);emit(['set_orientation','get_orientation'],obj.get_orientation()==lv.switch.ORIENTATION.VERTICAL,'native switch orientation');obj.delete()
    _target='lvgl.spinner';obj=fixture('spinner');obj.set_anim_params(500,90);emit('set_anim_params',lv.anim_count_running()>0,'native spinner creates its animation schedule');obj.delete()
    _target='lvgl.buttonmatrix';obj=fixture('buttonmatrix');mapping=['A','B',''];_keep.append(mapping);obj.set_map(mapping);ctrl=[lv.buttonmatrix.CTRL.CHECKABLE,lv.buttonmatrix.CTRL.DISABLED];_keep.append(ctrl);obj.set_ctrl_map(ctrl);emit('set_ctrl_map',obj.has_button_ctrl(0,lv.buttonmatrix.CTRL.CHECKABLE) and obj.has_button_ctrl(1,lv.buttonmatrix.CTRL.DISABLED),'native control array applies distinct bits per button');obj.set_button_width(0,3);obj.update_layout();emit('set_button_width',(obj.has_button_ctrl(0,3)),'native button width is stored in the low control bits');obj.delete()
    _target='lvgl.line';obj=fixture('line');points=[{'x':10,'y':20},{'x':30,'y':40}];_keep.append(points);obj.set_points_mutable(points,2);actual=obj.get_points_mutable();immutable=obj.get_points();emit(['set_points_mutable','get_points_mutable','get_points'],obj.is_point_array_mutable() and actual[0].x==10 and actual[1].y==40 and immutable[1].x==30,'native mutable point array returns both exact coordinates');obj.delete()
    _target='lvgl.spinbox';obj=fixture('spinbox');obj.set_digit_format(4,0);obj.set_range(0,9999);obj.set_value(1234);obj.set_cursor_pos(1);emit('set_cursor_pos',obj.get_step()==10,'native cursor digit selects decimal step');obj.set_digit_step_direction(lv.DIR.LEFT)
    encoder=lv.indev_create();encoder.set_type(lv.INDEV_TYPE.ENCODER);encoder.set_mode(lv.INDEV_MODE.EVENT);group=lv.group_create();group.add_obj(obj);encoder.set_group(group);group.set_editing(True);pressed=[False]
    def encoder_read(indev,data):data.state=lv.INDEV_STATE.PRESSED if pressed[0] else lv.INDEV_STATE.RELEASED;data.enc_diff=0
    encoder.set_read_cb(encoder_read);obj.set_cursor_pos(1);encoder.read();pressed[0]=True;encoder.read();pressed[0]=False;encoder.read();emit('set_digit_step_direction',obj.get_step()==100,'native encoder release moves one digit left',step=obj.get_step());encoder.delete();group.delete();obj.delete()
    _target='lvgl.table';obj=fixture('table');obj.set_row_count(2);obj.set_column_count(3);obj.set_selected_cell(1,2);row=bytearray(4);col=bytearray(4);obj.get_selected_cell(row,col);r=struct.unpack('I',row)[0];c=struct.unpack('I',col)[0];emit(['set_selected_cell','get_selected_cell'],r==1 and c==2,'native selected cell writes both output integer buffers',row=r,column=c);obj.set_cell_user_data(1,2,None);emit(['set_cell_user_data','get_cell_user_data'],obj.get_cell_user_data(1,2) is None,'native cell-specific null user-data roundtrip');obj.delete()
    _target='lvgl.textarea';obj=fixture('textarea');obj.set_one_line(False);obj.set_text('AB\nCD');obj.set_cursor_pos(1);obj.cursor_down();down=obj.get_cursor_pos();obj.cursor_up();up=obj.get_cursor_pos();emit(['cursor_down','cursor_up'],down==4 and up==1,'native vertical cursor movement follows same glyph column',down=down,up=up);obj.set_align(lv.TEXT_ALIGN.RIGHT);emit('set_align',obj.get_style_text_align(0)==lv.TEXT_ALIGN.RIGHT,'native textarea alignment reaches its text style')
    def insertion(e):obj.set_insert_replace('X')
    obj.add_event_cb(insertion,lv.EVENT.INSERT,None);obj.set_text('');obj.add_text('Z');emit('set_insert_replace',obj.get_text()=='X','native INSERT callback replaces incoming text');obj.delete()

def canvas():
    obj=fixture('canvas');raw=bytearray(8*8*4+16);_keep.append(raw);obj.set_buffer(raw,8,8,lv.COLOR_FORMAT.ARGB8888);obj.fill_bg(lv.color_hex(0x2255AA),255);obj.set_px(3,4,lv.color_hex(0xCC6633),255);pixel=obj.get_px(3,4);background=obj.get_px(0,0);draw=obj.get_draw_buf();image=obj.get_image()
    emit(['set_buffer','fill_bg','set_px','get_px','get_draw_buf','get_image','get_buf'],(pixel.red,pixel.green,pixel.blue,pixel.alpha)==(204,102,51,255) and (background.red,background.green,background.blue)==(34,85,170) and draw.header.w==8 and image.header.h==8 and bytes(obj.get_buf().__dereference__(4))==b'\xAA\x55\x22\xFF','native canvas writes real ARGB pixel bytes and descriptors')
    size=lv.canvas.buf_size(8,8,32,4);emit('buf_size',size==8*8*4+lv.DRAW_BUF_ALIGN,'native buffer sizing matches row alignment and mandatory allocation slack',size=size)
    second=lv.draw_buf_create(8,8,lv.COLOR_FORMAT.ARGB8888,32);second.clear(None);obj.set_draw_buf(second);emit('set_draw_buf',obj.get_draw_buf().header.w==8 and obj.get_px(3,4).alpha==0,'native draw-buffer adoption changes actual canvas storage')
    obj.copy_buf(lv.area_t({'x1':0,'y1':0,'x2':7,'y2':7}),draw,None);pixel=obj.get_px(3,4);emit('copy_buf',(pixel.red,pixel.green,pixel.blue)==(204,102,51),'native buffer copy fills canvas from the supplied source draw buffer')
    layer=lv.layer_t();obj.init_layer(layer);emit('init_layer',layer.draw_buf.header.w==8 and layer.buf_area.x2==7 and layer.buf_area.y2==7,'native canvas layer references full draw-buffer bounds')
    dsc=lv.draw_rect_dsc_t();dsc.init();dsc.bg_color=lv.color_hex(0x00FF00);dsc.bg_opa=255;area=lv.area_t({'x1':1,'y1':1,'x2':2,'y2':2});lv.draw_rect(layer,dsc,area);obj.finish_layer(layer);pixel=obj.get_px(1,1);emit('finish_layer',(pixel.red,pixel.green,pixel.blue)==(0,255,0),'native queued draw task reaches canvas buffer on layer finish');obj.delete();second.destroy()
    obj=fixture('canvas');palettebuf=bytearray(64);_keep.append(palettebuf);obj.set_buffer(palettebuf,8,8,lv.COLOR_FORMAT.I1);color=lv.color32_t({'red':255,'green':0,'blue':0,'alpha':255});obj.set_palette(1,color);obj.set_px(0,0,lv.color_hex(1),255);actual=bytes(obj.get_draw_buf().data.__dereference__(9));emit('set_palette',actual[4:8]==b'\x00\x00\xFF\xFF' and actual[8]==128,'indexed native canvas stores exact palette BGRA bytes and index bit',bytes=list(actual));obj.delete()

def menu():
    obj=fixture('menu');first=lv.menu_page(obj,'First');second=lv.menu_page(obj,'Second');sidebar=lv.menu_page(obj,'Sidebar');obj.set_page(first);obj.set_sidebar_page(sidebar)
    emit(['set_page','get_cur_main_page','set_sidebar_page','get_cur_sidebar_page'],obj.get_cur_main_page()==first and obj.get_cur_sidebar_page()==sidebar,'native menu selects exact allocated main and sidebar pages')
    header=obj.get_main_header();back=obj.get_main_header_back_button();sideheader=obj.get_sidebar_header();sideback=obj.get_sidebar_header_back_button()
    emit(['get_main_header','get_main_header_back_button','get_sidebar_header','get_sidebar_header_back_button'],back.get_parent()==header and sideback.get_parent()==sideheader,'native menu back buttons belong to the matching real headers')
    # Page titles are reflected by the main header's label on page selection.
    title=header.get_child(1)
    for method, text in (('set_page_title', 'Renamed'), ('set_page_title_static', 'Static title')):
        _keep.append(text)
        try:
            getattr(lv.menu, method)(first, text)
            obj.set_page(first)
            emit(method, title.get_text()==text, 'native menu page title reaches header label')
        except TypeError as error:
            print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.menu','method':method,'status':'UNSUPPORTED_BINDING','error':repr(error),'oracle':'namespace helper requires actual native menu page, not a menu receiver'}))
    obj.set_mode_root_back_button(lv.menu.ROOT_BACK_BUTTON.ENABLED);emit(['set_mode_root_back_button','back_button_is_root'],obj.back_button_is_root(back),'native root-back setting identifies root header button')
    button=lv.button(first);obj.set_load_page_event(button,second);button.send_event(lv.EVENT.CLICKED,None);emit('set_load_page_event',obj.get_cur_main_page()==second,'native CLICKED event loads bound second menu page')
    obj.clear_history();obj.set_page(first);emit('clear_history',obj.back_button_is_root(back),'cleared native navigation history returns to root')
    obj.set_mode_header(lv.menu.HEADER.TOP_FIXED);obj.update_layout();top=header.get_y()
    obj.set_mode_header(lv.menu.HEADER.BOTTOM_FIXED);obj.update_layout();bottom=header.get_y();emit('set_mode_header',bottom>top,'native header changes from top to bottom position',top=top,bottom=bottom);obj.delete()

def scale():
    obj=fixture('scale');obj.set_size(160,160);obj.set_mode(lv.scale.MODE.ROUND_OUTER);obj.set_total_tick_count(11);obj.set_major_tick_every(2);obj.set_label_show(True);obj.set_range(0,100);obj.set_angle_range(180);obj.set_rotation(90)
    emit(['set_mode','get_mode','set_total_tick_count','get_total_tick_count','set_major_tick_every','get_major_tick_every','set_label_show','get_label_show','set_range','get_range_min_value','get_range_max_value','set_angle_range','get_angle_range','set_rotation','get_rotation'],obj.get_mode()==lv.scale.MODE.ROUND_OUTER and obj.get_total_tick_count()==11 and obj.get_major_tick_every()==2 and obj.get_label_show() and obj.get_range_min_value()==0 and obj.get_range_max_value()==100 and obj.get_angle_range()==180 and obj.get_rotation()==90,'native scale exact mode/range/ticks/angles readback')
    line=lv.line(obj);obj.update_layout();obj.set_line_needle_value(line,40,50);points=line.get_points();emit('set_line_needle_value',line.get_point_count()==2 and (points[0].x!=points[1].x or points[0].y!=points[1].y),'native scale produces a real two-point needle for the requested nonzero length',points=[[points[i].x,points[i].y] for i in range(2)])
    image=lv.image(obj);image.set_src(raw_image());obj.set_image_needle_value(image,50);emit('set_image_needle_value',image.get_rotation()==1800,'native midpoint image needle derives rotation from 90 degree origin and 180 degree range',rotation=image.get_rotation())
    texts=['low','mid','high',None];_keep.append(texts);obj.set_text_src(texts);print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.scale','method':'set_text_src','status':'CALL_OK','oracle':'rooted NULL-terminated native text array supplied; exact glyph oracle pending'}))
    obj.set_post_draw(True);obj.set_draw_ticks_on_top(True);print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.scale','method':'set_post_draw','status':'CALL_OK','oracle':'native setter executed; drawing-order pixel oracle pending'}));print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.scale','method':'set_draw_ticks_on_top','status':'CALL_OK','oracle':'native setter executed; tick-over-arc pixel oracle pending'}))
    section=obj.add_section();obj.set_section_range(section,20,80);emit(['add_section','set_section_range'],section.range_min==20 and section.range_max==80,'native section allocation and inclusive range')
    style=lv.style_t();style.init();style.set_line_color(lv.color_hex(0xAABBCC));_keep.append(style)
    for method,field in [('set_section_style_main','main_style'),('set_section_style_indicator','indicator_style'),('set_section_style_items','items_style')]:
        getattr(obj,method)(section,style);actual=getattr(section,field);prop=lv.style_value_t();actual.get_prop(lv.STYLE.LINE_COLOR,prop);emit(method,prop.color.to_int()==0xAABBCC,'native section stores the actual line-color style')
    section.set_range(30,70);section.set_style(lv.PART.MAIN,style)
    for method,ok in [('set_range',section.range_min==30 and section.range_max==70),('set_style',section.main_style is not None)]:
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.scale_section_t','method':method,'status':'STATE_PASS' if ok else 'FAIL','oracle':'actual returned section direct method roundtrip'}))
    for method,args in [('section_set_range',(section,35,65)),('section_set_style',(section,lv.PART.MAIN,style))]:
        try:
            getattr(lv.scale,method)(*args);emit(method,True,'explicit class namespace alias accepts its actual scale section')
        except Exception as error:print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.scale','method':method,'status':'FAIL','error':repr(error),'oracle':'class namespace alias must accept actual scale_section_t, not a scale widget'}))
    obj.delete()

def spangroup():
    obj=fixture('spangroup');obj.set_mode(lv.SPAN_MODE.FIXED);obj.set_align(lv.TEXT_ALIGN.LEFT);obj.set_overflow(lv.SPAN_OVERFLOW.CLIP);obj.set_indent(0);obj.set_max_lines(2)
    emit(['set_mode','get_mode','set_align','get_align','set_overflow','get_overflow','set_indent','get_indent','set_max_lines','get_max_lines'],obj.get_mode()==lv.SPAN_MODE.FIXED and obj.get_align()==lv.TEXT_ALIGN.LEFT and obj.get_overflow()==lv.SPAN_OVERFLOW.CLIP and obj.get_indent()==0 and obj.get_max_lines()==2,'native span group exact layout settings')
    first=obj.add_span();obj.set_span_text(first,'AB');second=obj.add_span();static='CD';_keep.append(static);obj.set_span_text_static(second,static)
    emit(['add_span','set_span_text','set_span_text_static','get_child','get_span_count'],obj.get_span_count()==2 and obj.get_child(0)==first and first.txt=='AB' and second.txt=='CD','native spans preserve text and insertion order')
    style=lv.style_t();style.init();style.set_text_color(lv.color_hex(0x2255AA));style.set_text_font(lv.font_montserrat_14);obj.set_span_style(first,style);_keep.append(style);obj.refresh();obj.update_layout();settle()
    value=lv.style_value_t();first.style.get_prop(lv.STYLE.TEXT_COLOR,value);emit(['set_span_style','refresh'],value.color.to_int()==0x2255AA and first.txt=='AB','native span style and explicit refresh retain content')
    height=obj.get_max_line_height();width=obj.get_expand_width(1000);expanded=obj.get_expand_height(220)
    emit(['get_max_line_height','get_expand_width','get_expand_height'],height==lv.font_montserrat_14.line_height and width>0 and expanded==height,'single native span row has font-derived line height and calculated expansion',height=height,width=width,expanded=expanded)
    coords=obj.get_span_coords(first);area=coords.middle;point=lv.point_t({'x':obj.get_x()+area.x1+1,'y':obj.get_y()+area.y1+1});span=obj.get_span_by_point(point)
    emit(['get_span_coords','get_span_by_point'],area.x2>=area.x1 and area.y2>=area.y1 and span==first,'native span bounding region resolves back to original span',area=[area.x1,area.y1,area.x2,area.y2]);obj.delete_span(second);emit('delete_span',obj.get_span_count()==1 and obj.get_child(0)==first,'native deletion removes only specified span')
    first.set_text('EF');text=first.get_text();first.set_text_static('GH');static_text=first.get_text();actual=first.get_style();value=lv.style_value_t();actual.get_prop(lv.STYLE.TEXT_COLOR,value)
    for method in ['set_text','get_text','set_text_static','get_style']:print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.span_t','method':method,'status':'STATE_PASS' if text=='EF' and static_text=='GH' and value.color.to_int()==0x2255AA else 'FAIL','oracle':'returned span direct text and style methods retain exact values'}))
    obj.delete()

def codes():
    global _target
    global _target
    _target='lvgl.barcode';obj=fixture('barcode');obj.set_dark_color(lv.color_hex(0x102030));obj.set_light_color(lv.color_hex(0xF0E0D0));obj.set_scale(2)
    emit(['set_dark_color','get_dark_color','set_light_color','get_light_color','set_scale','get_scale'],obj.get_dark_color().to_int()==0x102030 and obj.get_light_color().to_int()==0xF0E0D0 and obj.get_scale()==2,'native barcode color/scale getters')
    obj.set_direction(lv.DIR.HOR);obj.set_tiled(False);result=obj.update('M5-2026');obj.update_layout();emit(['set_direction','set_tiled','update'],result==lv.RESULT.OK and obj.get_width()>30,'native barcode encoder accepts requested data and allocates bar pixels',width=obj.get_width());obj.delete()
    _target='lvgl.qrcode';obj=lv.qrcode(page);obj.set_pos(20,40);obj.set_size(120);obj.update_layout();obj.set_dark_color(lv.color_hex(0x000000));obj.set_light_color(lv.color_hex(0xFFFFFF));text='M5-NATIVE-QR';result=obj.update(text,len(text));emit(['set_size','update'],result==lv.RESULT.OK and obj.get_width()==120,'native QR encoder accepts exact bytes and requested size')
    print('M5EMU_UI_FRAME_ORACLE '+json.dumps({'api_target':'lvgl.qrcode','method':'update','oracle':{'kind':'qr_decode','text':text}}));print('M5EMU_UI_FRAME_ORACLE '+json.dumps({'api_target':'lvgl.qrcode','method':'set_dark_color','oracle':{'kind':'color_region','rgb':0,'box':[20,40,140,160],'minimum':200}}));print('M5EMU_UI_FRAME_ORACLE '+json.dumps({'api_target':'lvgl.qrcode','method':'set_light_color','oracle':{'kind':'color_region','rgb':0xFFFFFF,'box':[20,40,140,160],'minimum':200}}));_keep.append(obj)

def gif():
    import os
    obj=fixture('gif');obj.set_src('S:'+os.getcwd()+'/fixture.gif');loaded=obj.is_loaded();obj.set_loop_count(3);count=obj.get_loop_count();emit(['set_src','is_loaded','set_loop_count','get_loop_count'],loaded and count==3,'native file decoder loads the two-frame GIF and keeps exact repeat count')
    obj.pause();settle(350);paused=obj.get_loop_count();emit('pause',paused==3,'paused native GIF does not consume loops over multiple frame delays',loops=paused)
    obj.resume();settle(450);resumed=obj.get_loop_count();emit('resume',0<=resumed<3,'resumed native GIF consumes real frame loops',loops=resumed)
    obj.restart();emit('restart',obj.get_loop_count()==-1,'native rewind resets loop state before reading animation header');obj.delete()

def tree():
    global _target
    _target='lvgl.tree_class_t';cls=lv.tree_class_t();cls.instance_size=len(lv.tree_node_t().__dereference__());root=cls.node_create(None);child=cls.node_create(root);emit('node_create',root.child_cnt==1 and lv.tree_node_t.__cast__(child.parent)==root,'owned native tree node creation establishes actual parent/child relationship')
    _target='lvgl.tree_node_t';visited=[];data={'visited':visited}
    def walk(node,user):user.__cast__()['visited'].append(node);return True
    result=root.walk(lv.TREE_WALK.PRE_ORDER,walk,None,None,data);emit('walk',result and visited==[root,child],'native preorder callback visits exact root then child')
    child.delete();emit('delete',bytes(root.children.__dereference__(4))==b'\0'*4,'native deletion clears exact parent slot; this implementation retains child_cnt and allocator bytes are not measured');root.delete()

def extras():
    global _target
    _target='lvgl.list'
    obj=fixture('list')
    text=obj.add_text('List text')
    try:
        emit('add_text',text.get_text()=='List text','returned list text exposes its actual label content')
    except AttributeError as error:
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':_target,'method':'add_text','status':'FAIL','error':repr(error),'oracle':'returned native list label must expose its label methods'}))
    button=obj.add_button(None,'Button');before=obj.get_button_text(button);obj.set_button_text(button,'Updated')
    emit(['add_button','get_button_text','set_button_text'],before=='Button' and obj.get_button_text(button)=='Updated','actual list button text changes independently of private list-text subclasses');obj.delete()
    _target='lvgl.label';obj=fixture('label');subject=lv.subject_t();subject.init_int(12);observer=obj.bind_text(subject,'Value %d');before=obj.get_text();subject.set_int(34);emit('bind_text',before=='Value 12' and obj.get_text()=='Value 34','native subject observer updates formatted label text');obj.delete();subject.deinit()
    _target='lvgl.arc';obj=fixture('arc');obj.set_size(100,100);obj.set_rotation(0);obj.set_bg_angles(0,180);obj.set_range(0,100);obj.set_value(50);obj.set_style_arc_width(10,lv.PART.INDICATOR);obj.set_style_pad_all(0,0);obj.update_layout();marker=lv.obj(page);marker.remove_style_all();marker.set_size(10,10);obj.align_obj_to_angle(marker,0);marker.update_layout();x,y=marker.get_x(),marker.get_y();emit('align_obj_to_angle',abs(x-65)<=1 and abs(y-130)<=1,'midpoint arc at ninety degrees aligns marker below its center',x=x,y=y);obj.rotate_obj_to_angle(marker,0);emit('rotate_obj_to_angle',marker.get_style_transform_rotation(0)==1800,'native marker transform follows ninety-degree arc plus glyph origin');obj.set_change_rate(123);print('M5EMU_UI_RESULT '+json.dumps({'api_target':_target,'method':'set_change_rate','status':'CALL_OK','oracle':'setter executed; time-dependent pointer drag rate oracle pending'}));marker.delete();obj.delete()
    _target='lvgl.calendar';obj=fixture('calendar');header=lv.calendar_header_dropdown(obj);obj.header_dropdown_set_year_list('2025\n2026\n2027');year=header.get_child(0);emit('header_dropdown_set_year_list',year.get_options()=='2025\n2026\n2027','native calendar helper updates actual year dropdown options')
    _target='lvgl.calendar_header_dropdown'
    try:lv.calendar_header_dropdown.header_dropdown_set_year_list(obj,'2024\n2025');emit('header_dropdown_set_year_list',year.get_options()=='2024\n2025','explicit cross-object class alias updates actual calendar parent')
    except TypeError as error:print('M5EMU_UI_RESULT '+json.dumps({'api_target':_target,'method':'header_dropdown_set_year_list','status':'UNSUPPORTED_BINDING','error':repr(error),'oracle':'class alias requires actual calendar parent'}))
    obj.delete()
    _target='lvgl.keyboard';text=lv.textarea(page);obj=fixture('keyboard');mapping=['Z',''];controls=[1];_keep.extend([mapping,controls]);obj.set_map(lv.keyboard.MODE.USER_1,mapping,controls);obj.set_mode(lv.keyboard.MODE.USER_1);obj.set_textarea(text);emit('set_map',obj.get_button_text(0)=='Z','native custom keyboard map exposes exact requested key');obj.send_event(lv.EVENT.KEY,struct.pack('I',lv.KEY.RIGHT))
    def event(e):
        previous=e.code;e.code=lv.EVENT.VALUE_CHANGED
        try:lv.keyboard.def_event_cb(e)
        finally:e.code=previous
    obj.add_event_cb(event,lv.EVENT.CLICKED,None)
    try:
        obj.send_event(lv.EVENT.CLICKED,None);emit('def_event_cb',text.get_text()=='Z','explicit default event callback inserts selected actual custom key into textarea')
    except TypeError as error:
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':_target,'method':'def_event_cb','status':'UNSUPPORTED_BINDING','error':repr(error),'oracle':'namespace callback requires actual event, not a keyboard receiver'}))
    obj.delete();text.delete()

M5.begin();m5ui.init()
try:
    page=m5ui.M5Page(bg_c=0x0B1014);page.screen_load()
    for name,fn in [('image',image),('animimg',animimg),('imagebutton',imagebutton),('calendar',calendar),('chart',chart),('msgbox',msgbox),('win',win),('small',small),('canvas',canvas),('menu',menu),('scale',scale),('spangroup',spangroup),('codes',codes),('gif',gif),('tree',tree),('extras',extras)]:
        if not globals().get('NATIVE_WIDGET_GROUP') or name==NATIVE_WIDGET_GROUP:group(name,fn)
    done=lv.label(page);done.set_text('Native resource fixtures');done.set_pos(10,10);settle();print('M5EMU_UI_READY '+json.dumps({'scope':'native resource widgets'}))
    while True:M5.update();time.sleep_ms(20)
finally:m5ui.deinit()
