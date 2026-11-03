// Opt-in browser performance observer for the same explicit merged BIN in two
// production browser adapters. No guest state, clock, frame cadence or input is
// replaced. Raw output is confined to ignored .work storage.
import assert from 'node:assert/strict';
import {createHash,randomUUID} from 'node:crypto';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir,stat} from 'node:fs/promises';
import {dirname,extname,resolve,sep} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import os from 'node:os';
import {summarizeEmulatorRun as summary} from './emulator_performance_summary.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';
import {DEMO_FIRMWARE} from '../web/public-demo-firmware.js';

const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const engine=process.env.M5_BENCH_ENGINE||'qemu';
const device=process.env.M5_BENCH_DEVICE||'stackchan';
const firmwareSource=process.env.M5_BENCH_SOURCE||'local';
assert.ok(['local','default-compose'].includes(firmwareSource),'Firmware source must be local or default-compose');
assert.ok(firmwareSource!=='default-compose'||engine==='qemu'&&device==='cores3','Default composition is limited to the fixed CoreS3 reference');
const opponentProducts={stackchan:'m5stack-k151',stopwatch:'m5stack-stopwatch'};
assert.ok(['qemu','esp32sim'].includes(engine));
assert.ok(Object.hasOwn(opponentProducts,device)||firmwareSource==='default-compose','Unsupported comparison device');
if((firmwareSource==='local'&&!process.env.M5_BENCH_IMAGE)||!process.env.M5_BENCH_IMAGE_SHA256||!process.env.M5_BENCH_OUT){
  console.log('SKIP: explicit image SHA, output and (for local source) image path required');process.exit(0);
}
const image=firmwareSource==='local'?resolve(process.env.M5_BENCH_IMAGE):null,imageBytes=image?await readFile(image):null;
const firmwareSHA=imageBytes?sha(imageBytes):process.env.M5_BENCH_IMAGE_SHA256;
assert.equal(firmwareSHA,process.env.M5_BENCH_IMAGE_SHA256,'Explicit firmware SHA mismatch');
if(firmwareSource==='default-compose')assert.equal(firmwareSHA,DEMO_FIRMWARE.firmwareSHA256,'Default composition must keep the stock fixture identity');
const out=resolve(process.env.M5_BENCH_OUT);
assert.ok(out.startsWith(resolve(repo,'.work')+sep),'Raw evidence must remain under .work');
try{await stat(out);throw Error('Output exists; choose a fresh output directory');}catch(e){if(e.code!=='ENOENT')throw e;}
await mkdir(out,{recursive:true});
await writeFile(resolve(out,'harness.mjs'),await readFile(new URL(import.meta.url)));
for(const helper of ['emulator_performance_summary.mjs','public_qemu_performance.mjs','public_qemu_worker_targets.mjs']){
  await writeFile(resolve(out,helper),await readFile(new URL('./'+helper,import.meta.url)));
}
const sampleMs=Number(process.env.M5_BENCH_SAMPLE_MS||20000),runs=Number(process.env.M5_BENCH_RUNS||1);
const timeoutMs=Number(process.env.M5_BENCH_TIMEOUT_MS||120000);
const profileMs=Number(process.env.M5_BENCH_PROFILE_MS||0);
assert.ok(Number.isSafeInteger(profileMs)&&profileMs>=0&&profileMs<=120000,'Profile duration must be 0..120000 ms');
const stopDiagnostic=process.env.M5_BENCH_STOP_ON_DIAGNOSTIC??null;
assert.ok(stopDiagnostic===null||engine==='qemu'&&/^[A-Z0-9_]{1,128}$/.test(stopDiagnostic),'Diagnostic stop requires an explicit QEMU observer prefix');
const warmPositionMinimum=process.env.M5_BENCH_WARM_POSITION_MINIMUM===undefined?null:Number(process.env.M5_BENCH_WARM_POSITION_MINIMUM);
assert.ok(warmPositionMinimum===null||Number.isInteger(warmPositionMinimum)&&warmPositionMinimum>=0,'Warm sampling minimum must be a nonnegative integer');
const knownInput=process.env.M5_BENCH_INPUT==='known-device-controls';
const requireRenderedMotion=process.env.M5_BENCH_REQUIRE_RENDERED_MOTION==='1';
assert.ok(!requireRenderedMotion||engine==='qemu'&&device==='stackchan','Rendered-motion validation requires the actual QEMU StackChan model');
const candidateClock=process.env.M5_BENCH_CANDIDATE_CLOCK===undefined?null:Number(process.env.M5_BENCH_CANDIDATE_CLOCK);
assert.ok(candidateClock===null||engine==='qemu'&&[1,8].includes(candidateClock),'Explicit QEMU candidate clock must be 1 or 8');
assert.ok(process.env.M5_BENCH_CPU_EXECUTION===undefined&&process.env.M5_BENCH_CANDIDATE_ACCELERATOR===undefined,
  'Use the archived diagnostic harness for withdrawn CPU/scheduling experiments');
assert.ok(Number.isSafeInteger(sampleMs)&&sampleMs>=1000&&sampleMs<=120000);
assert.ok(Number.isSafeInteger(runs)&&runs>=1&&runs<=5);
const readyMarker=process.env.M5_BENCH_READY_MARKER??(firmwareSource==='default-compose'?'"kind": "ready"':firmwareSHA==='c854d3ac6b958439ad30c5277266575d8765f228febf75de243da5d011904542'?'StackChan auto-dance started':'');
const report={schema_version:1,kind:'same-firmware-browser-performance',validation:'virtual-device validation',hardware_validation:'NOT RUN',
  run_id:randomUUID(),engine,device,started_at:new Date().toISOString(),firmware:{source:firmwareSource,sha256:firmwareSHA,bytes:imageBytes?.length??DEMO_FIRMWARE.flashSize},
  host:{platform:os.platform(),release:os.release(),arch:os.arch(),cpu_model:os.cpus()[0]?.model,logical_cpus:os.cpus().length},
  configuration:{sample_ms:sampleMs,runs,warm_position_minimum:warmPositionMinimum,require_rendered_motion:requireRenderedMotion,ready_marker:readyMarker,gpu_mode:'verified-hardware',known_device_input:knownInput,profile_ms:profileMs,stop_on_diagnostic:stopDiagnostic,profiled_runs_are_not_uninstrumented_performance_samples:profileMs>0,
    candidate_clock:candidateClock,
    publication_eligible:candidateClock===null},harness_sha256:sha(await readFile(new URL(import.meta.url))),runs:[],errors:[],requests:[],blocked:[]};
