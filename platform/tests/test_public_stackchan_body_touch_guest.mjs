// Explicit browser guest acceptance: original StackChan API and Si12T I2C.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';
import {capturePublicQemuProvenance,QEMU_EXECUTED_WEB_PATHS} from './public_qemu_artifacts.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';
import {findPublicButtonPointerTarget} from './public_qemu_button_pointer.mjs';

const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const site=process.env.M5_PUBLIC_SITE&&resolve(process.env.M5_PUBLIC_SITE);
if(!site){console.log('SKIP: explicit M5_PUBLIC_SITE export required');process.exit(0);}
const out=resolve(process.env.M5_PUBLIC_QEMU_OUT||resolve(repo,'.work/stackchan-body-touch'));
assert.ok(out.startsWith(resolve(repo,'.work')+'/'),'Raw evidence belongs in ignored .work');
await mkdir(out,{recursive:false});
const basePath=process.env.M5_PUBLIC_BASE_PATH||'/showcase/';
const timeout=Number(process.env.M5_QEMU_READY_TIMEOUT_MS||300000);
assert.ok(Number.isSafeInteger(timeout)&&timeout>=30000&&timeout<=600000);
const {chromium}=await import(pathToFileURL(resolve(process.env.M5_WASM_NODE_MODULES||resolve(repo,'platform/tests/node_modules'),'playwright/index.mjs')));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex'),nonce=randomUUID();
const observerPath='tests/browser-qemu/stackchan_body_touch/main.py',observer=await readFile(resolve(repo,observerPath),'utf8');
const source=`RUN_NONCE = ${JSON.stringify(nonce)}\n`+observer;
const cases=[{zone:1,component:'touch-1',key:'KeyZ',domKey:'z',mask:48,levels:[3,0,0]},
  {zone:2,component:'touch-2',key:'KeyX',domKey:'x',mask:12,levels:[0,3,0]},
  {zone:3,component:'touch-3',key:'KeyC',domKey:'c',mask:3,levels:[0,0,3]}];
const report={kind:'browser-stackchan-three-body-touch',status:'FAIL',started_at:new Date().toISOString(),
  evidence_level:'virtual-device validation',hardware_validation:'NOT RUN',nonce,checks:[],inputs:[],errors:[],
  scope:'Default UIFlow workbench; real keyboard/mouse components, Si12T QMP readback and original StackChan.get_touch() I2C reads.',
  observer:{path:observerPath,sha256:hash(observer),executed_sha256:hash(source)},
  pointer_helper_sha256:hash(await readFile(resolve(repo,'platform/tests/public_qemu_button_pointer.mjs')))};
const check=(name,ok,details)=>{report.checks.push({name,ok,details});assert.ok(ok,name);console.log(name);};
let server,browser,page,workers;
const mime={'.html':'text/html','.js':'text/javascript','.json':'application/json','.mjs':'text/javascript',
  '.css':'text/css','.wasm':'application/wasm','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2','.svg':'image/svg+xml'};
