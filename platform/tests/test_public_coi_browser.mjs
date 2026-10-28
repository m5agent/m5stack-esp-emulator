// Real browser/Service Worker/shared-memory contract. No firmware or device run.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {resolve,dirname,extname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {parseArgs} from 'node:util';

const {values:args}=parseArgs({options:{'out-dir':{type:'string'}}});
assert.ok(args['out-dir'],'--out-dir must be a new ignored evidence directory');
const out=resolve(args['out-dir']);await mkdir(out,{recursive:false});
const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const {chromium}=process.env.M5_WASM_NODE_MODULES
  ? createRequire(resolve(process.env.M5_WASM_NODE_MODULES,'_resolver.cjs'))('playwright')
  : await import('playwright');
const prefix='/showcase/';
const sourcePaths=['platform/web/public-coi.js','platform/web/public-coi-serviceworker.js','platform/web/vendor/coi-serviceworker/coi-serviceworker.js','platform/web/vendor/coi-serviceworker/LICENSE','platform/tests/test_public_coi_browser.mjs'];
const report={status:'FAIL',category:'COI bootstrap browser contract; no guest',firmware_execution:'NOT RUN',hardware_execution:'NOT RUN',checks:{},navigation_responses:[],workers:[],errors:[],source_sha256:{}};
for(const name of sourcePaths)report.source_sha256[name]=createHash('sha256').update(await readFile(resolve(repo,name))).digest('hex');
const html=`<!doctype html><meta charset="utf-8"><link rel="icon" href="data:,"><title>COI project-scope contract</title>
<script>const loads=JSON.parse(sessionStorage.getItem('test-coi-loads')||'[]');loads.push({isolated:crossOriginIsolated,controlled:!!navigator.serviceWorker.controller,url:location.href});sessionStorage.setItem('test-coi-loads',JSON.stringify(loads));globalThis.probe={loads,errors:[]};</script>
<script type="module">import {ensurePublicIsolation} from '${prefix}platform/web/public-coi.js';(async()=>{probe.result=await ensurePublicIsolation({root:new URL('${prefix}',location.origin)});if(probe.result.isolated){const frame=document.createElement('iframe');frame.allow='cross-origin-isolated';frame.src='${prefix}frame.html';window.addEventListener('message',event=>{if(event.source===frame.contentWindow&&event.origin===location.origin)probe.frame=event.data;});document.body.append(frame);}})().catch(error=>probe.errors.push({code:error.code,message:error.message}));</script>`;
const frame=`<!doctype html><meta charset="utf-8"><script>
const memory=new WebAssembly.Memory({initial:1,maximum:1,shared:true});Atomics.store(new Int32Array(memory.buffer),0,71);
const worker=new Worker('${prefix}memory-worker.js');worker.onmessage=event=>{parent.postMessage({isolated:crossOriginIsolated,shared:memory.buffer instanceof SharedArrayBuffer,value:Atomics.load(new Int32Array(memory.buffer),0),worker:event.data},location.origin);worker.terminate();};worker.postMessage(memory);
</script>`;
const memoryWorker=`onmessage=event=>{const memory=event.data;Atomics.add(new Int32Array(memory.buffer),0,1);postMessage({isolated:crossOriginIsolated,shared:memory.buffer instanceof SharedArrayBuffer,value:Atomics.load(new Int32Array(memory.buffer),0)});};`;
const server=createServer(async(request,response)=>{
  try {
    const url=new URL(request.url,'http://localhost');let data,type='text/javascript';
    if([prefix,prefix+'platform/web/index.html'].includes(url.pathname)){data=html;type='text/html';}
    else if(url.pathname===prefix+'frame.html'){data=frame;type='text/html';}
    else if(url.pathname===prefix+'memory-worker.js')data=memoryWorker;
    else if(url.pathname===prefix+'coi-serviceworker.js')data=await readFile(resolve(repo,'platform/web/public-coi-serviceworker.js'));
    else if(url.pathname.startsWith(prefix+'platform/web/')){
      const path=resolve(repo,url.pathname.slice(prefix.length));assert.ok(path.startsWith(resolve(repo,'platform/web')+sep));
      data=await readFile(path);type=extname(path)==='.json'?'application/json':'text/javascript';
    } else if(url.pathname==='/neighbor/'){data='<!doctype html><title>outside project</title>';type='text/html';}
    else{response.writeHead(404).end();return;}
    // Deliberately no COOP/COEP/CORP or Service-Worker-Allowed headers.
    response.writeHead(200,{'Content-Type':type,'Cache-Control':'no-store'}).end(data);
  }catch{response.writeHead(404).end();}
});
let browserServer,browser,context;
try {
  await new Promise((done,bad)=>{server.once('error',bad);server.listen(0,'127.0.0.1',done);});
  const port=server.address().port;assert.ok(![8787,8830].includes(port));report.port=port;
  const origin=`http://127.0.0.1:${port}`;
  const response=await fetch(origin+prefix);assert.equal(response.headers.get('Cross-Origin-Opener-Policy'),null);assert.equal(response.headers.get('Cross-Origin-Embedder-Policy'),null);report.checks.server_has_no_isolation_headers=true;
  const executablePath=process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||process.env.M5_WASM_CHROME;
  browserServer=await chromium.launchServer({headless:true,...(executablePath?{executablePath}:{})});browser=await chromium.connect(browserServer.wsEndpoint());report.browser=browser.version();report.browser_pid=browserServer.process().pid;
  context=await browser.newContext();const page=await context.newPage();page.setDefaultTimeout(25000);
  const workerClosures=[];
  page.on('pageerror',error=>report.errors.push(error.message));
  page.on('worker',worker=>{const row={url:worker.url(),closed:false};report.workers.push(row);workerClosures.push(worker.waitForEvent('close',{timeout:25000}).then(()=>{row.closed=true;}));});
  page.on('response',async value=>{if(value.request().isNavigationRequest()){const headers=await value.allHeaders();report.navigation_responses.push({url:value.url(),from_service_worker:value.fromServiceWorker(),COOP:headers['cross-origin-opener-policy']||null,COEP:headers['cross-origin-embedder-policy']||null});}});
  const target=origin+prefix+'?device=cores3&autostart=0#screen';await page.goto(target,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>globalThis.probe?.frame||globalThis.probe?.errors.length);
  const initial=await page.evaluate(()=>probe);report.initial=initial;assert.deepEqual(initial.errors,[]);
  assert.equal(initial.loads.length,2);assert.equal(initial.loads[0].isolated,false);assert.equal(initial.loads[0].controlled,false);assert.equal(initial.loads[1].isolated,true);assert.equal(initial.loads[1].controlled,true);assert.equal(page.url(),target);report.checks.first_control_then_single_reload_preserves_URL=true;
  assert.deepEqual(initial.frame,{isolated:true,shared:true,value:72,worker:{isolated:true,shared:true,value:72}});report.checks.same_origin_iframe_and_real_shared_memory_worker=true;
  const registrations=await page.evaluate(async()=>({registrations:(await navigator.serviceWorker.getRegistrations()).map(r=>({scope:r.scope,script:r.active?.scriptURL})),controller:navigator.serviceWorker.controller.scriptURL}));
  assert.deepEqual(registrations,{registrations:[{scope:origin+prefix,script:origin+prefix+'coi-serviceworker.js'}],controller:origin+prefix+'coi-serviceworker.js'});report.registrations=registrations;report.checks.project_root_scope_without_allowed_header=true;
  await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>globalThis.probe?.frame);const repeat=await page.evaluate(()=>probe);assert.equal(repeat.loads.length,3);assert.equal(repeat.result.isolated,true);assert.deepEqual(repeat.errors,[]);report.checks.revisit_needs_no_automatic_reload=true;
  await page.goto(origin+prefix+'platform/web/index.html',{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>globalThis.probe?.frame);assert.equal(await page.evaluate(()=>crossOriginIsolated),true);report.checks.nested_entry_keeps_project_scope=true;
  await Promise.all(workerClosures);assert.ok(report.workers.length>=3&&report.workers.every(w=>w.closed));report.checks.owned_test_workers_closed_before_browser_cleanup=true;
  await page.goto(origin+'/neighbor/',{waitUntil:'domcontentloaded'});assert.deepEqual(await page.evaluate(()=>({isolated:crossOriginIsolated,controlled:!!navigator.serviceWorker.controller})),{isolated:false,controlled:false});report.checks.neighboring_project_not_controlled=true;
  assert.ok(report.navigation_responses.some(r=>!r.from_service_worker&&r.COOP===null&&r.COEP===null));assert.ok(report.navigation_responses.some(r=>r.from_service_worker&&r.COOP==='same-origin'&&r.COEP==='require-corp'));report.checks.actual_SW_navigation_headers=true;
  assert.deepEqual(report.errors,[]);report.status='PASS';
}catch(error){report.failure=error.stack;process.exitCode=1;}
finally {
  try {if(context)await context.close();if(browser)await browser.close();if(browserServer)await browserServer.close();}
  catch(error){report.status='FAIL';report.cleanup_error=String(error);process.exitCode=1;if(browserServer)await browserServer.kill().catch(()=>{});}
  finally {
    await new Promise(done=>server.close(done));report.checks.owned_server_closed=!server.listening;
    if(browserServer)report.checks.owned_browser_PID_gone=browserServer.process().exitCode!==null||browserServer.process().signalCode!==null;
    report.finished_at=new Date().toISOString();await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  }
}
console.log(JSON.stringify({status:report.status,checks:report.checks,failure:report.failure}));
