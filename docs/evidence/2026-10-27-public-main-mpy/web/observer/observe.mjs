// Root hands off one already-running managed Preview. No allocation or raw
// controller writes. Every write is made by the actual product's Web controls.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';

const script = fileURLToPath(import.meta.url), root = resolve(dirname(script), '../..');
const sha = value => createHash('sha256').update(value).digest('hex');
const options = {};
for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (['--execute', '--plan'].includes(arg)) options[arg] = true;
  else if (['--handoff', '--out-dir'].includes(arg)) {assert.ok(process.argv[i + 1]); options[arg] = process.argv[++i];}
  else throw Error(`Unknown option: ${arg}`);
}
const paths = ['platform/web/sessions.html', 'platform/web/sessions.js', 'platform/web/preview-client.js',
  'platform/web/uiflow-main-loader.js', 'platform/web/program-panel.js', 'platform/web/program-panel.css',
  'platform/web/unit-panel.js', 'platform/web/model-shell.js', 'platform/web/unit-annotations.js',
  'platform/web/unit-visual-mappings.js', 'platform/tools/preview_service.py', 'platform/tools/uiflow_main_loader.py',
  'platform/tools/device_service.py', '.work/main-mpy-web-acceptance-20261027/observe.mjs'];
const fingerprints = async () => Object.fromEntries(await Promise.all(paths.map(async path => [path, sha(await readFile(resolve(root, path)))])));
const plan = {status: 'NOT RUN', api_contacted: false, guests_started: 0, hardware: 'NOT RUN',
  scope: 'Actual sessions page, PreviewProgramPanel, mounted PIR+frame, repeated immutable MPY Run and explicit new main.py recovery.',
  phases: ['identity', 'load-binary', 'web-run', 'web-repeat', 'pir-true', 'pir-false', 'cancel', 'new-main-source', 'source-run'],
  mutations: 'Product UI only: one owned Preview Run/cancel/input and new program-revision for recovery; never allocate/reset/stop.',
  instrumentation: 'Append-only export of hash-verified sessions.js state/SessionVisual; no API substitution or synthetic Unit/frame values.',
  execution_arguments: ['--execute', '--handoff <root-owned.json>', '--out-dir <fresh-directory>'],
  handoff_fields: ['session_id', 'preview_id', 'owner_epoch', 'pid', 'firmware_sha256', 'worker_generation', 'service_pid',
    'runtime_sha256', 'nonce', 'owner_id', 'count', 'binary_revision_id', 'binary_file_sha256', 'pir_id', 'source_restore_file', 'source_restore_sha256'],
  source_sha256: await fingerprints()};
if (!options['--execute'] || options['--plan']) {console.log(JSON.stringify(plan, null, 2)); process.exit(0);}
assert.ok(options['--handoff'] && options['--out-dir']);
const handoffBytes = await readFile(resolve(options['--handoff'])); assert.ok(handoffBytes.length < 131072);
const hold = JSON.parse(handoffBytes), output = resolve(options['--out-dir']);
for (const key of ['session_id', 'preview_id', 'owner_epoch', 'nonce']) assert.match(hold[key] || '', /^[0-9a-f]{32}$/);
for (const key of ['firmware_sha256', 'runtime_sha256', 'binary_revision_id', 'source_restore_sha256']) assert.match(hold[key] || '', /^[0-9a-f]{64}$/);
for (const key of ['pid', 'worker_generation', 'service_pid', 'owner_id', 'count']) assert.ok(Number.isSafeInteger(hold[key]) && hold[key] > 0);
assert.ok(typeof hold.pir_id === 'string' && hold.pir_id && hold.source_restore_file);
const sourceBytes = await readFile(resolve(hold.source_restore_file)); assert.equal(sha(sourceBytes), hold.source_restore_sha256);
const source = new TextDecoder('utf-8', {fatal: true}).decode(sourceBytes);
assert.ok(source.includes(hold.nonce), 'Recovery source must explicitly verify the seed VM nonce');
await mkdir(output, {recursive: false});
const save = (name, value) => writeFile(resolve(output, name), JSON.stringify(value, null, 2) + '\n', {mode: 0o600});
const token = (await readFile(resolve(root, hold.token_file || '.work/preview-control-token'), 'utf8')).trim(); assert.ok(token);
const report = {schema_version: 1, category: 'actual-main-mpy-preview-web-acceptance', status: 'FAIL',
  captured_at: new Date().toISOString(), hardware: 'NOT RUN', handoff: hold, handoff_sha256: sha(handoffBytes),
  source_sha256: await fingerprints(), phases: [], http: [], browser_http: [], mutations: [], forbidden: [], page_errors: [],
  instrumentation: plan.instrumentation, snapshot_semantics: 'Independent stable-stage HTTP/controller, serial, frame and mounted samples; not atomic.'};
