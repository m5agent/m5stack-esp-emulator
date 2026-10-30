// Opt-in real per-board browser guest. Static hosting only; no Device Service.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname, extname, basename} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {capturePublicQemuProvenance} from './public_qemu_artifacts.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const site = process.env.M5_PUBLIC_SITE && resolve(process.env.M5_PUBLIC_SITE);
if (!site) { console.log('SKIP: explicit M5_PUBLIC_SITE candidate export required'); process.exit(0); }
const device = process.env.M5_QEMU_DEVICE || 'atoms3r', basePath = process.env.M5_PUBLIC_BASE_PATH || '/showcase/';
const uploadPath = process.env.M5_QEMU_UPLOAD && resolve(process.env.M5_QEMU_UPLOAD);
const clockDivisor = process.env.M5_QEMU_CLOCK_DIVISOR ? Number(process.env.M5_QEMU_CLOCK_DIVISOR) : undefined;
const diagnostic = process.env.M5_QEMU_FRAME_DIAGNOSTIC === '1';
const publicUI = process.env.M5_PUBLIC_UI === '1';
const hardwareGPU = process.env.M5_WASM_GPU === 'hardware';
const readyTimeout = Number(process.env.M5_QEMU_READY_TIMEOUT_MS || 180000);
assert.ok(Number.isInteger(readyTimeout) && readyTimeout >= 30000 && readyTimeout <= 600000,
  'M5_QEMU_READY_TIMEOUT_MS must be an integer from 30000 to 600000');
assert.ok(!publicUI || clockDivisor === undefined, 'public UI validation uses the exported default clock');
assert.ok(clockDivisor === undefined || [1, 8].includes(clockDivisor), 'candidate clock override must be explicit 1 or 8');
const output = resolve(process.env.M5_PUBLIC_QEMU_OUT || resolve(repo, '.work/public-qemu-board-' + device));
assert.ok(output.startsWith(resolve(repo, '.work') + '/'), 'raw guest evidence belongs in ignored .work');
await mkdir(output, {recursive:false});
const modules = process.env.M5_WASM_NODE_MODULES || resolve(repo, 'platform/tests/node_modules');
const {chromium} = await import(pathToFileURL(resolve(modules, 'playwright/index.mjs')));
const checks = [], errors = [], requests = [], workerObservations = [];
const report = {kind:'browser-local-qemu-board-acceptance', device, public_ui:publicUI, started_at:new Date().toISOString(), checks, errors, requests};
const epdOraclePath='platform/tests/fixtures/browser_epd_quality_oracles.json';
const epdOracleBytes=['papercolor','papermono'].includes(device)?await readFile(resolve(repo,epdOraclePath)):null;
const epdOracle=epdOracleBytes?JSON.parse(epdOracleBytes).devices[device]:null;
if(epdOracle)report.epd_oracle={path:epdOraclePath,sha256:createHash('sha256').update(epdOracleBytes).digest('hex'),
  generator_sha256:createHash('sha256').update(await readFile(resolve(repo,'tests/browser-qemu/board_display/epd_oracle.py'))).digest('hex'),
  evidence_level:'source-derived expectation; actual frame comparison required'};
