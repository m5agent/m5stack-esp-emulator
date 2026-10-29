// Opt-in real StackChan power path. No iframe/window references are retained.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {capturePublicQemuProvenance} from './public_qemu_artifacts.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';
const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
if(!process.env.M5_PUBLIC_SITE){console.log('SKIP: explicit M5_PUBLIC_SITE export required');process.exit(0);}
assert.ok(process.env.M5_STACKCHAN_WASM_SHA256&&process.env.M5_STACKCHAN_POWER_IMAGE&&process.env.M5_STACKCHAN_POWER_SHA256,'Explicit WASM and firmware image/SHA required');
const site=resolve(process.env.M5_PUBLIC_SITE),expectedWasm=process.env.M5_STACKCHAN_WASM_SHA256,image=resolve(process.env.M5_STACKCHAN_POWER_IMAGE),imageSha=process.env.M5_STACKCHAN_POWER_SHA256;
assert.match(expectedWasm,/^[a-f0-9]{64}$/);assert.match(imageSha,/^[a-f0-9]{64}$/);
const out=resolve(process.env.M5_STACKCHAN_OUT||resolve(repo,'.work/stackchan-power-guest'));
assert.ok(out.startsWith(resolve(repo,'.work')+'/'),'Raw guest evidence belongs in ignored .work');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
assert.equal(sha(await readFile(image)),imageSha,'Fixture image SHA changed');
await mkdir(out,{recursive:false});await writeFile(resolve(out,'harness.mjs'),await readFile(new URL(import.meta.url)));
const modules=process.env.M5_WASM_NODE_MODULES||resolve(repo,'platform/tests/node_modules');
const {chromium}=await import(pathToFileURL(resolve(modules,'playwright/index.mjs')));
const hardwareGPU=process.env.M5_WASM_GPU==='hardware';
const manifestBytes=await readFile(resolve(site,'public-site-manifest.json')),manifest=JSON.parse(manifestBytes),base=manifest.base_path;
if(process.env.M5_STACKCHAN_MANIFEST_SHA256)assert.equal(sha(manifestBytes),process.env.M5_STACKCHAN_MANIFEST_SHA256,'Unexpected export manifest');
assert.equal(manifest.assets.find(v=>v.path==='platform/runtime/qemu/qemu-system-xtensa.wasm')?.sha256,expectedWasm,'Export declares a different WASM');
const checks=[],errors=[],requests=[],blocked=[];
const report={kind:'stackchan-arduino-motion-reset-power-release-normal-DOM-smoke',started_at:new Date().toISOString(),checks,errors,blocked,requests,
 export_manifest_sha256:createHash('sha256').update(manifestBytes).digest('hex'),publication_eligible:manifest.publication_eligible,harness_sha256:createHash('sha256').update(await readFile(new URL(import.meta.url))).digest('hex'),instrumentation:'Production files are served unchanged. ModelDeviceShell.create and original runtime callbacks are wrapped only from page.evaluate; iframe removal follows the unmodified production method with no hold or override; final zero CDP targets and no DOM iframe are required.'};
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.wasm':'application/wasm','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2'};
let server,browser,page,targets;
function check(name,ok,detail){checks.push({name,ok,detail});console.log(name,ok?'PASS':'FAIL');assert.ok(ok,name);}
try {
 report.provenance=await capturePublicQemuProvenance({repo,site,testScript:'platform/tests/test_stackchan_power_guest.mjs'});
 server=createServer(async(req,res)=>{try{const path=new URL(req.url,'http://localhost').pathname;if(!path.startsWith(base)){res.writeHead(404).end();return;}const file=resolve(site,decodeURIComponent(path.slice(base.length))||'index.html');if(!file.startsWith(site+'/')){res.writeHead(403).end();return;}res.writeHead(200,{'content-type':mime[extname(file)]||'application/octet-stream','cache-control':'no-cache'});res.end(await readFile(file));}catch{res.writeHead(404).end();}});
 await new Promise(yes=>server.listen(0,'127.0.0.1',yes));
 const origin=`http://127.0.0.1:${server.address().port}${base}`;report.url=origin;
 browser=await chromium.launch({headless:true,...(process.env.M5_WASM_CHROME?{executablePath:process.env.M5_WASM_CHROME}:{}),args:['--enable-webgl','--use-gl=angle',...(hardwareGPU?['--use-angle=metal','--ignore-gpu-blocklist']:['--use-angle=swiftshader'])]});report.browser=browser.version();report.hardware_gpu=hardwareGPU;
 targets=await observeWorkerTargets(browser);
 page=await browser.newPage({viewport:{width:1200,height:900}});
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push({url:r.url(),method:r.method()}));
 await page.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>{blocked.push(route.request().url());return route.abort('blockedbyclient');});
 await page.goto(origin,{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>crossOriginIsolated,{}, {timeout:45000});
 await page.waitForFunction(()=>document.querySelector('#deviceMount')?.dataset.deviceId==='cores3',{}, {timeout:45000});
 await page.evaluate(async origin=>{
  const {ModelDeviceShell}=await import(new URL('platform/web/model-shell.js?v=20261026h',origin));
  const create=ModelDeviceShell.create;
  ModelDeviceShell.create=async function(...args){const shell=await create.apply(this,args);if(args[1].id==='stackchan')globalThis.smokeShell=shell;return shell;};
  const {PublicQemuRuntime}=await import(new URL('platform/web/public-qemu-runtime.js',origin));
  const start=PublicQemuRuntime.prototype.start;
  PublicQemuRuntime.prototype.start=function(...args){
   if(args[0].device==='stackchan'){
    const runtime=this,err=this.onError,onDeviceState=this.onDeviceState;
    globalThis.smokeRun={runtime,errors:[],samples:[]};
    this.onError=e=>{smokeRun.errors.push(e.message);err(e);};
    this.onDeviceState=state=>{onDeviceState(state);const shell=globalThis.smokeShell;
     smokeRun.samples.push({wall_ms:performance.now(),state:structuredClone(state),yaw:shell.model.find('yaw','joint').getState(),pitch:shell.model.find('pitch','joint').getState()});
     if(smokeRun.samples.length>1200)smokeRun.samples.shift();};
   }
   return start.apply(this,args);
  };
 },origin);
 await page.locator('button[data-device-id="stackchan"]').click();
 await page.waitForFunction(()=>globalThis.smokeShell?.device.id==='stackchan'&&document.querySelector('#deviceMount')?.dataset.deviceId==='stackchan',{}, {timeout:45000});
 await page.locator('.advanced-options > summary').click();
 await page.locator('#runtimeMode').selectOption('browser');
 await page.locator('input[name="firmwareSource"][value="local"]').check();
 await page.locator('#firmwareFile').setInputFiles(image);
 await page.locator('#firmwareSha').fill(imageSha);
 await page.locator('#startBtn').click();
 await page.waitForFunction(()=>globalThis.smokeRun&&/phase=ready/.test(smokeRun.runtime.serial||'')&&smokeRun.samples.length>1,{}, {timeout:180000});
 check('exact-final-WASM-and-firmware',await page.evaluate(({wasm,image})=>smokeRun.runtime.receipt.wasmSha256===wasm&&smokeRun.runtime.receipt.firmwareSha256===image,{wasm:expectedWasm,image:imageSha}));
 console.log('ready and first QOM samples arrived');
 const first=await page.evaluate(()=>{smokeRun.samples=[];return {session:smokeRun.runtime.sessionId,generation:smokeRun.runtime.generation};});
 await page.evaluate(()=>smokeShell.model.button('touch-1').press('real-motion-smoke'));
 await page.waitForTimeout(700);
 await page.evaluate(()=>smokeShell.model.button('touch-1').release('real-motion-smoke'));
 await page.waitForTimeout(6000);
 report.motion=await page.evaluate(()=>({samples:smokeRun.samples,receipt:smokeRun.runtime.receipt,serial:smokeRun.runtime.serial,errors:smokeRun.errors}));
 const sample=report.motion.samples;
 check('same-guest-real-servo-QOM-samples',sample.length>=2,{samples:sample.length});
 check('present-ticks-match-model-joints',sample.every(row=>Math.abs(row.yaw.angleDeg-(row.state.servos[0].present_position-460)*5/16)<1e-9&&Math.abs(row.pitch.angleDeg-Math.max(0,Math.min(90,(row.state.servos[1].present_position-620)*5/16)))<1e-9),{samples:sample.length});
 const ranges=[0,1].map(axis=>{const values=sample.map(r=>r.state.servos[axis].present_position);return Math.max(...values)-Math.min(...values);});
 check('real-servo-position-changes-at-least-50-ticks',Math.max(...ranges)>=50,{ranges});
 await page.screenshot({path:resolve(out,'motion.png'),fullPage:true});
 report.before_reset=await page.evaluate(()=>{const r=smokeRun.runtime;r.iframe.dataset.smokeResetIdentity=crypto.randomUUID();return {iframe_identity:r.iframe.dataset.smokeResetIdentity,session:r.sessionId,generation:r.generation,resets:r.machineEvents.filter(e=>e.event==='RESET').length,frame:r.lastFrame?.sequence};});
 await page.evaluate(()=>smokeRun.runtime.reset());
 await page.waitForFunction(before=>smokeRun.runtime.machineEvents.filter(e=>e.event==='RESET').length>before,report.before_reset.resets,{timeout:30000});
 await page.waitForFunction(()=>{const r=smokeRun.runtime;return r.status==='running'&&/phase=ready/.test(r.serial.slice(r.readySerialOffset));},{},{timeout:180000});
 report.after_reset=await page.evaluate(identity=>{const r=smokeRun.runtime;return {same_iframe:r.iframe?.dataset.smokeResetIdentity===identity,session:r.sessionId,generation:r.generation,resets:r.machineEvents.filter(e=>e.event==='RESET').length,serial:r.serial.slice(r.readySerialOffset),events:r.machineEvents};},report.before_reset.iframe_identity);
 check('hardware-reset-keeps-session-and-iframe-and-reaches-fresh-ready',report.after_reset.same_iframe&&report.after_reset.session===first.session&&report.after_reset.generation===first.generation&&report.after_reset.resets>report.before_reset.resets,report.after_reset);
 const beforePower=await page.evaluate(()=>smokeRun.runtime.inputs.length);
 await page.evaluate(()=>smokeShell.model.button('power').press('real-motion-smoke'));
 await page.waitForFunction(n=>smokeRun.runtime.inputs.slice(n).some(v=>v.type==='button'&&v.id==='p'&&v.down===true),beforePower,{timeout:5000});
 report.power_hold=await page.evaluate(()=>({acknowledged_down:smokeRun.runtime.inputs.at(-1),start_wall_ms:performance.now(),pressed:smokeShell.model.button('power').getState().pressed}));
 await page.waitForTimeout(6000);
 report.power_release=await page.evaluate(()=>{const end_wall_ms=performance.now();smokeShell.model.button('power').release('real-motion-smoke');return {end_wall_ms,pressed:smokeShell.model.button('power').getState().pressed};});
 check('actual-six-second-model-hold-and-release',report.power_hold.pressed&&report.power_release.pressed===false&&report.power_release.end_wall_ms-report.power_hold.start_wall_ms>=6000,{hold_ms:report.power_release.end_wall_ms-report.power_hold.start_wall_ms});
 report.power=await page.evaluate(()=>({status:smokeRun.runtime.status,evidence:smokeRun.runtime.evidence(),errors:smokeRun.errors,banner:document.querySelector('#errorBanner')?.textContent,iframe_count:document.querySelectorAll('iframe').length}));
 check('power-release-after-natural-stop-has-no-error-banner',!report.power.banner,report.power.banner);
 const natural=report.power.evidence.machine_events.some(e=>e.event==='SHUTDOWN'&&e.guest===true)&&report.power.evidence.cleanup?.exitCode===0;
 check('PWR-six-second-hold-causes-natural-SHUTDOWN-exit-zero',natural,report.power);
 const expected=report.power.evidence.cleanup.workersCreated+1;
 report.workers_after_removal=await targets.waitUntilClosed({minimumObserved:expected,timeoutMs:30000});
 if(!report.workers_after_removal.ok){
  const cdp=await browser.newBrowserCDPSession();report.remaining_worker_contexts=[];
  for(const target of report.workers_after_removal.live){
   const diagnostic={target_id:target.target_id};report.remaining_worker_contexts.push(diagnostic);let sessionId;
   try{diagnostic.target_info=await cdp.send('Target.getTargetInfo',{targetId:target.target_id});sessionId=(await cdp.send('Target.attachToTarget',{targetId:target.target_id,flatten:false})).sessionId;
    const answer=new Promise(done=>{const timer=setTimeout(()=>{cdp.off('Target.receivedMessageFromTarget',listener);done({timeout_ms:5000});},5000);function listener(e){if(e.sessionId!==sessionId)return;const data=JSON.parse(e.message);if(data.id!==1)return;clearTimeout(timer);cdp.off('Target.receivedMessageFromTarget',listener);done(data);}cdp.on('Target.receivedMessageFromTarget',listener);});
    await cdp.send('Target.sendMessageToTarget',{sessionId,message:JSON.stringify({id:1,method:'Runtime.evaluate',params:{expression:'1+1',returnByValue:true}})});diagnostic.constant_evaluation=await answer;
   }catch(e){diagnostic.error=e.message;}finally{if(sessionId)await cdp.send('Target.detachFromTarget',{sessionId}).catch(()=>{});}
  }await cdp.detach();
 }
 check('natural-shutdown-all-workers-and-iframe-closed',report.workers_after_removal.ok&&expected===6&&report.workers_after_removal.observed.length===6&&await page.locator('iframe').count()===0,report.workers_after_removal);
 check('no-API-or-user-service-requests',blocked.length===0&&!requests.some(r=>/\/api\/v1|:8787\b|:8830\b/.test(r.url)));
 check('no-page-errors',errors.length===0,errors);
 report.status='PASS';
}catch(error){report.status='FAIL';report.error=error.message;process.exitCode=1;if(page){report.failure=await page.evaluate(()=>({status:globalThis.smokeRun?.runtime?.status,evidence:globalThis.smokeRun?.runtime?.evidence(),errors:globalThis.smokeRun?.errors,banner:document.querySelector('#errorBanner')?.textContent})).catch(()=>null);await page.screenshot({path:resolve(out,'failure.png'),fullPage:true}).catch(()=>{});}}
finally{
 report.finished_at=new Date().toISOString();report.forced_browser_cleanup_after_failure=report.status!=='PASS';
 try{if(page)await writeFile(resolve(out,'serial.txt'),await page.evaluate(()=>globalThis.smokeRun?.runtime?.serial||'').catch(()=>''));
 await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');
 const concise={kind:report.kind,status:report.status,error:report.error,started_at:report.started_at,finished_at:report.finished_at,harness_sha256:report.harness_sha256,export_manifest_sha256:report.export_manifest_sha256,instrumentation:report.instrumentation,wasm_sha256:expectedWasm,firmware_sha256:imageSha,checks:checks.map(({name,ok})=>({name,ok})),power_hold:report.power_hold,power_release:report.power_release,machine_events:report.power?.evidence.machine_events,cleanup:report.power?.evidence.cleanup,worker_targets:report.workers_after_removal?{ok:report.workers_after_removal.ok,observed:report.workers_after_removal.observed.length,live:report.workers_after_removal.live,source:report.workers_after_removal.source}:null,remaining_worker_contexts:report.remaining_worker_contexts,forced_cleanup_after_failure:report.forced_browser_cleanup_after_failure};const conciseText=JSON.stringify(concise,null,2)+'\n';assert.ok(Buffer.byteLength(conciseText)<65536);await writeFile(resolve(out,'concise-summary.json'),conciseText);
 }finally{await targets?.detach().catch(()=>{});await browser?.close().catch(()=>{});
 if(server)await new Promise(resolve=>server.close(resolve));
 console.log('FINAL',report.status,report.error||'',out);
}}
