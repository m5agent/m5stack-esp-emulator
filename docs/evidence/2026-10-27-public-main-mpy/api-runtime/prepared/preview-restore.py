import sys,json,time
import M5
from unit import PIRUnit

_state=sys.modules['__m5_public_main_mpy_state__']
assert _state['nonce']=='bde3ea57a44c47719c547f310799f887', 'VM nonce lost'
assert __import__('__main__') is _state['owner'], 'REPL owner not restored'
M5.begin()
_screen=M5.Display
_screen.setBrightness(255)
_screen.fillScreen(0)
_screen.fillRect(_screen.width()//2-4,_screen.height()//2-4,8,8,0x0000FF)
_pir=PIRUnit((1,2))
print('PUBLIC_MAIN_MPY '+json.dumps({'kind':'source-recovery','nonce':_state['nonce'],'count':_state['count'],'owner_id':id(__import__('__main__')),'expected_owner_id':id(_state['owner']),'owner_restored':__import__('__main__') is _state['owner']}))
_sequence=0
_previous=None
while True:
 M5.update()
 _motion=bool(_pir.get_status())
 if _motion != _previous:
  _screen.fillRect(_screen.width()//2-4,_screen.height()//2+16,8,8,0xFFFFFF if _motion else 0)
  _previous=_motion
 _sequence+=1
 print('PUBLIC_MAIN_MPY '+json.dumps({'kind':'source-sample','nonce':_state['nonce'],'count':_state['count'],'sequence':_sequence,'motion':_motion}))
 time.sleep_ms(200)
