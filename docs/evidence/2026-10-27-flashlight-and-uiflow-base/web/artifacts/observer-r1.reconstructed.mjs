// Read-only observer of a root-owned 8787 session. No guest/API execution by default.
import assert from 'node:assert/strict';
import {createHash, randomUUID} from 'node:crypto';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {mkdir, readFile, writeFile, rename, readdir, stat} from 'node:fs/promises';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../..');
const sha = value => createHash('sha256').update(value).digest('hex');
const phases = ['initial-steady-on', 'steady-off', 'steady-on', 'slow2', 'steady-on'];
const options = {};
for (let i = 2; i < process.argv.length; i++) {
  const arg = process.argv[i];
  if (['--execute', '--plan'].includes(arg)) {assert.equal(options[arg], undefined); options[arg] = true;}
  else if (['--hold-file', '--out-dir', '--expected-runtime-sha256', '--expected-service-pid', '--expected-generation'].includes(arg)) {
    assert.equal(options[arg], undefined); assert.ok(process.argv[i + 1] && !process.argv[i + 1].startsWith('--'));
    options[arg] = process.argv[++i];
  } else throw Error(`Unknown option ${arg}`);
}
const sources = ['.work/flashlight-live-web-20261027/observe.mjs', '.work/flashlight-live-probe-20261027/probe.py',
  'platform/web/sessions.html', 'platform/web/sessions.js', 'platform/web/unit-panel.js', 'platform/web/model-shell.js',
  'platform/web/unit-visual-mappings.js', 'platform/web/device-shell-factory.js', 'platform/units/catalog.json',
  'platform/units/runtime-profiles.json', 'platform/units/host-ports.json', 'platform/tools/device_service.py',
  'platform/web/vendor/m5stack-models/src/core/components/Led.js',
  'platform/web/vendor/m5stack-models/src/units/flashlight/assembly.js',
  'platform/web/vendor/m5stack-models/src/units/flashlight/dimensions.js',
  'platform/tests/test_live_uniform_led_service_browser.mjs', 'platform/tests/test_live_relay2_preview_service_browser.mjs'];
const fingerprints = async () => Object.fromEntries(await Promise.all(sources.map(async path => [path, sha(await readFile(resolve(root, path)))])));
const plan = {status: 'NOT RUN', api_contacted: false, browser_started: false, guests_started: 0,
  phases, hardware: 'NOT RUN', requires: ['root explicit runtime READY + owned Torch hold ready', ...Object.keys(options).filter(key => key !== '--plan')],
  execution_arguments: ['--execute', '--hold-file <root-owned.json>', '--out-dir <fresh-directory>',
    '--expected-runtime-sha256 <64-hex>', '--expected-service-pid <pid>', '--expected-generation <generation>'],
  scope: 'Actual 8787 sessions page, actual default UnitPanel, mounted vendor FixedWhiteLed material, independent GET units/raw-QOM/frame/serial.',
  mutations: 'Only root-owned hold command/done files. No program/input POST, controller setter, synthetic state, or API reply substitution.',
  instrumentation: 'Append only window.__flashlightProbe={state,SessionVisual} to hash-verified sessions.js; actual GET replies are unchanged.',
  response_limits: {each_bytes: 2097152, aggregate_browser_bytes: 33554432, browser_rows: 3000, body_timeout_ms: 5000},
  source_sha256: await fingerprints()};
if (!options['--execute'] || options['--plan']) {console.log(JSON.stringify(plan, null, 2)); process.exit(0);}

