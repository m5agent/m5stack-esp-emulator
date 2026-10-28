"""Original native BMP/PNG/JPEG/BIN registry and MemFS bytes checks."""
import json,struct
import lvgl as lv
import fs_driver


def check(method,action,oracle,reason):
    print('LVGL_INTERNAL_CALL '+method)
    try:
        value=action();ok=oracle(value)
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl','method':method,'status':'STATE_PASS'if ok else'FAIL','value':value,'oracle':reason}))
        return value
    except Exception as error:
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl','method':method,'status':'FAIL','error':repr(error),'oracle':reason}))


def registry():
    inspector=lv.image.decoder_create();node=inspector.get_next();result=[]
    while node is not None:
        result.append(node.name);node=node.get_next()
    inspector.delete();return result


def decoder_library_cases():
    keep=[];handles=[]
    drv=lv.fs_drv_t();drv.init();fs_driver.fs_register(drv,'U',0);keep.append(drv)
    def opened(driver,path,mode):
        handle=fs_driver.fs_open_cb(driver,path,mode);handles.append(handle);return handle
    drv.open_cb=opened
    args=lv.image_decoder_args_t();args.no_cache=True;keep.append(args)
    for library,name,path in (('bmp','BMP','owned-2x2.bmp'),('lodepng','LODEPNG','owned-2x2.png'),('tjpgd','TJPGD','owned-red-8x8.jpg')):
        before=registry().count(name)
        getattr(lv,library+'_init')()
        dsc=lv.image_decoder_dsc_t();keep.append(dsc)
        result=dsc.open('U:/flash/'+path,args)
        if result==lv.RESULT.OK:
            dimensions=[dsc.header.w,dsc.header.h]
            if library=='lodepng':
                actual=bytes(dsc.decoded.data.__dereference__(dsc.decoded.data_size)).hex()
                ok=dimensions==[2,2]and actual=='0000ffff00ff00ffff0000ffffffffff'
            else:
                area=lv.area_t({'y1':lv.COORD.MIN})
                full=lv.area_t({'x1':0,'y1':0,'x2':dsc.header.w-1,'y2':dsc.header.h-1})
                rows=[]
                for index in range(2 if library=='bmp'else 1):
                    status=dsc.get_area(full,area)
                    rows.append([status,area.x1,area.y1,area.x2,area.y2,bytes(dsc.decoded.data.__dereference__(dsc.decoded.data_size)).hex()])
                actual=rows
                if library=='bmp':
                    ok=dimensions==[2,2]and rows[0][:5]==[lv.RESULT.OK,0,0,1,0]and rows[1][:5]==[lv.RESULT.OK,0,1,1,1]and rows[0][5][:12]=='0000ff00ff00'and rows[1][5][:12]=='ff0000ffffff'
                else:
                    raw=bytes.fromhex(rows[0][5]);channels=[list(raw[index:index+3])for index in range(0,len(raw),3)]
                    ok=dimensions==[8,8]and rows[0][:5]==[lv.RESULT.OK,0,0,7,7]and len(channels)==64 and all(p[0]<4 and p[1]<4 and p[2]>250 for p in channels)
            selected=dsc.decoder.name;dsc.close()
        else:dimensions=[];actual=[];ok=False;selected=None
        check(library+'_init',lambda:[registry().count(name)-before,result,dimensions,selected,actual],lambda value:ok and value[:4]==[1,lv.RESULT.OK,[8,8]if library=='tjpgd'else[2,2],name],
            'actual native registry insertion selects the original decoder and decodes owned Flash input; BMP/PNG exact independent pixels; JPEG all 64 red pixels with bounded lossy tolerance')
        check(library+'_deinit',lambda:(getattr(lv,library+'_deinit')(),registry().count(name))[1],lambda value:value==before,'actual native library deinit removes the decoder inserted for this test and restores the original registry count')
    # Native BIN init has no paired deinit; retain and delete its exact new node.
    sentinel=lv.image.decoder_create();before=sentinel.get_next();lv.bin_decoder_init()
    inspector=lv.image.decoder_create();added=inspector.get_next();inspector.delete()
    pixels=bytearray.fromhex('00f8e0071f00ffff');image=lv.image_dsc_t();image.header.magic=0x19
    image.header.cf=lv.COLOR_FORMAT.RGB565;image.header.w=2;image.header.h=2;image.header.stride=4;image.data_size=8;image.data=pixels
    dsc=lv.image_decoder_dsc_t();keep.extend([pixels,image,dsc])
    def bin_init_state():
        result=dsc.open(image,args)
        actual=bytes(dsc.decoded.data.__dereference__(8)).hex()if result==lv.RESULT.OK else None
        selected=dsc.decoder==added if result==lv.RESULT.OK else False
        if result==lv.RESULT.OK:dsc.close()
        return[added.get_next()==sentinel,result,selected,actual]
    check('bin_decoder_init',bin_init_state,lambda value:value==[True,lv.RESULT.OK,True,pixels.hex()],'actual inserted native BIN decoder is selected and exposes all four independent RGB565 pixel words')
    added.delete();sentinel.delete()
    # Extended path struct is backed by a retained bytearray so the public char*
    # API receives its real binary path and native buffer pointer, never an address.
    contents=bytearray(b'M5EMU-memfs-exact-0123456789');path_bytes=bytearray(lv.fs_path_ex_t.__SIZE__)
    path=lv.fs_path_ex_t.__cast__(path_bytes);path.make_path_from_buffer(ord('M'),contents,len(contents))
    file=lv.fs_file_t();out=bytearray(len(contents));read_count=bytearray(4);keep.extend([contents,path_bytes,path,file,out,read_count])
    def memfs_state():
        lv.fs_memfs_init();opened=file.open(path_bytes,lv.FS_MODE.RD)
        read=file.read(out,len(out),read_count)if opened==lv.FS_RES.OK else None
        closed=file.close()if opened==lv.FS_RES.OK else None
        return[opened,read,closed,struct.unpack('<I',read_count)[0],bytes(out).decode()]
    check('fs_memfs_init',memfs_state,lambda value:value==[lv.FS_RES.OK,lv.FS_RES.OK,lv.FS_RES.OK,len(contents),bytes(contents).decode()],
        'native memory filesystem registration opens a real extended typed path and reads the independent owned buffer byte for byte')
    return keep


try:lv.init();decoder_library_keep=decoder_library_cases();lv.deinit()
except Exception as error:print('LVGL_DECODER_LIBRARIES_ERROR '+repr(error))
print('LVGL_DECODER_LIBRARIES_DONE')
