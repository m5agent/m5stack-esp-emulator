#!/usr/bin/env python3
"""Verify archived bytes/results; optionally recompile the saved C controls."""
import argparse,hashlib,json,shutil,subprocess,tempfile
from pathlib import Path

def digest(data):return hashlib.sha256(data).hexdigest()
def verify(root,replay_c=False):
 index=json.loads((root/'index.json').read_text())
 paths=set()
 for record in index['files']:
  name=record['path'];path=root/name
  assert name not in paths and not Path(name).is_absolute() and '..' not in Path(name).parts,name
  paths.add(name);assert path.is_file() and not path.is_symlink(),name
  data=path.read_bytes();assert len(data)==record['archive_bytes'] and digest(data)==record['archive_sha256'],name
  if record['representation']=='original-bytes':
   assert record['source_sha256']==record['archive_sha256'] and record['source_bytes']==record['archive_bytes'],name
  elif record['representation']=='path-redacted-copy':assert record['transformations'],name
 actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
 assert actual==paths|{'index.json'},sorted(actual^(paths|{'index.json'}))
 original=root/'originals/bias-check'
 receipt=json.loads((original/'receipt.json').read_text())
 assert receipt['status']=='PASS' and receipt['source_unchanged'] and receipt['syntax_exit_code']==0
 assert len(receipt['results'])==2 and len(receipt['commands'])==5
 assert all(command['exit_code']==0 for command in receipt['commands'])
 source=root/'source-snapshots/hw/m5stopwatch/esp32s3_soft_i2c.c'
 assert digest(source.read_bytes())==receipt['source_sha256']
 for result in receipt['results']:
  name=result['mode'];assert result['compile_exit_code']==0 and result['run_exit_code']==0
  assert digest((original/(name+'-harness.c')).read_bytes())==result['harness_sha256']
  output=(original/(name+'-run.stdout.txt')).read_text()
  assert output.count('probe_reads=0x'+('1' if name=='before' else '3'))==4
  assert output.count('scl_known='+('1 conflict=0 board_up=0' if name=='before' else '0 conflict=1 board_up=1'))==4
  assert output.count('external=0 ie=1')==4
  assert 'case=core2 sda=21 scl=22 pullups='+str(int(name=='after'))+' legacy_levels=1,1' in output
  assert not (original/(name+'-run.stderr.txt')).read_bytes()
 proof=root/'originals/permanent-tests'
 tests=json.loads((proof/'receipt.json').read_text())
 assert tests['status']=='PASS' and tests['exit_code']==0
 stderr=(proof/'stderr.txt').read_bytes()
 assert digest(stderr)==tests['stderr_sha256'] and digest((proof/'stdout.txt').read_bytes())==tests['stdout_sha256']
 assert b'Ran 2 tests' in stderr and stderr.rstrip().endswith(b'OK')
 assert stderr.count(b' ... ok')==2
 for name,expected in tests['test_inputs'].items():
  assert digest((root/'test-snapshots'/name).read_bytes())==expected,name
 replay_status='NOT RUN'
 if replay_c:
  compiler=shutil.which('cc');assert compiler,'cc required for --replay-c'
  with tempfile.TemporaryDirectory(prefix='soft-i2c-offline-') as temporary:
   for name in ('before','after'):
    source=original/(name+'-harness.c');binary=Path(temporary)/name
    command=[compiler,'-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function','-fsanitize=undefined','-O1','-DWITH_PULLUPS='+str(int(name=='after')),str(source),'-o',str(binary)]
    compiled=subprocess.run(command,capture_output=True,timeout=30)
    assert compiled.returncode==0,compiled.stderr.decode(errors='replace')
    executed=subprocess.run([str(binary)],capture_output=True,timeout=10)
    assert executed.returncode==0,executed.stderr.decode(errors='replace')
    assert executed.stdout==(original/(name+'-run.stdout.txt')).read_bytes()
    assert not executed.stderr
  replay_status='PASS'
 return {'status':'PASS','files_verified':len(paths),'original_source_results':'before probe 0x1; after 0x3 with unknown/conflict; Core2 unchanged','permanent_tests':2,'offline_C_replay':replay_status,'guest_hardware_claim':False}

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--replay-c',action='store_true');args=parser.parse_args()
 print(json.dumps(verify(Path(__file__).resolve().parent,args.replay_c),indent=2))
