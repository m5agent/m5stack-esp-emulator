// Opt-in actual Arduino/M5Cardputer guest validation. No firmware is bundled.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {dirname,extname,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {capturePublicQemuProvenance} from './public_qemu_artifacts.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';
import {CARDPUTER_ADV_KEYS} from '../web/cardputer-adv-keymap.js';

if(!process.env.M5_PUBLIC_SITE||!process.env.M5_CARDPUTER_IMAGE){console.log('SKIP: explicit M5_PUBLIC_SITE/M5_CARDPUTER_IMAGE required');process.exit(0);}
const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..'),site=resolve(process.env.M5_PUBLIC_SITE),image=resolve(process.env.M5_CARDPUTER_IMAGE);
const out=resolve(process.env.M5_CARDPUTER_OUT||resolve(repo,'.work/cardputer-input-display'));
assert.ok(out.startsWith(resolve(repo,'.work')+'/'));await mkdir(out,{recursive:false});
const sha=value=>createHash('sha256').update(value).digest('hex'),imageSHA=sha(await readFile(image));
assert.equal(imageSHA,process.env.M5_CARDPUTER_IMAGE_SHA256,'Explicit image identity required');
assert.match(process.env.M5_CARDPUTER_WASM_SHA256||'',/^[a-f0-9]{64}$/,'Explicit WASM identity required');
const provenance=await capturePublicQemuProvenance({repo,site,testScript:'platform/tests/test_public_qemu_cardputer_input_display.mjs'});
const basePath=provenance.base_path,requests=[],blocked=[];
const report={kind:'cardputer-adv-arduino-keyboard-display-guest',status:'FAIL',started_at:new Date().toISOString(),firmware_sha256:imageSHA,
  wasm_sha256:process.env.M5_CARDPUTER_WASM_SHA256,provenance,checks:[],keys:[],hardware_validation:'NOT RUN'};
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.wasm':'application/wasm','.css':'text/css','.png':'image/png','.webp':'image/webp','.svg':'image/svg+xml'};
const server=createServer(async(req,res)=>{try{const pathname=new URL(req.url,'http://localhost').pathname;if(!pathname.startsWith(basePath)){res.writeHead(404).end();return;}const file=resolve(site,decodeURIComponent(pathname.slice(basePath.length))||'index.html');if(!file.startsWith(site+'/')){res.writeHead(403).end();return;}const bytes=await readFile(file);res.writeHead(200,{'content-type':mime[extname(file)]||'application/octet-stream','cache-control':'no-cache'});res.end(bytes);}catch{if(!res.headersSent)res.writeHead(404);res.end();}});
await new Promise(yes=>server.listen(0,'127.0.0.1',yes));report.url=`http://127.0.0.1:${server.address().port}${basePath}`;
const modules=process.env.M5_WASM_NODE_MODULES||resolve(repo,'platform/tests/node_modules'),{chromium}=await import(pathToFileURL(resolve(modules,'playwright/index.mjs')));
let browser,context,page,targets;
function check(name,ok,detail){ok=Boolean(ok);report.checks.push({name,ok,detail});console.log(name,ok?'PASS':'FAIL');}
async function eventState(){return page.evaluate(()=>({receipt:cardputerRun.runtime.receipt,serial:cardputerRun.serial,events:cardputerRun.events,frames:cardputerRun.frames,inputs:cardputerRun.runtime.inputs,status:cardputerRun.runtime.status,display:cardputerRun.runtime.display,errors:cardputerRun.errors}));}
async function keyPoint(row,col){return page.evaluate(async({row,col})=>{const shell=cardputerShell,c=shell.model.list('button').find(c=>c.meta.matrix?.[0]===row&&c.meta.matrix?.[1]===col);if(!c)throw Error('No physical key '+row+','+col);const THREE=await import(new URL('platform/web/vendor/three/three.module.js',document.baseURI)),v=c.object3d.getWorldPosition(new THREE.Vector3());v.project(shell.viewer.camera);const box=shell.viewer.renderer.domElement.getBoundingClientRect(),x=box.left+(v.x+1)*box.width/2,y=box.top+(1-v.y)*box.height/2;for(const dy of [0,-1,1,-2,2,-4,4])for(const dx of [0,-1,1,-2,2,-4,4])if(shell.viewer.pick({clientX:x+dx,clientY:y+dy})?.component===c)return {id:c.id,x:x+dx,y:y+dy};throw Error('Physical key not DOM-pickable '+c.id);},{row,col});}
async function waitKeys(positions,after=0){await page.waitForFunction(({positions,after})=>cardputerRun.events.some(e=>e.kind==='keys'&&e.seq>after&&JSON.stringify([...e.positions].sort())===JSON.stringify([...positions].sort())),{positions,after},{timeout:10000});return page.evaluate(({positions,after})=>cardputerRun.events.find(e=>e.kind==='keys'&&e.seq>after&&JSON.stringify([...e.positions].sort())===JSON.stringify([...positions].sort())),{positions,after});}
async function lastSeq(){return page.evaluate(()=>cardputerRun.events.at(-1)?.seq||0);}
async function phase(kind,rotation,after=0){await page.waitForFunction(({kind,rotation,after})=>cardputerRun.events.some(e=>e.kind===kind&&e.rotation===rotation&&e.seq>after),{kind,rotation,after},{timeout:180000});return page.evaluate(({kind,rotation,after})=>cardputerRun.events.find(e=>e.kind===kind&&e.rotation===rotation&&e.seq>after),{kind,rotation,after});}
async function captureStable(){
  let previous='';
  for(let attempt=0;attempt<12;attempt++){
    const value=await page.evaluate(async()=>{const r=cardputerRun.runtime,freshDisplay=await r.ask('display');await r.ask('frame');const f=r.lastFrame,canvas=document.querySelector('#rawFrameCanvas'),rgba=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;const pixel=(x,y)=>{const i=(y*f.width+x)*2;return f.pixels[i]|f.pixels[i+1]<<8;};return {freshDisplay,display:structuredClone(r.display),presentation:cardputerShell.presentationRotationDeg??0,sequence:f.sequence,width:f.width,height:f.height,pixels:Array.from(f.pixels),native_corners:[[4,4],[f.width-5,4],[4,f.height-5],[f.width-5,f.height-5]].map(([x,y])=>pixel(x,y)),planar:[canvas.width,canvas.height],planar_corners:[[4,4],[canvas.width-5,4],[4,canvas.height-5],[canvas.width-5,canvas.height-5]].map(([x,y])=>Array.from(rgba.slice((y*canvas.width+x)*4,(y*canvas.width+x)*4+3)))};});
    const digest=sha(new Uint8Array(value.pixels));
    if(previous===digest&&JSON.stringify(value.freshDisplay)===JSON.stringify(value.display))return {...value,native_sha256:digest};
    previous=digest;await page.waitForTimeout(250);
  }
  throw Error('No stable frame/display snapshot while guest waits for a real Enter edge');
}
async function advance(kind,rotation){const seq=await lastSeq();await page.keyboard.down('Enter');let next;try{next=await phase(kind,rotation,seq);}finally{await page.keyboard.up('Enter');}await waitKeys([],next?.seq??seq);return next;}
try{
  browser=await chromium.launch({headless:true,executablePath:process.env.M5_WASM_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:process.env.M5_WASM_GPU==='hardware'?['--enable-webgl','--use-gl=angle']:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  report.browser=browser.version();targets=await observeWorkerTargets(browser);context=await browser.newContext({viewport:{width:1400,height:1100}});page=await context.newPage();
  page.on('request',r=>requests.push(r.url()));page.on('pageerror',e=>(report.page_errors??=[]).push(e.message));
  await page.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>{blocked.push(route.request().url());return route.abort('blockedbyclient');});
  await page.goto(report.url,{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>crossOriginIsolated&&document.querySelector('#deviceMount')?.dataset.deviceId==='cores3',{}, {timeout:45000});
  await page.evaluate(async origin=>{
    const {ModelDeviceShell}=await import(new URL('platform/web/model-shell.js?v=20261026h',origin)),create=ModelDeviceShell.create;
    ModelDeviceShell.create=async function(...args){const shell=await create.apply(this,args);if(args[1].id==='cardputer-adv')globalThis.cardputerShell=shell;return shell;};
    const {PublicQemuRuntime}=await import(new URL('platform/web/public-qemu-runtime.js',origin)),start=PublicQemuRuntime.prototype.start;
    PublicQemuRuntime.prototype.start=function(...args){if(args[0].device==='cardputer-adv'){
      const r=this,serial=r.onSerial,frame=r.onFrame,error=r.onError;globalThis.cardputerRun={runtime:r,serial:'',line:'',events:[],frames:[],errors:[],phase:'boot',rotation:0};
      r.onError=e=>{cardputerRun.errors.push(e.message);error(e);};
      r.onSerial=text=>{serial(text);cardputerRun.serial+=text;cardputerRun.line+=text;let at;while((at=cardputerRun.line.indexOf('\n'))>=0){const line=cardputerRun.line.slice(0,at);cardputerRun.line=cardputerRun.line.slice(at+1);try{const event=JSON.parse(line);if(event.nonce==='cardputer-input-orientation-20261030-v1'){cardputerRun.events.push(event);if(event.kind.startsWith('rotation-')||event.kind==='ready'){cardputerRun.phase=event.kind;cardputerRun.rotation=event.rotation;}}}catch{}}};
      r.onFrame=f=>{frame(f);const d=cardputerShell.display;let textureMatches=!!d&&d.width===f.width&&d.height===f.height;for(let i=0,j=0;textureMatches&&i<f.pixels.length;i+=2,j+=4){const v=f.pixels[i]|f.pixels[i+1]<<8,rr=v>>11&31,gg=v>>5&63,bb=v&31;textureMatches=d.buffer[j]===(rr<<3|rr>>2)&&d.buffer[j+1]===(gg<<2|gg>>4)&&d.buffer[j+2]===(bb<<3|bb>>2);}
        const sample=(x,y)=>{const i=(y*f.width+x)*2;return f.pixels[i]|f.pixels[i+1]<<8;};
        const canvas=document.querySelector('#rawFrameCanvas');
        cardputerRun.frames.push({rotation:cardputerRun.rotation,phase:cardputerRun.phase,sequence:f.sequence,width:f.width,height:f.height,display:structuredClone(r.display),presentation:cardputerShell.presentationRotationDeg??0,nativeRasterRotation:d?.meta?.nativeRasterRotation??0,textureMatches,corners:[[4,4],[f.width-5,4],[4,f.height-5],[f.width-5,f.height-5]].map(([x,y])=>sample(x,y)),planar:[canvas.width,canvas.height]});};
    }return start.apply(this,args);};
  },report.url);
  await page.locator('button[data-device-id="cardputer-adv"]').click();await page.waitForFunction(()=>globalThis.cardputerShell&&document.querySelector('#deviceMount')?.dataset.deviceId==='cardputer-adv',{}, {timeout:45000});
  await page.locator('.advanced-options > summary').click();await page.locator('#runtimeMode').selectOption('browser');await page.locator('input[name="firmwareSource"][value="local"]').check();await page.locator('#firmwareFile').setInputFiles(image);await page.waitForFunction(()=>!document.querySelector('#startBtn').disabled);await page.locator('#startBtn').click();
  await page.waitForFunction(()=>globalThis.cardputerRun?.runtime.receipt,{}, {timeout:30000});
  const receipt=await page.evaluate(()=>cardputerRun.runtime.receipt);
  assert.equal(receipt.firmwareSha256,imageSHA);assert.equal(receipt.wasmSha256,report.wasm_sha256);
  check('exact-image-and-WASM',true,receipt);
  await phase('rotation-full',0);await page.locator('#deviceMount .three-device-stage canvas').focus();
  report.rotation_snapshots=[];
  for(let rotation=0;rotation<4;rotation++){
    const full=await captureStable(),fullEvent=await phase('rotation-full',rotation);
    const partialEvent=await advance('rotation-partial',rotation),partial=await captureStable();
    check('rotation-'+rotation+'-driver-size',[fullEvent,partialEvent].every(e=>e.width===(rotation%2?240:135)&&e.height===(rotation%2?135:240)),[fullEvent,partialEvent]);
    check('rotation-'+rotation+'-partial-orientation-stable',[full,partial].every(f=>f.freshDisplay.orientation===(rotation%2?'landscape':'portrait')&&JSON.stringify(f.freshDisplay)===JSON.stringify(f.display)),{full:full.display,partial:partial.display});
    const expected=[[0x07e0,0xffe0,0xf800,0x001f],[0xf800,0x07e0,0x001f,0xffe0],[0x001f,0xf800,0xffe0,0x07e0],[0xffe0,0x001f,0x07e0,0xf800]][rotation];
    check('rotation-'+rotation+'-physical-four-corners',[full,partial].every(f=>JSON.stringify(f.native_corners)===JSON.stringify(expected)),{expected,observed:[full.native_corners,partial.native_corners]});
    let partialMatches=true;for(let y=50;y<58;y++)for(let x=40;x<48;x++){const [px,py]=rotation===0?[y,134-x]:rotation===1?[x,y]:rotation===2?[239-y,x]:[239-x,134-y],i=(py*240+px)*2;partialMatches&&=(partial.pixels[i]|partial.pixels[i+1]<<8)===0xf81f;}
    check('rotation-'+rotation+'-partial-64-pixels',partialMatches);
    const upright=[[255,0,0],[0,255,0],[0,0,255],[255,255,0]],inverted=[upright[3],upright[2],upright[1],upright[0]],expectedPlanar=rotation>=2?inverted:upright;
    check('rotation-'+rotation+'-planar-presentation-corners',JSON.stringify(partial.planar_corners)===JSON.stringify(expectedPlanar),{expected:expectedPlanar,actual:partial.planar_corners});
    report.rotation_snapshots.push({rotation,fullEvent,partialEvent,full,partial});
    await page.screenshot({path:resolve(out,'rotation-'+rotation+'.png'),fullPage:true});
    if(rotation<3)await advance('rotation-full',rotation+1);else await advance('ready',1);
  }
  const initial=await eventState();report.display_capture=initial;
  check('official-native-ADV-reader-selected',initial.events.some(e=>e.kind==='board'&&e.board===24&&e.keyboard_path==='official-M5Cardputer-IRQ-update'));
  check('all-frames-bind-native-texture',initial.frames.length>8&&initial.frames.every(f=>f.textureMatches));
  await page.screenshot({path:resolve(out,'keyboard-landscape.png'),fullPage:true});
  for(let row=0;row<4;row++)for(let col=0;col<14;col++){
    const point=await keyPoint(row,col),seq=await lastSeq();await page.mouse.move(point.x,point.y);await page.mouse.down();let down;
    try{down=await waitKeys([[row,col]],seq);}finally{await page.mouse.up();}const up=await waitKeys([],down?.seq??seq);report.keys.push({row,col,id:point.id,down,up});
  }
  check('56-physical-keys-original-IRQ-state-and-release',report.keys.length===56);
  const pcPhysical=[];
  for(const key of CARDPUTER_ADV_KEYS.filter(row=>row.browserCode)){
    const seq=await lastSeq();await page.keyboard.down(key.browserCode);let down;
    try{down=await waitKeys([[key.row,key.col]],seq);}finally{await page.keyboard.up(key.browserCode);}
    const up=await waitKeys([],down?.seq??seq);pcPhysical.push({code:key.browserCode,row:key.row,col:key.col,down,up});
  }
  check('all-direct-PC-codes-reach-their-real-physical-switch',pcPhysical.length===55
    &&pcPhysical.every(key=>key.down?.positions?.some(([row,col])=>row===key.row&&col===key.col)),pcPhysical);
  const modifiers=[[2,0,'fn'],[2,1,'shift'],[3,0,'ctrl'],[3,1,'opt'],[3,2,'alt'],[2,13,'enter'],[0,13,'backspace']];
  check('original-modifier-and-special-key-flags',modifiers.every(([row,col,flag])=>{const key=report.keys.find(k=>k.row===row&&k.col===col);return key?.down?.[flag]===1&&key.up[flag]===0;}));
  await page.locator('#deviceMount .three-device-stage canvas').focus();
  for(const code of ['ShiftLeft','ShiftRight']){
    const seq=await lastSeq();await page.keyboard.down(code);const shift=await waitKeys([[2,1]],seq);await page.keyboard.down('a');const chord=await waitKeys([[2,1],[2,2]],shift.seq);check(code+'-uppercase-through-original-reader',chord.shift&&chord.word.includes(65),chord);await page.keyboard.up('a');await waitKeys([[2,1]],chord.seq);await page.keyboard.up(code);await waitKeys([],chord.seq);
  }
  {
    const seq=await lastSeq();await page.keyboard.down('ShiftLeft');await waitKeys([[2,1]],seq);await page.keyboard.down('ShiftRight');await page.keyboard.up('ShiftLeft');
    await page.keyboard.down('a');const chord=await waitKeys([[2,1],[2,2]],seq);check('overlapping-PC-Shift-holds-preserve-native-switch',chord.shift&&chord.word.includes(65),chord);await page.keyboard.up('a');await waitKeys([[2,1]],chord.seq);await page.keyboard.up('ShiftRight');await waitKeys([],chord.seq);
  }
  const seq=await lastSeq();await page.keyboard.down('Backquote');const grave=await waitKeys([[0,0]],seq);check('PC-Backquote-is-physical-grave',grave.word.includes(96)&&!grave.fn,grave);await page.keyboard.up('Backquote');await waitKeys([],grave.seq);
  const aliases=[[['ShiftRight'],[[2,1]]],[['ControlRight'],[[3,0]]],[['MetaRight'],[[3,1]]],[['AltRight'],[[3,2]]],[['Escape'],[[2,0],[0,0]]],[['Delete'],[[2,0],[0,13]]]];
  const aliasResults=[];
  for(const [[code],positions] of aliases){
    const before=await lastSeq();await page.keyboard.down(code);let down;
    try{down=await waitKeys(positions,before);}finally{await page.keyboard.up(code);}
    const up=await waitKeys([],down?.seq??before);aliasResults.push({code,positions,down,up});
  }
  check('PC-right-modifier-Escape-and-Delete-aliases-reach-real-switches',
    aliasResults.every((row,index)=>JSON.stringify([...row.down.positions].sort())===JSON.stringify([...aliases[index][1]].sort()))
      && aliasResults[4].down.fn && aliasResults[5].down.fn,aliasResults);
  const arrows=[[['ArrowUp'],[[2,0],[2,11]],'up'],[['ArrowDown'],[[2,0],[3,11]],'down'],[['ArrowLeft'],[[2,0],[3,10]],'left'],[['ArrowRight'],[[2,0],[3,12]],'right']];
  const arrowResults=[];
  for(const [[code],positions,flag] of arrows){
    const before=await lastSeq();await page.keyboard.down(code);let down;
    try{down=await waitKeys(positions,before);}finally{await page.keyboard.up(code);}
    const up=await waitKeys([],down?.seq??before);arrowResults.push({code,positions,flag,down,up});
  }
  check('PC-arrow-aliases-are-real-Fn-chords',arrowResults.every(row=>row.down.fn&&row.down[row.flag]),arrowResults);
  const fnPoint=await keyPoint(2,0),beforeFn=await lastSeq();await page.mouse.move(fnPoint.x,fnPoint.y);await page.mouse.down();
  try{const fn=await waitKeys([[2,0]],beforeFn);await page.keyboard.down('Semicolon');const up=await waitKeys([[2,0],[2,11]],fn.seq);check('physical-Fn-Up-original-reader',up.fn&&up.up,up);await page.keyboard.up('Semicolon');await waitKeys([[2,0]],up.seq);}finally{await page.mouse.up();}await waitKeys([],beforeFn);
  const final=await eventState();report.final=final;check('same-guest-remains-alive-and-error-free',final.status==='running'&&final.errors.length===0&&!(report.page_errors?.length));
  await page.locator('#stopBtn').click();await page.waitForFunction(()=>cardputerRun.runtime.status==='stopped',{}, {timeout:30000});report.cleanup=await page.evaluate(()=>cardputerRun.runtime.cleanupResult);report.worker_targets=await targets.waitUntilClosed({minimumObserved:6,timeoutMs:30000});
  check('normal-Stop-Worker-zero-before-context-close',report.worker_targets.ok&&await page.locator('iframe').count()===0,report.cleanup);
  check('no-protected-services-used',blocked.length===0,blocked);assert.ok(report.checks.every(c=>c.ok),'Selected guest assertions failed');report.status='PASS';
}catch(error){report.error=String(error.stack||error);console.error(report.error);process.exitCode=1;if(page)try{report.failure_state=await eventState();}catch{}}
finally{report.finished_at=new Date().toISOString();report.blocked=blocked;await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2)+'\n');await writeFile(resolve(out,'requests.json'),JSON.stringify(requests,null,2)+'\n');await targets?.detach();await context?.close();await browser?.close();await new Promise(yes=>server.close(yes));console.log('BROWSER_WINDOW_RELEASED');}
