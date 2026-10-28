"""Explicit construction boundaries for native return-only types and ESP-DL."""
import json
import image,code_scanner,dl


for api,constructor in (('image.Image',image.Image),('code_scanner.qrcode',code_scanner.qrcode)):
    try:
        value=constructor()
        print('SYSTEM_API '+json.dumps({'api':api,'status':'OBSERVED','reason':'zero-argument native type construction unexpectedly returned an object; no state oracle is assigned','type':type(value).__name__}))
    except TypeError as error:
        print('SYSTEM_API '+json.dumps({'api':api,'status':'UNSUPPORTED_CONSTRUCTOR','error':repr(error),'reason':'official native type has no make_new constructor; instances are produced by camera/scanner APIs and their independent method results remain separate'}))
    except Exception as error:
        print('SYSTEM_API '+json.dumps({'api':api,'status':'ERROR','error':repr(error)}))
try:
    recognizer=dl.HumanFaceRecognizer();recognizer.clear_id();count=recognizer.enrolled_id_num()
    print('SYSTEM_API '+json.dumps({'api':'dl.HumanFaceRecognizer','status':'STATE_PASS'if count==0 else'FAIL','value':count,'oracle':'actual native constructor followed by clear_id and independently read enrolled_id_num equals zero; inference/recognition are separate existing positive and negative tests'}))
except Exception as error:
    print('SYSTEM_API '+json.dumps({'api':'dl.HumanFaceRecognizer','status':'ERROR','error':repr(error)}))
print('NATIVE_CONSTRUCTORS_DONE')
