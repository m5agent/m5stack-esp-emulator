// Opt-in same-guest screen/servo test. Production files are served unchanged.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {capturePublicQemuProvenance} from './public_qemu_artifacts.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';

if(!process.env.M5_PUBLIC_SITE){console.log('SKIP: explicit M5_PUBLIC_SITE export required');process.exit(0);}
const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const site=resolve(process.env.M5_PUBLIC_SITE),out=resolve(process.env.M5_STACKCHAN_OUT||resolve(repo,'.work/stackchan-screen-motion-guest'));
assert.ok(out.startsWith(resolve(repo,'.work')+'/'),'Raw execution evidence must stay in ignored .work');
const expectedWasm=process.env.M5_STACKCHAN_WASM_SHA256,expectedManifest=process.env.M5_STACKCHAN_MANIFEST_SHA256;
assert.match(expectedWasm||'',/^[a-f0-9]{64}$/);assert.match(expectedManifest||'',/^[a-f0-9]{64}$/);
assert.ok(process.env.M5_STACKCHAN_SCREEN_IMAGES_JSON,'Explicit image/SHA manifest required');
const imagePath=resolve(process.env.M5_STACKCHAN_SCREEN_IMAGES_JSON),images=JSON.parse(await readFile(imagePath,'utf8'));
const names=(process.env.M5_STACKCHAN_SCREEN_CASES||'screen_polling,screen_blocked_control,reference').split(',');
assert.ok(names.length&&new Set(names).size===names.length&&names.every(n=>['screen_polling','screen_blocked_control','reference'].includes(n)));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
for(const name of names){assert.match(images[name]?.sha256||'',/^[a-f0-9]{64}$/);if(name!=='reference'){assert.equal(typeof images[name].path,'string');images[name].path=resolve(dirname(imagePath),images[name].path);assert.equal(sha(await readFile(images[name].path)),images[name].sha256);}}
await mkdir(out,{recursive:false});await writeFile(resolve(out,'harness.mjs'),await readFile(new URL(import.meta.url)));
const manifestBytes=await readFile(resolve(site,'public-site-manifest.json')),manifest=JSON.parse(manifestBytes),base=manifest.base_path;
assert.equal(sha(manifestBytes),expectedManifest);assert.equal(manifest.assets.find(r=>r.path==='platform/runtime/qemu/qemu-system-xtensa.wasm')?.sha256,expectedWasm);
const modules=process.env.M5_WASM_NODE_MODULES||resolve(repo,'platform/tests/node_modules');
const {chromium}=await import(pathToFileURL(resolve(modules,'playwright/index.mjs')));
const checks=[],requests=[],blocked=[],errors=[];
const report={kind:'stackchan-screen-input-during-real-servo-motion',started_at:new Date().toISOString(),wasm_sha256:expectedWasm,site_manifest_sha256:expectedManifest,harness_sha256:sha(await readFile(new URL(import.meta.url))),hardware_validation:'NOT RUN',checks,cases:[],requests,blocked,errors,
 instrumentation:'Only observers wrap production callbacks. Actual DOM mouse events target the current transformed LCD panel. QOM positions, original Touch API, optional guest I2C register observations and LCD pixels are independent observations. A raw-frame input is labelled diagnostic and never replaces DOM acceptance.'};
