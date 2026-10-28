"""Native object style resources, layouts, transforms and drawing descriptors."""
import time,json,sys,struct
import M5,m5ui,lvgl as lv
_keep=[]
def emit(methods,ok,oracle,**details):
    if isinstance(methods,str):methods=[methods]
    for m in methods:print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.obj','method':m,'status':'STATE_PASS' if ok else 'FAIL','oracle':oracle,'details':details}))
def group(name,fn):
    try:fn();print('M5EMU_UI_GROUP_DONE '+json.dumps({'group':name}))
    except Exception as e:print('M5EMU_UI_GROUP_ERROR '+json.dumps({'group':name,'error':repr(e)}));sys.print_exception(e)
def settle(ms=120):
    deadline=time.ticks_add(time.ticks_ms(),ms)
    while time.ticks_diff(deadline,time.ticks_ms())>0:M5.update();time.sleep_ms(10)
def make(parent=None):
    o=lv.obj(page if parent is None else parent);o.remove_style_all();o.set_pos(0,0);o.set_size(100,60);o.update_layout();return o

def resources():
    obj=make();style=lv.style_t();style.init();style.set_bg_color(lv.color_hex(0x123456));obj.add_style(style,0);first=obj.get_style_bg_color(0).to_int();other=lv.style_t();other.init();other.set_bg_color(lv.color_hex(0x654321));changed=obj.replace_style(style,other,0)
    emit(['add_style','replace_style'],first==0x123456 and changed and obj.get_style_bg_color(0).to_int()==0x654321,'native style replacement changes exact resolved property')
    obj.remove_style(other,0);obj.remove_style_all();emit(['remove_style','remove_style_all'],not obj.has_style_prop(0,lv.STYLE.BG_COLOR),'native style removal clears the resolved property source')
    value=lv.style_value_t();value.num=137;obj.set_local_style_prop(lv.STYLE.WIDTH,value,0);out=lv.style_value_t();result=obj.get_local_style_prop(lv.STYLE.WIDTH,out,0);resolved=obj.get_style_prop(0,lv.STYLE.WIDTH)
    emit(['set_local_style_prop','get_local_style_prop','get_style_prop','has_style_prop'],result==1 and out.num==137 and resolved.num==137 and obj.has_style_prop(0,lv.STYLE.WIDTH),'native local style stores and resolves exact typed numeric value')
    removed=obj.remove_local_style_prop(lv.STYLE.WIDTH,0);after=lv.style_value_t();status=obj.get_local_style_prop(lv.STYLE.WIDTH,after,0);present=obj.has_style_prop(0,lv.STYLE.WIDTH);emit('remove_local_style_prop',removed and status==0 and obj.get_style_prop(0,lv.STYLE.WIDTH).num==obj.get_class().width_def,'removing native local property restores class default width',returned=removed,local_status=status,has_property=present,resolved=obj.get_style_prop(0,lv.STYLE.WIDTH).num,default=obj.get_class().width_def)
    selector=lv.PART.INDICATOR|lv.STATE.PRESSED
    emit(['style_get_selector_part','style_get_selector_state'],lv.obj.style_get_selector_part(selector)==lv.PART.INDICATOR and lv.obj.style_get_selector_state(selector)==lv.STATE.PRESSED,'native static selector helpers split actual state and part bits')
    grad=lv.grad_dsc_t();grad.horizontal_init();colors=lv.color_t(2);colors[0]=lv.color_hex(0xFF0000);colors[1]=lv.color_hex(0x0000FF);grad.init_stops(colors,bytes([255,255]),bytes([0,255]),2)
    image=lv.image_dsc_t({'header':{'magic':0x19,'cf':lv.COLOR_FORMAT.RGB565,'w':2,'h':2,'stride':4},'data_size':8,'data':bytearray(b'\x00\xf8'*4)})
    filt=lv.color_filter_dsc_t();filt.init(lambda d,c,o:lv.color_hex(0x334455))
    anim=lv.anim_t();anim.init();anim.set_duration(123)
    transition=lv.style_transition_dsc_t();props=struct.pack('ii',lv.STYLE.WIDTH,0);transition.init(props,lv.anim_t.path_linear,77,13,None)
    tracks=struct.pack('iii',20,30,lv.GRID_TEMPLATE_LAST)
    items=[('bg_grad',grad),('bg_image_src',image),('arc_image_src',image),('text_font',lv.font_get_default()),('color_filter_dsc',filt),('anim',anim),('transition',transition),('bitmap_mask_src',image),('grid_column_dsc_array',tracks),('grid_row_dsc_array',tracks)]
    _keep.extend([style,other,colors,grad,image,filt,anim,transition,props,tracks])
    for name,resource in items:
        setter='set_style_'+name;getter='get_style_'+name;getattr(obj,setter)(resource,0);actual=getattr(obj,getter)(0);count=8 if isinstance(resource,bytes) else len(resource.__dereference__());expected=resource[:count] if isinstance(resource,bytes) else bytes(resource.__dereference__());observed=bytes(actual.__dereference__(count))
        emit([setter,getter],observed==expected,'native object style resource pointer resolves exact typed descriptor bytes',resource=name)
    obj.set_style_color_filter_opa(255,0)
    for name in ['bg_color','bg_grad_color','bg_image_recolor','border_color','shadow_color','outline_color','text_color','image_recolor','line_color','arc_color']:
        getattr(obj,'set_style_'+name)(lv.color_hex(0x123456),0);getter='get_style_'+name+'_filtered';actual=getattr(obj,getter)(0).to_int();emit(getter,actual==0x334455,'native filtered style color invokes configured actual Python filter',actual=actual)
    v=lv.style_value_t();v.color=lv.color_hex(0x123456);actual=obj.style_apply_color_filter(0,v);emit('style_apply_color_filter',actual.color.to_int()==0x334455,'native style-value filter invokes configured color transformation')
    obj.delete()