report.summary_algorithm_sha256=sha(await readFile(new URL('./emulator_performance_summary.mjs',import.meta.url)));
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.wasm':'application/wasm','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.woff2':'font/woff2'};
let server,browser,context,page,targets,expectedQemuWorkers=0;

function guestFailureObservations(serialEvents,machineEvents){
  const streams=new Map();for(const event of serialEvents){if(event.source==='uart1'||event.source==='emulator')continue;
    streams.set(event.source,(streams.get(event.source)||'')+event.data);}
  return {panic_or_watchdog_markers:[...streams].flatMap(([source,text])=>[...text.matchAll(/Guru Meditation Error|Interrupt wdt timeout|Task watchdog got triggered|abort\(\) was called|assert failed:|LoadProhibited|StoreProhibited/g)].map(match=>({source,marker:match[0]}))),
    reset_events:machineEvents?.filter(event=>event.event==='RESET')??[],
    rom_boot_markers_per_port:Object.fromEntries([...streams].map(([source,text])=>[source,(text.match(/ESP-ROM:/g)||[]).length]))};
}

async function profileWorkers(milliseconds,signal){
  const cdp=await browser.newBrowserCDPSession(),pending=new Map(),sessions=[],profiles=[];let id=0;
  const receive=({sessionId,message})=>{const value=JSON.parse(message),key=sessionId+':'+value.id,request=pending.get(key);if(!request)return;pending.delete(key);clearTimeout(request.timer);value.error?request.reject(Error(value.error.message)):request.resolve(value.result);};
  cdp.on('Target.receivedMessageFromTarget',receive);
  const command=(sessionId,method,params={})=>new Promise((resolveRequest,reject)=>{
    const serial=++id,key=sessionId+':'+serial,timer=setTimeout(()=>{pending.delete(key);reject(Error(method+' timed out'));},5000);
    pending.set(key,{resolve:resolveRequest,reject,timer});
    cdp.send('Target.sendMessageToTarget',{sessionId,message:JSON.stringify({id:serial,method,params})}).catch(error=>{pending.delete(key);clearTimeout(timer);reject(error);});
  });
  const processSnapshot=async()=>{try{return {wall_ms:performance.now(),...(await cdp.send('SystemInfo.getProcessInfo'))};}
    catch(error){return {wall_ms:performance.now(),error:String(error.message)};}};
  const processesBefore=await processSnapshot();
  const {targetInfos}=await cdp.send('Target.getTargets');
  for(const target of targetInfos.filter(t=>t.type==='worker')){
    if(signal?.aborted)break;
    try{const {sessionId}=await cdp.send('Target.attachToTarget',{targetId:target.targetId,flatten:false});
      await command(sessionId,'Profiler.enable');await command(sessionId,'Profiler.setSamplingInterval',{interval:1000});await command(sessionId,'Profiler.start');sessions.push({sessionId,target,started_at:new Date().toISOString()});
    }catch(error){profiles.push({target,error:String(error.message)});}
  }
  await new Promise(done=>{
    const finish=()=>{clearTimeout(timer);signal?.removeEventListener('abort',finish);done();};
    const timer=setTimeout(finish,milliseconds);
    if(signal?.aborted)finish();else signal?.addEventListener('abort',finish,{once:true});
  });
  for(const {sessionId,target,started_at} of sessions){try{profiles.push({target,started_at,requested_ms:milliseconds,
    stopped_early:signal?.aborted===true,...await command(sessionId,'Profiler.stop'),stopped_at:new Date().toISOString()});
  }catch(error){profiles.push({target,started_at,error:String(error.message)});}finally{await cdp.send('Target.detachFromTarget',{sessionId}).catch(()=>{});}}
  const processesAfter=await processSnapshot(),beforeById=new Map((processesBefore.processInfo??[]).map(process=>[process.id,process]));
  const matched=(processesAfter.processInfo??[]).filter(process=>beforeById.has(process.id));
  const cpuByType={};for(const process of matched){const delta=process.cpuTime-beforeById.get(process.id).cpuTime;
    if(Number.isFinite(delta)&&delta>=0)cpuByType[process.type]=(cpuByType[process.type]??0)+delta;}
  profiles.processCpu={source:'owned-browser-CDP-SystemInfo.getProcessInfo',before:processesBefore,after:processesAfter,
    wall_seconds:(processesAfter.wall_ms-processesBefore.wall_ms)/1000,matched_process_cpu_seconds_by_type:cpuByType,
    matched_processes:matched.length,new_processes:(processesAfter.processInfo??[]).filter(process=>!beforeById.has(process.id)).length,
    vanished_processes:(processesBefore.processInfo??[]).filter(process=>!(processesAfter.processInfo??[]).some(final=>final.id===process.id)).length,
    scope:'Process cpuTime differences for IDs present at both snapshots; excludes unmatched processes and is not per-Worker CPU attribution. Raw IDs remain private.'};
  cdp.off('Target.receivedMessageFromTarget',receive);await cdp.detach();return profiles;
}