let server,browser,targets,page,context,startedRuns=0;
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.wasm':'application/wasm','.css':'text/css','.png':'image/png','.webp':'image/webp','.svg':'image/svg+xml','.woff2':'font/woff2'};
function check(name,ok,detail){checks.push({name,ok,detail});console.log(name,ok?'PASS':'FAIL');return ok;}
const snapshot=()=>page.evaluate(()=>({events:screenRun.events,samples:screenRun.samples,frames:screenRun.frames,inputs:screenRun.inputs,serial:screenRun.serial,errors:screenRun.errors,receipt:screenRun.runtime.receipt,session:screenRun.runtime.sessionId,status:screenRun.runtime.status}));
async function pickScreen(){return page.evaluate(async()=>{
 const shell=screenShell,d=shell.model.find('lcd','display'),THREE=await import(new URL('platform/web/vendor/three/three.module.js',document.baseURI));
 shell.model.root.updateWorldMatrix(true,true);
 const v=d.panel.localToWorld(new THREE.Vector3(0,-.12*d.size[1],0)).project(shell.viewer.camera),box=shell.viewer.renderer.domElement.getBoundingClientRect(),x=box.left+(v.x+1)*box.width/2,y=box.top+(1-v.y)*box.height/2;
 const picked=shell.viewer.pick({clientX:x,clientY:y}),element=document.elementFromPoint(x,y);
 return {x,y,hit:picked?.component?.id,is_canvas:element===shell.viewer.renderer.domElement,wall_ms:performance.now(),raw_expected:{x:Math.floor(d.width*.5),y:Math.floor(d.height*.62)},yaw:shell.model.find('yaw','joint').getState(),pitch:shell.model.find('pitch','joint').getState()};
});}
async function ready(name){
 context=await browser.newContext({viewport:{width:1280,height:1000}});page=await context.newPage();
 page.on('pageerror',e=>errors.push({case:name,error:e.message}));page.on('request',r=>requests.push({case:name,url:r.url(),method:r.method()}));
 await page.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>{blocked.push(route.request().url());return route.abort('blockedbyclient');});
 await page.goto(report.url,{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>crossOriginIsolated&&document.querySelector('#deviceMount')?.dataset.deviceId==='cores3',{}, {timeout:45000});
 await page.evaluate(async origin=>{
  const {ModelDeviceShell}=await import(new URL('platform/web/model-shell.js?v=20261026h',origin)),create=ModelDeviceShell.create;
  ModelDeviceShell.create=async function(...args){const s=await create.apply(this,args);if(args[1].id==='stackchan')globalThis.screenShell=s;return s;};
  const {PublicQemuRuntime}=await import(new URL('platform/web/public-qemu-runtime.js',origin)),start=PublicQemuRuntime.prototype.start;
  const {sha256Bytes}=await import(new URL('platform/web/sha256.js',origin));
  PublicQemuRuntime.prototype.start=function(...args){
   if(args[0].device==='stackchan'){
    const runtime=this,onSerial=this.onSerial,onFrame=this.onFrame,onState=this.onDeviceState,onError=this.onError,input=this.input;
    globalThis.screenRun={runtime,serial:'',line:'',events:[],samples:[],frames:[],inputs:[],errors:[]};
    this.onSerial=text=>{onSerial(text);screenRun.serial+=text;screenRun.line+=text;let at;while((at=screenRun.line.indexOf('\n'))>=0){let line=screenRun.line.slice(0,at).trim();screenRun.line=screenRun.line.slice(at+1);const reference=line.startsWith('M5_BROWSER_PROBE ');if(reference)line=line.slice(17);try{const event=JSON.parse(line);if(reference||/^stackchan-screen-motion-20261030-v[123]$/.test(event.nonce||''))screenRun.events.push({...event,wall_ms:performance.now(),reference});}catch{}}};
    this.onError=e=>{screenRun.errors.push(e.message);onError(e);};
    this.onDeviceState=s=>{onState(s);screenRun.samples.push({wall_ms:performance.now(),state:structuredClone(s),yaw:screenShell.model.find('yaw','joint').getState(),pitch:screenShell.model.find('pitch','joint').getState()});};
    this.input=async function(event){const row={event:structuredClone(event),sent_wall_ms:performance.now()};screenRun.inputs.push(row);try{const result=await input.call(this,event);row.result=structuredClone(result??null);row.ack_wall_ms=performance.now();return result;}catch(e){row.error=e.message;throw e;}};
    this.onFrame=f=>{onFrame(f);const d=screenShell.model.find('lcd','display'),expected=new Uint8Array(d.buffer.length);for(let i=0,j=0;i<f.pixels.length;i+=2,j+=4){const v=f.pixels[i]|f.pixels[i+1]<<8;expected[j]=((v>>11)&31)<<3|((v>>11)&31)>>2;expected[j+1]=((v>>5)&63)<<2|((v>>5)&63)>>4;expected[j+2]=(v&31)<<3|(v&31)>>2;expected[j+3]=255;}
     screenRun.frames.push({wall_ms:performance.now(),sequence:f.sequence,sha256:sha256Bytes(f.pixels),lcd_sha256:sha256Bytes(d.buffer),pixels_match:expected.every((v,i)=>v===d.buffer[i])});};
   }return start.apply(this,args);
  };
 },report.url);
 await page.locator('button[data-device-id="stackchan"]').click();await page.waitForFunction(()=>globalThis.screenShell?.device.id==='stackchan',{}, {timeout:45000});
 await page.evaluate(()=>{screenShell.viewer.setView('front',{duration:0});screenShell.viewer.fit({duration:0});screenShell.viewer.requestRender();});
 await page.locator('.advanced-options > summary').click();await page.locator('#runtimeMode').selectOption('browser');
 if(name!=='reference'){await page.locator('input[name="firmwareSource"][value="local"]').check();await page.locator('#firmwareFile').setInputFiles(images[name].path);await page.locator('#firmwareSha').fill(images[name].sha256);}
 else await page.locator('input[name="firmwareSource"][value="reference"]').check();
 await page.locator('#startBtn').click();startedRuns++;
 await page.waitForFunction(()=>globalThis.screenRun?.events.some(e=>e.kind==='ready')&&screenRun.runtime.receipt&&screenRun.frames.length&&screenRun.samples.length,{}, {timeout:180000});
 const state=await snapshot();assert.equal(state.receipt.wasmSha256,expectedWasm);assert.equal(state.receipt.firmwareSha256,images[name].sha256);
 if(name!=='reference'){const identity=state.events.find(e=>e.kind==='identity');check(name+': original-screen-driver-enabled',identity?.touch_enabled===true&&identity.width===320&&identity.height===240&&identity.rotation===1,identity);}
 return state;
}
async function waitMoving(){await page.waitForFunction(()=>{
 const s=screenRun.samples,last=s.at(-1),before=s.at(-3);if(!last||!before||performance.now()-last.wall_ms>500)return false;
 const yaw=last.yaw.angleDeg,pitch=last.pitch.angleDeg;
 // Select the middle of the motion, leaving travel for the held pulse.
 return Math.abs(yaw)<25&&pitch<30&&last.state.servos.some((v,i)=>Math.abs(v.present_position-before.state.servos[i].present_position)>1);
},{},{timeout:45000});}
async function pulse(row,label,holdMs,{moving=false,raw=false,expected=true}={}){
 if(moving)await waitMoving();
 const target=raw?null:await pickScreen();if(target)assert.ok(target.hit==='lcd'&&target.is_canvas,'Current transformed LCD must be actual DOM target');
 const begin=await page.evaluate(()=>({wall_ms:performance.now(),event:screenRun.events.length,sample:screenRun.samples.length,input:screenRun.inputs.length}));
 if(raw)await page.evaluate(()=>screenRun.runtime.input({type:'touch',x:160,y:148,down:true}));
 else{await page.mouse.move(target.x,target.y);await page.mouse.down();}
 const downAt=await page.evaluate(()=>performance.now());
 try{await page.waitForTimeout(holdMs);}finally{if(raw)await page.evaluate(()=>screenRun.runtime.input({type:'touch',x:160,y:148,down:false}));else await page.mouse.up();}
 const upAt=await page.evaluate(()=>performance.now());
 if(expected)await page.waitForFunction(n=>{const es=screenRun.events.slice(n);return es.some(e=>['screen_down','pressed'].includes(e.kind))&&es.some(e=>['screen_up','released'].includes(e.kind));},begin.event,{timeout:3500}).catch(()=>{});
 else await page.waitForTimeout(500);
 const finish=await snapshot(),es=finish.events.slice(begin.event),inputs=finish.inputs.slice(begin.input),within=finish.samples.filter(s=>s.wall_ms>=downAt&&s.wall_ms<=upAt);
 const ranges=[0,1].map(axis=>{const values=within.map(s=>s.state.servos[axis].present_position);return values.length?Math.max(...values)-Math.min(...values):0;});
 const down=es.find(e=>['screen_down','pressed'].includes(e.kind));
 const up=down?es.find(e=>['screen_up','released'].includes(e.kind)&&e.wall_ms>down.wall_ms):undefined;
 const actualDown=inputs.find(i=>i.event.type==='touch'&&i.event.down),actualUp=inputs.find(i=>i.event.type==='touch'&&!i.event.down);
 const controller=es.filter(e=>['ft_down','ft_up'].includes(e.kind));
 const result={label,source:raw?'raw-frame-diagnostic':'actual-DOM-panel',hold_requested_ms:holdMs,hold_observed_ms:upAt-downAt,target,begin_wall_ms:begin.wall_ms,down_wall_ms:downAt,up_wall_ms:upAt,inputs,events:es,controller_events:controller,qom_samples_during_hold:within.length,present_ranges_during_hold:ranges,
  touch_api_detected:!!(down&&up),expected_touch_api:expected,session:finish.session,receipt_firmware_sha256:finish.receipt.firmwareSha256};row.pulses.push(result);
 check(row.name+':'+label+': real-down-up-input',!!actualDown&&!!actualUp&&!actualDown.error&&!actualUp.error,{inputs});
 check(row.name+':'+label+': Touch-API-expectation',expected?!!(down&&up):!down&&!up,{down,up});
 if(expected&&down&&actualDown){const xy=down.xy||[down.x,down.y];check(row.name+':'+label+': coordinates',Math.abs(xy[0]-actualDown.event.x)<=3&&Math.abs(xy[1]-actualDown.event.y)<=3,{guest:xy,input:actualDown.event});}
 if(expected&&row.name!=='reference')check(row.name+':'+label+': independent-FT-I2C-readback',controller.some(e=>e.kind==='ft_down'&&e.ft_read_ok&&e.ft_count===1)&&controller.some(e=>e.kind==='ft_up'&&e.ft_read_ok&&e.ft_count===0),{controller});
 if(moving)check(row.name+':'+label+': actual-position-changed-during-hold',within.length>=2&&Math.max(...ranges)>=2,{samples:within.length,ranges});
 return result;
}
async function stopCase(row){
 if(!page)return;
 Object.assign(row,await snapshot());
 const inputGaps=row.events.map(e=>e.max_input_gap_ms).filter(Number.isFinite);
 row.reference_input_polling=inputGaps.length?{max_observed_gap_ms:Math.max(...inputGaps),heartbeat_records:inputGaps.length}:null;
 if(row.name==='reference'){
  const worker=row.events.find(e=>e.kind==='servo-worker-ready');
  check('reference: actual-original-UART-worker-started',worker?.implementation==='_thread'&&worker.io==='uart1-scs-only',worker);
  const heartbeats=row.events.filter(e=>e.kind==='heartbeat');
  check('reference: bounded-UART-event-queue-no-drops',heartbeats.length>0&&heartbeats.every(e=>e.motion_events_dropped===0),heartbeats.map(e=>({ms:e.guest_ms,dropped:e.motion_events_dropped})));
 }
 await page.screenshot({path:resolve(out,row.name+'.png'),fullPage:true});
 await page.locator('#stopBtn').click();await page.waitForFunction(()=>screenRun.runtime.status==='stopped'&&!screenRun.runtime.iframe,{}, {timeout:45000});
 row.cleanup=await page.evaluate(()=>screenRun.runtime.evidence().cleanup);check(row.name+': graceful-stop',row.cleanup?.gracefulExit&&row.cleanup.exitCode===0&&row.cleanup.explicitWorkerDisposal);
 row.workers=await targets.waitUntilClosed({minimumObserved:startedRuns*6,timeoutMs:30000});check(row.name+': six-workers-zero-before-context-close',row.workers.ok&&row.workers.observed.length===startedRuns*6&&await page.locator('iframe').count()===0,{observed:row.workers.observed.length,live:row.workers.live.length});
 check(row.name+': actual-frame-to-model',row.frames.length>1&&row.frames.every(f=>f.pixels_match),{frames:row.frames.length,unique:new Set(row.frames.map(f=>f.sha256)).size});
 check(row.name+': no-runtime-or-UART-fallback-errors',!row.errors.length&&!row.events.some(e=>e.kind?.endsWith('-error'))&&!/ignore invalid current pos|fallback angle|RuntimeError|Traceback|Guru Meditation|memory access out of bounds/.test(row.serial));
 row.boot_diagnostics={psram_id_warning_count:(row.serial.match(/PSRAM ID read error/g)||[]).length,boundary:'All boot serial is retained. A PSRAM probe warning alone is not classified as a new screen/servo failure or physical-memory validation.'};
 const stopAt=checks.length;row.status=checks.some(c=>c.name.startsWith(row.name+':')&&!c.ok)?'FAIL':'PASS';row.checks_at_close=stopAt;
 await writeFile(resolve(out,row.name+'-serial.txt'),row.serial);await writeFile(resolve(out,row.name+'-report.json'),JSON.stringify(row,null,2)+'\n');
 let timer;try{await Promise.race([context.close(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Context close exceeded 30 seconds')),30000);})]);}finally{clearTimeout(timer);}context=null;page=null;
}
try{
 report.provenance=await capturePublicQemuProvenance({repo,site,testScript:'platform/tests/test_stackchan_screen_motion_guest.mjs'});
 server=createServer(async(req,res)=>{try{const p=new URL(req.url,'http://localhost').pathname;if(!p.startsWith(base)){res.writeHead(404).end();return;}const f=resolve(site,decodeURIComponent(p.slice(base.length))||'index.html');if(!f.startsWith(site+'/')){res.writeHead(403).end();return;}res.writeHead(200,{'content-type':mime[extname(f)]||'application/octet-stream','cache-control':'no-cache'});res.end(await readFile(f));}catch{res.writeHead(404).end();}});await new Promise(yes=>server.listen(0,'127.0.0.1',yes));report.url=`http://127.0.0.1:${server.address().port}${base}`;
 browser=await chromium.launch({headless:true,...(process.env.M5_WASM_CHROME?{executablePath:process.env.M5_WASM_CHROME}:{}),args:['--enable-webgl','--use-gl=angle',...(process.env.M5_WASM_GPU==='hardware'?['--use-angle=metal','--ignore-gpu-blocklist']:['--use-angle=swiftshader'])]});report.browser=browser.version();targets=await observeWorkerTargets(browser);
 for(const name of names){
  const row={name,firmware_sha256:images[name].sha256,pulses:[],status:'RUNNING'};report.cases.push(row);await ready(name);
  if(name==='screen_polling'){
   for(const ms of [100,300,800])await pulse(row,'idle-'+ms,ms);
   await page.waitForFunction(()=>screenRun.events.some(e=>e.phase==='moving'),{}, {timeout:30000});
   for(const ms of [100,300,800])await pulse(row,'moving-'+ms,ms,{moving:true});
   await pulse(row,'raw-moving-300',300,{moving:true,raw:true});
  }else if(name==='screen_blocked_control'){
   await pulse(row,'idle-300',300);
   await page.waitForFunction(()=>screenRun.events.some(e=>e.kind==='blocked_begin'),{}, {timeout:60000});
   row.blocked_pulse=await pulse(row,'blocked-300',300,{expected:false});
   check(name+': independent-motion-task-keeps-moving-during-block',row.blocked_pulse.qom_samples_during_hold>=2&&Math.max(...row.blocked_pulse.present_ranges_during_hold)>=2,{samples:row.blocked_pulse.qom_samples_during_hold,ranges:row.blocked_pulse.present_ranges_during_hold});
   await page.waitForFunction(()=>screenRun.events.some(e=>e.kind==='blocked_end'),{}, {timeout:15000});
   await pulse(row,'recovered-300',300);
   const es=(await snapshot()).events,begin=es.find(e=>e.kind==='blocked_begin'),end=es.find(e=>e.kind==='blocked_end');
   check(name+': blocked-control-real-six-second-poll-gap',!!begin&&!!end&&end.ms-begin.ms>=6000&&end.updates===begin.updates,{begin,end});
  }else{
   for(const ms of [100,300,800])await pulse(row,'reference-moving-'+ms,ms,{moving:true});
   await pulse(row,'reference-raw-moving-300',300,{moving:true,raw:true});
   row.reference_controller_boundary='Official base/framework retained; default main.py changed. The original M5.Touch API remains the I2C delivery witness. Independent raw FT register telemetry exists only in the separate Arduino probe.';
  }
  await stopCase(row);
 }
 check('no-user-service-or-device-API-requests',blocked.length===0&&!requests.some(r=>/\/api\/v1|:8787\b|:8830\b/.test(r.url)));
 check('no-page-errors',errors.length===0,errors);report.status=checks.every(c=>c.ok)?'PASS':'FAIL';if(report.status!=='PASS')process.exitCode=1;
}catch(error){report.status='FAIL';report.error=error.message;process.exitCode=1;if(report.cases.at(-1)?.status==='RUNNING')report.cases.at(-1).status='FAIL';if(page){report.failure=await snapshot().catch(()=>null);await page.screenshot({path:resolve(out,'failure.png'),fullPage:true}).catch(()=>{});}}
finally{
 report.finished_at=new Date().toISOString();report.forced_cleanup_after_failure=!!context;
 try{await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');const concise={kind:report.kind,status:report.status,error:report.error,started_at:report.started_at,finished_at:report.finished_at,wasm_sha256:expectedWasm,site_manifest_sha256:expectedManifest,harness_sha256:report.harness_sha256,hardware_validation:'NOT RUN',instrumentation:report.instrumentation,checks:checks.map(({name,ok})=>({name,ok})),cases:report.cases.map(r=>({name:r.name,status:r.status,firmware_sha256:r.firmware_sha256,pulses:r.pulses.map(p=>({label:p.label,source:p.source,hold_requested_ms:p.hold_requested_ms,hold_observed_ms:p.hold_observed_ms,touch_api_detected:p.touch_api_detected,expected_touch_api:p.expected_touch_api,qom_samples_during_hold:p.qom_samples_during_hold,present_ranges_during_hold:p.present_ranges_during_hold,guest_events:p.events.map(e=>({kind:e.kind,phase:e.phase,ms:e.ms,xy:e.xy||[e.x,e.y],last_update_gap_ms:e.last_update_gap_ms,max_update_gap_ms:e.max_update_gap_ms,ft_read_ok:e.ft_read_ok,ft_count:e.ft_count,ft_xy:e.ft_xy,draw_cost_us:e.draw_cost_us,previous_report_cost_us:e.previous_report_cost_us,motion_command_cost_us:e.motion_command_cost_us}))})),cleanup:r.cleanup,workers:r.workers?{ok:r.workers.ok,observed:r.workers.observed.length,remaining:r.workers.live.length,source:r.workers.source}:null,boot_diagnostics:r.boot_diagnostics,reference_controller_boundary:r.reference_controller_boundary,reference_input_polling:r.reference_input_polling})),blocked_requests:blocked.length,forced_cleanup_after_failure:report.forced_cleanup_after_failure};const body=JSON.stringify(concise,null,2)+'\n';assert.ok(Buffer.byteLength(body)<65536);await writeFile(resolve(out,'concise-summary.json'),body);}finally{let timer;try{if(context)await Promise.race([context.close().catch(()=>{}),new Promise(yes=>{timer=setTimeout(yes,15000);})]);}finally{clearTimeout(timer);}await targets?.detach().catch(()=>{});await browser?.close().catch(()=>{});if(server)await new Promise(yes=>server.close(yes));console.log('BROWSER_WINDOW_RELEASED');console.log('FINAL',report.status,report.error||'');}
}
