// Explicit candidate guest acceptance through the real browser QEMU runtime.
// The dedicated static harness never starts a native service or QEMU process.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, extname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {capturePublicQemuProvenance} from './public_qemu_artifacts.mjs';

const {chromium} = createRequire(import.meta.url)('playwright');
const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const site = resolve(process.env.M5_PUBLIC_SITE || resolve(repo, '.work/qemu-fast-site'));
const fixture = resolve(process.env.M5_WALLCLOCK_FIXTURE || resolve(repo, '.work/lvgl-wallclock-fixture'));
const out = resolve(process.env.M5_PUBLIC_QEMU_OUT || resolve(repo, '.work/lvgl-wallclock-browser'));
const base = '/showcase/';
const sha = data => createHash('sha256').update(data).digest('hex');
const contract = JSON.parse(await readFile(resolve(repo, 'tests/browser-qemu/cores3_lvgl_wallclock/contract.json')));
const composition = JSON.parse(await readFile(resolve(fixture, 'composition.json')));
const firmware = await readFile(resolve(fixture, 'candidate.bin'));
assert.equal(sha(firmware), composition.firmware_sha256);
assert.equal(composition.source_sha256, contract.identity.source_sha256);
assert.equal(composition.base_sha256, contract.identity.normalized_base.sha256);
assert.equal(composition.fixture, contract.fixture);
assert.equal(composition.preservation.source_readback_verified, true);
await mkdir(out, {recursive:true});

const report = {kind:'browser-qemu-lvgl-wallclock-candidate', status:'FAIL',
  scope:'Dedicated browser scheduler/frame/input lane; additional controller properties from the full fixture oracle remain separate.',
  fixture:contract.fixture, scheduler_candidate:composition.scheduler_candidate,
  composition, started_at:new Date().toISOString(), checks:[], requests:[], errors:[], workers:[],
  hardware_validation:'NOT RUN', c_timer_coalescing:'NOT IMPLEMENTED',
  qom_input_level_and_event_count:'NOT OBSERVABLE through the current browser bridge'};
