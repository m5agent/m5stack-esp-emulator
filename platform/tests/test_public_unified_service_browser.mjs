// Default: offline NOT RUN plan. Explicit --execute exercises only the new /
// workbench and one owned CoreS3+PIR native Preview; never the legacy sessions UI.
import assert from 'node:assert/strict';
import {createHash,randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {request as httpRequest} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {writeFileSync,openSync,closeSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const hash=value=>createHash('sha256').update(value).digest('hex');
export function unifiedServicePlan({tokenlessLocal=true}={}){return {kind:'public-unified-native-browser-plan',status:'NOT RUN',device:'cores3',unit:'pir',
  auth_mode:tokenlessLocal?'explicit-loopback-tokenless':'control-bearer',
  execute:tokenlessLocal
    ?'node platform/tests/test_public_unified_service_browser.mjs --execute --tokenless-local --service <owned-loopback-service:port> --out <new-.work-directory>'
    :'node platform/tests/test_public_unified_service_browser.mjs --execute --service <owned-loopback-service> --token-file <file> --out <new-.work-directory>',
  execute_bearer:'node platform/tests/test_public_unified_service_browser.mjs --execute --service <owned-loopback-service> --token-file <file> --out <new-.work-directory>',
  scope:['Canonical homepage only; actual service connection, device/Unit selection and UIFlow start.',
    'Run A/B, file import, public PIR driver/controller input, same-VM nonce, serial and displayed framebuffer.',
    'UI interrupt and UI stop, evidence ZIP, retained history, released owned PID/lease.'],
  boot_budget_ms:120000,per_run_budget_ms:120000,cleanup_budget_ms:45000,not_granted:['Other devices/Units','legacy session adoption','Pages/WASM','physical hardware','performance']};}

export function validateUnifiedServiceOptions(options){
  assert.ok(options.service&&options.out,'Explicit service/output required');
  assert.ok(options.tokenless_local===undefined||typeof options.tokenless_local==='boolean','Tokenless mode must be an explicit boolean');
  const tokenless=options.tokenless_local===true;
  assert.ok(tokenless?!options.token_file:options.token_file,'Choose --tokenless-local or an explicit --token-file');
  const base=new URL(options.service);assert.ok(base.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(base.hostname)
    &&base.pathname==='/'&&!base.search&&!base.hash&&!base.username&&!base.password,'Owned loopback HTTP service root required');
  assert.ok(!['8787','8830'].includes(base.port),'User testing services cannot be used by this harness');
  if(tokenless)assert.match(options.service,/^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\]):[1-9][0-9]{0,4}\/?$/,
    'Tokenless mode requires an explicit canonical owned loopback host and port');
  const output=resolve(options.out);assert.ok(output.startsWith(resolve(root,'.work')+'/'),'Output must be a new repository .work directory');
  return {base,output,tokenless};
}

// Explicit local CLI transport: Node fetch adds Sec-Fetch-Mode automatically.
// Browser request-context evidence below continues to come from Chromium.
export function localCliHttpRequest(url,{method='GET',headers={},body,signal}={}){
  const target=new URL(url);
  assert.ok(target.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(target.hostname)
    &&!['8787','8830'].includes(target.port)&&!target.username&&!target.password,'Owned local HTTP CLI target required');
  assert.ok(!Object.keys(headers).some(key=>/^(?:authorization|cookie|sec-fetch-)/i.test(key)),
    'Tokenless CLI transport must not supply authentication, cookies or Fetch Metadata');
  const payload=body===undefined?undefined:Buffer.from(body);
  return new Promise((resolve,reject)=>{
    const request=httpRequest(target,{method,signal,headers:{...headers,...(payload?{'Content-Length':String(payload.length)}:{})}},response=>{
      const chunks=[];response.on('data',chunk=>chunks.push(chunk));response.once('error',reject);
      response.once('aborted',()=>reject(new Error('Local CLI response aborted')));
      response.once('end',()=>{
        const responseHeaders=new Headers();for(let i=0;i<response.rawHeaders.length;i+=2)responseHeaders.append(response.rawHeaders[i],response.rawHeaders[i+1]);
        const status=response.statusCode;resolve({status,ok:status>=200&&status<300,headers:responseHeaders,bytes:Buffer.concat(chunks)});
      });
    });
    request.once('error',reject);request.end(payload);
  });
}