const mime = {'.html':'text/html', '.js':'text/javascript', '.mjs':'text/javascript', '.json':'application/json', '.wasm':'application/wasm', '.css':'text/css', '.svg':'image/svg+xml', '.png':'image/png', '.webp':'image/webp', '.woff2':'font/woff2'};
let server, browser, page, workerTargets;
function check(name, ok, details) { checks.push({name, ok, details}); assert.ok(ok, name); console.log(name); }
async function guest(kind, predicate = () => true, timeout = 180000) {
  const until = Date.now() + timeout; let nextProgress = 0;
  while (Date.now() < until) {
    const state = await page.evaluate(() => {
      const banner = document.querySelector('#errorBanner');
      return {serial:globalThis.boardRun?.serial || '', errors:[...(globalThis.boardRun?.errors || []),
        ...(banner && !banner.hidden && banner.textContent ? [banner.textContent] : [])]};
    });
    if(Date.now()>=nextProgress){await writeFile(resolve(output,'guest-progress.json'),JSON.stringify({waiting_for:kind,...state},null,2)+'\n');nextProgress=Date.now()+10000;}
    if (state.errors.length) throw new Error(state.errors.join('\n'));
    if (state.serial.includes('Traceback (most recent call last):')) throw new Error(`Guest Python traceback before ${kind}`);
    if (/Guru Meditation Error|Interrupt wdt timeout|A fatal error occurred/.test(state.serial)) throw new Error(`Guest panic before ${kind}`);
    const events = state.serial.split('\n').filter(line => line.startsWith('M5_BROWSER_PROBE ')).flatMap(line => {try {return [JSON.parse(line.slice(17))];} catch {return [];}});
    const event = events.find(row => row.kind === kind && predicate(row)); if (event) return event;
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error(`Guest ${kind} timed out`);
}
try {
  report.provenance = await capturePublicQemuProvenance({repo, site, testScript:'platform/tests/test_public_qemu_board_guest.mjs'});
  if(epdOracle){
    const runtime=JSON.parse(await readFile(resolve(site,'platform/runtime/qemu/runtime.json')));
    const expected=JSON.parse(epdOracleBytes).qemuController;
    assert.equal(runtime.source.patched_files_sha256[expected.path],expected.sha256,'EPD palette must bind the compiled controller source');
  }
  server = createServer(async (request, response) => {
    try {
      const path = new URL(request.url, 'http://localhost').pathname;
      if (!path.startsWith(basePath)) { response.writeHead(404).end(); return; }
      const file = resolve(site, decodeURIComponent(path.slice(basePath.length)) || 'index.html');
      if (!file.startsWith(site + '/')) { response.writeHead(403).end(); return; }
      // No COOP/COEP headers: the exported Pages Service Worker must enable SAB.
      response.writeHead(200, {'content-type':mime[extname(file)] || 'application/octet-stream', 'cache-control':'no-cache'});
      response.end(await readFile(file));
    } catch { response.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}${basePath}`; report.url = origin;
  browser = await chromium.launch({headless:true,
    ...(process.env.M5_WASM_CHROME ? {executablePath:process.env.M5_WASM_CHROME} : {}),
    args:['--enable-webgl', '--use-gl=angle', ...(hardwareGPU ? ['--use-angle=metal', '--ignore-gpu-blocklist'] : ['--use-angle=swiftshader'])]});
  report.browser = browser.version(); report.hardware_gpu = hardwareGPU;
  page = await browser.newPage({viewport:{width:1200,height:900}});
  workerTargets = await observeWorkerTargets(browser);
  await page.route(url => [8787,8830].includes(Number(url.port)) || /\/api\/v1(?:\/|$)/.test(url.pathname), route => route.abort('blockedbyclient'));
  page.on('worker', worker => {
    const row={kind:worker.url().includes('/public-qemu-engine.js')?'engine':'nested-pthread',
      created_at:new Date().toISOString(),closed_at:null};
    workerObservations.push(row);
    worker.on('close', () => { row.closed_at=new Date().toISOString(); });
  });
  report.observed_dedicated_workers = workerObservations;
  page.on('pageerror', error => errors.push(error.message)); page.on('request', request => requests.push({url:request.url(),method:request.method()}));
  await page.goto(origin, {waitUntil:'domcontentloaded'});
  await page.waitForFunction(() => crossOriginIsolated, {}, {timeout:45000});
  check('pages-service-worker-isolation', await page.evaluate(() => crossOriginIsolated && typeof SharedArrayBuffer === 'function'));
  report.admission = await page.evaluate(async ({device, origin, clockDivisor, publicUI}) => {
    const {loadQemuBrowserProfiles,getQemuBrowserProfile} = await import(new URL('platform/web/public-qemu-profiles.js', origin));
    const {composeQemuProbeFirmware} = await import(new URL('platform/web/public-qemu-probe-firmware.js', origin));
    const {PublicQemuRuntime} = await import(new URL('platform/web/public-qemu-runtime.js', origin));
    const configResponse = await fetch(new URL('platform/web/site-config.json', origin));
    if (!configResponse.ok) throw new Error('Exported site configuration unavailable');
    const config = await configResponse.json(), allowCandidateProfiles = config.publication_eligible === false;
    if (typeof config.publication_eligible !== 'boolean' || !Array.isArray(config.browser_candidate_profiles)) throw new Error('Invalid export admission configuration');
    const selected = config.browser_candidate_profiles;
    if (!allowCandidateProfiles && selected.length) throw new Error('Public export contains candidate selections');
    const registry = await loadQemuBrowserProfiles({root:origin});
    if (registry.profiles.some(row => row.admission === 'candidate' && (!allowCandidateProfiles || !selected.includes(row.deviceId)))
      || selected.some(id => !registry.profiles.some(row => row.deviceId === id))) throw new Error('Export contains an unselected or unavailable candidate');
    if (!allowCandidateProfiles && clockDivisor !== undefined) throw new Error('Public board validation must use the exported default clock');
    const profile = getQemuBrowserProfile(device, registry, {allowCandidateProfiles});
    if (!profile) throw new Error('Selected board absent from this export admission');
    const admission = {profile, publication_eligible:config.publication_eligible, allow_candidate_profiles:allowCandidateProfiles,
      candidate_profiles:selected, exported_profiles:registry.profiles.map(row => ({device:row.deviceId, admission:row.admission}))};
    if (publicUI) {
      // Observe the actual public controller and newly selected model shell.
      // This wraps their constructors/start path without replacing any input,
      // serial, pixels, firmware composition or production event callbacks.
      const {ModelDeviceShell} = await import(new URL('platform/web/model-shell.js?v=20261026h', origin));
      const create = ModelDeviceShell.create;
      ModelDeviceShell.create = async function(...args) {
        const shell = await create.apply(this, args);
        if (args[1].id === device) {
          globalThis.boardUiShell = shell;
          shell.observedRenderedSequence = 0;
          shell.viewer.on('render', () => { shell.observedRenderedSequence = shell.frameSeq; });
        }
        return shell;
      };
      const start = PublicQemuRuntime.prototype.start;
      PublicQemuRuntime.prototype.start = function(...args) {
        if (args[0].device === device) {
          const runtime = this, observedErrors = [], uiInputs = [], onError = this.onError, input = this.input;
          this.onError = error => { observedErrors.push(error.message); onError(error); };
          this.input = function(event) { uiInputs.push(structuredClone(event)); return input.call(this, event); };
          globalThis.boardRun = {profile, runtime, errors:observedErrors, uiInputs,
            renderPausedAtStart: globalThis.boardUiShell?.viewer?.renderingPaused,
            get serial(){return runtime.serial || '';}, get frame(){return runtime.lastFrame;}};
        }
        return start.apply(this, args);
      };
      return admission;
    }
    const composed = await composeQemuProbeFirmware({profile, root:origin});
    const canvas = document.createElement('canvas'); canvas.id = 'candidateGuestCanvas'; canvas.width = profile.display.width; canvas.height = profile.display.height;
    canvas.style.cssText = 'position:fixed;right:16px;top:16px;z-index:99999;border:4px solid #fff;background:#000;image-rendering:pixelated;transform-origin:top right;transform:scale(2)';
    document.body.append(canvas);
    const state = {profile, serial:'', frames:0, errors:[], composition:composed.provenance};
    const runtime = new PublicQemuRuntime({root:origin, allowCandidateProfiles, requestTimeout:90000,
      onSerial:text => {state.serial += text;}, onError:error => state.errors.push(error.message),
      onFrame:frame => {
        state.frame = frame; state.frames++;
        if (frame.source === 'qmp-screendump') state.qmpControlFrame = frame;
        const data = new ImageData(frame.width, frame.height);
        for (let at = 0; at < frame.width * frame.height; at++) {
          const color = frame.pixels[at * 2] | frame.pixels[at * 2 + 1] << 8;
          data.data[at * 4] = Math.round((color >> 11) * 255 / 31); data.data[at * 4 + 1] = Math.round((color >> 5 & 63) * 255 / 63); data.data[at * 4 + 2] = Math.round((color & 31) * 255 / 31); data.data[at * 4 + 3] = 255;
        }
        canvas.getContext('2d').putImageData(data, 0, 0);
      }});
    state.runtime = runtime; globalThis.boardRun = state;
    await runtime.start({device, firmware:composed.bytes, clockDivisor});
    return admission;
  }, {device, origin, clockDivisor, publicUI});
  if (publicUI) {
    await page.waitForFunction(() => document.querySelector('#deviceMount')?.dataset.deviceId === 'cores3', {}, {timeout:45000});
    const shellReady = async () => {
      await page.waitForFunction(id => {
        const mount = document.querySelector('#deviceMount');
        return mount?.dataset.deviceId === id
          && (globalThis.boardUiShell?.device.id === id || mount.querySelector('[data-renderer-fallback="true"]'));
      }, device, {timeout:45000});
      return page.evaluate(id => ({
        model_shell: globalThis.boardUiShell?.device.id === id,
        renderer_fallback: !!document.querySelector(`#deviceMount [data-renderer-fallback="true"]`),
      }), device);
    };
    await page.locator(`button[data-device-id="${device}"]`).click();
    let publicShell;
    try { publicShell = await shellReady(); }
    catch (error) {
      report.model_shell_selection_retry = {first_error:error.message,
        dom_device:await page.evaluate(() => document.querySelector('#deviceMount')?.dataset.deviceId || null)};
      await page.waitForTimeout(1000);
      await page.locator(`button[data-device-id="${device}"]`).click();
      publicShell = await shellReady();
    }
    report.public_shell = publicShell;
    report.webgl_renderer = publicShell.model_shell ? await page.evaluate(() => {
      const gl = boardUiShell.viewer.renderer.getContext();
      const info = gl.getExtension('WEBGL_debug_renderer_info');
      return info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    }) : 'generic-shell-fallback';
    if (hardwareGPU && publicShell.model_shell) assert.doesNotMatch(report.webgl_renderer, /swiftshader|software/i,
      'hardware WebGL was required but the browser selected software rendering');
    await page.locator('.advanced-options > summary').click();
    await page.locator('#runtimeMode').selectOption('browser');
    await page.locator('input[name="firmwareSource"][value="reference"]').check();
    check('public-ui-selected-board-reference', await page.locator('#referenceTitle').textContent().then(text => text.includes('屏幕与输入示例')));
    if (uploadPath) {
      const bytes = await readFile(uploadPath), hash = createHash('sha256').update(bytes).digest('hex');
      const profile = report.admission.profile;
      check('local-upload-exact-reviewed-firmware', hash === profile.fixture.firmwareSHA256 && bytes.length === profile.flashMb * 1048576);
      report.upload = {name:basename(uploadPath), bytes:bytes.length, sha256:hash};
      await page.locator('input[name="firmwareSource"][value="local"]').check();
      await page.locator('#firmwareFile').setInputFiles(uploadPath);
      await page.locator('#firmwareSha').fill(hash);
    }
    await page.locator('#startBtn').click();
  }
  const textureReadback = async () => {
    if (!publicUI || !report.public_shell?.model_shell) return null;
    const handle = await page.waitForFunction(() => {
      const shell = globalThis.boardUiShell, frame = globalThis.boardRun?.frame;
      if (!shell?.display || !frame || shell.frameSeq !== frame.sequence
          || shell.observedRenderedSequence < frame.sequence) return false;
      const display = shell.display;
      const rotated = display.meta.nativeRasterRotation === 90
        && frame.width === display.height && frame.height === display.width;
      if (!rotated && (frame.width !== display.width || frame.height !== display.height)) return false;
      for (let y=0; y<frame.height; y++) for (let x=0; x<frame.width; x++) {
        const at=(y*frame.width+x)*2, value=frame.pixels[at]|frame.pixels[at+1]<<8;
        const r=value>>11, g=value>>5&63, b=value&31;
        const rgb=display.getPixel(rotated ? display.width-1-y : x, rotated ? x : y);
        if (rgb[0]!==((r<<3)|(r>>2)) || rgb[1]!==((g<<2)|(g>>4)) || rgb[2]!==((b<<3)|(b>>2))) return false;
      }
      return {frame_sequence:frame.sequence, rendered_sequence:shell.observedRenderedSequence,
        pixels_compared:frame.width*frame.height, model_rotation:rotated ? 90 : 0,
        scope:'Exact native RGB565 to model texture buffer after the viewer render event; no optical or hardware claim.'};
    }, {}, {timeout:60000, polling:200});
    const result=await handle.jsonValue(); await handle.dispose(); return result;
  };
  const ready = await guest('ready', () => true, readyTimeout);
  if(device==='stickc-plus2')check('original-plus2-board-and-three-guest-buttons',ready.board===5&&ready.width===135&&ready.height===240
    &&JSON.stringify(ready.buttons)===JSON.stringify(['a','b','power']),ready);
  if(device==='stickc')check('original-stickc-board',ready.board===3&&ready.width===80&&ready.height===160,ready);
  if(device==='stickc-plus')check('original-stickc-plus-board',ready.board===4&&ready.width===135&&ready.height===240,ready);
  if(device==='stickc-plus-se')check('original-stickc-plus-se-board',ready.board===4&&ready.width===135&&ready.height===240,ready);
  const rawTouch = await page.evaluate(() => boardRun.profile.fixture.coordinateSource === 'official-raw-point');
  if (rawTouch) check('official-raw-touch-fixture-identity', ready.coordinate_source === 'official-raw-point'
    && ready.logical_touch_status === 'known-sdk-calibration-gap', ready);
  const dimensions = await page.evaluate(() => boardRun.profile.display);
  const logicalDimensions = await page.evaluate(() => boardRun.profile.fixture.logicalDisplay || boardRun.profile.display);
  check('same-guest-ready-and-display', ready.device === device && ready.width === logicalDimensions.width && ready.height === logicalDimensions.height, ready);
  if (publicUI && report.public_shell.model_shell) {
    const rendering = await page.evaluate(() =>
      ({at_start: boardRun.renderPausedAtStart, at_ready: boardUiShell.viewer.renderingPaused}));
    check('model-rendering-paused-until-guest-ready', rendering.at_start === true && rendering.at_ready === false, rendering);
  } else if (publicUI) {
    check('generic-shell-has-no-model-render-loop', await page.evaluate(() => Boolean(globalThis.boardRun) && globalThis.boardRun.renderPausedAtStart !== true), report.public_shell);
  }
  if (diagnostic) {
    try { await page.waitForFunction(() => boardRun.frame, {}, {timeout:15000}); } catch { report.shared_first_frame_timeout = true; }
    const snapshot = async () => {
      const run = globalThis.boardRun;
      const sample = async frame => {
        if (!frame) return null;
        const at = (2 * frame.width + 2) * 2, colors = new Map(), markerBounds = {};
        for (let at = 0; at < frame.pixels.length; at += 2) {
          const color = frame.pixels[at] | frame.pixels[at + 1] << 8; colors.set(color, (colors.get(color) || 0) + 1);
          if ([0xf800, 0x07e0].includes(color)) {
            const x = at / 2 % frame.width, y = Math.floor(at / 2 / frame.width), box = markerBounds[color] ||= {x1:x,y1:y,x2:x,y2:y,count:0};
            box.x1 = Math.min(box.x1, x); box.y1 = Math.min(box.y1, y); box.x2 = Math.max(box.x2, x); box.y2 = Math.max(box.y2, y); box.count++;
          }
        }
        const sha256 = [...new Uint8Array(await crypto.subtle.digest('SHA-256', frame.pixels))].map(value => value.toString(16).padStart(2, '0')).join('');
        return {width:frame.width, height:frame.height, source:frame.source, sourceSequence:frame.sourceSequence, sourceUpdates:frame.sourceUpdates,
          sha256, markerBounds, pixel_2_2:frame.pixels[at] | frame.pixels[at + 1] << 8, distinct_colors:colors.size, colors:[...colors.entries()].sort((a,b) => b[1] - a[1]).slice(0,20)};
      };
      return {frame:await sample(run.frame), qmpControl:await sample(run.qmpControlFrame), serial:run.serial, errors:run.errors, evidence:run.runtime.evidence()};
    };
    report.shared_before_control = await page.evaluate(snapshot);
    await writeFile(resolve(output, 'shared-before-control.json'), JSON.stringify(report.shared_before_control, null, 2) + '\n');
    try { await page.evaluate(() => boardRun.runtime.ask('frame', {diagnosticTransport:'qmp-screendump'})); }
    catch (error) { report.qmp_control_error = error.message; }
    await new Promise(resolve => setTimeout(resolve, 1000));
    report.after_explicit_qmp_control = await page.evaluate(snapshot);
    await writeFile(resolve(output, 'after-explicit-qmp-control.json'), JSON.stringify(report.after_explicit_qmp_control, null, 2) + '\n');
    await page.screenshot({path:resolve(output, 'diagnostic.png'), fullPage:true});
    report.status = 'DIAGNOSTIC'; report.functional_pass = false;
  } else {
  const frameOracle = await page.evaluate(() => boardRun.profile.fixture.frameOracle || null);
  if(epdOracle)await page.evaluate(oracle=>{
    if(boardRun.profile.fixture.sources['main.py'].sha256!==oracle.mainSHA256
      ||boardRun.profile.fixture.uiRotation!==oracle.uiRotation
      ||boardRun.profile.fixture.frameOracle.encoding!=='sdk-quality-pattern-v1')throw new Error('EPD oracle fixture identity mismatch');
    // These arrays only compare observed pixels; they never feed a controller.
    const compiled=new Map();
    const compile=region=>{
      if(compiled.has(region))return compiled.get(region);
      const r=region.rect,pixels=new Uint16Array(r.width*r.height).fill(region.primary);
      for(const point of region.exceptions)pixels[(point.y-r.y)*r.width+point.x-r.x]=point.rgb565;
      const value={rect:r,pixels};compiled.set(region,value);return value;
    };
    globalThis.boardPanelOracle=oracle;
    globalThis.boardPanelMatch=regions=>{
      const frame=boardRun.frame;if(!frame)return false;
      return regions.every(region=>{
        const {rect:r,pixels}=compile(region);
        for(let y=0;y<r.height;y++)for(let x=0;x<r.width;x++){
          const at=((r.y+y)*frame.width+r.x+x)*2;
          if((frame.pixels[at]|frame.pixels[at+1]<<8)!==pixels[y*r.width+x])return false;
        }
        return true;
      });
    };
  },epdOracle);
  const panelPage=async(count,previousCounter=null)=>{
    await page.waitForFunction(({count,previousCounter})=>{
      const f=boardRun.frame;if(!f)return false;
      if(!boardPanelMatch([...boardPanelOracle.palette,boardPanelOracle.bit0[count?'after':'before']]))return false;
      const at=(x,y)=>f.pixels[(y*f.width+x)*2]|f.pixels[(y*f.width+x)*2+1]<<8;
      const counter=[];for(let y=210;y<250;y++)for(let x=24;x<240;x++)counter.push(at(x,y));
      return !previousCounter||counter.some((value,index)=>value!==previousCounter[index]);
    },{count,previousCounter},{timeout:60000});
    return page.evaluate(async()=>{
      const f=boardRun.frame,counter=[];for(let y=210;y<250;y++)for(let x=24;x<240;x++){
        const at=(y*f.width+x)*2;counter.push(f.pixels[at]|f.pixels[at+1]<<8);
      }
      const digest=await crypto.subtle.digest('SHA-256',new Uint16Array(counter));
      return {counter,sha256:[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('')};
    });
  };
  await page.waitForFunction(oracle => {
    const frame = boardRun.frame; if (!frame || new Set(frame.pixels).size <= 1) return false;
    if (oracle) {
      if(oracle.encoding==='sdk-quality-pattern-v1')return boardPanelMatch([boardPanelOracle.marker.before]);
      const {x,y,width,height}=oracle.rect;
      for(let row=y;row<y+height;row++)for(let col=x;col<x+width;col++){
        const at=(row*frame.width+col)*2;
        if((frame.pixels[at]|frame.pixels[at+1]<<8)!==oracle.before)return false;
      }
      return true;
    }
    let red = 0; for (let at = 0; at < frame.pixels.length; at += 2) if (frame.pixels[at] === 0 && frame.pixels[at + 1] === 0xf8) red++;
    return red === 64;
  }, frameOracle, {timeout:60000});
  const marker = await page.evaluate(oracle => {
    const frame = boardRun.frame, pixels = [];
    if(oracle){
      const {x,y,width,height}=oracle.rect;
      for(let row=y;row<y+height;row++)for(let col=x;col<x+width;col++)pixels.push(row*frame.width+col);
    }else for (let at = 0; at < frame.pixels.length; at += 2) if (frame.pixels[at] === 0 && frame.pixels[at + 1] === 0xf8) pixels.push(at / 2);
    boardRun.markerPixels = pixels;
    const x = pixels.map(at => at % frame.width), y = pixels.map(at => Math.floor(at / frame.width));
    return {x1:Math.min(...x), y1:Math.min(...y), x2:Math.max(...x), y2:Math.max(...y), count:pixels.length, source:frame.source,
      sourceSequence:frame.sourceSequence, sourceUpdates:frame.sourceUpdates};
  }, frameOracle);
  const expectedMarker=frameOracle?.rect||await page.evaluate(()=>boardRun.profile.fixture.logicalMarker)||{x:2,y:2,width:8,height:8};
  check(frameOracle?'complete-native-panel-marker':'complete-native-red-marker',
    marker.count===expectedMarker.width*expectedMarker.height && marker.x2-marker.x1===expectedMarker.width-1
      && marker.y2-marker.y1===expectedMarker.height-1, marker);
  if (publicUI) {
    await page.waitForFunction(modelShell => Number(document.querySelector('#deviceMount').dataset.frameSequence) > 0
      && (!modelShell || globalThis.boardUiShell?.frameSeq > 0), report.public_shell.model_shell, {timeout:30000});
    if(await page.locator('#rawFramePanel').evaluate(panel=>panel.hidden))await page.locator('#nativeScreenBtn').click();
    check(report.public_shell.model_shell?'public-ui-3d-and-visible-native-frame':'public-ui-generic-and-visible-native-frame', await page.evaluate(modelShell => {
      const canvas = document.querySelector('#rawFrameCanvas');
      return (!modelShell || boardUiShell.model && boardUiShell.frameSeq > 0) && !document.querySelector('#rawFramePanel').hidden
        && canvas.width === boardRun.frame.width && canvas.height === boardRun.frame.height
        && new Set(canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data).size > 1;
    }, report.public_shell.model_shell));
    check('public-ui-native-to-rendered-model-texture-before-input', true, await textureReadback());
    if (!await page.evaluate(() => boardRun.profile.inputs.touch)) {
      await page.locator('#rawFrameCanvas').click();
      await page.waitForTimeout(250);
      check('non-touch-screen-click-does-not-send-touch-or-show-error', await page.evaluate(() =>
        !boardRun.uiInputs.some(event => event.type === 'touch') && document.querySelector('#errorBanner').hidden));
    }
  }
  report.display_coordinate_observation = {guest_marker:expectedMarker, frame_marker:marker,
    logical_display:logicalDimensions,physical_display:dimensions,
    offset_x:marker.x1 - expectedMarker.x, offset_y:marker.y1 - expectedMarker.y,
    exact_guest_coordinates:marker.x1 === expectedMarker.x && marker.y1 === expectedMarker.y,
    scope:'Observed firmware/model calibration only; a nonzero offset remains a separate display-model boundary.'};
  const first = await page.evaluate(() => boardRun.runtime.evidence());
  await writeFile(resolve(output, 'running-before-input.json'), JSON.stringify(first, null, 2) + '\n');
  check('hash-pinned-composed-firmware', first.receipt.firmwareSha256 === await page.evaluate(() => boardRun.profile.fixture.firmwareSHA256), first.receipt);
  const expectedProfile = await page.evaluate(() => ({id:boardRun.profile.profile, clockDivisor:boardRun.profile.clockDivisor}));
  check('exported-default-clock-profile', first.receipt.clockDivisor === (clockDivisor ?? expectedProfile.clockDivisor)
    && (clockDivisor !== undefined || first.receipt.profile === expectedProfile.id), first.receipt);
  check('actual-physical-frame-dimensions',first.last_frame.width===dimensions.width&&first.last_frame.height===dimensions.height);
  const touchPoint=await page.evaluate(()=>boardRun.profile.fixture.touchPoint||{x:Math.floor(boardRun.profile.display.width/2),y:Math.floor(boardRun.profile.display.height/2)});
  const keyboardOracle=await page.evaluate(()=>boardRun.profile.fixture.keyboardOracle||null);
  const firstPanelPage=frameOracle?await panelPage(0):null;
  if(firstPanelPage)check('epd-original-controller-palette-and-zero-count-pixels',true,{counter_sha256:firstPanelPage.sha256});
  // This fixed oracle belongs to the pinned Cardputer fixture: the counter is
  // separate from both corner markers and the key-state text at the bottom.
  const keyboardFrame = async (pressed, previousCounter = null) => {
    await page.waitForFunction(({pressed,previousCounter}) => {
      const f=boardRun.frame;if(!f||f.width!==240||f.height!==135)return false;
      const color=pressed?0xfe68:0x23bf;
      for(let y=2;y<10;y++)for(let x=228;x<236;x++){
        const at=(y*f.width+x)*2;if((f.pixels[at]|f.pixels[at+1]<<8)!==color)return false;
      }
      const counter=[];
      for(let y=67;y<97;y++)for(let x=8;x<232;x++){
        const at=(y*f.width+x)*2;counter.push(f.pixels[at],f.pixels[at+1]);
      }
      return !previousCounter||counter.some((value,index)=>value!==previousCounter[index]);
    },{pressed,previousCounter},{timeout:30000});
    return page.evaluate(async () => {
      const f=boardRun.frame,counter=[];
      for(let y=67;y<97;y++)for(let x=8;x<232;x++){
        const at=(y*f.width+x)*2;counter.push(f.pixels[at],f.pixels[at+1]);
      }
      const digest=await crypto.subtle.digest('SHA-256',new Uint8Array(counter));
      return {counter,sha256:[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('')};
    });
  };
  let lastKeyboardFrame=keyboardOracle?await keyboardFrame(false):null;
  const negativeTouch=await page.evaluate(()=>boardRun.profile.fixture.negativeTouchPoint||null);
  const touchAt=async point=>{
    await page.locator('#rawFrameCanvas').scrollIntoViewIfNeeded();
    const box=await page.locator('#rawFrameCanvas').boundingBox();
    await page.mouse.move(box.x+box.width*point.x/dimensions.width,box.y+box.height*point.y/dimensions.height);
  };
  if(publicUI&&negativeTouch){
    await touchAt(negativeTouch);await page.mouse.down();
    const ignored=await guest('ignored',row=>row.count===0,30000);await page.mouse.up();
    const negativeRelease=await guest('released',row=>row.count===0,30000);
    const negativePress=await guest('pressed',row=>row.seq===ignored.seq-1,30000);
    report.negative_touch_observation={pressed:negativePress,ignored,released:negativeRelease};
    check('outside-target-touch-keeps-zero-count',ignored.count===0,ignored);
    if (rawTouch) check('outside-target-official-raw-coordinates', ignored.coordinate_source === 'official-raw-point'
      && ignored.x === negativeTouch.x && ignored.y === negativeTouch.y, ignored);
    if (rawTouch) check('outside-target-press-and-cached-release', negativePress.coordinate_source === 'official-raw-point'
      && negativePress.coordinates_cached === false && negativePress.x === negativeTouch.x && negativePress.y === negativeTouch.y
      && negativePress.size === 1 && negativePress.touch_id === 0 && negativePress.logical_x === 240 && negativePress.logical_y === 400
      && negativeRelease.coordinate_source === 'official-raw-point' && negativeRelease.coordinates_cached === true
      && negativeRelease.x === negativePress.x && negativeRelease.y === negativePress.y, report.negative_touch_observation);
    const unchanged=await panelPage(0);
    check('outside-target-touch-keeps-counter-pixels',unchanged.sha256===firstPanelPage.sha256);
  }
  if (publicUI && await page.evaluate(() => boardRun.profile.inputs.touch)) {
    await touchAt(touchPoint); await page.mouse.down();
  } else if (publicUI) {
    const key = await page.evaluate(modelShell => {
      const target = {atoms3:'button',atoms3r:'button',sticks3:'btnA','stickc-plus2':'a',stickc:'a','stickc-plus':'a','stickc-plus-se':'a',stamplc:'a',papercolor:'key1',papermono:'key1','cardputer-adv':'key-KeyA'}[boardRun.profile.deviceId];
      if(!target)throw new Error('No reviewed public model input binding for this board');
      return {target,key:modelShell
        ? Object.entries(boardUiShell.model.keymap).find(([,path]) => path === target)?.[0] : null};
    }, report.public_shell.model_shell);
    if (report.public_shell.model_shell) {
      assert.ok(key.key, 'actual 3D button must expose a focused keyboard binding'); report.input_keyboard = key.key;
      await page.locator('#deviceMount .three-device-stage canvas').focus(); await page.keyboard.down(key.key);
    } else {
      const control=page.locator(`#deviceMount button.device-control[data-control-id="${key.target}"]`);
      const box=await control.boundingBox();assert.ok(box,'generic shell must expose the native control button');
      await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
      report.input_pointer_control=key.target;
    }
  } else await page.evaluate(async () => {
    const id = Object.keys(boardRun.profile.inputs.buttons)[0]||boardRun.profile.inputs.keyboard[0];
    const point=boardRun.profile.fixture.touchPoint||{x:Math.floor(boardRun.profile.display.width/2),y:Math.floor(boardRun.profile.display.height/2)};
    await boardRun.runtime.input(boardRun.profile.inputs.touch ? {type:'touch', ...point, down:true} : {type:'button', id, down:true});
  });
  const firstCount=await guest('count',row=>row.count===1,30000);
  check('guest-button-counter',firstCount.count===1,firstCount);
  const firstPress=await guest('pressed',row=>row.seq===firstCount.seq-1,30000);
  report.guest_input_observation={requested_physical_touch:await page.evaluate(()=>boardRun.profile.inputs.touch)?touchPoint:null,pressed:firstPress};
  if (rawTouch) check('original-ft-raw-point-and-stock-logical-gap', firstPress.coordinate_source === 'official-raw-point'
    && firstPress.coordinates_cached === false && firstPress.x === touchPoint.x && firstPress.y === touchPoint.y
    && firstPress.size === 1 && firstPress.touch_id === 0 && firstPress.logical_x === 90 && firstPress.logical_y === 400, firstPress);
  if(keyboardOracle){
    const key=keyboardOracle.cases[0];
    check('keyboard-original-driver-first-press',firstCount.keycode===key.keycode&&firstCount.row===key.row&&firstCount.col===key.col
      &&firstCount.driver_state===true&&firstPress.driver_pressed===true,firstCount);
    const pressedFrame=await keyboardFrame(true,lastKeyboardFrame.counter);
    check('keyboard-first-press-counter-and-state-pixels',pressedFrame.sha256!==lastKeyboardFrame.sha256,{counter_sha256:pressedFrame.sha256});
    lastKeyboardFrame=pressedFrame;
  }
  if (publicUI && await page.evaluate(() => boardRun.profile.inputs.touch)) await page.mouse.up();
  else if (publicUI && report.public_shell.model_shell) await page.keyboard.up(report.input_keyboard);
  else if (publicUI) await page.mouse.up();
  else await page.evaluate(() => {
    const point=boardRun.profile.fixture.touchPoint||{x:Math.floor(boardRun.profile.display.width/2),y:Math.floor(boardRun.profile.display.height/2)};
    return boardRun.runtime.input(boardRun.profile.inputs.touch ? {type:'touch', ...point, down:false}
      : {type:'button', id:Object.keys(boardRun.profile.inputs.buttons)[0]||boardRun.profile.inputs.keyboard[0], down:false});
  });
  const firstRelease=await guest('released',row=>row.count===1,30000);
  report.guest_input_observation.released=firstRelease;
  if (rawTouch) check('release-explicitly-retains-last-pressed-raw-point', firstRelease.coordinate_source === 'official-raw-point'
    && firstRelease.coordinates_cached === true && firstRelease.x === firstPress.x && firstRelease.y === firstPress.y, firstRelease);
  check('guest-button-release', !keyboardOracle||firstRelease.driver_pressed===false,firstRelease);
  if(keyboardOracle){
    const releasedFrame=await keyboardFrame(false);
    check('keyboard-first-release-state-pixels',releasedFrame.sha256===lastKeyboardFrame.sha256,{counter_sha256:releasedFrame.sha256});
  }
  await page.waitForFunction(oracle => {
    const f = boardRun.frame;
    if(oracle?.encoding==='sdk-quality-pattern-v1')return boardPanelMatch([boardPanelOracle.marker.after]);
    const expected=oracle?.after??0x07e0;
    if (!boardRun.markerPixels.every(at => (f.pixels[at*2]|f.pixels[at*2+1]<<8)===expected)) return false;
    if(!oracle)for (let at = 0; at < f.pixels.length; at += 2) if (f.pixels[at] === 0 && f.pixels[at + 1] === 0xf8) return false;
    return true;
  }, frameOracle, {timeout:60000}); check('controller-input-changes-native-frame-marker', true);
  if(firstPanelPage){
    const changed=await panelPage(1,firstPanelPage.counter);
    check('epd-refresh-changes-count-text-and-count-bit',changed.sha256!==firstPanelPage.sha256,{counter_sha256:changed.sha256});
  }
  if(device==='stickc-plus2'&&publicUI){
    report.multi_button_cases=[{button:'a',gpio:37,pressed:firstPress,count:firstCount,released:firstRelease}];
    for(const item of [{button:'b',gpio:39,index:1},{button:'power',gpio:35,index:2}]){
      const before=await page.evaluate(async index=>{
        const frame=boardRun.frame,pixels=[];
        for(let y=72+index*36;y<96+index*36;y++)for(let x=8;x<frame.width-8;x++){
          const at=(y*frame.width+x)*2;pixels.push(frame.pixels[at],frame.pixels[at+1]);
        }
        const hash=await crypto.subtle.digest('SHA-256',new Uint8Array(pixels));
        return {sequence:frame.sequence,sha256:[...new Uint8Array(hash)].map(n=>n.toString(16).padStart(2,'0')).join('')};
      },item.index);
      const key=await page.evaluate(target=>Object.entries(boardUiShell.model.keymap).find(([,path])=>path===target)?.[0],item.button);
      assert.ok(key,'original model button must expose its own keyboard binding');
      const domKey=/^Key[A-Z]$/.test(key)?key.slice(3).toLowerCase():key;
      await page.locator('#deviceMount .three-device-stage canvas').focus();await page.keyboard.down(domKey);
      let count,pressed;
      try{
        count=await guest('button-count',event=>event.button===item.button&&event.count===1,30000);
        pressed=await guest('button-pressed',event=>event.button===item.button&&event.seq===count.seq-1,30000);
      }finally{await page.keyboard.up(domKey);}
      const released=await guest('button-released',event=>event.button===item.button&&event.count===1,30000);
      check('plus2-'+item.button+'-original-driver-down-and-up',pressed.pressed===true&&released.pressed===false
        &&pressed.gpio===item.gpio&&released.gpio===item.gpio,{pressed,count,released});
      const changed=await page.waitForFunction(async({index,before})=>{
        const frame=boardRun.frame;if(frame.sequence<=before.sequence)return false;const pixels=[];
        for(let y=72+index*36;y<96+index*36;y++)for(let x=8;x<frame.width-8;x++){
          const at=(y*frame.width+x)*2;pixels.push(frame.pixels[at],frame.pixels[at+1]);
        }
        const hash=await crypto.subtle.digest('SHA-256',new Uint8Array(pixels));
        const sha256=[...new Uint8Array(hash)].map(n=>n.toString(16).padStart(2,'0')).join('');
        return sha256!==before.sha256?{sequence:frame.sequence,sha256}:false;
      },{index:item.index,before},{timeout:30000,polling:100});
      const after=await changed.jsonValue();await changed.dispose();
      check('plus2-'+item.button+'-changes-own-native-counter-pixels',true);
      report.multi_button_cases.push({...item,keyboard:key,dom_key:domKey,pressed,count,released,before_counter:before,after_counter:after,
        texture:await textureReadback()});
    }
  }
  if(keyboardOracle&&publicUI){
    report.keyboard_cases=[{...keyboardOracle.cases[0],count:firstCount,release:firstRelease,counter_sha256:lastKeyboardFrame.sha256}];
    for(const [index,key] of keyboardOracle.cases.entries()){
      if(index===0)continue;
      await page.locator('#deviceMount .three-device-stage canvas').focus();await page.keyboard.down(key.domKey);
      const event=await guest('count',row=>row.count===index+1,30000);
      const pressed=await guest('pressed',row=>row.count===index&&row.keycode===key.keycode,30000);
      check('keyboard-'+key.qcode+'-real-fifo-press',event.keycode===key.keycode&&event.row===key.row&&event.col===key.col
        &&event.driver_state===true&&pressed.driver_pressed===true,event);
      const pressedFrame=await keyboardFrame(true,lastKeyboardFrame.counter);
      check('keyboard-'+key.qcode+'-counter-and-press-pixels',pressedFrame.sha256!==lastKeyboardFrame.sha256,{counter_sha256:pressedFrame.sha256});
      lastKeyboardFrame=pressedFrame;
      await page.keyboard.up(key.domKey);
      const release=await guest('released',row=>row.count===index+1&&row.keycode===key.keycode,30000);
      check('keyboard-'+key.qcode+'-original-driver-release',release.driver_pressed===false,release);
      const releasedFrame=await keyboardFrame(false);
      check('keyboard-'+key.qcode+'-release-pixels',releasedFrame.sha256===pressedFrame.sha256,{counter_sha256:releasedFrame.sha256});
      report.keyboard_cases.push({...key,count:event,release,counter_sha256:releasedFrame.sha256});
    }
  }
  if (publicUI) check('public-ui-native-to-rendered-model-texture-after-input', true, await textureReadback());
  check('unsupported-button-fails-closed', await page.evaluate(async () => {try {await boardRun.runtime.input({type:'button', id:'unmapped-control', down:true}); return false;} catch {return true;}}));
  if (publicUI) { await page.locator('#pauseBtn').click(); await page.waitForFunction(() => boardRun.runtime.status === 'paused'); }
  else await page.evaluate(() => boardRun.runtime.pause());
  await new Promise(resolve => setTimeout(resolve, 500));
  const paused = await page.evaluate(() => boardRun.serial); await new Promise(resolve => setTimeout(resolve, 1400));
  check('qmp-pause-freezes-guest', paused === await page.evaluate(() => boardRun.serial));
  const heartbeatCount = (paused.match(/"kind": "heartbeat"/g) || []).length;
  if (publicUI) await page.locator('#pauseBtn').click();
  else await page.evaluate(() => boardRun.runtime.resume());
  await page.waitForFunction(previous => (boardRun.serial.match(/"kind": "heartbeat"/g) || []).length > previous,
    heartbeatCount, {timeout:30000}); check('qmp-resume-fresh-guest-heartbeat', true);
  // The fixture emits input edges before it finishes drawing text. Capture
  // after a fresh heartbeat so a screenshot does not stop mid-glyph.
  if(publicUI)report.final_texture_readback=await textureReadback();
  await page.screenshot({path:resolve(output, 'native-frame.png'), fullPage:true});
  const completeSerial=await page.evaluate(()=>boardRun.serial);
  check('guest-remains-free-of-panic-or-python-traceback',
    !/Guru Meditation Error|Interrupt wdt timeout|A fatal error occurred|Traceback \(most recent call last\):/.test(completeSerial));
  const running = await page.evaluate(() => boardRun.runtime.evidence()); await writeFile(resolve(output, 'running-after-input.json'), JSON.stringify(running, null, 2) + '\n');
  if (publicUI) report.public_ui_inputs = await page.evaluate(() => boardRun.uiInputs);
  // Defer DOM destruction to verify pthread exit before normal iframe removal.
  await page.evaluate(() => {
    const frame=boardRun.runtime.iframe, remove=frame.remove;
    globalThis.boardDeferredRemoval={frame,remove,requests:0};
    frame.remove=()=>{boardDeferredRemoval.requests++;};
  });
  if (publicUI) { await page.locator('#stopBtn').click(); await page.waitForFunction(() => document.querySelector('#runtimeStatus').dataset.status === 'stopped', {}, {timeout:30000}); }
  else await page.evaluate(() => boardRun.runtime.stop());
  const stopped = await page.evaluate(() => boardRun.runtime.evidence()); await writeFile(resolve(output, 'stopped.json'), JSON.stringify(stopped, null, 2) + '\n');
  check('clean-guest-stop-and-worker-disposal', stopped.cleanup?.gracefulExit && stopped.cleanup?.exitCode === 0
    && stopped.cleanup?.workersAtExit === 0 && stopped.cleanup?.disposal?.workersTerminatedByDispose === 0
    && stopped.cleanup?.disposal?.workersRemaining === 0 && stopped.cleanup?.explicitWorkerDisposal && stopped.cleanup?.iframeRemoved
    && stopped.cleanup?.engineOwnership?.engineCloseNotificationReceived === true
    && stopped.cleanup?.engineOwnership?.engineSelfCloseNotifications === 1
    && stopped.cleanup?.engineOwnership?.engineNormalTerminations === 0
    && stopped.cleanup?.engineOwnership?.engineFallbackTerminations === 0, stopped.cleanup);
  // Check nested pthreads while the iframe is held, then all targets after
  // normal DOM removal. Bind both phases to the same run's actual worker count.
  const expectedWorkerTargets=stopped.cleanup.workersCreated+1;
  assert.ok(Number.isInteger(expectedWorkerTargets)&&expectedWorkerTargets>=2,'same-run pthread creation count is required');
  const nestedClose=await workerTargets.waitUntilOnly({minimumObserved:expectedWorkerTargets,
    allowedUrlPart:'/public-qemu-engine.js',timeoutMs:30000});
  const deferredRemoval=await page.evaluate(() => ({iframe_present:boardDeferredRemoval.frame.isConnected,
    removal_requests:boardDeferredRemoval.requests,iframe_count:document.querySelectorAll('iframe').length}));
  report.iframe_removal_control={...deferredRemoval,removal_deferred_by_harness:true,
    scope:'Real UI stop/quit/dispose; nested pthread targets are checked before iframe DOM removal, then all targets after it.'};
  check('created-pthreads-close-before-iframe-finalization', nestedClose.ok
    &&nestedClose.observed.length===expectedWorkerTargets
    &&nestedClose.observed.filter(target=>target.url.includes('/public-qemu-engine.js')).length===1
    &&deferredRemoval.iframe_present&&deferredRemoval.removal_requests===1&&deferredRemoval.iframe_count===1,
    {worker_targets:nestedClose,playwright_worker_events:workerObservations,iframe_removal:deferredRemoval});
  await page.evaluate(() => {
    const held=boardDeferredRemoval;held.remove.call(held.frame);delete globalThis.boardDeferredRemoval;
  });
  const targetClose=await workerTargets.waitUntilClosed({minimumObserved:expectedWorkerTargets});
  report.worker_targets={before_removal:nestedClose,after_removal:targetClose};
  report.playwright_worker_events=workerObservations;
  check('engine-and-created-pthreads-close-after-iframe-finalization',targetClose.ok
    &&targetClose.observed.length===expectedWorkerTargets
    &&targetClose.observed.filter(target=>target.url.includes('/public-qemu-engine.js')).length===1,targetClose);
  check('no-leftover-guest-iframe', await page.locator('iframe').count() === 0);
  check('no-page-errors', errors.length === 0, errors);
  check('no-device-service-requests', !requests.some(row => /\/api\/v1|:8787\b|:8830\b/.test(row.url)));
  report.firmware_sha256 = stopped.receipt.firmwareSha256; report.runtime = stopped.receipt; report.session_id = stopped.session_id; report.status = 'PASS';
  }
} catch (error) {
  report.status = 'FAIL'; report.error = error.message; process.exitCode = 1;
  if (page) {
    const failure = await page.evaluate(() => ({evidence:globalThis.boardRun?.runtime?.evidence(), serial:globalThis.boardRun?.serial,
      errors:globalThis.boardRun?.errors, profile:globalThis.boardRun?.profile})).catch(() => null);
    if (failure) await writeFile(resolve(output, 'failure-state.json'), JSON.stringify(failure, null, 2) + '\n');
    await page.screenshot({path:resolve(output, 'failure.png'), fullPage:true}).catch(() => {});
  }
}
finally {
  if (page) {
    report.final_cleanup = await page.evaluate(async () => {
      await globalThis.boardRun?.runtime?.stop(); return globalThis.boardRun?.runtime?.cleanupResult || null;
    }).catch(() => null);
  }
  await browser?.close(); if (server) await new Promise(resolve => server.close(resolve));
  report.finished_at = new Date().toISOString(); await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n'); console.log(JSON.stringify(report, null, 2));
}
