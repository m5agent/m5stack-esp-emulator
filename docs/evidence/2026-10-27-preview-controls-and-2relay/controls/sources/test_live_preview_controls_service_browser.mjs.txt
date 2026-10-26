// Offline plan by default. --execute alone authorizes this local virtual-device
// runner; it never launches QEMU directly or mutates physical hardware.
import assert from 'node:assert/strict';
import {createHash, randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const python = process.env.M5_PREVIEW_PYTHON || '/opt/miniconda3/bin/python3.12';
const helper = 'tests/units/preview_controls_probe.py';
const args = process.argv.slice(2), options = {device: 'cores3', execute: false};
const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) for (let i = 0; i < args.length; i += 1) {
  const arg = args[i];
  if (arg === '--execute') { assert.equal(options.execute, false); options.execute = true; }
  else if (['--device', '--out-dir', '--base-url', '--expected-runtime-sha256', '--token-file'].includes(arg)) {
    assert.ok(args[i + 1] && !args[i + 1].startsWith('--'), `Missing ${arg} value`);
    const key = arg.slice(2).replaceAll('-', '_'); assert.equal(Object.hasOwn(options, key) && key !== 'device', false, `Duplicate ${arg}`);
    options[key] = args[++i];
  } else throw new Error(`Unknown argument ${arg}`);
}
assert.ok(['cores3', 'atoms3r', 'sticks3', 'stopwatch'].includes(options.device), 'Unadmitted device');
const pure = (action, input = null) => JSON.parse(execFileSync(python, ['-B', helper, action, '--device', options.device],
  {cwd: root, encoding: 'utf8', input: input === null ? undefined : JSON.stringify(input), maxBuffer: 8 * 1024 * 1024}));
let plan;
if (isMain && !options.execute) {
  plan = pure('plan');
  console.log(JSON.stringify(plan, null, 2));
} else if (isMain) {
  plan = pure('plan');
  await execute();
}

function rememberOwned(state, receipt) {
  assert.match(receipt.preview_id || '', /^[0-9a-f]{32}$/);
  if (state.previewId) assert.equal(receipt.preview_id, state.previewId);
  state.previewId = receipt.preview_id;
  assert.match(receipt.owner_epoch || '', /^[0-9a-f]{32}$/);
  if (state.ownerEpoch) assert.equal(receipt.owner_epoch, state.ownerEpoch);
  state.ownerEpoch = receipt.owner_epoch;
  if (receipt.session_id) {
    if (state.sessionId) assert.equal(receipt.session_id, state.sessionId);
    state.sessionId = receipt.session_id;
  }
}

// The only replay is recovery of this one original creation intent. Run and
// Unit input mutations are never retried by these cleanup helpers.
export async function createOwnedPreview(state, intent, send) {
  state.creation = {intent: structuredClone(intent), outcome: 'unknown'};
  try {
    const receipt = await send('previews', 'POST', state.creation.intent.body, state.creation.intent.key);
    rememberOwned(state, receipt); state.creation.outcome = 'confirmed'; return receipt;
  } catch (error) {
    if (error.responseComplete && error.status >= 400 && error.status < 500 && error.status !== 408) state.creation.outcome = 'rejected';
    throw error;
  }
}

export async function closeOwnedPreview(state, {send, wait, captureZip, pidGone, verify}) {
  state.cleanupWarnings ||= [];
  if (!state.previewId && state.creation?.outcome === 'unknown') {
    const {body, key} = state.creation.intent;
    rememberOwned(state, await send('previews', 'POST', body, key));
    state.creation.recovered_for_cleanup = true;
  }
  if (!state.previewId) return null;
  try { rememberOwned(state, await send(`previews/${state.previewId}`)); }
  catch (error) { state.cleanupWarnings.push({step: 'preview-read', error: String(error)}); }
  assert.ok(state.ownerEpoch, 'Owned Preview epoch unavailable');
  if (state.sessionId && !state.session) {
    try { state.session = await send(`sessions/${state.sessionId}`); }
    catch (error) { state.cleanupWarnings.push({step: 'session-read', error: String(error)}); }
  }
  if (state.sessionId && !state.zipBeforeClose) {
    try { await captureZip(state.sessionId); state.zipBeforeClose = true; }
    catch (error) { state.cleanupWarnings.push({step: 'evidence-before-close', error: String(error)}); }
  }
  // Failed reads or ZIP capture must never skip release of the owned Preview.
  try { await send(`previews/${state.previewId}/close`, 'POST', {expected_owner_epoch: state.ownerEpoch}); }
  catch (error) { state.cleanupWarnings.push({step: 'close-receipt', error: String(error)}); }
  const closed = await wait(() => send(`previews/${state.previewId}`), value => value.state === 'closed', 120000);
  rememberOwned(state, closed);
  if (!state.sessionId) return {preview: closed, session_allocation: 'not published'};
  const stopped = await send(`sessions/${state.sessionId}`), capacity = await send('capacity');
  const evidence = {preview: closed, session: stopped, capacity, session_id: state.sessionId,
    pid_gone: Number.isInteger(state.session?.pid) && state.session.pid > 0 ? await pidGone(state.session.pid) : false,
    zip_before_close: state.zipBeforeClose === true};
  // The fallback still releases a late allocation; absent before-close PID/ZIP
  // evidence fails this contract instead of manufacturing a cleanup PASS.
  evidence.contract = verify(evidence); return evidence;
}