export function observerDeadline(promise,timeoutMs,code){
  let timer;
  return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>{
    const error=new Error(code);error.code=code;reject(error);
  },timeoutMs);})]).finally(()=>clearTimeout(timer));
}

export function sameOriginPreviewEvidence(request,origin){
  return request.request_origin===origin&&request.document_origin===origin&&request.origin_header===origin
    &&(request.fetch_site===null||request.fetch_site==='same-origin');
}

const sourcePaths=['platform/tests/test_public_unified_service_browser.mjs','tests/units/preview_controls_probe.py',
  'platform/web/index.html','platform/web/public.js','platform/web/public-service.js','platform/web/public-session-controller.js',
  'platform/web/public-service-program.js','platform/web/public-unit-assembly.js','platform/web/unit-panel.js',
  'platform/web/preview-client.js','platform/web/model-shell.js','platform/tools/serve.py','platform/tools/preview_request_context.py','platform/tools/device_service.py',
  'platform/tools/preview_service.py','platform/tools/unit_runtime.py','platform/units/runtime-profiles.json','platform/units/host-ports.json'];
async function fingerprints(){return Object.fromEntries(await Promise.all(sourcePaths.map(async path=>[path,hash(await readFile(resolve(root,path)))])));}
function processIdentity(pid,python){
  assert.ok(Number.isSafeInteger(pid)&&pid>0);
  return JSON.parse(execFileSync(python,['-c',`import ctypes,hashlib,json,pathlib,sys
p=int(sys.argv[1])
if sys.platform=='darwin':
 b=ctypes.create_string_buffer(4096)
 assert ctypes.CDLL('/usr/lib/libproc.dylib').proc_pidpath(p,b,len(b))>0
 f=pathlib.Path(b.value.decode())
else: f=(pathlib.Path('/proc')/str(p)/'exe').resolve()
print(json.dumps({'executable_name':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}))`,String(pid)],{encoding:'utf8'}));
}
function pidGone(pid){try{process.kill(pid,0);return false;}catch(error){if(error.code==='ESRCH')return true;throw error;}}
function program(phase,nonce,pins){
  assert.ok(['A','B'].includes(phase));
  assert.ok(['white','yellow'].every(k=>Number.isSafeInteger(pins[k])&&pins[k]>=0&&pins[k]<=48));
  const init=`import sys,time\nimport M5\nfrom unit import PIRUnit\nM5.begin()\npir=PIRUnit((${pins.white},${pins.yellow}))\n`;
  if(phase==='A')return init+`sys.modules['_m5_unified_web_probe']={'nonce':'${nonce}'}\nM5.Lcd.setBrightness(255)\nM5.Lcd.fillScreen(0xFF0000)\nprint('UNIFIED_A_${nonce}',int(pir.get_status()))\n`;
  return init+`assert sys.modules['_m5_unified_web_probe']['nonce']=='${nonce}'\nM5.Lcd.fillScreen(0x00FF00)\nprint('UNIFIED_B_READY_${nonce}')\nprevious=None\nwhile True:\n M5.update()\n value=int(pir.get_status())\n if value!=previous:\n  print('UNIFIED_B_PIR_${nonce}',value)\n  previous=value\n time.sleep_ms(25)\n`;
}

