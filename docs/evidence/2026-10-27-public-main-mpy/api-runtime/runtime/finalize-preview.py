from pathlib import Path
import io,json,sys,zipfile
from datetime import datetime,timezone
sys.path[:0]=['tests/units','platform/tools']
import run_binary_checkpoint_admission as c
import run_main_mpy_runtime as r
from PIL import Image
root=r.ROOT
base=root/'.work/public-main-mpy-runtime-gen45-20261027-r1'
output=base/'preview-finalization'
output.mkdir(exist_ok=False)
handoff_path=base/'preview/handoff.json'
hold=json.loads(handoff_path.read_text())
web_path=root/'.work/main-mpy-web-acceptance-20261027/gen45-r1/report.json'
web=json.loads(web_path.read_text())
report={'status':'FAIL','category':'public-main-mpy-managed-preview-finalization','hardware':'NOT RUN','started_at':datetime.now(timezone.utc).isoformat(),'handoff_report_sha256':c.sha((base/'preview/report.json').read_bytes()),'handoff_sha256':c.sha(handoff_path.read_bytes()),'web_report_sha256':c.sha(web_path.read_bytes()),'web_status':web['status'],'errors':[]}
require=c.require
require(web['status']=='PASS' and web['handoff']==hold,'Web report ownership/status differs')
client=c.Client('http://127.0.0.1:8787',c.read_token(root/'.work/preview-control-token'),output)
sid,pid,preview=hold['session_id'],hold['pid'],hold['preview_id']
session=None
expected_frame='e94c98d777799feb6de6025fcbc60f0d1e46faf415d98281204a2d85c95ca942'
try:
 health=client.json('health');worker=health['capacity']['worker']
 require(worker['generation']==45 and worker['pid']==95400 and health['capacity']['active_sessions']==1,'service generation/ownership changed')
 report['health_before']=health
 session=client.json('sessions/'+sid)
 require(session['state']=='running' and session['pid']==pid and session['firmware_sha256']==hold['firmware_sha256'] and session['worker']['generation']==45,'guest identity differs')
 require(c.runtime_identity(pid)['sha256']==hold['runtime_sha256'],'runtime executable differs')
 pre=client.json('previews/'+preview)
 require(pre['owner_epoch']==hold['owner_epoch'] and pre['session_id']==sid,'Preview identity differs')
 program=client.json('sessions/'+sid+'/program')['program']
 require(program['state']=='running' and program['entrypoint']=='main.py','Web recovery source not running')
 serial=client.json(f'sessions/{sid}/serial?offset={program["serial_offset"]}&limit=1048576')
 rows=r.records(serial['data'])
 recovery=next(row for row in rows if row.get('kind')=='source-recovery')
 require(recovery['nonce']==hold['nonce'] and recovery['count']==3 and recovery['owner_id']==recovery['expected_owner_id']==hold['owner_id'] and recovery['owner_restored'] is True,'same VM source/owner restoration differs')
 raw,headers=client.request(f'sessions/{sid}/frame.png?max_age_ms=1',binary=True)
 require(c.sha(raw)==headers['x-frame-sha256']==expected_frame,'final frame differs from actual Web frame')
 require(headers['x-frame-execution-id']==program['execution_id'] and headers['x-frame-revision-id']==program['revision_id'],'final frame belongs to another execution')
 with Image.open(io.BytesIO(raw)) as im: require(list(im.convert('RGB').getpixel((im.width//2,im.height//2)))==[0,0,255],'final source frame not blue')
 (output/'last-live.png').write_bytes(raw)
 runs={row['execution_id']:row for row in json.loads((base/'preview/report.json').read_text())['runs']}
 for phase in web['phases']:
  row=(phase.get('execution') or {}).get('program')
  if row:runs[row['execution_id']]=row
 runs[program['execution_id']]=program
 raw=client.json('sessions/'+sid+'/evidence',binary=True)
 (output/'evidence-before-close.zip').write_bytes(raw)
 zip_receipt=c.verify_zip(raw,session,list(runs.values()))
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  manifest=json.loads(z.read('manifest.json'))
  durable={name:json.loads(z.read(name)) for name in z.namelist() if name.startswith('programs/') and name.endswith('.json') and len(name.split('/'))==2}
  require({row['execution_id'] for row in durable.values()}==set(runs),'final ZIP missing Web/API runs')
 report.update(session_before=session,preview_before=pre,final_program=program,source_recovery=recovery,
               final_frame_sha256=expected_frame,zip_before_close=zip_receipt,durable_programs=durable,
               web_run_count=len(web['phases']),web_mutation_count=len(web['mutations']),web_forbidden=web['forbidden'])
except BaseException as error:
 report['errors'].append({'stage':'before-close','type':type(error).__name__,'message':str(error)})
finally:
 try:
  report['close_receipt']=client.json('previews/'+preview+'/close','POST',{'expected_owner_epoch':hold['owner_epoch']})
  closed=c.poll(lambda:client.json('previews/'+preview),lambda x:x['state']=='closed',120)
  stopped=c.poll(lambda:client.json('sessions/'+sid),lambda x:x['state']=='stopped',30)
  gone=c.poll(lambda:c.pid_gone(pid),bool,15)
  require(stopped['flash_retained'] is False and stopped['worker']['lease_active'] is False and gone is True,'Flash/owned PID/lease not released')
  historical=client.json('sessions/'+sid+'/frame.png',binary=True)
  (output/'history-last.png').write_bytes(historical)
  require(c.sha(historical)==expected_frame,'history frame does not retain exact Web final SHA')
  capacity=client.json('capacity')
  require(capacity['active_sessions']==0 and capacity['worker']['active_lease_count']==0,'final owned service still has allocations')
  require(report['handoff_report_sha256']==c.sha((base/'preview/report.json').read_bytes()),'handoff report mutated')
  require(report.get('zip_before_close',{}).get('status')=='PASS','final ZIP before close unavailable')
  report.update(closed_preview=closed,stopped_session=stopped,pid_gone=gone,history_frame_sha256=c.sha(historical),final_capacity=capacity)
 except BaseException as error:
  report['errors'].append({'stage':'close-confirmation','type':type(error).__name__,'message':str(error)})
 if not report['errors']:report['status']='PASS'
 c.save(base/'finalization.json',report)
 print(json.dumps({'status':report['status'],'errors':report['errors'],'session_id':sid,'pid_gone':report.get('pid_gone'),'history_frame_sha256':report.get('history_frame_sha256'),'active_sessions':report.get('final_capacity',{}).get('active_sessions')},indent=2))
