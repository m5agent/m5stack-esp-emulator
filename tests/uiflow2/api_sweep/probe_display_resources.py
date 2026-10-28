"""Real Display decoder file/buffer domains with explicit known image pixels.

Prepend DISPLAY_FIXTURES=probe_ui.fixture_files() on the host. The files are
written inside disposable guest Flash and decoded by the native SDK, then sent
through the emulated SPI/GDMA/panel path. No host pixels are injected.
"""
import os
import json
import time
import binascii
import M5

M5.begin()
M5.Display.fillScreen(0x0B1014)
M5.Display.setTextColor(0xFFFFFF)
M5.Display.drawString('Native decoder domains',8,8)
long_directory='/flash/gfx-'+'x'*56
try:
    os.mkdir(long_directory)
except OSError:
    pass
fixtures=globals()['DISPLAY_FIXTURES']
for name,record in fixtures.items():
    raw=binascii.a2b_base64(record['data'])
    for path in ('/flash/'+name,long_directory+'/'+name):
        with open(path,'wb') as handle:
            handle.write(raw)
methods=[('drawPng','fixture.png'),('drawBmp','fixture.bmp'),('drawJpg','fixture.jpg'),('drawImage','fixture.png')]
for row,(method,name) in enumerate(methods):
    y=40+row*25
    for x,domain,value in [(20,'short-absolute-file','/flash/'+name),(80,'64-to-127-character-file',long_directory+'/'+name),(140,'image-bytes',binascii.a2b_base64(fixtures[name]['data']))]:
        try:
            getattr(M5.Display,method)(value,x,y)
        except Exception as error:
            print('M5EMU_UI_RESULT '+json.dumps({'api_target':'M5.Display','method':method,'argument_domain':domain,'status':'FAIL','error':repr(error)}))
        points=[[x+2,y+2,0xFF0000],[x+12,y+2,0x00FF00],[x+2,y+12,0x0000FF],[x+12,y+12,0xFFFF00]]
        print('M5EMU_UI_FRAME_ORACLE '+json.dumps({'api_target':'M5.Display','method':method,'argument_domain':domain,'oracle':{'kind':'pixels','points':points},'tolerance':8}))
for _ in range(30):
    M5.update()
    time.sleep_ms(20)
print('DISPLAY_RESOURCE_DOMAINS_DONE')