def combinations():
    obj=make();obj.set_style_pad_all(7,0);emit('set_style_pad_all',all(getattr(obj,'get_style_pad_'+side)(0)==7 for side in ('left','right','top','bottom')),'native padding shorthand sets all four sides')
    obj.set_style_pad_hor(8,0);obj.set_style_pad_ver(9,0);obj.set_style_pad_gap(10,0);emit(['set_style_pad_hor','set_style_pad_ver','set_style_pad_gap'],obj.get_style_pad_left(0)==8 and obj.get_style_pad_right(0)==8 and obj.get_style_pad_top(0)==9 and obj.get_style_pad_bottom(0)==9 and obj.get_style_pad_row(0)==10 and obj.get_style_pad_column(0)==10,'native axis/gap shorthands retain independently requested values')
    obj.set_style_margin_all(3,0);emit('set_style_margin_all',all(getattr(obj,'get_style_margin_'+side)(0)==3 for side in ('left','right','top','bottom')),'native margin shorthand sets all sides');obj.set_style_margin_hor(4,0);obj.set_style_margin_ver(5,0);emit(['set_style_margin_hor','set_style_margin_ver'],obj.get_style_margin_left(0)==4 and obj.get_style_margin_right(0)==4 and obj.get_style_margin_top(0)==5 and obj.get_style_margin_bottom(0)==5,'native axis margin shorthand values')
    obj.set_style_size(42,43,0);emit('set_style_size',obj.get_style_width(0)==42 and obj.get_style_height(0)==43,'native style size shorthand sets both dimensions')
    obj.set_style_transform_scale(512,0);emit('set_style_transform_scale',obj.get_style_transform_scale_x(0)==512 and obj.get_style_transform_scale_y(0)==512,'native uniform transform scale sets both axes')
    obj.set_style_transform_scale_x(0,0);obj.set_style_transform_scale_y(0,0);emit(['get_style_transform_scale_x_safe','get_style_transform_scale_y_safe'],obj.get_style_transform_scale_x_safe(0)==1 and obj.get_style_transform_scale_y_safe(0)==1,'native safe getters clamp zero scale to one')
    obj.set_style_border_width(2,0);obj.set_style_border_side(lv.BORDER_SIDE.FULL,0)
    emit(['get_style_space_left','get_style_space_right','get_style_space_top','get_style_space_bottom'],[getattr(obj,'get_style_space_'+x)(0) for x in ('left','right','top','bottom')]==[10,10,11,11],'native content space combines each padding with enabled border')
    obj.set_style_opa(255,0);emit('get_style_opa_recursive',obj.get_style_opa_recursive(0)==255,'fully opaque actual parent chain remains fully opaque')
    obj.set_style_text_align(lv.TEXT_ALIGN.AUTO,0);obj.set_style_base_dir(lv.BASE_DIR.LTR,0);emit('calculate_style_text_align',obj.calculate_style_text_align(0,'abc')==lv.TEXT_ALIGN.LEFT,'native automatic text alignment resolves LTR glyph text')
    obj.delete()

