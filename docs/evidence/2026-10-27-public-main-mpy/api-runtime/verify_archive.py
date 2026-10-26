#!/usr/bin/env python3
"""Portable read-only verification; optional exact official fixture rebuild."""
import argparse,base64,hashlib,json,struct,subprocess,tempfile,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sha=lambda value:hashlib.sha256(value).hexdigest()
def read_document(path):
 value=json.loads(path.read_bytes())
 return value['document'] if isinstance(value,dict) and 'archive_notice' in value else value

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--compiler',type=Path);args=parser.parse_args()
 raw=(ROOT/'index.json').read_bytes();assert sha(raw)==(ROOT/'INDEX.sha256').read_text().split()[0], 'index SHA'
 index=json.loads(raw);seen=set();origins={}
 counts={}
 for row in index['records']:
  kind=row['classification'];counts[kind]=counts.get(kind,0)+1
  assert kind in {'original','redacted-json','redacted-text','hash-only','generated'}
  origin=row['original_source']
  if origin is not None:
   assert origin not in origins,origin
   origins[origin]=row
   assert len(row['original_sha256'])==64 and row['original_bytes']>=0
  rel=row['archive_path']
  if kind=='hash-only':assert rel is None;continue
  assert rel and not Path(rel).is_absolute() and '..' not in Path(rel).parts and rel not in seen, rel
  seen.add(rel);path=ROOT/rel;data=path.read_bytes()
  assert len(data)==row['archive_bytes'] and sha(data)==row['archive_sha256'],rel
  if kind=='original':assert row['original_bytes']==len(data) and row['original_sha256']==sha(data),rel
  if kind=='redacted-json':
   notice=json.loads(data)['archive_notice'];assert notice['original_sha256']==row['original_sha256'] and notice['original_bytes']==row['original_bytes'];assert notice['classification']=='redacted-json'
  if kind=='redacted-text':assert data.startswith(b'ARCHIVE REDACTED TEXT; original SHA256 '+row['original_sha256'].encode())
  assert path.suffix not in {'.mpy','.bin','.rom','.elf','.zip'},rel
  if data.startswith(b'\x89PNG\r\n\x1a\n'):
   offset=8;chunks=[]
   while offset<len(data):
    size=struct.unpack('>I',data[offset:offset+4])[0];name=data[offset+4:offset+8];body=data[offset+8:offset+8+size]
    assert zlib.crc32(name+body)&0xffffffff==struct.unpack('>I',data[offset+8+size:offset+12+size])[0],rel
    chunks.append(name);offset+=size+12
   assert offset==len(data) and chunks[0]==b'IHDR' and chunks[-1]==b'IEND',rel
 actual={str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file()}
 assert actual==seen|{'index.json','INDEX.sha256'},sorted(actual-seen-{'index.json','INDEX.sha256'})
 for origin,row in origins.items():
  if origin.endswith('!manifest.json'):
   manifest=read_document(ROOT/row['archive_path']);container=origin.removesuffix('!manifest.json')
   for name,item in manifest['files'].items():
    member=origins[container+'!'+name]
    assert member['original_sha256']==item['sha256'] and member['original_bytes']==item['size'],origin+'!'+name
 repro=read_document(ROOT/'reproducibility.json')
 for name,recipe in repro['recipes'].items():assert sha((ROOT/recipe['source']).read_bytes())==recipe['source_sha256']
 for name,package in repro['packages'].items():
  identity={'source_kind':'uiflow2-package','entrypoint':'main.mpy','files':package['files']}
  canonical=json.dumps(identity,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
  assert sha(canonical)==package['revision_id'],name
 assert repro['packages']['v1']['files']['main.mpy']==repro['packages']['v2']['files']['main.mpy']
 assert repro['packages']['v1']['files']['dep.mpy']!=repro['packages']['v2']['files']['dep.mpy']
 # Every encoded file payload was omitted, including bytecode in JSON members.
 def no_payload(value):
  if isinstance(value,dict):
   assert not (value.get('encoding')=='base64' and isinstance(value.get('data'),str))
   for x in value.values():no_payload(x)
  elif isinstance(value,list):
   for x in value:no_payload(x)
 for rel in seen:
  data=(ROOT/rel).read_bytes()
  try:value=json.loads(data)
  except (ValueError,UnicodeError):continue
  no_payload(value)
 if args.compiler:
  assert sha(args.compiler.read_bytes())==repro['compiler_sha256'],'official compiler SHA'
  with tempfile.TemporaryDirectory(prefix='m5-main-mpy-verify-') as temporary:
   for name,recipe in repro['recipes'].items():
    output=Path(temporary)/(name+'.mpy')
    subprocess.run([str(args.compiler.resolve()),'-s',recipe['source_name'],'-o',str(output),str(ROOT/recipe['source'])],check=True,capture_output=True,timeout=15)
    assert sha(output.read_bytes())==recipe['bytecode_sha256'],name
 print(json.dumps({'status':'PASS','archive_files':len(seen),'record_classes':counts,'fixture_rebuild':'PASS' if args.compiler else 'NOT RUN','api_contacted':False,'guests_started':0},sort_keys=True))
if __name__=='__main__':main()
