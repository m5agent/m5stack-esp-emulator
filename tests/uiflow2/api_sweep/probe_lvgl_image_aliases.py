"""Image namespace and canonical draw buffers use exact pixels and real VFS.

A final internal decoder init/deinit epoch runs in a dedicated cold process.
Nothing calls lv.deinit after decoder_deinit, whose implementation leaves its
cache globals dangling. Native allocation frees never receive Python storage.
"""
import json,struct,uctypes,sys
import lvgl as lv

def emit(target,methods,ok,oracle,**details):
    if isinstance(methods,str):methods=[methods]
    for method in methods:print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl'+('.'+target if target else ''),'method':method,'status':'STATE_PASS' if ok else 'FAIL','oracle':oracle,'details':details}))
def called(target,method,oracle):
    print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl'+('.'+target if target else ''),'method':method,'status':'CALL_OK','oracle':oracle}))
def group(name,fn):
    try:fn()
    except Exception as error:print('M5EMU_UI_GROUP_ERROR '+json.dumps({'group':name,'error':repr(error)}));sys.print_exception(error)

def buffers():
    color=lv.color32_t({'red':255,'green':34,'blue':17,'alpha':255})
    for target in ['image','image_dsc_t']:
        data=bytearray(16);image=lv.image_dsc_t({'header':{'magic':0x19,'cf':lv.COLOR_FORMAT.I1,'w':8,'h':8,'stride':1},'data_size':16,'data':data})
        try:
            if target=='image':lv.image.buf_set_palette(image,1,color)
            else:image.buf_set_palette(1,color)
            emit(target,'buf_set_palette',bytes(data[4:8])==b'\x11\x22\xff\xff','exact BGRA palette entry written to caller-owned image buffer')
        except Exception as error:emit(target,'buf_set_palette',False,'explicit namespace accepts typed native image resource',error=repr(error))
        storage=lv.malloc(len(lv.image_dsc_t().__dereference__()));owned=lv.image_dsc_t.__cast__(storage);owned.data=lv.malloc(16)
        try:
            if target=='image':lv.image.buf_free(owned)
            else:owned.buf_free()
            called(target,'buf_free','native descriptor and native pixel allocation freed exactly once; no borrowed Python storage or allocator accounting')
        except Exception as error:
            emit(target,'buf_free',False,'explicit namespace accepts actual owned native descriptor',error=repr(error));lv.free(owned.data);lv.free(storage)
    draw=lv.draw_buf_create(8,8,lv.COLOR_FORMAT.I1,0);draw.set_palette(1,color);actual=bytes(draw.data.__dereference__(8))[4:8];emit('draw_buf_t','set_palette',actual==b'\x11\x22\xff\xff','canonical native draw-buffer palette writes exact BGRA bytes');draw.destroy()
    image=lv.image_dsc_t({'header':{'magic':0x19,'cf':lv.COLOR_FORMAT.RGB565,'w':2,'h':2,'stride':4},'data_size':8,'data':bytearray.fromhex('00f8e0071f00ffff')});header=lv.image_header_t();result=lv.image.decoder_get_info(image,header);emit('image','decoder_get_info',result==lv.RESULT.OK and (header.w,header.h,header.stride)==(2,2,4),'explicit image namespace decodes independent variable-image dimensions and stride')
    kinds=[lv.image.src_get_type(image),lv.image.src_get_type('S:/flash/fixture.bin'),lv.image.src_get_type(lv.SYMBOL.OK)];emit('image','src_get_type',kinds==[lv.image.SRC.VARIABLE,lv.image.SRC.FILE,lv.image.SRC.SYMBOL],'image classifier distinguishes actual typed descriptor, file and symbol domains',actual=kinds)
    area=lv.area_t();lv.image.buf_get_transformed_area(area,2,3,0,256,256,lv.point_t({'x':0,'y':0}));emit('image','buf_get_transformed_area',(area.x1,area.y1,area.x2,area.y2)==(0,0,1,2),'identity transform preserves exact two-by-three pixel bounds')

