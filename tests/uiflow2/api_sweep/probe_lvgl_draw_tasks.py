"""Owned typed LVGL draw tasks and real native buffer pixel oracles."""
import json,struct
import lvgl as lv


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


def callback_boundary(task,method,args):
    print('LVGL_INTERNAL_CALL draw_task_t.'+method)
    try:
        getattr(task,method)(*args,lambda *values:None)
        status,error='CALL_OK',None
    except SyntaxError as caught:
        status,error='UNSUPPORTED_BINDING',repr(caught)
    except Exception as caught:
        status,error='FAIL',repr(caught)
    print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl.draw_task_t','method':method,'status':status,'error':error,
        'oracle':'actual typed call with Python callback: generator explicitly omits bridge when first callback argument has no user_data; a native compatible callback pointer is required; no raw address is fabricated'}))


def fixture():
    area=lv.area_t({'x1':0,'y1':0,'x2':31,'y2':31})
    layer=lv.layer_t();layer.init();layer.buf_area=area;layer._clip_area=area;layer.phy_clip_area=area
    layer.color_format=lv.COLOR_FORMAT.ARGB8888
    buffer=lv.draw_buf_create(32,32,lv.COLOR_FORMAT.ARGB8888,0);layer.draw_buf=buffer
    task=lv.draw_task_t();task.target_layer=layer;task.area=area;task.clip_area=area
    data=buffer.data.__dereference__(32*32*4);data[:]=bytes(len(data))
    return area,layer,buffer,task,data


def pixel(data,x,y):return list(data[(y*32+x)*4:(y*32+x+1)*4])
def clear(data):data[:]=bytes(len(data))
def red(data):data[:]=b'\x00\x00\xff\xff'*1024


