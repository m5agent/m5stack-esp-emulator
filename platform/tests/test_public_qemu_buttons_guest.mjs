// Opt-in browser-WASM validation through the public model, UART and UIFlow API.
// The page executes real firmware. This test does not use Device Service.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';
import {capturePublicQemuProvenance,QEMU_EXECUTED_WEB_PATHS} from './public_qemu_artifacts.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';
import {PUBLIC_QEMU_BUTTON_CASES,PUBLIC_QEMU_BUTTON_LIMITS,PM1_BUTTON_OBSERVER_SETUP} from './public_qemu_button_cases.mjs';
import {findPublicButtonPointerTarget} from './public_qemu_button_pointer.mjs';

const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const site=process.env.M5_PUBLIC_SITE&&resolve(process.env.M5_PUBLIC_SITE);
if(!site){console.log('SKIP: explicit M5_PUBLIC_SITE export required');process.exit(0);}
const device=process.env.M5_QEMU_DEVICE||'stickc-plus';
const cases=PUBLIC_QEMU_BUTTON_CASES[device];
assert.ok(cases?.length,`No complete public button observer case for ${device}; ${PUBLIC_QEMU_BUTTON_LIMITS[device]||''}`);
const out=resolve(process.env.M5_PUBLIC_QEMU_OUT||resolve(repo,'.work/public-qemu-buttons-'+device));
assert.ok(out.startsWith(resolve(repo,'.work')+'/'),'raw browser evidence belongs in ignored .work');
await mkdir(out,{recursive:false});
const timeout=Number(process.env.M5_QEMU_READY_TIMEOUT_MS||180000);
assert.ok(Number.isSafeInteger(timeout)&&timeout>=30000&&timeout<=600000);
const holdMs=Number(process.env.M5_QEMU_BUTTON_HOLD_MS||250);
assert.ok(Number.isSafeInteger(holdMs)&&holdMs>=50&&holdMs<=1000);
const basePath=process.env.M5_PUBLIC_BASE_PATH||'/showcase/';
const modules=process.env.M5_WASM_NODE_MODULES||resolve(repo,'platform/tests/node_modules');
const {chromium}=await import(pathToFileURL(resolve(modules,'playwright/index.mjs')));
const observerPath='tests/browser-qemu/uiflow_workbench/button_observer.py';
const observer=await readFile(resolve(repo,observerPath),'utf8');
const nonce=randomUUID(),specs=cases.map(item=>[item.id,item.owner]);
const pm1Setup=PM1_BUTTON_OBSERVER_SETUP[device]||{};
const source=`BUTTON_SPECS = ${JSON.stringify(specs)}\nBUTTON_PM1_SETUP = ${JSON.stringify(pm1Setup)}\nRUN_NONCE = ${JSON.stringify(nonce)}\n`+observer;
const digest=value=>createHash('sha256').update(value).digest('hex');
const checks=[],errors=[];
const report={kind:'browser-qemu-uiflow-buttons',device,status:'FAIL',started_at:new Date().toISOString(),
  checks,errors,nonce,input_cases:[],hardware_validation:'NOT RUN',
  scope:'Exact firmware/profile, original public M5.update/Button APIs and real public-model keyboard and mouse input.',
  observer:{path:observerPath,sha256:digest(observer),executed_sha256:digest(source)},
  pmic_application_setup:pm1Setup,
  input_registry:{path:'platform/tests/public_qemu_button_cases.mjs',
    sha256:digest(await readFile(resolve(repo,'platform/tests/public_qemu_button_cases.mjs')))},
  pointer_helper:{path:'platform/tests/public_qemu_button_pointer.mjs',
    sha256:digest(await readFile(resolve(repo,'platform/tests/public_qemu_button_pointer.mjs')))},
  limits:PUBLIC_QEMU_BUTTON_LIMITS[device]?[PUBLIC_QEMU_BUTTON_LIMITS[device]]:[]};
const check=(name,ok,details)=>{checks.push({name,ok,details});assert.ok(ok,name);console.log(name);};
let server,browser,page,workers;
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json',
  '.wasm':'application/wasm','.css':'text/css','.png':'image/png','.webp':'image/webp','.svg':'image/svg+xml'};