export async function execute(options){
  const {base,output,tokenless}=validateUnifiedServiceOptions(options),origin=base.origin;
  const token=tokenless?'':(await readFile(resolve(options.token_file),'utf8')).trim();assert.ok(tokenless||token,'Explicit control token required');
  await mkdir(output,{recursive:false});
  const python=options.python||process.env.M5_PYTHON||'python3',nonce=randomUUID().replaceAll('-','');
  const report={kind:'public-unified-native-browser',status:'FAIL',started_at:new Date().toISOString(),scope:unifiedServicePlan({tokenlessLocal:tokenless}),
    auth_mode:tokenless?'loopback-tokenless':'control-bearer',preview_requests:[],preview_request_errors:[],
    observer_http_transport:tokenless?'node:http explicit local CLI without Fetch Metadata':'Node fetch with explicit control Bearer',
    evidence_level:'virtual-device validation',hardware_validation:'NOT RUN',nonce,source_sha256:await fingerprints(),checks:[],runs:[],inputs:[],frames:[],http:[],page_errors:[],
    instrumentation:'Only append globalThis.__unifiedWorkbenchProbe={state} to hash-verified public.js; product methods/API/guest output unchanged.'};
  const check=(name,ok,details)=>{report.checks.push({name,ok,details});assert.ok(ok,name);console.log(name);};
  const save=(name,value)=>writeFile(resolve(output,name),JSON.stringify(value,null,2)+'\n');
  let deadline=Date.now()+120000,cleanupMode=false,browser,page,previewId,ownerEpoch,sessionId,session,creationIntent,zip,stopped;
  const browserTasks=[];
  async function drainBrowserTasks(required=false){
    try{await observerDeadline(Promise.allSettled(browserTasks),10000,'browser_tasks_observer_timeout');}
    catch(error){report.browser_tasks_observer_timeout=true;report.status='FAIL';process.exitCode=1;
      report.error ||= String(error?.stack||error);if(required)throw error;}
  }
  const left=(maximum=30000)=>{const n=cleanupMode?maximum:Math.min(maximum,deadline-Date.now());assert.ok(n>0,'120s phase budget exceeded');return Math.max(1,Math.ceil(n));};
  async function api(path,{method='GET',body,binary=false,headers={}}={}){
    if(tokenless)assert.ok(!Object.keys(headers).some(key=>key.toLowerCase()==='authorization'),'Tokenless helper cannot inject Authorization');
    const request={method,redirect:'error',credentials:'omit',signal:AbortSignal.timeout(left()),
      headers:{...(tokenless?{}:{Authorization:`Bearer ${token}`}),...(body===undefined?{}:{'Content-Type':'application/json'}),...headers},...(body===undefined?{}:{body:JSON.stringify(body)})};
    const response=await (tokenless?localCliHttpRequest:fetch)(origin+'/api/v1/'+path,request);
    const bytes=tokenless?response.bytes:Buffer.from(await response.arrayBuffer());report.http.push({path,method,status:response.status,bytes:bytes.length,sha256:hash(bytes)});
    assert.ok(response.ok,`${method} ${path}: HTTP${response.status} ${bytes.toString().slice(0,500)}`);
    return binary?{bytes,headers:Object.fromEntries(response.headers)}:JSON.parse(bytes);
  }
  async function until(read,predicate,timeout=30000){
    const end=Date.now()+left(timeout);for(;;){const value=await read();if(predicate(value))return value;if(Date.now()>=end)throw new Error('Observation deadline exceeded');await delay(100);}
  }
  async function sameVM(){
    const value=await api(`sessions/${sessionId}`);
    for(const k of ['session_id','pid','firmware_sha256','worker'])assert.deepEqual(value[k],session[k]);
    assert.equal(value.state,'running');return value;
  }
  async function observe(marker,offset=0){return until(()=>api(`sessions/${sessionId}/serial?offset=${offset}&limit=65536`),x=>x.data.includes(marker));}
  async function submit(name,source,{file=false,running=false}={}){
    deadline=Date.now()+120000;
    const admitted=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/v1/previews/${previewId}/runs`&&r.request().method()==='POST',{timeout:left()});
    if(file){await page.locator('#pythonFile').setInputFiles({name:'unified-import.py',mimeType:'text/x-python',buffer:Buffer.from(source)});
      await until(()=>page.locator('#pythonSource').inputValue(),v=>v===source);}
    else await page.locator('#pythonSource').fill(source);
    await page.locator('#pythonRunBtn').click({timeout:left(5000)});const reply=await admitted,receipt=await reply.json();
    assert.equal(reply.status(),202);assert.equal(receipt.preview_id,previewId);
    const run=await until(()=>api(`previews/${previewId}/runs/${receipt.run_id}`),x=>running?x.state==='running':['completed','failed','cancelled','unknown'].includes(x.state),120000);
    assert.equal(run.state,running?'running':'completed');for(const k of ['run_id','execution_id','revision_id'])assert.equal(run[k],receipt[k]);
    report.runs.push({name,source,source_sha256:hash(source),...run});await sameVM();
    if(!running)await until(()=>page.locator('#pythonRunBtn').isEnabled(),Boolean);
    check(name+'-actual-same-guest-run',true,{state:run.state,source_sha256:hash(source)});return run;
  }
  async function frame(name,color){
    const raw=await api(`sessions/${sessionId}/frame.png?max_age_ms=1`,{binary:true});await writeFile(resolve(output,name+'.png'),raw.bytes);
    const pixel=await page.evaluate(async base64=>{
      const bytes=Uint8Array.from(atob(base64),x=>x.charCodeAt(0)),image=await createImageBitmap(new Blob([bytes],{type:'image/png'}));
      const c=document.createElement('canvas');c.width=image.width;c.height=image.height;const g=c.getContext('2d');g.drawImage(image,0,0);
      const rgba=Array.from(g.getImageData(c.width-2,c.height-2,1,1).data);image.close();return {width:c.width,height:c.height,rgba};
    },raw.bytes.toString('base64'));
    check(name+'-actual-guest-color',pixel.rgba[color]>220&&pixel.rgba[(color+1)%3]<20&&pixel.rgba[(color+2)%3]<20,pixel);
    await until(()=>page.evaluate(expected=>{const d=globalThis.__unifiedWorkbenchProbe?.state.shell?.display,p=d?.getPixel(d.width-2,d.height-2);
      return !!p&&expected.slice(0,3).every((c,i)=>c===p[i]);},pixel.rgba),Boolean);
    report.frames.push({name,bytes:raw.bytes.length,sha256:hash(raw.bytes),...pixel,headers:raw.headers});check(name+'-same-frame-on-main-model',true);
  }
  function verifyZip(){
    assert.ok(zip?.length,'Evidence ZIP required');
    const input=resolve(output,'zip-verification-input.json');
    writeFileSync(input,JSON.stringify({bytes:zip.toString('base64'),expected:{session_id:sessionId,device_id:'cores3',firmware_sha256:session.firmware_sha256,pid:session.pid,
      runs:report.runs.map(x=>({execution_id:x.execution_id,revision_id:x.revision_id}))}}),{flag:'wx',mode:0o600});
    const fd=openSync(input,'r');
    try{return JSON.parse(execFileSync(python,['-B','tests/units/preview_controls_probe.py','zip','--device','cores3'],
      {cwd:root,encoding:'utf8',maxBuffer:1024*1024,timeout:10000,stdio:[fd,'pipe','pipe']}));}
    finally{closeSync(fd);}
  }
  try{
    const capacity=await api('capacity');assert.equal(capacity.active_sessions,0,'Dedicated service must begin with no active sessions');
    const devices=await api('devices'),core=devices.devices.find(x=>x.device_id==='cores3');assert.ok(core?.creatable&&core.program_modes.includes('uiflow-live'));
    const modules=options.node_modules||process.env.M5_WASM_NODE_MODULES||resolve(root,'platform/tests/node_modules');
    const {chromium}=await import(pathToFileURL(resolve(modules,'playwright/index.mjs')));
    browser=await chromium.launch({headless:true,...(options.chrome?{executablePath:options.chrome}:{}),args:['--use-gl=angle','--use-angle=metal','--enable-webgl','--ignore-gpu-blocklist']});
    report.browser_version=browser.version();page=await browser.newPage({viewport:{width:1440,height:1100}});page.setDefaultTimeout(5000);
    page.on('pageerror',error=>report.page_errors.push(error.message));
    page.on('request',request=>{const u=new URL(request.url());
      if(u.pathname==='/api/v1/previews'&&request.method()==='POST')creationIntent={body:request.postDataJSON(),key:request.headers()['idempotency-key']};
      if(tokenless&&request.method()==='POST'&&/^\/api\/v1\/previews(?:\/|$)/.test(u.pathname))browserTasks.push((async()=>{
        const headers=await request.allHeaders(),documentOrigin=new URL(request.frame().url()).origin;
        const evidence={path:u.pathname,method:request.method(),authorization_present:Object.hasOwn(headers,'authorization'),
          request_origin:u.origin,document_origin:documentOrigin,origin_header:headers.origin??null,fetch_site:headers['sec-fetch-site']??null};
        report.preview_requests.push({...evidence,same_origin:sameOriginPreviewEvidence(evidence,origin)});
      })().catch(error=>report.preview_request_errors.push(String(error?.message||error))));
      if(/\.wasm$/.test(u.pathname))report.unexpected_browser_wasm=true;
      if(u.pathname==='/platform/web/sessions.html')report.legacy_sessions_page_requested=true;
    });
    page.on('response',response=>{const path=new URL(response.url()).pathname;
      if(path==='/api/v1/previews'&&response.request().method()==='POST')browserTasks.push((async()=>{const r=await response.json();if(response.ok()&&r.preview_id){previewId=r.preview_id;ownerEpoch=r.owner_epoch;}})());
      if(sessionId&&path===`/api/v1/sessions/${sessionId}/evidence`&&response.request().method()==='GET')browserTasks.push((async()=>{
        report.network_evidence={status:response.status(),headers:await response.allHeaders()};
        if(response.ok()){
          report.ui_evidence_request=true;
          try{const bytes=Buffer.from(await observerDeadline(response.body(),5000,'network_body_observer_timeout'));await writeFile(resolve(output,'network-evidence-before-stop.zip'),bytes);
            Object.assign(report.network_evidence,{bytes:bytes.length,sha256:hash(bytes)});
          }catch(error){report.network_evidence.body_observation_error=String(error?.message||error);
            if(error?.code==='network_body_observer_timeout')report.network_evidence.network_body_observer_timeout=true;}
        }
      })());
    });
    await page.route('**/platform/web/public.js*',async route=>{const response=await route.fetch(),bytes=await response.body();
      assert.equal(hash(bytes),report.source_sha256['platform/web/public.js']);
      await route.fulfill({response,body:bytes.toString()+'\nglobalThis.__unifiedWorkbenchProbe={state};\n'});
    });
    const entry=await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:left()});assert.equal(hash(await entry.body()),report.source_sha256['platform/web/index.html']);
    await page.waitForFunction(()=>document.querySelector('#deviceMount')?.dataset.deviceId==='cores3'&&globalThis.__unifiedWorkbenchProbe?.state.shell,{}, {timeout:left()});
    if(!await page.locator('#serviceUrl').isVisible())await page.locator('#serviceConnection > summary').click();
    await page.locator('#serviceUrl').fill(origin);
    if(tokenless)assert.equal(await page.locator('#serviceToken').inputValue(),'','Tokenless run must begin with an empty UI token');
    else await page.locator('#serviceToken').fill(token);
    await page.locator('#connectServiceBtn').click();
    await until(()=>page.evaluate(()=>globalThis.__unifiedWorkbenchProbe.state.serviceDevices.some(x=>x.device_id==='cores3'&&x.program_modes?.includes('uiflow-live'))),Boolean);
    if(!await page.locator('#runtimeMode').isVisible())await page.locator('.advanced-options > summary').click();
    await page.locator('#runtimeMode').selectOption('service');await page.locator('#referenceExample').selectOption('uiflow');
    await page.locator('#unitModelSelect option[value="pir"]').waitFor({state:'attached',timeout:left()});await page.locator('#unitModelSelect').selectOption('pir');
    await until(()=>page.evaluate(()=>globalThis.__unifiedWorkbenchProbe.state.picker.attachments('cores3').some(x=>x.unit_id==='pir')),Boolean);
    const creation=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/previews'&&r.request().method()==='POST',{timeout:left()});
    await page.locator('#startBtn').click();const created=await creation,receipt=await created.json();if(receipt.preview_id){previewId=receipt.preview_id;ownerEpoch=receipt.owner_epoch;}
    assert.equal(created.status(),202);assert.equal(receipt.request.device_id,'cores3');assert.equal(receipt.request.units[0].unit_id,'pir');
    deadline=Date.now()+120000;
    const preview=await until(()=>api(`previews/${previewId}`),p=>['ready','failed','closed'].includes(p.state),120000);assert.equal(preview.state,'ready');sessionId=preview.session_id;
    session=await api(`sessions/${sessionId}`);assert.equal(session.device_id,'cores3');assert.equal(session.management_binding.preview_id,previewId);
    report.session=session;report.preview=preview;report.runtime=processIdentity(session.pid,python);
    await until(()=>page.locator('#pythonRunBtn').isEnabled(),Boolean);check('main-ui-created-owned-native-cores3-with-pir',true);
    const attached=session.units.find(x=>x.unit_id==='pir');assert.ok(attached);report.attachment=attached;
    await submit('run-A',program('A',nonce,attached.pins));await observe('UNIFIED_A_'+nonce);
    await until(()=>page.locator('#pythonOutput').textContent(),text=>text.includes('UNIFIED_A_'+nonce));await frame('program-a-frame',0);
    const running=await submit('run-B',program('B',nonce,attached.pins),{running:true});await observe('UNIFIED_B_READY_'+nonce);
    const field=page.locator('#runtimeUnitPanel [data-input-field="motion"]');await until(()=>field.isEnabled(),Boolean);
    for(const motion of [true,false]){
      const offset=(await api(`sessions/${sessionId}/serial?limit=65536`)).next_offset;
      const response=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/v1/previews/${previewId}/input`&&r.request().method()==='POST',{timeout:left()});
      await field.setChecked(motion);const reply=await response,body=await reply.json(),request=reply.request().postDataJSON();assert.equal(reply.status(),200);
      assert.equal(request.unit_input.id,attached.id);assert.equal(request.unit_input.values.motion,motion);
      for(const k of ['preview_id','run_id','execution_id','revision_id'])assert.equal(body[k],running[k]);
      await observe(`UNIFIED_B_PIR_${nonce} ${Number(motion)}`,offset);
      const qom=await api(`sessions/${sessionId}/qom?path=${encodeURIComponent('/machine/units/'+attached.id)}&property=motion`);assert.equal(qom.value,motion);
      const units=await api(`sessions/${sessionId}/units`);assert.equal(units.units.find(x=>x.id===attached.id).properties.motion,motion);
      report.inputs.push({request,response:body,qom,units});check('pir-ui-controller-original-driver-'+motion,true);
    }
    await frame('program-b-frame',1);await until(()=>page.locator('#pythonInterruptBtn').isEnabled(),Boolean);await page.locator('#pythonInterruptBtn').click();
    const interrupted=await until(()=>api(`previews/${previewId}/runs/${running.run_id}`),r=>['cancelled','interrupted','failed','unknown'].includes(r.state));
    assert.ok(['cancelled','interrupted'].includes(interrupted.state));report.interrupted=interrupted;
    await until(()=>page.locator('#pythonRunBtn').isEnabled(),Boolean);check('main-ui-interrupt-confirmed',true);
    const imported=`import sys,math\nassert sys.modules['_m5_unified_web_probe']['nonce']=='${nonce}'\nprint('UNIFIED_IMPORT_${nonce}',int(math.sqrt(81)),'你好')\n`;
    await submit('import-file',imported,{file:true});await observe(`UNIFIED_IMPORT_${nonce} 9 你好`);
    await until(()=>page.locator('#pythonOutput').textContent(),text=>text.includes(`UNIFIED_IMPORT_${nonce} 9 你好`));
    await sameVM();await page.screenshot({path:resolve(output,'unified-main.png'),fullPage:true});
    const stoppedRunHandle=await page.evaluateHandle(()=>globalThis.__unifiedWorkbenchProbe.state.run);
    cleanupMode=true;await page.locator('#stopBtn').click();await until(()=>api(`previews/${previewId}`),p=>p.state==='closed');
    stopped=await until(()=>api(`sessions/${sessionId}`),s=>s.state==='stopped'&&!s.stop_pending&&s.worker?.lease_active===false);
    const productEvidence=await stoppedRunHandle.evaluate(async run=>{
      const blob=run.python.lastEvidence;if(!blob)return {present:false};const bytes=new Uint8Array(await blob.arrayBuffer());let raw='';
      for(let i=0;i<bytes.length;i+=16384)raw+=String.fromCharCode(...bytes.subarray(i,i+16384));
      return {present:true,size:blob.size,type:blob.type,base64:btoa(raw)};
    });await stoppedRunHandle.dispose();
    assert.ok(productEvidence.present&&productEvidence.size>0,'Product UI stop must retain a nonempty evidence Blob');
    zip=Buffer.from(productEvidence.base64,'base64');assert.equal(zip.length,productEvidence.size);
    report.product_evidence={present:true,size:productEvidence.size,type:productEvidence.type,sha256:hash(zip)};
    await writeFile(resolve(output,'evidence-before-stop.zip'),zip);
    await drainBrowserTasks(true);assert.ok(report.ui_evidence_request);
    assert.equal(Number(report.network_evidence.headers['content-length']),zip.length,'Product Blob must match actual evidence response Content-Length');
    if(report.network_evidence.bytes>0)assert.equal(report.network_evidence.sha256,hash(zip),'Observed nonempty network body must match product Blob');
    report.zip=verifyZip();
    assert.equal(stopped.flash_retained,false);await until(()=>Promise.resolve(pidGone(session.pid)),Boolean);report.stopped=stopped;
    const after=await api('capacity');assert.equal(after.active_sessions,0);assert.equal(after.worker.active_lease_count,0);report.cleanup={ui_stop:true,pid_gone:true,capacity:after};
    check('ui-stop-zip-history-pid-and-lease-cleanup',true);
    assert.equal(report.page_errors.length,0);assert.ok(!report.unexpected_browser_wasm&&!report.legacy_sessions_page_requested);
    if(tokenless){
      assert.equal(report.preview_request_errors.length,0);
      assert.ok(report.preview_requests.some(request=>request.path==='/api/v1/previews'),'Actual UI Preview creation POST required');
      check('tokenless-preview-posts-no-authorization-and-same-origin',report.preview_requests.every(request=>!request.authorization_present&&request.same_origin),
        {post_count:report.preview_requests.length});
    }
    assert.deepEqual(await fingerprints(),report.source_sha256);check('same-source-new-homepage-native-only',true);report.status='PASS';
  }catch(error){report.error=String(error?.stack||error);process.exitCode=1;}
  finally{
    cleanupMode=true;
    if(page)await page.screenshot({path:resolve(output,report.status==='PASS'?'stopped-main.png':'failure.png'),fullPage:true}).catch(()=>{});
    if(!stopped&&(previewId||creationIntent)){
      try{
        if(!previewId){assert.ok(creationIntent.key);const recovered=await api('previews',{method:'POST',body:creationIntent.body,headers:{'Idempotency-Key':creationIntent.key}});previewId=recovered.preview_id;ownerEpoch=recovered.owner_epoch;}
        const p=await api(`previews/${previewId}`);sessionId ||= p.session_id;
        if(sessionId&&!zip){const captured=await api(`sessions/${sessionId}/evidence`,{binary:true});zip=captured.bytes;await writeFile(resolve(output,'fallback-evidence.zip'),zip);}
      }catch(error){report.cleanup_capture_error=String(error?.message||error);}
      try{
        if(previewId&&ownerEpoch){await api(`previews/${previewId}/close`,{method:'POST',body:{expected_owner_epoch:ownerEpoch}});
          await until(()=>api(`previews/${previewId}`),p=>p.state==='closed',45000);if(sessionId)report.fallback_stopped=await api(`sessions/${sessionId}`);}
      }catch(error){report.cleanup_error=String(error?.stack||error);}
    }
    await drainBrowserTasks();if(browser){await browser.close();report.browser_disconnected=!browser.isConnected();}
    report.finished_at=new Date().toISOString();await save('report.json',report);
    console.log(JSON.stringify({status:report.status,checks:report.checks.length,output,error:report.error||null}));
  }
  return report;
}

const isMain=process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url);
if(isMain){const options={execute:false},args=process.argv.slice(2);
  for(let i=0;i<args.length;i++){
    if(args[i]==='--execute'){assert.equal(options.execute,false);options.execute=true;continue;}
    if(args[i]==='--tokenless-local'){assert.ok(!Object.hasOwn(options,'tokenless_local'));options.tokenless_local=true;continue;}
    assert.ok(['--service','--token-file','--out','--chrome','--node-modules','--python'].includes(args[i]),'Unknown argument');
    const key=args[i].slice(2).replaceAll('-','_');assert.ok(args[i+1]&&!args[i+1].startsWith('--')&&!Object.hasOwn(options,key));options[key]=args[++i];
  }
  if(!options.execute)console.log(JSON.stringify(unifiedServicePlan(),null,2));else await execute(options);
}
