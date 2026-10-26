from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlparse
from datetime import datetime,timezone
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent
urls=json.loads(Path(sys.argv[1]).read_text())
def fetch(item):
 name,url=item
 assert urlparse(url).hostname in ('api.github.com','raw.githubusercontent.com','github.com','docs.m5stack.com','static-cdn.m5stack.com','m5stack-doc.oss-cn-shenzhen.aliyuncs.com','m5stack.oss-cn-shenzhen.aliyuncs.com')
 record={'name':name,'url':url,'fetched_at':datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={'User-Agent':'Codex-M5Stack-LED-placement-research'}),timeout=25) as response:
   body=response.read(20*1024*1024+1);assert len(body)<=20*1024*1024
   record.update(status=response.status,final_url=response.url,content_type=response.headers.get('Content-Type'),size=len(body),sha256=hashlib.sha256(body).hexdigest());target=ROOT/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
 except HTTPError as e:record.update(status=e.code,error=str(e))
 except Exception as e:record.update(status='ERROR',error=str(e))
 (ROOT/(name+'.receipt.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
 return record
for result in ThreadPoolExecutor(max_workers=5).map(fetch,urls):print(result['name'],result['status'],result.get('size'))
