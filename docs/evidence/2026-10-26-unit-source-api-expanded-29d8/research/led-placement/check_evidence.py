from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone
import hashlib, json, re

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent.parent
checks=[]
def check(name,condition):
    checks.append({'name':name,'passed':bool(condition)})
    if not condition:
        raise AssertionError(name)
def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
source_index=read('source-index.json')
allowed={'api.github.com','raw.githubusercontent.com','github.com','docs.m5stack.com','static-cdn.m5stack.com','m5stack-doc.oss-cn-shenzhen.aliyuncs.com','m5stack.oss-cn-shenzhen.aliyuncs.com'}
for source in source_index['sources']:
    name=source['name']
    check('public_source_host:'+name,urlparse(source['url']).hostname in allowed)
    check('source_fetch_and_hash:'+name,source['status']==200 and sha(ROOT/name)==source['sha256'])
    check('source_receipt_matches_index:'+name,read(name+'.receipt.json')==source)
audit=read('frozen-model-audit.json')
for file in audit['files']:
    check('frozen_vendor_hash:'+file['repo_path'],sha(REPO/file['repo_path'])==file['sha256']==file['vendor_manifest_sha256'])
for item in read('frozen-source-asset-comparison.json')['matches']:
    check('public_asset_matches_freeze:'+item['file'],sha(ROOT/item['file'])==item['sha256'] and item['matches_frozen_vendor_source'])
findings=read('findings.json')
check('both_mappings_open',all(p['mapping_status']=='OPEN' for p in findings['products'].values()))
check('rgb_physical_mapping_stays_empty',all(v is None for v in findings['products']['rgb']['electrical_chain_position_to_visual_id'].values()))
check('encoder_protocol_mapping_stays_empty',all(v is None for v in findings['products']['encoder']['protocol_index_to_visual_id'].values()))
check('encoder_refdes_side_stays_empty',all(v is None for v in findings['products']['encoder']['refdes_to_physical_side'].values()))
check('no_runtime_claim',findings['mutations']['device_service_calls']==0 and findings['mutations']['runtime_or_qemu_started'] is False)
feedback_ids=[]
for product in ('rgb','encoder'):
    response=read('internal/mcp-feedback-'+product+'.json')['result']
    result=response['structuredContent']
    check('official_feedback_accepted:'+product,response['isError'] is False and result['accepted'] is True and result['feedback_id'])
    feedback_ids.append(result['feedback_id'])
# Keep service/session identifiers and home paths outside public authored outputs.
for name in ('report.md','findings.json','source-index.json','frozen-model-audit.json','frozen-source-asset-comparison.json'):
    text=(ROOT/name).read_text(encoding='utf-8')
    check('authored_public_output_redaction:'+name,
          not any(x in text for x in feedback_ids) and 'https://mcp.' not in text and '/Users/' not in text)
report=(ROOT/'report.md').read_text(encoding='utf-8')
for link in re.findall(r'\]\(([^)]+)\)',report):
    if not urlparse(link).scheme:
        check('report_local_link:'+link,(ROOT/link).is_file())
for path in ROOT.iterdir():
    if path.is_file() and path.suffix in ('.json','.md','.py','.txt','.mjs'):
        path.read_text(encoding='utf-8')
check('root_text_files_valid_utf8',True)
result={'schema_version':1,'checked_at':datetime.now(timezone.utc).isoformat(),
        'status':'PASS','source_count':len(source_index['sources']),
        'frozen_file_count':len(audit['files']),'check_count':len(checks),'checks':checks,
        'scope':'Offline artifact integrity, redaction and unresolved-mapping checks only; no API/runtime/hardware execution.'}
(ROOT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:result[k] for k in ('status','source_count','frozen_file_count','check_count')},ensure_ascii=False))
