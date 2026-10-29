// Explicit real guest acceptance. Serves static files only; never starts a
// Device Service, Node QEMU wrapper or native emulator. ROM/base go upstream.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {capturePublicQemuProvenance} from './public_qemu_artifacts.mjs';
import {DEMO_FIRMWARE,WALLCLOCK_DEMO_FIRMWARE} from '../web/public-demo-firmware.js';
const {chromium}=createRequire(import.meta.url)('playwright');
const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const site=resolve(process.env.M5_PUBLIC_SITE||resolve(repo,'.work/qemu-public-site-test'));
const out=resolve(process.env.M5_PUBLIC_QEMU_OUT||resolve(repo,'.work/public-qemu-guest'));
const base=process.env.M5_PUBLIC_BASE_PATH||'/showcase/';
const example=process.env.M5_QEMU_EXAMPLE||'stock-div8';
const hardwareGPU=process.env.M5_WASM_GPU==='hardware';
assert.ok(['stock-div8','wallclock-candidate'].includes(example),'M5_QEMU_EXAMPLE must select a named reference example');
const candidate=example==='wallclock-candidate',fixture=candidate?WALLCLOCK_DEMO_FIRMWARE:DEMO_FIRMWARE;
const expectedProfile=candidate?'cores3-wasm-wallclock-sdk-candidate':'cores3-wasm-vm-div8';
await mkdir(out,{recursive:true});
const requests=[],errors=[],checks=[],workers=[];
let server,browser,context,page;
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.wasm':'application/wasm','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.woff2':'font/woff2'};
const report={kind:'browser-local-qemu-acceptance',started_at:new Date().toISOString(),example,checks,requests,errors};
function check(name,ok,details){checks.push({name,ok,details});assert.ok(ok,name);console.log(name);}
async function deferIframeRemoval() {
  await page.evaluate(() => {
    const frame=document.querySelector('iframe[src*="public-qemu-instance.html"]'),remove=frame.remove;
    globalThis.qemuDeferredRemoval={frame,remove,requests:0};
    frame.remove=()=>{qemuDeferredRemoval.requests++;};
  });
}
async function closeWorkersBeforeRemovingIframe(name,total) {
  // Playwright can deliver the engine Worker close event just after the
  // functional checks finish on shared macOS runners. Keep observing the real
  // event and leave the iframe alive until it arrives.
  const deadline=Date.now()+30000;
  while(workers.some(row=>!row.closed_at)&&Date.now()<deadline)await page.waitForTimeout(100);
  const held=await page.evaluate(() => ({iframe_present:qemuDeferredRemoval.frame.isConnected,
    removal_requests:qemuDeferredRemoval.requests,iframe_count:document.querySelectorAll('iframe[src*="public-qemu-instance.html"]').length}));
  (report.iframe_removal_controls||=[]).push({...held,removal_deferred_by_harness:true});
  check(name,workers.length===total&&workers.filter(row=>row.kind==='engine').length===total/6
    &&workers.every(row=>row.closed_at)&&held.iframe_present&&held.removal_requests===1&&held.iframe_count===1);
  await page.evaluate(() => {const held=qemuDeferredRemoval;held.remove.call(held.frame);delete globalThis.qemuDeferredRemoval;});
}
function exactReceipt(receipt){
  return receipt.engine==='qemu-wasm'&&receipt.profile===expectedProfile&&receipt.clockDivisor===(candidate?1:8)
    &&receipt.firmwareSha256===fixture.firmwareSHA256&&(candidate
      ?receipt.firmwareVariant?.firmwareSHA256===fixture.firmwareSHA256&&receipt.firmwareVariant.sourceSHA256===fixture.sourceSHA256&&receipt.firmwareVariant.schedulerCandidate===fixture.schedulerCandidate
      :!receipt.firmwareVariant);
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
async function tap(x,y){const box=await page.locator('#rawFrameCanvas').boundingBox();await page.mouse.move(box.x+x/320*box.width,box.y+y/240*box.height);await page.mouse.down();await page.waitForTimeout(650);await page.mouse.up();}
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
  browser=await chromium.launch({headless:true,...(process.env.M5_CHROME?{executablePath:process.env.M5_CHROME}:{}),
    args:['--enable-webgl','--use-gl=angle',...(hardwareGPU?['--use-angle=metal','--ignore-gpu-blocklist']:['--use-angle=swiftshader'])]});
  context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  await context.route(url=>[8787,8830].includes(Number(url.port))||/\/api\/v1(?:\/|$)/.test(url.pathname),route=>route.abort('blockedbyclient'));
  page=await context.newPage();
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
  await page.locator('#referenceExample').selectOption(example);
  check('explicit-public-reference-example',await page.locator('#referenceExample').inputValue()===example,example);
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
  await tap(310,235);await page.waitForTimeout(1200);
  check('negative-touch-does-not-click',!guestEvents(await page.locator('#serialOutput').textContent()).some(event=>event.kind==='touch_clicked'));
  await tap(160,184);const click=await waitGuest('touch_clicked',event=>event.clicks===1,15000);check('actual-dom-touch-lvgl-callback',click.clicks===1);
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
    && stopped.cleanup.engineOwnership?.engineFallbackTerminations===0,stopped.cleanup.engineOwnership);
  check('local-history-retains-hash',await page.locator('#browserHistoryText').textContent().then(text=>text.includes(fixture.firmwareSHA256.slice(0,12))));
  const firstId=stopped.session_id;
  const shared=new URL(url);shared.searchParams.set('device','cores3');shared.searchParams.set('mode','browser');
  shared.searchParams.set('sha256',fixture.firmwareSHA256);
  await page.goto(shared.href,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#runtimeStatus').dataset.status==='running',{},{timeout:180000});
  await waitGuest('ready');
  check('shared-reference-restores-example',await page.locator('#referenceExample').inputValue()===example);
  const reopened=await evidence('reopened-running');check('fresh-guest-reopen-from-shared-reference',reopened.session_id!==firstId&&!guestEvents(reopened.serial).some(event=>event.kind==='touch_clicked'));
  check('shared-reference-exact-runtime-variant',exactReceipt(reopened.receipt),reopened.receipt);
  await deferIframeRemoval();
  await page.locator('#stopBtn').click();await page.waitForFunction(()=>document.querySelector('#runtimeStatus').dataset.status==='stopped',{},{timeout:30000});
  const final=await evidence('stopped-reopened');check('reopen-cleanup',final.cleanup.gracefulExit&&final.cleanup.explicitWorkerDisposal,final.cleanup);
  await closeWorkersBeforeRemovingIframe('both-engines-and-ten-pthreads-close-before-iframe-removal',12);
  check('reopened-engine-notification-without-owner-fallback',final.cleanup.engineOwnership?.engineCloseNotificationReceived===true
    &&final.cleanup.engineOwnership?.engineFallbackTerminations===0,final.cleanup.engineOwnership);
  check('no-service-or-local-emulator-requests',!requests.some(row=>/\/api\/v1|:8787\b|:8830\b/.test(row.url)));
  check('no-javascript-errors',errors.length===0,errors);
  report.result='PASS';report.final_receipt=final.receipt;report.workers=workers;
}catch(error){report.result='FAIL';report.failure=String(error.stack||error);console.error(error);if(page){await page.screenshot({path:resolve(out,'failure.png'),fullPage:true}).catch(()=>{});await writeFile(resolve(out,'failure-serial.txt'),await page.locator('#serialOutput').textContent().catch(()=>''));if(await page.locator('#browserEvidenceBtn').isVisible().catch(()=>false))await evidence('failure-evidence').catch(()=>{});}process.exitCode=1;}
finally{
  await context?.close();await browser?.close();if(server)await new Promise(done=>server.close(done));
  report.workers=workers;report.finished_at=new Date().toISOString();await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2));
}
