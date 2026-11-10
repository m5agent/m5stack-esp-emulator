// Independent opt-in IRQ acceptance. No guest is executed without an explicit
// exported site and this lane's opt-in flag. This does not extend the old
// eleven-key fixture's result or modify any existing publication gate.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';
import {capturePublicQemuProvenance,QEMU_EXECUTED_WEB_PATHS} from './public_qemu_artifacts.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';
import {findPublicButtonPointerTarget} from './public_qemu_button_pointer.mjs';
import {CARDPUTER_KEYBOARD_CASES,CARDPUTER_KEYBOARD_CODES,CARDPUTER_KEYBOARD_SOURCE,
  requireCardputerKeyboardObservation} from './public_qemu_cardputer_keyboard_cases.mjs';

const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const site=process.env.M5_PUBLIC_SITE&&resolve(process.env.M5_PUBLIC_SITE);
if(!site||process.env.M5_CARDPUTER_KEYBOARD_IRQ!=='1'){
  console.log('SKIP: explicit M5_PUBLIC_SITE and M5_CARDPUTER_KEYBOARD_IRQ=1 required');process.exit(0);
}
assert.ok(!process.env.M5_QEMU_DEVICE||process.env.M5_QEMU_DEVICE==='cardputer-adv','Cardputer-ADV exact default image only');
assert.ok(!process.env.M5_QEMU_BUTTON_HOLD_MS||process.env.M5_QEMU_BUTTON_HOLD_MS==='250','formal keyboard pulse is fixed at 250 ms');
const device='cardputer-adv',holdMs=250,basePath=process.env.M5_PUBLIC_BASE_PATH||'/showcase/';
const mode=process.env.M5_CARDPUTER_WORKER_DIAG||'baseline';
assert.ok(['baseline','finalize-self','finalize-owner'].includes(mode));
const selected=process.env.M5_CARDPUTER_WORKER_DIAG_KEYS||'K,L,DOT';
const cases=selected==='all'?CARDPUTER_KEYBOARD_CASES:CARDPUTER_KEYBOARD_CASES.filter(item=>selected.split(',').includes(item.physical));
assert.ok(cases.length>0&&(selected==='all'||cases.length===selected.split(',').length));
const activeMs=Number(process.env.M5_CARDPUTER_WORKER_ACTIVE_MS||30000);
assert.ok(Number.isSafeInteger(activeMs)&&activeMs>=0&&activeMs<=60000);
const exitActive=process.env.M5_CARDPUTER_WORKER_INTERRUPT!=='1';
const out=resolve(process.env.M5_PUBLIC_QEMU_OUT||resolve(repo,'.work/public-uiflow-cardputer-keyboard-irq'));
assert.ok(out.startsWith(resolve(repo,'.work')+'/'),'raw evidence belongs in ignored .work');
await mkdir(out,{recursive:false});
const readyTimeout=Number(process.env.M5_QEMU_READY_TIMEOUT_MS||300000);
assert.ok(Number.isSafeInteger(readyTimeout)&&readyTimeout>=30000&&readyTimeout<=600000);
const overallDeadline=Date.now()+900000;
const modules=process.env.M5_WASM_NODE_MODULES||resolve(repo,'platform/tests/node_modules');
const {chromium}=await import(pathToFileURL(resolve(modules,'playwright/index.mjs')));
const observerPath='tests/browser-qemu/uiflow_workbench/cardputer_keyboard_observer.py';
const observer=await readFile(resolve(repo,observerPath),'utf8');
const hash=value=>createHash('sha256').update(value).digest('hex'),nonce=randomUUID();
const source=`RUN_NONCE = ${JSON.stringify(nonce)}\nKEY_CODES = ${JSON.stringify(CARDPUTER_KEYBOARD_CODES)}\n`+observer;
const checks=[],errors=[],requests=[];
const report={kind:'browser-uiflow-cardputer-worker-finalization-diagnostic',status:'FAIL',device,nonce,
  worker_diagnostic_status:'NOT RUN',mode,selected_keys:selected,minimum_active_ms:activeMs,stop_observer_active:exitActive,
  started_at:new Date().toISOString(),evidence_level:'virtual-device validation',hardware_validation:'NOT RUN',
  scope:'Selected physical keys through keyboard and raycast mouse input with the original public MatrixKeyboard callback and release state.',
  formal_hold_ms:holdMs,input_cases:[],checks,errors,source_oracle:CARDPUTER_KEYBOARD_SOURCE,
  observer:{path:observerPath,sha256:hash(observer),executed_sha256:hash(source)},
  oracle_sha256:hash(await readFile(resolve(repo,'platform/tests/public_qemu_cardputer_keyboard_cases.mjs'))),
  pointer_helper_sha256:hash(await readFile(resolve(repo,'platform/tests/public_qemu_button_pointer.mjs'))),
  limits:['Fn is tested using the documented Fn+grave ESC chord. Pointer Fn uses keyboard grave as a separately recorded companion.',
    'The original driver emits code 0 for standalone Fn; code 0 alone cannot pass its functional case.',
    'Source oracle hashes describe the inspected official source; the actual official image must independently pass this guest run.']};
