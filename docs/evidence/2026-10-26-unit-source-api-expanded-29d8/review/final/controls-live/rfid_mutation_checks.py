"""Synthetic negative mutations derived from terminal serial; never runtime evidence."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import copy,hashlib,importlib.util,json,os,re,socket,subprocess,urllib.request
ROOT=Path.cwd();HERE=ROOT/'.work/unit-expanded-cross-review-20261026/controls-live';SOURCE=ROOT/'.work/unit-source-controls-expanded-20261026';LIVE=SOURCE/'live-v2-r1';OUT=HERE/'rfid-negative-probes'
OUT.mkdir(exist_ok=False)
sha=lambda raw:hashlib.sha256(raw).hexdigest();load=lambda p:json.loads(p.read_bytes())
calls=[]
def deny(*a,**kw):calls.append('forbidden');raise AssertionError('negative parser check attempted API/process')
with ExitStack() as guards:
 for owner,name in ((urllib.request,'urlopen'),(socket,'socket'),(socket,'create_connection'),(subprocess,'Popen'),(subprocess,'run'),(os,'system'),(os,'popen')):guards.enter_context(patch.object(owner,name,deny))
 spec=importlib.util.spec_from_file_location('controls_negative_parser',SOURCE/'run_source_controls.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
 row=load(LIVE/'rfid2/prepared.json');result=load(LIVE/'rfid2/result.json');serial=(LIVE/'rfid2/serial.txt').read_bytes().decode();fixture=load(LIVE/'source-snapshot/platform/units/fixtures/cardkb-keymap.json.txt')
 phases=load(HERE/'independent-actual-evidence.json')['cases']['rfid2']['closed_fresh_uid_phases'];results=[]
 for phase_index,phase in enumerate(phases):
  markers=list(phase['ordered_marker_offsets']);start,end=phase['start'],phase['end_exclusive']
  for marker_index,marker in enumerate(markers):
   position=phase['ordered_marker_offsets'][marker];replacement=marker.replace('CONTROL_RFID_','CONTROL_XFID_',1);altered=serial[:position]+replacement+serial[position+len(marker):]
   label=f'uid{phase_index+1}-missing-marker-{marker_index+1}';directory=OUT/label;directory.mkdir();changed=copy.deepcopy(result)
   for index,step in enumerate(changed['steps']):
    prefix=altered[:step['serial_offset']].encode();name=f'before-{index}.txt';(directory/name).write_bytes(prefix);step.update(before_file=name,before_sha256=sha(prefix))
   (directory/'serial.txt').write_bytes(altered.encode())
   try:h.replay_controls(directory,row,changed,altered,fixture)
   except RuntimeError as error:
    message=str(error);assert ('RFID per-UID ordered positive/negative missing:' in message or 'fresh RFID UID absent:' in message),message
   else:raise AssertionError('checker borrowed missing marker across UID phase: '+label)
   results.append({'case':label,'removed_marker':marker,'rejected':True,'error':message})
  # Reorder CRC and key checks while preserving overall phase length/closed offsets.
  lines=serial[start:end].splitlines(keepends=True);a=next(i for i,line in enumerate(lines) if line.rstrip('\r\n')=='CONTROL_RFID_BAD_CRC 1');b=next(i for i,line in enumerate(lines) if line.rstrip('\r\n')=='CONTROL_RFID_BAD_KEY 1');lines[a],lines[b]=lines[b],lines[a];altered=serial[:start]+''.join(lines)+serial[end:]
  label=f'uid{phase_index+1}-reordered-crc-key';directory=OUT/label;directory.mkdir();changed=copy.deepcopy(result)
  for index,step in enumerate(changed['steps']):
   prefix=altered[:step['serial_offset']].encode();name=f'before-{index}.txt';(directory/name).write_bytes(prefix);step.update(before_file=name,before_sha256=sha(prefix))
  (directory/'serial.txt').write_bytes(altered.encode())
  try:h.replay_controls(directory,row,changed,altered,fixture)
  except RuntimeError as error:message=str(error);assert 'RFID per-UID ordered positive/negative missing:' in message,message
  else:raise AssertionError('checker accepted reordered controls: '+label)
  results.append({'case':label,'rejected':True,'error':message})
 assert len(results)==24 and not calls
 report={'status':'PASS','category':'SYNTHETIC_OFFLINE_MUTATION_OF_TERMINAL_SERIAL','runtime_or_guest_executed':False,'api_or_process_calls':0,'original_actual_serial_sha256':sha(serial.encode()),'tests':results}
 (HERE/'rfid-negative-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':'PASS','negative_mutations_rejected':len(results),'api_or_process_calls':0}))
