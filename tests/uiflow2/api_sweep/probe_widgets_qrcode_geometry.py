"""Real QR relocation/resizing must erase the old exclusive screen region."""
import json,time
import M5
from M5 import Widgets
M5.begin()
Widgets.setRotation(1)
Widgets.fillScreen(0x0B1014)
# Disjoint move: decode the new position and require every old-area pixel clear.
moved=Widgets.QRCode('MOVE-QR',10,30,60,3)
moved.setCursor(90,30)
# Shrink: a separate QR leaves an old bottom strip that must become background.
shrunk=Widgets.QRCode('SIZE-QR',190,30,100,3)
shrunk.setSize(60)
# Version changes retain position/size and must still decode the requested text.
versioned=Widgets.QRCode('VERSION-QR',90,140,60,3)
versioned.setVersion(4)
for method,domain,oracle in [
 ('setCursor','disjoint-move-new-QR',{'kind':'qr_decode','text':'MOVE-QR','box':[80,20,160,100]}),
 ('setCursor','disjoint-move-old-exclusive',{'kind':'color_region','rgb':0x0B1014,'box':[10,30,70,90],'minimum':3600}),
 ('setSize','shrink-new-QR',{'kind':'qr_decode','text':'SIZE-QR','box':[180,20,260,100]}),
 ('setSize','shrink-old-exclusive',{'kind':'color_region','rgb':0x0B1014,'box':[190,90,290,130],'minimum':4000}),
 ('setVersion','version4-same-geometry',{'kind':'qr_decode','text':'VERSION-QR','box':[80,130,160,210]}),
]:
 print('M5EMU_UI_FRAME_ORACLE '+json.dumps({'api_target':'M5.Widgets.QRCode','method':method,'argument_domain':domain,'oracle':oracle,'tolerance':8}))
print('WIDGETS_QRCODE_GEOMETRY_DONE')
while True:
 M5.update();time.sleep_ms(20)
