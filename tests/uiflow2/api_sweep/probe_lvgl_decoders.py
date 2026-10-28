"""Typed native image/bin decoder sessions with real Flash files and bytes.

decoder_cases(lv, namespace=lv.image) exercises namespace aliases independently;
the default calls the canonical resource methods. No decoder is replaced:
Python callbacks delegate to the original native BIN decoder and count dispatch.
"""
import json,struct,os


def check(target,method,action,oracle,reason):
    print('LVGL_INTERNAL_CALL '+target+'.'+method)
    try:
        value=action();ok=oracle(value)
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl'+('.'+target if target else''),'method':method,
            'status':'STATE_PASS'if ok else'FAIL','value':value if isinstance(value,(bool,int,str,list,tuple))or value is None else repr(value),'oracle':reason}))
        return value
    except Exception as error:
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl'+('.'+target if target else''),'method':method,
            'status':'FAIL','error':repr(error),'oracle':reason}))


def decoder_cases(lv,namespace=None,continue_namespace_errors=False):
    import fs_driver
    keep=[];handles=[];failed_aliases={}
    def call(method,resource,*args):
        if namespace is None:return getattr(resource,method)(*args)
        try:return getattr(namespace,'decoder_'+method)(resource,*args)
        except TypeError as error:
            if not continue_namespace_errors:raise
            failed_aliases[method]=repr(error)
            # Prepare later resources using the canonical method, while keeping
            # this alias's failed invocation as FAIL in observed() below.
            return getattr(resource,method)(*args)
    def observed(owner,method,action,oracle,reason):
        if namespace is not None and method in failed_aliases:
            value=action()
            print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.image','method':'decoder_'+method,
                'status':'FAIL','error':failed_aliases[method],'oracle':reason,
                'fixture_continuation':'canonical method used only to prepare later tests; alias remains FAIL'}))
            return value
        return check('image'if namespace is not None else owner,'decoder_'+method if namespace is not None else method,action,oracle,reason)
    drv=lv.fs_drv_t();drv.init();fs_driver.fs_register(drv,'U',0);keep.append(drv)
    def opened(driver,path,mode):
        handle=fs_driver.fs_open_cb(driver,path,mode);handles.append(handle);return handle
    drv.open_cb=opened
    pixels=bytearray.fromhex('00f8e0071f00ffff')
    image=lv.image_dsc_t();image.header.magic=0x19;image.header.cf=lv.COLOR_FORMAT.RGB565
    image.header.w=2;image.header.h=2;image.header.stride=4;image.data_size=8;image.data=pixels
    keep.extend([pixels,image])
    with open('/flash/lvgl-owned-decoder.bin','wb')as stream:
        stream.write(struct.pack('<BBHHHHH',0x19,lv.COLOR_FORMAT.RGB565,0,2,2,4,0));stream.write(pixels)
    decoder=lv.image.decoder_create();decoder.name='OWNED-BIN';keep.append(decoder)
    events=[]
    def info_callback(dec,dsc,header):
        events.append('info');return lv.bin_decoder_info(dec,dsc,header)
    def open_callback(dec,dsc):
        events.append('open');return lv.bin_decoder_open(dec,dsc)
    def area_callback(dec,dsc,full,area):
        events.append('area');return lv.bin_decoder_get_area(dec,dsc,full,area)
    def close_callback(dec,dsc):
        events.append('close');lv.bin_decoder_close(dec,dsc)
    for method,callback in (('set_info_cb',info_callback),('set_open_cb',open_callback),('set_get_area_cb',area_callback),('set_close_cb',close_callback)):
        call(method,decoder,callback)
    observed('image_decoder_t','get_next',lambda:call('get_next',decoder)is not None,bool,'created native decoder links to the existing built-in decoder registry')
    args=lv.image_decoder_args_t();args.no_cache=True
    dsc=lv.image_decoder_dsc_t();keep.extend([args,dsc])
    opened=observed('image_decoder_dsc_t','open',lambda:call('open',dsc,image,args),lambda value:value==lv.RESULT.OK,'typed variable image opens through original BIN decoder callback dispatch')
    if opened==lv.RESULT.OK:
        check('','bin_decoder_open',lambda:bytes(dsc.decoded.data.__dereference__(8)).hex(),lambda value:value==pixels.hex(),'original native BIN open exposes all independently specified RGB565 bytes')
        observed('image_decoder_t','set_info_cb',lambda:events.count('info'),lambda value:value>0,'actual native decode invokes registered info callback')
        observed('image_decoder_t','set_open_cb',lambda:events.count('open'),lambda value:value==1,'actual native decode invokes registered open callback exactly once')
        observed('image_decoder_dsc_t','close',lambda:(call('close',dsc),events.count('close'))[1],lambda value:value==1,'native decoder close invokes original registered resource cleanup callback')
        observed('image_decoder_t','set_close_cb',lambda:events.count('close'),lambda value:value==1,'registered close callback runs through actual session close')
    header=lv.image_header_t();raw=lv.image_decoder_dsc_t();raw.src=image;raw.src_type=lv.image.SRC.VARIABLE
    check('','bin_decoder_info',lambda:(lv.bin_decoder_info(decoder,raw,header),header.w,header.h,header.stride),lambda value:value==(lv.RESULT.OK,2,2,4),'direct original native header decoder matches independent dimensions and stride')
    file_dsc=lv.image_decoder_dsc_t();keep.append(file_dsc)
    result=observed('image_decoder_dsc_t','open',lambda:call('open',file_dsc,'U:/flash/lvgl-owned-decoder.bin',args),lambda value:value==lv.RESULT.OK,'actual Flash .bin file opens through native LVGL filesystem and decoder callbacks')
    if result==lv.RESULT.OK:
        full=lv.area_t({'x1':0,'y1':0,'x2':1,'y2':1});area=lv.area_t({'y1':lv.COORD.MIN})
        rows=[]
        for index in range(2):
            status=call('get_area',file_dsc,full,area)
            row=bytes(file_dsc.decoded.data.__dereference__(4))if status==lv.RESULT.OK else b''
            rows.append([status,area.y1,row.hex()])
        observed('image_decoder_dsc_t','get_area',lambda:rows,lambda value:value==[[lv.RESULT.OK,0,pixels[:4].hex()],[lv.RESULT.OK,1,pixels[4:].hex()]],'native file decoder advances exactly one scan line and returns both independent RGB565 rows')
        observed('image_decoder_t','set_get_area_cb',lambda:events.count('area'),lambda value:value==2,'actual file scanline decode invokes registered area callback twice')
        check('','bin_decoder_get_area',lambda:rows,lambda value:value==[[lv.RESULT.OK,0,pixels[:4].hex()],[lv.RESULT.OK,1,pixels[4:].hex()]],'registered callback delegates actual native BIN scanline implementation with exact bytes')
        before=events.count('close');call('close',file_dsc)
        check('','bin_decoder_close',lambda:events.count('close')-before,lambda value:value==1,'native BIN file/partial-buffer close invoked through original session cleanup')
    rgba=lv.draw_buf_create(2,1,lv.COLOR_FORMAT.ARGB8888,0);keep.append(rgba)
    rgba.data.__dereference__(8)[:]=b'\xff\x00\x00\x80'*2
    post=lv.image_decoder_dsc_t();post.args.premultiply=True
    processed=call('post_process',post,rgba);keep.append(processed)
    observed('image_decoder_dsc_t','post_process',lambda:bytes(processed.data.__dereference__(8)).hex(),lambda value:value==(b'\x7f\x00\x00\x80'*2).hex(),'native post processing premultiplies exact independently specified BGRA channels')
    # Decoder cache takes ownership of this independent native draw buffer.
    try:
        lv.image.cache_resize(4096,False)
        cached_buf=lv.draw_buf_create(2,2,lv.COLOR_FORMAT.RGB565,0);cached_buf.data.__dereference__(8)[:]=pixels
        key=lv.image_cache_data_t();key.src=image;key.src_type=lv.image.SRC.VARIABLE;key.slot.size=8
        entry=call('add_to_cache',decoder,key,cached_buf,None)
        keep.extend([cached_buf,key,entry])
        observed('image_decoder_t','add_to_cache',lambda:bytes(lv.image_cache_data_t.__cast__(entry.get_data()).decoded.data.__dereference__(8)).hex(),lambda value:value==pixels.hex(),'enabled native image cache entry retains exact independently owned decoded bytes')
        lv.image.cache_drop(image)
    except Exception as error:
        observed('image_decoder_t','add_to_cache',lambda:repr(error),lambda value:False,'actual cache enable/insert/read path failed; no configured-state PASS')
    # Deleting the owned decoder must restore the registry head.
    following=call('get_next',decoder)
    def delete_restore():
        call('delete',decoder)
        new=lv.image.decoder_create()
        restored=call('get_next',new)==following
        call('delete',new)
        return restored
    observed('image_decoder_t','delete',delete_restore,bool,'deleting actual owned decoder restores the independently retained registry successor')
    os.remove('/flash/lvgl-owned-decoder.bin')
    return keep


if not globals().get('LVGL_DECODER_HELPER_ONLY',False):
    import lvgl as lv
    try:
        lv.init();decoder_keep=decoder_cases(lv);lv.deinit()
    except Exception as error:print('LVGL_DECODERS_ERROR '+repr(error))
    print('LVGL_DECODERS_DONE')
