// Explicit real guest acceptance. Serves static files only; never starts a
// Device Service, Node QEMU wrapper or native emulator. ROM/base go upstream.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {capturePublicQemuProvenance} from './public_qemu_artifacts.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';
import {isMatchingCanvasObservation,waitForCanvasPixels} from './public_qemu_pixel_observer.mjs';
import {DEMO_FIRMWARE,WALLCLOCK_DEMO_FIRMWARE} from '../web/public-demo-firmware.js';
const {chromium}=createRequire(import.meta.url)('playwright');
const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const site=resolve(process.env.M5_PUBLIC_SITE||resolve(repo,'.work/qemu-public-site-test'));
const out=resolve(process.env.M5_PUBLIC_QEMU_OUT||resolve(repo,'.work/public-qemu-guest'));
const base=process.env.M5_PUBLIC_BASE_PATH||'/showcase/';
const requestedExample=process.env.M5_QEMU_EXAMPLE||'stock-reference';
const hardwareGPU=process.env.M5_WASM_GPU==='hardware';
const chromeExecutable=process.env.M5_WASM_CHROME||process.env.M5_CHROME;
assert.ok(['stock-reference','stock-div8','wallclock-candidate'].includes(requestedExample),'M5_QEMU_EXAMPLE must select a named reference example');
// Keep the existing UI value and legacy runner alias while naming the
// acceptance case after the fixed firmware identity instead of a clock rate.
const example=requestedExample==='stock-div8'?'stock-reference':requestedExample;
const candidate=example==='wallclock-candidate',fixture=candidate?WALLCLOCK_DEMO_FIRMWARE:DEMO_FIRMWARE;
const uiExample=candidate?'wallclock-candidate':'stock-div8';
const expectedProfile=candidate?'cores3-wasm-wallclock-sdk-candidate':'cores3-wasm-stock-wallclock';
const stockSourceSHA256='7672397edc3bff5256015c5d857fa3b4c53cba814bac6a982fb7eeb521cef3cb';
const stockRuntimePatch={path:'patches/qemu-wasm-probe/0027-gpio-bounded-transactions.patch',
  sha256:'43685da86d9b959b2e769cd9cda5785a5c4039b5076f73f3b9d6033d1d161bdf'};
