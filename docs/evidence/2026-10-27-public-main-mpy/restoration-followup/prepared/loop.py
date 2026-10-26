import sys,json,time
import M5
import dep
_state=sys.modules['__m5_public_main_mpy_state__']
_state['count']+=1
_main=sys.modules.get('main')
_identity={'nonce':_state['nonce'],'count':_state['count'],'owner_id':id(_state['owner']),'name':__name__,'file':__file__,'main_id':id(_main),'sys_main_id':id(sys.modules.get('__main__')),'import_main_id':id(__import__('__main__')),'dep_value':dep.VALUE,'dep_file':dep.__file__}
assert __name__=='__main__'
assert _main is sys.modules.get('__main__') and _main is __import__('__main__')
assert _main is not _state['owner']
_screen=M5.Display
_screen.fillRect(_screen.width()//2-4,_screen.height()//2-4,8,8,dep.COLOR)
if __name__=='__main__':
 _row=_identity.copy()
 _row.update(kind='mpy-entry',guard=True)
 print('PUBLIC_MAIN_MPY '+json.dumps(_row))
from unit import PIRUnit
_pir=PIRUnit((1,2))
_sequence=0
_previous=None
while True:
 M5.update()
 _motion=bool(_pir.get_status())
 if _motion != _previous:
  _screen.fillRect(_screen.width()//2-4,_screen.height()//2-4,8,8,0xFFFFFF if _motion else dep.COLOR)
  _screen.fillRect(_screen.width()//2-4,_screen.height()//2+16,8,8,0xFFFFFF if _motion else 0)
  _previous=_motion
 _sequence+=1
 _row=_identity.copy()
 _row.update(kind='mpy-sample',sequence=_sequence,motion=_motion)
 print('PUBLIC_MAIN_MPY '+json.dumps(_row))
 time.sleep_ms(200)