async function execute() {
  const base = (options.base_url || process.env.M5_DEVICE_SERVICE_URL || 'http://127.0.0.1:8787').replace(/\/$/, '');
  const parsed = new URL(base);
  assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(parsed.hostname) && !parsed.username && !parsed.password && parsed.pathname === '/', 'Local Device Service root required');
  const expectedRuntime = options.expected_runtime_sha256 || process.env.M5_EXPECTED_RUNTIME_SHA256;
  assert.match(expectedRuntime || '', /^[0-9a-f]{64}$/);
  const token = (await readFile(options.token_file || process.env.M5_CONTROL_TOKEN_FILE, 'utf8')).trim();
  assert.ok(token, 'Control token required');
  const output = resolve(options.out_dir || process.env.M5_PREVIEW_CONTROLS_OUT || `/tmp/m5-preview-controls-${options.device}-${Date.now()}`);
  await mkdir(output, {recursive: false});
  const sha = bytes => createHash('sha256').update(bytes).digest('hex');
  const sources = ['platform/tests/test_live_preview_controls_service_browser.mjs', helper, 'tests/units/test_preview_controls_probe.py',
    'platform/web/sessions.js', 'platform/web/sessions.html', 'platform/web/preview-client.js', 'platform/web/program-panel.js',
    'platform/web/unit-panel.js', 'platform/web/unit-visual-mappings.js', 'platform/web/model-shell.js', 'platform/tools/preview_service.py',
    'platform/tools/preview_store.py', 'platform/tools/device_service.py', 'platform/tools/program_packages.py', 'platform/tools/unit_runtime.py',
    'platform/units/runtime-profiles.json', 'platform/units/host-ports.json', 'tests/units/controls_probe/control_drivers/source-manifest.json'];
  const fingerprints = async () => Object.fromEntries(await Promise.all(sources.map(async path => [path, sha(await readFile(resolve(root, path)))])));
  const report = {schema_version: 1, category: 'virtual-device-managed-preview-hub-controls-web', status: 'FAIL', plan,
    hardware: 'NOT RUN', device_id: options.device, source_sha256: await fingerprints(), http: [], browser_http: [], page_errors: [], runs: [], observations: []};
  const save = (name, data) => writeFile(resolve(output, name), JSON.stringify(data, null, 2) + '\n');
  let browser, page, previewId, ownerEpoch, sessionId, session;
  const owned = {zipBeforeClose: false}, traffic = new Map();
  const browserTasks = [];
  async function api(path, method = 'GET', body = null, key = null) {
    const index = report.http.length, row = {path, method}; report.http.push(row);
    if (body !== null) await save(`http-${index}.request.json`, body);
    const response = await fetch(`${base}/api/v1/${path}`, {method, redirect: 'error', signal: AbortSignal.timeout(30000),
      headers: {Authorization: `Bearer ${token}`, ...(body === null ? {} : {'Content-Type': 'application/json'}), ...(key ? {'Idempotency-Key': key} : {})},
      ...(body === null ? {} : {body: JSON.stringify(body)})});
    const bytes = Buffer.from(await response.arrayBuffer());
    Object.assign(row, {status: response.status, sha256: sha(bytes), bytes: bytes.length, headers: Object.fromEntries(response.headers)});
    await writeFile(resolve(output, `http-${index}.response`), bytes);
    if (!response.ok) throw Object.assign(new Error(`HTTP ${response.status} for ${path}`), {status: response.status, responseComplete: true});
    return {body: path.includes('frame.png') || path.endsWith('/evidence') ? bytes : JSON.parse(bytes), headers: response.headers, index};
  }
  const json = async (...args) => (await api(...args)).body;
  async function until(read, predicate, timeout = 60000) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) { const value = await read(); if (predicate(value)) return value; await delay(100); }
    throw new Error('Managed controls observation deadline exceeded');
  }
  function runtimeIdentity(pid) {
    return JSON.parse(execFileSync(python, ['-B', '-c', `import ctypes,hashlib,json,pathlib,sys
p=int(sys.argv[1])
if sys.platform=='darwin':
 b=ctypes.create_string_buffer(4096)
 assert ctypes.CDLL('/usr/lib/libproc.dylib').proc_pidpath(p,b,len(b))>0
 f=pathlib.Path(b.value.decode())
else:
 f=pathlib.Path('/proc')/str(p)/'exe'
print(json.dumps({'pid':p,'executable_name':f.resolve().name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}))`, String(pid)], {encoding: 'utf8'}));
  }
  async function sameVM() {
    const current = await json(`sessions/${sessionId}`);
    for (const key of ['session_id', 'pid', 'firmware_sha256', 'worker']) assert.deepEqual(current[key], session[key]);
    assert.equal(current.state, 'running'); assert.deepEqual(runtimeIdentity(current.pid), report.runtime);
    return current;
  }
  async function currentRun(run) {
    const p = await json(`previews/${previewId}`), row = await json(`previews/${previewId}/runs/${run.run_id}`);
    assert.equal(p.active_run_id, run.run_id); assert.equal(p.owner_epoch, ownerEpoch);
    for (const key of ['preview_id', 'run_id', 'execution_id', 'revision_id']) assert.equal(row[key], run[key]);
    assert.equal(row.state, 'running'); return row;
  }
  const serial = offset => json(`sessions/${sessionId}/serial?offset=${offset}&limit=1048576`);
  async function application(run, phase, freshOffset = null, predicate = () => true) {
    return until(async () => {
      await currentRun(run);
      const complete = await serial(run.serialOffset), fresh = freshOffset === null ? null : await serial(freshOffset);
      if (fresh) assert.ok(fresh.offset >= run.serialOffset, 'Input cursor precedes current execution');
      const parsed = pure('parse', {text: complete.data, execution: run.execution_id, nonce: report.nonce, phase,
        require_ready: true, ...(fresh ? {fresh_text: fresh.data} : {})});
      return {complete, fresh, parsed};
    }, row => !!row.parsed && predicate(row.parsed.sample));
  }
  async function admittedRun(receipt, offset, phase) {
    for (const key of ['run_id', 'execution_id']) assert.match(receipt[key], /^[0-9a-f]{32}$/);
    assert.equal(receipt.preview_id, previewId);
    const run = await until(() => json(`previews/${previewId}/runs/${receipt.run_id}`), row => ['running', 'completed', 'failed', 'unknown'].includes(row.state), 120000);
    for (const key of ['preview_id', 'run_id', 'execution_id', 'revision_id']) assert.equal(run[key], receipt[key]);
    Object.assign(run, {serialOffset: offset, phase}); report.runs.push(run);
    if (phase === 'seed') {
      assert.ok(['running', 'completed'].includes(run.state));
      await until(() => serial(offset), data => {
        const marker = `__M5_EXEC_${run.execution_id}__:START`, start = data.data.indexOf(marker);
        return start >= 0 && data.data.slice(start + marker.length).split(/\r?\n/).some(line => {
          try { const value = JSON.parse(line.slice(17)); return line.startsWith('PREVIEW_CONTROLS ') && value.kind === 'seed' && value.nonce === report.nonce; } catch { return false; }
        });
      });
    } else { assert.equal(run.state, 'running'); await application(run, phase); }
    await sameVM(); return run;
  }
  async function apiRun(payload, phase) {
    const offset = (await serial(0)).next_offset;
    const checkpoint = await json('program-revisions', 'POST', payload), p = await json(`previews/${previewId}`);
    const receipt = await json(`previews/${previewId}/runs`, 'POST', {revision_id: checkpoint.revision.revision_id,
      expected_owner_epoch: ownerEpoch, expected_generation: p.generation, client_generation: `controls-${report.nonce}-${phase}`, timeout_seconds: 120}, randomUUID());
    assert.equal(receipt.revision_id, checkpoint.revision.revision_id);
    return admittedRun(receipt, offset, phase);
  }
  async function input(run, instance, field, expected, perform) {
    await currentRun(run); const offset = (await serial(0)).next_offset;
    const receipt = page.waitForResponse(response => {
      if (response.request().method() !== 'POST' || new URL(response.url()).pathname !== `/api/v1/previews/${previewId}/input`) return false;
      const command = response.request().postDataJSON();
      return command.expected_run_id === run.run_id && command.unit_input?.id === instance && Object.hasOwn(command.unit_input.values || {}, field);
    });
    await perform(); const response = await receipt; assert.equal(response.status(), 200);
    const body = await response.json();
    for (const key of ['preview_id', 'run_id', 'execution_id', 'revision_id']) assert.equal(body[key], run[key]);
    assert.equal(body.result.session_id, sessionId);
    assert.deepEqual(response.request().postDataJSON().unit_input.values[field], expected);
    return offset;
  }
  async function raw(instance, property) {
    const path = `/machine/units/${instance}`, value = await json(`sessions/${sessionId}/qom?path=${encodeURIComponent(path)}&property=${encodeURIComponent(property)}`);
    assert.equal(value.session_id, sessionId); assert.equal(value.path, path); assert.equal(value.property, property); return value;
  }
  async function visual() {
    return page.evaluate(id => {
      const v = window.__previewControls.state.visuals.get(id), p = v.unitPanel;
      return {bindings: structuredClone(p.bindingsByUnit), units: Object.fromEntries(['encoder', 'eight'].map(instance => {
        const mounted = p.mounted.get(instance), module = v.shell.model.port(mounted.port).module;
        const targets = instance === 'encoder' ? ['led0', 'led1'] : Array.from({length: 9}, (_, i) => `rgb-${i + 1}`);
        return [instance, {available: p.states.get(instance)?.available, colors: p.states.get(instance)?.properties['led-rgb'],
          joints: module.list('joint').map(joint => joint.getState()), leds: targets.map(name => {
            const led = v.shell.model.find(`${mounted.port}/${name}`, 'led');
            return {attached: module.components.get(led.id) === led, known: led.runtimeKnown, userDataKnown: led.object3d.userData.runtimeKnown,
              state: led.getState(), emissive: led.lensMaterial.emissive.toArray(), glow: led.glow.visible,
              opacity: led.glow.material.opacity, glowColor: '#' + led.glow.material.color.getHexString()};
          })}];
      }))};
    }, sessionId);
  }
  async function observe(run, phase, label, offset = null, predicate = () => true) {
    const observed = await application(run, phase, offset, predicate), sample = observed.parsed.sample, qom = {};
    const wanted = {encoder: {counter: sample.encoder.counter, pressed: sample.encoder.pressed, 'led-rgb': sample.written.encoder},
      eight: {counters: sample.eight.counters, pressed: sample.eight.pressed, 'switch-on': sample.eight.switch_on, 'led-rgb': sample.written.eight},
      joystick: {'x-raw': sample.joystick.x_raw, 'y-raw': sample.joystick.y_raw, 'button-raw': sample.joystick.button_raw}};
    for (const [instance, fields] of Object.entries(wanted)) {
      qom[instance] = {};
      for (const [property, expected] of Object.entries(fields)) { const row = await raw(instance, property); assert.deepEqual(row.value, expected); qom[instance][property] = row; }
      qom[instance].transactions = await raw(instance, 'transactions');
      const count = qom[instance].transactions.value, previous = traffic.get(instance) || 0;
      assert.ok(Number.isInteger(count) && count > previous, `Fresh ${instance} I2C traffic required`);
      qom[instance].transaction_delta = count - previous; traffic.set(instance, count);
    }
    const mounted = await until(visual, value => ['encoder', 'eight'].every(instance => value.units[instance].available
      && JSON.stringify(value.units[instance].colors) === JSON.stringify(sample.written[instance])
      && value.units[instance].leds.every(led => led.known && led.state.color === '#' + sample.written[instance][0].toString(16).padStart(6, '0'))));
    assert.deepEqual(mounted.bindings, {});
    for (const [instance, unit] of Object.entries(mounted.units)) {
      const color = sample.written[instance][0], hex = '#' + color.toString(16).padStart(6, '0'), brightness = color ? 1 : 0;
      assert.equal(unit.leds.length, instance === 'encoder' ? 2 : 9);
      for (const led of unit.leds) {
        assert.equal(led.attached, true); assert.equal(led.userDataKnown, true); assert.deepEqual(led.state, {color: hex, brightness});
        assert.equal(led.glow, !!brightness); assert.equal(led.opacity, .85 * brightness); assert.equal(led.glowColor, hex);
        const expected = [color >> 16 & 255, color >> 8 & 255, color & 255].map(c => (c / 255 <= .04045 ? c / 255 / 12.92 : ((c / 255 + .055) / 1.055) ** 2.4) * 2.2);
        led.emissive.forEach((v, i) => assert.ok(Math.abs(v - expected[i]) < 1e-6));
      }
      assert.ok(unit.joints.every(joint => joint.angleDeg === 0 && joint.targetAngleDeg === 0 && joint.rpm === 0), 'Logical counts must not invent mechanical motion');
    }
    const result = {label, run_id: run.run_id, execution_id: run.execution_id, revision_id: run.revision_id, serial: observed, qom, mounted};
    report.observations.push(result); return result;
  }
  async function frame(run, phase) {
    const {body: bytes, headers} = await api(`previews/${previewId}/runs/${run.run_id}/frame.png`);
    for (const [header, expected] of Object.entries({'X-Preview-ID': previewId, 'X-Run-ID': run.run_id,
      'X-Frame-Execution-ID': run.execution_id, 'X-Frame-Revision-ID': run.revision_id, 'X-Frame-SHA256': sha(bytes)})) assert.equal(headers.get(header), expected);
    await writeFile(resolve(output, `phase-${phase}-frame.png`), bytes);
    const pixel = await page.evaluate(async encoded => {
      const bitmap = await createImageBitmap(new Blob([Uint8Array.from(atob(encoded), c => c.charCodeAt(0))], {type: 'image/png'}));
      try { const canvas = document.createElement('canvas'); canvas.width = bitmap.width; canvas.height = bitmap.height;
        const c = canvas.getContext('2d'); c.drawImage(bitmap, 0, 0); return {x: Math.floor(bitmap.width / 2), y: Math.floor(bitmap.height / 2), value: [...c.getImageData(Math.floor(bitmap.width / 2), Math.floor(bitmap.height / 2), 1, 1).data]};
      } finally { bitmap.close(); }
    }, bytes.toString('base64'));
    const expected = {A: [255, 0, 0], B: [0, 255, 0], C: [0, 0, 255]}[phase]; assert.deepEqual(pixel.value.slice(0, 3), expected);
    await page.waitForFunction(({id, run, pixel, expected}) => {
      const v = window.__previewControls.state.visuals.get(id), observed = v?.shell?.display?.getPixel(pixel.x, pixel.y);
      return v?.frameBlob && v.frameMetadata?.['x-frame-execution-id'] === run.execution_id && v.frameMetadata?.['x-frame-revision-id'] === run.revision_id
        && observed && expected.every((c, i) => observed[i] === c);
    }, {id: sessionId, run, pixel, expected});
    report.observations.push({label: `frame-${phase}`, run_id: run.run_id, sha256: sha(bytes), headers: Object.fromEntries(headers), selected_pixel: pixel});
  }
  async function closeOwned() {
    const result = await closeOwnedPreview(owned, {send: json, wait: until,
      captureZip: async id => { const zip = await json(`sessions/${id}/evidence`); await writeFile(resolve(output, 'failure-evidence.zip'), zip); },
      pidGone: pid => { try { process.kill(pid, 0); return false; } catch (error) { if (error.code === 'ESRCH') return true; throw error; } },
      verify: value => pure('cleanup', value)});
    return result;
  }
  try {
    const health = await json('health'); assert.equal(health.capacity.active_sessions, 0, 'Root-owned idle service required');
    const devices = await json('devices'); assert.ok(devices.devices.find(d => d.device_id === options.device)?.program_modes.includes('uiflow-live'));
    const inventory = await json(`units?device_id=${options.device}`);
    const createIntent = {key: randomUUID(), body: {device_id: options.device, runtime: 'qemu', ttl_seconds: 900, units: plan.attachments}};
    await save('create-intent.json', createIntent);
    const created = await createOwnedPreview(owned, createIntent, json);
    previewId = created.preview_id; ownerEpoch = created.owner_epoch; assert.match(previewId, /^[0-9a-f]{32}$/);
    const p = await until(() => json(`previews/${previewId}`), value => ['ready', 'failed'].includes(value.state), 120000);
    assert.equal(p.state, 'ready'); ownerEpoch = p.owner_epoch; sessionId = p.session_id;
    session = await json(`sessions/${sessionId}`); Object.assign(owned, {sessionId, session});
    report.runtime = runtimeIdentity(session.pid); assert.equal(report.runtime.sha256, expectedRuntime);
    Object.assign(report, {preview_id: previewId, owner_epoch: ownerEpoch, session_id: sessionId, pid: session.pid, firmware_sha256: session.firmware_sha256,
      worker: session.worker, frozen_attachments: session.units, inventory_sha256: sha(JSON.stringify(inventory)), nonce: randomUUID().replaceAll('-', '')});
    assert.equal(session.units.length, 4); assert.deepEqual(session.units.map(u => u.id).sort(), ['eight', 'encoder', 'hub1', 'joystick']);
    const pins = session.units.find(u => u.id === 'hub1').pins; assert.ok(session.units.every(u => JSON.stringify(u.pins) === JSON.stringify(pins)));
    const {chromium} = await import('playwright');
    browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
      args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
    page = await browser.newPage({viewport: {width: 1440, height: 1080}}); page.on('pageerror', error => report.page_errors.push(error.message));
    page.on('response', response => {
      if (!response.url().startsWith(base + '/api/v1/')) return;
      const row = {path: new URL(response.url()).pathname, method: response.request().method(), status: response.status()}; report.browser_http.push(row);
      if (row.method !== 'GET') { row.body = response.request().postDataJSON(); browserTasks.push(response.json().then(value => { row.response = value; }).catch(error => { row.observation_error = error.message; })); }
    });
    await page.route('**/platform/web/sessions.js*', async route => {
      const response = await route.fetch(), text = await response.text(); assert.equal(sha(text), report.source_sha256['platform/web/sessions.js']);
      await route.fulfill({response, body: text + '\nwindow.__previewControls={state,SessionVisual};\n'});
    });
    await page.goto(`${base}/platform/web/sessions.html`, {waitUntil: 'domcontentloaded'});
    await page.fill('#tokenInput', token); await page.click('#saveTokenBtn');
    const card = page.locator(`[data-session-id="${sessionId}"]`); await card.waitFor();
    await page.waitForFunction(id => window.__previewControls.state.visuals.get(id)?.unitPanel?.mounted.size === 4, sessionId);
    await apiRun(pure('seed', {nonce: report.nonce}), 'seed');
    const bundle = pure('package', {nonce: report.nonce, pins}); await save('complete-package.json', bundle);
    const a = await apiRun(bundle, 'A');
    await observe(a, 'A', 'initial');
    const press = instance => card.locator(`[data-unit-id="${instance}"] [data-press-field="pressed"]${instance === 'eight' ? '[data-press-index="0"]' : ''}`).first();
    async function pointer(instance, down, run, phase) {
      const button = press(instance); await button.scrollIntoViewIfNeeded(); await until(() => button.isEnabled(), Boolean);
      const box = await button.boundingBox(); assert.ok(box);
      const offset = await input(run, instance, 'pressed', instance === 'eight' ? [down, false, false, false, false, false, false, false] : down, async () => {
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse[down ? 'down' : 'up']();
      });
      return observe(run, phase, `${instance}-${down ? 'hold' : 'release'}`, offset, s => instance === 'encoder' ? s.encoder.pressed === down : s.eight.pressed[0] === down);
    }
    for (const instance of ['encoder', 'eight']) { await pointer(instance, true, a, 'A'); await pointer(instance, false, a, 'A'); }
    const countInput = card.locator('[data-unit-id="encoder"] [data-input-field="counter"]');
    for (const value of [123, 0]) {
      const offset = await input(a, 'encoder', 'counter', value, async () => { await countInput.fill(String(value)); await countInput.press('Tab'); });
      await observe(a, 'A', `counter-${value}-no-axis-motion`, offset, s => s.encoder.counter === value);
    }
    for (const [field, value] of Object.entries({'x-raw': 31, 'y-raw': 240, 'button-raw': 1})) {
      const node = card.locator(`[data-unit-id="joystick"] [data-input-field="${field}"]`);
      const offset = await input(a, 'joystick', field, value, async () => { await node.fill(String(value)); await node.press('Tab'); });
      await observe(a, 'A', `joystick-${field}`, offset, s => s.joystick[field.replaceAll('-', '_')] === value);
    }
    await frame(a, 'A');
    const load = card.locator('[data-program-load]'); await until(() => load.isEnabled(), Boolean); await load.click();
    const editor = card.locator('[data-program-source]'); await until(() => editor.inputValue(), text => text.includes('PREVIEW_CONTROLS'));
    const original = await editor.inputValue(), offset = (await serial(0)).next_offset;
    await editor.fill("_preview_phase='B'\n" + original);
    const checkpointReply = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/v1/program-revisions');
    const runReply = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === `/api/v1/previews/${previewId}/runs`);
    await card.locator('[data-program-run]').click(); const checkpointResponse = await checkpointReply; assert.equal(checkpointResponse.status(), 201);
    const response = await runReply; assert.equal(response.status(), 202); const b = await admittedRun(await response.json(), offset, 'B');
    const preserved = await json(`program-revisions/${b.revision_id}/files`);
    for (const [path, file] of Object.entries(bundle.files)) if (path !== 'main.py') assert.deepEqual(Buffer.from(preserved.files[path].data, 'base64'), Buffer.from(file.data, file.encoding === 'utf8' ? 'utf8' : 'base64'));
    await pointer('eight', true, b, 'B'); await frame(b, 'B');
    // Leave the trusted pointer held while the server cancels B. Its release
    // after C starts must never become an input for C.
    await json(`previews/${previewId}/runs/${b.run_id}/cancel`, 'POST', {expected_owner_epoch: ownerEpoch});
    const cancelled = await until(() => json(`previews/${previewId}/runs/${b.run_id}`), row => row.state === 'cancelled');
    assert.equal(cancelled.interrupt_ack, 'confirmed'); report.cancelled = cancelled;
    const cPackage = structuredClone(bundle); cPackage.files['main.py'].data = "_preview_phase='C'\n" + original;
    const c = await apiRun(cPackage, 'C'); await observe(c, 'C', 'after-cancel-new-run', null, s => !s.encoder.pressed && s.eight.pressed.every(v => !v));
    const before = report.browser_http.length; await page.mouse.up(); await delay(1000);
    assert.equal(report.browser_http.slice(before).filter(row => row.method === 'POST' && row.path.endsWith('/input') && row.body?.expected_run_id === c.run_id).length, 0, 'Old held release must not target C');
    await pointer('encoder', true, c, 'C'); await pointer('encoder', false, c, 'C'); await frame(c, 'C');
    for (const width of [390, 768, 1024, 1440]) {
      await page.setViewportSize({width, height: 1080}); await page.evaluate(() => scrollTo(0, 0)); await delay(200);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.screenshot({path: resolve(output, `controls-${width}.png`), fullPage: true});
    }
    await sameVM();
    const zip = await json(`sessions/${sessionId}/evidence`); await writeFile(resolve(output, 'evidence-before-close.zip'), zip); owned.zipBeforeClose = true;
    report.zip = pure('zip', {bytes: zip.toString('base64'), expected: {session_id: sessionId, device_id: options.device,
      firmware_sha256: session.firmware_sha256, pid: session.pid, runs: report.runs}});
    report.cleanup = await closeOwned(); assert.equal(report.cleanup.preview.close_evidence.status, 'captured');
    await Promise.all(browserTasks); assert.deepEqual(report.page_errors, []);
    assert.deepEqual(report.browser_http.filter(row => row.method !== 'GET' && /\/sessions\/[^/]+\/(program|input|unit-input|renew|reset)$/.test(row.path)), []);
    assert.deepEqual(await fingerprints(), report.source_sha256); report.status = 'PASS';
  } catch (error) { report.error = error.stack || String(error); }
  finally {
    if (!report.cleanup) { try { report.failure_cleanup = await closeOwned(); } catch (error) { report.cleanup_error = error.stack || String(error); } }
    report.creation = owned.creation; report.cleanup_warnings = owned.cleanupWarnings;
    await browser?.close(); await Promise.all(browserTasks); await save('report.json', report);
  }
  console.log(`LIVE_PREVIEW_CONTROLS_${report.status} ${options.device}`);
  if (report.status !== 'PASS') process.exitCode = 1;
}
