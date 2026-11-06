// Model/browser contracts with explicit logical sessions and synthetic pixels.
// This test does not run firmware and is not virtual-device acceptance evidence.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, mkdir} from 'node:fs/promises';
import {dirname, extname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const harness = `<!doctype html><html><head><meta charset="utf-8">
<style>body{margin:0}#host{width:1200px;height:700px}.observatory-device-label,.observatory-group-label{background:white;border:1px solid #cddde6;padding:5px;font:11px sans-serif}</style>
<script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script>
</head><body><div id="host"></div></body></html>`;
const mime = {'.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.css': 'text/css'};
const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/__scene__') {response.setHeader('Content-Type', 'text/html'); response.end(harness); return;}
    if (pathname === '/favicon.ico') {response.writeHead(204); response.end(); return;}
    const path = resolve(root, '.' + decodeURIComponent(pathname));
    if (!path.startsWith(root + '/')) {response.writeHead(403); response.end(); return;}
    response.setHeader('Content-Type', mime[extname(path)] || 'application/octet-stream'); response.end(await readFile(path));
  } catch {response.writeHead(404); response.end();}
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
try {
  browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  const page = await browser.newPage({viewport: {width: 1200, height: 700}}), errors = [], writes = [];
  const screenshotDirectory = process.env.M5_OBSERVATORY_SCENE_OUT;
  if (screenshotDirectory) await mkdir(screenshotDirectory, {recursive: true});
  await page.exposeFunction('__captureScene', async name => {
    if (screenshotDirectory) await page.screenshot({path: resolve(screenshotDirectory, `${name}.png`)});
  });
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {if (request.method() !== 'GET') writes.push(request.method());});
  await page.goto(`http://127.0.0.1:${server.address().port}/__scene__`);
  const result = await page.evaluate(async () => {
    const {ObservatoryScene} = await import('/platform/web/observatory-scene.js');
    const core = await (await fetch('/devices/esp32-s3/cores3/device.json')).json();
    const atom = await (await fetch('/devices/esp32-s3/atoms3/device.json')).json();
    const selections = [], sceneErrors = [];
    const scene = window.scene = new ObservatoryScene(document.querySelector('#host'), {onSelect: id => selections.push(id), onError: error => sceneErrors.push(error.message)});
    const metadata = new Map([['cores3', core], ['atoms3', atom]]);
    const unit = {id: 'relay-a', unit_id: '2relay', port_id: 'port-a', visual_port: 'grove'};
    const sessions = [
      {session_id: 'same-board-a', device_id: 'cores3', state: 'running', firmware_sha256: 'a'.repeat(64), created_at: '2026-11-06T00:00:00Z', serial_bytes: 11, units: [unit], management_binding: {preview_id: 'fixture', session_id: 'same-board-a'}},
      {session_id: 'same-board-b', device_id: 'cores3', state: 'running', firmware_sha256: 'a'.repeat(64), created_at: '2026-11-06T00:00:01Z', serial_bytes: 12, units: []},
      {session_id: 'other-model-c', device_id: 'atoms3', state: 'stopping', created_at: '2026-11-06T00:00:02Z', serial_bytes: 0, units: []},
      {session_id: 'same-board-d', device_id: 'cores3', state: 'running', created_at: '2026-11-06T00:00:03Z', serial_bytes: 14, units: []},
    ];
    await scene.setSessions(sessions, metadata);
    const before = scene.snapshot();
    const record = scene.records.get('same-board-a'), other = scene.records.get('same-board-b');
    const sameHostScale = [record.model.root.scale.x, other.model.root.scale.x];
    const pixels = record.model.find('lcd', 'display');
    const neutral = pixels.getPixel(10, 10);
    const canvas = document.createElement('canvas'); canvas.width = pixels.width; canvas.height = pixels.height;
    const context = canvas.getContext('2d'); context.fillStyle = '#ff0000'; context.fillRect(0, 0, canvas.width, canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve));
    await scene.setFrame(record.id, blob);
    const red = pixels.getPixel(10, 10), independent = other.model.find('lcd', 'display').getPixel(10, 10);
    scene.setUnits(record.id, {session_id: record.id, source: 'live', units: [{...unit, available: true,
      properties: {'output-1-level': true, 'output-2-level': false}, errors: {}}]});
    const led = record.model.find('grove/led-1', 'led');
    const unitObserved = {known: led.runtimeKnown, state: led.getState()};
    const rejected = scene.setUnits(record.id, {session_id: other.id, units: []});
    const originalPosition = record.object.position.toArray();
    await scene.setSessions([sessions[2], sessions[1], {...sessions[0], management_binding: {session_id: 'same-board-a', preview_id: 'fixture'}}, sessions[3]], metadata);
    const stablePosition = record.object.position.toArray();
    const sameOwner = scene.records.get(record.id) === record;
    const settle = async () => {
      const deadline = performance.now() + 5000;
      while (scene.cameraTween && performance.now() < deadline) await new Promise(resolve => setTimeout(resolve, 25));
    };
    scene.home(); await settle(); await window.__captureScene('overview');
    scene.focus(record.id);
    await settle(); await window.__captureScene('device-focus');
    const focusVisible = [...scene.records.values()].filter(item => item.object.visible).map(item => item.id);
    scene.focusGroup('cores3'); await settle(); await window.__captureScene('group-focus');
    const groupVisible = [...scene.records.values()].filter(item => item.object.visible).map(item => item.id);
    scene.home(); await settle();
    const homeVisible = [...scene.records.values()].filter(item => item.object.visible).map(item => item.id);
    scene.focus(record.id); await settle();
    const selected = scene.snapshot().selectedSessionId;
    scene.clearObservations(record.id);
    const cleared = {pixel: pixels.getPixel(10, 10), frame: scene.snapshot().sessions.find(row => row.session_id === record.id).frame_seq,
      known: led.runtimeKnown, units: scene.snapshot().sessions.find(row => row.session_id === record.id).units};
    // A decode that completes after context withdrawal cannot revive old pixels.
    let valid = true;
    const stale = scene.setFrame(record.id, blob, () => valid); valid = false;
    const staleApplied = await stale;
    const input = [];
    record.model.on('input', event => input.push(event));
    const cameraBeforeInput = scene.camera.position.toArray(), selectionBeforeInput = scene.selectedSessionId;
    const modelCanvas = scene.renderer.domElement;
    const interactiveElements = document.querySelector('#host').querySelectorAll('button,a,input,select,textarea,[tabindex],[role="button"]').length;
    const deviceLabel = document.querySelector(`[data-session-id="${record.id}"]`);
    const staticLabel = {tag: deviceLabel.tagName, tabIndex: deviceLabel.tabIndex, pointerEvents: getComputedStyle(deviceLabel).pointerEvents};
    deviceLabel.dispatchEvent(new MouseEvent('click', {bubbles: true}));
    modelCanvas.dispatchEvent(new PointerEvent('pointerdown', {pointerId: 1, clientX: 100, clientY: 100, button: 0}));
    modelCanvas.dispatchEvent(new PointerEvent('pointermove', {pointerId: 1, clientX: 300, clientY: 200, button: 0}));
    modelCanvas.dispatchEvent(new PointerEvent('pointerup', {pointerId: 1, clientX: 300, clientY: 200, button: 0}));
    modelCanvas.dispatchEvent(new WheelEvent('wheel', {deltaY: 500, cancelable: true}));
    modelCanvas.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
    window.dispatchEvent(new KeyboardEvent('keydown', {code: 'KeyP', key: 'p'}));
    const inputCount = input.length;
    const cameraAfterInput = scene.camera.position.toArray(), selectionAfterInput = scene.selectedSessionId;
    const screenWorld = record.model.find('lcd', 'display').panel.getWorldPosition(new (await import('three')).Vector3());
    const screenProjection = screenWorld.clone().project(scene.camera).toArray();
    const beforeDispose = scene.rendererInfo;
    await scene.setSessions([], metadata);
    await new Promise(resolve => setTimeout(resolve, 350));
    const emptied = scene.snapshot();
    // Logical display pressure only: tour between groups so admission really
    // swaps the 32 detailed models, then verify every existing bay stays put.
    const pressureSessions = ['cores3', 'atoms3'].flatMap(device_id => Array.from({length: 32}, (_, index) => ({
      session_id: `pressure-${device_id}-${index}`, device_id, state: 'running', created_at: '2026-11-06T00:01:00Z',
      serial_bytes: 0, units: [],
    })));
    scene.home(); await scene.setSessions(pressureSessions, metadata);
    const Vector3 = (await import('three')).Vector3;
    const positions = () => new Map([...scene.records].map(([id, item]) => [id, {
      local: item.object.position.toArray(), world: item.object.getWorldPosition(new Vector3()).toArray(),
    }]));
    const baseline = positions(), pressure = {max_delta: 0, mismatches: [], phases: []};
    const inspectPressure = phase => {
      const current = positions();
      for (const [id, before] of baseline) {
        const after = current.get(id);
        const delta = Math.max(...['local', 'world'].flatMap(space => before[space].map((value, index) => Math.abs(value - after[space][index]))));
        pressure.max_delta = Math.max(pressure.max_delta, delta);
        if (delta > 1e-8) pressure.mismatches.push({phase, id, before, after, delta});
      }
      pressure.phases.push({phase, detailed: scene.rendererInfo.detailedModels,
        core_models: [...scene.records.values()].filter(item => item.model && item.session.device_id === 'cores3').length,
        atom_models: [...scene.records.values()].filter(item => item.model && item.session.device_id === 'atoms3').length});
    };
    inspectPressure('initial-core-budget');
    scene.focusGroup('atoms3'); await scene.setSessions(pressureSessions, metadata); inspectPressure('atom-group-tour');
    scene.home(); await scene.setSessions(pressureSessions, metadata); inspectPressure('back-to-overview');
    scene.focus('pressure-atoms3-31'); await scene.setSessions(pressureSessions, metadata); inspectPressure('outside-budget-device-tour');
    scene.dispose();
    return {before, neutral, red, independent, unitObserved, rejected, originalPosition, stablePosition,
      selected, sameOwner, sameHostScale, focusVisible, groupVisible, homeVisible,
      cleared, staleApplied, inputCount, selections, interactiveElements, staticLabel,
      cameraBeforeInput, cameraAfterInput, selectionBeforeInput, selectionAfterInput,
      screenProjection, beforeDispose, emptied, pressure,
      disposed: scene.rendererInfo, canvasesAfter: document.querySelectorAll('canvas').length, sceneErrors};
  });
  assert.equal(result.before.renderer.contexts, 1);
  assert.equal(result.before.renderer.detailedModels, 4);
  assert.deepEqual(result.before.sessions.map(row => row.group_id), ['cores3', 'cores3', 'atoms3', 'cores3']);
  assert.deepEqual(result.before.sessions[0].attached_units, ['relay-a']);
  assert.deepEqual(result.neutral, [0, 0, 0]); assert.deepEqual(result.red, [255, 0, 0]);
  assert.deepEqual(result.independent, [0, 0, 0], 'same-model instances must not share their dynamic screen');
  assert.equal(result.unitObserved.known, true); assert.equal(result.rejected, false);
  assert.deepEqual(result.stablePosition, result.originalPosition, 'response ordering cannot move stable slots');
  assert.equal(result.sameOwner, true, 'binding object key order must not recreate the model owner');
  assert.equal(result.sameHostScale[0], result.sameHostScale[1], 'attaching a Unit must not shrink a same-model host');
  assert.deepEqual(result.focusVisible, ['same-board-a']);
  assert.deepEqual(result.groupVisible, ['same-board-a', 'same-board-b', 'same-board-d']);
  assert.deepEqual(result.homeVisible, ['same-board-a', 'same-board-b', 'other-model-c', 'same-board-d']);
  assert.equal(result.selected, 'same-board-a');
  assert.deepEqual(result.cleared, {pixel: [0, 0, 0], frame: 0, known: false, units: []});
  assert.equal(result.staleApplied, false); assert.equal(result.inputCount, 0);
  assert.deepEqual(result.selections, []);
  assert.equal(result.interactiveElements, 0);
  assert.deepEqual(result.staticLabel, {tag: 'DIV', tabIndex: -1, pointerEvents: 'none'});
  assert.deepEqual(result.cameraAfterInput, result.cameraBeforeInput, 'display-only scene must ignore pointer/wheel gestures');
  assert.equal(result.selectionAfterInput, result.selectionBeforeInput, 'display-only labels cannot change the automatic tour');
  assert.ok(result.screenProjection.every(Number.isFinite));
  assert.equal(result.emptied.sessions.length, 0); assert.equal(result.emptied.renderer.detailedModels, 0);
  assert.ok(result.pressure.max_delta <= 1e-8, JSON.stringify(result.pressure.mismatches.slice(0, 5)));
  assert.deepEqual(result.pressure.phases, [
    {phase: 'initial-core-budget', detailed: 32, core_models: 32, atom_models: 0},
    {phase: 'atom-group-tour', detailed: 32, core_models: 0, atom_models: 32},
    {phase: 'back-to-overview', detailed: 32, core_models: 32, atom_models: 0},
    {phase: 'outside-budget-device-tour', detailed: 32, core_models: 31, atom_models: 1},
  ]);
  assert.equal(result.disposed.disposed, true); assert.equal(result.canvasesAfter, 0);
  assert.deepEqual(result.sceneErrors, []); assert.deepEqual(errors, []); assert.deepEqual(writes, []);
  console.log('observatory-scene browser/model contracts passed (no firmware execution)');
} finally {
  await browser?.close(); await new Promise(resolve => server.close(resolve));
}
