// Opt-in real guest acceptance. Each run owns a dedicated Device Service lease,
// retains its ZIP before purge=0 stop, and compares only the frame controller.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createHash, randomBytes} from 'node:crypto';
import {spawn, execFileSync} from 'node:child_process';
import {createWriteStream} from 'node:fs';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname, extname, sep} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';

if (!process.argv.includes('--execute')) {
  console.log('NOT RUN: --execute requires M5_NATIVE_QEMU, M5_NATIVE_ROMS, M5_NATIVE_ESP_EMU, M5_NATIVE_DANCE, M5_NATIVE_CORES3; optional M5_NATIVE_NODE_MODULES/PYTHONPATH/OUT');
  process.exit(0);
}
const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const out = resolve(process.env.M5_NATIVE_OUT || resolve(repo, '.work/native-performance'));
const python = process.env.M5_NATIVE_PYTHON || 'python3';
const baselineRef = process.env.M5_NATIVE_BASELINE || '3691870c';
assert.match(baselineRef, /^[a-f0-9]{7,40}$/);
const sampleMs = Number(process.env.M5_NATIVE_SAMPLE_MS || 12000);
assert.ok(Number.isFinite(sampleMs) && sampleMs >= 5000 && sampleMs <= 60000);
for (const name of ['M5_NATIVE_QEMU', 'M5_NATIVE_ROMS', 'M5_NATIVE_ESP_EMU', 'M5_NATIVE_DANCE', 'M5_NATIVE_CORES3']) assert.ok(process.env[name], `${name} is required`);
await mkdir(dirname(out), {recursive: true});
// A failed round is evidence too. Never reuse or truncate an earlier archive.
await mkdir(out, {mode: 0o700});
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const controllerPath = 'platform/web/public-session-controller.js';
const baselineController = execFileSync('git', ['show', `${baselineRef}:${controllerPath}`], {cwd: repo});
const currentController = await readFile(resolve(repo, controllerPath));
const token = randomBytes(32).toString('hex'), tokenPath = resolve(out, 'control-token.private');
await writeFile(tokenPath, token, {mode: 0o600});
const report = {schema_version: 1, category: 'native-device-service-frame-controller-performance',
  validation: 'virtual-device validation', hardware_validation: 'NOT RUN', status: 'FAIL',
  startup_comparison: 'NOT RUN: Flash preparation/cache warmth is uncontrolled between the two runs.',
  baseline_ref: baselineRef, sources: {[controllerPath]: {before: sha(baselineController), after: sha(currentController)}},
  baseline_commit: execFileSync('git', ['rev-parse', baselineRef], {cwd: repo, encoding: 'utf8'}).trim(),
  native_runtime_sha256: sha(await readFile(process.env.M5_NATIVE_QEMU)), runs: [], errors: []};
for (const path of ['platform/tests/test_public_native_performance.mjs', 'platform/web/public.js', 'platform/web/public-config.js',
  'platform/web/public-firmware.js', 'platform/web/public-qemu-profiles.js', 'platform/web/qemu-browser-profiles.json',
  'platform/web/public-service.js', 'platform/tools/device_service.py', 'platform/tools/serve.py']) report.sources[path] = sha(await readFile(resolve(repo, path)));
// Browser availability is enabled deliberately so auto must choose between two
// real advertised lanes. No browser engine is started by this native test.
const siteConfig = {schema_version:1, service_url:'', max_firmware_bytes:64*1024*1024,
  browser_board_execution:true, browser_runtime_engine:'qemu-wasm', publication_eligible:true};
