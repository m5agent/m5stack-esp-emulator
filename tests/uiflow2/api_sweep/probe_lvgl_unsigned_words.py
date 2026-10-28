"""Unsigned native-word argument boundaries, without signed-value workarounds."""
import json
import lvgl as lv


def check(method,action,oracle,description):
    try:
        value=action();passed=oracle(value)
        print("M5EMU_UI_RESULT "+json.dumps({"api_target":"lvgl","method":method,
            "status":"STATE_PASS"if passed else"FAIL","value":value,"oracle":description}))
    except Exception as error:
        print("M5EMU_UI_RESULT "+json.dumps({"api_target":"lvgl","method":method,
            "status":"FAIL","error":repr(error),"oracle":description}))


encoded=lv.anim_speed(100)
check("anim_speed",lambda:encoded,lambda value:value&0x80000000!=0,"public speed encoder returns its real unsigned high-bit C value")
check("anim_resolve_speed",lambda:lv.anim_resolve_speed(encoded,0,100),lambda value:value==1000,"100 units at 100 units/second resolves to exactly 1000ms using the original positive encoded uint32")
check("anim_resolve_speed",lambda:lv.anim_resolve_speed(1000,0,100),lambda value:value==1000,"ordinary duration value remains exactly 1000ms")
check("color_hex",lambda:[lv.color_hex(0xffffffff).red,lv.color_hex(0xffffffff).green,lv.color_hex(0xffffffff).blue],lambda value:value==[255,255,255],"full positive 0xffffffff C input preserves RGB white without signed substitution")
check("color_hex",lambda:[lv.color_hex(0x80010203).red,lv.color_hex(0x80010203).green,lv.color_hex(0x80010203).blue],lambda value:value==[1,2,3],"high-bit ARGB input preserves each independent RGB byte")
check("color_hex",lambda:[lv.color_hex(-1).red,lv.color_hex(-1).green,lv.color_hex(-1).blue],lambda value:value==[255,255,255],"ordinary C unsigned conversion of negative one retains previous behavior")
print("LVGL_UNSIGNED_WORDS_DONE")
