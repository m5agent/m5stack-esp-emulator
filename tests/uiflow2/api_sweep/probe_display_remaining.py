"""Finite owned Display/Canvas lifecycle, stream, font and register fixtures.

The host freezes explicit intermediate frames. A returned register call is
only CALL_OK until a matching controller/readback oracle exists.
"""
import json
import os
import time
import M5

M5.begin()
M5.Lcd.setRotation(1)
canvas = globals().get('DISPLAY_CONTRACT_CANVAS', False)
obj = M5.Lcd.newCanvas(M5.Lcd.width(), M5.Lcd.height(), 16, 'CoreS3' in os.uname().machine) if canvas else M5.Lcd
target = 'M5.Display.Canvas' if canvas else 'M5.Display'
assert obj.width() == M5.Lcd.width() and obj.height() == M5.Lcd.height(), 'native canvas allocation failed'


def emit(method, status, **details):
    print('M5EMU_UI_RESULT ' + json.dumps(dict(api_target=target, method=method, status=status, **details)))


def frame(method, oracle):
    if canvas:
        obj.push(0, 0)
    print('M5EMU_DISPLAY_FRAME ' + json.dumps(dict(api_target=target, method=method, oracle=oracle)))
    deadline = time.ticks_add(time.ticks_ms(), 4000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(10)


def call(method, args=(), status='CALL_OK', reason=None):
    try:
        value = getattr(obj, method)(*args)
        emit(method, status, value=value if isinstance(value, (int, bool, str)) or value is None else repr(value), oracle=reason)
        return value
    except Exception as error:
        emit(method, 'FAIL', error=repr(error), argument_domain=repr(args))


obj.fillScreen(0x38B8C8)
for method in ('powerSaveOn', 'powerSaveOff'):
    call(method, status='BLOCKED_MODEL', reason='actual IDMON/IDMOFF command invoked; the SPI panel model does not implement idle-mode color/power behavior, and Canvas has no physical power contract')
old = obj.getEpdMode()
obj.setEpdMode(1)
new = obj.getEpdMode()
for method in ('setEpdMode', 'getEpdMode'):
    emit(method, 'UNAVAILABLE_ON_DEVICE', value=new,
         oracle='selected LCD/Canvas ignores EPD mode; actual getter/setter called, no EPD waveform capability')
obj.setEpdMode(old)

obj.setFont(M5.Lcd.FONTS.DejaVu18)
base_height = obj.fontHeight()
base_width = obj.textWidth('MMMM')
loaded = call('loadFont', (os.getcwd() + '/contract-font.vlw',), reason='pinned official Montserrat VLW asset')
loaded_height = obj.fontHeight()
emit('loadFont', 'STATE_PASS' if loaded is True and loaded_height > 0 and (loaded_height, obj.textWidth('MMMM')) != (base_height, base_width) else 'FAIL',
     oracle='actual VLW load changes builtin font metrics', before_height=base_height, after_height=loaded_height)
obj.fillScreen(0)
obj.setTextColor(0xFFFFFF, 0)
obj.drawString('FONT', 10, 38)
frame('loadFont', {'kind': 'text', 'text': 'FONT', 'box': [0, 25, 200, 85]})
call('unloadFont')
emit('unloadFont', 'STATE_PASS' if obj.fontHeight() == 8 else 'FAIL',
     oracle='M5GFX unloadFont restores builtin Font0 (8px), even when that font lacks a Python export', value=obj.fontHeight(), expected=8)
if not canvas:
    obj.setFont(M5.Lcd.FONTS.DejaVu18)
    obj.fillScreen(0)
    obj.setCursor(10, 38)
    written = call('write', (b'STREAM',))
    emit('write', 'STATE_PASS' if written == 6 and obj.getCursor()[0] > 10 else 'FAIL',
         bytes_written=written, cursor=list(obj.getCursor()), oracle='ASCII byte count and actual native cursor advance')
    frame('write', {'kind': 'text', 'text': 'STREAM', 'box': [0, 25, 200, 85]})
    value = call('read', (4,))
    emit('read', 'STATE_PASS' if value == b'' else 'FAIL', oracle='bounded native Display stream EOF stub; this is not a keyboard or external RX data plane')


# These runtime exports accept native register arguments, but a successful
# return cannot establish an arbitrary panel register protocol.
for method, args in (('writeCommand', (0,)), ('writeCommand16', (0,)),
                     ('writeData', (0,)), ('writeData16', (0,)), ('writeData32', (0,))):
    call(method, args, reason='safe native NOP/data-domain invocation; arbitrary register effects require a modeled command/readback fixture')
for method in ('readData', 'readData16', 'readData32'):
    call(method, (0,), status='BLOCKED_MODEL', reason='native read invoked; selected SPI panel implements identification/display commands but no complete indexed register readback; Canvas has no hardware registers')

try:
    import camera
    camera.init(pixformat=camera.RGB565, framesize=camera.QVGA)
    img = camera.snapshot()
    img.draw_rectangle(60, 70, 40, 40, color=0x33CC00, fill=True)
    obj.show(img, 0, 0, 320, 240)
    emit('show', 'CALL_OK', oracle='real camera-owned image with independently drawn solid rectangle; host pixel oracle required')
    frame('show', {'kind': 'pixels', 'points': [[75, 85, 0x33CC00], [85, 95, 0x33CC00]]})
    camera.deinit()
except ImportError as error:
    emit('show', 'UNAVAILABLE_ON_DEVICE', error=repr(error), oracle='official image/camera module is CoreS3-only')
except Exception as error:
    emit('show', 'FAIL', error=repr(error))

for method in ('lvgl_deinit', 'lvgl_init', 'lvgl_deinit'):
    if hasattr(obj, method):
        try:
            import lvgl as lv
            getattr(obj, method)()
            expected = method == 'lvgl_init'
            emit(method, 'STATE_PASS' if bool(lv.is_initialized()) == expected else 'FAIL',
                 oracle='empty owned LVGL core initialization flag; no M5UI display/timer claim', value=bool(lv.is_initialized()))
        except Exception as error:
            emit(method, 'FAIL', error=repr(error))
if canvas:
    call('delete', reason='owned Canvas native storage released once; freed receiver is never dereferenced')
else:
    call('close', reason='native stream ioctl close is a no-op; global display lifetime is not invalidated')
print('DISPLAY_REMAINING_DONE')
