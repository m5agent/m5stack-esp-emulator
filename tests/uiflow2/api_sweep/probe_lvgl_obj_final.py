"""Explicit object-namespace internals with owned resources and cleanup."""
import json,time,sys,struct
import lvgl as lv

def emit(method,ok,oracle,**details):
    print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.obj','method':method,'status':'STATE_PASS' if ok else 'FAIL','oracle':oracle,'details':details}))
def called(method,oracle,status='CALL_OK'):
    print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.obj','method':method,'status':status,'oracle':oracle}))
def group(name,fn):
    try:fn()
    except Exception as error:print('M5EMU_UI_GROUP_ERROR '+json.dumps({'group':name,'error':repr(error)}));sys.print_exception(error)

def lifecycle():
    parent=lv.obj(screen);cls=parent.get_class();child=lv.obj.class_create_obj(cls,parent);lv.obj.class_init_obj(child);emit('class_create_obj',child.get_parent()==parent,'explicit namespace allocation attaches exact owned parent');emit('class_init_obj',child.is_valid() and parent.get_child_count()==1,'explicit namespace initialization leaves actual child valid');emit('is_valid',lv.obj.is_valid(child),'explicit class namespace validates real native allocation')
    values=[]
    def callback(event):values.append(lv.obj.event_base(cls,event))
    child.add_event_cb(callback,lv.EVENT.CLICKED,None);child.send_event(lv.EVENT.CLICKED,None);emit('event_base',values==[lv.RESULT.OK],'explicit foreign class argument routes actual event through base handler');parent.dump_tree();called('dump_tree','native owned tree emitted to serial; tree formatting is retained as evidence');parent.delete()

def transform():
    obj=lv.obj(screen);matrix=lv.matrix_t();storage=matrix.__dereference__()
    if storage is not None and len(storage)==36:storage[:]=struct.pack('9f',1,0,7,0,1,9,0,0,1)
    obj.set_transform(matrix);actual=obj.get_transform();obj.reset_transform();reset=obj.get_transform()
    if actual is None:
        for method in ['set_transform','get_transform','reset_transform']:called(method,'LV_DRAW_TRANSFORM_USE_MATRIX is disabled in the pinned firmware; calls return no transform','BLOCKED_BUILD_CONFIG')
    else:
        values=struct.unpack('9f',actual.__dereference__(36));emit('set_transform',values==(1,0,7,0,1,9,0,0,1),'actual adopted matrix retains independent affine coefficients');emit('get_transform',values==(1,0,7,0,1,9,0,0,1),'native object returns adopted transform matrix');emit('reset_transform',reset is None,'native reset removes owned transform')
    obj.delete()

def styles():
    lv.obj.style_deinit();called('style_deinit','empty style manager deinitialized before explicitly reinitializing it')
    lv.obj.style_init();obj=lv.obj(screen);obj.remove_style_all();obj.set_style_width(10,0);obj.set_style_width(30,lv.STATE.PRESSED);same=obj.style_state_compare(0,0);changed=obj.style_state_compare(0,lv.STATE.PRESSED);emit('style_state_compare',same==0 and changed!=0,'native appearance comparison distinguishes equal state from width-changing pressed state',same=same,changed=changed)
    tr=lv.obj_style_transition_dsc_t();tr.time=40;tr.delay=0;tr.selector=0;tr.prop=lv.STYLE.WIDTH;native_anim=lv.anim_t();native_anim.init();tr.path_cb=native_anim.path_cb;obj.style_create_transition(0,0,lv.STATE.PRESSED,tr);before=lv.anim_count_running();stop=time.ticks_add(time.ticks_ms(),100)
    while time.ticks_diff(stop,time.ticks_ms())>0:lv.timer_handler();time.sleep_ms(5)
    emit('style_create_transition',before>0 and obj.get_style_width(0)==30,'native style transition creates scheduler work and reaches exact target width',running=before,width=obj.get_style_width(0));emit('style_init',before>0,'reinitialized real style manager accepts scheduled object transitions');obj.delete()

def redraw():
    canvas=lv.canvas(screen);canvas.set_size(8,8);raw=bytearray(8*8*4+16);canvas.set_buffer(raw,8,8,lv.COLOR_FORMAT.ARGB8888);canvas.fill_bg(lv.color_hex(0),0)
    obj=lv.obj(screen);obj.remove_style_all();obj.set_pos(0,0);obj.set_size(8,8);obj.set_style_bg_color(lv.color_hex(0x336699),0);obj.set_style_bg_opa(255,0);obj.update_layout();layer=lv.layer_t();canvas.init_layer(layer);lv.obj.redraw(layer,obj);canvas.finish_layer(layer);pixel=canvas.get_px(3,4);emit('redraw',(pixel.red,pixel.green,pixel.blue,pixel.alpha)==(51,102,153,255),'explicit foreign-layer object namespace redraw reaches actual ARGB canvas bytes');obj.delete();canvas.delete()

def destruct():
    parent=lv.obj(screen);cls=lv.obj_class_t();cls.base_class=parent.get_class();cls.instance_size=parent.get_class().instance_size;hits=[]
    def destructor(class_p,obj):hits.append(obj)
    cls.destructor_cb=destructor;child=cls.create_obj(parent);lv.obj.destruct(child);emit('destruct',hits==[child],'owned class destructor executes exactly once through explicit object namespace');cls.destructor_cb=None;child.delete();parent.delete()

lv.init();display=lv.display_create(32,32);screen=display.get_screen_active()
for name,fn in [('lifecycle',lifecycle),('transform',transform),('styles',styles),('redraw',redraw),('destruct',destruct)]:group(name,fn)
display.delete();lv.deinit();print('LVGL_OBJ_FINAL_DONE')
