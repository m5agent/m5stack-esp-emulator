"""Typed software masks and independently known opacity/half-plane inputs."""
import json
import lvgl as lv


def check(target,method,action,oracle,reason):
    print('LVGL_INTERNAL_CALL '+target+'.'+method)
    try:
        value=action();ok=oracle(value)
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl'+('.'+target if target else''),'method':method,
            'status':'STATE_PASS'if ok else'FAIL','value':value,'oracle':reason}))
        return value
    except Exception as error:
        print('M5EMU_UI_RESULT '+json.dumps({'api_target':'lvgl'+('.'+target if target else''),'method':method,
            'status':'FAIL','error':repr(error),'oracle':reason}))


def applied(param,x,y,count=1):
    output=bytearray([255]*count)
    status=lv.draw_sw_mask_apply([param,None],output,x,y,count)
    return status,list(output)


def run():
    lv.init();lv.draw_sw_mask_init()
    left=lv.draw_sw_mask_line_param_t()
    check('draw_sw_mask_line_param_t','points_init',lambda:(left.points_init(3,-10,3,10,lv.DRAW_SW_MASK_LINE_SIDE.LEFT),applied(left,-5,0),applied(left,10,0))[1:],
        lambda value:value[0][0]==lv.DRAW_SW_MASK_RES.FULL_COVER and value[1][0]==lv.DRAW_SW_MASK_RES.TRANSP,'vertical x=3 half-plane retains distant left pixel and excludes distant right pixel')
    check('draw_sw_mask_line_param_t','angle_init',lambda:(left.angle_init(3,0,90,lv.DRAW_SW_MASK_LINE_SIDE.LEFT),applied(left,-5,0),applied(left,10,0))[1:],
        lambda value:value[0][0]==lv.DRAW_SW_MASK_RES.FULL_COVER and value[1][0]==lv.DRAW_SW_MASK_RES.TRANSP,'90-degree line agrees with independent vertical half-plane')
    angle=lv.draw_sw_mask_angle_param_t()
    check('draw_sw_mask_angle_param_t','init',lambda:(angle.init(0,0,0,90),applied(angle,5,5),applied(angle,-5,-5))[1:],
        lambda value:value[0][0]==lv.DRAW_SW_MASK_RES.FULL_COVER and value[1][0]==lv.DRAW_SW_MASK_RES.TRANSP,'first quadrant wedge includes positive x/y and excludes opposite quadrant')
    area=lv.area_t({'x1':0,'y1':0,'x2':7,'y2':7})
    radius=lv.draw_sw_mask_radius_param_t()
    check('draw_sw_mask_radius_param_t','init',lambda:(radius.init(area,2,False),applied(radius,4,4),applied(radius,-5,-5))[1:],
        lambda value:value[0][0]in(lv.DRAW_SW_MASK_RES.FULL_COVER,lv.DRAW_SW_MASK_RES.CHANGED) and value[0][1]==[255] and value[1][0]==lv.DRAW_SW_MASK_RES.TRANSP,'rounded rectangle keeps central pixel opacity and excludes a pixel outside its bounds')
    fade=lv.draw_sw_mask_fade_param_t()
    check('draw_sw_mask_fade_param_t','init',lambda:(fade.init(area,255,0,0,7),applied(fade,0,0,4),applied(fade,0,7,4))[1:],
        lambda value:value[0][1]==[255]*4 and value[1][1]==[0]*4,'fade top and bottom produce independently specified full/zero alpha bytes')
    mask=lv.draw_sw_mask_map_param_t();coordinates=lv.area_t({'x1':0,'y1':0,'x2':3,'y2':0});pixels=bytearray([0,64,128,255])
    check('draw_sw_mask_map_param_t','init',lambda:(mask.init(coordinates,pixels),applied(mask,0,0,4))[1],
        lambda value:value[1]==[0,64,128,255],'caller-owned four alpha bytes are applied without replacement')
    check('','draw_sw_mask_apply',lambda:applied(mask,0,0,4),lambda value:value[0]==lv.DRAW_SW_MASK_RES.CHANGED and value[1]==[0,64,128,255],'terminated typed mask pointer array transforms actual destination bytes')
    check('','draw_sw_mask_free_param',lambda:(lv.draw_sw_mask_free_param(radius),applied(mask,0,0,4))[1],lambda value:value[1]==[0,64,128,255],'free radius mask resource while an independently owned map remains functional')
    check('','draw_sw_mask_cleanup',lambda:(lv.draw_sw_mask_cleanup(),applied(mask,0,0,4))[1],lambda value:value[1]==[0,64,128,255],'cache cleanup preserves live independent map output')
    check('','draw_sw_mask_deinit',lambda:lv.draw_sw_mask_deinit(),lambda value:value is None,'native mask mutex lifecycle deinitializes after actual radius/map use')
    check('','draw_sw_mask_init',lambda:(lv.draw_sw_mask_init(),applied(mask,0,0,4))[1],lambda value:value[1]==[0,64,128,255],'native mask lifecycle reinitializes and actual alpha mapping still works')
    lv.deinit()


try:run()
except Exception as error:print('LVGL_MASKS_ERROR '+repr(error))
print('LVGL_MASKS_DONE')
