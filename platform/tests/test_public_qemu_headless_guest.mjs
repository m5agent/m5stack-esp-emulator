// Opt-in real public-UI guest acceptance. Static hosting; no Device Service.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname,extname,basename} from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {capturePublicQemuProvenance} from './public_qemu_artifacts.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';

const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const site=process.env.M5_PUBLIC_SITE&&resolve(process.env.M5_PUBLIC_SITE);
if(!site){console.log('SKIP: explicit M5_PUBLIC_SITE candidate export required');process.exit(0);}
const device=process.env.M5_QEMU_DEVICE||'atoms3-lite', matrix=['atom-matrix','atom-matrix-v11'].includes(device),basePath=process.env.M5_PUBLIC_BASE_PATH||'/showcase/';
assert.ok(['atoms3-lite','atom-lite','atom-matrix','atom-matrix-v11'].includes(device),'unsupported headless board');
const output=resolve(process.env.M5_PUBLIC_QEMU_OUT||resolve(repo,'.work/public-qemu-headless-'+device));
assert.ok(output.startsWith(resolve(repo,'.work')+'/'),'raw guest evidence belongs in ignored .work');
const uploadPath=process.env.M5_QEMU_UPLOAD&&resolve(process.env.M5_QEMU_UPLOAD);
const timeout=Number(process.env.M5_QEMU_READY_TIMEOUT_MS||180000);
assert.ok(Number.isInteger(timeout)&&timeout>=30000&&timeout<=600000);
await mkdir(output,{recursive:false});
const modules=process.env.M5_WASM_NODE_MODULES||resolve(repo,'platform/tests/node_modules');
const {chromium}=await import(pathToFileURL(resolve(modules,'playwright/index.mjs')));
const checks=[],errors=[],requests=[],workers=[];
const report={kind:'browser-local-qemu-headless-acceptance',device,public_ui:true,status:'FAIL',
  started_at:new Date().toISOString(),checks,errors,requests,workers,
  scope:'Same-browser original RGB()/USER input, RMT-decoded digital color, model readback and Worker cleanup',
  device_complete:false,hardware_pass:false,device_status:matrix?'partial':'selected-behaviors-only',
  limitations:matrix?['Only uniform 25-LED frames are mapped to the model; nonuniform spatial order is unvalidated.',
    'IMU behavior did not satisfy the native board-axis oracle; API/source interpretation remains under review and this RGB/button fixture does not validate it.']:[]};
let server,browser,page,workerTargets;
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json',
  '.wasm':'application/wasm','.css':'text/css','.png':'image/png','.webp':'image/webp','.svg':'image/svg+xml'};
