// Opt-in real per-board browser guest. Static hosting only; no Device Service.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname, extname} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {capturePublicQemuProvenance} from './public_qemu_artifacts.mjs';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const site = process.env.M5_PUBLIC_SITE && resolve(process.env.M5_PUBLIC_SITE);
if (!site) { console.log('SKIP: explicit M5_PUBLIC_SITE candidate export required'); process.exit(0); }
const device = process.env.M5_QEMU_DEVICE || 'atoms3r', basePath = process.env.M5_PUBLIC_BASE_PATH || '/showcase/';
const clockDivisor = process.env.M5_QEMU_CLOCK_DIVISOR ? Number(process.env.M5_QEMU_CLOCK_DIVISOR) : undefined;
const diagnostic = process.env.M5_QEMU_FRAME_DIAGNOSTIC === '1';
const publicUI = process.env.M5_PUBLIC_UI === '1';
assert.ok(!publicUI || clockDivisor === undefined, 'public UI validation uses the exported default clock');
assert.ok(clockDivisor === undefined || [1, 8].includes(clockDivisor), 'candidate clock override must be explicit 1 or 8');
const output = resolve(process.env.M5_PUBLIC_QEMU_OUT || resolve(repo, '.work/public-qemu-board-' + device));
assert.ok(output.startsWith(resolve(repo, '.work') + '/'), 'raw guest evidence belongs in ignored .work');
await mkdir(output, {recursive:false});
const modules = process.env.M5_WASM_NODE_MODULES || resolve(repo, 'platform/tests/node_modules');
const {chromium} = await import(pathToFileURL(resolve(modules, 'playwright/index.mjs')));
const checks = [], errors = [], requests = [];
const report = {kind:'browser-local-qemu-board-acceptance', device, public_ui:publicUI, started_at:new Date().toISOString(), checks, errors, requests};
const mime = {'.html':'text/html', '.js':'text/javascript', '.mjs':'text/javascript', '.json':'application/json', '.wasm':'application/wasm', '.css':'text/css', '.svg':'image/svg+xml', '.png':'image/png', '.webp':'image/webp', '.woff2':'font/woff2'};
let server, browser, page;
function check(name, ok, details) { checks.push({name, ok, details}); assert.ok(ok, name); console.log(name); }
async function guest(kind, predicate = () => true, timeout = 180000) {
  const until = Date.now() + timeout;
  while (Date.now() < until) {
    const state = await page.evaluate(() => {
      const banner = document.querySelector('#errorBanner');
      return {serial:globalThis.boardRun?.serial || '', errors:[...(globalThis.boardRun?.errors || []),
        ...(banner && !banner.hidden && banner.textContent ? [banner.textContent] : [])]};
    });
    if (state.errors.length) throw new Error(state.errors.join('\n'));
    if (state.serial.includes('Traceback (most recent call last):')) throw new Error(`Guest Python traceback before ${kind}`);
    const events = state.serial.split('\n').filter(line => line.startsWith('M5_BROWSER_PROBE ')).flatMap(line => {try {return [JSON.parse(line.slice(17))];} catch {return [];}});
    const event = events.find(row => row.kind === kind && predicate(row)); if (event) return event;
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error(`Guest ${kind} timed out`);
}
try {
  report.provenance = await capturePublicQemuProvenance({repo, site, testScript:'platform/tests/test_public_qemu_board_guest.mjs'});
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
  browser = await chromium.launch({headless:true, ...(process.env.M5_WASM_CHROME ? {executablePath:process.env.M5_WASM_CHROME} : {}), args:['--enable-webgl', '--use-gl=angle', '--use-angle=swiftshader']}); report.browser = browser.version();
  page = await browser.newPage({viewport:{width:1200,height:900}});
  await page.route(url => [8787,8830].includes(Number(url.port)) || /\/api\/v1(?:\/|$)/.test(url.pathname), route => route.abort('blockedbyclient'));
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
    const admission = {publication_eligible:config.publication_eligible, allow_candidate_profiles:allowCandidateProfiles,
      candidate_profiles:selected, exported_profiles:registry.profiles.map(row => ({device:row.deviceId, admission:row.admission}))};
    if (publicUI) {
      // Observe the actual public controller and newly selected model shell.
      // This wraps their constructors/start path without replacing any input,
      // serial, pixels, firmware composition or production event callbacks.
      const {ModelDeviceShell} = await import(new URL('platform/web/model-shell.js?v=20261026h', origin));
      const create = ModelDeviceShell.create;
      ModelDeviceShell.create = async function(...args) {
        const shell = await create.apply(this, args);
        if (args[1].id === device) globalThis.boardUiShell = shell;
        return shell;
      };
      const start = PublicQemuRuntime.prototype.start;
      PublicQemuRuntime.prototype.start = function(...args) {
        if (args[0].device === device) {
          const runtime = this, observedErrors = [], uiInputs = [], onError = this.onError, input = this.input;
          this.onError = error => { observedErrors.push(error.message); onError(error); };
          this.input = function(event) { uiInputs.push(structuredClone(event)); return input.call(this, event); };
          globalThis.boardRun = {profile, runtime, errors:observedErrors, uiInputs,
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
    await page.locator(`[data-device-id="${device}"]`).click();
    await page.waitForFunction(id => document.querySelector('#deviceMount')?.dataset.deviceId === id
      && globalThis.boardUiShell?.device.id === id, device, {timeout:45000});
    await page.locator('.advanced-options > summary').click();
    await page.locator('#runtimeMode').selectOption('browser');
    await page.locator('input[name="firmwareSource"][value="reference"]').check();
    check('public-ui-selected-board-reference', await page.locator('#referenceTitle').textContent().then(text => text.includes('屏幕与输入示例')));
    await page.locator('#startBtn').click();
  }
  const ready = await guest('ready');
  const dimensions = await page.evaluate(() => boardRun.profile.display);
  check('same-guest-ready-and-display', ready.device === device && ready.width === dimensions.width && ready.height === dimensions.height, ready);
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
  await page.waitForFunction(() => {
    const frame = boardRun.frame; if (!frame || new Set(frame.pixels).size <= 3) return false;
    let red = 0; for (let at = 0; at < frame.pixels.length; at += 2) if (frame.pixels[at] === 0 && frame.pixels[at + 1] === 0xf8) red++;
    return red === 64;
  }, {}, {timeout:30000});
  const marker = await page.evaluate(() => {
    const frame = boardRun.frame, pixels = [];
    for (let at = 0; at < frame.pixels.length; at += 2) if (frame.pixels[at] === 0 && frame.pixels[at + 1] === 0xf8) pixels.push(at / 2);
    boardRun.markerPixels = pixels;
    const x = pixels.map(at => at % frame.width), y = pixels.map(at => Math.floor(at / frame.width));
    return {x1:Math.min(...x), y1:Math.min(...y), x2:Math.max(...x), y2:Math.max(...y), count:pixels.length, source:frame.source,
      sourceSequence:frame.sourceSequence, sourceUpdates:frame.sourceUpdates};
  });
  check('complete-native-red-marker', marker.count === 64 && marker.x2 - marker.x1 === 7 && marker.y2 - marker.y1 === 7, marker);
  if (publicUI) {
    await page.waitForFunction(() => globalThis.boardUiShell?.frameSeq > 0
      && Number(document.querySelector('#deviceMount').dataset.frameSequence) > 0, {}, {timeout:30000});
    await page.locator('#nativeScreenBtn').click();
    check('public-ui-3d-and-visible-native-frame', await page.evaluate(() => {
      const canvas = document.querySelector('#rawFrameCanvas');
      return boardUiShell.model && boardUiShell.frameSeq > 0 && !document.querySelector('#rawFramePanel').hidden
        && canvas.width === boardRun.frame.width && canvas.height === boardRun.frame.height
        && new Set(canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data).size > 8;
    }));
    if (!await page.evaluate(() => boardRun.profile.inputs.touch)) {
      await page.locator('#rawFrameCanvas').click();
      await page.waitForTimeout(250);
      check('non-touch-screen-click-does-not-send-touch-or-show-error', await page.evaluate(() =>
        !boardRun.uiInputs.some(event => event.type === 'touch') && document.querySelector('#errorBanner').hidden));
    }
  }
  report.display_coordinate_observation = {guest_marker:{x:2,y:2,width:8,height:8}, frame_marker:marker,
    offset_x:marker.x1 - 2, offset_y:marker.y1 - 2, exact_guest_coordinates:marker.x1 === 2 && marker.y1 === 2,
    scope:'Observed firmware/model calibration only; a nonzero offset remains a separate display-model boundary.'};
  const first = await page.evaluate(() => boardRun.runtime.evidence());
  await writeFile(resolve(output, 'running-before-input.json'), JSON.stringify(first, null, 2) + '\n');
  check('hash-pinned-composed-firmware', first.receipt.firmwareSha256 === await page.evaluate(() => boardRun.profile.fixture.firmwareSHA256), first.receipt);
  const expectedProfile = await page.evaluate(() => ({id:boardRun.profile.profile, clockDivisor:boardRun.profile.clockDivisor}));
  check('exported-default-clock-profile', first.receipt.clockDivisor === (clockDivisor ?? expectedProfile.clockDivisor)
    && (clockDivisor !== undefined || first.receipt.profile === expectedProfile.id), first.receipt);
  if (publicUI && await page.evaluate(() => boardRun.profile.inputs.touch)) {
    const box = await page.locator('#rawFrameCanvas').boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.mouse.down();
  } else if (publicUI) {
    const key = await page.evaluate(() => {
      const target = boardRun.profile.deviceId === 'atoms3r' ? 'button' : 'btnA';
      return Object.entries(boardUiShell.model.keymap).find(([,path]) => path === target)?.[0];
    });
    assert.ok(key, 'actual 3D button must expose a focused keyboard binding'); report.input_keyboard = key;
    await page.locator('#deviceMount .three-device-stage canvas').focus(); await page.keyboard.down(key);
  } else await page.evaluate(async () => {
    const id = Object.keys(boardRun.profile.inputs.buttons)[0];
    const {width,height} = boardRun.profile.display;
    await boardRun.runtime.input(boardRun.profile.inputs.touch ? {type:'touch', x:Math.floor(width / 2), y:Math.floor(height / 2), down:true} : {type:'button', id, down:true});
  });
  check('guest-button-counter', (await guest('count', row => row.count === 1, 30000)).count === 1);
  if (publicUI && await page.evaluate(() => boardRun.profile.inputs.touch)) await page.mouse.up();
  else if (publicUI) await page.keyboard.up(report.input_keyboard);
  else await page.evaluate(() => {
    const {width,height} = boardRun.profile.display;
    return boardRun.runtime.input(boardRun.profile.inputs.touch ? {type:'touch', x:Math.floor(width / 2), y:Math.floor(height / 2), down:false}
      : {type:'button', id:Object.keys(boardRun.profile.inputs.buttons)[0], down:false});
  });
  await guest('released', () => true, 30000); check('guest-button-release', true);
  await page.waitForFunction(() => {
    const f = boardRun.frame;
    if (!boardRun.markerPixels.every(at => f.pixels[at * 2] === 0xe0 && f.pixels[at * 2 + 1] === 0x07)) return false;
    for (let at = 0; at < f.pixels.length; at += 2) if (f.pixels[at] === 0 && f.pixels[at + 1] === 0xf8) return false;
    return true;
  }, {}, {timeout:15000}); check('controller-input-changes-native-frame-marker', true);
  check('unsupported-button-fails-closed', await page.evaluate(async () => {try {await boardRun.runtime.input({type:'button', id:'unmapped-control', down:true}); return false;} catch {return true;}}));
  await page.screenshot({path:resolve(output, 'native-frame.png'), fullPage:true});
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
  const running = await page.evaluate(() => boardRun.runtime.evidence()); await writeFile(resolve(output, 'running-after-input.json'), JSON.stringify(running, null, 2) + '\n');
  if (publicUI) report.public_ui_inputs = await page.evaluate(() => boardRun.uiInputs);
  if (publicUI) { await page.locator('#stopBtn').click(); await page.waitForFunction(() => document.querySelector('#runtimeStatus').dataset.status === 'stopped', {}, {timeout:30000}); }
  else await page.evaluate(() => boardRun.runtime.stop());
  const stopped = await page.evaluate(() => boardRun.runtime.evidence()); await writeFile(resolve(output, 'stopped.json'), JSON.stringify(stopped, null, 2) + '\n');
  check('clean-guest-stop-and-worker-disposal', stopped.cleanup?.gracefulExit && stopped.cleanup?.exitCode === 0
    && stopped.cleanup?.workersAtExit === 0 && stopped.cleanup?.disposal?.workersTerminatedByDispose === 0
    && stopped.cleanup?.disposal?.workersRemaining === 0 && stopped.cleanup?.explicitWorkerDisposal && stopped.cleanup?.iframeRemoved, stopped.cleanup);
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