def layouts():
    parent=make();parent.set_size(200,60);parent.set_flex_flow(lv.FLEX_FLOW.ROW);parent.set_flex_align(lv.FLEX_ALIGN.START,lv.FLEX_ALIGN.CENTER,lv.FLEX_ALIGN.START);parent.set_style_pad_column(10,0);a=make(parent);a.set_size(20,10);b=make(parent);b.set_size(30,20);parent.update_layout()
    emit(['set_flex_flow','set_flex_align','is_layout_positioned'],(a.get_x(),a.get_y(),b.get_x(),b.get_y())==(0,5,30,0) and a.is_layout_positioned(),'native flex positions actual children with exact gap/cross alignment',positions=[a.get_x(),a.get_y(),b.get_x(),b.get_y()])
    b.set_flex_grow(1);parent.update_layout();emit('set_flex_grow',b.get_width()==170,'native flex growth consumes remaining parent content width',width=b.get_width());parent.delete()
    parent=make();parent.set_size(200,100);cols=[50,60,lv.GRID_TEMPLATE_LAST];rows=[30,40,lv.GRID_TEMPLATE_LAST];_keep.extend([cols,rows]);parent.set_grid_dsc_array(cols,rows);parent.set_layout(lv.LAYOUT.GRID);parent.set_grid_align(lv.GRID_ALIGN.CENTER,lv.GRID_ALIGN.CENTER);child=make(parent);child.set_grid_cell(lv.GRID_ALIGN.STRETCH,1,1,lv.GRID_ALIGN.STRETCH,0,1);parent.update_layout()
    emit(['set_grid_dsc_array','set_layout','set_grid_align','set_grid_cell'],(child.get_x(),child.get_y(),child.get_width(),child.get_height())==(95,15,60,30),'native grid track arrays determine actual centered child rectangle',rectangle=[child.get_x(),child.get_y(),child.get_width(),child.get_height()]);parent.delete()

def descriptors():
    obj=make();obj.set_style_bg_color(lv.color_hex(0x123456),0);obj.set_style_text_color(lv.color_hex(0x234567),0);obj.set_style_text_font(lv.font_montserrat_14,0);obj.set_style_line_color(lv.color_hex(0x345678),0);obj.set_style_line_width(4,0);obj.set_style_arc_color(lv.color_hex(0x456789),0);obj.set_style_arc_width(5,0);obj.set_style_image_recolor(lv.color_hex(0x56789A),0);obj.set_style_image_recolor_opa(255,0)
    obj.set_style_bg_opa(255,0);r=lv.draw_rect_dsc_t();r.init();obj.init_draw_rect_dsc(0,r);emit('init_draw_rect_dsc',r.bg_color.to_int()==0x123456,'native rectangle draw descriptor resolves object color')
    t=lv.draw_label_dsc_t();t.init();obj.init_draw_label_dsc(0,t);emit('init_draw_label_dsc',t.color.to_int()==0x234567 and t.font.line_height==lv.font_montserrat_14.line_height,'native label draw descriptor resolves exact color and actual font')
    l=lv.draw_line_dsc_t();l.init();obj.init_draw_line_dsc(0,l);emit('init_draw_line_dsc',l.color.to_int()==0x345678 and l.width==4,'native line descriptor resolves color and width')
    a=lv.draw_arc_dsc_t();a.init();obj.init_draw_arc_dsc(0,a);emit('init_draw_arc_dsc',a.color.to_int()==0x456789 and a.width==5,'native arc descriptor resolves color and width')
    i=lv.draw_image_dsc_t();i.init();obj.init_draw_image_dsc(0,i);emit('init_draw_image_dsc',i.recolor.to_int()==0x56789A and i.recolor_opa==255,'native image draw descriptor resolves recolor and opacity')
    obj.set_style_outline_width(7,0);obj.set_style_outline_pad(3,0);obj.refresh_ext_draw_size();actual=obj.get_ext_draw_size();calculated=obj.calculate_ext_draw_size(0);emit(['refresh_ext_draw_size','get_ext_draw_size','calculate_ext_draw_size'],actual==10 and calculated==10,'native extended draw bound includes exact outline width and gap',actual=actual,calculated=calculated)
    obj.set_style_transform_rotation(300,0);obj.update_layer_type();emit(['update_layer_type','get_layer_type'],obj.get_layer_type()==lv.LAYER_TYPE.TRANSFORM,'native object transform selects transformation render layer');obj.delete()

