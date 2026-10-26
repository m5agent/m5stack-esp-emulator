#!/usr/bin/env python3
"""Local common helpers, copied byte-exact from the reviewed source API harness.

No CoreS3 firmware/profile constants or source composition helpers are copied.
"""
from __future__ import annotations
import hashlib,json,os,urllib.error,urllib.parse,urllib.request
from datetime import datetime,timezone

def need(condition,message):
    if not condition: raise RuntimeError(message)

def sha(data): return hashlib.sha256(data).hexdigest()

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def load(path):return json.loads(path.read_bytes())

def now():return datetime.now(timezone.utc).isoformat()

class HTTPRecorder:
    """Record actual urllib traffic; all reads return the original response bytes."""
    def __init__(self,directory):self.directory=directory;self.events=[];self.original=None
    def __enter__(self):
        self.directory.mkdir(parents=True,exist_ok=True);self.original=urllib.request.urlopen;urllib.request.urlopen=self.open;return self
    def __exit__(self,*args):
        urllib.request.urlopen=self.original;save(self.directory/'index.json',self.events)
    def open(self,request,*args,**kwargs):
        url=request.full_url if isinstance(request,urllib.request.Request) else str(request)
        method=request.get_method() if isinstance(request,urllib.request.Request) else 'GET'
        need(urllib.parse.urlparse(url).hostname in {'127.0.0.1','localhost','::1'},'runner records only the local Device Service')
        number=len(self.events);prefix=f'{number:05d}';body=getattr(request,'data',None)
        event={'at':now(),'method':method,'url':url,'path':urllib.parse.urlsplit(url).path,'query':urllib.parse.urlsplit(url).query,'request_file':prefix+'.request.raw','response_file':prefix+'.response.raw'}
        self.events.append(event);(self.directory/event['request_file']).write_bytes(body or b'')
        def record(data):
            target=self.directory/event['response_file']
            with target.open('ab') as stream:stream.write(data)
            event['response_sha256']=sha(target.read_bytes());event['response_size']=target.stat().st_size
            save(self.directory/'index.json',self.events)
            return data
        try:response=self.original(request,*args,**kwargs)
        except urllib.error.HTTPError as error:
            event['status']=error.code;real_read=error.read
            def audited_error_read(*read_args,**read_kwargs):return record(real_read(*read_args,**read_kwargs))
            error.read=audited_error_read
            raise
        event['status']=response.status
        class Response:
            def __enter__(self):response.__enter__();return self
            def __exit__(self,*values):return response.__exit__(*values)
            def __getattr__(self,name):return getattr(response,name)
            def read(self,*values,**options):return record(response.read(*values,**options))
        return Response()

def pid_gone(pid):
    try:os.kill(pid,0)
    except ProcessLookupError:return True
    except PermissionError:return False
    return False
