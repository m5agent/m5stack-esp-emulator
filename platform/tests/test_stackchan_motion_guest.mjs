// Opt-in StackChan official SDK guests. Static files only; no native service or hardware.
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
assert.ok(process.env.M5_STACKCHAN_WASM_SHA256&&process.env.M5_STACKCHAN_IMAGES_JSON,'Explicit WASM SHA and fixture image manifest required');
const site=resolve(process.env.M5_PUBLIC_SITE),expectedWasm=process.env.M5_STACKCHAN_WASM_SHA256;
assert.match(expectedWasm,/^[a-f0-9]{64}$/);
const out=resolve(process.env.M5_STACKCHAN_OUT||resolve(repo,'.work/stackchan-motion-guest'));
assert.ok(out.startsWith(resolve(repo,'.work')+'/'),'Raw guest evidence belongs in ignored .work');
const allowed=['scs_command_edges','motion_calibration','motion_lifecycle','dance','original'];
const wanted=(process.env.M5_STACKCHAN_CASES||allowed.join(',')).split(',');
assert.ok(wanted.length&&new Set(wanted).size===wanted.length&&wanted.every(v=>allowed.includes(v)),'Invalid or duplicate StackChan case');
const imageManifest=resolve(process.env.M5_STACKCHAN_IMAGES_JSON),rawImages=JSON.parse(await readFile(imageManifest,'utf8')),images=new Map();
for(const name of wanted){const raw=rawImages[name];assert.ok(raw&&typeof raw.path==='string'&&/^[a-f0-9]{64}$/.test(raw.sha256),'Each selected image needs explicit path and SHA256: '+name);images.set(name,{path:resolve(dirname(imageManifest),raw.path),sha256:raw.sha256});}
await mkdir(out,{recursive:false});await writeFile(resolve(out,'harness.mjs'),await readFile(new URL(import.meta.url)));
const modules=process.env.M5_WASM_NODE_MODULES||resolve(repo,'platform/tests/node_modules');
const {chromium}=await import(pathToFileURL(resolve(modules,'playwright/index.mjs')));
const hardwareGPU=process.env.M5_WASM_GPU==='hardware';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const manifestBytes=await readFile(resolve(site,'public-site-manifest.json')),manifest=JSON.parse(manifestBytes),base=manifest.base_path,assetHashes=new Map(manifest.assets.map(v=>[v.path,v.sha256]));
if(process.env.M5_STACKCHAN_MANIFEST_SHA256)assert.equal(sha(manifestBytes),process.env.M5_STACKCHAN_MANIFEST_SHA256,'Unexpected export manifest');
assert.equal(assetHashes.get('platform/runtime/qemu/qemu-system-xtensa.wasm'),expectedWasm,'Export declares a different WASM');
const report={kind:'stackchan-deep-official-sdk-browser',started_at:new Date().toISOString(),expected_wasm:expectedWasm,export_manifest_sha256:sha(manifestBytes),checks:[],cases:[],errors:[],blocked:[],hardware_validation:'NOT RUN',harness_sha256:sha(await readFile(new URL(import.meta.url))),instrumentation:'Files are served unchanged. Test page.evaluate wraps ModelDeviceShell.create using the production module query and PublicQemuRuntime callbacks to observe the same instance; independent matrix/pixel checks run after original callbacks.',served_observation_files:{}};
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.wasm':'application/wasm','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2'};
let browser,page,targets,server,observedRuns=0;const requests=[];
function check(name,ok,detail){report.checks.push({name,ok,detail});console.log(name,ok?'PASS':'FAIL');assert.ok(ok,name);}
async function pointerTarget(id,kind,view='top'){
 return page.evaluate(async({id,kind,view})=>{
  const shell=smokeShell,c=shell.model.find(id,kind),THREE=await import(new URL('platform/web/vendor/three/three.module.js',document.baseURI));
  shell.viewer.setView(view,{duration:0});shell.viewer.fit({duration:0});
  await new Promise(yes=>{const off=shell.viewer.on('render',()=>{off();yes();});shell.viewer.requestRender();});
  const box=shell.viewer.renderer.domElement.getBoundingClientRect();
  const v=c.meta.surfaceCenter?shell.model.root.localToWorld(new THREE.Vector3(...c.meta.surfaceCenter)):c.object3d.getWorldPosition(new THREE.Vector3());v.project(shell.viewer.camera);
  const x=box.left+(v.x+1)*box.width/2,y=box.top+(1-v.y)*box.height/2;
  for(const dy of [0,-2,2,-4,4,-8,8])for(const dx of [0,-2,2,-4,4,-8,8])if(shell.viewer.pick({clientX:x+dx,clientY:y+dy})?.component===c)return {id,kind,x:x+dx,y:y+dy};
  throw Error('Actual model surface not pickable '+id);
 },{id,kind,view});
}
async function topClick(){
 const p=await pointerTarget('touch-1','button');
 const before=await page.evaluate(p=>{const canvas=smokeShell.viewer.renderer.domElement,el=document.elementFromPoint(p.x,p.y),hit=smokeShell.viewer.pick({clientX:p.x,clientY:p.y});return {p,wall_ms:performance.now(),input_count:smokeRun.runtime.inputs.length,is_canvas:el===canvas,dom:{tag:el?.tagName,id:el?.id,classes:el?.className},model_hit:hit?.component?.id,button:smokeShell.model.button('touch-1').getState(),raw_state:smokeRun.runtime.lastDeviceState};},p);
 await page.evaluate(v=>smokeRun.input_traces.push({before:v}),before);console.log('TOP_TARGET',JSON.stringify({is_canvas:before.is_canvas,dom:before.dom,hit:before.model_hit}));
 assert.ok(before.is_canvas&&before.model_hit==='touch-1','Actual DOM pointer target must be the picked canvas');
 await page.mouse.move(p.x,p.y);await page.mouse.down();
 try{await page.waitForFunction(n=>smokeRun.runtime.inputs.slice(n).some(i=>i.type==='capacitive-touch'&&i.down===true&&i.result?.touch_bits>0),before.input_count,{timeout:5000});await page.waitForTimeout(1000);}
 finally{await page.mouse.up();}
 await page.waitForFunction(n=>smokeRun.runtime.inputs.slice(n).some(i=>i.type==='capacitive-touch'&&i.down===false&&i.result?.touch_bits===0),before.input_count,{timeout:5000});
 return page.evaluate(({p,before})=>{const trace={p,before,after:{wall_ms:performance.now(),inputs:smokeRun.runtime.inputs.slice(before.input_count),button:smokeShell.model.button('touch-1').getState()},pointer_events:smokePointerLog.slice(-12)};smokeRun.input_traces[smokeRun.input_traces.length-1]=trace;return trace;},{p,before});
}
async function read(){return page.evaluate(()=>({receipt:smokeRun.runtime.receipt,events:smokeRun.events,input_traces:smokeRun.input_traces,pointer_events:globalThis.smokePointerLog,samples:smokeRun.samples,observations:smokeRun.observations,frames:smokeRun.frames,serial:smokeRun.serialAll,errors:smokeRun.errors,geometry_rest:smokeRun.rest,status:smokeRun.runtime.status,session:smokeRun.runtime.sessionId,generation:smokeRun.runtime.generation,machine_events:smokeRun.runtime.machineEvents,inputs:smokeRun.runtime.inputs,diagnostics:smokeRun.runtime.diagnostics,observation:smokeRun.runtime.observe(),engine_ownership:smokeRun.runtime.readEngineOwnership(),page_wall_ms:performance.now()}));}
async function waitEvent(kind,timeout=180000,boot=0){await page.waitForFunction(({kind,boot})=>smokeRun.events.some(e=>e.kind===kind&&(!boot||e.boot===boot)),{kind,boot},{timeout});}
async function startCase(name,image){
 const row={name,image_sha256:sha(await readFile(image)),status:'RUNNING'};report.cases.push(row);assert.equal(row.image_sha256,images.get(name).sha256,'Fixture image SHA changed: '+name);
 const context=await browser.newContext({viewport:{width:1300,height:1000}});page=await context.newPage();
 page.on('pageerror',e=>report.errors.push({name,error:e.message}));page.on('request',r=>requests.push({name,url:r.url()}));
 await page.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>{report.blocked.push(route.request().url());return route.abort('blockedbyclient');});
 await page.goto(report.url,{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>crossOriginIsolated&&document.querySelector('#deviceMount')?.dataset.deviceId==='cores3',{}, {timeout:45000});
 await page.evaluate(async origin=>{
  globalThis.smokePointerLog=[];for(const type of ['pointerdown','pointerup','pointercancel','mousedown','mouseup'])document.addEventListener(type,e=>{if(!globalThis.smokeRun)return;const el=e.target,hit=smokeShell.viewer.pick({clientX:e.clientX,clientY:e.clientY});smokePointerLog.push({type,wall_ms:performance.now(),x:e.clientX,y:e.clientY,target:{tag:el?.tagName,id:el?.id,classes:typeof el?.className==='string'?el.className:null},hit:hit?.component?.id});},true);
  const {ModelDeviceShell}=await import(new URL('platform/web/model-shell.js?v=20261026h',origin)),create=ModelDeviceShell.create;
  ModelDeviceShell.create=async function(...args){const shell=await create.apply(this,args);if(args[1].id==='stackchan')globalThis.smokeShell=shell;return shell;};
  const {PublicQemuRuntime}=await import(new URL('platform/web/public-qemu-runtime.js',origin));
  const THREE=await import(new URL('platform/web/vendor/three/three.module.js',origin));
  const {sha256Bytes}=await import(new URL('platform/web/sha256.js',origin));
  const start=PublicQemuRuntime.prototype.start;
  PublicQemuRuntime.prototype.start=function(...args){
   if(args[0].device==='stackchan'){
    const runtime=this,err=this.onError,deviceState=this.onDeviceState,serial=this.onSerial,frame=this.onFrame;
    globalThis.smokeRun={runtime,errors:[],samples:[],observations:[],frames:[],events:[],input_traces:[],serialAll:'',line:'',phase:'boot',boot:1,rest:null};
    const geometry=()=>{
     const m=smokeShell.model,root=m.root,lcd=m.find('lcd','display'),yaw=m.find('yaw','joint'),pitch=m.find('pitch','joint');root.updateWorldMatrix(true,true);
     const inverse=root.matrixWorld.clone().invert();
     const rel=o=>new THREE.Matrix4().multiplyMatrices(inverse,o.matrixWorld);
     const lcdMatrix=rel(lcd.panel),center=new THREE.Vector3().setFromMatrixPosition(lcdMatrix).toArray();
     const normal=new THREE.Vector3(0,0,1).applyNormalMatrix(new THREE.Matrix3().getNormalMatrix(lcdMatrix)).toArray();
     const base=rel(m.parts.base).toArray(),usb=rel(m.port('base-usb').object3d).toArray();
     const ancestors=[];for(let o=lcd.panel;o;o=o.parent)ancestors.push(o.uuid);
     return {center,normal,base,usb,pitch_in_yaw:pitch.object3d.parent===yaw.object3d,lcd_in_pitch:ancestors.includes(pitch.object3d.uuid),lcd_in_yaw:ancestors.includes(yaw.object3d.uuid),base_in_yaw:(()=>{for(let o=m.parts.base;o;o=o.parent)if(o===yaw.object3d)return true;return false;})()};
    };
    smokeRun.rest=geometry();
    const originalAsk=this.ask;this.ask=async function(op,...rest){const result=await originalAsk.call(this,op,...rest);if(op==='outputs'&&this.lastDeviceState)smokeRun.observations.push({wall_ms:performance.now(),phase:smokeRun.phase,boot:smokeRun.boot,readback:structuredClone(result??null),state:structuredClone(this.lastDeviceState)});return result;};
    this.onError=e=>{smokeRun.errors.push(e.message);err(e);};
    this.onSerial=text=>{smokeRun.serialAll+=text;serial(text);smokeRun.line+=text;let at;while((at=smokeRun.line.indexOf('\n'))>=0){const line=smokeRun.line.slice(0,at).trim();smokeRun.line=smokeRun.line.slice(at+1);try{const e=JSON.parse(line);if(String(e.nonce||'').startsWith('stackchan-')){smokeRun.events.push(e);if(e.phase)smokeRun.phase=e.phase;if(e.boot)smokeRun.boot=e.boot;}}catch{}}};
    this.onFrame=f=>{frame(f);const d=smokeShell.model.find('lcd','display'),expected=new Uint8Array(d.buffer.length);for(let i=0,j=0;i<f.pixels.length;i+=2,j+=4){const v=f.pixels[i]|f.pixels[i+1]<<8;expected[j]=((v>>11)&31)<<3|((v>>11)&31)>>2;expected[j+1]=((v>>5)&63)<<2|((v>>5)&63)>>4;expected[j+2]=(v&31)<<3|(v&31)>>2;expected[j+3]=255;}
     smokeRun.frames.push({phase:smokeRun.phase,boot:smokeRun.boot,sequence:f.sequence,source_sequence:f.sourceSequence,hash:sha256Bytes(f.pixels),lcd_hash:sha256Bytes(d.buffer),expected_lcd_hash:sha256Bytes(expected),pixels_match:expected.every((v,i)=>v===d.buffer[i])});};
    this.onDeviceState=s=>{deviceState(s);const g=geometry(),rest=smokeRun.rest,y=(s.servos[0].present_position-460)*5/16*Math.PI/180,p=Math.max(0,Math.min(90,(s.servos[1].present_position-620)*5/16))*Math.PI/180;
     const rotP=v=>[v[0],Math.cos(p)*v[1]+Math.sin(p)*v[2],-Math.sin(p)*v[1]+Math.cos(p)*v[2]],rotY=v=>[Math.cos(y)*v[0]+Math.sin(y)*v[2],v[1],-Math.sin(y)*v[0]+Math.cos(y)*v[2]],sub=(a,b)=>a.map((v,i)=>v-b[i]),add=(a,b)=>a.map((v,i)=>v+b[i]);
     const pp=[0,6.65,-2],yp=[0,-24.15,-2],expectedCenter=add(rotY(sub(add(rotP(sub(rest.center,pp)),pp),yp)),yp),expectedNormal=rotY(rotP(rest.normal));
     const diff=(a,b)=>Math.max(...a.map((v,i)=>Math.abs(v-b[i])));
     smokeRun.samples.push({phase:smokeRun.phase,boot:smokeRun.boot,wall_ms:performance.now(),state:structuredClone(s),yaw:smokeShell.model.find('yaw','joint').getState(),pitch:smokeShell.model.find('pitch','joint').getState(),geometry:{...g,expected_center:expectedCenter,expected_normal:expectedNormal,center_error_mm:diff(g.center,expectedCenter),normal_error:diff(g.normal,expectedNormal),fixed_base_error:diff(g.base,rest.base),fixed_usb_error:diff(g.usb,rest.usb)},actuator:{code:document.querySelector('#actuatorStatus')?.dataset.code,text:document.querySelector('#actuatorStatus')?.textContent}});
    };
   }
   return start.apply(this,args);
  };
 },report.url);
 await page.locator('button[data-device-id="stackchan"]').click();await page.waitForFunction(()=>globalThis.smokeShell?.device.id==='stackchan',{}, {timeout:45000});
 await page.locator('.advanced-options > summary').click();await page.locator('#runtimeMode').selectOption('browser');await page.locator('input[name="firmwareSource"][value="local"]').check();
 await page.locator('#firmwareFile').setInputFiles(image);await page.locator('#firmwareSha').fill(row.image_sha256);await page.locator('#startBtn').click();observedRuns++;
 await page.waitForFunction(()=>globalThis.smokeRun?.runtime.receipt&&smokeRun.runtime.lastFrame&&smokeRun.samples.length>2,{}, {timeout:180000});
 check(name+': exact-firmware-WASM',await page.evaluate(({image,wasm})=>smokeRun.runtime.receipt.firmwareSha256===image&&smokeRun.runtime.receipt.wasmSha256===wasm,{image:row.image_sha256,wasm:expectedWasm}));
 return {row,context};
}
async function finishCase(row,context){
 Object.assign(row,await read());
 check(row.name+': independent-matrix-geometry',row.samples.length>3&&row.samples.every(s=>s.geometry.center_error_mm<1e-7&&s.geometry.normal_error<1e-9&&s.geometry.fixed_base_error<1e-9&&s.geometry.fixed_usb_error<1e-9&&s.geometry.pitch_in_yaw&&s.geometry.lcd_in_pitch&&s.geometry.lcd_in_yaw&&!s.geometry.base_in_yaw),{samples:row.samples.length,max_center_mm:Math.max(...row.samples.map(s=>s.geometry.center_error_mm)),max_normal:Math.max(...row.samples.map(s=>s.geometry.normal_error))});
 check(row.name+': actual-guest-frame-on-LCD',row.frames.length>1&&row.frames.every(f=>f.pixels_match),{frames:row.frames.length,distinct_hashes:new Set(row.frames.map(f=>f.hash)).size});
 check(row.name+': QOM-present-matches-joints',row.samples.every(s=>Math.abs(s.yaw.angleDeg-(s.state.servos[0].present_position-460)*5/16)<1e-8&&Math.abs(s.pitch.angleDeg-Math.max(0,Math.min(90,(s.state.servos[1].present_position-620)*5/16)))<1e-8));
 check(row.name+': no-SDK-UART-fallback',!/ignore invalid current pos|fallback angle/.test(row.serial)&&row.errors.length===0,row.errors);
 await page.screenshot({path:resolve(out,row.name+'-finished.png'),fullPage:true});await page.locator('#stopBtn').click();await page.waitForFunction(()=>smokeRun.runtime.status==='stopped'&&!smokeRun.runtime.iframe,{}, {timeout:45000});
 row.cleanup=await page.evaluate(()=>smokeRun.runtime.evidence().cleanup);check(row.name+': natural-cleanup',row.cleanup?.gracefulExit&&row.cleanup.exitCode===0&&row.cleanup.explicitWorkerDisposal,row.cleanup);
 row.worker_targets=await targets.waitUntilClosed({minimumObserved:observedRuns*6,timeoutMs:30000});
 check(row.name+': all-six-runtime-workers-closed-before-context',row.worker_targets.ok&&row.worker_targets.observed.length===observedRuns*6,row.worker_targets);
 row.status='PASS';await writeFile(resolve(out,row.name+'-serial.txt'),row.serial);await writeFile(resolve(out,row.name+'-report.json'),JSON.stringify(row,null,2)+'\n');
 let closeTimer;try{await Promise.race([context.close(),new Promise((_,reject)=>{closeTimer=setTimeout(()=>reject(Error(row.name+': context.close exceeded 30000ms')),30000);})]);}finally{clearTimeout(closeTimer);}page=null;
}
const phaseSamples=(row,phase,boot=1)=>row.samples.filter(s=>s.phase===phase&&s.boot===boot);
const last=(row,name,boot=1)=>phaseSamples(row,name,boot).at(-1);
try{
 report.provenance=await capturePublicQemuProvenance({repo,site,testScript:'platform/tests/test_stackchan_motion_guest.mjs'});
 server=createServer(async(req,res)=>{try{const p=new URL(req.url,'http://localhost').pathname;if(!p.startsWith(base)){res.writeHead(404).end();return;}const f=resolve(site,decodeURIComponent(p.slice(base.length))||'index.html');if(!f.startsWith(site+'/')){res.writeHead(403).end();return;}const b=await readFile(f);if(['platform/web/public.js','platform/web/public-qemu-runtime.js','platform/web/model-shell.js'].some(v=>f===resolve(site,v)))report.served_observation_files[f.slice(site.length+1)]=sha(b);res.writeHead(200,{'content-type':mime[extname(f)]||'application/octet-stream','cache-control':'no-cache'});res.end(b);}catch{res.writeHead(404).end();}});
 await new Promise(yes=>server.listen(0,'127.0.0.1',yes));report.url=`http://127.0.0.1:${server.address().port}${base}`;
 browser=await chromium.launch({headless:true,...(process.env.M5_WASM_CHROME?{executablePath:process.env.M5_WASM_CHROME}:{}),args:['--enable-webgl','--use-gl=angle',...(hardwareGPU?['--use-angle=metal','--ignore-gpu-blocklist']:['--use-angle=swiftshader'])]});report.browser=browser.version();report.hardware_gpu=hardwareGPU;targets=await observeWorkerTargets(browser);
 for(const name of wanted){
  const image=images.get(name).path;
  const {row,context}=await startCase(name,image);
  if(name==='original'){
   await page.waitForTimeout(2000);await page.evaluate(()=>smokeRun.phase='original-dance');row.top_input=await topClick();await page.waitForTimeout(18000);Object.assign(row,await read());
   const ss=phaseSamples(row,'original-dance'),span=(axis,key)=>Math.max(...ss.map(s=>s.state.servos[axis][key]))-Math.min(...ss.map(s=>s.state.servos[axis][key]));
   check('original: torque-disabled-negative-control',ss.length>10&&span(0,'goal_position')>200&&span(1,'goal_position')>100&&span(0,'present_position')===0&&span(1,'present_position')===0&&ss.every(s=>s.state.servos.every(v=>v.torque===0)&&s.actuator.code==='torque-disabled'),{sample_count:ss.length});
  }else if(name==='dance'){
   await page.waitForFunction(()=>smokeRun.serialAll.includes('phase=ready'),{}, {timeout:120000});
   row.dances=[];
   for(let dance=1;dance<=3;dance++){
    await page.waitForFunction(n=>(smokeRun.serialAll.match(/phase=idle_release/g)||[]).length>=n,dance,{timeout:15000});
    await page.evaluate(n=>{smokeRun.phase='dance-'+n;},dance);row.dances.push({dance,input:await topClick()});
    await page.waitForFunction(n=>(smokeRun.serialAll.match(/phase=top_pressed/g)||[]).length>=n,dance,{timeout:10000});
    await page.waitForFunction(n=>(smokeRun.serialAll.match(/phase=finished/g)||[]).length>=n,dance,{timeout:45000});
    await page.waitForTimeout(400);await page.evaluate(()=>{smokeShell.viewer.setView('front',{duration:0});smokeShell.viewer.fit({duration:0});smokeShell.viewer.requestRender();});
    await page.screenshot({path:resolve(out,'dance-'+dance+'.png'),fullPage:true});
   }
   Object.assign(row,await read());
   check('dance: original-three-keyframe-tables',row.dances.every(d=>(row.serial.match(new RegExp(`phase=target dance=${d.dance} frame=`, 'g'))||[]).length===[14,8,8][d.dance-1]));
   check('dance: actual-Shake-yaw-and-Nod-pitch',(()=>{const shake=phaseSamples(row,'dance-2'),nod=phaseSamples(row,'dance-3'),span=(s,a)=>Math.max(...s.map(x=>x.state.servos[a].present_position))-Math.min(...s.map(x=>x.state.servos[a].present_position));return shake.length>2&&nod.length>2&&span(shake,0)>100&&span(nod,1)>80;})());
  }else if(name==='scs_command_edges'){
   await waitEvent('done');Object.assign(row,await read());
   check('edges: no-concurrent-BSP-motion',row.events.some(e=>e.kind==='ready'&&e.no_bsp_motion_thread&&e.uart_driver&&e.power_driver));
   for(const phase of ['write_move_repeat','reg_move_repeat','sync_move_repeat']){
    const end=row.events.find(e=>e.kind==='phase_end'&&e.phase===phase),repeats=row.events.filter(e=>e.kind==='after_repeat'&&e.phase===phase);
    const cmd=row.events.find(e=>e.kind==='command'&&e.phase===phase&&/^WritePos800Time/.test(e.name)),finished=row.events.find(e=>e.phase===phase&&['sample','after_repeat','phase_end'].includes(e.kind)&&e.present===800&&e.moving===0);check('edges: '+phase+'-no-restart',repeats.length===7&&repeats.every(e=>e.moving===1&&e.present<800&&e.time_ms===4000)&&end?.present===800&&end.moving===0&&finished&&finished.ms-cmd.ms<=4500,{repeats:repeats.length,mid_motion:repeats.map(e=>({ms:e.ms,present:e.present,moving:e.moving})),completion_ms:finished?finished.ms-cmd.ms:null,end});
   }
   check('edges: official-SwitchMode-restores-custom-limits',row.events.some(e=>e.kind==='pwm_readback'&&e.min===0&&e.max===0)&&row.events.some(e=>e.kind==='restored_readback'&&e.min===100&&e.max===900)&&row.events.some(e=>e.kind==='command'&&e.name==='SwitchMode0'&&e.rc===0));
   check('edges: restored-position-actually-moves',row.events.some(e=>e.kind==='done'&&e.present===650&&e.goal===650&&e.moving===0));
  }else{
   await waitEvent('ready',180000,1);row.top_input=await topClick();const posePhase=name==='motion_lifecycle'?'combined':'custom_combined';await page.waitForFunction(phase=>smokeRun.samples.some(s=>s.phase===phase&&s.state.servos[0].present_position>550&&s.state.servos[1].present_position>690),posePhase,{timeout:240000});await page.evaluate(()=>{smokeShell.viewer.setView('front',{duration:0});smokeShell.viewer.fit({duration:0});smokeShell.viewer.requestRender();});await page.screenshot({path:resolve(out,name+'-combined-pose.png'),fullPage:true});await waitEvent('await_reset',240000,1);await page.waitForTimeout(250);Object.assign(row,await read());
   await page.evaluate(async()=>{await smokeRun.runtime.pause();await smokeRun.runtime.ask('outputs');});Object.assign(row,await read());
   const before={session:row.session,generation:row.generation,iframe:await page.evaluate(()=>smokeRun.runtime.iframe?.src),present:row.samples.at(-1).state.servos.map(s=>s.present_position)};
   row.pre_reset=before;
   if(name==='motion_lifecycle'){
    const os=row.observations,st=o=>o.state,pp=o=>st(o).servos.map(v=>v.present_position),same=(a,b)=>a.length===b.length&&a.every((v,i)=>v===b[i]),both=(o,n)=>st(o).servos.every(v=>v.torque===n),end=name=>row.events.find(e=>e.kind==='phase_end'&&e.phase===name);
    const offStart=os.findIndex(o=>st(o).powered&&both(o,0)&&same(pp(o),[460,620])&&st(o).servos.some(v=>v.goal_position!==v.present_position));
    const offEnd=os.findIndex((o,i)=>i>offStart&&st(o).servos.some(v=>v.torque===1));
    const enabled=os.findIndex((o,i)=>i>offEnd&&both(o,1)&&pp(o)[0]>=590&&pp(o)[1]>=705);
    const blocked=offStart>=0&&offEnd>offStart&&os.slice(offStart,offEnd).every(o=>st(o).powered&&both(o,0)&&same(pp(o),[460,620]));
    row.async_observation_boundary='UART phase markers are delayed relative to QOM. Guest phase_end SDK feedback proves firmware-phase positions; actual QOM readbacks (including unchanged confirmations) prove the ordered torque/power/shaft sequence without assigning a delayed serial label to an immediate snapshot.';
    row.auto_release_sequence={off_start:offStart,off_end:offEnd,enabled,blocked_readbacks:offEnd-offStart,guest_idle:end('auto_release_idle'),guest_blocked:end('auto_release_command'),guest_enabled:end('explicit_reenable')};
    check('lifecycle: auto-release-inhibits-motion-until-explicit-enable',blocked&&enabled>offEnd&&same(end('auto_release_idle')?.sdk_ddeg||[],[0,0])&&same(end('auto_release_command')?.sdk_ddeg||[],[0,0])&&end('explicit_reenable')?.sdk_ddeg[0]>400&&end('explicit_reenable')?.sdk_ddeg[1]>250,row.auto_release_sequence);
    const railOff=os.findIndex((o,i)=>i>enabled&&!st(o).powered),railOn=os.findIndex((o,i)=>i>railOff&&st(o).powered),recover=os.findIndex((o,i)=>i>railOn&&st(o).servos.some(v=>v.torque===1));
    const held=railOff>=0&&railOn>railOff&&recover>railOn&&os.slice(railOff,recover).every(o=>both(o,0)&&same(pp(o),pp(os[railOff])));
    row.rail_sequence={rail_off:railOff,rail_on:railOn,recovery:recover,held_pose:railOff>=0?pp(os[railOff]):null,guest_off:end('rail_off_hold'),guest_on:end('rail_on_no_torque')};
    check('lifecycle: rail-loss-and-volatility',held&&end('rail_off_hold')?.sdk_feedback_expected===false&&end('rail_on_no_torque')?.sdk_feedback_expected===true&&os.slice(recover).some(o=>st(o).powered&&both(o,1)&&same(pp(o),[460,620])),row.rail_sequence);
    const wire=row.events.filter(e=>e.kind==='wire_goal');check('lifecycle: actual-wire-time20-speed0',wire.length>8&&wire.every(e=>e.time_ms===20&&e.speed_raw===0),{wire_packets:wire.length});
    row.retarget_wire=wire.filter(e=>e.phase==='reverse_back').slice(0,8);
   }else{
    check('calibration: initial-and-pending-NVS-real-IDF',row.events.some(e=>e.kind==='nvs_ready'&&e.x===520&&e.y===700&&e.x_rc===0&&e.y_rc===0)&&row.events.some(e=>e.kind==='nvs_pending_reset'&&e.x===550&&e.y===720&&e.x_rc===0&&e.y_rc===0));
    const home=last(row,'custom_home'),pending=last(row,'write_pending_zero');check('calibration: SDK-home-and-physical-offset-remain-distinct',home?.state.servos[0].present_position===520&&home?.state.servos[1].present_position===700&&Math.abs(home.yaw.angleDeg-18.75)<1e-9&&Math.abs(home.pitch.angleDeg-25)<1e-9&&pending?.state.servos[0].goal_position===616&&pending?.state.servos[1].goal_position===796);
    check('calibration: visual-clamp-retains-raw',phaseSamples(row,'custom_pitch_limit').some(s=>s.state.servos[1].present_position>908&&s.pitch.angleDeg===90&&s.actuator.code==='visual-range'));
   }
   await page.evaluate(async()=>{await smokeRun.runtime.reset();await smokeRun.runtime.ask('outputs');});row.paused_after_reset=await read();check(name+': exact-paused-reset-keeps-physical-pose',row.paused_after_reset.session===before.session&&row.paused_after_reset.generation===before.generation&&row.paused_after_reset.samples.at(-1).state.servos.every((s,i)=>s.present_position===before.present[i]),{before,paused_after:row.paused_after_reset.samples.at(-1).state});await page.evaluate(()=>smokeRun.runtime.resume());await waitEvent('ready',180000,2);await page.waitForTimeout(500);row.after_reset=await read();
   const bootZero=name==='motion_calibration'?[550,720]:[460,620],expectedInitGoal=before.present.map((raw,i)=>{const angle=Math.max(i===0?-1280:0,Math.min(i===0?1280:900,Math.trunc((raw-bootZero[i])*50/16)));return Math.max(0,Math.min(1000,bootZero[i]+Math.trunc(Math.trunc(angle*16/5)/10)));});
   const bootReady=row.after_reset.events.find(e=>e.kind==='ready'&&e.boot===2),actualBoot=row.after_reset.samples.at(-1).state.servos;
   row.bsp_init_boundary={mechanical_before:before.present,software_zero:bootZero,expected_init_goal:expectedInitGoal,actual_goal_packet:bootReady?.wire_last,actual_after:actualBoot.map(s=>s.present_position),reason:'Unmodified Servo::init teleports to ReadPos-derived integer decidegrees and calls update before disabling torque. This can command a one-tick rounding move; exact controller RESET pose is checked separately while CPUs remain paused.'};
   check(name+': same-instance-BSP-init-follows-real-quantized-command',row.after_reset.session===before.session&&row.after_reset.generation===before.generation&&bootReady?.wire_last.every((w,i)=>w[0]===expectedInitGoal[i]&&w[1]===20&&w[2]===0)&&actualBoot.every((s,i)=>s.torque===0&&s.present_position>=Math.min(before.present[i],expectedInitGoal[i])&&s.present_position<=Math.max(before.present[i],expectedInitGoal[i])),row.bsp_init_boundary);
   if(name==='motion_calibration')check('calibration: RESET-reloads-pending-NVS',row.after_reset.events.some(e=>e.kind==='nvs_ready'&&e.boot===2&&e.x===550&&e.y===720&&e.x_rc===0&&e.y_rc===0));
   row.reset_top_input=await topClick();await waitEvent('reset_home_done',180000,2);await page.waitForTimeout(250);Object.assign(row,await read());
   const expected=name==='motion_calibration'?[550,720]:[460,620];check(name+': reset-home-follows-real-calibration',row.samples.at(-1).state.servos.every((s,i)=>s.present_position===expected[i]),{expected,actual:row.samples.at(-1).state.servos});
  }
  await finishCase(row,context);
 }
 report.workers=await targets.waitUntilClosed({minimumObserved:observedRuns*6,timeoutMs:30000});check('all-runtime-workers-closed',report.workers.ok&&report.workers.observed.length===observedRuns*6,report.workers);
 check('served-production-observation-files-match-manifest',Object.entries(report.served_observation_files).length===3&&Object.entries(report.served_observation_files).every(([p,h])=>assetHashes.get(p)===h),report.served_observation_files);
 check('zero-user-services-or-API-requests',report.blocked.length===0&&!requests.some(r=>/\/api\/v1|:8787\b|:8830\b/.test(r.url)));check('no-page-errors',report.errors.length===0,report.errors);report.status='PASS';
}catch(error){if(report.cases.at(-1)?.status==='RUNNING')report.cases.at(-1).status='FAIL';report.status='FAIL';report.error=error.stack;process.exitCode=1;if(page){report.failure=await read().catch(()=>null);await page.screenshot({path:resolve(out,'failure.png'),fullPage:true}).catch(()=>{});}}
finally{report.finished_at=new Date().toISOString();report.forced_cleanup_after_failure=report.status!=='PASS';try{await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');const concise={kind:report.kind,status:report.status,error:report.error,expected_wasm:report.expected_wasm,harness_sha256:report.harness_sha256,export_manifest_sha256:report.export_manifest_sha256,started_at:report.started_at,finished_at:report.finished_at,hardware_validation:report.hardware_validation,checks:report.checks.map(c=>c.name==='all-runtime-workers-closed'?{name:c.name,ok:c.ok,detail:{observed:c.detail?.observed?.length,live:c.detail?.live?.length,source:c.detail?.source}}:c),workers:report.workers?{ok:report.workers.ok,source:report.workers.source,minimum_observed:report.workers.minimum_observed,observed_count:report.workers.observed.length,live_count:report.workers.live.length,event_count:report.workers.events.length}:null,instrumentation:report.instrumentation,served_observation_files:report.served_observation_files,cases:report.cases.map(r=>({name:r.name,status:r.status,firmware_sha256:r.image_sha256,samples:r.samples?.length,confirmed_qom_reads:r.observations?.length,unchanged_qom_confirmations:r.observations?.filter(o=>o.readback?.unchanged).length,async_observation_boundary:r.async_observation_boundary,input_traces:r.input_traces?.map(t=>({target:t.before?.dom,is_canvas:t.before?.is_canvas,model_hit:t.before?.model_hit,inputs:t.after?.inputs})),frames:r.frames?.length,unique_frame_hashes:r.frames?new Set(r.frames.map(f=>f.hash)).size:0,cleanup:r.cleanup,worker_targets:r.worker_targets?{ok:r.worker_targets.ok,source:r.worker_targets.source,observed_count:r.worker_targets.observed.length,live_count:r.worker_targets.live.length}:null,retarget_wire:r.retarget_wire,geometry_max_center_mm:r.samples?.length?Math.max(...r.samples.map(s=>s.geometry.center_error_mm)):null,geometry_max_normal:r.samples?.length?Math.max(...r.samples.map(s=>s.geometry.normal_error)):null,pre_reset:r.pre_reset,post_reset:r.after_reset?{session:r.after_reset.session,generation:r.after_reset.generation,machine_events:r.after_reset.machine_events}:null}))};let conciseText=JSON.stringify(concise,null,2)+'\n';if(Buffer.byteLength(conciseText)>65535){concise.checks=concise.checks.map(({name,ok})=>({name,ok}));concise.full_check_details='See ignored report.json';conciseText=JSON.stringify(concise,null,2)+'\n';}assert.ok(Buffer.byteLength(conciseText)<65536,'Concise summary exceeds 64KiB');await writeFile(resolve(out,'concise-summary.json'),conciseText);}finally{await targets?.detach().catch(()=>{});await browser?.close().catch(()=>{});if(server)await new Promise(done=>server.close(done));console.log('FINAL',report.status,report.error||'',out);}}