await mkdir(out,{recursive:true});
const requests=[],errors=[],checks=[],workers=[];
let server,browser,context,page,workerTargetObserver;
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.wasm':'application/wasm','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.woff2':'font/woff2'};
const report={kind:'browser-local-qemu-acceptance',started_at:new Date().toISOString(),example,requested_example:requestedExample,ui_example:uiExample,checks,requests,errors};
report.pixel_observer_sha256=createHash('sha256').update(await readFile(new URL('./public_qemu_pixel_observer.mjs',import.meta.url))).digest('hex');
report.pixel_observer_wait_strategy='awaited-evaluate-poll';
function check(name,ok,details){checks.push({name,ok,details});assert.ok(ok,name);console.log(name);}
async function deferIframeRemoval() {
  await page.evaluate(() => {
    const frame=document.querySelector('iframe[src*="public-qemu-instance.html"]'),remove=frame.remove;
    globalThis.qemuDeferredRemoval={frame,remove,requests:0};
    frame.remove=()=>{qemuDeferredRemoval.requests++;};
  });
}
async function closeWorkersBeforeRemovingIframe(name,total) {
  // Nested pthreads must close while the iframe remains. The engine target is
  // checked again after normal iframe DOM removal, where macOS Chrome releases
  // any remaining dedicated-Worker target even after owner finalization.
  const nestedClose=await workerTargetObserver.waitUntilOnly({minimumObserved:total,
    allowedUrlPart:'/public-qemu-engine.js',timeoutMs:30000});
  const held=await page.evaluate(() => ({iframe_present:qemuDeferredRemoval.frame.isConnected,
    removal_requests:qemuDeferredRemoval.requests,iframe_count:document.querySelectorAll('iframe[src*="public-qemu-instance.html"]').length}));
  (report.iframe_removal_controls||=[]).push({...held,removal_deferred_by_harness:true});
  check(`${name}-pthreads-before-iframe-finalization`,nestedClose.ok&&held.iframe_present&&held.removal_requests===1&&held.iframe_count===1,
    {worker_targets:nestedClose,playwright_worker_events:workers});
  await page.evaluate(() => {const held=qemuDeferredRemoval;held.remove.call(held.frame);delete globalThis.qemuDeferredRemoval;});
  const targetClose=await workerTargetObserver.waitUntilClosed({minimumObserved:total});
  (report.worker_target_lifecycles||=[]).push({name,nested_before_removal:nestedClose,all_after_removal:targetClose,playwright_worker_events:workers});
  check(`${name}-all-targets-after-iframe-finalization`,targetClose.ok,targetClose);
}
function exactReceipt(receipt){
  if(receipt.engine!=='qemu-wasm'||receipt.profile!==expectedProfile||receipt.clockDivisor!==1
    ||receipt.firmwareSha256!==fixture.firmwareSHA256)return false;
  // Retain the independently admitted e950 SDK-candidate oracle.
  if(candidate)return receipt.firmwareVariant?.firmwareSHA256===fixture.firmwareSHA256
    &&receipt.firmwareVariant.sourceSHA256===fixture.sourceSHA256
    &&receipt.firmwareVariant.schedulerCandidate===fixture.schedulerCandidate;
  const variant=receipt.firmwareVariant,args=receipt.actualArguments;
  return variant?.firmwareSHA256===fixture.firmwareSHA256
    &&variant.profile===expectedProfile&&variant.clockDivisor===1
    &&variant.sourceSHA256===stockSourceSHA256&&!Object.hasOwn(variant,'sourceKind')
    &&variant.fixture===fixture.fixture&&variant.readyMarker==='\"kind\": \"ready\"'
    &&variant.schedulerCandidate==='qemu-tci-mmio-blocks-v1'
    &&variant.oneInsnPerTb===true&&receipt.oneInsnPerTb===true
    &&variant.requiredRuntimePatch?.path===stockRuntimePatch.path
    &&variant.requiredRuntimePatch?.sha256===stockRuntimePatch.sha256
    &&receipt.requiredRuntimePatch?.path===stockRuntimePatch.path
    &&receipt.requiredRuntimePatch?.sha256===stockRuntimePatch.sha256
    &&Array.isArray(args)&&args.filter(value=>value==='-accel').length===1
    &&args[args.indexOf('-accel')+1]==='tcg,thread=multi,one-insn-per-tb=on'
    &&!args.includes('-icount');
}
function guestEvents(text){return text.split('\n').filter(line=>line.startsWith('CORES3_WASM ')).flatMap(line=>{try{return[JSON.parse(line.slice(12))];}catch{return[];}});}
async function waitGuest(kind,predicate=()=>true,timeout=180000){
  await page.waitForFunction(({kind})=>document.querySelector('#serialOutput').textContent.includes(`"kind": "${kind}"`) || !document.querySelector('#errorBanner').hidden,{kind},{timeout});
  const failure=await page.locator('#errorBanner').textContent();if(failure)throw new Error(failure);
  const until=Date.now()+timeout;
  while(Date.now()<until){const found=guestEvents(await page.locator('#serialOutput').textContent()).find(event=>event.kind===kind&&predicate(event));if(found)return found;await page.waitForTimeout(200);}
  throw new Error(`Guest ${kind} condition timed out`);
}
async function evidence(name){
  const download=page.waitForEvent('download');await page.locator('#browserEvidenceBtn').click();const item=await download;
  const path=resolve(out,name+'.json');await item.saveAs(path);return JSON.parse(await readFile(path,'utf8'));
}
// Real RGB565 frames from the same stock full Flash789612/main767239.
// Before: cold-steady fe4d5e41...; after: stable cold Clicks1 frame2d993066...
// Both labels were visually inspected; immediate callback screenshots were0.
const STOCK_CLICK_PIXELS={
  firmware:'78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f',
  source:'7672397edc3bff5256015c5d857fa3b4c53cba814bac6a982fb7eeb521cef3cb',
  regions:[
    {name:'Clicks label',x:20,y:60,width:180,height:40,zero:'467791f6a283bc099e6f4004b3ff01b9821760194c99e06979092092c15bb23f',one:'7755d8e1afc5dcbff0477707b761f924703fe98a86da1a71aa33345e5f801b94'},
    {name:'Count button text',x:96,y:168,width:128,height:32,zero:'ff20083d11136131f279d5a9255a29eb166917c7f53066ced19cdcfd62b65c8e',one:'54b3f99534946e2e95d8ed92a5913915ae838ee56bef93491838fb517121ee3e'},
  ],
};
let lastStockTap=null;
async function tap(x,y){
  const canvas=page.locator('#rawFrameCanvas');await canvas.waitFor({state:'visible'});await canvas.scrollIntoViewIfNeeded();
  const box=await canvas.boundingBox();assert.ok(box,'Actual raw canvas must be visible');
  const px=box.x+x/320*box.width,py=box.y+y/240*box.height;
  const hit=await page.evaluate(({x,y})=>({id:document.elementFromPoint(x,y)?.id??null,x,y,at_ms:performance.now(),
    frame_sequence:Number(document.querySelector('#deviceMount')?.dataset.frameSequence||0),viewport:{width:innerWidth,height:innerHeight}}),{x:px,y:py});
  check('actual-raw-canvas-input-target-visible',hit.id==='rawFrameCanvas'&&px>=0&&py>=0&&px<hit.viewport.width&&py<hit.viewport.height,hit);
  lastStockTap=hit;
  await page.evaluate(()=>{
    const events=[],record=event=>events.push({type:event.type,isTrusted:event.isTrusted,at_ms:performance.now(),target:event.target?.id??null,x:event.clientX,y:event.clientY});
    window.__m5StockTouchTrace={events,stop:()=>{for(const type of ['pointerdown','pointerup'])window.removeEventListener(type,record,true);}};
    for(const type of ['pointerdown','pointerup'])window.addEventListener(type,record,{capture:true,passive:true});
  });
  try{await page.mouse.move(px,py);await page.mouse.down();await page.waitForTimeout(650);await page.mouse.up();}
  finally{
    lastStockTap.dom_events=await page.evaluate(()=>{const trace=window.__m5StockTouchTrace;trace.stop();delete window.__m5StockTouchTrace;return trace.events;});
  }
  check('actual-trusted-native-pointer-down-up',lastStockTap.dom_events.length===2
    &&lastStockTap.dom_events.every(event=>event.isTrusted&&event.target==='rawFrameCanvas')
    &&lastStockTap.dom_events[0].type==='pointerdown'&&lastStockTap.dom_events[1].type==='pointerup',lastStockTap.dom_events);
  (report.raw_touch_trials||=[]).push({requested_native_xy:{x,y},requested_hold_ms:650,...lastStockTap});
}
async function waitStockClickPixels(name,one){
  assert.equal(fixture.firmwareSHA256,STOCK_CLICK_PIXELS.firmware,'Pixel oracle is bound to the unchanged stock full Flash');
  const regions=STOCK_CLICK_PIXELS.regions.map(row=>({...row,expected:one?row.one:row.zero}));
  if(one)assert.ok(lastStockTap&&Number.isFinite(lastStockTap.callback_observed_ms));
  const boundary={minimumSequence:one?lastStockTap.frame_sequence:-1,notBeforeMs:one?lastStockTap.callback_observed_ms:0};
  const actual=await waitForCanvasPixels(page,{regions,boundary,timeoutMs:15000,pollingMs:100});
  assert.ok(isMatchingCanvasObservation(actual,{regions,boundary}),'Returned canvas observation must pass the full measured predicate');
  check(name+'-actual-clicks-and-count-pixels',isMatchingCanvasObservation(actual,{regions,boundary}),{state:one?1:0,firmware:STOCK_CLICK_PIXELS.firmware,source:STOCK_CLICK_PIXELS.source,boundary,actual});
  (report.stock_visual_samples||=[]).push({name,state:one?1:0,boundary,actual,
    timing_scope:'First matching coherent canvas observed after callback; observation latency is an upper bound, not physical response time.'});
  await page.screenshot({path:resolve(out,name+'-visible.png'),fullPage:true});
}
async function stockSteadyWindow(name){
  const started=performance.now();
  for(let n=0;n<40;n++){
    await page.waitForTimeout(500);
    assert.equal(await page.locator('#runtimeStatus').getAttribute('data-status'),'running');
    assert.equal(await page.locator('#errorBanner').isHidden(),true);
    assert.doesNotMatch(await page.locator('#serialOutput').textContent(),/Guru Meditation Error|wdt timeout|Task watchdog|abort\(\) was called|assert failed:/);
    assert.equal(errors.length,0);
  }
  (report.stock_steady_windows||=[]).push({name,duration_ms:performance.now()-started});
}
async function verifyStockClickReceipts(name){
  assert.ok(lastStockTap);lastStockTap.callback_observed_ms=await page.evaluate(()=>performance.now());
  const state=await evidence(name+'-controller');
  check(name+'-same-fixture-receipt',exactReceipt(state.receipt),state.receipt);
  const receipts=state.inputs.filter(row=>row.type==='touch'&&Math.abs(row.x-160)<=1&&Math.abs(row.y-184)<=1);
  // CSS/native conversion uses floor: the same requested point may be183px.
  check(name+'-controller-down-up',receipts.length===2&&receipts[0].down===true&&receipts[1].down===false,receipts);
  const held=Date.parse(receipts[1].at)-Date.parse(receipts[0].at);
  check(name+'-controller-hold',held>=500&&held<=1200,{actual_hold_ms:held,requested_hold_ms:650,receipts});
  check(name+'-guest-clicks1',guestEvents(state.serial).some(event=>event.kind==='touch_clicked'&&event.clicks===1));
}

