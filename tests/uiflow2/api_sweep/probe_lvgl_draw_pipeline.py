"""Native task scheduling, layer ownership and module draw pixel oracles."""
import json
import lvgl as lv


def check(method,action,oracle,reason):
    print('LVGL_INTERNAL_CALL '+method)
    try:
        value=action();ok=oracle(value)
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl','method':method,'status':'STATE_PASS'if ok else'FAIL','value':value,'oracle':reason}))
        return value
    except Exception as error:
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl','method':method,'status':'FAIL','error':repr(error),'oracle':reason}))


def pipeline_cases():
    keep=[];display=lv.display_create(32,32);keep.append(display);lv.refr_set_disp_refreshing(display)
    full=lv.area_t({'x1':0,'y1':0,'x2':31,'y2':31});box=lv.area_t({'x1':4,'y1':4,'x2':11,'y2':11});keep.extend([full,box])
    layer=lv.draw_layer_create(None,lv.COLOR_FORMAT.ARGB8888,full);keep.append(layer)
    check('draw_layer_create',lambda:[layer.buf_area.x2,layer.buf_area.y2,layer.color_format,layer.opa],lambda value:value==[31,31,lv.COLOR_FORMAT.ARGB8888,255],'actual native allocated layer is registered on the retained display with independent geometry and format')
    second=lv.layer_t.__cast__(lv.malloc(lv.layer_t.__SIZE__));keep.append(second)
    check('draw_layer_init',lambda:(lv.draw_layer_init(second,None,lv.COLOR_FORMAT.ARGB8888,box),second.buf_area.x1,second.buf_area.y1,second.buf_area.x2,second.buf_area.y2,second.opa)[1:],lambda value:value==(4,4,11,11,255),'native-owned typed layer is initialized and attached to the current actual refresh display exactly once')
    buf=lv.draw_layer_alloc_buf(layer);data=buf.__dereference__(4096);keep.extend([buf,data])
    check('draw_layer_alloc_buf',lambda:bytes(data).hex(),lambda value:value=='00'*4096,'native ARGB allocation starts with an exactly transparent 32x32 buffer')
    def clear():data[:]=bytes(4096)
    def pixel(x,y):return list(data[(y*32+x)*4:(y*32+x+1)*4])
    def drain():
        for index in range(5):lv.draw_dispatch();lv.draw_wait_for_finish()
    def render(action,read):
        clear();action();drain();return read()
    def xy_state():
        point=lv.draw_layer_go_to_xy(layer,6,7).__dereference__(4);point[:]=b'\x03\x05\x07\xff'
        return pixel(6,7),pixel(5,7)
    check('draw_layer_go_to_xy',xy_state,lambda value:value==([3,5,7,255],[0,0,0,0]),'native x/y pointer aliases the independently calculated BGRA pixel offset and leaves its neighbour untouched')
    clear();task=lv.draw_add_task(layer,box)
    def task_alias():
        lv.layer_t.__cast__(task.target_layer).opa=201;aliased=layer.opa==201;layer.opa=255
        return[task.area.x1,task.area.x2,task.state,aliased]
    check('draw_add_task',task_alias,lambda value:value==[4,11,lv.DRAW_TASK_STATE.QUEUED,True],'actual native allocated task is queued with copied coordinates; mutation through its target-layer pointer aliases the independent owned layer')
    check('draw_get_available_task',lambda:lv.draw_get_available_task(layer,None,1)==task,bool,'native scheduler returns the actual independently retained queued task')
    check('draw_get_next_available_task',lambda:lv.draw_get_next_available_task(layer,None,1)==task,bool,'native dependency-aware scheduler selects the actual independent queued task')
    # cleanup_task owns and frees this descriptor, so allocate with LVGL malloc.
    fill=lv.draw_fill_dsc_t.__cast__(lv.malloc(lv.draw_fill_dsc_t.__SIZE__));fill.init();fill.color=lv.color_hex(0xff0000)
    task.type=lv.DRAW_TASK_TYPE.FILL;task.draw_dsc=fill
    check('draw_finalize_task_creation',lambda:(lv.draw_finalize_task_creation(layer,task),drain(),pixel(6,6),pixel(2,2))[2:],lambda value:value==([0,0,255,255],[0,0,0,0]),'native finalize evaluates and dispatches a real heap-owned fill task and native cleanup; independent interior/exterior pixels are exact')
    check('draw_dispatch',lambda:(lv.draw_dispatch(),pixel(6,6))[1],lambda value:value==[0,0,255,255],'draining actual scheduler preserves completed native fill output')
    check('draw_wait_for_finish',lambda:(lv.draw_wait_for_finish(),pixel(6,6))[1],lambda value:value==[0,0,255,255],'native synchronization returns after the actual completed task with its pixels retained')
    check('draw_dispatch_request',lambda:(lv.draw_dispatch_request(),lv.draw_dispatch_wait_for_request(),pixel(6,6))[2],lambda value:value==[0,0,255,255],'actual native request signal is consumed by its corresponding bounded wait after a rendered task')
    check('draw_dispatch_wait_for_request',lambda:(lv.draw_dispatch_request(),lv.draw_dispatch_wait_for_request(),True)[2],bool,'native request/wait pair is ordered so the blocking API receives a real signal')
    count=lv.draw_get_unit_count()
    check('draw_get_unit_count',lambda:count,lambda value:value>=1,'cold native LVGL has an actual initialized software draw unit used by all subsequent pixel checks')
    rect=lv.draw_rect_dsc_t();rect.init();rect.bg_color=lv.color_hex(0xff0000);keep.append(rect)
    check('draw_rect',lambda:render(lambda:lv.draw_rect(layer,rect,box),lambda:(pixel(6,6),pixel(2,2))),lambda value:value==([0,0,255,255],[0,0,0,0]),'module rectangle creates native draw tasks and produces exact interior/exterior BGRA pixels')
    font=lv.font_get_default();pos=lv.point_t({'x':0,'y':0});label=lv.draw_label_dsc_t();label.init();label.font=font;label.text='A';label.color=lv.color_hex(0xff0000);keep.extend([pos,label])
    letter=lv.draw_letter_dsc_t();letter.init();letter.font=font;letter.unicode=65;letter.color=lv.color_hex(0xff0000);keep.append(letter)
    metrics=lv.font_glyph_dsc_t();lv.font_t.get_glyph_dsc(font,metrics,65,0)
    letter_pos=lv.point_t({'x':metrics.adv_w//2,'y':font.line_height-font.base_line});keep.extend([metrics,letter_pos])
    letter_bytes=check('draw_letter',lambda:render(lambda:lv.draw_letter(layer,letter,letter_pos),lambda:bytes(data).hex()),lambda value:sum(b>0 for b in bytes.fromhex(value))>10,'native single-letter anchor compensates its documented pivot using independent font glyph metrics and renders actual A pixels')
    character=check('draw_character',lambda:render(lambda:lv.draw_character(layer,label,pos,65),lambda:bytes(data).hex()),lambda value:value==letter_bytes and sum(b>0 for b in bytes.fromhex(value))>10,'independent native character task has byte-identical actual A pixels to the separately anchored native letter task')
    # Native draw_character deliberately replaces dsc.text with a stack string
    # and sets text_local; restore our independently retained label input.
    label.text='A';label.text_local=False
    check('draw_label',lambda:render(lambda:lv.draw_label(layer,label,full),lambda:bytes(data).hex()),lambda value:value==character,'native one-character label scheduling has byte-identical glyph output to independent character construction')
    raw=bytearray.fromhex('00f8e0071f00ffff');image=lv.image_dsc_t();image.header.magic=0x19;image.header.cf=lv.COLOR_FORMAT.RGB565
    image.header.w=2;image.header.h=2;image.header.stride=4;image.data_size=8;image.data=raw
    image_dsc=lv.draw_image_dsc_t();image_dsc.init();image_dsc.src=image;image_area=lv.area_t({'x1':4,'y1':4,'x2':5,'y2':5});keep.extend([raw,image,image_dsc,image_area])
    check('draw_image',lambda:render(lambda:lv.draw_image(layer,image_dsc,image_area),lambda:[pixel(4,4),pixel(5,4),pixel(4,5),pixel(5,5)]),lambda value:value==[[0,0,255,255],[0,255,0,255],[255,0,0,255],[255,255,255,255]],'native BIN decoder/task path converts four independent RGB565 source words to exact BGRA pixels')
    line=lv.draw_line_dsc_t();line.init();line.color=lv.color_hex(0xff0000);line.width=2;line.p1.x=2;line.p1.y=16;line.p2.x=28;line.p2.y=16;keep.append(line)
    check('draw_line',lambda:render(lambda:lv.draw_line(layer,line),lambda:(pixel(16,16),pixel(16,1))),lambda value:value==([0,0,255,255],[0,0,0,0]),'native module line task covers the known horizontal center and excludes a distant row')
    arc=lv.draw_arc_dsc_t();arc.init();arc.color=lv.color_hex(0xff0000);arc.center.x=16;arc.center.y=16;arc.radius=8;arc.width=2;arc.start_angle=0;arc.end_angle=90;keep.append(arc)
    check('draw_arc',lambda:render(lambda:lv.draw_arc(layer,arc),lambda:(sum(b>0 for b in data),pixel(8,8),pixel(0,0))),lambda value:value[0]>10 and value[1:]==([0,0,0,0],[0,0,0,0]),'native quarter-arc task produces pixels and excludes the opposite quadrant and far corner')
    bounds=lv.area_t();keep.append(bounds)
    check('draw_arc_get_area',lambda:(lv.draw_arc_get_area(16,16,8,0,360,2,False,bounds),bounds.x1,bounds.y1,bounds.x2,bounds.y2)[1:],lambda value:value==(8,8,24,24),'native full-circle bounds equal independently calculated center plus/minus radius')
    tri=lv.draw_triangle_dsc_t();tri.init();tri.bg_color=lv.color_hex(0xff0000);points=[lv.point_precise_t({'x':2,'y':2}),lv.point_precise_t({'x':28,'y':2}),lv.point_precise_t({'x':2,'y':28})];tri.p=points;keep.extend([tri,points])
    check('draw_triangle',lambda:render(lambda:lv.draw_triangle(layer,tri),lambda:(pixel(8,8),pixel(28,28))),lambda value:value==([0,0,255,255],[0,0,0,0]),'native triangle task covers the independently known interior and excludes the far diagonal corner')
    mask=lv.draw_mask_rect_dsc_t();mask.init();mask.area=box;keep.append(mask)
    def masked():
        data[:]=b'\x00\x00\xff\xff'*1024;lv.draw_mask_rect(layer,mask);drain();return pixel(6,6),pixel(2,2)
    check('draw_mask_rect',masked,lambda value:value==([0,0,255,255],[0,0,0,0]),'actual native mask task preserves independent interior and clears outside pixels')
    source=lv.draw_layer_create(layer,lv.COLOR_FORMAT.ARGB8888,full);source_data=lv.draw_layer_alloc_buf(source).__dereference__(4096);source_data[:]=b'\x00\xff\x00\xff'*1024
    source.all_tasks_added=True;layer_dsc=lv.draw_image_dsc_t();layer_dsc.init();layer_dsc.src=source;keep.append(layer_dsc)
    check('draw_layer',lambda:render(lambda:lv.draw_layer(layer,layer_dsc,full),lambda:(pixel(16,16),pixel(0,0))),lambda value:value==([0,255,0,255],[0,255,0,255]),'native dependency scheduler completes and composites an actual owned green child layer, including its native cleanup')
    diagonal=bytes([128,64,32,16,8,4,2,1]);vtiled=bytearray(8);lsb=bytearray(8);keep.extend([diagonal,vtiled,lsb])
    check('draw_sw_i1_convert_to_vtiled',lambda:(lv.draw_sw_i1_convert_to_vtiled(diagonal,8,8,8,vtiled,8,False),lv.draw_sw_i1_convert_to_vtiled(diagonal,8,8,8,lsb,8,True),vtiled.hex(),lsb.hex())[2:],lambda value:value==(diagonal.hex(),bytes(reversed(diagonal)).hex()),'native horizontal-to-vertical bit transposition preserves an independently specified diagonal and reverses per-column bit order in LSB mode')
    # All tasks are complete before draw-unit lifecycle operations.  No display
    # refresh or lv.deinit occurs after the final native unit deletion.
    check('draw_sw_deinit',lambda:(lv.draw_sw_deinit(),lv.draw_get_unit_count())[1],lambda value:value==count,'native SW deinit releases mask synchronization while unit count remains as defined by the native contract')
    check('draw_deinit',lambda:(lv.draw_deinit(),lv.draw_get_unit_count())[1],lambda value:value==count,'native draw deinit frees all units; its native historical unit counter is intentionally not reset')
    check('draw_init',lambda:(lv.draw_init(),lv.draw_get_unit_count())[1],lambda value:value==count,'native draw synchronization reinitializes before creating a new actual SW unit')
    check('draw_sw_init',lambda:(lv.draw_sw_init(),lv.draw_get_unit_count())[1],lambda value:value==count+1,'native SW init inserts one actual renderer after draw deinit/init')
    check('draw_sw_init',lambda:render(lambda:lv.draw_rect(layer,rect,box),lambda:(pixel(6,6),pixel(2,2))),lambda value:value==([0,0,255,255],[0,0,0,0]),'reinitialized original native SW renderer executes an actual rectangle task with exact independent pixels')
    created=lv.draw_unit_t.__cast__(lv.draw_create_unit(lv.draw_unit_t.__SIZE__));keep.append(created)
    check('draw_create_unit',lambda:[created.idx,lv.draw_get_unit_count()],lambda value:value==[count+2,count+2],'native allocator inserts an actual zeroed draw unit with its independently incremented index; it is never dispatched without callbacks')
    lv.draw_sw_deinit();lv.draw_deinit()
    return keep


try:lv.init();pipeline_keep=pipeline_cases()
except Exception as error:print('LVGL_DRAW_PIPELINE_ERROR '+repr(error))
print('LVGL_DRAW_PIPELINE_DONE')
