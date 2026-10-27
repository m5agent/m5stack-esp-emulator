#!/usr/bin/env python3
"""Verify the fixed wrap-up archive without requiring the repository or network."""
import hashlib
import json
from pathlib import Path
import re

root=Path(__file__).resolve().parent
index=json.loads((root/'index.json').read_text())
actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}-{'index.json'}
assert actual==set(index['files']), 'unlisted or missing archive files'
for name,record in index['files'].items():
    data=(root/name).read_bytes()
    assert len(data)==record['bytes'] and hashlib.sha256(data).hexdigest()==record['sha256'], name
first=json.loads((root/'testing/first-candidate/summary.json').read_text())['results']
assert {k:v['status'] for k,v in first.items()}=={'cores3-peripherals':'FAIL','core2-axp192':'PASS','cores3-aw9523-full':'FAIL'}
fixed=json.loads((root/'testing/fixed/run/summary.json').read_text())['results']
assert len(fixed)==22 and all(v['status']=='PASS' and not v.get('retry_used') and v['attempts']==1 for v in fixed.values())
assert sum(len(v.get('checks',[])) for v in fixed.values())==92
for case in first:
    assert first[case]['reference_layout']['base_firmware_sha256']==fixed[case]['reference_layout']['base_firmware_sha256']
receipt=json.loads((root/'build/fixed/replay-receipt.json').read_text())
assert receipt['status']=='PASS' and receipt['patch_count']==13 and receipt['source_file_union_count']==109
assert receipt['all_109_sources_match_final_receipt'] and receipt['reverse_equals_fixed_base_tree'] and receipt['restore_equals_first_forward_tree']
assert len(receipt['patch_0047_nine_file_bindings'])==10
assert receipt['postimage_tree']==receipt['restored_tree']
build=json.loads((root/'build/fixed/build-manifest.json').read_text())
source=json.loads((root/'build/fixed/source-receipt.json').read_text())
assert build['binary_sha256']==index['runtime_sha256'] and build['files']==source['files'] and len(source['patches'])==13
for name,digest in source['patches'].items():
    assert hashlib.sha256((root/'build/fixed/patches'/(Path(name).name+'.txt')).read_bytes()).hexdigest()==digest
platform=(root/'testing/platform-final/platform.stderr.txt').read_text()
assert re.search(r'Ran 1226 tests in [\d.]+s\s+OK\s*$',platform), 'platform run did not finish successfully'
launch=json.loads((root/'testing/fixed/receipt.json').read_text())
assert launch['returncode']==0 and launch['runtime_sha256']==launch['runtime_after_sha256']==index['runtime_sha256']
closing=json.loads((root/'service/closing-state.json').read_text())
assert closing['all_service_sources_match'] and not closing['owned_qemu_processes']
assert closing['health']['capacity']['active_sessions']==0 and closing['health']['capacity']['worker']['active_lease_count']==0
assert index['unit_api']==index['mounted_web']==index['full_matrix']==index['hardware']=='NOT RUN'
print(json.dumps({'status':'PASS','files':len(actual),'platform_tests':1226,'targeted_cases':22,'checks':92,'new_unit_api':'NOT RUN','full_matrix':'NOT RUN'}))
