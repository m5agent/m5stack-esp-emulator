// Opt-in, real Device Service + firmware test. Creates and stops only its own
// visible lease. Browser instrumentation exposes existing module objects for
// observation; product functions and all API requests remain unmodified.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium} from 'playwright';

assert.equal(process.env.M5_UNIT_SERVICE_E2E, '1', 'Explicit opt-in required: this test starts a visible virtual device.');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const base = process.env.M5_DEVICE_SERVICE_URL || 'http://127.0.0.1:8787';
const output = resolve(process.env.M5_UNIT_SERVICE_BROWSER_OUT || '/tmp/m5-unit-service-browser');
await mkdir(output, {recursive: true});
const unitId = process.env.M5_UNIT_BROWSER_UNIT || 'button';
assert.ok(['button', 'key'].includes(unitId));
const referencePath = process.env.M5_UNIT_BROWSER_REFERENCE_RESULT || 'docs/evidence/2026-10-26-unit-runtime/button/result.json';
const reference = JSON.parse(await readFile(resolve(root, referencePath), 'utf8'));
assert.equal(reference.unit_id, unitId);
const readyMarker = unitId === 'key' ? 'IO_PROBE_READY key' : 'UNIT_PROBE_READY';
const downMarker = unitId === 'key' ? 'IO_KEY_RAW 0' : 'UNIT_BUTTON 0';
const upMarker = unitId === 'key' ? 'IO_KEY_RAW 1' : 'UNIT_BUTTON 1';
const files = ['platform/web/sessions.js', 'platform/web/sessions.html', 'platform/web/unit-panel.js', 'platform/web/unit-panel.css', 'platform/web/unit-visual-mappings.js', 'platform/web/unit-annotations.js', 'platform/web/unit-assembly-layout.js', 'platform/web/model-shell.js', 'platform/web/device-shell-factory.js', 'platform/tests/test_unit_service_browser.mjs'];
const fingerprints = async () => Object.fromEntries(await Promise.all(files.map(async name => [name, createHash('sha256').update(await readFile(resolve(root, name))).digest('hex')])));
const report = {category: 'virtual-device-browser-integration', status: 'FAIL', captured_at: new Date().toISOString(), device_id: 'cores3', unit_id: unitId, runtime: 'qemu', firmware_sha256: reference.firmware_sha256, hardware_execution: 'NOT RUN', source_sha256: await fingerprints(), checks: {}, page_errors: [], unit_posts: [], instrumentation: 'Appends only window.__unitBrowserProbe={state,SessionVisual} to the actual sessions.js response; no function/API behavior replacement.'};
const api = async (path, options = {}) => {
  const response = await fetch(`${base}/api/v1/${path}`, options);
  const body = await response.json();
  if (!response.ok) throw new Error(`${response.status}: ${JSON.stringify(body)}`);
  return body;
};
const post = (path, value) => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)});
const eventually = async (predicate, timeout = 60000) => {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { const value = await predicate(); if (value) return value; await delay(200); }
  throw new Error('Timed out waiting for the real guest/browser observation');
};
let sessionId, browser, page;
try {
  const session = await post('sessions', {device_id: 'cores3', firmware_id: reference.firmware_sha256, runtime: 'qemu', ttl_seconds: 600, ready_marker: readyMarker, ready_timeout_seconds: 150, units: [{id: 'external1', unit_id: unitId, port_id: 'port-a'}]});
  sessionId = session.session_id;
  report.session_id = sessionId;
  console.log(`Visible browser validation session: ${sessionId}`);
  const serial = async () => (await api(`sessions/${sessionId}/serial?limit=262144`)).data || '';
  await eventually(async () => (await serial()).includes(readyMarker), 180000);
  report.checks.same_guest_ready = true;
  browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  report.browser_version = browser.version();
  page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  page.on('pageerror', error => report.page_errors.push(error.message));
  page.on('request', request => { if (request.method() === 'POST' && request.url().includes(`/sessions/${sessionId}/unit-input`)) report.unit_posts.push(request.postDataJSON()); });
  await page.route('**/platform/web/sessions.js*', async route => {
    const response = await route.fetch();
    const source = await response.text();
    assert.equal(createHash('sha256').update(source).digest('hex'), report.source_sha256['platform/web/sessions.js']);
    await route.fulfill({response, body: `${source}\nwindow.__unitBrowserProbe = {state, SessionVisual};\n`});
  });
  const document = await page.goto(`${base}/platform/web/sessions.html`, {waitUntil: 'domcontentloaded'});
  assert.equal(document.ok(), true, 'the actual sessions product page must load');
  const card = page.locator(`[data-session-id="${sessionId}"]`);
  await card.waitFor({state: 'visible', timeout: 60000});
  await page.waitForFunction(id => {
    const visual = window.__unitBrowserProbe?.state.visuals.get(id);
    return visual?.shell?.model?.find('grove/press', 'button') && visual.unitPanel?.mounted.size === 1;
  }, sessionId, {timeout: 60000});
  const button = card.locator('.unit-control button[data-press-field="pressed"]');
  await button.waitFor({state: 'visible'});
  assert.equal(await button.isEnabled(), true);
  const beforeDown = (await serial()).length;
  await button.hover();
  await page.mouse.down();
  await eventually(async () => (await serial()).slice(beforeDown).includes(downMarker));
  const pressed = await eventually(async () => {
    const state = await api(`sessions/${sessionId}/units`);
    return state.units[0].properties.pressed === true && (unitId !== 'key' || state.units[0].properties['led-rgb'] === 0x123456) && state;
  });
  assert.equal(pressed.units[0].properties.pressed, true);
  assert.equal(pressed.units[0].properties['input-level'], false);
  assert.ok(pressed.definitions?.find(unit => unit.id === unitId), 'live session owns its frozen schema');
  await page.waitForFunction(id => window.__unitBrowserProbe.state.visuals.get(id).shell.model.button('grove/press').getState().pressed === true, sessionId);
  await page.waitForFunction(id => window.__unitBrowserProbe.state.visuals.get(id).shell.model.button('grove/press').getActuationState().depthMm > 0.3, sessionId);
  report.pressed_state = pressed;
  report.checks.dom_press_same_guest_gpio_qom_and_mechanical_readback = true;
  if (unitId === 'key') {
    await page.waitForFunction(id => window.__unitBrowserProbe.state.visuals.get(id).shell.model.find('grove/rgb', 'led').getState().color === '#123456', sessionId);
    report.pressed_led_visual = await page.evaluate(id => window.__unitBrowserProbe.state.visuals.get(id).shell.model.find('grove/rgb', 'led').getState(), sessionId);
  }
  await writeFile(`${output}/pressed-frame.png`, Buffer.from(await (await fetch(`${base}/api/v1/sessions/${sessionId}/frame.png`)).arrayBuffer()));
  await card.screenshot({path: `${output}/pressed-browser.png`});
  const beforeUp = (await serial()).length;
  await page.mouse.up();
  await eventually(async () => (await serial()).slice(beforeUp).includes(upMarker));
  const released = await eventually(async () => {
    const state = await api(`sessions/${sessionId}/units`);
    return state.units[0].properties.pressed === false && (unitId !== 'key' || state.units[0].properties['led-rgb'] === 0x2468AC) && state;
  });
  assert.equal(released.units[0].properties.pressed, false);
  assert.equal(released.units[0].properties['input-level'], true);
  await page.waitForFunction(id => {
    const button = window.__unitBrowserProbe.state.visuals.get(id).shell.model.button('grove/press');
    return !button.getState().pressed && button.getActuationState().depthMm < 0.001;
  }, sessionId);
  report.released_state = released;
  report.checks.dom_release_same_guest_gpio_qom_and_mechanical_readback = true;
  if (unitId === 'key') {
    await page.waitForFunction(id => window.__unitBrowserProbe.state.visuals.get(id).shell.model.find('grove/rgb', 'led').getState().color === '#2468ac', sessionId);
    report.released_led_visual = await page.evaluate(id => window.__unitBrowserProbe.state.visuals.get(id).shell.model.find('grove/rgb', 'led').getState(), sessionId);
    report.checks.guest_rmt_rgb_output_reaches_qom_and_same_shell_led = true;
  }
  await writeFile(`${output}/released-frame.png`, Buffer.from(await (await fetch(`${base}/api/v1/sessions/${sessionId}/frame.png`)).arrayBuffer()));
  await card.screenshot({path: `${output}/released-browser.png`});
  report.checks.shell_received_real_framebuffer = await page.evaluate(id => {
    const visual = window.__unitBrowserProbe.state.visuals.get(id);
    return visual.shell.frameSeq > 0 && visual.shell.display.getPixel(0, 0).some(channel => channel > 0);
  }, sessionId);
  assert.equal(report.checks.shell_received_real_framebuffer, true);
  const degraded = await page.evaluate(id => {
    const visual = window.__unitBrowserProbe.state.visuals.get(id), shell = visual.shell;
    visual.setThreeAllowed(false);
    return {disposed: shell.disposed, shellNull: visual.shell === null, panelShellNull: visual.unitPanel.shell === null, mounted: visual.unitPanel.mounted.size, threeClass: visual.container.classList.contains('is-three')};
  }, sessionId);
  assert.deepEqual(degraded, {disposed: true, shellNull: true, panelShellNull: true, mounted: 0, threeClass: false});
  await page.evaluate(id => window.__unitBrowserProbe.state.visuals.get(id).setThreeAllowed(true), sessionId);
  await page.waitForFunction(id => {
    const visual = window.__unitBrowserProbe.state.visuals.get(id);
    return visual.shell && visual.unitPanel?.mounted.size === 1 && visual.shell.frameSeq > 0;
  }, sessionId);
  report.checks.sessions_webgl_limit_disposes_shell_detaches_units_and_restores = true;
  assert.deepEqual(report.page_errors, []);
  assert.deepEqual(report.unit_posts, [{id: 'external1', values: {pressed: true}}, {id: 'external1', values: {pressed: false}}], 'readback/remount must not echo controller inputs');
  report.checks.no_readback_input_echo = true;
  assert.deepEqual(await fingerprints(), report.source_sha256, 'source files changed during the run');
  report.status = 'PASS';
} catch (error) {
  report.error = error.stack || String(error);
} finally {
  if (page) { try { await page.mouse.up(); } catch {} }
  if (sessionId) {
    try {
      const serial = (await api(`sessions/${sessionId}/serial?limit=262144`)).data || '';
      await writeFile(`${output}/serial.txt`, serial);
      const response = await fetch(`${base}/api/v1/sessions/${sessionId}/evidence`);
      assert.equal(response.ok, true);
      const zip = Buffer.from(await response.arrayBuffer());
      await writeFile(`${output}/evidence.zip`, zip);
      report.evidence_sha256 = createHash('sha256').update(zip).digest('hex');
      report.checks.evidence_requested_before_stop = true;
    } catch (error) { report.evidence_error = String(error); report.status = 'FAIL'; }
    try {
      const stopped = await api(`sessions/${sessionId}?purge=0`, {method: 'DELETE'});
      assert.ok(['stopped', 'failed'].includes(stopped.state));
      const history = await api(`sessions/${sessionId}`);
      assert.equal(history.session_id, sessionId);
      assert.equal(history.last_frame_available, true);
      report.checks.stopped_with_metadata_serial_and_frame_history = true;
    } catch (error) { report.stop_error = String(error); report.status = 'FAIL'; }
  }
  if (browser) await browser.close();
  await writeFile(`${output}/report.json`, JSON.stringify(report, null, 2) + '\n');
}
console.log(`UNIT_SERVICE_BROWSER_${report.status} ${output}/report.json`);
if (report.status !== 'PASS') { console.error(report.error || report.evidence_error || report.stop_error); process.exitCode = 1; }
