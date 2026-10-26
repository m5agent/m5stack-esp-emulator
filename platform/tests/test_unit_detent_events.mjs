// Real vendored components and product event/queue paths in a browser fixture.
// No firmware, controller, guest, electrical-polarity or hardware PASS is implied.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, extname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = resolve(process.env.M5_UNIT_DETENT_OUT || '/tmp/m5-unit-detent-events-test');
await mkdir(output, {recursive: true});
const device = JSON.parse(await readFile(resolve(root, 'devices/catalog.source.json'), 'utf8')).devices.find(item => item.id === 'sticks3');
const catalog = JSON.parse(await readFile(resolve(root, 'platform/units/catalog.json'), 'utf8'));
const profiles = JSON.parse(await readFile(resolve(root, 'platform/units/runtime-profiles.json'), 'utf8')).units;
const definition = catalog.units.find(item => item.id === '8encoder');
const inventory = {
  units: [{...definition, runtime: profiles['8encoder']}],
  hosts: JSON.parse(await readFile(resolve(root, 'platform/units/host-ports.json'), 'utf8')).hosts.filter(item => item.device_id === device.id),
};
const manifest = JSON.parse(await readFile(resolve(root, 'platform/web/vendor/m5stack-models/vendor-manifest.json'), 'utf8'));
const sources = [
  'platform/web/model-shell.js', 'platform/web/unit-panel.js', 'platform/web/unit-visual-mappings.js',
  'platform/tests/test_unit_detent_events.mjs',
  'platform/web/vendor/m5stack-models/src/core/components/Button.js',
  'platform/web/vendor/m5stack-models/src/units/8encoder/index.js',
];
const report = {
  category: 'browser-vendor-detent-event-fixture', status: 'FAIL', captured_at: new Date().toISOString(),
  vendor_commit: manifest.source_commit, hardware_execution: 'NOT RUN', guest_execution: 'NOT RUN',
  electrical_switch_mapping: 'NOT VERIFIED; both polarities below are explicit synthetic fixtures',
  source_sha256: Object.fromEntries(await Promise.all(sources.map(async path =>
    [path, createHash('sha256').update(await readFile(resolve(root, path))).digest('hex')]))),
  checks: [], page_errors: [], missing_assets: [],
};
const harness = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="/platform/web/three-device-viewer.css">
<style>html,body{margin:0}#host{width:900px;height:700px}.three-device-root,.three-device-stage{min-height:700px!important}</style>
<script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script>
</head><body><div id="host"></div><div id="panel"></div></body></html>`;
const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/harness') { response.setHeader('Content-Type', 'text/html'); response.end(harness); return; }
    const path = resolve(root, `.${decodeURIComponent(pathname)}`);
    if (!path.startsWith(root + '/')) { response.writeHead(403).end(); return; }
    response.setHeader('Content-Type', {'.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.json': 'application/json'}[extname(path)] || 'application/octet-stream');
    response.end(await readFile(path));
  } catch { response.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
try {
  browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  report.browser_version = browser.version();
  const page = await browser.newPage({viewport: {width: 1100, height: 850}});
  page.on('pageerror', error => report.page_errors.push(error.message));
  page.on('response', response => {
    if (response.status() >= 400 && !response.url().endsWith('/favicon.ico')) report.missing_assets.push(response.url());
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/harness`, {waitUntil: 'networkidle'});
  await page.evaluate(async device => {
    const {createModelShell} = await import('/platform/web/model-shell.js');
    const {Button} = await import('/platform/web/vendor/m5stack-models/src/core/components/Button.js');
    window.shell = await createModelShell(document.querySelector('#host'), device, {live: true});
    await window.shell.attachUnit('8encoder');
    window.switchButton = window.shell.model.button('grove/switch');
    if (!(window.switchButton instanceof Button) || !window.switchButton.isLatching) throw new Error('Expected the actual vendored 8Encoder latching Button');
    window.events = [];
    window.shell.on('unit-input', event => window.events.push(structuredClone(event)));
    window.pointerEvents = [];
    for (const type of ['pointerdown', 'pointerup', 'pointercancel']) window.shell.viewer.renderer.domElement.addEventListener(type, event => {
      window.pointerEvents.push({type, isTrusted: event.isTrusted, pointerId: event.pointerId});
    });
  }, device);

  report.two_toggles = await page.evaluate(() => {
    const button = window.switchButton;
    button.press('first'); button.release('first');
    button.press('second'); button.release('second');
    return {events: window.events.splice(0), state: button.getState()};
  });
  assert.deepEqual(report.two_toggles.events.filter(event => event.action === 'down').map(event => event.position), [1, 0], 'actual vendor down events must carry the post-toggle detent');
  assert.deepEqual(report.two_toggles.events.map(event => event.action), ['down', 'up', 'click', 'down', 'up', 'click']);
  assert.equal(report.two_toggles.state.position, 0);
  report.checks.push('actual-vendor-down-contains-detent-1-then-0');

  report.source_ownership = await page.evaluate(() => {
    const button = window.switchButton;
    button.press('held'); button.press('held'); button.press('other');
    const afterRepeatedDown = {state: button.getState(), eventCount: window.events.length};
    button.release('unknown'); button.release('held');
    const afterPartialRelease = {state: button.getState(), eventCount: window.events.length};
    button.cancel('other'); button.cancel('other'); button.release('held');
    const afterCancel = {state: button.getState(), events: window.events.splice(0)};
    button.press('next'); button.release('next');
    return {afterRepeatedDown, afterPartialRelease, afterCancel, nextEvents: window.events.splice(0)};
  });
  for (const state of [report.source_ownership.afterRepeatedDown, report.source_ownership.afterPartialRelease]) {
    assert.deepEqual(state.state, {pressed: true, position: 1, latching: true});
    assert.equal(state.eventCount, 1);
  }
  assert.deepEqual(report.source_ownership.afterCancel.events.map(event => event.action), ['down', 'up']);
  assert.equal(report.source_ownership.afterCancel.events[1].cancelled, true);
  assert.deepEqual(report.source_ownership.afterCancel.state, {pressed: false, position: 1, latching: true});
  assert.equal(report.source_ownership.nextEvents[0].position, 0);
  report.checks.push('duplicate-and-multiple-sources-release-cancel-do-not-toggle-again');

  report.momentary_readback = await page.evaluate(async () => {
    const button = window.shell.model.button('grove/press-1');
    button.longPressMs = 20;
    button.press('first'); button.press('first'); button.press('second');
    button.release('first'); button.cancel('second'); button.release('second');
    const cancelled = window.events.splice(0);
    window.shell.applyVisualState({type: 'button-state', target: button.path, pressed: true});
    button.press('with-readback'); button.release('with-readback');
    const heldVisually = button.getState().pressed;
    const userEvents = window.events.splice(0);
    await new Promise(resolve => setTimeout(resolve, 60));
    const delayedEcho = window.events.splice(0);
    window.shell.applyVisualState({type: 'button-state', target: button.path, pressed: false});
    window.shell.applyVisualState({type: 'position', target: 'grove/switch', position: 1});
    window.shell.applyVisualState({type: 'position', target: 'grove/switch', position: 0});
    return {cancelled, userEvents, heldVisually, delayedEcho, outputEcho: window.events.splice(0), state: button.getState()};
  });
  assert.deepEqual(report.momentary_readback.cancelled.map(event => event.action), ['down', 'up']);
  assert.equal(report.momentary_readback.cancelled[1].cancelled, true);
  assert.deepEqual(report.momentary_readback.userEvents.map(event => event.action), ['down', 'up', 'click']);
  assert.ok([...report.momentary_readback.cancelled, ...report.momentary_readback.userEvents].every(event => !Object.hasOwn(event, 'position')), 'momentary events must retain their original shape');
  assert.equal(report.momentary_readback.heldVisually, true);
  assert.equal(report.momentary_readback.state.pressed, false);
  assert.deepEqual(report.momentary_readback.delayedEcho, []);
  assert.deepEqual(report.momentary_readback.outputEcho, []);
  report.checks.push('momentary-ownership-and-runtime-readback-remain-output-only');

  // Project geometry only to locate a real canvas hit. Input comes from the
  // browser mouse, through DeviceViewer raycast and the actual Button hooks.
  const locateSwitch = () => page.evaluate(async () => {
    const {Box3, Vector3} = await import('three');
    const viewer = window.shell.viewer, button = window.switchButton;
    viewer.setView('front', {duration: 0}); viewer.fit({padding: 1.15, duration: 0});
    viewer.scene.updateMatrixWorld(true); viewer.camera.updateMatrixWorld(true);
    const bounds = new Box3().setFromObject(button.cap), rect = viewer.renderer.domElement.getBoundingClientRect();
    for (const fx of [0.5, 0.25, 0.75]) for (const fy of [0.5, 0.25, 0.75]) {
      const projected = new Vector3(bounds.min.x + (bounds.max.x - bounds.min.x) * fx, bounds.min.y + (bounds.max.y - bounds.min.y) * fy, bounds.max.z).project(viewer.camera);
      const point = {clientX: rect.left + (projected.x + 1) * rect.width / 2, clientY: rect.top + (1 - projected.y) * rect.height / 2};
      if (viewer.pick(point)?.component === button) return {x: point.clientX, y: point.clientY};
    }
    throw new Error('Actual switch cap is not a visible raycast target');
  });
  const firstPoint = await locateSwitch();
  await page.mouse.move(firstPoint.x, firstPoint.y); await page.mouse.down();
  const pointerDown = await page.evaluate(() => window.events.at(-1));
  assert.equal(pointerDown.action, 'down'); assert.equal(pointerDown.position, 1);
  assert.match(pointerDown.source, /^pointer:/);
  await page.evaluate(() => window.shell.viewer.renderer.domElement.blur());
  await page.mouse.up();
  report.canvas_blur = await page.evaluate(() => ({events: window.events.splice(0), pointers: window.pointerEvents.splice(0), state: window.switchButton.getState()}));
  assert.deepEqual(report.canvas_blur.events.map(event => event.action), ['down', 'up']);
  assert.equal(report.canvas_blur.events[1].cancelled, true);
  assert.equal(report.canvas_blur.state.position, 1); assert.equal(report.canvas_blur.state.pressed, false);
  assert.ok(report.canvas_blur.pointers.some(event => event.type === 'pointerdown' && event.isTrusted));
  report.checks.push('trusted-canvas-pointer-down-and-blur-cancel-preserve-detent');

  const secondPoint = await locateSwitch();
  await page.mouse.click(secondPoint.x, secondPoint.y);
  report.canvas_click = await page.evaluate(() => ({events: window.events.splice(0), pointers: window.pointerEvents.splice(0), state: window.switchButton.getState()}));
  assert.deepEqual(report.canvas_click.events.map(event => event.action), ['down', 'up', 'click']);
  assert.equal(report.canvas_click.events[0].position, 0);
  assert.ok(report.canvas_click.pointers.every(event => event.isTrusted));
  const disposePoint = await locateSwitch();
  await page.mouse.move(disposePoint.x, disposePoint.y); await page.mouse.down();
  report.dispose = await page.evaluate(() => {
    window.shell.dispose();
    return {events: window.events.splice(0), state: window.switchButton.getState()};
  });
  await page.mouse.up();
  assert.deepEqual(report.dispose.events.map(event => event.action), ['down', 'up']);
  assert.equal(report.dispose.events[0].position, 1); assert.equal(report.dispose.events[1].cancelled, true);
  assert.equal(report.dispose.state.pressed, false); assert.equal(report.dispose.state.position, 1);
  report.checks.push('trusted-canvas-click-and-dispose-release-do-not-add-toggle');

  report.panel_mapping = await page.evaluate(async ({device, inventory}) => {
    const {createModelShell} = await import('/platform/web/model-shell.js');
    const {createUnitPanel} = await import('/platform/web/unit-panel.js');
    const shell = await createModelShell(document.querySelector('#host'), device, {live: true});
    const attachment = {id: 'synthetic-8encoder', unit_id: '8encoder', port_id: 'port-a', visual_port: 'grove'};
    const session = {session_id: 'synthetic-detent-session', device_id: device.id, state: 'running', units: [attachment]};
    const properties = Object.fromEntries(Object.entries({...inventory.units[0].inputs, ...inventory.units[0].outputs}).map(([field, schema]) => [field, structuredClone(schema.default)]));
    const unit = {...attachment, available: true, errors: {}, properties};
    const calls = [], events = [];
    const payload = () => structuredClone({source: 'browser-test-fixture', session_id: session.session_id, definitions: inventory.units, units: [unit]});
    const api = async (path, options = {}) => {
      if (path.startsWith('/api/v1/units?')) return inventory;
      if (path !== `/api/v1/sessions/${session.session_id}/${options.method === 'POST' ? 'unit-input' : 'units'}`) throw new Error(`Unexpected fixture API path: ${path}`);
      if (options.method === 'POST') {
        const body = JSON.parse(options.body);
        calls.push(body);
        Object.assign(unit.properties, body.values);
      }
      return payload();
    };
    const panel = await createUnitPanel(document.querySelector('#panel'), {session, shell, api});
    clearTimeout(panel.timer);
    const button = shell.model.button('grove/switch');
    shell.on('unit-input', event => { events.push(structuredClone(event)); panel.handleInput(event); });
    const tap = async source => {
      button.press(source); button.release(source);
      await Promise.all([...panel.queues.values()]);
    };
    await tap('unbound');
    panel.bindingsByUnit = {'8encoder': {switchPositions: {on: 0, off: 1}}};
    await tap('without-evidence');
    panel.bindingsByUnit = {'8encoder': {evidence: 'synthetic-invalid-detent-fixture', switchPositions: {on: 0, off: 0}}};
    await tap('invalid-detents');
    const rejected = {postCount: calls.length, events: events.splice(0)};
    const mapped = [];
    for (const on of [0, 1]) {
      unit.properties['switch-on'] = false;
      panel.bindingsByUnit = {'8encoder': {evidence: 'synthetic fixture only; physical polarity NOT VERIFIED', switchPositions: {on, off: 1 - on}}};
      panel.paint(unit);
      const before = calls.length;
      await tap(`mapped-on-${on}`); await tap(`mapped-off-${on}`);
      mapped.push({on, calls: calls.slice(before), events: events.splice(0), state: button.getState()});
    }
    const beforeReadback = {calls: calls.length, events: events.length};
    shell.applyVisualState({type: 'position', target: button.path, position: 0});
    shell.applyVisualState({type: 'position', target: button.path, position: 1});
    panel.paint(unit);
    await Promise.all([...panel.queues.values()]);
    const readbackEcho = {calls: calls.length - beforeReadback.calls, events: events.length - beforeReadback.events};
    panel.dispose(); shell.dispose();
    return {rejected, mapped, readbackEcho};
  }, {device, inventory});
  assert.equal(report.panel_mapping.rejected.postCount, 0, 'unbound, unevidenced and invalid mappings must not submit fixture input');
  assert.equal(report.panel_mapping.rejected.events.filter(event => event.action === 'down').length, 3);
  for (const result of report.panel_mapping.mapped) {
    assert.deepEqual(result.calls, [true, false].map(value => ({id: 'synthetic-8encoder', values: {'switch-on': value}})), 'actual captured events must pass through UnitPanel queue once per toggle');
    assert.deepEqual(result.events.filter(event => event.action === 'down').map(event => event.position), [result.on, 1 - result.on]);
    assert.deepEqual(result.events.map(event => event.action), ['down', 'up', 'click', 'down', 'up', 'click']);
    assert.equal(result.state.position, 1 - result.on); assert.equal(result.state.pressed, false);
  }
  assert.deepEqual(report.panel_mapping.readbackEcho, {calls: 0, events: 0});
  report.checks.push('unit-panel-queue-maps-real-events-only-with-explicit-synthetic-binding');
  report.checks.push('both-fixture-polarities-and-output-readback-zero-post-echo');
  assert.deepEqual(report.page_errors, []); assert.deepEqual(report.missing_assets, []);
  report.status = 'PASS';
  console.log(`UNIT_DETENT_EVENTS_OK ${report.checks.length} browser fixture checks; guest/hardware NOT RUN; electrical mapping NOT VERIFIED`);
} catch (error) {
  report.failure = {message: error.message, stack: error.stack};
  throw error;
} finally {
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