def handlers():
    defaults=lv.draw_buf_get_handlers();args=[defaults.buf_malloc_cb,defaults.buf_free_cb,defaults.align_pointer_cb,defaults.invalidate_cache_cb,defaults.flush_cache_cb,defaults.width_to_stride_cb]
    first=lv.draw_buf_handlers_t();first.init(*args);buffer=bytearray(range(64));view=memoryview(buffer)[1:];address=uctypes.addressof(view);offset=(-address)%lv.DRAW_BUF_ALIGN;actual=first.align_ex(view,lv.COLOR_FORMAT.RGB565)
    ok=bytes(actual.__dereference__(4))==bytes(view[offset:offset+4]);emit('draw_buf_handlers_t',['init','align_ex'],ok,'canonical handlers adopt actual default native callbacks and align independently known bytes')
    lv.draw_buf_init_handlers();actual=lv.draw_buf_align(view,lv.COLOR_FORMAT.RGB565);emit('',['draw_buf_init_handlers','draw_buf_align'],bytes(actual.__dereference__(4))==bytes(view[offset:offset+4]),'module handler aliases invoked explicitly with same native callback resource and independent byte oracle')

def saved_file():
    import fs_driver,os
    driver=lv.fs_drv_t();driver.init();fs_driver.fs_register(driver,'V',0);handles=[]
    def opened(d,path,mode):
        file=fs_driver.fs_open_cb(d,path,mode);handles.append(file);return file
    driver.open_cb=opened
    draw=lv.draw_buf_create(2,2,lv.COLOR_FORMAT.RGB565,4);pixels=bytes.fromhex('00f8e0071f00ffff');draw.data.__dereference__(8)[:]=pixels;result=draw.save_to_file('V:/flash/lvgl-owned-saved.bin')
    with open('/flash/lvgl-owned-saved.bin','rb') as file:data=file.read()
    header=struct.unpack('<BBHHHHH',data[:12]);emit('draw_buf_t','save_to_file',result==lv.RESULT.OK and len(data)==20 and header[0]==0x19 and header[1]==lv.COLOR_FORMAT.RGB565 and header[3:6]==(2,2,4) and data[12:]==pixels,'native file output independently read through guest VFS contains expected header geometry and exact RGB565 bytes');draw.destroy();os.remove('/flash/lvgl-owned-saved.bin')

def caches():
    for prefix,size in [('cache_',2048),('header_cache_',4)]:
        result=getattr(lv.image,prefix+'init')(size);emit('image',prefix+'init',result==lv.RESULT.OK,'native cache namespace initialization accepts existing initialized cache')
        getattr(lv.image,prefix+'resize')(0,True);disabled=not getattr(lv.image,prefix+'is_enabled')();getattr(lv.image,prefix+'resize')(size,True);enabled=getattr(lv.image,prefix+'is_enabled')();emit('image',[prefix+'resize',prefix+'is_enabled'],disabled and enabled,'actual cache capacity switches between disabled zero and enabled positive size')
        iterator=getattr(lv.image,prefix+'iter_create')();slot=bytearray(4);empty=iterator.next(slot)==lv.RESULT.INVALID;iterator.destroy();emit('image',prefix+'iter_create',empty,'actual empty native cache iterator reports exhaustion')
        getattr(lv.image,prefix+'drop')(None);iterator=getattr(lv.image,prefix+'iter_create')();empty=iterator.next(slot)==lv.RESULT.INVALID;iterator.destroy();emit('image',prefix+'drop',empty,'native drop-all leaves actual owned cache iterator empty')
        getattr(lv.image,prefix+'dump')();called('image',prefix+'dump','native empty-cache diagnostic called; log formatting has no independent content oracle')

def decoder_lifecycle():
    lv.image.decoder_init(2048,4);owned=lv.image.decoder_create();emit('image','decoder_init',lv.image.decoder_get_next(owned) is None,'explicit internal decoder initialization resets its native registry; old built-in decoder allocations are not counted')
    emit('image','decoder_create',owned is not None,'explicit image namespace creates an owned native decoder');lv.image.decoder_delete(owned);lv.image.decoder_deinit();called('image','decoder_deinit','final internal lifecycle teardown returns; no further LVGL or cache calls follow')

if not globals().get('LVGL_IMAGE_ALIAS_HELPER_ONLY',False):
    lv.init()
    for name,fn in [('buffers',buffers),('handlers',handlers),('saved_file',saved_file),('caches',caches),('decoder_lifecycle',decoder_lifecycle)]:group(name,fn)
    print('LVGL_IMAGE_ALIASES_DONE')