function browserProbe({engine,origin,readyMarker,device,candidateClock,firmwareSource}){
  const empty=()=>({start_ms:null,first_serial_ms:null,ready_ms:null,serial:'',serial_events:[],diagnostic_events:[],frames:[],states:[],render_poses:[],asset_loads:[],stats:[],inputs:[],errors:[],statuses:[],phases:[],active:false});
  const p=globalThis.emulatorPerf={engine,run:empty(),runtime:null};
  p.begin=()=>{p.run=empty();p.run.start_ms=performance.now();p.run.resource_start_index=performance.getEntriesByType('resource').length;
    p.run.render_trace_installed=typeof p.stopRenderTrace==='function';p.run.active=true;};
  p.serial=(data,source='uart0')=>{const r=p.run;if(!r.active)return;const at=performance.now();r.serial+=data;
    if(source!=='emulator'&&r.first_serial_ms===null&&data.trim())r.first_serial_ms=at;
    if(r.ready_ms===null&&readyMarker&&r.serial.includes(readyMarker))r.ready_ms=at;
    r.serial_events.push({at_ms:at,source,data});};
  p.guestFailure=()=>{
    // Used only by private diagnostic early-stop polling. Keep ports separate
    // so a marker split across real UART chunks is found without joining ports.
    const streams=new Map();for(const event of p.run.serial_events){
      if(event.source==='uart1'||event.source==='emulator')continue;
      streams.set(event.source,(streams.get(event.source)||'')+event.data);
    }
    for(const [source,text] of streams){
      const marker=text.match(/Guru Meditation Error|Interrupt wdt timeout|Task watchdog got triggered|abort\(\) was called|assert failed:|LoadProhibited|StoreProhibited/);
      if(marker)return {source,marker:marker[0]};
    }
    const reset=p.runtime?.machineEvents?.find(event=>event.event==='RESET');
    return reset?{source:'qemu-machine-event',event:structuredClone(reset)}:null;
  };
  p.frame=f=>{const r=p.run;if(!r.active)return;const before=performance.now(),b=f.pixels;
    let hash=2166136261,nonblack=0;const rgba=b.length===f.width*f.height*4;
    // Hash the real pixels at their native transport depth. Pixel-change rates
    // are compared within each run; cross-engine digests are never equated.
    for(let i=0;i<b.length;i++){hash=Math.imul(hash^b[i],16777619);if((!rgba||i%4!==3)&&b[i])nonblack++;}
    r.frames.push({at_ms:before,sequence:f.sequence??f.frameNumber,width:f.width,height:f.height,
      digest:(hash>>>0).toString(16),nonblack_channels:nonblack,observer_ms:performance.now()-before});};
  p.pose=()=>{
    if(device!=='stackchan'||!p.shell?.model)return null;
    const before=performance.now(),mount=document.querySelector('#deviceMount');
    const result={at_ms:before,yaw:p.shell.model.find('yaw','joint')?.getState(),pitch:p.shell.model.find('pitch','joint')?.getState(),
      dom:{yawTicks:mount?.dataset.servoYawTicks??null,pitchTicks:mount?.dataset.servoPitchTicks??null,
        packets:mount?.dataset.servoPackets??null,known:mount?.dataset.outputKnown??null,source:mount?.dataset.outputSource??null},
      runtime_binding:{session_id:p.runtime?.sessionId??null,firmware_sha256:p.runtime?.receipt?.firmwareSha256??null,
        device_id:p.runtime?.profile?.deviceId??null}};
    return {...result,observer_ms:performance.now()-before};
  };
  p.state=s=>{if(p.run.active)p.run.states.push({at_ms:performance.now(),state:structuredClone(s),presentation:p.pose(),expected_joint_targets:p.expectedJointTargets?.(s)??null});};
  p.snapshot=()=>({...p.run,receipt:p.runtime?.receipt??null,status:p.runtime?.status??null,
    evidence:p.runtime?.evidence?.()??null});
  if(engine==='esp32sim'){
    p.unsubscribe=espTester.subscribe(e=>{
      if(e.type==='frame')p.frame(e);
      else if(e.type==='serial')p.serial(e.data,e.source);
      else if(e.type==='servos')p.state({servos:e.servos,supply:e.supply});
      else if(e.type==='stats'&&p.run.active)p.run.stats.push({at_ms:performance.now(),...e.stats});
      else if(e.type==='input'&&p.run.active)p.run.inputs.push({at_ms:performance.now(),...e});
      else if(e.type==='state'&&p.run.active)p.run.statuses.push({at_ms:performance.now(),status:e.state.status});
      else if(e.type==='load-progress'&&p.run.active)p.run.phases.push({at_ms:performance.now(),...e});
      else if(e.type==='error')p.run.errors.push(e.error);
    });return;
  }
  return Promise.all([import(new URL('platform/web/public-qemu-runtime.js',origin)),import(new URL('platform/web/model-shell.js?v=20261026h',origin)),import(new URL('platform/web/public-qemu-servo.js',origin))]).then(([{PublicQemuRuntime},{ModelDeviceShell},{qemuServoVisualCommands}])=>{
    const receive=PublicQemuRuntime.prototype.receive;
    PublicQemuRuntime.prototype.receive=function(data,generation){
      if(this===p.runtime&&p.run.active&&generation===this.generation&&data?.type==='diagnostic')
        p.run.diagnostic_events.push({at_ms:performance.now(),data:String(data.value)});
      return receive.call(this,data,generation);
    };
    p.expectedJointTargets=state=>p.runtime?.profile?.outputs?.kind==='stackchan-scs-qom-v1'
      ? qemuServoVisualCommands(p.runtime.profile,state).map(({target,angleDeg})=>({target,angleDeg})):null;
    const createShell=ModelDeviceShell.create;
    ModelDeviceShell.create=async function(...args){
      const shell=await createShell.apply(this,args);
      if(args[1].id===device){
        p.stopRenderTrace?.();p.shell=shell;
        p.stopRenderTrace=device==='stackchan'?shell.viewer.on('render',()=>{
          if(p.run.active&&p.runtime?.status==='running')p.run.render_poses.push(p.pose());
        }):null;
      }
      return shell;
    };
    const start=PublicQemuRuntime.prototype.start;
    PublicQemuRuntime.prototype.start=function(...args){
      if(args[0].device===device){
        // This explicit test-only candidate changes execution configuration,
        // never firmware bytes or controller state. It cannot grant publication
        // eligibility to the production profile.
        if(candidateClock!==null){this.allowCandidateProfiles=true;args[0]={...args[0],clockDivisor:candidateClock};}
        p.runtime=this;const previous={onSerial:this.onSerial,onFrame:this.onFrame,onDeviceState:this.onDeviceState,onError:this.onError,onState:this.onState};
        if(!this.__perfObserved){this.__perfObserved=true;
          const loadAsset=this.loadAsset;
          if(typeof loadAsset==='function')this.loadAsset=async(...assetArgs)=>{
            const owner=p.run,result=await loadAsset.apply(this,assetArgs);
            if(owner.active&&owner===p.run)owner.asset_loads.push({at_ms:performance.now(),url:assetArgs[0],cache:result.cache,
              sha256:result.sha256,bytes:result.size});
            return result;
          };
          this.onSerial=data=>{previous.onSerial(data);p.serial(data);};
          this.onFrame=frame=>{previous.onFrame(frame);p.frame(frame);};
          this.onDeviceState=state=>{previous.onDeviceState(state);p.state(state);};
          this.onError=e=>{p.run.errors.push(e.message);previous.onError(e);};
          this.onState=s=>{if(p.run.active)p.run.statuses.push({at_ms:performance.now(),status:s.status});previous.onState(s);};
        }
        p.run.runtime_start_ms=performance.now();
        const input=args[0].firmware,owner=input instanceof ArrayBuffer?input:input.buffer;
        p.seenFirmwareInputs ||= new WeakSet();
        p.run.input_firmware_buffer_seen_before=p.seenFirmwareInputs.has(owner);p.seenFirmwareInputs.add(owner);
        p.run.input_firmware_bytes=input.byteLength;
        p.run.firmware_source_selection={source:document.querySelector('input[name="firmwareSource"]:checked')?.value,
          example:document.querySelector('#referenceExample')?.value,expected_path:firmwareSource};
      }
      return start.apply(this,args);
    };
  });
}

