from pathlib import Path
import base64,hashlib,io,json,socket,sys,tempfile,types
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
PROBE=ROOT/'.work/flashlight-live-probe-20261027/probe.py'
SOURCE=Path(__file__).with_name('probe-reviewed.py.txt').read_bytes()
def deny(*args,**kwargs):raise AssertionError('network prohibited in offline review')
socket.create_connection=deny;socket.socket.connect=deny
m=types.ModuleType('offline_flashlight_probe');m.__file__=str(PROBE)
exec(compile(SOURCE,str(PROBE),'exec'),m.__dict__)
phases=[]
for phase in m.PHASES:
 payload=m.package('a'*32,phase,{'white':2,'yellow':1})
 compile(payload['files']['main.py']['data'],'main.py','exec')
 assert base64.b64decode(payload['files']['official_flash.py']['data'])==m.DRIVER.read_bytes()
 phases.append(phase)
class FakeClient:
 def __init__(self):self.after=False;self.lane=None
 def json(self,path,method='GET',body=None,**kw):
  if path.startswith('sessions/') and '/serial?' in path:
   record={'phase':'raw9','nonce':self.lane.nonce,'en':0,'driver_sha256':m.DRIVER_SHA,'driver_file':'/fixture/official_flash.py'}
   return {'next_offset':0,'data':m.PREFIX+json.dumps(record)+'\n' if self.after else ''}
  if path=='program-revisions':return {'revision':{'revision_id':'a'*64}}
  if path.endswith('/program'):
   if method=='POST':self.after=True;return {'program':{'execution_id':'b'*32,'revision_id':'a'*64,'pid':1234,'firmware_sha256':'f'*64,'state':'running'}}
   return {'program':{'execution_id':'c'*32,'revision_id':'d'*64,'pid':1234,'firmware_sha256':'f'*64,'state':'completed'}}
  if path.endswith('/units'):
   return {'units':[{'available':True,'errors':{},'properties':{'flash-mode':True,'mode-frozen':True,'output-known':False,'active':False,'edge-count':0,'decoded-programs':0,'unqualified-programs':0}}]}
  raise AssertionError(('unexpected fake route',path))
 def request(self,path,**kw):
  image=m.Image.new('RGB',(64,64),(0,0,0));buffer=io.BytesIO();image.save(buffer,format='PNG');raw=buffer.getvalue()
  return raw,{'x-frame-sha256':m.common.sha(raw),'x-frame-execution-id':'c'*32,'x-frame-revision-id':'d'*64}
with tempfile.TemporaryDirectory() as temp:
 client=FakeClient();lane=m.Lane(client,SimpleNamespace(),'cores3',True,Path(temp));client.lane=lane
 lane.owned['session_id']='1'*32;lane.session={'pid':1234,'firmware_sha256':'f'*64};lane.pins={'white':2,'yellow':1};lane.same_vm=lambda:None
 observation=lane.phase('raw9')
 assert observation['execution']['execution_id']=='c'*32
 assert lane.report['runs'][0]['execution_id']=='b'*32
 assert observation['unit']['properties']['edge-count']==0
 wrong_run_accepted={'status':'REPRODUCED','category':'offline fake negative control only','submitted_revision':'a'*64,'receipt_execution':'b'*32,'observed_execution':'c'*32,'observed_revision':'d'*64,'actual_Lane_phase_returned_without_error':True,'unit_output_known':False,'unit_edge_count':0}
# Isolate execute's classification policy using fake observations, never an API.
with tempfile.TemporaryDirectory() as temp:
 lane=m.Lane(None,SimpleNamespace(hold_file=None),'cores3',True,Path(temp))
 lane.create=lambda:None;lane.same_vm=lambda:None;lane.reject_mode=lambda:None;lane.capture_zip=lambda:None;lane.cleanup=lambda:{'status':'PASS'}
 lane.phase=lambda phase:{'phase':phase,'unit':{'properties':{'output-known':False,'active':False,'edge-count':0,'decoded-programs':0,'unqualified-programs':0}}}
 result=lane.execute();assert result['status']=='PASS'
 classification={'status':'REPRODUCED','category':'offline fake negative control only','all_Flash_phase_output_known':False,'all_Flash_phase_edge_count':0,'actual_Lane_execute_report_status':result['status']}
report={'category':'OFFLINE_CHECKER_AUDIT_NO_GUEST_NO_API','probe_sha256':hashlib.sha256(SOURCE).hexdigest(),'driver_sha256':hashlib.sha256(m.DRIVER.read_bytes()).hexdigest(),'driver_bytes':len(m.DRIVER.read_bytes()),'phases_compiled':phases,'network':'DENIED','wrong_Run_identity_negative':wrong_run_accepted,'Flash_classifier_negative':classification}
Path(__file__).with_name('report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