report.site_config = siteConfig;
const cases = [
  {device: 'stackchan', firmware: resolve(process.env.M5_NATIVE_DANCE), ready: 'StackChan auto-dance started'},
  {device: 'cores3', firmware: resolve(process.env.M5_NATIVE_CORES3), ready: '"kind": "ready"'},
];
for (const c of cases) {c.inputSHA = sha(await readFile(c.firmware));}
let phase = 'before', browser, backend, serviceUrl, siteServer, activeId, stopped = true;
const backendLog = createWriteStream(resolve(out, 'service.log'));
async function waitFor(check, timeout = 90000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {if (await check()) return; await delay(100);}
  throw new Error(`Native service condition exceeded ${timeout}ms`);
}
async function api(path, method = 'GET', body) {
  const response = await fetch(`${serviceUrl}/api/v1/${path}`, {method,
    headers: {Authorization: `Bearer ${token}`, ...(body ? {'Content-Type': 'application/json'} : {})},
    ...(body ? {body: JSON.stringify(body)} : {}), signal: AbortSignal.timeout(30000)});
  const bytes = Buffer.from(await response.arrayBuffer());
  assert.ok(response.ok, `${method} ${path}: ${response.status} ${bytes.toString().slice(0, 120)}`);
  return path.includes('frame.png') || path.endsWith('/evidence') ? bytes : JSON.parse(bytes);
}
function cpuSeconds(pid) {
  const value = execFileSync('ps', ['-p', String(pid), '-o', 'time='], {encoding: 'utf8'}).trim();
  const parts = value.split(':').map(Number);
  assert.ok(parts.length >= 2 && parts.every(Number.isFinite));
  return parts.reduce((seconds, part) => seconds * 60 + part, 0);
}
const mime = {'.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.jpg': 'image/jpeg'};
try {
  const portProbe = createServer();
  await new Promise(done => portProbe.listen(0, '127.0.0.1', done));
  const port = portProbe.address().port;
  await new Promise(done => portProbe.close(done));
  assert.ok(![8787, 8830].includes(port));
  serviceUrl = `http://127.0.0.1:${port}`;
  backend = spawn(python, ['platform/tools/serve.py', String(port), '--state-dir', resolve(out, 'service-state'), '--api-token-file', tokenPath, '--max-sessions', '1', '--max-per-device', '1'], {
    cwd: repo, env: {...process.env, M5_QEMU_XTENSA: process.env.M5_NATIVE_QEMU,
      M5_QEMU_XTENSA_ROM_DIR: process.env.M5_NATIVE_ROMS, M5_SERVICE_ESP_EMU: process.env.M5_NATIVE_ESP_EMU}, stdio: ['ignore', 'pipe', 'pipe']});
  backend.stdout.pipe(backendLog); backend.stderr.pipe(backendLog);
  await waitFor(async () => {try {return (await api('health')).capacity.active_sessions === 0;} catch {return false;}}, 20000);
  console.log('NATIVE_PERF: dedicated authenticated service ready');
  siteServer = createServer(async (request, response) => {
    try {
      response.setHeader('Cross-Origin-Opener-Policy','same-origin');
      response.setHeader('Cross-Origin-Embedder-Policy','require-corp');
      response.setHeader('Cross-Origin-Resource-Policy','same-origin');
      const pathname = new URL(request.url, 'http://localhost').pathname;
      if (pathname === '/favicon.ico') {response.writeHead(204).end(); return;}
      const file = resolve(repo, '.' + (pathname === '/' ? '/platform/web/index.html' : decodeURIComponent(pathname)));
      assert.ok(['platform/web', 'devices'].some(prefix => file.startsWith(resolve(repo, prefix) + sep)));
      let bytes = file === resolve(repo, 'platform/web/site-config.json') ? Buffer.from(JSON.stringify(siteConfig))
        : file === resolve(repo, controllerPath) ? (phase === 'before' ? baselineController : currentController) : await readFile(file);
      if (file === resolve(repo, 'platform/web/public.js')) bytes = Buffer.concat([bytes, Buffer.from('\nwindow.__nativeWorkbench={state,browserProfile,lane};\n')]);
      response.writeHead(200, {'Content-Type': mime[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store'}); response.end(bytes);
    } catch {response.writeHead(404).end();}
  });
  await new Promise(done => siteServer.listen(0, '127.0.0.1', done));
  const siteUrl = `http://127.0.0.1:${siteServer.address().port}`;
  assert.ok(![8787, 8830].includes(siteServer.address().port));
  const modules = process.env.M5_NATIVE_NODE_MODULES || resolve(repo, 'platform/tests/node_modules');
  const {chromium} = await import(pathToFileURL(resolve(modules, 'playwright/index.mjs')));
  browser = await chromium.launch({headless: true, executablePath: process.env.M5_NATIVE_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', args: ['--enable-gpu', '--enable-webgl', '--use-gl=angle', '--use-angle=metal']});
  report.browser = browser.version();
  const browserCDP = await browser.newBrowserCDPSession();
  const system = await browserCDP.send('SystemInfo.getInfo');
  report.browser_gpu = {devices: system.gpu.devices, featureStatus: system.gpu.featureStatus};
  await browserCDP.detach();
  for (const c of cases) for (const version of ['before', 'after']) {
    phase = version;
    const dir = resolve(out, `${c.device}-${version}`); await mkdir(dir, {recursive: true});
    const mode = c.device === 'stackchan' && phase === 'after' ? 'auto' : 'service';
    const row = {device: c.device, phase, selected_mode:mode, input_firmware_sha256: c.inputSHA,
      controller_sha256: phase === 'before' ? sha(baselineController) : sha(currentController),
      http: [], browser_runtime_requests:[], page_errors: [], checks: {}};
    report.runs.push(row);
    const page = await browser.newPage({viewport: {width: 1440, height: 1080}});
    page.on('pageerror', error => row.page_errors.push(error.message));
    page.on('request', request => {
      const path = new URL(request.url()).pathname;
      if(path.startsWith('/platform/runtime/qemu/'))row.browser_runtime_requests.push(path);
    });
    page.on('response', response => {
      if (!response.url().startsWith(serviceUrl + '/api/v1/')) return;
      const u = new URL(response.url()), headers = response.headers();
      row.http.push({method: response.request().method(), path: u.pathname, query: u.search, status: response.status(), bytes: Number(headers['content-length'] || 0), frame_sha256: headers['x-frame-sha256'] || null, at_ms: Date.now()});
    });
    await page.goto(`${siteUrl}/?device=${c.device}&mode=${mode}&autostart=0`, {waitUntil: 'domcontentloaded'});
    await page.waitForFunction(device => window.__nativeWorkbench?.state.selected?.id === device && window.__nativeWorkbench.state.shell, c.device);
    row.webgl = await page.evaluate(() => {
      const gl = window.__nativeWorkbench.state.shell.viewer?.renderer?.getContext();
      if (!gl) return {scope: 'actual-workbench-model-canvas', renderer: null};
      const info = gl.getExtension('WEBGL_debug_renderer_info');
      return {scope: 'actual-workbench-model-canvas', renderer: info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
        vendor: info ? gl.getParameter(info.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR), version: gl.getParameter(gl.VERSION)};
    });
    assert.ok(row.webgl.renderer, 'Read the actual workbench model renderer before starting the guest');
    assert.doesNotMatch(row.webgl.renderer, /swiftshader|llvmpipe|softpipe|lavapipe|software|basic render|\bwarp\b/i, 'Hardware comparison rejects a software renderer');
    await page.locator('#serviceConnection').evaluate(node => {node.open = true;});
    await page.fill('#serviceUrl', serviceUrl); await page.fill('#serviceToken', token); await page.click('#connectServiceBtn');
    await page.waitForFunction(device => window.__nativeWorkbench.state.serviceDevices.some(row => row.device_id === device && row.creatable), c.device);
    row.routing = await page.evaluate(() => {
      const w=window.__nativeWorkbench,select=document.querySelector('#runtimeMode'),mode=select.value;
      const selected=w.lane(),browserAvailable=!!w.browserProfile(w.state.selected.id);
      select.value='browser';const explicitBrowser=w.lane();select.value=mode;
      return {mode,selected_lane:selected,browser_available:browserAvailable,explicit_browser_lane:explicitBrowser,
        cross_origin_isolated:crossOriginIsolated,service_connected:!!w.state.service};
    });
    assert.equal(row.routing.mode,mode);assert.equal(row.routing.selected_lane,'service');
    assert.equal(row.routing.browser_available,true);assert.equal(row.routing.explicit_browser_lane,'browser');
    assert.equal(row.routing.cross_origin_isolated,true);assert.equal(row.routing.service_connected,true);
    row.checks.native_route_with_browser_available = true;
    await page.evaluate(async () => {
      const {PublicSessionController} = await import('/platform/web/public-session-controller.js');
      const start = PublicSessionController.prototype.start;
      window.__nativePerf = {frames: [], serial: '', states: [], outputs: [], outputAvailability: [], poses: []};
      const pose = () => {
        const shell = window.__nativeWorkbench.state.shell, mount = document.querySelector('#deviceMount');
        return {at_ms: performance.now(), yaw: shell.model?.find('yaw', 'joint')?.getState(), pitch: shell.model?.find('pitch', 'joint')?.getState(),
          dom: {yawTicks: mount.dataset.servoYawTicks ?? null, pitchTicks: mount.dataset.servoPitchTicks ?? null,
            packets: mount.dataset.servoPackets ?? null, known: mount.dataset.outputKnown ?? null, source: mount.dataset.outputSource ?? null}};
      };
      window.__nativePerfStopTrace = window.__nativeWorkbench.state.selected.id === 'stackchan'
        ? window.__nativeWorkbench.state.shell.viewer.on('render', () => {
          if (window.__nativePerf.controller?.current?.state === 'running') window.__nativePerf.poses.push(pose());
        }) : () => {};
      PublicSessionController.prototype.start = function (...args) {
        const p = window.__nativePerf, frame = this.onFrame, serial = this.onSerial, state = this.onState;
        const output = this.onDeviceState || (() => {}), outputAvailability = this.onOutputState || (() => {});
        this.onFrame = value => {frame(value); p.frames.push({at_ms: performance.now(), sequence: value.sequence, etag: this.etag, applied: value.applied});};
        this.onSerial = value => {serial(value); p.serial += value;};
        this.onState = value => {state(value); p.states.push({at_ms: performance.now(), status: value.status, frameReady: value.frameReady});};
        this.onDeviceState = value => {output(value); p.outputs.push({state: structuredClone(value), observation: structuredClone(this.outputObservation), ...pose()});};
        this.onOutputState = value => {outputAvailability(value); p.outputAvailability.push(value);};
        p.controller = this; p.started_ms = performance.now(); return start.apply(this, args);
      };
    });
    await page.locator('input[name="firmwareSource"][value="local"]').check();
    await page.locator('#firmwareFile').setInputFiles(c.firmware);
    await page.locator('#firmwareSha').evaluate(node => {for (let parent = node.parentElement; parent; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;});
    await page.fill('#firmwareSha', c.inputSHA); await page.click('#startBtn');
    await page.waitForFunction(() => window.__nativePerf.controller?.current?.session_id, {}, {timeout: 90000});
    activeId = await page.evaluate(() => window.__nativePerf.controller.current.session_id); stopped = false;
    row.session_id = activeId;
    row.actual_controller = await page.evaluate(async () => {
      const {PublicSessionController}=await import('/platform/web/public-session-controller.js');
      const w=window.__nativeWorkbench;
      return {run_kind:w.state.run.kind,constructor:w.state.run.controller.constructor.name,
        is_public_session_controller:w.state.run.controller instanceof PublicSessionController,
        is_instrumented_owner:w.state.run.controller===window.__nativePerf.controller};
    });
    assert.equal(row.actual_controller.run_kind,'service');assert.equal(row.actual_controller.is_public_session_controller,true);
    assert.equal(row.actual_controller.is_instrumented_owner,true);row.checks.same_native_controller_path = true;
    await page.waitForFunction(marker => window.__nativePerf.serial.includes(marker) && window.__nativePerf.controller.frameReady, c.ready, {timeout: 120000});
    const session = await api(`sessions/${activeId}`);
    assert.equal(session.state, 'running'); assert.ok(Number.isSafeInteger(session.pid) && session.pid > 0);
    row.firmware_sha256 = session.firmware_sha256; row.runtime = session.runtime; row.pid = session.pid;
    row.actual_qemu_command = execFileSync('ps', ['-p', String(session.pid), '-o', 'command='], {encoding: 'utf8'}).trim();
    assert.equal(session.runtime,'qemu');assert.ok(row.actual_qemu_command.startsWith(process.env.M5_NATIVE_QEMU+' '));
    assert.doesNotMatch(row.actual_qemu_command,/(?:^|\s)-icount(?:=|\s|$)|vm-clock-divisor/);
    row.checks.native_qemu_normal_launch = true;
    assert.equal(session.firmware_sha256,c.inputSHA);row.checks.exact_firmware_sha = true;
    row.startup_scope = 'controller start after browser firmware upload/intake';
    row.checks.application_serial_and_frame = true;
    if (c.device === 'stackchan') row.servo_before = await api(`sessions/${activeId}/qom?path=${encodeURIComponent('/machine/scs_servo')}&property=state`);
    const cpuBefore = {guest: cpuSeconds(session.pid), service: cpuSeconds(backend.pid)}, wallStart = performance.now(), sampleWallStart = Date.now();
    await page.evaluate(() => {window.__nativePerf.sample_start_ms = performance.now();});
    console.log(`NATIVE_PERF: ${c.device} ${phase} sampling`);
    await delay(sampleMs);
    const observation = await page.evaluate(() => ({...window.__nativePerf, controller: undefined, sample_end_ms: performance.now()}));
    const seconds = (performance.now() - wallStart) / 1000;
    row.cpu = {guest_percent_one_core: (cpuSeconds(session.pid) - cpuBefore.guest) / seconds * 100, service_percent_one_core: (cpuSeconds(backend.pid) - cpuBefore.service) / seconds * 100};
    const frames = observation.frames.filter(frame => frame.at_ms >= observation.sample_start_ms && frame.at_ms <= observation.sample_end_ms && frame.applied);
    const sampleSeconds = (observation.sample_end_ms - observation.sample_start_ms) / 1000;
    const payloads = row.http.filter(r => r.path.endsWith('/frame.png') && r.at_ms >= sampleWallStart);
    row.measurement = {sample_seconds: sampleSeconds, applied_frames: frames.length, delivered_fps: frames.length / sampleSeconds,
      frame_payload_bytes: payloads.reduce((bytes, r) => bytes + r.bytes, 0), frame_requests: payloads.length,
      frame_not_modified: payloads.filter(r => r.status === 304).length, first_frame_ms: observation.frames[0]?.at_ms - observation.started_ms};
    row.checks.display_updates = frames.length >= 3;
    if (c.device === 'stackchan') {
      const outputs = observation.outputs.filter(o => o.at_ms >= observation.sample_start_ms && o.at_ms <= observation.sample_end_ms);
      const poses = observation.poses.filter(o => o.at_ms >= observation.sample_start_ms && o.at_ms <= observation.sample_end_ms);
      const range = values => values.length ? [Math.min(...values), Math.max(...values)] : null;
      row.servo_model = {controller_observations: outputs.length, rendered_pose_samples: poses.length,
        distinct_raw_yaw_positions: new Set(outputs.map(o => o.state.servos[0].present_position)).size,
        distinct_raw_pitch_positions: new Set(outputs.map(o => o.state.servos[1].present_position)).size,
        raw_yaw_range: range(outputs.map(o => o.state.servos[0].present_position)), raw_pitch_range: range(outputs.map(o => o.state.servos[1].present_position)),
        distinct_yaw_poses: new Set(poses.map(p => p.yaw?.angleDeg?.toFixed(3))).size,
        distinct_pitch_poses: new Set(poses.map(p => p.pitch?.angleDeg?.toFixed(3))).size,
        actual_intermediate_rendered_poses: poses.filter(p => p.yaw?.transitioning && Math.abs(p.yaw.angleDeg - p.yaw.targetAngleDeg) > 0.01
          || p.pitch?.transitioning && Math.abs(p.pitch.angleDeg - p.pitch.targetAngleDeg) > 0.01).length,
        yaw_visual_range: range(poses.map(p => p.yaw?.angleDeg).filter(Number.isFinite)), pitch_visual_range: range(poses.map(p => p.pitch?.angleDeg).filter(Number.isFinite)),
        source: outputs.at(-1)?.observation?.transport ?? null};
      if (phase === 'after') {
        row.checks.native_servo_readback = outputs.length >= 5 && outputs.every(o => o.observation?.session_id === activeId
          && o.observation.firmware_sha256 === session.firmware_sha256 && o.observation.transport === 'native-service-qom-v1');
        row.checks.real_controller_positions_change = row.servo_model.distinct_raw_yaw_positions >= 3 && row.servo_model.distinct_raw_pitch_positions >= 3;
        row.checks.raw_dom_matches_controller = outputs.every(o => Number(o.dom.yawTicks) === o.state.servos[0].present_position
          && Number(o.dom.pitchTicks) === o.state.servos[1].present_position && Number(o.dom.packets) === o.state.packets && o.dom.source === 'native-service-qom-v1');
        row.checks.model_targets_match_present = outputs.every(o => Math.abs(o.yaw.targetAngleDeg - (o.state.servos[0].present_position - 460) * 5 / 16) < 1e-9
          && Math.abs(o.pitch.targetAngleDeg - Math.max(0, Math.min(90, (o.state.servos[1].present_position - 620) * 5 / 16))) < 1e-9);
        row.checks.actual_rendered_joint_motion = row.servo_model.distinct_yaw_poses >= 20 && row.servo_model.distinct_pitch_poses >= 20
          && row.servo_model.actual_intermediate_rendered_poses >= 20;
      } else {
        row.checks.baseline_missing_servo_bridge_reproduced = outputs.length === 0 && row.servo_model.distinct_yaw_poses === 1 && row.servo_model.distinct_pitch_poses === 1;
      }
    }
    row.input = await page.evaluate(async () => {
      const p = window.__nativePerf, at = performance.now();
      const result = await p.controller.input({kind: 'longpress', x: 160, y: 184, hold_seconds: 0.4});
      return {result, at_ms: at};
    });
    if (c.device === 'cores3') {
      await page.waitForFunction(() => window.__nativePerf.serial.includes('"kind": "touch_clicked"'), {}, {timeout: 20000});
      row.checks.guest_touch_callback = true;
    } else {
      row.servo_after = await api(`sessions/${activeId}/qom?path=${encodeURIComponent('/machine/scs_servo')}&property=state`);
      row.checks.servo_packets = row.servo_after.value?.source === 'qemu-uart1-scs-controller' && row.servo_after.value.packets > 0;
      row.input_scope = 'touch controller protocol only; this dance application has no touch-response assertion';
    }
    await writeFile(resolve(dir, 'frame.png'), await api(`sessions/${activeId}/frame.png`));
    await page.screenshot({path: resolve(dir, 'workbench.png')});
    await page.click('#stopBtn');
    await page.waitForFunction(() => window.__nativePerf.controller.current === null, {}, {timeout: 60000});
    const outputCountAtStop = await page.evaluate(() => {window.__nativePerfStopTrace(); return window.__nativePerf.outputs.length;});
    await delay(100);
    assert.equal(await page.evaluate(() => window.__nativePerf.outputs.length), outputCountAtStop, 'late native replies cannot republish a stopped model pose');
    const zip = await page.evaluate(async () => Array.from(new Uint8Array(await window.__nativePerf.controller.lastEvidence.arrayBuffer())));
    await writeFile(resolve(dir, 'evidence.zip'), Buffer.from(zip));
    assert.equal(Buffer.from(zip).subarray(0, 2).toString(), 'PK');
    row.evidence = JSON.parse(execFileSync(python, ['-c',
      'import hashlib,json,sys,zipfile;z=zipfile.ZipFile(sys.argv[1]);m=json.loads(z.read("manifest.json"));rows=m["files"];assert all(len(z.read(p))==r["size"] and hashlib.sha256(z.read(p)).hexdigest()==r["sha256"] for p,r in rows.items());print(json.dumps({"verified_files":len(rows),"session_id":m["session"]["session_id"]}))', resolve(dir, 'evidence.zip')], {encoding: 'utf8'}));
    assert.equal(row.evidence.session_id, activeId);
    const order = row.http, zipAt = order.findIndex(e => e.path.endsWith('/evidence') && e.status === 200), stopAt = order.findIndex(e => e.method === 'DELETE' && e.path.endsWith(activeId));
    assert.ok(zipAt >= 0 && stopAt > zipAt); assert.match(order[stopAt].query, /purge=0/);
    row.evidence_sha256 = sha(Buffer.from(zip)); row.checks.evidence_before_stop = true;
    const history = await api(`sessions/${activeId}`);
    assert.equal(history.state, 'stopped'); assert.equal(history.worker?.lease_active, false);
    await writeFile(resolve(dir, 'history.json'), JSON.stringify(history, null, 2));
    await writeFile(resolve(dir, 'retained-frame.png'), await api(`sessions/${activeId}/frame.png`));
    await waitFor(() => {try {process.kill(session.pid, 0); return false;} catch (e) {if (e.code === 'ESRCH') return true; throw e;}}, 10000);
    row.checks.guest_reaped_history_retained = true; stopped = true;
    assert.equal((await api('health')).capacity.active_sessions, 0);
    const final = await page.evaluate(() => ({serial: window.__nativePerf.serial, frames: window.__nativePerf.frames, states: window.__nativePerf.states}));
    await writeFile(resolve(dir, 'observations.json'), JSON.stringify({...observation, ...final}, null, 2));
    row.serial_sha256 = sha(Buffer.from(final.serial));
    row.checks.no_browser_qemu_boot = row.browser_runtime_requests.length === 0;
    row.status = Object.values(row.checks).every(Boolean) && row.page_errors.length === 0 ? 'PASS' : 'FAIL';
    console.log(JSON.stringify({device: c.device, phase, status: row.status, measurement: row.measurement, cpu: row.cpu}));
    await page.close();
  }
  for (const c of cases) assert.equal(report.runs.find(r => r.device === c.device && r.phase === 'before').firmware_sha256, report.runs.find(r => r.device === c.device && r.phase === 'after').firmware_sha256);
  report.status = report.runs.every(row => row.status === 'PASS') ? 'PASS' : 'FAIL';
} catch (error) {report.errors.push(error.stack || String(error)); throw error;}
finally {
  if (serviceUrl && backend && backend.exitCode === null && backend.signalCode === null) {
    try {
      // This listener started empty and is private to the harness. Recover even
      // an allocation whose browser receipt failed before activeId was known.
      const sessions = (await api('sessions')).sessions;
      for (const session of sessions.filter(s => !['stopped', 'failed'].includes(s.state) || s.worker?.lease_active)) {
        await writeFile(resolve(out, `cleanup-${session.session_id}-evidence.zip`), await api(`sessions/${session.session_id}/evidence`));
        await api(`sessions/${session.session_id}?purge=0`, 'DELETE');
        await waitFor(async () => {const s = await api(`sessions/${session.session_id}`); return ['stopped', 'failed'].includes(s.state) && s.worker?.lease_active === false;}, 10000);
      }
      assert.equal((await api('health')).capacity.active_sessions, 0);
    } catch (e) {report.errors.push(`cleanup: ${e.message}`);}
  }
  if (browser) await browser.close();
  if (siteServer) await new Promise(done => siteServer.close(done));
  if (backend) {
    backend.kill('SIGTERM');
    await Promise.race([new Promise(done => backend.once('exit', done)), delay(3000)]);
    if (backend.exitCode === null && backend.signalCode === null) backend.kill('SIGKILL');
  }
  backendLog.end();
  await writeFile(resolve(out, 'report.json'), JSON.stringify(report, null, 2));
}