const expectedRuntime = options['--expected-runtime-sha256']; assert.match(expectedRuntime || '', /^[0-9a-f]{64}$/);
const expectedPid = Number(options['--expected-service-pid']), expectedGeneration = Number(options['--expected-generation']);
assert.ok(Number.isSafeInteger(expectedPid) && expectedPid > 0 && Number.isSafeInteger(expectedGeneration) && expectedGeneration > 0);
assert.ok(options['--hold-file'] && options['--out-dir']);
const holdPath = resolve(options['--hold-file']); assert.ok(holdPath.endsWith('.json'));
const commandPath = holdPath.replace(/\.json$/, '.command.json'), observationPath = holdPath.replace(/\.json$/, '.observation.json'), donePath = holdPath.replace(/\.json$/, '.done');
const holdBytes = await readFile(holdPath); assert.ok(holdBytes.length < 131072);
const hold = JSON.parse(holdBytes); assert.equal(hold.mode, false, 'Only an explicit Torch fixture is admitted');
assert.match(hold.session_id || '', /^[0-9a-f]{32}$/); assert.match(hold.nonce || '', /^[0-9a-f]{32}$/);
assert.ok(Number.isSafeInteger(hold.pid) && hold.pid > 0); assert.equal(hold.runtime_sha256, expectedRuntime);
assert.equal(hold.worker.generation, expectedGeneration); assert.match(hold.firmware_sha256 || '', /^[0-9a-f]{64}$/);
for (const path of [commandPath, observationPath, donePath]) {
  try {await stat(path); throw Error('A fresh owned hold is required; coordination file already exists');}
  catch (error) {if (error.code !== 'ENOENT') throw error;}
}
const output = resolve(options['--out-dir']); await mkdir(output, {recursive: false});
// Authentication is read only after explicit execution gates, kept in memory,
// and never included in evidence, headers, hashes, stdout, or hold files.
const token = (await readFile(resolve(root, '.work/preview-control-token'), 'utf8')).trim(); assert.ok(token);
const save = (name, value) => writeFile(resolve(output, name), JSON.stringify(value, null, 2) + '\n', {mode: 0o600});
const report = {schema_version: 1, category: 'actual-u152-controller-to-mounted-web-observation', status: 'FAIL',
  captured_at: new Date().toISOString(), hold, hold_sha256: sha(holdBytes), hardware: 'NOT RUN',
  source_sha256: await fingerprints(), http: [], browser_http: [], phases: [], forbidden_mutations: [],
  console_errors: [], page_errors: [], resource_errors: [], instrumentation: plan.instrumentation,
  scope: 'Steady Torch on/off + actual modulation-unknown withdrawal + same-VM recovery; no optical/photometric/electrical equivalence.',
  snapshot_semantics: 'HTTP, individual QOM properties, guest frames and mounted render are separate stable-stage samples, not atomic.'};