function check(name,ok,details){checks.push({name,ok,details});assert.ok(ok,name);console.log(name);}
async function guest(kind,predicate=()=>true){
  const end=Date.now()+timeout;let nextProgress=0;
  while(Date.now()<end){
    const observation=await page.evaluate(()=>({serial:globalThis.headlessRun?.runtime.serial||'',errors:globalThis.headlessRun?.errors||[],
      banner:document.querySelector('#errorBanner')?.hidden?'':document.querySelector('#errorBanner')?.textContent}));
    if(Date.now()>=nextProgress){await writeFile(resolve(output,'guest-progress.json'),JSON.stringify({waiting_for:kind,...observation},null,2)+'\n');nextProgress=Date.now()+10000;}
    if(observation.errors.length||observation.banner)throw new Error([...observation.errors,observation.banner].filter(Boolean).join('\n'));
    if(/Traceback \(most recent call last\):|Guru Meditation Error|Interrupt wdt timeout|A fatal error occurred/.test(observation.serial))throw new Error('Guest panic or Python traceback');
    const events=observation.serial.split('\n').filter(line=>line.startsWith('M5_BROWSER_PROBE ')).flatMap(line=>{
      try{return [JSON.parse(line.slice(17))];}catch{return [];}
    });
    const found=events.find(event=>event.kind===kind&&predicate(event));if(found)return found;
    await new Promise(resolve=>setTimeout(resolve,200));
  }
  throw new Error('Guest '+kind+' timed out');
}
async function outputState({color,pressed,after=0}){
  await page.waitForFunction(({color,pressed,after})=>{
    const run=globalThis.headlessRun,s=run?.runtime.lastDeviceState;
    return (Array.isArray(s?.led_rgb)?s.led_rgb.length===25&&s.led_rgb.every(value=>value===color):s?.led_rgb===color)&&s.pressed===pressed&&s.led_frames>after;
  },{color,pressed,after},{timeout:30000});
  return page.evaluate(()=>structuredClone(headlessRun.runtime.lastDeviceState));
}
async function modelReadback(state){
  const handle=await page.waitForFunction(expected=>{
    const shell=globalThis.headlessShell,button=shell?.model.find('button','button'),matrix=Array.isArray(expected.led_rgb);
    const targets=matrix?Array.from({length:25},(_,index)=>'led'+index):['rgb'];
    const colors=matrix?expected.led_rgb:[expected.led_rgb],leds=targets.map(target=>shell?.model.find(target,'led'));
    if(!button||leds.some(led=>!led)||shell.display||shell.observedOutput?.led_frames!==expected.led_frames
      ||shell.observedOutput?.pressed!==expected.pressed||JSON.stringify(shell.observedOutput?.led_rgb)!==JSON.stringify(expected.led_rgb))return false;
    const values=leds.map(led=>led.getState());
    if(values.some((value,index)=>value.color!=='#'+colors[index].toString(16).padStart(6,'0')
      ||value.brightness!==(colors[index]?1:0)||leds[index].runtimeKnown!==true)
      ||button.getState().pressed!==expected.pressed)return false;
    return {leds:values,known:leds.every(led=>led.runtimeKnown),pressed:button.getState().pressed,rendered_outputs:shell.observedOutputRenders,
      spatial_mapping:matrix?'uniform-only-v1':'single-led'};
  },state,{timeout:30000});
  const value=await handle.jsonValue();await handle.dispose();return value;
}
try{
  report.provenance=await capturePublicQemuProvenance({repo,site,testScript:'platform/tests/test_public_qemu_headless_guest.mjs'});
  server=createServer(async(request,response)=>{
    try{
      const path=new URL(request.url,'http://localhost').pathname;
      if(!path.startsWith(basePath)){response.writeHead(404).end();return;}
      const file=resolve(site,decodeURIComponent(path.slice(basePath.length))||'index.html');
      if(!file.startsWith(site+'/')){response.writeHead(403).end();return;}
      // The exported Pages Service Worker must provide isolation itself.
      response.writeHead(200,{'content-type':mime[extname(file)]||'application/octet-stream','cache-control':'no-cache'});
      response.end(await readFile(file));
    }catch{response.writeHead(404).end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}${basePath}`;report.url=origin;
  browser=await chromium.launch({headless:true,...(process.env.M5_WASM_CHROME?{executablePath:process.env.M5_WASM_CHROME}:{}),
    args:['--enable-webgl','--use-gl=angle',...(process.env.M5_WASM_GPU==='hardware'?['--use-angle=metal','--ignore-gpu-blocklist']:['--use-angle=swiftshader'])]});
  workerTargets=await observeWorkerTargets(browser);
  report.browser=browser.version();page=await browser.newPage({viewport:{width:1200,height:900}});
  await page.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>route.abort('blockedbyclient'));
  page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>requests.push({url:request.url(),method:request.method()}));
  page.on('worker',worker=>{
    const item={kind:worker.url().includes('/public-qemu-engine.js')?'engine':'pthread',closed:false};workers.push(item);
    worker.on('close',()=>{item.closed=true;});
  });
  await page.goto(origin,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>crossOriginIsolated,{}, {timeout:45000});
  check('pages-service-worker-isolation',await page.evaluate(()=>crossOriginIsolated&&typeof SharedArrayBuffer==='function'));
  report.admission=await page.evaluate(async({origin,device})=>{
    const config=await (await fetch(new URL('platform/web/site-config.json',origin))).json();
    const {loadQemuBrowserProfiles,getQemuBrowserProfile}=await import(new URL('platform/web/public-qemu-profiles.js',origin));
    const registry=await loadQemuBrowserProfiles({root:origin}),allowCandidateProfiles=config.publication_eligible===false;
    const profile=getQemuBrowserProfile(device,registry,{allowCandidateProfiles});
    if(!profile||profile.display!==null||!['single-ws2812-qom-v1','matrix-ws2812-qom-v1'].includes(profile.outputs.kind))throw new Error('Missing explicit headless browser profile');
    if(profile.admission==='candidate'&&(!allowCandidateProfiles||!config.browser_candidate_profiles?.includes(device)))throw new Error('Unselected candidate');
    const {ModelDeviceShell}=await import(new URL('platform/web/model-shell.js?v=20261026h',origin)),create=ModelDeviceShell.create;
    ModelDeviceShell.create=async function(...args){
      const shell=await create.apply(this,args);
      if(args[1].id===device){
        globalThis.headlessShell=shell;shell.observedOutputRenders=0;
        shell.viewer.on('render',()=>{if(globalThis.headlessRun?.runtime.lastDeviceState){
          shell.observedOutputRenders++;shell.observedOutput=structuredClone(headlessRun.runtime.lastDeviceState);
        }});
      }
      return shell;
    };
    const {PublicQemuRuntime}=await import(new URL('platform/web/public-qemu-runtime.js',origin)),start=PublicQemuRuntime.prototype.start;
    PublicQemuRuntime.prototype.start=function(...args){
      if(args[0].device===device){
        const runtime=this,onError=this.onError,input=this.input,ask=this.ask,errors=[],inputs=[],operations=[];
        this.onError=error=>{errors.push(error.message);onError(error);};
        this.input=function(event){inputs.push(structuredClone(event));return input.call(this,event);};
        this.ask=function(op,...rest){operations.push(op);return ask.call(this,op,...rest);};
        globalThis.headlessRun={runtime,profile,errors,inputs,operations};
      }
      return start.apply(this,args);
    };
    return {admission:profile.admission,publication_eligible:config.publication_eligible,profile};
  },{origin,device});
  await page.waitForFunction(()=>document.querySelector('#deviceMount')?.dataset.deviceId==='cores3',{}, {timeout:45000});
  await page.locator(`[data-device-id="${device}"]`).click();
  await page.waitForFunction(device=>globalThis.headlessShell?.device.id===device,device, {timeout:45000});
  report.webgl_renderer=await page.evaluate(()=>{
    const gl=headlessShell.viewer.renderer.getContext(),info=gl.getExtension('WEBGL_debug_renderer_info');
    return info?gl.getParameter(info.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);
  });
  if(process.env.M5_WASM_GPU==='hardware')assert.doesNotMatch(report.webgl_renderer,/swiftshader|software/i);
  await page.locator('.advanced-options > summary').click();await page.locator('#runtimeMode').selectOption('browser');
  await page.locator('input[name="firmwareSource"][value="reference"]').check();
  check('public-headless-reference-label',(await page.locator('#referenceTitle').textContent()).includes('RGB 与按键示例'));
  check('public-headless-reference-instructions',!(await page.locator('#referenceDescription').textContent()).includes('屏幕'));
  if(uploadPath){
    const bytes=await readFile(uploadPath),hash=createHash('sha256').update(bytes).digest('hex');
    check('local-upload-exact-reviewed-firmware',hash===report.admission.profile.fixture.firmwareSHA256&&bytes.length===report.admission.profile.flashMb*1048576);
    report.upload={name:basename(uploadPath),bytes:bytes.length,sha256:hash};
    await page.locator('input[name="firmwareSource"][value="local"]').check();
    await page.locator('#firmwareFile').setInputFiles(uploadPath);
    await page.locator('#firmwareSha').fill(hash);
  }
  await page.locator('#startBtn').click();
  const ready=await guest('ready',event=>event.device===device&&event.output===(device==='atoms3-lite'?'ws2812-rmt-gpio35':'ws2812-rmt-gpio27'));report.ready=ready;
  check('original-firmware-board-and-output-route',ready.board===(matrix?141:device==='atoms3-lite'?137:128)&&ready.input==='button'&&(!matrix||ready.leds===25),ready);
  const idle=await outputState({color:0x204060,pressed:false});report.idle={qom:idle,model:await modelReadback(idle)};
  check('no-lcd-or-frame-transport',await page.evaluate(()=>!headlessShell.display&&headlessRun.runtime.profile.display===null
    &&headlessRun.runtime.lastFrame===null&&headlessRun.runtime.receipt.frameTransport===null&&document.querySelector('#nativeScreenBtn').hidden));
  const key=await page.evaluate(()=>Object.entries(headlessShell.model.keymap).find(([,target])=>target==='button')?.[0]);
  assert.ok(key,'the actual model button must expose a keyboard binding');report.input_keyboard=key;
  await page.locator('#deviceMount .three-device-stage canvas').focus();await page.keyboard.down(key);
  report.count=await guest('count',event=>event.count===1);report.press=await guest('pressed',event=>event.seq===report.count.seq-1);
  const down=await outputState({color:0x40A020,pressed:true,after:idle.led_frames});report.down={qom:down,model:await modelReadback(down)};
  await page.screenshot({path:resolve(output,'pressed-rgb.png'),fullPage:true});
  await page.keyboard.up(key);report.release=await guest('released',event=>event.count===1);
  const up=await outputState({color:0x204060,pressed:false,after:down.led_frames});report.up={qom:up,model:await modelReadback(up)};
  check('same-guest-rmt-output-and-qmp-button-loop',idle.led_frames<down.led_frames&&down.led_frames<up.led_frames,report.up);
  check('read-only-output-and-no-display-negative-controls',await page.evaluate(async()=>{
    for(const [op,value] of [['frame',{}],['outputs',{path:'/machine/other'}],['outputs',{property:'led-rgb',value:0}]]){
      try{await headlessRun.runtime.ask(op,value);return false;}catch{}
    }
    try{await headlessRun.runtime.input({type:'touch',x:0,y:0,down:true});return false;}catch{}
    return true;
  }));
  const inputs=await page.evaluate(()=>headlessRun.inputs);report.inputs=inputs;
  check('exact-model-button-edges-and-no-output-echo',inputs.filter(input=>input.type==='button').length===2
    &&inputs[0].down===true&&inputs[1].down===false,inputs);
  check('automatic-poll-never-requests-a-frame',await page.evaluate(()=>headlessRun.operations.filter(op=>op==='frame').length===1));
  await writeFile(resolve(output,'running.json'),JSON.stringify(await page.evaluate(()=>headlessRun.runtime.evidence()),null,2)+'\n');
  await page.evaluate(()=>{
    const frame=headlessRun.runtime.iframe,remove=frame.remove;globalThis.headlessDeferredRemoval={frame,remove,requests:0};
    frame.remove=()=>{headlessDeferredRemoval.requests++;};
  });
  await page.locator('#stopBtn').click();await page.waitForFunction(()=>document.querySelector('#runtimeStatus').dataset.status==='stopped',{}, {timeout:30000});
  const stopped=await page.evaluate(()=>headlessRun.runtime.evidence());report.runtime=stopped.receipt;report.session_id=stopped.session_id;report.cleanup=stopped.cleanup;
  await writeFile(resolve(output,'stopped.json'),JSON.stringify(stopped,null,2)+'\n');
  check('clean-guest-and-worker-stop',stopped.cleanup?.gracefulExit&&stopped.cleanup.exitCode===0&&stopped.cleanup.workersAtExit===0
    &&stopped.cleanup.explicitWorkerDisposal&&stopped.cleanup.disposal?.workersRemaining===0
    &&stopped.cleanup.disposal?.workersTerminatedByDispose===0&&stopped.cleanup.engineOwnership?.engineCloseNotificationReceived
    &&stopped.cleanup.engineOwnership?.engineSelfCloseNotifications===1
    &&stopped.cleanup.engineOwnership?.engineNormalTerminations===0
    &&stopped.cleanup.engineOwnership?.engineFallbackTerminations===0,stopped.cleanup);
  const expectedWorkerTargets=stopped.cleanup.workersCreated+1;
  assert.ok(Number.isInteger(expectedWorkerTargets)&&expectedWorkerTargets>=2,'same-run pthread creation count is required');
  const nestedClose=await workerTargets.waitUntilOnly({minimumObserved:expectedWorkerTargets,
    allowedUrlPart:'/public-qemu-engine.js',timeoutMs:30000});
  const held=await page.evaluate(()=>({connected:headlessDeferredRemoval.frame.isConnected,requests:headlessDeferredRemoval.requests}));
  report.iframe_removal_control={...held,removal_deferred_by_harness:true};
  check('created-pthreads-close-before-iframe-finalization',nestedClose.ok&&held.connected&&held.requests===1
    &&nestedClose.observed.length===expectedWorkerTargets
    &&nestedClose.observed.filter(target=>target.url.includes('/public-qemu-engine.js')).length===1,
    {worker_targets:nestedClose,playwright_worker_events:workers,iframe_removal:held});
  await page.evaluate(()=>{const held=headlessDeferredRemoval;held.remove.call(held.frame);delete globalThis.headlessDeferredRemoval;});
  const targetClose=await workerTargets.waitUntilClosed({minimumObserved:expectedWorkerTargets});
  report.worker_targets={before_removal:nestedClose,after_removal:targetClose};
  check('engine-and-created-pthreads-close-after-iframe-finalization',targetClose.ok
    &&targetClose.observed.length===expectedWorkerTargets
    &&targetClose.observed.filter(target=>target.url.includes('/public-qemu-engine.js')).length===1,targetClose);
  check('no-leftover-iframe',await page.locator('iframe').count()===0);
  check('no-device-service-or-page-errors',errors.length===0&&!requests.some(request=>/\/api\/v1|:8787\b|:8830\b/.test(request.url)),errors);
  check('stopped-model-output-unknown',await page.evaluate(()=>{const matrix=headlessRun.profile.outputs.kind==='matrix-ws2812-qom-v1';return (matrix?Array.from({length:25},(_,i)=>'led'+i):['rgb']).every(target=>headlessShell.model.find(target,'led').runtimeKnown===false);}));
  report.status='PASS';
}catch(error){
  report.error=error.message;process.exitCode=1;
  if(page){
    await writeFile(resolve(output,'failure-state.json'),JSON.stringify(await page.evaluate(()=>globalThis.headlessRun?.runtime.evidence()).catch(()=>null),null,2)+'\n');
    await page.screenshot({path:resolve(output,'failure.png'),fullPage:true}).catch(()=>{});
  }
}finally{
  if(page)await page.evaluate(()=>globalThis.headlessRun?.runtime.stop()).catch(()=>{});
  await workerTargets?.detach();
  await browser?.close();if(server)await new Promise(resolve=>server.close(resolve));
  report.finished_at=new Date().toISOString();await writeFile(resolve(output,'report.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
}
