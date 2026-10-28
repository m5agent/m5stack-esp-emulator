"""QR text changes must alter decoded framebuffer payload on either board."""
import json,time
import M5
from M5 import Widgets
M5.begin();Widgets.setRotation(1);Widgets.fillScreen(0x0B1014)
control=Widgets.QRCode('UIFLOW2-API',10,30,90,3)
changed=Widgets.QRCode('UIFLOW2-API',130,30,90,3)
changed.setText('UPDATED-API')
for method,text,box in [('QRCode','UIFLOW2-API',[0,20,110,130]),('setText','UPDATED-API',[120,20,230,130])]:
    print('M5EMU_UI_FRAME_ORACLE '+json.dumps({'api_target':'M5.Widgets.QRCode','method':method,'oracle':{'kind':'qr_decode','text':text,'box':box}}))
print('WIDGETS_QRCODE_TEXT_DONE')
while True:M5.update();time.sleep_ms(20)