const base = 'http://127.0.0.1:8787', prefix = `sessions/${hold.session_id}`;
let browser, page, browserBytes = 0, sealed = false;
const observerTasks = [], pending = new Set();
const redact = value => String(value).replace(/Bearer\s+[^\s"']+/gi, 'Bearer [redacted]').slice(0, 6000);
const headersOnly = headers => Object.fromEntries(Object.entries(headers).filter(([key]) => ['content-type', 'content-length', 'etag', 'cache-control'].includes(key.toLowerCase()) || key.toLowerCase().startsWith('x-frame-')));
function pngMetrics(path) {
  return JSON.parse(execFileSync('/opt/miniconda3/bin/python3.12', ['-c',
    'import json,sys;from PIL import Image;im=Image.open(sys.argv[1]);im.load();assert im.format=="PNG";rgba=im.convert("RGBA");pixels=list(rgba.getdata());visible=[p[:3] for p in pixels if p[3]>0];print(json.dumps({"size":list(im.size),"center":list(rgba.getpixel((im.width//2,im.height//2)))[:3],"visible_pixels":len(visible),"unique_rgb":len(set(visible))}))', path],
    {encoding: 'utf8', timeout: 15000}));
}
async function bounded(operation, milliseconds, name) {
  let timer;
  try {return await Promise.race([Promise.resolve().then(operation), new Promise((_, reject) => {timer = setTimeout(() => reject(Error(`${name} timed out`)), milliseconds);})]);}
  finally {clearTimeout(timer);}
}
async function until(read, predicate, timeout = 60000) {
  const end = Date.now() + timeout; let last;
  while (Date.now() < end) {last = await read(); if (predicate(last)) return last; await delay(125);}
  throw Error(`Observation timeout: ${JSON.stringify(last).slice(-1500)}`);
}
async function readJSON(path) {
  const bytes = await readFile(path); assert.ok(bytes.length < 2097152); return JSON.parse(bytes);
}
async function owned() {assert.equal(sha(await readFile(holdPath)), report.hold_sha256, 'Owned hold identity changed');}
async function coordinate(sequence, phase) {
  await owned();
  const temp = `${commandPath}.${randomUUID()}.tmp`;
  await writeFile(temp, JSON.stringify({sequence, phase}) + '\n', {flag: 'wx', mode: 0o600}); await rename(temp, commandPath);
  return until(async () => {try {return await readJSON(observationPath);} catch (error) {if (error.code === 'ENOENT' || error instanceof SyntaxError) return null; throw error;}},
    value => value?.sequence === sequence && value.phase === phase, 90000);
}
async function api(path, binary = false) {
  const row = {index: report.http.length, method: 'GET', path, observed_at: new Date().toISOString()}; report.http.push(row);
  const response = await fetch(`${base}/api/v1/${path}`, {method: 'GET', headers: {Authorization: `Bearer ${token}`}, redirect: 'error', signal: AbortSignal.timeout(15000)});
  row.status = response.status; row.headers = headersOnly(Object.fromEntries(response.headers));
  const chunks = []; let length = 0;
  for await (const chunk of response.body) {length += chunk.length; assert.ok(length <= 2097152, 'API response exceeded bound'); chunks.push(chunk);}
  const bytes = Buffer.concat(chunks); Object.assign(row, {bytes: length, sha256: sha(bytes), body: `http-${row.index}.response`});
  await writeFile(resolve(output, row.body), bytes, {mode: 0o600}); await save(`http-${row.index}.json`, row);
  assert.equal(response.status, 200, `${path} HTTP ${response.status}`);
  return binary ? {bytes, headers: row.headers} : JSON.parse(bytes);
}
function captureBrowser(response) {
  if (sealed) return;
  const url = new URL(response.url()), path = url.pathname;
  if (!path.startsWith(`/api/v1/${prefix}`)) return;
  if (report.browser_http.length >= 3000) {report.browser_limit_exceeded = true; return;}
  const row = {index: report.browser_http.length, method: response.request().method(), path: path + url.search,
    status: response.status(), observed_at: new Date().toISOString(), state: 'pending'};
  report.browser_http.push(row);
  const task = (async () => {
    try {
      const bytes = await bounded(() => response.body(), 5000, 'Browser body');
      assert.ok(bytes.length <= 2097152 && browserBytes + bytes.length <= 33554432, 'Browser response bytes exceeded bounds');
      browserBytes += bytes.length; Object.assign(row, {bytes: bytes.length, sha256: sha(bytes), body: `browser-${row.index}.response`});
      await bounded(() => writeFile(resolve(output, row.body), bytes, {mode: 0o600}), 5000, 'Browser body save');
      if (path === `/api/v1/${prefix}/units` && row.status === 200) row.unit_payload = JSON.parse(bytes);
      row.headers = headersOnly(await bounded(() => response.allHeaders(), 5000, 'Browser headers')); row.state = 'complete';
    } catch (error) {row.state = 'error'; row.error = redact(error.message);}
    try {await bounded(() => save(`browser-${row.index}.json`, row), 5000, 'Browser metadata save');}
    catch (error) {row.metadata_error = redact(error.message);}
  })(); observerTasks.push(task); pending.add(task); void task.finally(() => pending.delete(task));
}
async function sessionIdentity() {
  const session = await api(prefix);
  for (const field of ['pid', 'firmware_sha256', 'worker', 'device_id']) assert.deepEqual(session[field], hold[field]);
  assert.equal(session.state, 'running');
  return session;
}
const properties = ['output-known', 'pad-synchronized', 'gpio-route-supported', 'flash-mode', 'mode-frozen', 'en-level', 'active', 'flash-level-pct', 'timeout-ms'];
const phaseWanted = phase => ({known: phase !== 'slow2', active: phase !== 'steady-off' && phase !== 'slow2', en: phase !== 'steady-off'});
function checkQOM(unit, phase) {
  const expected = phaseWanted(phase), p = unit.properties;
  assert.equal(unit.id, 'lamp'); assert.equal(unit.unit_id, 'flashlight'); assert.equal(unit.available, true);
  assert.deepEqual(unit.errors, {}); assert.equal(unit.source, 'guest-qom');
  assert.equal(p['flash-mode'], false); assert.equal(p['mode-frozen'], true); assert.equal(p['en-level'], expected.en);
  assert.equal(p['pad-synchronized'], true); assert.equal(p['gpio-route-supported'], true); assert.equal(p['output-known'], expected.known);
  if (expected.known) {assert.equal(p.active, expected.active); assert.equal(p['flash-level-pct'], 0); assert.equal(p['timeout-ms'], 0);}
}
async function mounted() {
  return page.evaluate(id => {
    const v = window.__flashlightProbe?.state.visuals.get(id), panel = v?.unitPanel;
    const attachment = panel?.session.units.find(unit => unit.id === 'lamp'), mounted = panel?.mounted.get('lamp');
    if (!mounted || !v?.shell) return null;
    const module = v.shell.model.port(mounted.port).module, led = v.shell.model.find(`${mounted.port}/light`, 'led');
    if (!led) return null;
    const card = panel.cards.get('lamp'), display = v.shell.display;
    return {session_id: panel.session.session_id, session: {pid: panel.session.pid, firmware_sha256: panel.session.firmware_sha256, worker: panel.session.worker},
      port: mounted.port, attachment, bindings: structuredClone(panel.bindingsByUnit), unit: structuredClone(panel.states.get('lamp')),
      state_source: panel.stateSource, frozen_definitions: panel.frozenDefinitions, physical_events: window.__flashlightEvents?.length || 0,
      led: {id: led.id, path: led.path, class_name: led.constructor.name, attached: module.components.get('light') === led,
        actual_vendor_light: module.flashlightAssembly?.light.led === led, known: led.runtimeKnown, userDataKnown: led.object3d.userData.runtimeKnown,
        state: led.getState(), emissive: led.lensMaterial.emissive.toArray(), glow: led.glow.visible, opacity: led.glow.material.opacity},
      live_controls: card.querySelectorAll('[data-input-field="flash-mode"], [data-press-field="flash-mode"]').length,
      creation_note: card.querySelector('[data-unit-creation-only="flash-mode"]')?.textContent,
      frame: {metadata: v.frameMetadata, sha256: v.lastFrameHash, width: display?.width, height: display?.height,
        center: display ? [...display.getPixel(Math.floor(display.width / 2), Math.floor(display.height / 2))].slice(0, 3) : null}};
  }, hold.session_id);
}
function checkMounted(value, phase, execution) {
  assert.ok(value); assert.equal(value.session_id, hold.session_id); assert.deepEqual(value.bindings, {});
  for (const field of ['pid', 'firmware_sha256', 'worker']) assert.deepEqual(value.session[field], hold[field]);
  assert.equal(value.state_source, 'live'); assert.equal(value.frozen_definitions, true); checkQOM(value.unit, phase);
  const wanted = phaseWanted(phase); assert.equal(value.physical_events, 0); assert.equal(value.live_controls, 0);
  assert.match(value.creation_note, /创建时固定，运行中只读/);
  assert.equal(value.led.class_name, 'FixedWhiteLed'); assert.equal(value.led.attached, true); assert.equal(value.led.actual_vendor_light, true);
  assert.equal(value.led.known, wanted.known); assert.equal(value.led.userDataKnown, wanted.known);
  assert.deepEqual(value.led.state, {color: '#fffaf0', brightness: wanted.active ? 1 : 0}); assert.equal(value.led.glow, false);
  const expectedEmission = [255, 250, 240].map(c => {const s = c / 255; return (s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4) * 2.2 * Number(wanted.active);});
  expectedEmission.forEach((number, i) => assert.ok(Math.abs(value.led.emissive[i] - number) < 1e-6));
  assert.equal(value.frame.metadata?.['x-frame-execution-id'], execution.execution_id);
  assert.equal(value.frame.metadata?.['x-frame-revision-id'], execution.revision_id);
  assert.equal(value.frame.metadata?.['x-frame-source'], 'live');
  assert.deepEqual(value.frame.center, phaseWanted(phase).en ? [255, 255, 255] : [0, 0, 0]);
}
async function screenshots(label) {
  const card = page.locator(`[data-session-id="${hold.session_id}"]`), stage = card.locator('.three-device-stage').first();
  const panelPath = `${label}-panel.png`, panelBytes = await card.locator('[data-unit-id="lamp"]').screenshot({path: resolve(output, panelPath)});
  await stage.scrollIntoViewIfNeeded(); await stage.evaluate(node => node.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'}));
  const render = await page.evaluate(async id => {
    const {Box3, Vector3} = await import('/platform/web/vendor/three/three.module.js');
    const visual = window.__flashlightProbe.state.visuals.get(id), viewer = visual.shell.viewer;
    viewer.setView('front', {duration: 0}); viewer.resize(); viewer.fit({padding: 1.8, duration: 0});
    await new Promise((resolve, reject) => {let off; const timer = setTimeout(() => {off?.(); reject(Error('Render timeout'));}, 5000);
      off = viewer.once('render', () => {clearTimeout(timer); resolve();}); viewer.requestRender();});
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    viewer.scene.updateMatrixWorld(true); viewer.camera.updateMatrixWorld(true);
    const rect = viewer.renderer.domElement.getBoundingClientRect(), port = visual.unitPanel.mounted.get('lamp').port;
    const entries = [{name: 'host-and-unit', object: visual.shell.model.root}, {name: 'flashlight', object: visual.shell.model.port(port).module.root}];
    const bounds = entries.map(({name, object}) => {
      const box = new Box3().setFromObject(object), points = []; let visible = true;
      for (let n = object; n; n = n.parent) if (!n.visible) visible = false;
      for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
        const p = new Vector3(x, y, z).project(viewer.camera); points.push({x: (p.x + 1) * rect.width / 2, y: (1 - p.y) * rect.height / 2, z: p.z});
      }
      return {name, visible, points};
    });
    return {width: rect.width, height: rect.height, viewport: {x: rect.x, y: rect.y, width: innerWidth, height: innerHeight}, bounds, png: viewer.screenshot()};
  }, hold.session_id);
  assert.ok(render.viewport.x >= 0 && render.viewport.y >= 0 && render.viewport.x + render.width <= render.viewport.width && render.viewport.y + render.height <= render.viewport.height);
  assert.ok(render.bounds.every(b => b.visible && b.points.every(p => p.x >= 2 && p.y >= 2 && p.x <= render.width - 2 && p.y <= render.height - 2 && p.z > -1 && p.z < 1)));
  const unit = render.bounds.find(b => b.name === 'flashlight'), span = axis => Math.max(...unit.points.map(p => p[axis])) - Math.min(...unit.points.map(p => p[axis]));
  assert.ok(span('x') >= 16 && span('y') >= 16, 'Unit must have a visible viewport footprint');
  const rendererBytes = Buffer.from(render.png.split(',')[1], 'base64'); delete render.png;
  const rendererPath = `${label}-webgl.png`; await writeFile(resolve(output, rendererPath), rendererBytes);
  const metrics = pngMetrics(resolve(output, rendererPath)); assert.ok(metrics.visible_pixels > 1000 && metrics.unique_rgb > 50, 'Actual WebGL render must not be blank');
  const viewportPath = `${label}-viewport.png`, viewportBytes = await page.screenshot({path: resolve(output, viewportPath)});
  const stagePath = `${label}-stage.png`, stageBytes = await stage.screenshot({path: resolve(output, stagePath)});
  return {...render, panel: {path: panelPath, sha256: sha(panelBytes)}, renderer: {path: rendererPath, sha256: sha(rendererBytes), metrics},
    viewport_image: {path: viewportPath, sha256: sha(viewportBytes)}, stage: {path: stagePath, sha256: sha(stageBytes)}};
}
async function capture(sequence, phase, observation) {
  const label = `${sequence}-${phase}`, record = {sequence, phase, root_observation: observation, http_start: report.http.length, browser_http_start: report.browser_http.length};
  report.phases.push(record); await sessionIdentity();
  const execution = (await api(`${prefix}/program`)).program;
  for (const field of ['execution_id', 'revision_id', 'pid', 'firmware_sha256']) assert.equal(execution[field], observation.execution[field]);
  assert.equal(execution.state, 'completed'); assert.equal(execution.pid, hold.pid); assert.equal(execution.firmware_sha256, hold.firmware_sha256);
  record.execution = execution;
  const units = await api(`${prefix}/units`); assert.equal(units.source, 'live'); assert.equal(units.session_id, hold.session_id);
  const lamp = units.units.find(unit => unit.id === 'lamp'); checkQOM(lamp, phase); record.units = units; record.raw_qom = {};
  for (const property of properties) {
    const row = await api(`${prefix}/qom?path=${encodeURIComponent('/machine/units/lamp')}&property=${encodeURIComponent(property)}`);
    assert.equal(row.session_id, hold.session_id); assert.equal(row.path, '/machine/units/lamp'); assert.equal(row.property, property);
    assert.equal(row.value, lamp.properties[property]); record.raw_qom[property] = row;
  }
  const serial = await api(`${prefix}/serial?offset=0&limit=1048576`), marker = `__M5_EXEC_${execution.execution_id}__:START`;
  const start = serial.data.lastIndexOf(marker); assert.ok(start >= 0);
  const records = serial.data.slice(start + marker.length).split('\n').filter(line => line.startsWith('FLASHLIGHT_GUEST ')).map(line => JSON.parse(line.slice('FLASHLIGHT_GUEST '.length)));
  assert.equal(records.length, 1); assert.equal(records[0].nonce, hold.nonce); assert.equal(records[0].phase, phase); assert.deepEqual(records[0], observation.guest);
  record.serial = {offset: serial.offset, next_offset: serial.next_offset, execution_start: start, guest: records[0]};
  record.mounted = await until(mounted, value => {try {checkMounted(value, phase, execution); return true;} catch {return false;}}, 60000);
  checkMounted(record.mounted, phase, execution);
  const frame = await api(`${prefix}/frame.png?max_age_ms=1`, true), framePath = `${label}-frame.png`;
  assert.equal(frame.headers['x-frame-sha256'], sha(frame.bytes)); assert.equal(frame.headers['x-frame-execution-id'], execution.execution_id);
  assert.equal(frame.headers['x-frame-revision-id'], execution.revision_id); assert.equal(frame.headers['x-frame-source'], 'live');
  await writeFile(resolve(output, framePath), frame.bytes);
  const metrics = pngMetrics(resolve(output, framePath)); assert.deepEqual(metrics.center, phaseWanted(phase).en ? [255, 255, 255] : [0, 0, 0]);
  assert.deepEqual(metrics.size, [Number(frame.headers['x-frame-width']), Number(frame.headers['x-frame-height'])]);
  record.frame = {path: framePath, headers: frame.headers, sha256: sha(frame.bytes), metrics};
  record.screenshots = await screenshots(label);
  record.mounted_after_render = await mounted(); checkMounted(record.mounted_after_render, phase, execution);
  record.web_qom_response = await until(async () => report.browser_http.slice(record.browser_http_start).find(row => {
    try {
      assert.equal(row.unit_payload?.session_id, hold.session_id); assert.equal(row.unit_payload.source, 'live');
      checkQOM(row.unit_payload.units.find(unit => unit.id === 'lamp'), phase); return row.state === 'complete';
    } catch {return false;}
  }), Boolean, 10000);
  record.http_end = report.http.length; record.browser_http_end = report.browser_http.length;
  assert.deepEqual(report.forbidden_mutations, []); await save(`${label}.json`, record);
  console.log(`FLASHLIGHT_WEB_PHASE ${sequence} ${phase} ${execution.execution_id} ${execution.revision_id}`);
}
try {
  report.health = await api('health'); assert.equal(report.health.capacity.worker.pid, expectedPid); assert.equal(report.health.capacity.worker.generation, expectedGeneration);
  await sessionIdentity();
  const python = '/opt/miniconda3/bin/python3.12';
  report.runtime = JSON.parse(execFileSync(python, ['-c', 'import ctypes,hashlib,json,pathlib,sys;p=int(sys.argv[1]);b=ctypes.create_string_buffer(4096);assert ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath(p,b,len(b))>0;f=pathlib.Path(b.value.decode());print(json.dumps({"pid":p,"executable_name":f.name,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()}))', String(hold.pid)], {encoding: 'utf8', timeout: 15000}));
  assert.equal(report.runtime.sha256, expectedRuntime);
  const {chromium} = createRequire(resolve(root, 'platform/tests/package.json'))('playwright');
  browser = await chromium.launch({executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  report.browser_version = browser.version(); page = await browser.newPage({viewport: {width: 1440, height: 1080}, deviceScaleFactor: 2});
  await page.addInitScript(value => sessionStorage.setItem('m5-service-token', value), token);
  page.on('pageerror', error => report.page_errors.push(redact(error.message)));
  page.on('console', message => {if (['warning', 'error'].includes(message.type())) report.console_errors.push({type: message.type(), text: redact(message.text())});});
  page.on('response', response => {if (response.status() >= 400 && new URL(response.url()).pathname.includes('/vendor/')) report.resource_errors.push({path: new URL(response.url()).pathname, status: response.status()}); captureBrowser(response);});
  await page.route('**/api/v1/**', async route => {
    if (route.request().method() === 'GET') await route.continue();
    else {report.forbidden_mutations.push({method: route.request().method(), path: new URL(route.request().url()).pathname}); await route.abort('blockedbyclient');}
  });
  await page.route('**/platform/web/sessions.js*', async route => {
    const response = await route.fetch(), content = await response.text(); assert.equal(sha(content), report.source_sha256['platform/web/sessions.js']);
    await route.fulfill({response, body: content + '\nwindow.__flashlightProbe={state,SessionVisual};\n'});
  });
  await page.goto(`${base}/platform/web/sessions.html`, {waitUntil: 'domcontentloaded', timeout: 30000});
  await page.waitForFunction(id => window.__flashlightProbe?.state.visuals.get(id)?.unitPanel?.mounted.has('lamp'), hold.session_id, {timeout: 90000});
  await page.evaluate(id => {window.__flashlightEvents = []; window.__flashlightProbe.state.visuals.get(id).shell.on('unit-input', e => window.__flashlightEvents.push(structuredClone(e)));}, hold.session_id);
  const candidates = (await readdir(hold.output)).filter(name => /^\d+-steady-on\.json$/.test(name)).sort(); assert.ok(candidates.length);
  const initial = await readJSON(resolve(hold.output, candidates.at(-1))); assert.equal(initial.phase, 'steady-on'); assert.equal(initial.guest.nonce, hold.nonce);
  await capture(0, 'steady-on', initial);
  for (let sequence = 1; sequence < phases.length; sequence++) {
    const phase = phases[sequence], ack = await coordinate(sequence, phase); await save(`root-${sequence}.observation.json`, ack);
    await capture(sequence, phase, ack.observation);
  }
  await delay(1100); assert.deepEqual(report.forbidden_mutations, []); assert.deepEqual(report.page_errors, []); assert.deepEqual(report.resource_errors, []);
  assert.equal((await mounted()).physical_events, 0); report.source_sha256_after = await fingerprints();
  assert.deepEqual(report.source_sha256_after, report.source_sha256, 'Source files changed during live observation');
  report.status = 'PASS';
} catch (error) {report.error = {name: error.name, message: redact(error.message), stack: redact(error.stack)};}
finally {
  sealed = true;
  try {await bounded(() => Promise.allSettled(observerTasks), 2000, 'Browser observer preclose');} catch (error) {report.observer_preclose_error = redact(error.message);}
  try {await bounded(() => browser?.close(), 10000, 'Browser close');} catch (error) {report.browser_close_error = redact(error.message); report.status = 'FAIL';}
  try {await bounded(() => Promise.allSettled(observerTasks), 21000, 'Browser observer final drain');} catch (error) {report.observer_drain_error = redact(error.message); report.status = 'FAIL';}
  report.browser_capture = {rows: report.browser_http.length, bytes: browserBytes, pending: pending.size,
    errors: report.browser_http.filter(row => row.state !== 'complete' || row.metadata_error).length, sealed: true, limits: plan.response_limits};
  if (report.browser_capture.errors || pending.size || report.browser_limit_exceeded) report.status = 'FAIL';
  await save('report.json', report);
  await owned(); await writeFile(donePath, JSON.stringify({observer_status: report.status, session_id: hold.session_id, nonce: hold.nonce,
    report: resolve(output, 'report.json'), report_sha256: sha(await readFile(resolve(output, 'report.json')))}) + '\n', {flag: 'wx', mode: 0o600});
  console.log(JSON.stringify({status: report.status, phases: report.phases.length, browser_http: report.browser_http.length, error: report.error?.message, report: resolve(output, 'report.json')}));
  process.exitCode = report.status === 'PASS' ? 0 : 1;
}