const rows=()=>page.evaluate(nonce=>(globalThis.bodyTouchRun?.output||'').split('\n').flatMap(line=>{
  if(!line.startsWith('M5_STACKCHAN_TOUCH '))return [];
  try{const row=JSON.parse(line.slice('M5_STACKCHAN_TOUCH '.length));return row.nonce===nonce?[row]:[];}catch{return [];}
}),nonce);
async function observe(predicate,description,waitMs=30000){
  const deadline=Date.now()+waitMs;
  while(Date.now()<deadline){
    const state=await page.evaluate(()=>({error:globalThis.bodyTouchRun?.error,output:globalThis.bodyTouchRun?.output||'',result:globalThis.bodyTouchRun?.result}));
    if(state.error||/Traceback \(most recent call last\):|Guru Meditation Error|Interrupt wdt timeout/.test(state.output))throw new Error(state.error||'Guest exception/panic');
    const match=(await rows()).find(predicate);if(match)return match;
    if(state.result)throw new Error('Observer finished before '+description);
    await page.waitForTimeout(50);
  }
  throw new Error('Original guest touch observation timed out: '+description);
}
try{
  report.provenance=await capturePublicQemuProvenance({repo,site,testScript:'platform/tests/test_public_stackchan_body_touch_guest.mjs',
    webPaths:[...QEMU_EXECUTED_WEB_PATHS,'platform/web/public-micropython.js','platform/web/public-uiflow-firmware.js',
      'platform/web/uiflow-workbench-profiles.json','platform/web/vendor/m5stack-models/src/devices/stackchan/index.js',
      'platform/web/vendor/m5stack-models/src/devices/stackchan/touch-led.js','platform/web/vendor/m5stack-models/src/core/DeviceViewer.js',
      'platform/web/vendor/m5stack-models/src/core/components/Button.js']});
  server=createServer(async(request,response)=>{
    try{
      const pathname=new URL(request.url,'http://localhost').pathname;
      if(!pathname.startsWith(basePath)){response.writeHead(404).end();return;}
      const file=resolve(site,decodeURIComponent(pathname.slice(basePath.length))||'index.html');
      if(!file.startsWith(site+'/')){response.writeHead(403).end();return;}
      response.writeHead(200,{'content-type':mime[extname(file)]||'application/octet-stream','cache-control':'no-cache'});
      response.end(await readFile(file));
    }catch{response.writeHead(404).end();}
  });
  await new Promise(done=>server.listen(0,'127.0.0.1',done));
  const origin=`http://127.0.0.1:${server.address().port}${basePath}`;report.url=origin;
  browser=await chromium.launch({headless:true,...(process.env.M5_WASM_CHROME?{executablePath:process.env.M5_WASM_CHROME}:{}),
    args:['--enable-webgl','--use-gl=angle','--use-angle=metal','--ignore-gpu-blocklist']});
  report.browser=browser.version();
  workers=await observeWorkerTargets(browser);page=await browser.newPage({viewport:{width:1200,height:1000}});
  page.on('pageerror',error=>report.errors.push(error.message));let privateRequests=0;
  await page.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>{privateRequests++;return route.abort('blockedbyclient');});
  await page.goto(origin,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>crossOriginIsolated&&document.querySelector('#deviceMount')?.dataset.deviceId==='cores3',{}, {timeout:45000});
  check('cross-origin-isolated',await page.evaluate(()=>crossOriginIsolated));
  await page.evaluate(async origin=>{
    const {ModelDeviceShell}=await import(new URL('platform/web/model-shell.js?v=20261026h',origin));
    const create=ModelDeviceShell.create;
    ModelDeviceShell.create=async function(...args){const shell=await create.apply(this,args);if(args[1].id==='stackchan'){
      globalThis.bodyTouchShell=shell;globalThis.bodyTouchEvents=[];
      shell.on('capacitive-touch',event=>bodyTouchEvents.push({...event,wall_ms:performance.now()}));
    }return shell;};
    const {PublicQemuRuntime}=await import(new URL('platform/web/public-qemu-runtime.js',origin)),start=PublicQemuRuntime.prototype.start;
    PublicQemuRuntime.prototype.start=function(...args){if(args[0].device==='stackchan')globalThis.bodyTouchRuntime=this;return start.apply(this,args);};
  },origin);
  await page.locator('button[data-device-id="stackchan"]').click();
  await page.waitForFunction(()=>globalThis.bodyTouchShell?.device.id==='stackchan',{}, {timeout:45000});
  report.renderer=await page.evaluate(()=>{const gl=bodyTouchShell.viewer.renderer.getContext(),debug=gl.getExtension('WEBGL_debug_renderer_info');return gl.getParameter(debug?debug.UNMASKED_RENDERER_WEBGL:gl.RENDERER);});
  check('actual-hardware-angle-renderer',!/swiftshader|software/i.test(report.renderer),report.renderer);
  check('actual-public-keyboard-aliases',await page.evaluate(cases=>cases.every(item=>bodyTouchShell.model.keymap[item.key]===item.component),cases));
  check('visible-keyboard-help',await page.evaluate(()=>['Z 前部','X 中部','C 后部'].every(text=>bodyTouchShell.hint.textContent.includes(text))));
  if(!await page.locator('#runtimeMode').isVisible())await page.locator('.advanced-options > summary').click();
  await page.locator('#runtimeMode').selectOption('browser');await page.locator('input[name="firmwareSource"][value="reference"]').check();
  check('actual-default-workbench-selected',await page.locator('#referenceExample').inputValue()==='uiflow');
  await page.locator('#startBtn').click();
  await page.waitForFunction(()=>globalThis.bodyTouchRuntime?.status==='running',{}, {timeout});
  report.initial=await page.evaluate(()=>bodyTouchRuntime.evidence());
  report.controller=await page.evaluate(()=>bodyTouchRuntime.profile.inputs.capacitiveTouch);
  check('bound-si12t-controller-route',report.controller.path==='/machine/si12t'&&report.controller.property==='touch-bits'
    &&JSON.stringify(report.controller.masks)==='[48,12,3]',report.controller);
  const registry=JSON.parse(await readFile(resolve(site,'platform/web/uiflow-workbench-profiles.json'))),expected=registry.profiles.find(row=>row.deviceId==='stackchan');
  check('exact-workbench-and-runtime',report.initial.receipt.firmwareSha256===expected.firmwareSHA256
    &&report.initial.receipt.wasmSha256===report.provenance.runtime_assets['qemu-system-xtensa.wasm'].sha256,report.initial.receipt);
  await page.evaluate(async({origin,source})=>{
    const {PublicMicroPythonRunner}=await import(new URL('platform/web/public-micropython.js',origin));
    const runner=new PublicMicroPythonRunner(bodyTouchRuntime),run={runner,output:'',result:null,error:null};globalThis.bodyTouchRun=run;
    run.pending=runner.run(source,{timeoutMs:120000,onOutput:text=>run.output+=text})
      .then(result=>run.result=result,error=>run.error=String(error?.message||error));
  },{origin,source});
  const ready=await observe(row=>row.kind==='ready','original driver ready',timeout);
  check('original-api-zero-state',JSON.stringify(ready.levels)==='[0,0,0]'&&JSON.stringify(ready.driver_levels)==='[0,0,0]',ready);
  for(const item of cases)for(const method of ['keyboard','pointer']){
    const before=(await rows()).at(-1)?.seq||0;
    const start=await page.evaluate(()=>({inputs:bodyTouchRuntime.inputs.length,events:bodyTouchEvents.length}));
    const canvas=page.locator('#deviceMount .three-device-stage canvas');await canvas.scrollIntoViewIfNeeded();
    let pointer=null,downAt,upAt;
    if(method==='keyboard'){
      await canvas.focus();downAt=performance.now();await page.keyboard.down(item.domKey);
      try{await page.waitForTimeout(250);}finally{await page.keyboard.up(item.domKey);}upAt=performance.now();
    }else{
      pointer=await page.evaluate(findPublicButtonPointerTarget,{componentId:item.component,origin,shellGlobal:'bodyTouchShell'});
      check(`pointer-${item.zone}-real-surface-hit`,await page.evaluate(p=>document.elementFromPoint(p.clientX,p.clientY)===bodyTouchShell.viewer.renderer.domElement
        &&bodyTouchShell.viewer.pick(p)?.component.path===p.component,pointer),pointer);
      await page.mouse.move(pointer.clientX,pointer.clientY);downAt=performance.now();await page.mouse.down();
      try{await page.waitForTimeout(250);}finally{await page.mouse.up();}upAt=performance.now();
    }
    const pressed=await observe(row=>row.kind==='state'&&row.seq>before&&JSON.stringify(row.levels)===JSON.stringify(item.levels),`${method} zone ${item.zone} down`);
    const released=await observe(row=>row.kind==='state'&&row.seq>pressed.seq&&row.levels.every(value=>value===0),`${method} zone ${item.zone} up`);
    await page.waitForFunction(start=>bodyTouchRuntime.inputs.length>=start+2,start.inputs,{timeout:15000});
    const actual=await page.evaluate(start=>({inputs:bodyTouchRuntime.inputs.slice(start.inputs),events:bodyTouchEvents.slice(start.events)}),start);
    check(`${method}-${item.zone}-capacitive-model-events`,actual.events.length===2&&actual.events.every(row=>row.zone===item.zone)
      &&actual.events[0].down===true&&actual.events[1].down===false
      &&actual.events.every(row=>row.source?.startsWith(method==='keyboard'?'key:':'pointer:')),actual.events);
    check(`${method}-${item.zone}-actual-si12t-readback`,actual.inputs.length===2&&actual.inputs.every(row=>row.type==='capacitive-touch'&&row.zone===item.zone)
      &&actual.inputs[0].down===true&&actual.inputs[0].result?.touch_bits===item.mask
      &&actual.inputs[1].down===false&&actual.inputs[1].result?.touch_bits===0
      &&actual.inputs.every(row=>row.result?.source==='qemu-qom-readback'),actual.inputs);
    check(`${method}-${item.zone}-original-i2c-driver-levels`,JSON.stringify(pressed.driver_levels)===JSON.stringify([...item.levels].reverse())
      &&released.driver_levels.every(value=>value===0),{pressed,released});
    report.inputs.push({...item,method,requested_hold_ms:250,observed_hold_ms:upAt-downAt,pointer,pressed,released,...actual});
  }
  await page.evaluate(()=>bodyTouchRun.runner.interrupt());await page.waitForFunction(()=>!bodyTouchRun.runner.busy,{}, {timeout:30000});
  report.execution=await page.evaluate(()=>({result:bodyTouchRun.result,error:bodyTouchRun.error,output:bodyTouchRun.output}));
  check('raw-repl-interrupt-returned',!report.execution.error&&report.execution.result?.interrupted===true
    &&report.execution.result.stderr.includes('KeyboardInterrupt'),report.execution.result);
  await page.screenshot({path:resolve(out,'body-touch.png'),fullPage:true});
  await page.evaluate(()=>{const frame=bodyTouchRuntime.iframe;globalThis.bodyTouchDeferred={frame,remove:frame.remove,requests:0};frame.remove=()=>bodyTouchDeferred.requests++;});
  await page.locator('#stopBtn').click();await page.waitForFunction(()=>bodyTouchRuntime.status==='stopped',{}, {timeout:45000});
  report.stopped=await page.evaluate(()=>bodyTouchRuntime.evidence());const cleanup=report.stopped.cleanup,minimum=cleanup.workersCreated+1;
  check('normal-guest-worker-cleanup',cleanup.gracefulExit&&cleanup.exitCode===0&&cleanup.workersAtExit===0
    &&cleanup.explicitWorkerDisposal===true&&cleanup.disposal.workersRemaining===0&&cleanup.disposal.workersTerminatedByDispose===0
    &&cleanup.disposal.ownerTerminatesAfterAcknowledgement===true&&cleanup.disposal.engineSelfClosesAfterAcknowledgement===false
    &&cleanup.engineOwnership.engineOwnerLive===false&&cleanup.engineOwnership.engineCloseNotificationReceived===true
    &&cleanup.engineOwnership.engineCloseNotifications===1&&cleanup.engineOwnership.engineNormalTerminations===1
    &&cleanup.engineOwnership.engineFinalizationAcknowledged===true && cleanup.engineOwnership.engineFallbackTerminations===0,cleanup);
  report.pthreads_closed=await workers.waitUntilOnly({minimumObserved:minimum,allowedUrlPart:'/public-qemu-engine.js',timeoutMs:30000});
  check('pthreads-close-before-iframe',report.pthreads_closed.ok&&await page.evaluate(()=>bodyTouchDeferred.frame.isConnected&&bodyTouchDeferred.requests===1));
  await page.evaluate(()=>bodyTouchDeferred.remove.call(bodyTouchDeferred.frame));
  report.worker_targets=await workers.waitUntilClosed({minimumObserved:minimum});check('all-cdp-workers-close-before-context',report.worker_targets.ok,report.worker_targets);
  check('no-private-service-requests',privateRequests===0);check('no-page-errors',report.errors.length===0,report.errors);
  report.status='PASS';
}catch(error){
  report.error=String(error?.stack||error);process.exitCode=1;
  if(page){report.failure=await page.evaluate(()=>({evidence:globalThis.bodyTouchRuntime?.evidence(),output:globalThis.bodyTouchRun?.output})).catch(()=>null);
    await page.evaluate(()=>globalThis.bodyTouchRuntime?.stop()).catch(()=>{});
    await page.evaluate(()=>globalThis.bodyTouchDeferred?.remove.call(bodyTouchDeferred.frame)).catch(()=>{});
    if(workers)report.failure_cleanup=await workers.waitUntilClosed({minimumObserved:1,timeoutMs:30000}).catch(()=>null);
  }
}finally{
  report.finished_at=new Date().toISOString();const bytes=JSON.stringify(report,null,2)+'\n';await writeFile(resolve(out,'report.json'),bytes);
  const summary={kind:report.kind,status:report.status,started_at:report.started_at,finished_at:report.finished_at,
    raw_report:{bytes:Buffer.byteLength(bytes),sha256:hash(bytes)},observer:report.observer,source_test_sha256:report.provenance?.test_script.sha256,
    site_manifest_sha256:report.provenance?.site_manifest_sha256,firmware_sha256:report.initial?.receipt.firmwareSha256,
    wasm_sha256:report.initial?.receipt.wasmSha256,controller:report.controller,checks:report.checks.map(({name,ok})=>({name,ok})),
    inputs:report.inputs.map(({zone,method,requested_hold_ms,observed_hold_ms,mask,pressed,released})=>({zone,method,requested_hold_ms,observed_hold_ms,mask,
      down_levels:pressed.levels,up_levels:released.levels,down_driver_levels:pressed.driver_levels,up_driver_levels:released.driver_levels})),
    cleanup:report.stopped?.cleanup,worker_targets:report.worker_targets?{ok:report.worker_targets.ok,observed:report.worker_targets.observed.length,live:report.worker_targets.live.length}:null,
    error:report.error?{recorded_in_raw_report:true}:null,
    limits:['Only these three logical body-touch zones and six 250ms keyboard/pointer pulses.','No physical capacitance, threshold, gesture or timing claims.']};
  const text=JSON.stringify(summary,null,2)+'\n';assert.ok(Buffer.byteLength(text)<65536);await writeFile(resolve(out,'summary.json'),text);
  await workers?.detach();await browser?.close();if(server)await new Promise(done=>server.close(done));
  console.log(JSON.stringify({status:report.status,output:out,checks:report.checks.length}));
}