let server, browser, context, page;
function check(name, ok, details) {
  report.checks.push({name, ok, details});
  assert.ok(ok, name); console.log(name);
}
async function snapshot(name) {
  const evidence = await page.evaluate(() => h.runtime.evidence());
  await writeFile(resolve(out, name + '.json'), JSON.stringify(evidence));
  return evidence;
}
async function waitEvent(kind, fields={}, timeout=90000) {
  await page.waitForFunction(({kind, fields}) => h.events.some(row => row.event.kind === kind
    && Object.entries(fields).every(([key, value]) => row.event[key] === value)) || h.errors.length,
  {kind, fields}, {timeout});
  const state = await page.evaluate(() => ({events:h.events, errors:h.errors}));
  assert.deepEqual(state.errors, []);
  return state.events.find(row => row.event.kind === kind
    && Object.entries(fields).every(([key, value]) => row.event[key] === value));
}
async function tap(x, y) {
  const box = await page.locator('canvas').boundingBox();
  await page.mouse.move(box.x + x / 320 * box.width, box.y + y / 240 * box.height);
  await page.mouse.down(); await page.waitForTimeout(750); await page.mouse.up();
  await page.evaluate(() => h.inputPending);
}
try {
  report.provenance = await capturePublicQemuProvenance({repo, site,
    webPaths:['platform/web/public-config.js','platform/web/public-firmware.js','platform/web/sha256.js',
      'platform/web/public-qemu-runtime.js','platform/web/public-qemu-instance.js',
      'platform/web/public-qemu-instance.html','platform/web/public-qemu-profiles.js','platform/web/public-qemu-frame.js'],
    testScript:'platform/tests/test_public_qemu_wallclock_guest.mjs'});
  const exportedRegistry = await readFile(resolve(site,'platform/web/qemu-browser-profiles.json'));
  const siteManifest = JSON.parse(await readFile(resolve(site,'public-site-manifest.json')));
  const declaredRegistry = siteManifest.assets.find(row=>row.path==='platform/web/qemu-browser-profiles.json');
  assert.equal(sha(exportedRegistry),declaredRegistry?.sha256);
  report.provenance.profile_registry_sha256 = sha(exportedRegistry);
  const mime = {'.html':'text/html', '.js':'text/javascript', '.mjs':'text/javascript',
    '.json':'application/json', '.wasm':'application/wasm', '.css':'text/css'};
  server = createServer(async (request, response) => {
    const headers = {'Cross-Origin-Opener-Policy':'same-origin',
      'Cross-Origin-Embedder-Policy':'require-corp', 'Cache-Control':'no-store'};
    try {
      const path = new URL(request.url, 'http://localhost').pathname;
      if (path === base + '__fixture.bin') {
        response.writeHead(200, {...headers, 'Content-Type':'application/octet-stream'}).end(firmware); return;
      }
      if (path === base + '__harness.html') {
        response.writeHead(200, {...headers, 'Content-Type':'text/html'}).end(`<!doctype html><meta charset="utf-8">
          <title>Explicit LVGL wallclock candidate</title><style>body{font:16px sans-serif;background:#eee}
          canvas{width:640px;height:480px;touch-action:none;image-rendering:pixelated}pre{white-space:pre-wrap}</style>
          <h1>CoreS3 · explicit LVGL candidate · divisor 1</h1><canvas width="320" height="240"></canvas>
          <p><label><input id="pir" type="checkbox"> PIR motion</label> <span id="status">stopped</span></p><pre id="serial"></pre>`); return;
      }
      if (!path.startsWith(base)) { response.writeHead(404, headers).end(); return; }
      const file = resolve(site, decodeURIComponent(path.slice(base.length)));
      if (!file.startsWith(site + '/')) { response.writeHead(403, headers).end(); return; }
      response.writeHead(200, {...headers, 'Content-Type':mime[extname(file)] || 'application/octet-stream'});
      response.end(await readFile(file));
    } catch { response.writeHead(404, headers).end(); }
  });
  await new Promise(done => server.listen(0, '127.0.0.1', done));
  const root = `http://127.0.0.1:${server.address().port}${base}`;
  report.url = root + '__harness.html';
  browser = await chromium.launch({headless:true,
    ...(process.env.M5_CHROME ? {executablePath:process.env.M5_CHROME} : {})});
  context = await browser.newContext({viewport:{width:1000,height:1000}});
  page = await context.newPage();
  page.on('pageerror', error => report.errors.push(String(error)));
  page.on('request', request => report.requests.push({method:request.method(),url:request.url()}));
  page.on('worker', worker => {
    const record = {url:worker.url(), created_at:new Date().toISOString()}; report.workers.push(record);
    worker.on('close', () => { record.closed_at = new Date().toISOString(); });
  });
  await page.goto(report.url);
  check('dedicated-static-harness-shared-memory', await page.evaluate(() => crossOriginIsolated));
  await page.evaluate(async ({root, fixtureId}) => {
    const {PublicQemuRuntime} = await import(root + 'platform/web/public-qemu-runtime.js');
    const registry = await (await fetch(root + 'platform/web/qemu-browser-profiles.json')).json();
    const canvas = document.querySelector('canvas'), ctx = canvas.getContext('2d');
    const h = globalThis.h = {events:[], frames:[], errors:[], carry:'', inputPending:Promise.resolve()};
    function digest(bytes) { let n=2166136261; for (const byte of bytes) { n ^= byte; n=Math.imul(n,16777619); } return (n>>>0).toString(16); }
    h.region = region => digest(ctx.getImageData(...region).data);
    h.roi = () => h.region([20,128,280,24]);
    h.runtime = new PublicQemuRuntime({root, profiles:registry, allowCandidateProfiles:true,
      onError:error => h.errors.push(String(error)),
      onState:state => { document.querySelector('#status').textContent = state.status; },
      onSerial:text => {
        document.querySelector('#serial').textContent += text; h.carry += text;
        let index;
        while ((index=h.carry.indexOf('\n'))>=0) {
          const line=h.carry.slice(0,index).trim(); h.carry=h.carry.slice(index+1);
          if (line.startsWith('CORES3_WASM ')) try {
            const event=JSON.parse(line.slice(12));
            if (event.fixture!==fixtureId) h.errors.push('unexpected guest fixture');
            h.events.push({at_ms:performance.now(),event});
          } catch (error) { h.errors.push('invalid guest JSON: '+error); }
        }
      },
      onFrame:frame => {
        canvas.width=frame.width; canvas.height=frame.height;
        const image=ctx.createImageData(frame.width,frame.height);
        for (let i=0,p=0;i<frame.pixels.length;i+=2,p+=4) {
          const value=frame.pixels[i]|(frame.pixels[i+1]<<8);
          image.data[p]=((value>>11)&31)*255/31; image.data[p+1]=((value>>5)&63)*255/63;
          image.data[p+2]=(value&31)*255/31; image.data[p+3]=255;
        }
        ctx.putImageData(image,0,0);
        h.frames.push({at_ms:performance.now(),source:frame.source,source_sequence:frame.sourceSequence,
          width:frame.width,height:frame.height,animation_roi:h.roi()});
      }});
    const input = event => { h.inputPending=h.inputPending.then(()=>h.runtime.input(event)).catch(error=>h.errors.push(String(error))); };
    for (const type of ['pointerdown','pointerup']) canvas.addEventListener(type,event=>{
      if (type==='pointerdown') canvas.setPointerCapture(event.pointerId);
      const box=canvas.getBoundingClientRect();
      input({type:'touch',x:Math.min(319,Math.max(0,Math.floor((event.clientX-box.x)*320/box.width))),
        y:Math.min(239,Math.max(0,Math.floor((event.clientY-box.y)*240/box.height))),down:type==='pointerdown'});
    });
    document.querySelector('#pir').addEventListener('change',event=>input({type:'pir',motion:event.target.checked}));
    const firmware=new Uint8Array(await (await fetch(root+'__fixture.bin')).arrayBuffer());
    h.started_ms=performance.now();
    await h.runtime.start({device:'cores3',firmware,clockDivisor:1});
  }, {root, fixtureId:contract.fixture});
  const ready = await waitEvent('ready');
  check('same-guest-original-m5ui-drivers-ready', ready.event.width===320 && ready.event.height===240, ready);
  check('actual-guest-boot-markers',await page.evaluate(kinds=>h.events.slice(0,4).map(row=>row.event.kind).join()===kinds.join(),contract.oracle.ready_kinds));
  const lvReady = await waitEvent('lvgl_ready');
  check('explicit-scheduler-candidate', lvReady.event.scheduler_candidate===composition.scheduler_candidate, lvReady);
  await waitEvent('pir', {value:0});
  await waitEvent('heartbeat');
  const boot = await snapshot('running-boot');
  check('normal-clock-exact-runtime-firmware', boot.receipt.engine==='qemu-wasm'
    && boot.receipt.clockDivisor===1 && boot.receipt.profile==='cores3-wasm-wallclock-candidate'
    && boot.receipt.firmwareSha256===composition.firmware_sha256, boot.receipt);
  check('actual-framebuffer-pixels', boot.last_frame?.width===320 && boot.last_frame?.height===240
    && boot.last_frame.pixels.length===153600 && new Set(boot.last_frame.pixels).size>8);
  const pixelAudit=await page.evaluate(()=>{
    const ctx=document.querySelector('canvas').getContext('2d');
    const sample=(x,y)=>[...ctx.getImageData(x,y,1,1).data].slice(0,3);
    const title=ctx.getImageData(20,18,260,30).data;let white=0;
    for(let index=0;index<title.length;index+=4)if(title[index]>220&&title[index+1]>220&&title[index+2]>220)white++;
    return {background:sample(300,120),button:sample(50,184),title_white_pixels:white};
  });
  check('expected-background-button-and-title-glyphs',pixelAudit.background.every((value,index)=>Math.abs(value-[16,32,48][index])<=8)
    &&pixelAudit.button.every((value,index)=>Math.abs(value-[33,118,255][index])<=8)
    &&pixelAudit.title_white_pixels>=101&&pixelAudit.title_white_pixels<=4999,pixelAudit);
  const clearPirRegion=await page.evaluate(()=>h.region([20,100,220,28]));
  await page.locator('canvas').screenshot({path:resolve(out,'frame-ready.png')});
  const negativeSequence=await page.evaluate(()=>h.events.at(-1).event.seq);
  await tap(310,235);
  await page.waitForFunction(seq=>h.events.some(row=>row.event.kind==='heartbeat'&&row.event.seq>seq),negativeSequence,{timeout:15000});
  check('background-touch-does-not-click', await page.evaluate(()=>!h.events.some(row=>row.event.kind==='touch_clicked')));
  for (const clicks of [1,2]) {
    const before=await page.evaluate(()=>({count:h.region([20,60,210,30]),button:h.region([90,164,150,40])}));
    await tap(160,184); await waitEvent('touch_clicked',{clicks},20000);
    await page.waitForFunction(before=>h.region([20,60,210,30])!==before.count
      &&h.region([90,164,150,40])!==before.button,before,{timeout:10000});
    check(`click-${clicks}-updates-real-count-and-button-frame`,true);
  }
  const touchKinds=await page.evaluate(()=>h.events.filter(row=>row.event.kind.startsWith('touch_')).map(row=>row.event.kind));
  check('two-real-dom-touch-clicks',touchKinds.join()===['touch_pressed','touch_released','touch_clicked','touch_pressed','touch_released','touch_clicked'].join(),touchKinds);
  await page.locator('#pir').check(); await page.evaluate(()=>h.inputPending); await waitEvent('pir',{value:1,clicks:2},20000);
  await page.waitForFunction(before=>h.region([20,100,220,28])!==before,clearPirRegion,{timeout:10000});
  await page.locator('canvas').screenshot({path:resolve(out,'frame-pir-motion.png')});
  await page.locator('#pir').uncheck(); await page.evaluate(()=>h.inputPending); await waitEvent('pir',{value:0,clicks:2},20000);
  await page.waitForFunction(before=>h.region([20,100,220,28])===before,clearPirRegion,{timeout:10000});
  check('pir-motion-frame-changes-and-clear-frame-restores',true);
  check('pir-controller-input-and-guest-clear-motion-clear', true);
  const steadyStart = await page.evaluate(()=>performance.now());
  await page.waitForTimeout(Number(process.env.M5_WALLCLOCK_OBSERVE_MS || 20000));
  const observed = await page.evaluate(start=>({events:h.events.filter(row=>row.at_ms>=start),
    frames:h.frames.filter(row=>row.at_ms>=start), errors:h.errors, inputs:h.runtime.inputs}),steadyStart);
  const heartbeats=observed.events.filter(row=>row.event.kind==='heartbeat');
  check('continued-heartbeat-progress',heartbeats.length>=5,{samples:heartbeats.length});
  const first=heartbeats[0], last=heartbeats.at(-1), hostDelta=last.at_ms-first.at_ms;
  report.clocks={host_delta_ms:hostDelta,guest_delta_ms:last.event.elapsed_ms-first.event.elapsed_ms,
    lvgl_delta_ms:last.event.tick_total-first.event.tick_total, samples:heartbeats,
    max_abs_elapsed_tick_difference_ms:Math.max(...heartbeats.map(row=>Math.abs(row.event.elapsed_ms-row.event.tick_total)))};
  report.clocks.guest_to_host_rate=report.clocks.guest_delta_ms/hostDelta;
  report.clocks.lvgl_to_host_rate=report.clocks.lvgl_delta_ms/hostDelta;
  check('normal-clock-rate-measured',report.clocks.guest_to_host_rate>.75 && report.clocks.guest_to_host_rate<1.25,report.clocks);
  check('elapsed-lvgl-ticks-preserved',report.clocks.max_abs_elapsed_tick_difference_ms<=2000,report.clocks);
  check('scheduler-continues-without-errors',heartbeats.every(row=>row.event.scheduler_errors===0 && row.event.scheduled===0)
    && last.event.task_runs>first.event.task_runs && last.event.timer_callbacks>first.event.timer_callbacks,heartbeats);
  check('real-lvgl-animation-advances',last.event.animation_samples>first.event.animation_samples
    && new Set(observed.frames.map(row=>row.animation_roi)).size>=2,{frames:observed.frames.length,distinct_roi:new Set(observed.frames.map(row=>row.animation_roi)).size});
  const motionInputs=observed.inputs.filter(row=>row.type==='pir');
  check('qom-motion-readback',motionInputs.length===2 && motionInputs[0].result.motion===true
    && motionInputs[1].result.motion===false,motionInputs);
  await page.locator('canvas').screenshot({path:resolve(out,'frame-final.png')});
  await page.evaluate(()=>h.runtime.pause()); await page.waitForTimeout(300);
  const paused=await page.evaluate(()=>({serial:h.runtime.serial,events:h.events.length}));
  await page.waitForTimeout(1700);
  check('pause-stops-guest',await page.evaluate(before=>h.runtime.serial===before.serial&&h.events.length===before.events,paused));
  const lastSequence=await page.evaluate(()=>h.events.at(-1).event.seq);
  await page.evaluate(()=>h.runtime.resume());
  await page.waitForFunction(seq=>h.events.some(row=>row.event.kind==='heartbeat'
    &&row.event.seq>seq&&row.event.clicks===2&&row.event.pir===0),lastSequence,{timeout:20000});
  const serialState=await page.evaluate(()=>({events:h.events,serial:h.runtime.serial}));
  check('single-guest-sequence-and-no-scheduler-errors',serialState.events.filter(row=>row.event.kind==='begin').length===1
    &&serialState.events.every((row,index)=>index===0||row.event.seq>serialState.events[index-1].event.seq)
    &&!/schedule queue full|CORES3_WALLCLOCK_SCHEDULER_ERROR|Guru Meditation|Traceback/.test(serialState.serial));
  report.running_evidence = 'running-final.json'; await snapshot('running-final');
  await page.evaluate(()=>h.runtime.stop());
  const final=await snapshot('stopped-final'); report.final_receipt=final.receipt; report.cleanup=final.cleanup;
  check('qemu-exit-worker-disposal-and-history',final.cleanup.gracefulExit&&final.cleanup.exitCode===0
    &&final.cleanup.explicitWorkerDisposal&&final.cleanup.iframeRemoved,final.cleanup);
  check('history-retains-source-session',await page.evaluate(sha=>JSON.stringify(localStorage).includes(sha),composition.firmware_sha256));
  check('no-native-service-requests',!report.requests.some(row=>/\/api\/v1|:8787\b|:8830\b/.test(row.url)));
  check('no-browser-errors',report.errors.length===0&&observed.errors.length===0,report.errors);
  report.status='PASS';
} catch (error) {
  report.failure=String(error.stack||error); console.error(error); process.exitCode=1;
  if(page) {
    await page.screenshot({path:resolve(out,'failure.png'),fullPage:true}).catch(()=>{});
    await snapshot('failure-evidence').catch(()=>{});
    await writeFile(resolve(out,'failure-state.json'),JSON.stringify(await page.evaluate(()=>({events:h?.events,frames:h?.frames,errors:h?.errors})).catch(()=>null)));
  }
} finally {
  if(page) await page.evaluate(()=>h?.runtime?.stop()).catch(()=>{});
  await context?.close(); await browser?.close();
  if(server) await new Promise(done=>server.close(done));
  report.finished_at=new Date().toISOString();
  await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2));
}