await writeFile(resolve(output, 'observer.executed.mjs'), await readFile(script), {mode: 0o600});
await writeFile(resolve(output, 'source-restore.py'), sourceBytes, {mode: 0o600});
const base = 'http://127.0.0.1:8787', prefix = `/api/v1/previews/${hold.preview_id}`;
let browser, page, card, sealed = false;
let expectedEntryCount = hold.count;
const tasks = [];
const clean = value => String(value).replace(/Bearer\s+[^\s"']+/gi, 'Bearer [redacted]').slice(0, 8000);
const selectedHeaders = headers => Object.fromEntries(Object.entries(headers).filter(([key]) => ['content-type', 'etag'].includes(key.toLowerCase())
  || key.toLowerCase().startsWith('x-frame-') || ['x-preview-id', 'x-run-id'].includes(key.toLowerCase())));
async function bounded(action, milliseconds = 15000) {
  let timer;
  try {return await Promise.race([Promise.resolve().then(action), new Promise((_, reject) => {timer = setTimeout(() => reject(Error('Bounded observer timeout')), milliseconds);})]);}
  finally {clearTimeout(timer);}
}
async function until(action, predicate, milliseconds = 60000) {
  let last, end = Date.now() + milliseconds;
  while (Date.now() < end) {last = await action(); if (predicate(last)) return last; await delay(125);}
  throw Error(`Observation timeout: ${JSON.stringify(last).slice(-3000)}`);
}
async function get(path, binary = false) {
  const row = {index: report.http.length, path, method: 'GET', observed_at: new Date().toISOString()}; report.http.push(row);
  const response = await fetch(`${base}/api/v1/${path}`, {headers: {Authorization: `Bearer ${token}`}, redirect: 'error', signal: AbortSignal.timeout(15000)});
  const bytes = Buffer.from(await response.arrayBuffer()); assert.ok(bytes.length <= 32 * 1024 * 1024);
  Object.assign(row, {status: response.status, bytes: bytes.length, sha256: sha(bytes), headers: selectedHeaders(Object.fromEntries(response.headers)), body: `http-${row.index}.response`});
  await writeFile(resolve(output, row.body), bytes, {mode: 0o600}); await save(`http-${row.index}.json`, row);
  assert.equal(response.status, 200, `${path}: HTTP ${response.status}`);
  return binary ? {bytes, headers: row.headers} : JSON.parse(bytes);
}
async function sameVM() {
  const session = await get(`sessions/${hold.session_id}`);
  for (const key of ['pid', 'firmware_sha256']) assert.equal(session[key], hold[key]);
  assert.equal(session.worker.generation, hold.worker_generation); assert.equal(session.state, 'running');
  const binding = session.management_binding;
  assert.equal(binding.preview_id, hold.preview_id); assert.equal(binding.owner_epoch, hold.owner_epoch);
  assert.equal(session.program_capabilities.status, 'verified'); assert.equal(session.program_capabilities.mpy_entrypoint, true);
  return session;
}
async function mounted() {
  return page.evaluate(({sid, pir}) => {
    const visual = window.__mainMpyProbe?.state.visuals.get(sid), panel = visual?.unitPanel, item = panel?.mounted.get(pir);
    if (!visual?.shell || !item) return null;
    const module = visual.shell.model.port(item.port).module, annotation = visual.shell.unitAnnotations?.items.get(item.port);
    const display = visual.shell.display;
    return {session_id: panel.session.session_id, pid: panel.session.pid, worker: panel.session.worker,
      firmware_sha256: panel.session.firmware_sha256, bindings: structuredClone(panel.bindingsByUnit),
      unit: structuredClone(panel.states.get(pir)), state_source: panel.stateSource, frozen_definitions: panel.frozenDefinitions,
      port: item.port, module: {class_name: module.constructor.name, meta_id: module.constructor.meta?.id || null,
        annotation_owns_actual_anchor: !!annotation && visual.shell.model.find(`${item.port}/sensor`) === annotation.anchor,
        anchor_role: visual.shell.model.find(`${item.port}/sensor`)?.meta?.role || null},
      annotation: annotation ? {text: annotation.note.textContent, signature: annotation.signature,
        values: Object.fromEntries([...annotation.note.querySelectorAll('[data-annotation-field]')].map(node => [node.dataset.annotationField, node.textContent]))} : null,
      frame: {metadata: visual.frameMetadata, sha256: visual.lastFrameHash, width: display?.width, height: display?.height,
        center: display ? [...display.getPixel(Math.floor(display.width / 2), Math.floor(display.height / 2))].slice(0, 3) : null},
      editor: {entrypoint: visual.programPanel?.workspace?.entrypoint, revision_id: visual.programPanel?.workspace?.revisionId,
        preview: structuredClone(visual.previewClient?.snapshot()?.preview), source: visual.programPanel?.source.value}};
  }, {sid: hold.session_id, pir: hold.pir_id});
}
async function currentRun() {
  const preview = await get(`previews/${hold.preview_id}`), id = preview.active_run_id;
  if (!id) return {preview, run: null};
  return {preview, run: await get(`previews/${hold.preview_id}/runs/${id}`)};
}
function guestRecords(serial) {
  return serial.data.split(/\r?\n/).filter(line => line.startsWith('PUBLIC_MAIN_MPY '))
    .map(line => JSON.parse(line.slice('PUBLIC_MAIN_MPY '.length)));
}
function checkIdentity(value, path) {
  assert.equal(value.nonce, hold.nonce); assert.equal(value.count, expectedEntryCount); assert.equal(value.owner_id, hold.owner_id);
  assert.equal(value.name, '__main__'); assert.equal(value.file, `${path}/main.mpy`);
  assert.equal(value.dep_value, 29); assert.equal(value.dep_file, `${path}/dep.mpy`);
  assert.ok(Number.isSafeInteger(value.main_id) && value.main_id > 0 && value.main_id !== hold.owner_id);
  assert.equal(value.sys_main_id, value.main_id); assert.equal(value.import_main_id, value.main_id);
}
function pngMetrics(path) {
  return JSON.parse(execFileSync('/opt/miniconda3/bin/python3.12', ['-c',
    'import json,sys;from PIL import Image;im=Image.open(sys.argv[1]);im.load();assert im.format=="PNG";print(json.dumps({"size":list(im.size),"center":list(im.convert("RGB").getpixel((im.width//2,im.height//2)))}))', path],
    {encoding: 'utf8', timeout: 15000}));
}
async function capture(label, expectedRun = null, expectedMotion = null) {
  const row = {label, observed_at: new Date().toISOString(), http_start: report.http.length}; report.phases.push(row);
  row.session = await sameVM(); row.execution = await get(`sessions/${hold.session_id}/program`);
  if (expectedRun) assert.equal(row.execution.program.execution_id, expectedRun.execution_id);
  row.units = await get(`sessions/${hold.session_id}/units`);
  const unit = row.units.units.find(value => value.id === hold.pir_id);
  assert.equal(row.units.source, 'live'); assert.equal(unit.available, true); assert.equal(unit.source, 'guest-qom'); assert.deepEqual(unit.errors, {});
  if (expectedMotion !== null) assert.equal(unit.properties.motion, expectedMotion);
  const binary = row.execution.program.entrypoint === 'main.mpy', motion = expectedMotion ?? unit.properties.motion;
  const expectedCenter = binary ? (hold.frame_center_by_motion?.[String(motion)] ?? (motion ? [255, 255, 255] : [0, 255, 0]))
    : hold.source_restore_center ?? [0, 0, 255];
  row.mounted = await until(mounted, value => value?.unit?.available && value.unit.source === 'guest-qom'
    && value.state_source === 'live' && value.frozen_definitions === true
    && (expectedMotion === null || value.unit.properties.motion === expectedMotion)
    && JSON.stringify(value.frame.center) === JSON.stringify(expectedCenter)
    && (!expectedRun || value.frame.metadata?.['x-frame-execution-id'] === expectedRun.execution_id));
  assert.equal(row.mounted.session_id, hold.session_id); assert.equal(row.mounted.pid, hold.pid); assert.equal(row.mounted.worker.generation, hold.worker_generation);
  assert.deepEqual(row.mounted.bindings, {}); assert.ok(row.mounted.annotation, 'Actual mounted PIR annotation required');
  assert.equal(row.mounted.module.meta_id, 'm5.unit.pir.grove'); assert.equal(row.mounted.module.anchor_role, 'visual-anchor');
  assert.equal(row.mounted.module.annotation_owns_actual_anchor, true);
  if (expectedMotion !== null) assert.equal(row.mounted.annotation.values.motion, String(expectedMotion));
  const serialOffset = row.execution.program.serial_offset; assert.ok(Number.isSafeInteger(serialOffset) && serialOffset >= 0);
  row.serial = await until(() => get(`sessions/${hold.session_id}/serial?offset=${serialOffset}&limit=1048576`), value => {
    try {
      const marker = `__M5_EXEC_${expectedRun.execution_id}__:${binary ? 'LOAD' : 'START'}`;
      const start = value.data.indexOf(marker); if (start < 0) return false;
      const records = guestRecords({data: value.data.slice(start + marker.length)});
      if (binary) {
        const entry = records.find(record => record.kind === 'mpy-entry'), samples = records.filter(record => record.kind === 'mpy-sample');
        if (!entry || !samples.length) return false;
        checkIdentity(entry, row.execution.program.deployment.package_path); assert.equal(entry.guard, true);
        const sample = samples.at(-1); checkIdentity(sample, row.execution.program.deployment.package_path);
        if (sample.motion !== motion) return false;
        const earlier = [...report.phases].reverse().find(phase => phase !== row && phase.execution?.program.execution_id === expectedRun.execution_id && phase.guest?.sample);
        if (earlier && sample.sequence <= earlier.guest.sample.sequence) return false;
        row.guest = {entry, sample}; return true;
      }
      const recovery = records.find(record => record.kind === 'source-recovery'); if (!recovery) return false;
      assert.equal(recovery.nonce, hold.nonce); assert.equal(recovery.count, expectedEntryCount); assert.equal(recovery.owner_id, hold.owner_id);
      assert.equal(recovery.expected_owner_id, hold.owner_id); assert.equal(recovery.owner_restored, true);
      row.guest = {recovery}; return true;
    } catch {return false;}
  });
  const frame = await get(`sessions/${hold.session_id}/frame.png?max_age_ms=1`, true);
  assert.equal(frame.headers['x-frame-sha256'], sha(frame.bytes));
  if (expectedRun) {assert.equal(frame.headers['x-frame-execution-id'], expectedRun.execution_id); assert.equal(frame.headers['x-frame-revision-id'], expectedRun.revision_id);}
  const frameName = `${label}-frame.png`; await writeFile(resolve(output, frameName), frame.bytes);
  row.frame = {path: frameName, sha256: sha(frame.bytes), headers: frame.headers, metrics: pngMetrics(resolve(output, frameName))};
  assert.deepEqual(row.frame.metrics.center, expectedCenter); assert.deepEqual(row.mounted.frame.center, expectedCenter);
  const stage = card.locator('.three-device-stage'); await stage.scrollIntoViewIfNeeded();
  await page.evaluate(id => window.__mainMpyProbe.state.visuals.get(id).shell.viewer.requestRender(), hold.session_id);
  await delay(200); await stage.screenshot({path: resolve(output, `${label}-mounted.png`)});
  await card.screenshot({path: resolve(output, `${label}-card.png`)});
  row.http_end = report.http.length; await save(`${label}.json`, row); console.log(`MAIN_MPY_WEB_PHASE ${label}`); return row;
}
async function webRun(label, previousRunId, revision) {
  await card.locator('[data-program-run]').click();
  const row = await until(currentRun, value => value.run && value.run.run_id !== previousRunId && value.run.revision_id === revision
    && ['running', 'completed'].includes(value.run.state));
  expectedEntryCount += 1;
  await capture(label, row.run); return row.run;
}
try {
  report.health = await get('health'); assert.equal(report.health.capacity.worker.pid, hold.service_pid);
  assert.equal(report.health.capacity.worker.generation, hold.worker_generation);
  report.initial_session = await sameVM();
  report.runtime = JSON.parse(execFileSync('/opt/miniconda3/bin/python3.12', ['-c',
    'import ctypes,hashlib,json,pathlib,sys;b=ctypes.create_string_buffer(4096);assert ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath(int(sys.argv[1]),b,len(b))>0;p=pathlib.Path(b.value.decode());print(json.dumps({"name":p.name,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}))', String(hold.pid)], {encoding: 'utf8', timeout: 15000}));
  assert.equal(report.runtime.sha256, hold.runtime_sha256);
  const pack = await get(`program-revisions/${hold.binary_revision_id}/files`);
  assert.equal(pack.revision.entrypoint, 'main.mpy'); assert.equal(pack.revision.revision_id, hold.binary_revision_id);
  for (const [path, digest] of Object.entries(hold.binary_file_sha256)) assert.equal(sha(Buffer.from(pack.files[path].data, 'base64')), digest);
  report.binary_checkpoint = pack;
  const {chromium} = createRequire(resolve(root, 'platform/tests/package.json'))('playwright');
  browser = await chromium.launch({executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  page = await browser.newPage({viewport: {width: 1440, height: 1200}}); report.browser_version = browser.version();
  await page.addInitScript(value => sessionStorage.setItem('m5-service-token', value), token);
  page.on('pageerror', error => report.page_errors.push(clean(error.message)));
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method();
    if (method === 'GET') return await route.continue();
    const allowed = method === 'POST' && (path === '/api/v1/program-revisions' || path === `${prefix}/runs`
      || path === `${prefix}/input` || new RegExp(`^${prefix}/runs/[0-9a-f]{32}/cancel$`).test(path));
    const row = {path, method, body: request.postDataJSON(), observed_at: new Date().toISOString()};
    if (allowed) {report.mutations.push(row); await route.continue();}
    else {report.forbidden.push(row); await route.abort('blockedbyclient');}
  });
  page.on('response', response => {
    if (sealed || !new URL(response.url()).pathname.startsWith('/api/v1/')) return;
    const row = {index: report.browser_http.length, path: new URL(response.url()).pathname, status: response.status(), method: response.request().method()};
    report.browser_http.push(row);
    tasks.push((async () => {try {
      if (row.status === 304) row.body_absent = 'HTTP 304 no response entity';
      else {const bytes = await bounded(() => response.body(), 5000); assert.ok(bytes.length <= 2 * 1024 * 1024);
        Object.assign(row, {bytes: bytes.length, sha256: sha(bytes), body: `browser-${row.index}.response`}); await writeFile(resolve(output, row.body), bytes, {mode: 0o600});
        if (row.status === 200 && row.path.endsWith('/frame.png') && !bytes.length) row.error = 'Optional browser observer returned empty PNG entity; not image evidence';}
      row.headers = selectedHeaders(await bounded(() => response.allHeaders(), 5000)); row.capture_status = row.error ? 'partial' : 'complete';
    } catch (error) {row.capture_status = 'partial'; row.error = clean(error.message);}
    await save(`browser-${row.index}.json`, row);})());
  });
  await page.route('**/platform/web/sessions.js*', async route => {
    const response = await route.fetch(), content = await response.text(); assert.equal(sha(content), report.source_sha256['platform/web/sessions.js']);
    await route.fulfill({response, body: content + '\nwindow.__mainMpyProbe={state,SessionVisual};\n'});
  });
  await page.goto(`${base}/platform/web/sessions.html`, {waitUntil: 'domcontentloaded'});
  card = page.locator(`[data-session-id="${hold.session_id}"]`); await card.waitFor();
  await page.waitForFunction(({sid, pir}) => window.__mainMpyProbe?.state.visuals.get(sid)?.unitPanel?.mounted.has(pir), {sid: hold.session_id, pir: hold.pir_id}, {timeout: 90000});
  await card.locator('[data-program-load]').click();
  await page.waitForFunction(id => window.__mainMpyProbe.state.visuals.get(id).programPanel.workspace?.entrypoint === 'main.mpy', hold.session_id);
  assert.equal(await card.locator('[data-program-source]').isVisible(), false); assert.equal(await card.locator('[data-program-run]').isEnabled(), true);
  const initial = (await currentRun()).run; assert.equal(initial.revision_id, hold.binary_revision_id); await capture('load-binary', initial);
  const first = await webRun('web-run', initial.run_id, hold.binary_revision_id);
  const repeated = await webRun('web-repeat', first.run_id, hold.binary_revision_id);
  assert.equal(report.mutations.filter(row => row.path === '/api/v1/program-revisions').length, 0);
  for (const motion of [true, false]) {
    const control = card.locator(`[data-input-field="motion"]`); await control.setChecked(motion);
    await until(async () => (await get(`sessions/${hold.session_id}/units`)).units.find(row => row.id === hold.pir_id), value => value.properties.motion === motion);
    await capture(`pir-${motion}`, repeated, motion);
  }
  await card.locator('[data-program-cancel]').click();
  report.cancelled = await until(() => get(`previews/${hold.preview_id}/runs/${repeated.run_id}`), row => row.state === 'cancelled');
  assert.equal(report.cancelled.interrupt_ack, 'confirmed');
  const writes = report.mutations.length;
  await card.locator('[data-program-new-source]').click();
  assert.equal(await card.locator('[data-program-source]').isVisible(), true); assert.equal(report.mutations.length, writes);
  await card.locator('[data-program-source]').fill(source);
  await card.locator('[data-program-run]').click();
  const recovery = await until(currentRun, value => value.run && value.run.revision_id !== hold.binary_revision_id
    && ['running', 'completed'].includes(value.run.state));
  const saved = report.mutations.filter(row => row.path === '/api/v1/program-revisions'); assert.equal(saved.length, 1);
  assert.equal(saved[0].body.entrypoint, 'main.py'); assert.equal(Object.hasOwn(saved[0].body.files, 'main.mpy'), false);
  for (const [path, file] of Object.entries(pack.files)) if (path !== 'main.mpy') assert.deepEqual(saved[0].body.files[path], file);
  await capture('source-recovery', recovery.run);
  const finalPackage = await get(`program-revisions/${hold.binary_revision_id}/files`); assert.deepEqual(finalPackage, pack);
  report.evidence_before_handoff_return = await get(`sessions/${hold.session_id}/evidence`, true);
  await writeFile(resolve(output, 'evidence-before-handoff-return.zip'), report.evidence_before_handoff_return.bytes);
  report.evidence_before_handoff_return = {sha256: sha(report.evidence_before_handoff_return.bytes), path: 'evidence-before-handoff-return.zip'};
  assert.deepEqual(report.forbidden, []); assert.deepEqual(report.page_errors, []);
  report.source_sha256_after = await fingerprints(); assert.deepEqual(report.source_sha256_after, report.source_sha256);
  report.status = 'PASS';
} catch (error) {report.error = {name: error.name, message: clean(error.message), stack: clean(error.stack)};}
finally {
  sealed = true;
  try {await bounded(() => Promise.allSettled(tasks), 3000);} catch (error) {report.browser_capture_preclose = clean(error.message);}
  try {await bounded(() => browser?.close(), 10000);} catch (error) {report.browser_close_error = clean(error.message); report.status = 'FAIL';}
  try {await bounded(() => Promise.allSettled(tasks), 12000);} catch (error) {report.browser_capture_shutdown = clean(error.message);}
  report.browser_capture = {scope: 'Optional exact response capture; direct GET/frame/mounted/serial acceptance is independent',
    responses: report.browser_http.length, partial: report.browser_http.filter(row => row.capture_status !== 'complete').length};
  report.last_observed_at = new Date().toISOString(); await save('report.json', report);
  console.log(JSON.stringify({status: report.status, phases: report.phases.length, mutations: report.mutations.length,
    error: report.error?.message, report: resolve(output, 'report.json')})); process.exitCode = report.status === 'PASS' ? 0 : 1;
}