try{
  let url;
  if(engine==='qemu'){
    assert.ok(process.env.M5_BENCH_SITE,'QEMU needs an explicit exported static site');
    const site=resolve(process.env.M5_BENCH_SITE),manifestBytes=await readFile(resolve(site,'public-site-manifest.json')),manifest=JSON.parse(manifestBytes);
    report.provenance={site_manifest_sha256:sha(manifestBytes),base_path:manifest.base_path,assets:{}};
    report.configuration.site_publication_eligible=manifest.publication_eligible===true;
    report.configuration.publication_eligible&&=manifest.publication_eligible===true;
    if(manifest.diagnostic_overlay)report.provenance.diagnostic_overlay=manifest.diagnostic_overlay;
    if(stopDiagnostic){
      assert.equal(manifest.publication_eligible,false,'Early observer stop is restricted to a private diagnostic export');
      report.kind='same-firmware-instrumented-browser-diagnostic';report.configuration.nonperformance_diagnostic=true;
    }
    for(const asset of manifest.assets.filter(a=>/^platform\/web\/(public.*\.(?:js|json)|sha256.js|qemu-browser-profiles.json|model-shell.js)$/.test(a.path)||/^platform\/runtime\/qemu\/.*(?:wasm|js|json)$/.test(a.path))){
      const bytes=await readFile(resolve(site,asset.path));assert.equal(bytes.length,asset.bytes);assert.equal(sha(bytes),asset.sha256);
      report.provenance.assets[asset.path]={sha256:asset.sha256,bytes:asset.bytes};
      if(asset.path==='platform/runtime/qemu/runtime.json')report.runtime_manifest=JSON.parse(bytes);
    }
    if(firmwareSource==='default-compose'){
      for(const asset of manifest.assets.filter(a=>a.path.startsWith('platform/runtime/littlefs/'))){
        const bytes=await readFile(resolve(site,asset.path));assert.equal(bytes.length,asset.bytes);assert.equal(sha(bytes),asset.sha256);
        report.provenance.assets[asset.path]={sha256:asset.sha256,bytes:asset.bytes};
      }
      const composer=JSON.parse(await readFile(resolve(site,'platform/runtime/littlefs/manifest.json')));
      report.composition_identity={path:'normal-product-reference-composer',fixture:composer.fixture,
        composer_source:composer.source,composer_build:composer.build,composer_assets:composer.assets,
        actual_result_verified_by:'runtime firmware SHA and normal composer result validation; product provenance object is not separately exposed'};
    }
    server=createServer(async(req,res)=>{try{
      const pathname=new URL(req.url,'http://localhost').pathname;if(!pathname.startsWith(manifest.base_path)){res.writeHead(404).end();return;}
      const file=resolve(site,decodeURIComponent(pathname.slice(manifest.base_path.length))||'index.html');if(!file.startsWith(site+sep)){res.writeHead(403).end();return;}
      res.writeHead(200,{'content-type':mime[extname(file)]||'application/octet-stream','cache-control':'no-cache'});res.end(await readFile(file));
    }catch{res.writeHead(404).end();}});
    await new Promise(done=>server.listen(0,'127.0.0.1',done));assert.ok(![8787,8830].includes(server.address().port));
    url=`http://127.0.0.1:${server.address().port}${manifest.base_path}`;
  }else{
    url=process.env.M5_BENCH_URL||'https://zhuzhe1983.github.io/esp-online-tester/platform/';
    const assetRoot=new URL('../',url);report.provenance={url,assets:{}};
    for(const path of ['wasm/esp32sim.wasm','wasm/worker.js','wasm/jit.mjs','wasm/pacing.mjs','platform/runtime.js']){
      const response=await fetch(new URL(path,assetRoot));assert.ok(response.ok);const bytes=Buffer.from(await response.arrayBuffer());report.provenance.assets[path]={sha256:sha(bytes),bytes:bytes.length};
    }
    if(process.env.M5_BENCH_WASM_SHA256)assert.equal(report.provenance.assets['wasm/esp32sim.wasm'].sha256,process.env.M5_BENCH_WASM_SHA256);
  }
  report.url=url;
  const modules=process.env.M5_WASM_NODE_MODULES||resolve(repo,'platform/tests/node_modules');
  const {chromium}=await import(pathToFileURL(resolve(modules,'playwright/index.mjs')));
  const args=['--enable-gpu','--enable-webgl','--use-gl=angle',...(os.platform()==='darwin'?['--use-angle=metal']:[])];
  browser=await chromium.launch({headless:true,executablePath:process.env.M5_WASM_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args});
  report.browser=browser.version();targets=await observeWorkerTargets(browser);
  context=await browser.newContext({viewport:{width:1400,height:1100}});page=await context.newPage();
  page.on('pageerror',e=>report.errors.push(e.message));
  page.on('request',req=>report.requests.push({url:req.url(),method:req.method(),at:new Date().toISOString()}));
  await context.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>{report.blocked.push(route.request().url());return route.abort('blockedbyclient');});
  await page.goto(url,{waitUntil:'domcontentloaded'});
  if(engine==='qemu'){
    await page.waitForFunction(()=>crossOriginIsolated&&document.querySelector('#deviceMount')?.dataset.deviceId==='cores3',{}, {timeout:45000});
    await page.evaluate(browserProbe,{engine,origin:url,readyMarker,device,candidateClock,firmwareSource});
    await page.locator(`button[data-device-id="${device}"]`).click();
    await page.waitForFunction(id=>document.querySelector('#deviceMount')?.dataset.deviceId===id,device);
    await page.locator('.advanced-options > summary').click();await page.locator('#runtimeMode').selectOption('browser');
    if(firmwareSource==='default-compose'){
      await page.locator('input[name="firmwareSource"][value="reference"]').check();
      await page.locator('#referenceExample').selectOption('stock-div8');
      assert.equal(await page.locator('#firmwareSha').inputValue(),'','Use the normal reference SHA without a custom form override');
    }else{
      await page.locator('input[name="firmwareSource"][value="local"]').check();await page.locator('#firmwareFile').setInputFiles(image);await page.locator('#firmwareSha').fill(firmwareSHA);
    }
  }else{
    await page.waitForFunction(()=>globalThis.espTester,{}, {timeout:45000});
    await page.locator('#product-select').selectOption(opponentProducts[device]);
    await page.locator('[data-firmware-tab="local"]').click();await page.locator('#firmware-file').setInputFiles(image);
    await page.waitForFunction(()=>document.querySelector('#local-build-status')?.textContent.includes('完整合并镜像'),{}, {timeout:30000});
    await page.evaluate(browserProbe,{engine,origin:url,readyMarker,device,candidateClock,firmwareSource});
  }
  // Requested launch flags are not renderer evidence. Read the actual visible
  // model context and refuse a silent software fallback before timing a guest.
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('canvas[data-engine^="three.js"]')).some(canvas=>{
    const gl=canvas.getContext('webgl2')||canvas.getContext('webgl');return !!gl;
  }),{}, {timeout:30000});
  report.webgl=await page.evaluate(()=>Array.from(document.querySelectorAll('canvas[data-engine^="three.js"]')).flatMap(canvas=>{
    const gl=canvas.getContext('webgl2')||canvas.getContext('webgl');if(!gl)return [];
    const extension=gl.getExtension('WEBGL_debug_renderer_info');return [{scope:'actual-workbench-model-canvas',canvas_id:canvas.id,
      version:gl.getParameter(gl.VERSION),vendor:gl.getParameter(gl.VENDOR),renderer:gl.getParameter(gl.RENDERER),
      unmasked_vendor:extension?gl.getParameter(extension.UNMASKED_VENDOR_WEBGL):null,
      unmasked_renderer:extension?gl.getParameter(extension.UNMASKED_RENDERER_WEBGL):null}];
  }));
  const gpuCDP=await browser.newBrowserCDPSession(),gpuInfo=await gpuCDP.send('SystemInfo.getInfo');await gpuCDP.detach();
  report.gpu={devices:gpuInfo.gpu.devices,aux_attributes:gpuInfo.gpu.auxAttributes,feature_status:gpuInfo.gpu.featureStatus};
  assert.ok(report.webgl.length>0&&report.webgl.every(row=>row.unmasked_renderer
    &&!/swiftshader|llvmpipe|softpipe|software/i.test(row.unmasked_renderer)
    &&/Apple|AMD|Intel|NVIDIA|Qualcomm|Adreno|Mali|PowerVR/i.test(row.unmasked_renderer+' '+row.unmasked_vendor)),
  'Actual model WebGL renderer must be identified hardware; software fallback is not a performance sample');
  for(let i=0;i<runs;i++){
    await page.evaluate(()=>emulatorPerf.begin());
    await page.locator(engine==='qemu'?'#startBtn':'#load-firmware').click();
    await page.waitForFunction(({marker,diagnostic})=>{
      const r=emulatorPerf.run;return r.errors.length||(diagnostic&&(r.diagnostic_events.some(e=>e.data.includes(diagnostic))||emulatorPerf.guestFailure()))
        ||(r.frames.some(f=>f.nonblack_channels)&&(!marker||r.ready_ms!==null));
    },{marker:readyMarker,diagnostic:stopDiagnostic},{timeout:timeoutMs});
    const early=await page.evaluate(()=>emulatorPerf.run.errors);assert.equal(early.length,0,JSON.stringify(early));
    console.log(JSON.stringify({engine,device,run:i+1,phase:'ready',observation:await page.evaluate(()=>{
      const r=emulatorPerf.run,f=r.frames.find(f=>f.nonblack_channels);return {
        first_serial_ms:r.first_serial_ms-r.start_ms,ready_marker_ms:r.ready_ms===null?null:r.ready_ms-r.start_ms,
        first_nonblack_ms:f?f.at_ms-r.start_ms:null,last_state:r.states.at(-1)?.state??null};
    })}));
    const profileAbort=profileMs>0?new AbortController():null;
    const profiling=profileMs>0?profileWorkers(profileMs,profileAbort.signal):null;
    await page.evaluate(()=>emulatorPerf.run.sample_start_ms=performance.now());
    if(stopDiagnostic){
      await page.waitForFunction(prefix=>emulatorPerf.run.diagnostic_events.some(e=>e.data.includes(prefix))||emulatorPerf.guestFailure(),stopDiagnostic,
        {timeout:sampleMs,polling:50}).catch(error=>{if(error.name!=='TimeoutError')throw error;});
      if(await page.evaluate(prefix=>emulatorPerf.run.diagnostic_events.some(e=>e.data.includes(prefix))||emulatorPerf.guestFailure(),stopDiagnostic))
        await page.waitForTimeout(150); // Drain the paired saved-register diagnostic lines before graceful stop.
    }else await page.waitForTimeout(sampleMs);
    await page.evaluate(()=>emulatorPerf.run.sample_end_ms=performance.now());
    if(profileAbort&&stopDiagnostic&&await page.evaluate(prefix=>emulatorPerf.run.diagnostic_events.some(e=>e.data.includes(prefix))||emulatorPerf.guestFailure(),stopDiagnostic))
      profileAbort.abort();
    const row=await page.evaluate(()=>emulatorPerf.snapshot());row.run=i+1;row.session_id=engine==='qemu'?row.evidence?.session_id:randomUUID();row.session_identity_source=engine==='qemu'?'production adapter receipt':'harness browser-local run id';
    row.resource_timing=await page.evaluate(()=>performance.getEntriesByType('resource').map(r=>({name:r.name,start_ms:r.startTime,duration_ms:r.duration,transfer_bytes:r.transferSize,encoded_bytes:r.encodedBodySize,decoded_bytes:r.decodedBodySize})));
    row.run_resource_timing=row.resource_timing.slice(row.resource_start_index);
    if(profiling){const profiles=await profiling;await writeFile(resolve(out,`run-${i+1}-worker-profiles.json`),JSON.stringify(profiles));
      row.profile_process_cpu=profiles.processCpu;
      await writeFile(resolve(out,`run-${i+1}-process-cpu.json`),JSON.stringify(profiles.processCpu));
      row.worker_profiles=profiles.map(p=>({target:p.target,error:p.error,started_at:p.started_at,stopped_at:p.stopped_at,
        requested_ms:p.requested_ms,stopped_early:p.stopped_early,start_time:p.profile?.startTime,end_time:p.profile?.endTime,
        nodes:p.profile?.nodes?.length,samples:p.profile?.samples?.length}));}
    if(engine==='esp32sim'){
      row.observation=await page.evaluate(()=>espTester.observe());
      assert.equal(row.observation.firmware.artifacts.find(a=>a.kind==='flash')?.sha256,firmwareSHA,'Other engine must load the same complete Flash bytes');
    }
    row.stopped_on_diagnostic=stopDiagnostic?row.diagnostic_events.find(e=>e.data.includes(stopDiagnostic))??null:null;
    row.stopped_on_guest_failure=stopDiagnostic?await page.evaluate(()=>emulatorPerf.guestFailure()):null;
    assert.ok(row.frames.length>0||row.stopped_on_diagnostic||row.stopped_on_guest_failure,'Require real framebuffer observations or an explicitly captured diagnostic/failure stop');if(engine==='qemu'){
      assert.equal(row.receipt.firmwareSha256,firmwareSHA);
      if(firmwareSource==='default-compose'){
        assert.equal(row.receipt.profile,'cores3-wasm-stock-wallclock');assert.equal(row.receipt.clockDivisor,1);
        assert.equal(row.receipt.oneInsnPerTb,true);
        assert.equal(row.receipt.firmwareVariant?.sourceSHA256,'7672397edc3bff5256015c5d857fa3b4c53cba814bac6a982fb7eeb521cef3cb');
        assert.equal(row.input_firmware_bytes,DEMO_FIRMWARE.flashSize);assert.equal(row.input_firmware_buffer_seen_before,false,'Every composition must supply a fresh Flash input buffer');
        assert.equal(row.firmware_source_selection.source,'reference');assert.equal(row.firmware_source_selection.example,'stock-div8');
        assert.equal(row.receipt.persistentFlash,false);
        assert.ok(row.serial.includes('"kind": "ready"')&&!row.serial.includes('"kind": "touch_clicked"'),'Each new guest starts from untouched composed Flash');
        assert.ok(report.runs.every(previous=>previous.session_id!==row.session_id),'Warm module reuse must start a new VM session');
        assert.equal(row.receipt.wasmCompilation,i===0?'compiled':'memory','Warm run must reuse compiled code while creating a fresh guest');
        assert.ok(row.asset_loads.length>=4,'Record actual verified runtime and ROM asset loader results');
        if(i>0)assert.ok(row.asset_loads.every(asset=>asset.cache==='memory'),'Warm immutable runtime/ROM assets must hit the real memory cache');
        row.composition_validation={result:'PASS',firmware_source:'default-compose',fresh_flash_input:true,
          new_session:true,compiled_module_cache:row.receipt.wasmCompilation,normal_ui_reference:true,
          fixture:DEMO_FIRMWARE.fixture,base_sha256:DEMO_FIRMWARE.rawBaseSHA256,firmware_sha256:firmwareSHA};
      }
      if(candidateClock!==null){
        assert.equal(row.receipt.clockDivisor,candidateClock);
        assert.equal(row.receipt.clockOverride?.candidate,true);
        assert.equal(row.receipt.oneInsnPerTb,false,'a clock override clears the admitted variant execution binding');
      }
      if(row.receipt.oneInsnPerTb){
        const args=row.receipt.actualArguments,required=row.receipt.requiredRuntimePatch;
        assert.equal(row.receipt.clockDivisor,1);assert.equal(row.receipt.accelerator,null);
        assert.equal(row.receipt.firmwareVariant?.firmwareSHA256,firmwareSHA);
        assert.equal(row.receipt.firmwareVariant.oneInsnPerTb,true);
        assert.deepEqual(row.receipt.firmwareVariant.requiredRuntimePatch,required);
        assert.equal(row.receipt.clockOverride,null);
        assert.ok(Array.isArray(args));assert.equal(args.filter(value=>value==='-accel').length,1);
        assert.equal(args[args.indexOf('-accel')+1],'tcg,thread=multi,one-insn-per-tb=on');
        assert.ok(!args.includes('-icount')&&!args.includes('-smp'));
        assert.deepEqual(report.runtime_manifest.source.patches.filter(row=>row.path===required.path),[required]);
      }
    }
    row.summary=summary(row);report.runs.push(row);
    if(requireRenderedMotion){
      const trace=row.summary.steady.rendered_joint_trace;
      const poses=row.render_poses.filter(p=>p&&p.at_ms>=row.sample_start_ms&&p.at_ms<=row.sample_end_ms&&p.dom?.known==='true');
      const states=row.states.filter(s=>s.at_ms>=row.sample_start_ms&&s.at_ms<=row.sample_end_ms);
      assert.ok(trace?.actual_angle_changes>0&&trace.intermediate_observations>0,'Real viewer-render poses must move through intermediate angles');
      assert.ok(states.length>1&&poses.length>1,'Real controller and renderer traces are both required');
      for(const pose of [...poses,...states.map(s=>s.presentation)]){
        assert.equal(pose?.runtime_binding.session_id,row.session_id,'Rendered poses must bind to this browser session');
        assert.equal(pose.runtime_binding.firmware_sha256,firmwareSHA);
        assert.equal(pose.runtime_binding.device_id,device);
        assert.equal(pose.dom.known,'true');assert.equal(pose.dom.source,'browser-qemu-qom');
      }
      for(const state of states){
        assert.equal(state.presentation.dom.yawTicks,String(state.state.servos[0].present_position));
        assert.equal(state.presentation.dom.pitchTicks,String(state.state.servos[1].present_position));
        assert.equal(state.presentation.dom.packets,String(state.state.packets));
        for(const {target,angleDeg} of state.expected_joint_targets||[])
          assert.ok(Math.abs(state.presentation[target].targetAngleDeg-angleDeg)<1e-6,'Actual joint targets must follow this QOM observation and profile calibration');
        assert.equal(state.expected_joint_targets?.length,2);
      }
      row.rendered_motion_validation={result:'PASS',source:'actual-workbench-viewer-render',observations:poses.length,
        actual_angle_changes:trace.actual_angle_changes,intermediate_observations:trace.intermediate_observations,
        controller_bindings_checked:states.length,session_and_firmware_bound:true,
        meaning:'Observed 3D presentation follows real QOM positions. This is virtual-device visual evidence, not physical servo behavior.'};
    }
    if(knownInput){
      const before=await page.evaluate(()=>{
        emulatorPerf.stopInputTrace?.();emulatorPerf.run.input_dom_events=[];
        const record=event=>{if(event.isTrusted)emulatorPerf.run.input_dom_events.push({type:event.type,at_ms:performance.now(),
          event_ms:event.timeStamp,isTrusted:event.isTrusted,key:event.key??null,clientX:event.clientX??null,
          clientY:event.clientY??null,buttons:event.buttons??null,pointerType:event.pointerType??null,
          target: event.target?.tagName??null});};
        const types=['pointerdown','pointerup','keydown','keyup'];for(const type of types)window.addEventListener(type,record,true);
        emulatorPerf.stopInputTrace=()=>{for(const type of types)window.removeEventListener(type,record,true);};
        return {at_ms:performance.now(),time_origin_ms:performance.timeOrigin,serial_length:emulatorPerf.run.serial.length,
          digest:emulatorPerf.run.frames.at(-1)?.digest,input_count:emulatorPerf.runtime?.inputs.length??emulatorPerf.run.inputs.length};
      });
      const captured=async()=>page.evaluate(async engine=>engine==='qemu'?document.querySelector('#rawFrameCanvas').toDataURL('image/png'):(await espTester.capture({format:'png'})).dataUrl,engine);
      await writeFile(resolve(out,`run-${i+1}-before-input-frame.png`),Buffer.from((await captured()).split(',')[1],'base64'));
      const keys=device==='stopwatch'?['a','b']:['1'],holdMs=device==='stopwatch'?1000:500;
      let pointer=null;
      if(engine==='qemu'&&device==='stackchan'){
        pointer=await page.evaluate(async origin=>{
          const shell=emulatorPerf.shell,c=shell.model.find('touch-1','button'),THREE=await import(new URL('platform/web/vendor/three/three.module.js',origin));
          shell.viewer.setView('top',{duration:0});shell.viewer.fit({duration:0});
          await new Promise(done=>{const off=shell.viewer.on('render',()=>{off();done();});shell.viewer.requestRender();});
          const box=shell.viewer.renderer.domElement.getBoundingClientRect();
          const point=c.meta.surfaceCenter?shell.model.root.localToWorld(new THREE.Vector3(...c.meta.surfaceCenter)):c.object3d.getWorldPosition(new THREE.Vector3());point.project(shell.viewer.camera);
          const x=box.left+(point.x+1)*box.width/2,y=box.top+(1-point.y)*box.height/2;
          for(const dy of [0,-2,2,-4,4,-8,8])for(const dx of [0,-2,2,-4,4,-8,8]){
            if(shell.viewer.pick({clientX:x+dx,clientY:y+dy})?.component===c)return {x:x+dx,y:y+dy,component:c.id};
          }
          throw Error('Front capacitive surface is not pickable');
        },url);
        await page.mouse.move(pointer.x,pointer.y);await page.mouse.down();
        try{await page.waitForTimeout(holdMs);}finally{await page.mouse.up();}
      }else{
        await page.locator('canvas[data-engine^="three.js"]').focus();
        for(const key of keys)await page.keyboard.down(key);
        try{await page.waitForTimeout(holdMs);}finally{for(const key of [...keys].reverse())await page.keyboard.up(key);}
      }
      await page.waitForTimeout(2000);
      const after=await page.evaluate(before=>({at_ms:performance.now(),serial_new:emulatorPerf.run.serial.slice(before.serial_length),
        digest:emulatorPerf.run.frames.at(-1)?.digest,inputs:(emulatorPerf.runtime?.inputs??emulatorPerf.run.inputs).slice(before.input_count),
        dom_events:structuredClone(emulatorPerf.run.input_dom_events),last_state:emulatorPerf.run.states.at(-1)?.state??null}),before);
      await page.evaluate(()=>emulatorPerf.stopInputTrace?.());
      row.input_observation={scope:device==='stopwatch'?'Official A+B hold for menu; inspect same-guest framebuffer outcome':'Front body capacitive pad through actual keyboard/model/controller; application response is not asserted',
        keys:pointer?null:keys,pointer,requested_hold_ms:holdMs,before,after,actual_controller_receipts:after.inputs.length,frame_digest_changed:before.digest!==after.digest};
      assert.ok(after.inputs.length>=keys.length*2,'Every actual DOM key down/up must reach the production controller input path');
      await writeFile(resolve(out,`run-${i+1}-after-input-frame.png`),Buffer.from((await captured()).split(',')[1],'base64'));
      await writeFile(resolve(out,`run-${i+1}-input-serial.txt`),after.serial_new);
    }
    const finalSerialEvents=knownInput?await page.evaluate(()=>emulatorPerf.run.serial_events):row.serial_events;
    if(knownInput)row.input_serial_events=finalSerialEvents;
    const finalMachineEvents=knownInput&&engine==='qemu'?await page.evaluate(()=>emulatorPerf.runtime.machineEvents):row.evidence?.machine_events;
    row.guest_failure_observations=guestFailureObservations(finalSerialEvents,finalMachineEvents);
    await page.screenshot({path:resolve(out,`run-${i+1}.png`),fullPage:true});
    await writeFile(resolve(out,`run-${i+1}-serial.txt`),row.serial);
    if(engine==='qemu'){
      await page.locator('#stopBtn').click();await page.waitForFunction(()=>emulatorPerf.runtime.status==='stopped'&&!emulatorPerf.runtime.iframe,{}, {timeout:45000});
      row.cleanup=await page.evaluate(()=>emulatorPerf.runtime.evidence().cleanup);
      const pthreadWorkers=row.cleanup?.workersCreated,engineWorkers=row.cleanup?.engineOwnership?.engineWorkersCreated;
      assert.ok(Number.isInteger(pthreadWorkers)&&pthreadWorkers>=1&&Number.isInteger(engineWorkers)&&engineWorkers>=1,
        'Successful exit must receipt actual created pthread and engine Worker counts');
      expectedQemuWorkers+=pthreadWorkers+engineWorkers;
      row.worker_targets=await targets.waitUntilClosed({minimumObserved:expectedQemuWorkers,timeoutMs:30000});
      if(profiling){
        const previousTargets=new Set(report.runs.slice(0,-1).flatMap(previous=>previous.worker_targets?.observed??[]).map(target=>target.targetId));
        const observed=row.worker_targets.observed.filter(target=>!previousTargets.has(target.targetId));
        const profiled=new Set(row.worker_profiles.filter(profile=>!profile.error&&profile.samples>0).map(profile=>profile.target.targetId));
        const missing=observed.filter(target=>!profiled.has(target.targetId));
        row.worker_profile_validation={result:missing.length===0&&observed.length===pthreadWorkers+engineWorkers?'PASS':'PARTIAL',
          expected_receipted_workers:pthreadWorkers+engineWorkers,observed_workers:observed.length,
          sampled_workers:observed.filter(target=>profiled.has(target.targetId)).length,missing_targets:missing,
          scope:'Every actually observed run-owned Worker must have a nonempty raw profile; aborted fault captures retain their actual shorter duration.'};
        if(row.worker_profile_validation.result!=='PASS')row.errors.push('Actual Worker CPU profile coverage incomplete; inspect raw profile validation');
      }
      row.diagnostic_events=await page.evaluate(()=>emulatorPerf.run.diagnostic_events);
      row.diagnostics_full=row.diagnostic_events.map(e=>e.data+'\n').join('');
      await writeFile(resolve(out,`run-${i+1}-diagnostics.txt`),row.diagnostics_full);
      // A panic line can arrive after the sampled snapshot but before stop.
      // Preserve its actual exit-time source events without extending metrics.
      const exit=await page.evaluate(()=>({serial:emulatorPerf.run.serial,serial_events:emulatorPerf.run.serial_events,
        machine_events:emulatorPerf.runtime.machineEvents}));
      row.exit_serial=exit.serial;row.exit_serial_events=exit.serial_events;
      row.guest_failure_observations=guestFailureObservations(exit.serial_events,exit.machine_events);
      await writeFile(resolve(out,`run-${i+1}-exit-serial.txt`),exit.serial);
    }else{
      await page.evaluate(()=>espTester.pause());
      if(i<runs-1)await page.evaluate(()=>espTester.clearDeviceStorage());
      else{await page.evaluate(()=>espTester.dispose());row.worker_targets=await targets.waitUntilClosed({minimumObserved:i+1,timeoutMs:30000});}
    }
    console.log(JSON.stringify({engine,run:i+1,startup_ms:row.summary.startup_ms,steady:row.summary.steady,
      last_packets:row.summary.servo_last_state?.packets,guest_speed:row.summary.guest_speed,
      cue_count:row.summary.serial_cues.filter(c=>c.line.startsWith('DANCE cue=')).length,cleanup:row.worker_targets?.ok}));
    if(row.stopped_on_diagnostic){
      report.remaining_runs_skipped={reason:'Requested real diagnostic captured; all remaining instrumented reproduction samples are skipped.',planned:runs,completed:i+1};
      break;
    }
    if(row.guest_failure_observations.panic_or_watchdog_markers.length||row.guest_failure_observations.reset_events.length){
      report.remaining_runs_skipped={reason:'Guest panic/watchdog/reset retained; do not replace this failure with an ordinary warm retry.',
        planned:runs,completed:i+1};
      break;
    }
    if(i===0&&runs>1&&warmPositionMinimum!==null){
      const observed=row.summary.steady.position_change_observations;
      report.warm_sampling_selection={minimum: warmPositionMinimum,observed,continue:observed>=warmPositionMinimum,
        meaning:'Controls optional warm sampling only; it is not a firmware acceptance criterion.'};
      if(!report.warm_sampling_selection.continue)break;
    }
  }
  if(stopDiagnostic)report.diagnostic_outcome={target_captured:report.runs.some(r=>r.stopped_on_diagnostic),
    result_scope:'Instrumented acquisition and cleanup only; no firmware stability or performance acceptance is granted.'};
  report.result=report.errors.length||report.blocked.length||report.runs.some(r=>r.errors.length||r.worker_targets?.ok===false||r.guest_failure_observations?.panic_or_watchdog_markers.length||r.guest_failure_observations?.reset_events.length)?'PARTIAL':'PASS';
}catch(error){report.result='FAIL';report.failure=String(error.stack||error);console.error(error);
  if(page){report.failure_state=await page.evaluate(()=>globalThis.emulatorPerf?.snapshot()).catch(()=>null);await page.screenshot({path:resolve(out,'failure.png'),fullPage:true}).catch(()=>{});}process.exitCode=1;
}finally{
  if(page){if(engine==='qemu')await page.locator('#stopBtn').click({timeout:2000}).catch(()=>{});else await page.evaluate(()=>globalThis.espTester?.dispose()).catch(()=>{});}
  if(page&&engine==='qemu'&&report.result==='FAIL'){
    report.failure_cleanup={scope:'Actual state before browser/context teardown; no successful guest run is inferred.'};
    try{
      await page.waitForFunction(()=>!globalThis.emulatorPerf?.runtime?.iframe,{}, {timeout:45000});
      report.failure_cleanup.runtime=await page.evaluate(()=>({iframe_removed:!globalThis.emulatorPerf?.runtime?.iframe,
        cleanup:globalThis.emulatorPerf?.runtime?.evidence?.().cleanup??null}));
      report.failure_cleanup.worker_targets=await targets.waitUntilClosed({minimumObserved:expectedQemuWorkers,timeoutMs:30000});
    }catch(error){report.failure_cleanup.error=String(error.message);}
  }
  report.finished_at=new Date().toISOString();await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');
  await targets?.detach();await context?.close();await browser?.close();if(server)await new Promise(done=>server.close(done));
  console.log('BROWSER_WINDOW_RELEASED',report.result);
}