const events=async()=>page.evaluate(nonce=>{
  const output=globalThis.buttonRun?.output||'';
  return output.split('\n').filter(line=>line.startsWith('M5_BUTTON_OBSERVER ')).flatMap(line=>{
    try{const item=JSON.parse(line.slice(19));return item.nonce===nonce?[item]:[];}catch{return [];}
  });
},nonce);
async function observe(predicate,description,waitMs=30000){
  const deadline=Date.now()+waitMs;
  for(;;){
    const state=await page.evaluate(()=>({error:globalThis.buttonRun?.error,output:globalThis.buttonRun?.output||''}));
    if(state.error)throw new Error(state.error);
    if(/Traceback \(most recent call last\):|Guru Meditation Error|Interrupt wdt timeout/.test(state.output))throw new Error('Guest traceback or panic');
    const rows=await events(),result=rows.find(predicate);
    if(result)return result;
    if(Date.now()>=deadline)throw new Error(`Guest button observation timed out: ${description}`);
    await page.waitForTimeout(50);
  }
}
try{
  report.provenance=await capturePublicQemuProvenance({repo,site,
    webPaths:[...QEMU_EXECUTED_WEB_PATHS,'platform/web/public-micropython.js',
      'platform/web/public-uiflow-firmware.js','platform/web/uiflow-workbench-profiles.json'],
    testScript:'platform/tests/test_public_qemu_buttons_guest.mjs'});
  server=createServer(async(request,response)=>{
    try{
      const path=new URL(request.url,'http://localhost').pathname;
      if(!path.startsWith(basePath)){response.writeHead(404).end();return;}
      const file=resolve(site,decodeURIComponent(path.slice(basePath.length))||'index.html');
      if(!file.startsWith(site+'/')){response.writeHead(403).end();return;}
      response.writeHead(200,{'content-type':mime[extname(file)]||'application/octet-stream','cache-control':'no-cache'});
      response.end(await readFile(file));
    }catch{response.writeHead(404).end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}${basePath}`;report.url=origin;
  browser=await chromium.launch({headless:true,...(process.env.M5_WASM_CHROME?{executablePath:process.env.M5_WASM_CHROME}:{}),
    args:['--enable-webgl','--use-gl=angle',...(process.env.M5_WASM_GPU==='hardware'?['--use-angle=metal','--ignore-gpu-blocklist']:['--use-angle=swiftshader'])]});
  workers=await observeWorkerTargets(browser);page=await browser.newPage({viewport:{width:1200,height:900}});
  report.browser=browser.version();
  await page.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>route.abort('blockedbyclient'));
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(origin,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>crossOriginIsolated,{}, {timeout:45000});
  await page.waitForFunction(()=>document.querySelector('#deviceMount')?.dataset.deviceId==='cores3',{}, {timeout:45000});
  await page.evaluate(async({device,origin})=>{
    const {ModelDeviceShell}=await import(new URL('platform/web/model-shell.js?v=20261026h',origin));
    const create=ModelDeviceShell.create;
    ModelDeviceShell.create=async function(...args){
      const shell=await create.apply(this,args);
      if(args[1].id===device){
        globalThis.buttonShell=shell;globalThis.buttonControlEvents=[];
        shell.on('control',event=>buttonControlEvents.push({...event,observed_at_ms:performance.now()}));
        shell.on('touch',event=>buttonControlEvents.push({...event,id:'screen',observed_at_ms:performance.now()}));
      }
      return shell;
    };
    const {PublicQemuRuntime}=await import(new URL('platform/web/public-qemu-runtime.js',origin));
    const start=PublicQemuRuntime.prototype.start;
    PublicQemuRuntime.prototype.start=function(...args){
      if(args[0].device===device)globalThis.buttonRuntime=this;
      return start.apply(this,args);
    };
  },{device,origin});
  if(device==='cores3'){
    await page.locator('button[data-device-id="atom-matrix"]').click();
    await page.waitForFunction(()=>document.querySelector('#deviceMount')?.dataset.deviceId==='atom-matrix');
  }
  await page.locator(`button[data-device-id="${device}"]`).click();
  await page.waitForFunction(device=>globalThis.buttonShell?.device.id===device,device,{timeout:45000});
  if(!await page.locator('#runtimeMode').isVisible())await page.locator('.advanced-options > summary').click();
  await page.locator('#runtimeMode').selectOption('browser');
  await page.locator('input[name="firmwareSource"][value="reference"]').check();
  await page.locator('#startBtn').click();
  await page.waitForFunction(()=>globalThis.buttonRuntime?.status==='running',{}, {timeout});
  check('public-ui-started-browser-session',true,await page.evaluate(()=>buttonRuntime.evidence().receipt));
  await page.evaluate(async({source,origin})=>{
    const {PublicMicroPythonRunner}=await import(new URL('platform/web/public-micropython.js',origin));
    const runner=new PublicMicroPythonRunner(buttonRuntime);
    const run={runner,output:'',phases:[],result:null,error:null};globalThis.buttonRun=run;
    run.pending=runner.run(source,{timeoutMs:120000,onOutput:text=>{run.output+=text;},onPhase:phase=>run.phases.push(phase)})
      .then(result=>{run.result=result;},error=>{run.error=String(error?.message||error);});
  },{source,origin});
  const ready=await observe(row=>row.kind==='ready','ready',timeout);
  check('original-button-api-probe-ready',Object.keys(ready.states).length===cases.length
    &&cases.every(item=>ready.states[item.id]===false),ready);
  if(PM1_BUTTON_OBSERVER_SETUP[device])check('explicit-pm1-user-application-irq-mode',ready.pmic_setup?.applied===true
    &&ready.pmic_setup.configuration_api===pm1Setup.configuration_api
    &&ready.pmic_setup.api===(pm1Setup.configuration_api==='m5pm1-python-driver'
      ?'M5PM1.disable_single_click_reset+set_button_timing':'machine.I2C.readfrom_mem+writeto_mem')
    &&ready.pmic_setup.click_window_ms===500
    &&ready.pmic_setup.cfg49_after===((ready.pmic_setup.cfg49_before&~7)|5)
    &&ready.pmic_setup.cfg4a_before===ready.pmic_setup.cfg4a_after,ready.pmic_setup);
  for(const item of cases)for(const method of item.mode==='touch-edges'?['pointer']:['keyboard','pointer']){
    const before=await events(),afterSeq=before.at(-1)?.seq||0;
    const controlsBefore=await page.evaluate(()=>buttonControlEvents.length);
    let key=null,domKey=null,pointer=null,downAt,upAt;
    const canvas=page.locator('#deviceMount .three-device-stage canvas');
    await canvas.scrollIntoViewIfNeeded();
    if(method==='keyboard'){
      key=await page.evaluate(component=>Object.entries(buttonShell.model.keymap).find(([,path])=>path===component)?.[0],item.component);
      assert.ok(key,`${device}/${item.component} has no focused public keyboard alias`);
      domKey=/^Key[A-Z]$/.test(key)?key.slice(3).toLowerCase():key==='Space'?'Space':key;
      await canvas.focus();
      downAt=performance.now();await page.keyboard.down(domKey);
      try{await page.waitForTimeout(holdMs);}finally{await page.keyboard.up(domKey);}upAt=performance.now();
    }else if(item.mode==='touch-edges'){
      pointer=await page.evaluate(async({point,origin})=>{
        const {Vector3}=await import(new URL('platform/web/vendor/three/three.module.js',origin));
        const {display,viewer}=buttonShell;
        const projected=display.panel.localToWorld(new Vector3(
          ((point.x+0.5)/display.width-0.5)*display.size[0],
          (0.5-(point.y+0.5)/display.height)*display.size[1],0,
        )).project(viewer.camera);
        const rect=viewer.renderer.domElement.getBoundingClientRect();
        const clientX=rect.left+(projected.x+1)*rect.width/2,clientY=rect.top+(1-projected.y)*rect.height/2;
        if(document.elementFromPoint(clientX,clientY)!==viewer.renderer.domElement)
          throw new Error('Projected PaperS3 touch is occluded');
        return {clientX,clientY,point};
      },{point:item.point,origin});
      await page.mouse.move(pointer.clientX,pointer.clientY);
      downAt=performance.now();await page.mouse.down();
      try{await page.waitForTimeout(holdMs);}finally{await page.mouse.up();}upAt=performance.now();
    }else{
      pointer=await page.evaluate(findPublicButtonPointerTarget,{componentId:item.component,origin});
      await page.mouse.move(pointer.clientX,pointer.clientY);
      const verified=await page.evaluate(({clientX,clientY,component})=>{
        const canvas=buttonShell.viewer.renderer.domElement;
        return document.elementFromPoint(clientX,clientY)===canvas
          &&buttonShell.viewer.pick({clientX,clientY})?.component.path===component;
      },pointer);
      assert.ok(verified,`${device}/${item.component} pointer target changed before the real mouse press`);
      downAt=performance.now();await page.mouse.down();
      try{await page.waitForTimeout(holdMs);}finally{await page.mouse.up();}upAt=performance.now();
    }
    let pressed=null,released=null,event=null;
    if(item.mode==='driver-edges'||item.mode==='touch-edges'){
      pressed=await observe(row=>row.kind==='state'&&row.button===item.id&&row.pressed===true&&row.seq>afterSeq,`${item.id} pressed`);
      released=await observe(row=>row.kind==='state'&&row.button===item.id&&row.pressed===false&&row.seq>pressed.seq,`${item.id} released`);
    }else event=await observe(row=>row.kind==='event'&&row.button===item.id&&row.seq>afterSeq
      &&['wasPressed','wasClicked','wasHold'].includes(row.method),`${item.id} PMIC event`);
    const heartbeat=await observe(row=>row.kind==='heartbeat'&&row.seq>(released?.seq||event?.seq||0)
      &&row.states[item.id]===false,`${item.id} released heartbeat`);
    const modelEvents=await page.evaluate(start=>buttonControlEvents.slice(start),controlsBefore);
    check(`${method}-${item.id}-actual-model-down-and-up`,modelEvents.length===2&&modelEvents[0].down===true
      &&modelEvents[1].down===false&&modelEvents[0].id===item.id&&modelEvents[1].id===item.id,modelEvents);
    if(item.mode==='touch-edges')check('gt911-original-logical-coordinates',
      ['x','y'].every(axis=>Math.abs(modelEvents[0][axis]-item.point[axis])<=2
        &&Math.abs(pressed[axis]-modelEvents[0][axis])<=1),{pressed,model:modelEvents[0]});
    const input={...item,method,keyboard:key,dom_key:domKey,pointer,model_events:modelEvents,
      requested_hold_ms:holdMs,observed_hold_ms:upAt-downAt,
      model_hold_ms:modelEvents[1].observed_at_ms-modelEvents[0].observed_at_ms,
      after_seq:afterSeq,pressed,released,event,heartbeat};
    report.input_cases.push(input);check(`guest-${method}-${item.id}-${item.mode}`,true,input);
  }
  await page.evaluate(()=>buttonRun.runner.interrupt());
  await page.waitForFunction(()=>!buttonRun.runner.busy,{}, {timeout:30000});
  report.execution=await page.evaluate(()=>({output:buttonRun.output,phases:buttonRun.phases,result:buttonRun.result,error:buttonRun.error}));
  check('probe-interrupt-returned-through-raw-repl',!report.execution.error&&report.execution.result?.interrupted===true,report.execution.phases);
  report.running=await page.evaluate(()=>buttonRuntime.evidence());
  await page.screenshot({path:resolve(out,'buttons.png'),fullPage:true});
  await page.locator('#stopBtn').click();
  await page.waitForFunction(()=>buttonRuntime.status==='stopped',{}, {timeout:30000});
  report.stopped=await page.evaluate(()=>buttonRuntime.evidence());
  const cleanup=report.stopped.cleanup;
  check('normal-browser-worker-cleanup',cleanup?.gracefulExit&&cleanup.exitCode===0&&cleanup.workersAtExit===0
    &&cleanup.disposal?.workersTerminatedByDispose===0&&cleanup.engineOwnership?.engineFallbackTerminations===0,cleanup);
  report.worker_targets=await workers.waitUntilClosed({minimumObserved:cleanup.workersCreated+1,timeoutMs:120000});
  check('actual-worker-targets-disappeared',report.worker_targets.ok,report.worker_targets);
  check('browser-page-free-of-errors',errors.length===0,errors);
  report.status='PASS';
}catch(error){
  report.failure=String(error?.stack||error);
  if(page&&!page.isClosed()){
    report.failure_state=await page.evaluate(()=>({output:globalThis.buttonRun?.output,error:globalThis.buttonRun?.error,
      evidence:globalThis.buttonRuntime?.evidence(),banner:document.querySelector('#errorBanner')?.textContent})).catch(()=>null);
    report.failure_stopped_evidence=await page.evaluate(async()=>{
      const runtime=globalThis.buttonRuntime;if(!runtime)return null;
      await runtime.stop();
      const evidence=runtime.evidence(),frame=evidence.last_frame;
      const {pixels,...frameSummary}=frame||{};
      return {session_id:evidence.session_id,console_epoch:evidence.console_epoch,status:runtime.status,
        stopped_at:evidence.stopped_at,receipt:evidence.receipt,cleanup:evidence.cleanup,
        machine_events:evidence.machine_events,last_frame:frame?frameSummary:null};
    }).catch(error=>({capture_error:String(error?.message||error)}));
    report.failure_worker_targets=await workers?.waitUntilClosed({minimumObserved:1,timeoutMs:30000}).catch(()=>null);
  }
  throw error;
}finally{
  report.finished_at=new Date().toISOString();await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');
  await workers?.detach();await browser?.close();await new Promise(resolve=>server?server.close(resolve):resolve());
}
console.log(`${device} public-model/UIFlow button validation passed`);