const check=(name,ok,details)=>{checks.push({name,ok,details});assert.ok(ok,name);console.log(name);};
const save=()=>writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json',
  '.wasm':'application/wasm','.css':'text/css','.png':'image/png','.webp':'image/webp','.svg':'image/svg+xml','.woff2':'font/woff2'};
let server,browser,page,workers,cdp,browserCDP;
let lastProgress=0;
async function events(){return page.evaluate(nonce=>{
  const prefix='M5_CARDPUTER_KEYBOARD ';
  return (globalThis.keyboardRun?.output||'').split('\n').filter(line=>line.startsWith(prefix)).flatMap(line=>{
    try{const row=JSON.parse(line.slice(prefix.length));return row.nonce===nonce?[row]:[];}catch{return [];}
  });
},nonce);}
async function observe(predicate,description,timeout=30000){
  const deadline=Math.min(overallDeadline,Date.now()+timeout);
  for(;;){
    const state=await page.evaluate(()=>({error:globalThis.keyboardRun?.error,output:globalThis.keyboardRun?.output||'',
      banner:document.querySelector('#errorBanner')?.hidden?'':document.querySelector('#errorBanner')?.textContent}));
    if(state.error||state.banner)throw new Error(state.error||state.banner);
    if(/Traceback \(most recent call last\):|Guru Meditation Error|Interrupt wdt timeout|A fatal error occurred/.test(state.output))
      throw new Error(`Original guest failed: ${description}`);
    assert.ok(state.output.length<=1048576,'observer output exceeded bounded receipt size');
    const rows=await events();
    if(predicate(rows))return rows;
    if(Date.now()>=deadline)throw new Error(`Original IRQ observation timed out: ${description}`);
    if(Date.now()-lastProgress>10000){lastProgress=Date.now();report.waiting_for=description;report.latest_events=rows.slice(-8);await save();}
    await page.waitForTimeout(50);
  }
}
async function nativeKey(code,down){
  if(code==='Fn')await cdp.send('Input.dispatchKeyEvent',{type:down?'keyDown':'keyUp',key:'Fn',code:'Fn',
    windowsVirtualKeyCode:0,nativeVirtualKeyCode:0,modifiers:0});
  else if(down)await page.keyboard.down(code);else await page.keyboard.up(code);
}
async function readRawWorkers(){
  const response=await browserCDP.send('Target.getTargets');
  return response.targetInfos.filter(target=>target.type==='worker');
}
async function bounded(task,ms,label){
  let timer;
  try{
    return await Promise.race([task,new Promise((_,reject)=>{
      timer=setTimeout(()=>reject(new Error(label+' timed out after '+ms+'ms')),ms);
    })]);
  }finally{clearTimeout(timer);}
}
async function probeLingeringEngine(target){
  // This is after the formal deadline and outside the strict raw-zero check.
  // Merely listing or attaching a target does not prove runnable worker JS.
  const result={target_id:target.targetId,attempted_at:new Date().toISOString()};
  let sessionId, listener;
  try{
    ({sessionId}=await bounded(browserCDP.send('Target.attachToTarget',{targetId:target.targetId,flatten:false}),1000,'late CDP attach'));
    result.attached=true;
    const response=new Promise(resolve=>{
      listener=event=>{
        if(event.sessionId!==sessionId)return;
        try{const message=JSON.parse(event.message);if(message.id===1)resolve(message);}catch{}
      };
      browserCDP.on('Target.receivedMessageFromTarget',listener);
    });
    const command=JSON.stringify({id:1,method:'Runtime.evaluate',params:{expression:'6 * 7',returnByValue:true}});
    [,result.response]=await bounded(Promise.all([
      browserCDP.send('Target.sendMessageToTarget',{sessionId,message:command}),response,
    ]),1000,'late Worker Runtime.evaluate');
    result.evaluated=result.response?.result?.result?.value===42;
  }catch(error){result.error=String(error?.message||error);}
  finally{
    if(listener)browserCDP.off('Target.receivedMessageFromTarget',listener);
    if(sessionId)await bounded(browserCDP.send('Target.detachFromTarget',{sessionId}),500,'late CDP detach').catch(()=>{});
  }
  return result;
}
async function stopAndObserve(){
  if(!page||page.isClosed()||!await page.evaluate(()=>!!globalThis.keyboardRuntime))return;
  report.worker_diagnostic_status='FAIL';
  report.before_stop=await page.evaluate(()=>keyboardRuntime.evidence());
  report.worker_pre_stop=await readRawWorkers();
  report.observer_pre_stop=await page.evaluate(()=>({running:!!globalThis.keyboardRun&&!keyboardRun.finished,
    error:globalThis.keyboardRun?.error||null,output_bytes:globalThis.keyboardRun?.output.length||0}));
  await page.evaluate(()=>keyboardRuntime.stop());
  report.stopped=await page.evaluate(()=>keyboardRuntime.evidence());
  const cleanup=report.stopped.cleanup, engine=report.worker_pre_stop.find(row=>row.url.includes('/public-qemu-engine.js'));
  const expected=cleanup?.workersCreated+1, ownerMode=mode==='finalize-owner';
  check('positive-engine-and-all-pthreads-before-stop',Number.isInteger(expected)&&expected>=2&&!!engine
    &&report.worker_pre_stop.length===expected&&report.worker_pre_stop.filter(row=>row.parentId===engine.targetId).length===expected-1,
    report.worker_pre_stop);
  const finalization=cleanup?.engineOwnership?.engineFinalization;
  check('normal-qmp-quit-and-worker-cleanup',cleanup?.gracefulExit&&cleanup.exitCode===0&&cleanup.workersAtExit===0
    &&cleanup.disposal?.workersRemaining===0&&cleanup.disposal.workersTerminatedByDispose===0
    &&cleanup.disposal.ownerTerminatesAfterAcknowledgement===ownerMode&&cleanup.disposal.engineSelfClosesAfterAcknowledgement===!ownerMode
    &&cleanup.engineOwnership?.engineNormalTerminations===Number(ownerMode)&&cleanup.engineOwnership.engineFallbackTerminations===0
    &&cleanup.engineOwnership.engineCloseNotifications===1,cleanup);
  if(mode!=='baseline')check('worker-processed-post-dispose-finalization-in-a-later-task',
    finalization?.mode===mode&&!finalization.request_error&&Number.isFinite(finalization.port_drained_worker_epoch_ms)
    &&finalization.finalized_worker_epoch_ms>=finalization.port_drained_worker_epoch_ms
    &&finalization.acknowledgement_page_epoch_ms>=finalization.request_page_epoch_ms,finalization);
  report.worker_targets=await workers.waitUntilClosed({minimumObserved:expected,timeoutMs:120000});
  report.worker_final_raw=await readRawWorkers();
  if(report.worker_final_raw.length)
    report.browser_processes=await bounded(browserCDP.send('SystemInfo.getProcessInfo'),1000,'process info').catch(()=>null);
  const lingering=report.worker_final_raw.find(target=>target.targetId===engine.targetId);
  if(lingering&&process.env.M5_CARDPUTER_WORKER_PROBE_LINGER==='1')
    report.late_engine_probe=await probeLingeringEngine(lingering);
  check('actual-workers-closed-before-browser-context',report.worker_targets.ok&&report.worker_final_raw.length===0
    &&report.worker_targets.observed.length===expected,report.worker_targets);
  report.worker_diagnostic_status='PASS';
}

