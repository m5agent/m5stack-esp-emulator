"""Keep failed native Canvas allocation from publishing an empty receiver."""
import json
import time
import M5


def emit(method, status, **details):
    print('M5EMU_UI_RESULT ' + json.dumps(dict(api_target='M5.Display.Canvas', method=method, status=status, **details)))


M5.begin()
M5.Lcd.setRotation(1)
M5.Lcd.fillScreen(0x0B1014)
for width, height in ((0, 24), (32, 0), (-1, 24), (32, -1)):
    domain = [width, height, 16, False]
    try:
        canvas = M5.Lcd.newCanvas(*domain)
        dimensions = [canvas.width(), canvas.height()]
        # An unallocated baseline wrapper is released without dereferencing its
        # null framebuffer; deliberately do not reproduce the later native crash.
        canvas.delete()
        emit('newCanvas', 'FAIL', argument_domain=domain, returned_dimensions=dimensions,
             oracle='invalid dimensions must raise ValueError before a Canvas wrapper is published')
    except ValueError:
        emit('newCanvas', 'STATE_PASS', argument_domain=domain, exception='ValueError',
             oracle='invalid dimensions rejected before publishing a Canvas')
    except Exception as error:
        emit('newCanvas', 'FAIL', argument_domain=domain, exception=repr(error))

try:
    canvas = M5.Lcd.newCanvas(320, 240, 16, False)
    dimensions = [canvas.width(), canvas.height()]
    canvas.delete()
    emit('newCanvas', 'FAIL' if dimensions != [320, 240] else 'ALLOCATION_SUCCEEDED',
         argument_domain=[320, 240, 16, False], returned_dimensions=dimensions,
         oracle='the selected DMA allocation failure must raise MemoryError; a successful allocator is outside this negative domain')
except MemoryError:
    emit('newCanvas', 'STATE_PASS', argument_domain=[320, 240, 16, False], exception='MemoryError',
         oracle='native DMA allocation failure is raised instead of returning an empty unsafe Canvas')
except Exception as error:
    emit('newCanvas', 'FAIL', argument_domain=[320, 240, 16, False], exception=repr(error))

canvas = M5.Lcd.newCanvas(32, 24, 16, False)
canvas.fillScreen(0x38B8C8)
canvas.push(10, 10)
emit('newCanvas', 'STATE_PASS' if [canvas.width(), canvas.height(), canvas.getColorDepth()] == [32, 24, 16] else 'FAIL',
     argument_domain=[32, 24, 16, False], dimensions=[canvas.width(), canvas.height()], color_depth=canvas.getColorDepth(),
     oracle='normal DMA Canvas still allocates, draws and pushes after rejected dimensions and OOM; independent final framebuffer checks pixels')
canvas.delete()
for _ in range(20):
    M5.update()
    time.sleep_ms(10)
print('CANVAS_ALLOCATION_DONE')
