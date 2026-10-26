#!/usr/bin/env python3
"""Offline archive audit; --write refreshes only audit-report.json/root SHA256SUMS.

--add-source REPO_RELATIVE=ARCHIVE_RELATIVE copies/registers additional raw root
verification logs without rewriting bytes. No API, subprocess, guest or compiler.
"""
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit
import argparse,ast,hashlib,io,ipaddress,json,re,zipfile
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda raw:hashlib.sha256(raw).hexdigest()
load=lambda path:json.loads(path.read_bytes())
AUTHORED={'README.md','assemble_archive.py','audit_archive.py','machine-summary.json','copy-provenance.json','transport-paths.json','exclusions.json','audit-report.json','SHA256SUMS'}
BAD_SUFFIX={'.pyc','.bin','.elf','.rom','.exe','.dylib','.so','.o','.a'}
EXEC_MAGIC={b'\x7fELF',b'\xcf\xfa\xed\xfe',b'\xce\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xfe\xed\xfa\xce',b'\xca\xfe\xba\xbe'}
IMAGE_MAGIC=(b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff',b'GIF87a',b'GIF89a')
def write(name,value):(HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def local(relative):
 path=(HERE/relative).resolve();assert path.is_relative_to(HERE) and path!=HERE,'unsafe archive path';return path

def register(spec):
 source_name,target_name=spec.split('=',1);source=(ROOT/source_name).resolve();assert source.is_relative_to(ROOT) and source.is_file() and not source.is_symlink()
 target=local(target_name);assert target.suffix.lower() not in BAD_SUFFIX and source.read_bytes()[:4] not in EXEC_MAGIC
 raw=source.read_bytes();original=target.relative_to(HERE).as_posix()
 if target.suffix.lower()=='.md':
  target=target.with_name(target.name+'.txt');transport=load(HERE/'transport-paths.json');row={'original_relative_path':original,'transport_relative_path':target.relative_to(HERE).as_posix(),'sha256':sha(raw),'size':len(raw),'byte_changes':False};transport['files']=[r for r in transport['files'] if r['original_relative_path']!=original]+[row];transport['files'].sort(key=lambda r:r['original_relative_path']);write('transport-paths.json',transport)
 target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():assert target.read_bytes()==raw,'new verification must use fresh destination or identical bytes'
 else:target.write_bytes(raw)
 provenance=load(HERE/'copy-provenance.json');provenance['files'][target.relative_to(HERE).as_posix()]={'source':source.relative_to(ROOT).as_posix(),'sha256':sha(raw),'size':len(raw),'byte_changes':False};write('copy-provenance.json',provenance)


def audit(validate_root=True):
 files=sorted(p for p in HERE.rglob('*') if p.is_file());relative={p.relative_to(HERE).as_posix():p for p in files};transport=load(HERE/'transport-paths.json')['files'];transport_by_original={row['original_relative_path']:row for row in transport};provenance=load(HERE/'copy-provenance.json')['files'];exclusions=load(HERE/'exclusions.json')['excluded'];excluded_by_path={row['archive_path']:row for row in exclusions}
 checks=0;privacy=[];nested=[];zip_entries=0;zip_payloads=0;zip_unique=set();images=0;text_files=0
 def check(ok,message):
  nonlocal checks
  checks+=1
  if not ok:raise AssertionError(message)
 def transported(name):return transport_by_original.get(name,{}).get('transport_relative_path',name)
 for row in transport:
  path=local(row['transport_relative_path']);check(path.is_file() and sha(path.read_bytes())==row['sha256'] and len(path.read_bytes())==row['size'] and row['byte_changes'] is False,'Markdown transport bytes differ: '+row['transport_relative_path'])
  check(not (HERE/row['original_relative_path']).exists(),'untransported Markdown duplicate: '+row['original_relative_path'])
 check({name for name in relative if name.endswith('.md')}=={'README.md'},'original MD was not transported')
 check(set(relative)-set(provenance)<=AUTHORED,'unregistered source artifacts: '+str(sorted(set(relative)-set(provenance)-AUTHORED)))
 for name,row in provenance.items():
  path=local(name);check(path.is_file() and sha(path.read_bytes())==row['sha256'] and path.stat().st_size==row['size'] and row['byte_changes'] is False,'copy provenance bytes differ: '+name)
  source=ROOT/row['source']
  if source.is_file():check(source.read_bytes()==path.read_bytes(),'copied source bytes were changed: '+name)
 for name,path in relative.items():
  check(not path.is_symlink() and '__pycache__' not in path.parts and path.name!='.DS_Store' and path.suffix.lower() not in BAD_SUFFIX,'binary/cache/symlink artifact: '+name)
  check(path.read_bytes()[:4] not in EXEC_MAGIC,'native executable artifact: '+name)
  check('/internal/' not in '/'+name and not name.startswith('research/upstream/mcp-') and not name.endswith('/official_mcp_client.mjs'),'private raw research artifact included: '+name)
  if path.name in ('SHA256SUMS','HARNESS_SHA256SUMS') and path!=HERE/'SHA256SUMS':
   for line in path.read_text().splitlines():
    if not line:continue
    match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line);check(match is not None,'invalid original nested SHA line: '+name)
    digest,member=match.groups();original=(path.parent/PurePosixPath(member)).relative_to(HERE).as_posix();target=local(transported(original))
    if target.is_file():check(sha(target.read_bytes())==digest,'original nested checksum differs after transport: '+original);nested.append({'manifest':name,'member':member,'status':'VERIFIED'})
    else:
     excluded=excluded_by_path.get(original);check(excluded is not None and excluded.get('sha256')==digest,'unexplained missing nested SHA input: '+original);nested.append({'manifest':name,'member':member,'status':'EXPLICITLY_EXCLUDED','sha256':digest})
 def privacy_scan(raw,locator):
  nonlocal text_files
  try:text=raw.decode('utf-8')
  except UnicodeDecodeError:return
  text_files+=1
  patterns={'private-key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----','openai-key':r'\bsk-[A-Za-z0-9_-]{24,}','literal-bearer':r'(?i)\bBearer\s+([A-Za-z0-9_.~+/-]{24,})','literal-secret-assignment':r'''(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)\s*[=:]\s*["']([^"'\r\n]{16,})["']''','mac-address':r'(?<![\da-fA-F])(?:[\da-fA-F]{2}:){5}[\da-fA-F]{2}(?![\da-fA-F])'}
  for kind,pattern in patterns.items():
   for match in re.finditer(pattern,text):
    # Checker source contains regex literals, not captured credential values.
    value=match.group(0)
    privacy.append({'kind':kind,'path':locator,'match_sha256':sha(value.encode()),'length':len(value)})
  for match in re.finditer(r'https?://[^\s\x22\x27<>\\)]+',text):
   value=match.group(0)
   if any(c in value for c in '{}$'):continue
   try:host=urlsplit(value).hostname
   except ValueError:continue
   if not host:continue
   try:ip=ipaddress.ip_address(host)
   except ValueError:
    if host.endswith('.local') or host.endswith('.lan'):privacy.append({'kind':'private-host-url','path':locator,'match_sha256':sha(value.encode()),'length':len(value)})
    continue
   # Loopback Device Service and QEMU's documented SLiRP fixture are reproducible local test endpoints.
   allowed=ip.is_loopback or str(ip) in ('10.0.2.2','10.0.2.15') or ip in ipaddress.ip_network('192.0.2.0/24') or ip in ipaddress.ip_network('198.51.100.0/24') or ip in ipaddress.ip_network('203.0.113.0/24')
   if ip.is_private and not allowed:privacy.append({'kind':'private-ip-url','path':locator,'match_sha256':sha(value.encode()),'length':len(value)})
 def decode_image(raw,locator):
  nonlocal images
  with Image.open(io.BytesIO(raw)) as im:im.load();check(im.width>0 and im.height>0,'invalid image dimensions: '+locator)
  images+=1
 def inspect(raw,locator,inside_zip=False):
  nonlocal zip_entries,zip_payloads
  check(raw[:4] not in EXEC_MAGIC,'native executable inside archive container: '+locator)
  is_image=raw.startswith(IMAGE_MAGIC) or (raw.startswith(b'RIFF') and raw[8:12]==b'WEBP')
  if is_image:decode_image(raw,locator)
  elif raw.startswith(b'PK\x03\x04') or raw.startswith(b'PK\x05\x06'):
   check(not inside_zip,'nested ZIP is not expected: '+locator);zip_payloads+=1;zip_unique.add(sha(raw))
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    check(z.testzip() is None,'ZIP CRC failure: '+locator);names=z.namelist();check(len(names)==len(set(names)),'ZIP duplicate members: '+locator)
    for info in z.infolist():
     name=info.filename;parts=PurePosixPath(name);check(not parts.is_absolute() and '..' not in parts.parts and '\\' not in name,'unsafe ZIP member path: '+locator+'!'+name)
     check(PurePosixPath(name).suffix.lower() not in BAD_SUFFIX and '__pycache__' not in parts.parts,'binary/cache ZIP member: '+locator+'!'+name)
     zip_entries+=1
     if not info.is_dir():inspect(z.read(info),locator+'!'+name,True)
    if 'manifest.json' in names:
     manifest=json.loads(z.read('manifest.json'));index=manifest.get('files',{});check(set(index)==set(names)-{'manifest.json'},'ZIP manifest membership differs: '+locator)
     for name,row in index.items():data=z.read(name);check(len(data)==row['size'] and sha(data)==row['sha256'],'ZIP manifest member bytes differ: '+locator+'!'+name)
  else:privacy_scan(raw,locator)
 for name,path in relative.items():
  if name in ('audit-report.json','SHA256SUMS'):continue
  inspect(path.read_bytes(),name)
  if path.suffix=='.py':ast.parse(path.read_text(),filename=name)
 # Public LED sources can be fully checked without private MCP feedback files.
 led=HERE/'research/led-placement';source_index=load(led/'source-index.json')
 allowed_hosts={'api.github.com','raw.githubusercontent.com','github.com','docs.m5stack.com','static-cdn.m5stack.com','m5stack-doc.oss-cn-shenzhen.aliyuncs.com','m5stack.oss-cn-shenzhen.aliyuncs.com'}
 for row in source_index['sources']:
  original='research/led-placement/'+row['name'];path=local(transported(original));check(path.is_file() and sha(path.read_bytes())==row['sha256'] and path.stat().st_size==row['size'] and row['status']==200 and urlsplit(row['url']).hostname in allowed_hosts,'public LED source/receipt differs: '+row['name']);check(load(led/(row['name']+'.receipt.json'))==row,'LED source receipt differs: '+row['name'])
 findings=load(led/'findings.json');check(all(p['mapping_status']=='OPEN' for p in findings['products'].values()),'LED mapping was closed without evidence')
 check(all(v is None for v in findings['products']['rgb']['electrical_chain_position_to_visual_id'].values()) and all(v is None for v in findings['products']['encoder']['protocol_index_to_visual_id'].values()) and all(v is None for v in findings['products']['encoder']['refdes_to_physical_side'].values()),'LED unresolved map was filled')
 # Recompute current/combined counts from exact saved result bytes.
 summary=load(HERE/'machine-summary.json');sessions=summary['sessions'];check(len(sessions)==25 and len({s['session_id'] for s in sessions})==25,'current archive session count differs')
 for row in sessions:
  path=local(row['result_path']);r=load(path);check(sha(path.read_bytes())==row['result_sha256'] and r['session_id']==row['session_id'] and r['status']==row['status'] and r['firmware_sha256']==row['firmware_sha256'] and r['source']['artifact_id']==row['source_cas_sha256'],'machine summary session was relabeled: '+row['result_path'])
  check(r['runtime_provenance']['runtime_binary_sha256']==summary['runtime_sha256'] and r['runtime_provenance']['worker_generation']==11,'session runtime/generation differs')
 current={'total_sessions':len(sessions),'functional_pass_sessions':sum(s['status']=='PASS' and s['classification'].startswith('functional-') for s in sessions),'negative_control_pass_sessions':sum(s['status']=='PASS' and s['classification']=='negative-runtime-control' for s in sessions),'review_sessions':sum(s['status']=='REVIEW_REQUIRED' for s in sessions),'failed_sessions':sum(s['status']=='FAIL' for s in sessions)}
 check(current==summary['current_archive_counts']=={'total_sessions':25,'functional_pass_sessions':22,'negative_control_pass_sessions':1,'review_sessions':1,'failed_sessions':1},'current counts differ')
 root_count=load(HERE/'verification/root-count-audit.json');check(root_count['total_sessions']==33 and root_count['functional_pass_sessions']==30 and root_count['negative_control_pass_sessions']==root_count['review_sessions']==root_count['failed_sessions']==1,'combined count differs')
 check(len(root_count['covered_selected_scenarios'])==27 and len(root_count['original_types'])==25 and set(root_count['custom_types'])=={'ir','buzzer'} and not root_count['missing_catalog_types'] and not root_count['excess_types'],'combined selected Unit set differs')
 for row in root_count['rows']:
  # Current 25 results live in this archive; prior eight live in its sibling.
  # Original .work files are an optional additional check, never a dependency.
  archived=[local(name) for name,entry in provenance.items() if entry['source']==row['result']]
  if not archived:
   previous_prefixes={'.work/unit-agent-api-live-20261026/live-button-r1/':'batches/button-smoke-r1/','.work/unit-agent-api-live-20261026/live-five-r1/':'batches/five-r1/','.work/unit-guide-live-20261026/live-r1/':'batches/guide-r1/'}
   for prefix,target in previous_prefixes.items():
    if row['result'].startswith(prefix):archived.append(HERE.parent/'2026-10-26-unit-source-api-29d8'/target/row['result'][len(prefix):])
  check(bool(archived) and all(path.is_file() and sha(path.read_bytes())==row['sha256'] for path in archived),'root count archived result changed or missing')
  source=(ROOT/row['result']).resolve();check(source.is_relative_to(ROOT),'root count source path escapes repository')
  if source.is_file():check(sha(source.read_bytes())==row['sha256'],'optional local count source result changed')
 # Do not store the actual matched values; the report records only locator/hash.
 check(not privacy,'credential/MAC/private-URL candidates need classification: '+json.dumps(privacy[:12],ensure_ascii=False))
 expected_root=HERE/'SHA256SUMS'
 if validate_root:
  check(expected_root.is_file(),'root SHA256SUMS missing; run --write after assembly')
  listed=set()
  for line in expected_root.read_text().splitlines():
   digest,name=line.split('  ',1)
   listed.add(name)
   check(local(name).is_file() and sha(local(name).read_bytes())==digest,'root checksum changed: '+name)
  check(listed==set(relative)-{'SHA256SUMS'},'root SHA inventory omits or adds files')
 payload=[p for p in files if p.name!='SHA256SUMS' and p!=HERE/'audit-report.json']
 return {'schema_version':1,'status':'PASS','scope':'Offline archive bytes/transport/provenance/CRC/images/privacy/counts only; no API/guest/QEMU/compiler call','check_count':checks,'payload_file_count_excluding_root_audit_and_checksum':len(payload),'payload_bytes_excluding_root_audit_and_checksum':sum(p.stat().st_size for p in payload),'copy_provenance_files':len(provenance),'transported_markdown_files':len(transport),'nested_checksum_entries':len(nested),'nested_checksum_verified':sum(r['status']=='VERIFIED' for r in nested),'nested_checksum_explicit_exclusions':[r for r in nested if r['status']=='EXPLICITLY_EXCLUDED'],'zip_payload_copies':zip_payloads,'unique_zip_sha256_count':len(zip_unique),'zip_member_checks':zip_entries,'decoded_images_including_raw_and_zip_copies':images,'decoded_utf8_payloads':text_files,'credential_mac_private_url_candidates':privacy,'public_led_source_count':len(source_index['sources']),'current_archive_counts':current,'combined_counts':{k:root_count[k] for k in ('total_sessions','functional_pass_sessions','negative_control_pass_sessions','review_sessions','failed_sessions')},'no_binary_or_private_raw_inputs':True,'markdown_transport_byte_changes':False,'hardware':'NOT RUN'}


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');parser.add_argument('--add-source',action='append',default=[]);args=parser.parse_args()
 if args.add_source:assert args.write,'--add-source requires --write'
 for value in args.add_source:register(value)
 report=audit(validate_root=not args.write)
 if args.write:
  write('audit-report.json',report)
  files=sorted(p for p in HERE.rglob('*') if p.is_file() and p!=HERE/'SHA256SUMS');(HERE/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.relative_to(HERE).as_posix()+'\n' for p in files))
 files=[p for p in HERE.rglob('*') if p.is_file()]
 print(json.dumps({'status':report['status'],'file_count':len(files),'bytes':sum(p.stat().st_size for p in files),'checks':report['check_count'],'zip_payload_copies':report['zip_payload_copies'],'unique_zip_hashes':report['unique_zip_sha256_count'],'zip_members':report['zip_member_checks'],'decoded_images':report['decoded_images_including_raw_and_zip_copies'],'transported_markdown':report['transported_markdown_files'],'nested_checksums':report['nested_checksum_entries']},indent=2))
if __name__=='__main__':main()