try{
  report.provenance=await capturePublicQemuProvenance({repo,site,publicUrl:process.env.M5_PUBLIC_URL});
  let url=process.env.M5_PUBLIC_URL;
  if(!url){
    server=createServer(async(req,res)=>{
      try{
        const path=new URL(req.url,'http://localhost').pathname;
        if(!path.startsWith(base)){res.writeHead(404).end();return;}
        const file=resolve(site,decodeURIComponent(path.slice(base.length))||'index.html');
        if(!file.startsWith(site+'/')){res.writeHead(403).end();return;}
        // Deliberately no COOP/COEP response headers: exercise the Pages SW.
        res.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream','Cache-Control':'no-cache'});
        res.end(await readFile(file));
      }catch{res.writeHead(404).end();}
    });
    await new Promise(done=>server.listen(0,'127.0.0.1',done));url=`http://127.0.0.1:${server.address().port}${base}`;
  }
  report.url=url;report.deployment=process.env.M5_PUBLIC_URL?'remote-static-host':'local-static-project-prefix';
  browser=await chromium.launch({headless:true,...(chromeExecutable?{executablePath:chromeExecutable}:{}),
    args:['--enable-webgl','--use-gl=angle',...(hardwareGPU?['--use-angle=metal','--ignore-gpu-blocklist']:['--use-angle=swiftshader'])]});
  context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  await context.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>route.abort('blockedbyclient'));
  page=await context.newPage();
  workerTargetObserver=await observeWorkerTargets(browser);
  page.on('pageerror',error=>errors.push(String(error)));
  page.on('request',request=>requests.push({url:request.url(),method:request.method()}));
  context.on('page',child=>child.on('pageerror',error=>errors.push(String(error))));
  page.on('worker',worker=>{const row={url:worker.url(),kind:worker.url().includes('/public-qemu-engine.js')?'engine':'nested-pthread',created_at:new Date().toISOString()};workers.push(row);worker.on('close',()=>{row.closed_at=new Date().toISOString();});});
  await page.goto(url,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>crossOriginIsolated&&document.querySelector('#deviceMount')?.dataset.deviceId==='cores3',{},{timeout:45000});
  report.webgl_renderer=await page.evaluate(()=>{
    const gl=document.querySelector('#deviceMount .three-device-stage canvas')?.getContext('webgl2')
      ||document.querySelector('#deviceMount .three-device-stage canvas')?.getContext('webgl');
    const info=gl?.getExtension('WEBGL_debug_renderer_info');
    return gl?(info?gl.getParameter(info.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER)):null;
  });
  if(hardwareGPU)assert.doesNotMatch(report.webgl_renderer||'',/swiftshader|software/i,
    'hardware WebGL was required but the browser selected software rendering');
  check('pages-service-worker-shared-memory',await page.evaluate(()=>crossOriginIsolated&&typeof SharedArrayBuffer==='function'));
  await page.locator('#referenceExample').selectOption(uiExample);
  check('explicit-public-reference-example',await page.locator('#referenceExample').inputValue()===uiExample,{example,ui_example:uiExample});
  await page.locator('#startBtn').click();
  const ready=await waitGuest('ready');check('actual-cores3-lvgl-ready',ready.width===320&&ready.height===240,ready);
  await page.waitForFunction(()=>Number(document.querySelector('#deviceMount').dataset.frameSequence)>0);
  await page.waitForFunction(()=>{
    const canvas=document.querySelector('#rawFrameCanvas');
    if(!canvas.width||!canvas.height)return false;
    const rgba=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
    return new Set(rgba).size>16;
  },{},{timeout:30000});
  await page.locator('#nativeScreenBtn').click();
  const boot=await evidence('running-boot');
  check('c-qemu-runtime-and-exact-fixture',exactReceipt(boot.receipt),boot.receipt);
  check('real-frame-pixels',boot.last_frame.width===320&&boot.last_frame.pixels.length===153600&&new Set(boot.last_frame.pixels).size>8);
  if(!candidate){await stockSteadyWindow('cold-stock');await waitStockClickPixels('cold-before-input',false);}
  await tap(310,235);await page.waitForTimeout(1200);
  check('negative-touch-does-not-click',!guestEvents(await page.locator('#serialOutput').textContent()).some(event=>event.kind==='touch_clicked'));
  await tap(160,184);const click=await waitGuest('touch_clicked',event=>event.clicks===1,15000);check('actual-dom-touch-lvgl-callback',click.clicks===1);
  if(!candidate){await verifyStockClickReceipts('cold-stock');await waitStockClickPixels('cold-clicks1',true);}
  await page.locator('#browserPir').check();await waitGuest('pir',event=>event.value===1,20000);
  check('pir-qom-readback',await page.locator('#browserPirState').textContent()==='QOM: MOTION');
  await page.locator('#browserPir').uncheck();await waitGuest('pir',event=>event.value===0&&event.clicks===1,20000);
  check('pir-guest-both-transitions',true);
  await page.locator('#pauseBtn').click();await page.waitForFunction(()=>document.querySelector('#runtimeStatus').dataset.status==='paused');
  const paused=await page.locator('#serialOutput').textContent();await page.waitForTimeout(1800);
  check('qmp-pause-stops-guest-progress',await page.locator('#serialOutput').textContent()===paused);
  await page.locator('#pauseBtn').click();await page.waitForFunction(()=>document.querySelector('#runtimeStatus').dataset.status==='running');
  check('qmp-resume',true);
  for(const width of [1440,1024,768,390]){
    await page.setViewportSize({width,height:1000});await page.waitForTimeout(250);
    check(`layout-${width}`,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.screenshot({path:resolve(out,`layout-${width}.png`),fullPage:true});
  }
  await page.setViewportSize({width:1440,height:1000});
  await deferIframeRemoval();
  await page.locator('#stopBtn').click();await page.waitForFunction(()=>document.querySelector('#runtimeStatus').dataset.status==='stopped',{},{timeout:30000});
  const stopped=await evidence('stopped-first');
  check('quit-and-container-cleanup',stopped.cleanup.gracefulExit&&stopped.cleanup.exitCode===0&&stopped.cleanup.explicitWorkerDisposal&&stopped.cleanup.iframeRemoved,stopped.cleanup);
  await closeWorkersBeforeRemovingIframe('first-engine-and-five-pthreads-close-before-iframe-removal',6);
  check('no-instance-frame-after-stop',await page.locator('iframe[src*="public-qemu-instance.html"]').count()===0);
  check('dedicated-engine-closing-notification-without-owner-fallback',stopped.cleanup.engineOwnership?.engineCloseNotificationReceived===true
    && stopped.cleanup.disposal?.ownerTerminatesAfterAcknowledgement===false&&stopped.cleanup.disposal.engineSelfClosesAfterAcknowledgement===true
    && stopped.cleanup.engineOwnership?.engineCloseNotifications===1
    && stopped.cleanup.engineOwnership?.engineNormalTerminations===0
    && stopped.cleanup.engineOwnership?.engineFallbackTerminations===0,stopped.cleanup.engineOwnership);
  check('local-history-retains-hash',await page.locator('#browserHistoryText').textContent().then(text=>text.includes(fixture.firmwareSHA256.slice(0,12))));
  const firstId=stopped.session_id;
  const shared=new URL(url);shared.searchParams.set('device','cores3');shared.searchParams.set('mode','browser');
  shared.searchParams.set('sha256',fixture.firmwareSHA256);
  await page.goto(shared.href,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#runtimeStatus').dataset.status==='running',{},{timeout:180000});
  await waitGuest('ready');
  check('shared-reference-restores-example',await page.locator('#referenceExample').inputValue()===uiExample);
  const reopened=await evidence('reopened-running');check('fresh-guest-reopen-from-shared-reference',reopened.session_id!==firstId&&!guestEvents(reopened.serial).some(event=>event.kind==='touch_clicked'));
  check('shared-reference-exact-runtime-variant',exactReceipt(reopened.receipt),reopened.receipt);
  if(!candidate){
    await page.locator('#nativeScreenBtn').click();await stockSteadyWindow('reopened-stock');await waitStockClickPixels('reopened-before-input',false);
    await tap(160,184);const click=await waitGuest('touch_clicked',event=>event.clicks===1,15000);check('reopened-real-touch-clicks1',click.clicks===1);
    await verifyStockClickReceipts('reopened-stock');await waitStockClickPixels('reopened-clicks1',true);
  }
  await deferIframeRemoval();
  await page.locator('#stopBtn').click();await page.waitForFunction(()=>document.querySelector('#runtimeStatus').dataset.status==='stopped',{},{timeout:30000});
  const final=await evidence('stopped-reopened');check('reopen-cleanup',final.cleanup.gracefulExit&&final.cleanup.explicitWorkerDisposal,final.cleanup);
  await closeWorkersBeforeRemovingIframe('both-engines-and-ten-pthreads-close-before-iframe-removal',12);
  check('reopened-engine-notification-without-owner-fallback',final.cleanup.engineOwnership?.engineCloseNotificationReceived===true
    &&final.cleanup.disposal?.ownerTerminatesAfterAcknowledgement===false&&final.cleanup.disposal.engineSelfClosesAfterAcknowledgement===true
    &&final.cleanup.engineOwnership?.engineCloseNotifications===1
    &&final.cleanup.engineOwnership?.engineNormalTerminations===0
    &&final.cleanup.engineOwnership?.engineFallbackTerminations===0,final.cleanup.engineOwnership);
  check('no-service-or-local-emulator-requests',!requests.some(row=>/\/api\/v1|:8787\b|:8830\b/.test(row.url)));
  check('no-javascript-errors',errors.length===0,errors);
  report.result='PASS';report.final_receipt=final.receipt;report.workers=workers;
}catch(error){report.result='FAIL';report.failure=String(error.stack||error);console.error(error);if(page){await page.screenshot({path:resolve(out,'failure.png'),fullPage:true}).catch(()=>{});await writeFile(resolve(out,'failure-serial.txt'),await page.locator('#serialOutput').textContent().catch(()=>''));if(await page.locator('#browserEvidenceBtn').isVisible().catch(()=>false))await evidence('failure-evidence').catch(()=>{});}process.exitCode=1;}
finally{
  if(report.result==='FAIL'&&page){
    await page.locator('#stopBtn').click({timeout:2000}).catch(()=>{});
    await page.waitForFunction(()=>document.querySelector('#runtimeStatus')?.dataset.status==='stopped',{}, {timeout:30000}).catch(()=>{});
    await page.evaluate(()=>{const held=globalThis.qemuDeferredRemoval;if(held){held.remove.call(held.frame);delete globalThis.qemuDeferredRemoval;}}).catch(()=>{});
    if(workerTargetObserver)report.failure_worker_targets=await workerTargetObserver.waitUntilClosed({minimumObserved:workers.length,timeoutMs:30000}).catch(error=>({ok:false,error:String(error.message)}));
    else report.failure_worker_targets={ok:false,status:'NOT CAPTURED',error:'Worker observer was not initialized; original failure retained'};
  }
  await context?.close();await browser?.close();if(server)await new Promise(done=>server.close(done));
  report.workers=workers;report.finished_at=new Date().toISOString();await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2));
}