try{
  report.provenance=await capturePublicQemuProvenance({repo,site,
    testScript:'platform/tests/test_public_uiflow_cardputer_keyboard_guest.mjs',webPaths:[...QEMU_EXECUTED_WEB_PATHS,
      'platform/web/public-micropython.js','platform/web/public-uiflow-firmware.js','platform/web/uiflow-workbench-profiles.json',
      'platform/web/cardputer-adv-keymap.js','platform/web/vendor/m5stack-models/src/core/DeviceViewer.js',
      'platform/web/vendor/m5stack-models/src/core/components/Button.js','platform/web/vendor/m5stack-models/src/devices/cardputer-adv/index.js']});
  const registry=JSON.parse(await readFile(resolve(site,'platform/web/uiflow-workbench-profiles.json')));
  const expected=registry.profiles.find(row=>row.deviceId===device);assert.ok(expected,'Cardputer default registry row missing');
  report.expected_workbench=expected;
  server=createServer(async(request,response)=>{
    try{
      const path=new URL(request.url,'http://localhost').pathname;
      if(!path.startsWith(basePath)){response.writeHead(404).end();return;}
      const file=resolve(site,decodeURIComponent(path.slice(basePath.length))||'index.html');
      if(!file.startsWith(site+'/')){response.writeHead(403).end();return;}
      // The exported Pages service worker supplies cross-origin isolation.
      response.writeHead(200,{'content-type':mime[extname(file)]||'application/octet-stream','cache-control':'no-cache'});
      response.end(await readFile(file));
    }catch{response.writeHead(404).end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}${basePath}`;report.url=origin;
  browser=await chromium.launch({headless:true,...(process.env.M5_WASM_CHROME?{executablePath:process.env.M5_WASM_CHROME}:{}),
    args:['--enable-webgl','--use-gl=angle',...(process.env.M5_WASM_GPU==='software'?['--use-angle=swiftshader']:['--use-angle=metal','--ignore-gpu-blocklist'])]});
  report.browser=browser.version();workers=await observeWorkerTargets(browser);
  browserCDP=await browser.newBrowserCDPSession();
  page=await browser.newPage({viewport:{width:1440,height:1100}});cdp=await page.context().newCDPSession(page);
  await page.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>route.abort('blockedbyclient'));
  page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>requests.push(request.url()));
  const workbenchURL=new URL(origin);
  if(mode!=='baseline')workbenchURL.searchParams.set('m5-worker-finalization',mode);
  await page.goto(workbenchURL.href,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>crossOriginIsolated&&document.querySelector('#deviceMount')?.dataset.deviceId==='cores3',{}, {timeout:45000});
  await page.evaluate(async({origin,device})=>{
    const {ModelDeviceShell}=await import(new URL('platform/web/model-shell.js?v=20261026h',origin));
    const create=ModelDeviceShell.create;
    ModelDeviceShell.create=async function(...args){
      const shell=await create.apply(this,args);
      if(args[1].id===device){
        globalThis.keyboardShell=shell;globalThis.keyboardModelEvents=[];globalThis.keyboardControls=[];
        shell.on('model-input',event=>{if(['down','up'].includes(event.action))keyboardModelEvents.push({...event,at_ms:performance.now()});});
        shell.on('control',event=>keyboardControls.push({...event,at_ms:performance.now()}));
      }
      return shell;
    };
    const {PublicQemuRuntime}=await import(new URL('platform/web/public-qemu-runtime.js',origin));
    const start=PublicQemuRuntime.prototype.start,input=PublicQemuRuntime.prototype.input;
    PublicQemuRuntime.prototype.start=function(...args){if(args[0].device===device)globalThis.keyboardRuntime=this;return start.apply(this,args);};
    globalThis.keyboardInputs=[];globalThis.keyboardDom=[];
    PublicQemuRuntime.prototype.input=async function(event){
      const row={event:{...event},at_ms:performance.now()};
      if(this===globalThis.keyboardRuntime)keyboardInputs.push(row);
      try{row.response=await input.call(this,event);return row.response;}catch(error){row.error=String(error);throw error;}
    };
    // Capture native browser trust before the public focused-key handlers run.
    for(const type of ['keydown','keyup','pointerdown','pointerup'])window.addEventListener(type,event=>{
      if(event.target===globalThis.keyboardShell?.viewer.renderer.domElement)keyboardDom.push({type,code:event.code||null,key:event.key||null,
        trusted:event.isTrusted,pointer_type:event.pointerType||null,at_ms:performance.now()});
    },true);
    const {PublicMicroPythonRunner}=await import(new URL('platform/web/public-micropython.js',origin));
    const run=PublicMicroPythonRunner.prototype.run;
    PublicMicroPythonRunner.prototype.run=async function(source,options={}){
      const row={source,output:'',phases:[],error:null,result:null};globalThis.keyboardRun=row;
      try{return row.result=await run.call(this,source,{...options,
        onOutput:(...args)=>{row.output+=args[0];options.onOutput?.(...args);},
        onPhase:(...args)=>{row.phases.push(args[0]);options.onPhase?.(...args);}});
      }catch(error){row.error=String(error?.message||error);throw error;}finally{row.finished=true;}
    };
  },{origin,device});
  await page.locator(`button[data-device-id="${device}"]`).click();
  await page.waitForFunction(()=>globalThis.keyboardShell?.device.id==='cardputer-adv',{}, {timeout:45000});
  if(!await page.locator('#runtimeMode').isVisible())await page.locator('.advanced-options > summary').click();
  await page.locator('#runtimeMode').selectOption('browser');
  await page.locator('input[name="firmwareSource"][value="reference"]').check();
  check('public-workbench-default-selected',await page.locator('#referenceExample').inputValue()==='uiflow');
  await page.locator('#startBtn').click();
  await page.waitForFunction(()=>globalThis.keyboardRuntime?.status==='running'&&keyboardRuntime.guestReady(),{}, {timeout:readyTimeout});
  report.initial=await page.evaluate(()=>({evidence:keyboardRuntime.evidence(),generation:keyboardRuntime.generation,
    ready_firmware:keyboardRuntime.profile.readyFirmwareSHA256}));
  const receipt=report.initial.evidence.receipt;
  check('exact-cardputer-default-flash-and-runtime',receipt.deviceId===device&&receipt.firmwareSha256===expected.firmwareSHA256
    &&receipt.uiflowWorkbench?.baseSha256===expected.baseSHA256&&report.initial.ready_firmware===expected.firmwareSHA256
    &&receipt.wasmSha256===report.provenance.runtime_assets['qemu-system-xtensa.wasm']?.sha256,receipt);
  check('all-56-public-model-components-mounted',await page.evaluate(cases=>cases.length===56
    &&cases.every(item=>keyboardShell.model.find(item.component,'button')?.interactive)
    &&keyboardShell.model.keymap.Fn==='key-Fn',CARDPUTER_KEYBOARD_CASES));
  report.renderer=await page.evaluate(()=>{const gl=keyboardShell.viewer.renderer.getContext(),debug=gl.getExtension('WEBGL_debug_renderer_info');
    return {renderer:debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):null,version:gl.getParameter(gl.VERSION)};});
  await page.locator('#pythonSource').fill(source);await page.locator('#pythonRunBtn').click();
  const readyRows=await observe(rows=>rows.some(row=>row.kind==='ready'),'original public IRQ observer ready',readyTimeout);
  const ready=readyRows.find(row=>row.kind==='ready');
  check('editor-source-reached-original-public-runner',await page.evaluate(source=>keyboardRun.source===source,source));
  check('original-cardputer-public-irq-api-ready',ready.api==='MatrixKeyboard.set_callback'&&!ready.pending
    &&Object.keys(ready.states).length===CARDPUTER_KEYBOARD_CODES.length&&Object.values(ready.states).every(value=>value===false),ready);
  const activeSince=Date.now();
  for(const item of cases)for(const method of ['keyboard','pointer']){
    const afterSeq=(await events()).at(-1)?.seq||0;
    const before=await page.evaluate(()=>({model:keyboardModelEvents.length,controls:keyboardControls.length,input:keyboardInputs.length,dom:keyboardDom.length}));
    const trial={physical:item.physical,component:item.component,row:item.row,col:item.col,qcode:item.qcode,
      expected_codes:item.expectedCodes,method,after_seq:afterSeq,requested_hold_ms:holdMs,companion:item.companion};
    report.input_cases.push(trial);
    const canvas=page.locator('#deviceMount .three-device-stage canvas');await canvas.scrollIntoViewIfNeeded();
    if(method==='pointer'){
      trial.pointer=await page.evaluate(findPublicButtonPointerTarget,{componentId:item.component,origin,shellGlobal:'keyboardShell'});
      await page.mouse.move(trial.pointer.clientX,trial.pointer.clientY);
      check(`raycast-${item.physical}`,await page.evaluate(({clientX,clientY,component})=>
        document.elementFromPoint(clientX,clientY)===keyboardShell.viewer.renderer.domElement
        &&keyboardShell.viewer.pick({clientX,clientY})?.component.path===component,trial.pointer),trial.pointer);
    }
    await canvas.focus();
    const code=item.browserCode||'Fn';trial.keyboard_code=method==='keyboard'?code:null;
    trial.down_at_ms=performance.now();
    let companionDown=false;
    try{
      if(method==='keyboard')await nativeKey(code,true);else await page.mouse.down();
      if(item.companion){await nativeKey('Backquote',true);companionDown=true;trial.companion_down_at_ms=performance.now();}
      // Deliberately release on the fixed host pulse, before awaiting a guest
      // acknowledgement. Missing edges remain FAIL; no ack-held diagnostic.
      await page.waitForTimeout(holdMs);
    }finally{
      if(companionDown)await nativeKey('Backquote',false);
      if(method==='keyboard')await nativeKey(code,false);else await page.mouse.up();
      trial.up_at_ms=performance.now();trial.observed_hold_ms=trial.up_at_ms-trial.down_at_ms;
    }
    trial.host=await page.evaluate(before=>({model:keyboardModelEvents.slice(before.model),controls:keyboardControls.slice(before.controls),
      inputs:keyboardInputs.slice(before.input),dom:keyboardDom.slice(before.dom)}),before);
    const expectedQcodes=item.companion?[item.qcode,'grave_accent']: [item.qcode];
    check(`${method}-${item.physical}-actual-model-edges`,trial.host.model.length===expectedQcodes.length*2
      &&[item.component,...(item.companion?['key-Escape']:[])].every(component=>{
        const rows=trial.host.model.filter(row=>row.id===component);return rows.length===2&&rows[0].action==='down'&&rows[1].action==='up';
      }),trial.host.model);
    check(`${method}-${item.physical}-trusted-browser-input`,trial.host.dom.length===expectedQcodes.length*2
      &&trial.host.dom.every(row=>row.trusted)&&trial.host.dom.filter(row=>row.type===(method==='keyboard'?'keydown':'pointerdown')).length>=1,trial.host.dom);
    // Runtime input acknowledgements can arrive after the DOM handler. Wait
    // for those real commands, without retaining or extending the input pulse.
    await page.waitForFunction(({start,count})=>keyboardInputs.length===start+count
      &&keyboardInputs.slice(start).every(row=>row.response?.accepted),{start:before.input,count:expectedQcodes.length*2},{timeout:10000});
    trial.host.inputs=await page.evaluate(start=>keyboardInputs.slice(start),before.input);
    check(`${method}-${item.physical}-original-controller-inputs`,trial.host.inputs.length===expectedQcodes.length*2
      &&expectedQcodes.every(code=>{const rows=trial.host.inputs.filter(row=>(row.event.id||row.event.key)===code);
        return rows.length===2&&rows[0].event.down===true&&rows[1].event.down===false&&rows.every(row=>row.response?.accepted&&!row.error);}),trial.host.inputs);
    const rows=await observe(rows=>item.expectedCodes.every(code=>{
      const pressed=rows.find(row=>row.seq>afterSeq&&row.kind==='state'&&row.code===code&&row.pressed);
      return pressed&&rows.some(row=>row.seq>pressed.seq&&row.kind==='state'&&row.code===code&&!row.pressed)
        &&rows.some(row=>row.seq>afterSeq&&row.kind==='callback'&&row.codes.includes(code));
    }),`${method} ${item.physical} public callback plus press/release`);
    trial.observations=requireCardputerKeyboardObservation({item,afterSeq,events:rows});
    trial.status='PASS';check(`guest-${method}-${item.physical}-irq-press-release`,true,trial.observations);await save();
  }
  check('all-selected-keys-both-public-input-paths',report.input_cases.length===cases.length*2&&report.input_cases.every(row=>row.status==='PASS'));
  if(exitActive){
    await page.waitForTimeout(Math.max(0,activeMs-(Date.now()-activeSince)));
    check('real-irq-observer-remains-active-at-stop',await page.evaluate(()=>!keyboardRun.finished&&!keyboardRun.error));
  }else{
  await page.locator('#pythonInterruptBtn').click();
  await page.waitForFunction(()=>globalThis.keyboardRun?.finished,{}, {timeout:15000});
  report.execution=await page.evaluate(()=>keyboardRun);
  const deinit=(await events()).find(row=>row.kind==='deinit');
  check('public-driver-deinit-and-raw-repl-interrupt',!!deinit&&!report.execution.error&&report.execution.source===source&&report.execution.result?.interrupted
    &&report.execution.result.sessionId===report.initial.evidence.session_id
    &&report.execution.result.consoleEpoch===report.initial.evidence.console_epoch,report.execution.phases);
  }
  check('same-runtime-and-console-through-all-inputs',await page.evaluate(({session,generation,epoch})=>
    keyboardRuntime.sessionId===session&&keyboardRuntime.generation===generation&&keyboardRuntime.consoleEpoch===epoch
    &&!keyboardRuntime.machineEvents.some(row=>row.event==='RESET'),{session:report.initial.evidence.session_id,
      generation:report.initial.generation,epoch:report.initial.evidence.console_epoch}));
  await page.screenshot({path:resolve(out,'keyboard.png'),fullPage:true});
  await stopAndObserve();
  check('no-device-service-requests',!requests.some(url=>/\/api\/v1|:8787\b|:8830\b/.test(url)));
  check('no-page-errors',errors.length===0,errors);report.status='DIAGNOSTIC_PASS';
}catch(error){
  report.failure=String(error?.stack||error);process.exitCode=1;
  if(page&&!page.isClosed()){
    report.failure_state=await page.evaluate(()=>({run:globalThis.keyboardRun,evidence:globalThis.keyboardRuntime?.evidence(),
      model_events:globalThis.keyboardModelEvents,controls:globalThis.keyboardControls,inputs:globalThis.keyboardInputs,dom:globalThis.keyboardDom})).catch(()=>null);
    if(!report.stopped)try{await stopAndObserve();}catch(cleanupError){report.cleanup_failure=String(cleanupError?.stack||cleanupError);}
  }
}finally{
  report.finished_at=new Date().toISOString();await save();
  await cdp?.detach().catch(()=>{});await browserCDP?.detach().catch(()=>{});
  await workers?.detach();await browser?.close();
  await new Promise(resolve=>server?server.close(resolve):resolve());
}
console.log(`Cardputer public IRQ keyboard validation: ${report.status}`);
