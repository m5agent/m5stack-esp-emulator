#!/usr/bin/env python3
"""Copy only terminal evidence/public research; transport Markdown without editing bytes.

Repository-local archival helper. It never calls an API, executes a guest,
compiles the C diagnostic or includes firmware/runtime binaries.
"""
from pathlib import Path
import hashlib,json,shutil
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sha=lambda raw:hashlib.sha256(raw).hexdigest()
EXCLUDED=[];COPIED={}
BATCHES={
 'sensors-r1':'.work/unit-source-sensors-expanded-20261026/live-r1',
 'controls-v2-r1':'.work/unit-source-controls-expanded-20261026/live-v2-r1',
 'io-default9-r1':'.work/unit-source-io-expanded-20261026/live-default9-r1',
 'custom2-r1':'.work/unit-source-custom-io-20261026/live-custom2-r1',
 'original-risk2-r1':'.work/unit-source-io-expanded-20261026/live-original-risk-r1',
 'thermal-negative-r1':'.work/unit-source-sensors-expanded-20261026/live-thermal-negative-r1',
}
def save(name,value):(HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def blocked(path):
 if '__pycache__' in path.parts or path.name=='.DS_Store' or path.suffix.lower() in ('.pyc','.bin','.elf','.rom','.exe','.dylib','.so','.o','.a'):return True
 if path.is_symlink():return True
 if path.is_file() and path.read_bytes()[:4] in (b'\x7fELF',b'\xcf\xfa\xed\xfe',b'\xce\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xfe\xed\xfa\xce',b'\xca\xfe\xba\xbe'):return True
 return False

def copy(source,target):
 if blocked(source):
  EXCLUDED.append({'source':source.relative_to(ROOT).as_posix(),'archive_path':target.relative_to(HERE).as_posix(),'reason':'cache/symlink/firmware-or-native-executable','sha256':sha(source.read_bytes()) if source.is_file() and not source.is_symlink() else None});return
 raw=source.read_bytes();target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():assert target.read_bytes()==raw, 'existing archive copy drift: '+target.relative_to(HERE).as_posix()
 else:target.write_bytes(raw)
 COPIED[target.relative_to(HERE).as_posix()]={'source':source.relative_to(ROOT).as_posix(),'sha256':sha(raw),'size':len(raw),'byte_changes':False}

def tree(source,target,exclude=None,top_only=False):
 for path in sorted(source.iterdir() if top_only else source.rglob('*')):
  if not path.is_file():continue
  relative=path.relative_to(source).as_posix()
  if exclude and exclude(relative):
   dest=target/relative;EXCLUDED.append({'source':path.relative_to(ROOT).as_posix(),'archive_path':dest.relative_to(HERE).as_posix(),'reason':'private raw metadata or unnecessary full API metadata; public source/summary retained','sha256':sha(path.read_bytes()),'size':path.stat().st_size})
   if dest.exists():dest.unlink()
   continue
  copy(path,target/relative)

for name,source in BATCHES.items():
 path=ROOT/source;batch=json.loads((path/'batch-result.json').read_bytes());assert batch.get('finished_at'), 'batch is not terminal: '+name
 tree(path,HERE/'batches'/name)

harnesses={
 'sensors':('.work/unit-source-sensors-expanded-20261026',['run_source_sensor_acceptance.py','source_api_common.py','sensor_contract.py','contract-origin.json','delivery-freeze.json','README.md'],['fixtures']),
 'controls':('.work/unit-source-controls-expanded-20261026',['run_source_controls.py','contract.json','original-assertion-block.py.txt','test_rfid_phase_windows.py','README.md'],['freeze-v1','rfid-window-checker-r2']),
 'io':('.work/unit-source-io-expanded-20261026',['run_expanded_io.py','source_api_common.py','README.md','ready.json','offline-self-check.json','HARNESS_SHA256SUMS'],[]),
 'custom':('.work/unit-source-custom-io-20261026',['run_custom_io.py','source_api_common.py','README.md','ready.json','offline-self-check.json','HARNESS_SHA256SUMS','delivery-freeze.json'],[]),
}
for name,(source,files,dirs) in harnesses.items():
 for file in files:copy(ROOT/source/file,HERE/'harness'/name/file)
 for sub in dirs:tree(ROOT/source/sub,HERE/'harness'/name/sub)
# Preserve all final reviewers plus the prior harness review already copied.
reviews=ROOT/'.work/unit-expanded-cross-review-20261026'
assert sha((reviews/'io-live/review.json').read_bytes())=='e71379992b9a89d57c8c47e28469a1305118c74012bcfad78b81979b8eb17a2a'
assert sha((reviews/'custom/review.json').read_bytes())=='d81bf1f032c967f57ee190dad58ab416050fdab4f608f7fe9c16bda15b6fcc43'
assert sha((reviews/'original-risk/review.json').read_bytes())=='952fb7532d68874407c17d686675405d8ae4d7267158810186e1c3201569f52d'
tree(reviews,HERE/'review/final')
tree(reviews/'controls',HERE/'review/harness/controls')
tree(reviews/'sensors',HERE/'review/harness/sensors')
tree(reviews/'io',HERE/'review/harness/io')
# Only the public root of LED research is transported. No internal traversal.
led=ROOT/'.work/unit-led-placement-research-20261026';tree(led,HERE/'research/led-placement',top_only=True)
EXCLUDED.append({'source':'.work/unit-led-placement-research-20261026/internal/','archive_path':'research/led-placement/internal/','reason':'PRIVATE: raw MCP requests, clients, request/feedback identifiers and unrelated screenshots omitted as one entire subtree'})
up=ROOT/'.work/unit-driver-upstream-research-20261026';tree(up,HERE/'research/upstream',exclude=lambda name:name.startswith('mcp-') or name=='commit.json')
route=ROOT/'.work/unit-pwm-route-diagnostic-20261026'
for name in ('diagnostic.c','receipt.json'):copy(route/name,HERE/'host-pwm-route'/name)
EXCLUDED.append({'source':'.work/unit-pwm-route-diagnostic-20261026/diagnostic','archive_path':'host-pwm-route/diagnostic','reason':'native compiled diagnostic executable omitted; source and historical receipt retained; no compilation performed','sha256':sha((route/'diagnostic').read_bytes()),'size':(route/'diagnostic').stat().st_size})
copy(ROOT/'.work/unit-expanded-unit-tests-final.log',HERE/'verification/unit-tests-final.log')
copy(ROOT/'.work/unit-expanded-count-audit.json',HERE/'verification/root-count-audit.json')
# Original Markdown bytes are data. Only this archive's authored README is live MD.
transport=[]
for path in sorted(HERE.rglob('*.md')):
 if path==HERE/'README.md':continue
 original=path.relative_to(HERE).as_posix();target=path.with_name(path.name+'.txt');raw=path.read_bytes()
 if target.exists():assert target.read_bytes()==raw
 else:target.write_bytes(raw)
 path.unlink()
 transport.append({'original_relative_path':original,'transport_relative_path':target.relative_to(HERE).as_posix(),'sha256':sha(raw),'size':len(raw),'byte_changes':False})
# Support repeated assembly after already-transported Markdown; never change content.
previous=HERE/'transport-paths.json'
if previous.exists():
 known={item['original_relative_path']:item for item in json.loads(previous.read_bytes())['files']}
 known.update({item['original_relative_path']:item for item in transport});transport=list(known.values())
save('transport-paths.json',{'schema_version':1,'rule':'Original Markdown is transported as .md.txt without any byte edit; restore only the filename before original nested checksum/checker replay. Archive main README is authored separately.','byte_changes':False,'files':sorted(transport,key=lambda item:item['original_relative_path'])})
for item in transport:
 original=item['original_relative_path']
 if original in COPIED:COPIED[item['transport_relative_path']]=COPIED.pop(original)
save('copy-provenance.json',{'schema_version':1,'rule':'All copied source bytes retained exactly; source files are never modified. Markdown destination names may be transported using transport-paths.json.','files':COPIED})
save('exclusions.json',{'schema_version':1,'policy':['no firmware/ROM/BIN/ELF/native executable/cache','no private MCP/client/request/feedback raw metadata','LED research public root only','no original byte cleanup/redaction; omit whole private inputs instead'],'excluded':EXCLUDED})
print(json.dumps({'status':'COPIED_AND_TRANSPORTED','copied_files':len(COPIED),'transported_markdown':len(transport),'excluded_entries':len(EXCLUDED),'device_service_calls':0,'guest_processes':0,'compiled_binaries':0}))
