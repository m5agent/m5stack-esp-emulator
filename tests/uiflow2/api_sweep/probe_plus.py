"""Real HTTP-to-Widgets LabelPlus/ImagePlus fixture; URL supplied by host."""
import M5,time,json,sys,os,hashlib,requests
if globals().get('PLUS_CANDIDATE'):
    from candidate_label_plus import LabelPlus
else:
    from label_plus import LabelPlus
from image_plus import ImagePlus

def emit(target,method,ok,domain,**details):
    print('M5EMU_UI_RESULT '+json.dumps({'api_target':target,'method':method,'status':'STATE_PASS' if ok else 'FAIL','argument_domain':domain,'details':details}))
def attempt(target,method,fn,verify,domain):
    try:
        actual=fn();emit(target,method,bool(verify(actual)),domain,actual=actual)
    except Exception as error:emit(target,method,False,domain,error=repr(error))
M5.begin();connect_wifi();M5.Lcd.fillScreen(0x0B1014)
for directory in ['/flash/res','/flash/res/img']:
    try:os.mkdir(directory)
    except OSError:pass
label=LabelPlus('Initial',10,10,1.0,0xFFFFFF,0x0B1014,M5.Lcd.FONTS.DejaVu18,TEST_BASE_URL+'/label',0,False,'value','ERROR')
emit('label_plus.LabelPlus','__init__',label.get_data()=='PLUS42','disabled-zero-period-real-http',value=label.get_data())
attempt('label_plus.LabelPlus','get_data',label.get_data,lambda x:x=='PLUS42','JSON-key-from-wire')
attempt('label_plus.LabelPlus','is_valid_data',label.is_valid_data,lambda x:x is True,'actual-HTTP-success')
attempt('label_plus.LabelPlus','update',lambda:(label.update(),label.get_data())[1],lambda x:x=='PLUS42','disabled-zero-period-explicit-update')
attempt('label_plus.LabelPlus','show_value_of_key',lambda:(label.show_value_of_key('chosen'),label.get_data())[1],lambda x:x=='NEXT7','disabled-zero-period-explicit-key-update')
attempt('label_plus.LabelPlus','set_update_period',lambda:(label.set_update_period(100),label._period)[1],lambda x:x==100,'disabled-period-setting')
def peer_json(path):
    r=requests.get(TEST_BASE_URL+path)
    try:return r.json()
    finally:r.close()
def label_enable():
    before=peer_json('/stats')['label_count'];label.set_update_enable(True)
    for _ in range(35):M5.update();time.sleep_ms(10)
    after=peer_json('/stats')['label_count'];return label._enable,label._tim is not None,after-before
attempt('label_plus.LabelPlus','set_update_enable',label_enable,lambda x:x[0] and x[1] and x[2]>=1,'actual-timer-causes-additional-peer-request')
attempt('label_plus.LabelPlus','set_url',lambda:(label.set_url(TEST_BASE_URL+'/alternate'),label.update(),label.get_data())[2],lambda x:x=='ALT9','new-URL-reaches-second-peer-route')
attempt('label_plus.LabelPlus','setColor',lambda:(label.setColor(0x2255AA,0x0B1014),label._text_color)[1],lambda x:x==0x2255AA,'typed-label-color')
attempt('label_plus.LabelPlus','deinit',lambda:(label.deinit(),label._enable)[1],lambda x:x is False,'positive-period-timer-stopped')
# The zero-period enabled branch must also be safe to deinitialize.
zero=LabelPlus('Zero',10,35,1.0,0xFFFFFF,0x0B1014,M5.Lcd.FONTS.DejaVu18,TEST_BASE_URL+'/label',0,True,'value','ERROR')
attempt('label_plus.LabelPlus','deinit',lambda:(zero.deinit(),zero._enable)[1],lambda x:x is False,'enabled-zero-period-no-timer')
image=ImagePlus(TEST_BASE_URL+'/fixture.png',30,70,False,60000,default_img='/flash/res/img/fixture.png')
attempt('image_plus.ImagePlus','is_valid_image',image.is_valid_image,lambda x:x is True,'actual-http-png-download')
with open('/flash/res/img/fixture.png','rb') as handle:actual=hashlib.sha256(handle.read()).digest()
emit('image_plus.ImagePlus','__init__',actual==EXPECTED_PNG_DIGEST,'downloaded-file-byte-identity')
attempt('image_plus.ImagePlus','set_update_period',lambda:(image.set_update_period(60000),image._period)[1],lambda x:x==60000,'image-period-setting')
def image_worker():
    before=peer_json('/stats')['png_count'];image.set_update_period(100);image.set_update_enable(True);time.sleep_ms(350);image.set_update_enable(False);time.sleep_ms(150);peer_json('/disabled-marker');time.sleep_ms(250);stats=peer_json('/stats');return image._enable,stats['png_count']-before,stats['png_after_stop']
attempt('image_plus.ImagePlus','set_update_enable',image_worker,lambda x:x[0] is False and x[1]>=1 and x[2]==0,'real-worker-fetches-additional-image-then-stops-peer-requests')
attempt('image_plus.ImagePlus','deinit',lambda:(image.deinit(),image._enable)[1],lambda x:x is False,'real-image-worker-disabled')
label.setText('PLUS HTTP PASS');label.setColor(0xFFFFFF,0x0B1014)
for _ in range(15):M5.update();time.sleep_ms(20)
print('M5EMU_UI_FRAME_ORACLE '+json.dumps({'api_target':'image_plus.ImagePlus','method':'__init__','oracle':{'kind':'pixels','points':[[32,72,0xFF0000],[40,72,0x00FF00]]}}))
print('M5EMU_PLUS_DONE')
while True:M5.update();time.sleep_ms(20)