def transforms():
    obj=make();obj.set_style_transform_pivot_x(0,0);obj.set_style_transform_pivot_y(0,0);obj.set_style_transform_scale(512,0);obj.update_layout();p=lv.point_t({'x':10,'y':15});obj.transform_point(p,0);emit('transform_point',(p.x,p.y)==(20,30),'native style scale transforms real point output')
    raw=bytearray(struct.pack('iiii',10,15,20,25));points=lv.point_t.__cast__(raw);obj.transform_point_array(points,2,0);actual=struct.unpack('iiii',raw);emit('transform_point_array',actual==(20,30,40,50),'native point array writes exact transformed coordinates',actual=actual)
    area=lv.area_t({'x1':0,'y1':0,'x2':99,'y2':59});obj.get_transformed_area(area,0);emit('get_transformed_area',(area.x1,area.y1,area.x2,area.y2)==(0,0,200,120),'native transformed rectangle applies style scale to both endpoints',actual=[area.x1,area.y1,area.x2,area.y2]);obj.delete()

def lifecycle():
    obj=make();obj.fade_out(40,0);settle(80);out=obj.get_style_opa(0);obj.fade_in(40,0);settle(80);inside=obj.get_style_opa(0);emit(['fade_out','fade_in'],out==0 and inside==255,'native fade animations reach exact opacity endpoints',out=out,inside=inside);obj.delete()
    obj=make();slot=lv.C_Pointer({'ptr_val':obj});lv.obj.null_on_delete(slot);obj.delete();emit('null_on_delete',slot.ptr_val is None,'native delete event clears actual external object-pointer slot')
    obj=make();animation=lv.anim_t();animation.init();animation.set_var(obj);before=page.get_child_count();lv.obj.delete_anim_completed_cb(animation);emit('delete_anim_completed_cb',page.get_child_count()==before-1,'native completion callback deletes its exact animation target')
    obj=make();obj.set_style_bg_color(lv.color_hex(0x224466),0);obj.refresh_style(0,lv.STYLE.BG_COLOR);emit('refresh_style',obj.get_style_bg_color(0).to_int()==0x224466,'explicit refresh retains actual resolved property');lv.obj.report_style_change(None);lv.obj.enable_style_refresh(False);obj.set_style_width(77,0);lv.obj.enable_style_refresh(True);obj.refresh_style(0,lv.STYLE.WIDTH);obj.update_layout();emit(['report_style_change','enable_style_refresh'],obj.get_width()==77,'native refresh control resumes and applies stored property');obj.delete()

M5.begin();m5ui.init()
try:
    page=m5ui.M5Page(bg_c=0x0B1014);page.screen_load()
    for name,fn in [('resources',resources),('combinations',combinations),('layouts',layouts),('descriptors',descriptors),('transforms',transforms),('lifecycle',lifecycle)]:group(name,fn)
    print('M5EMU_UI_READY '+json.dumps({'scope':'native object resources and layouts'}))
    while True:M5.update();time.sleep_ms(20)
finally:m5ui.deinit()