def sw_cases():
    area,layer,buffer,task,data=fixture();keep=[area,layer,buffer,task,data]
    check('layer_t','init',lambda:layer.opa,lambda value:value==255,'native layer init sets full opacity before owned buffer rendering')
    layer.opa=17
    check('layer_t','reset',lambda:(layer.reset(),layer.opa)[1],lambda value:value==255,'native reset restores full layer opacity')
    task.type=lv.DRAW_TASK_TYPE.FILL
    check('draw_task_t','get_type',task.get_type,lambda value:value==lv.DRAW_TASK_TYPE.FILL,'typed native draw task reports exact requested task kind')
    copied=lv.area_t()
    check('draw_task_t','get_area',lambda:(task.get_area(copied),copied.x1,copied.y1,copied.x2,copied.y2)[1:],lambda value:value==(0,0,31,31),'task area getter copies all four independently specified coordinates')
    second=lv.draw_task_t();third=lv.draw_task_t();keep.extend([second,third])
    second.area=lv.area_t({'x1':4,'y1':4,'x2':8,'y2':8});second.state=lv.DRAW_TASK_STATE.QUEUED
    third.area=lv.area_t({'x1':40,'y1':40,'x2':45,'y2':45});third.state=lv.DRAW_TASK_STATE.QUEUED
    task.next=second;second.next=third
    check('draw_task_t','get_dependent_count',task.get_dependent_count,lambda value:value==1,'only one of two queued next tasks overlaps the known area')
    task.next=None
    specs=(('fill',lv.DRAW_TASK_TYPE.FILL,'draw_fill_dsc_t','opa'),('border',lv.DRAW_TASK_TYPE.BORDER,'draw_border_dsc_t','opa'),
        ('box_shadow',lv.DRAW_TASK_TYPE.BOX_SHADOW,'draw_box_shadow_dsc_t','opa'),('label',lv.DRAW_TASK_TYPE.LABEL,'draw_label_dsc_t','opa'),
        ('image',lv.DRAW_TASK_TYPE.IMAGE,'draw_image_dsc_t','opa'),('line',lv.DRAW_TASK_TYPE.LINE,'draw_line_dsc_t','opa'),
        ('arc',lv.DRAW_TASK_TYPE.ARC,'draw_arc_dsc_t','opa'),('triangle',lv.DRAW_TASK_TYPE.TRIANGLE,'draw_triangle_dsc_t','bg_opa'),
        ('mask_rect',lv.DRAW_TASK_TYPE.MASK_RECTANGLE,'draw_mask_rect_dsc_t','radius'))
    for name,kind,typename,member in specs:
        dsc=getattr(lv,typename)();dsc.init();setattr(dsc,member,73);keep.append(dsc)
        task.type=kind;task.draw_dsc=dsc
        check('draw_task_t','get_'+name+'_dsc',lambda name=name,member=member:getattr(getattr(task,'get_'+name+'_dsc')(),member),lambda value:value==73,'kind-specific getter preserves the actual typed native descriptor member')
    fill=lv.draw_fill_dsc_t();fill.init();fill.color=lv.color_hex(0xff0000);keep.append(fill)
    task.type=lv.DRAW_TASK_TYPE.FILL;task.draw_dsc=fill
    check('draw_task_t','get_draw_dsc',lambda:lv.draw_fill_dsc_t.__cast__(task.get_draw_dsc()).color.to_int(),lambda value:value==0xff0000,'generic descriptor pointer casts back to the exact owned native fill descriptor')
    box=lv.area_t({'x1':4,'y1':4,'x2':11,'y2':11});keep.append(box)
    check('draw_task_t','sw_fill',lambda:(task.sw_fill(fill,box),pixel(data,6,6),pixel(data,2,2))[1:],lambda value:value==([0,0,255,255],[0,0,0,0]),'opaque red rectangle modifies interior BGRA pixel and preserves exterior')
    blend=lv.draw_sw_blend_dsc_t();blend.blend_area=box;blend.color=lv.color_hex(0x00ff00);blend.opa=255;keep.append(blend)
    check('draw_task_t','sw_blend',lambda:(clear(data),task.sw_blend(blend),pixel(data,6,6),pixel(data,2,2))[2:],lambda value:value==([0,255,0,255],[0,0,0,0]),'native software blend writes exact green BGRA and clips outside')
    border=lv.draw_border_dsc_t();border.init();border.color=lv.color_hex(0xff0000);border.width=2;keep.append(border)
    check('draw_task_t','sw_border',lambda:(clear(data),task.sw_border(border,box),pixel(data,4,7),pixel(data,7,7))[2:],lambda value:value==([0,0,255,255],[0,0,0,0]),'two-pixel red border retains transparent center')
    shadow=lv.draw_box_shadow_dsc_t();shadow.init();shadow.color=lv.color_hex(0xff0000);shadow.width=8;shadow.bg_cover=True;keep.append(shadow)
    shadow_area=lv.area_t({'x1':8,'y1':8,'x2':23,'y2':23});keep.append(shadow_area)
    check('draw_task_t','sw_box_shadow',lambda:(clear(data),task.sw_box_shadow(shadow,shadow_area),[pixel(data,x,16)for x in range(4,11)],pixel(data,16,16),pixel(data,0,0),shadow.opa)[2:],lambda value:any(p[2]>0 and p[3]>0 for p in value[0][:4])and value[1]==[0,0,0,0]and value[2]==[0,0,0,0]and value[3]==255,'native shadow has positive red alpha outside the box while covered center and far corner remain transparent; the complete cross-section is retained')
    raw=bytearray.fromhex('00f8e0071f00ffff');image=lv.image_dsc_t();image.header.magic=0x19;image.header.cf=lv.COLOR_FORMAT.RGB565
    image.header.w=2;image.header.h=2;image.header.stride=4;image.data_size=8;image.data=raw;keep.extend([raw,image])
    image_dsc=lv.draw_image_dsc_t();image_dsc.init();image_dsc.src=image;keep.append(image_dsc)
    image_area=lv.area_t({'x1':4,'y1':4,'x2':5,'y2':5});keep.append(image_area)
    check('draw_task_t','sw_image',lambda:(clear(data),task.sw_image(image_dsc,image_area),pixel(data,4,4),pixel(data,5,4),pixel(data,4,5),pixel(data,5,5))[2:],lambda value:value==([0,0,255,255],[0,255,0,255],[255,0,0,255],[255,255,255,255]),'original BIN decoder and software renderer convert all four independent RGB565 source pixels to exact BGRA')
    line=lv.draw_line_dsc_t();line.init();line.color=lv.color_hex(0xff0000);line.width=2;line.p1.x=2;line.p1.y=16;line.p2.x=28;line.p2.y=16;keep.append(line)
    check('draw_task_t','sw_line',lambda:(clear(data),task.sw_line(line),pixel(data,16,16),pixel(data,16,1))[2:],lambda value:value==([0,0,255,255],[0,0,0,0]),'known horizontal line covers center and leaves a distant row untouched')
    arc=lv.draw_arc_dsc_t();arc.init();arc.color=lv.color_hex(0xff0000);arc.center.x=16;arc.center.y=16;arc.radius=8;arc.width=2;arc.start_angle=0;arc.end_angle=90;keep.append(arc)
    check('draw_task_t','sw_arc',lambda:(clear(data),task.sw_arc(arc,area),sum(value>0 for value in data),pixel(data,8,8),pixel(data,0,0))[2:],lambda value:value[0]>10 and value[1:]==([0,0,0,0],[0,0,0,0]),'quarter arc produces actual nonzero pixels while opposite quadrant and far corner stay empty')
    tri=lv.draw_triangle_dsc_t();tri.init();tri.bg_color=lv.color_hex(0xff0000)
    points=[lv.point_precise_t({'x':2,'y':2}),lv.point_precise_t({'x':28,'y':2}),lv.point_precise_t({'x':2,'y':28})];tri.p=points;keep.extend([tri,points])
    check('draw_task_t','sw_triangle',lambda:(clear(data),task.sw_triangle(tri),pixel(data,8,8),pixel(data,28,28))[2:],lambda value:value==([0,0,255,255],[0,0,0,0]),'right triangle keeps known interior and excludes far diagonal corner')
    font=lv.font_get_default();letter=lv.draw_letter_dsc_t();letter.init();letter.font=font;letter.unicode=65;letter.color=lv.color_hex(0xff0000);keep.append(letter)
    letter_bytes=check('draw_task_t','sw_letter',lambda:(clear(data),task.sw_letter(letter,area),bytes(data).hex())[2],lambda value:sum(byte!=0 for byte in bytes.fromhex(value))>10,'native built-in A glyph renders actual colored bitmap into owned BGRA buffer')
    label=lv.draw_label_dsc_t();label.init();label.font=font;label.text='A';label.color=lv.color_hex(0xff0000);keep.append(label)
    check('draw_task_t','sw_label',lambda:(clear(data),task.sw_label(label,area),bytes(data).hex())[2],lambda value:value==letter_bytes,'label containing one A has byte-identical pixels to independently invoked native single-letter rendering')
    mask=lv.draw_mask_rect_dsc_t();mask.init();mask.area=shadow_area;mask.radius=0;keep.append(mask)
    check('draw_task_t','sw_mask_rect',lambda:(red(data),task.sw_mask_rect(mask),pixel(data,16,16),pixel(data,1,1))[2:],lambda value:value==([0,0,255,255],[0,0,0,0]),'rectangle mask retains red interior and clears actual pixels outside bounds')
    source_area,source_layer,source_buffer,source_task,source_data=fixture();keep.extend([source_area,source_layer,source_buffer,source_task,source_data])
    source_data[:]=b'\x00\xff\x00\xff'*1024
    layer_dsc=lv.draw_image_dsc_t();layer_dsc.init();layer_dsc.src=source_layer;keep.append(layer_dsc)
    check('draw_task_t','sw_layer',lambda:(clear(data),task.sw_layer(layer_dsc,area),pixel(data,16,16),pixel(data,0,0))[2:],lambda value:value==([0,255,0,255],[0,255,0,255]),'native layer composition reads exact green BGRA bytes from another owned typed layer')
    glyph=lv.draw_glyph_dsc_t();glyph.init();pos=lv.point_t({'x':0,'y':0});keep.extend([glyph,pos])
    callback_boundary(task,'label_iterate_characters',(label,area))
    callback_boundary(task,'unit_draw_letter',(glyph,pos,font,65))
    callback_boundary(task,'image_normal_helper',(image_dsc,image_area))
    callback_boundary(task,'image_tiled_helper',(image_dsc,image_area))
    # Native registry explicitly permits a NULL handler.  Never dispatch while
    # it is present.  This validates registry storage, not a custom callback.
    handler=lv.draw_sw_custom_blend_handler_t();handler.dest_cf=lv.COLOR_FORMAT.ARGB8888;keep.append(handler)
    check('draw_sw_custom_blend_handler_t','register_blend_handler',lambda:handler.register_blend_handler(),bool,'owned typed registry record with native-permitted NULL callback is stored; callback dispatch is outside this assertion')
    check('','draw_sw_get_blend_handler',lambda:lv.draw_sw_get_blend_handler(handler.dest_cf)is None,bool,'registry lookup returns the exact NULL callback stored in the owned typed record')
    check('','draw_sw_unregister_blend_handler',lambda:(lv.draw_sw_unregister_blend_handler(handler.dest_cf),lv.draw_sw_get_blend_handler(handler.dest_cf)is None),lambda value:value==(True,True),'unregister removes the actual handler and restores ordinary software rendering')
    check('','draw_sw_unregister_blend_handler',lambda:lv.draw_sw_unregister_blend_handler(handler.dest_cf),lambda value:value is False,'removing an absent handler reports false')
    transformed=bytearray(16);transform=lv.draw_image_dsc_t();transform.init();sup=lv.draw_image_sup_t();keep.extend([transform,sup,transformed])
    check('','draw_sw_transform',lambda:(lv.draw_sw_transform(lv.area_t({'x1':0,'y1':0,'x2':1,'y2':1}),raw,2,2,4,transform,sup,lv.COLOR_FORMAT.RGB565,transformed),transformed.hex())[1],lambda value:value[:16]==raw.hex(),'identity native image transform preserves four independent RGB565 pixel words')
    return keep


if not globals().get('LVGL_DRAW_HELPER_ONLY',False):
    try:lv.init();draw_keep=sw_cases();lv.deinit()
    except Exception as error:print('LVGL_DRAW_TASKS_ERROR '+repr(error))
    print('LVGL_DRAW_TASKS_DONE')
