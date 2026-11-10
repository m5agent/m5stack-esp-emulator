// Runs a pinned merged image through the actual workbench upload and input UI.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {extname, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {capturePublicQemuProvenance} from './public_qemu_artifacts.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';

const repo = fileURLToPath(new URL('../../', import.meta.url));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const mime = {'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript',
  '.json':'application/json','.wasm':'application/wasm','.css':'text/css',
  '.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2'};

export async function runPublicStockGuest({device, board, firmware, testScript, exercise}) {
  const site = process.env.M5_PUBLIC_SITE && resolve(process.env.M5_PUBLIC_SITE);
  const publicUrl = process.env.M5_PUBLIC_URL;
  const firmwarePath = process.env.M5_QEMU_UPLOAD && resolve(process.env.M5_QEMU_UPLOAD);
  assert.ok(Boolean(site) !== Boolean(publicUrl), 'select exactly one local export or deployed site');
  assert.ok(firmwarePath, 'M5_QEMU_UPLOAD must point to the pinned local merged image');
  const timeout = Number(process.env.M5_QEMU_READY_TIMEOUT_MS || 180000);
  assert.ok(Number.isSafeInteger(timeout) && timeout >= 30000 && timeout <= 600000);
  const output = resolve(process.env.M5_PUBLIC_QEMU_OUT || resolve(repo,'.work/public-qemu-stock-' + device));
  assert.ok(output.startsWith(resolve(repo,'.work') + '/'), 'raw guest evidence belongs in ignored .work');
  await mkdir(output,{recursive:false});
  const bytes = await readFile(firmwarePath);
  assert.equal(bytes.length,firmware.bytes);
  assert.equal(digest(bytes),firmware.sha256);
  const modules = process.env.M5_WASM_NODE_MODULES || resolve(repo,'platform/tests/node_modules');
  const {chromium} = await import(pathToFileURL(resolve(modules,'playwright/index.mjs')));
  const report = {status:'FAIL',validation:'virtual-device validation',hardware_validation:'NOT RUN',
    device, board, firmware, errors:[], started_at:new Date().toISOString()};
  let server, browser, page, targets;
  try {
    report.provenance = await capturePublicQemuProvenance({repo,site,publicUrl,testScript});
    const basePath = report.provenance.base_path;
    if (site) {
      const manifest = JSON.parse(await readFile(resolve(site,'public-site-manifest.json')));
      const files = new Set(manifest.assets.map(row=>row.path));
      server = createServer(async (request,response) => {
        try {
          const path = new URL(request.url,'http://localhost').pathname;
          if(!path.startsWith(basePath)) {response.writeHead(404).end();return;}
          const relative = decodeURIComponent(path.slice(basePath.length)) || 'index.html';
          const file = resolve(site,relative);
          if(!files.has(relative) || !file.startsWith(site+'/')) {response.writeHead(404).end();return;}
          const body = await readFile(file);
          response.writeHead(200,{'Content-Type':mime[extname(file)] || 'application/octet-stream'});
          response.end(body);
        } catch {response.writeHead(404).end();}
      });
      await new Promise(done=>server.listen(0,'127.0.0.1',done));
    }
    const origin = publicUrl ? new URL('./',publicUrl).href : `http://127.0.0.1:${server.address().port}${basePath}`;
    assert.equal(new URL(origin).pathname,basePath);
    const hardwareGPU = process.env.M5_WASM_GPU === 'hardware';
    browser = await chromium.launch({headless:true,executablePath:process.env.M5_WASM_CHROME || undefined,
      args:['--enable-webgl','--use-gl=angle',hardwareGPU?'--use-angle=metal':'--use-angle=swiftshader',
        ...(hardwareGPU?['--ignore-gpu-blocklist']:['--enable-unsafe-swiftshader'])]});
    report.browser = browser.version();
    page = await browser.newPage({viewport:{width:1300,height:950}});
    targets = await observeWorkerTargets(browser);
    const serviceCalls = [];
    await page.route(url=>[8787,8830].includes(Number(url.port)) || /\/api\/v1(?:\/|$)/.test(url.pathname),
      async route=>{serviceCalls.push(route.request().method());await route.abort('blockedbyclient');});
    page.on('pageerror',error=>report.errors.push(error.message));
    await page.goto(origin,{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>crossOriginIsolated && typeof SharedArrayBuffer==='function',null,{timeout:45000});
    await page.waitForFunction(()=>document.querySelector('#deviceMount')?.dataset.deviceId==='cores3',null,{timeout:45000});
    await page.evaluate(async ({origin,device})=>{
      const {PublicQemuRuntime}=await import(new URL('platform/web/public-qemu-runtime.js',origin));
      const {ModelDeviceShell}=await import(new URL('platform/web/model-shell.js?v=20261026h',origin));
      const start=PublicQemuRuntime.prototype.start, create=ModelDeviceShell.create;
      PublicQemuRuntime.prototype.start=function(...args) {
        if(args[0].device===device) globalThis.stockGuestRuntime=this;
        return start.apply(this,args);
      };
      ModelDeviceShell.create=async function(...args) {
        const shell=await create.apply(this,args);
        if(args[1].id===device) globalThis.stockGuestShell=shell;
        return shell;
      };
    },{origin,device});
    await page.locator('#deviceLibrary').evaluate(el=>el.open=true);
    await page.locator(`button[data-device-id="${device}"]`).click();
    const canvas = page.locator(`[data-renderer="${device}-three"] .three-device-stage canvas`);
    await canvas.waitFor({timeout:45000});
    await page.locator('.advanced-options > summary').click();
    await page.locator('#runtimeMode').selectOption('browser');
    await page.locator('input[name=firmwareSource][value=local]').check();
    await page.locator('#firmwareFile').setInputFiles(firmwarePath);
    await page.locator('#firmwareSha').fill(firmware.sha256);
    await page.locator('#startBtn').click();
    const readState=()=>page.evaluate(()=>{
      const runtime=globalThis.stockGuestRuntime, banner=document.querySelector('#errorBanner');
      return {status:runtime?.status,serial:runtime?.serial || '',
        ready:runtime?.status==='running' && !!runtime.receipt,
        error:banner && !banner.hidden ? banner.textContent : ''};
    });
    const progress=(waitingFor,state,frame)=>writeFile(resolve(output,'progress.json'),
      JSON.stringify({waitingFor,...state,frame},null,2)+'\n');
    const assertHealthy=state=>{
      assert.ok(!state.error && state.status!=='error',state.error || 'guest runtime failed');
      assert.doesNotMatch(state.serial,/Guru Meditation Error|Interrupt wdt timeout|A fatal error occurred/);
    };
    const bootDeadline=Date.now()+timeout;
    let nextProgress=0;
    for(;;){
      const state=await readState();
      if(Date.now()>=nextProgress){
        await progress('guest startup',state,null);
        nextProgress=Date.now()+10000;
      }
      assertHealthy(state);
      if(state.ready)break;
      assert.ok(Date.now()<bootDeadline,'guest startup timed out');
      await page.waitForTimeout(125);
    }
    const receipt=await page.evaluate(()=>stockGuestRuntime.receipt);
    assert.equal(receipt.deviceId,device);
    assert.equal(receipt.board,board);
    assert.equal(receipt.engine,'qemu-wasm');
    assert.equal(receipt.clockOverride,null);
    assert.equal(receipt.firmwareSha256,firmware.flashSha256);
    report.runtime=receipt;
    const sampleFrame=region=>page.evaluate(async region=>{
      const {lastFrame:frame,sessionId}=stockGuestRuntime;
      const shell=stockGuestShell;
      if(!frame || shell.frameSeq!==frame.sequence
        || shell.display.width!==frame.width || shell.display.height!==frame.height) return null;
      const [x,y,width,height]=region || [0,0,frame.width,frame.height];
      const pixels=new Uint8Array(width*height*2);
      for(let row=0;row<height;row++){
        const at=((y+row)*frame.width+x)*2;
        pixels.set(frame.pixels.subarray(at,at+width*2),row*width*2);
        for(let col=0;col<width;col++){
          const value=frame.pixels[at+col*2]|(frame.pixels[at+col*2+1]<<8);
          const r=value>>11,g=(value>>5)&63,b=value&31;
          const rgb=shell.display.getPixel(x+col,y+row);
          if(rgb[0]!==((r<<3)|(r>>2)) || rgb[1]!==((g<<2)|(g>>4))
            || rgb[2]!==((b<<3)|(b>>2))) return null;
        }
      }
      const hash=await crypto.subtle.digest('SHA-256',pixels);
      const sha256=Array.from(new Uint8Array(hash),x=>x.toString(16).padStart(2,'0')).join('');
      return {sessionId,sha256,width:frame.width,height:frame.height,
        sequence:frame.sequence,source:frame.source,texturePixelsCompared:width*height};
    },region);
    const waitFrame=async (sha256,region=null)=>{
      const limit=Date.now()+timeout;
      let frame, nextFrameProgress=0;
      while(Date.now()<limit) {
        const state=await readState();
        assertHealthy(state);
        frame=await sampleFrame(region);
        if(Date.now()>=nextFrameProgress){
          await progress('frame '+sha256,state,frame);
          nextFrameProgress=Date.now()+10000;
        }
        if(frame?.sha256===sha256)return frame;
        await page.waitForTimeout(125);
      }
      throw new Error(`Expected guest/model frame ${sha256}, last sample ${JSON.stringify(frame)}`);
    };
    await exercise({page,canvas,origin,waitFrame,report,output,timeout});
    const beforeStop = await page.evaluate(()=>stockGuestRuntime.evidence());
    await page.locator('#stopBtn').click();
    await page.waitForFunction(()=>globalThis.stockGuestRuntime?.status==='stopped',null,{timeout:60000});
    const stopped=await page.evaluate(()=>stockGuestRuntime.evidence());
    report.cleanup=stopped.cleanup;
    assert.equal(stopped.session_id,beforeStop.session_id);
    assert.ok(stopped.cleanup?.gracefulExit && stopped.cleanup.exitCode===0
      && stopped.cleanup.workersAtExit===0 && stopped.cleanup.explicitWorkerDisposal
      && stopped.cleanup.disposal?.workersRemaining===0 && stopped.cleanup.iframeRemoved
      && stopped.cleanup.engineOwnership?.engineFinalizationAcknowledged===true
      && stopped.cleanup.engineOwnership.engineNormalTerminations===1
      && stopped.cleanup.engineOwnership.engineFallbackTerminations===0);
    const minimumObserved=stopped.cleanup.workersCreated+1;
    assert.ok(Number.isInteger(minimumObserved)&&minimumObserved>=2);
    const closed=await targets.waitUntilClosed({minimumObserved});
    report.worker_targets={observed:closed.observed.length,live:closed.live.length,
      expected:minimumObserved,source:closed.source,nested_before_iframe:'NOT CAPTURED'};
    if(closed.live.length)report.worker_targets.surviving_scripts=closed.live.slice(0,8).map(target=>({
      script:target.url?.startsWith('blob:')?'blob-worker':target.url?.split(/[?#]/,1)[0].split('/').at(-1)?.slice(0,96)||null,
      attached:target.attached,
    }));
    assert.ok(closed.ok && closed.observed.length===minimumObserved
      && closed.observed.filter(target=>target.url.includes('/public-qemu-engine.js')).length===1);
    assert.deepEqual(report.errors,[]);
    assert.deepEqual(serviceCalls,[]);
    await writeFile(resolve(output,'guest-evidence.json'),JSON.stringify(beforeStop,null,2)+'\n');
    report.status='PASS';
  } catch(error) {
    report.error=error.message;
    if(page) {
      const current=await page.evaluate(()=>globalThis.stockGuestRuntime?.evidence()).catch(()=>null);
      if(current)await writeFile(resolve(output,'failure-guest-evidence.json'),JSON.stringify(current,null,2)+'\n');
      await page.screenshot({path:resolve(output,'failure.png')}).catch(()=>{});
      await page.evaluate(()=>globalThis.stockGuestRuntime?.stop()).catch(()=>{});
    }
    throw error;
  } finally {
    await writeFile(resolve(output,'report.json'),JSON.stringify(report,null,2)+'\n');
    await targets?.detach().catch(()=>{});
    await browser?.close();
    if(server)await new Promise(done=>server.close(done));
  }
}
