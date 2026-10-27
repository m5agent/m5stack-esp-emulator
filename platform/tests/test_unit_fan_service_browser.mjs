// Opt-in real guest PWM -> qualitative adapter activity test. No RPM/physical
// motor equivalence claim. Creates, records and stops only its own API lease.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium} from 'playwright';
assert.equal(process.env.M5_UNIT_SERVICE_E2E, '1', 'Explicit visible-runtime opt-in required');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const base = process.env.M5_DEVICE_SERVICE_URL || 'http://127.0.0.1:8787';
const output = resolve(process.env.M5_UNIT_FAN_BROWSER_OUT || '/tmp/m5-unit-fan-service-browser');
await mkdir(output, {recursive: true});
const reference = JSON.parse(await readFile(resolve(root, process.env.M5_UNIT_FAN_REFERENCE_RESULT || '.work/io-unit-validation-r3-20261026/fan/result.json'), 'utf8'));
const files = ['platform/web/sessions.js', 'platform/web/unit-panel.js', 'platform/web/unit-panel.css', 'platform/web/unit-visual-mappings.js', 'platform/web/unit-annotations.js', 'platform/web/unit-assembly-layout.js', 'platform/web/model-shell.js', 'platform/tests/test_unit_fan_service_browser.mjs'];
const hashes = async () => Object.fromEntries(await Promise.all(files.map(async name => [name, createHash('sha256').update(await readFile(resolve(root, name))).digest('hex')])));
const report = {category: 'virtual-device-browser-drive-activity', status: 'FAIL', captured_at: new Date().toISOString(), unit_id: 'fan', device_id: 'cores3', runtime: 'qemu', firmware_sha256: reference.firmware_sha256, shaft_speed: 'UNMODELED', hardware_execution: 'NOT RUN', source_sha256: await hashes(), checks: {}, page_errors: []};
const api = async (path, options = {}) => { const response = await fetch(`${base}/api/v1/${path}`, options); const value = await response.json(); if (!response.ok) throw new Error(`${response.status}: ${JSON.stringify(value)}`); return value; };
let sessionId, browser, page;
try {
  const session = await api('sessions', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({device_id: 'cores3', firmware_id: reference.firmware_sha256, runtime: 'qemu', ttl_seconds: 600, ready_marker: 'IO_PROBE_READY fan', ready_timeout_seconds: 150, units: [{id: 'external1', unit_id: 'fan', port_id: 'port-a'}]})});
  sessionId = session.session_id; report.session_id = sessionId;
  console.log(`Visible fan activity session: ${sessionId}`);
  const deadline = Date.now() + 180000;
  while (!(await api(`sessions/${sessionId}/serial?limit=262144`)).data.includes('IO_PROBE_READY fan')) { if (Date.now() > deadline) throw new Error('guest did not reach ready'); await delay(200); }
  browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  report.browser_version = browser.version();
  page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  page.on('pageerror', error => report.page_errors.push(error.message));
  await page.route('**/platform/web/sessions.js*', async route => { const response = await route.fetch(); const source = await response.text(); assert.equal(createHash('sha256').update(source).digest('hex'), report.source_sha256['platform/web/sessions.js']); await route.fulfill({response, body: `${source}\nwindow.__unitBrowserProbe={state,SessionVisual};\n`}); });
  assert.equal((await page.goto(`${base}/platform/web/sessions.html`, {waitUntil: 'domcontentloaded'})).ok(), true);
  await page.waitForFunction(id => window.__unitBrowserProbe?.state.visuals.get(id)?.unitPanel?.mounted.size === 1, sessionId, {timeout: 60000});
  const snapshot = async () => page.evaluate(id => {
    const visual = window.__unitBrowserProbe.state.visuals.get(id), joint = visual?.shell?.model.find('grove/rotor', 'joint'), state = visual?.unitPanel?.states.get('external1');
    return {available: state?.available, properties: state?.properties, active: visual?.shell?.driveActivities.get('grove/rotor')?.active, angle: joint?.getState().angleDeg, rpmState: joint?.getState().rpm};
  }, sessionId);
  await page.waitForFunction(id => {
    const visual = window.__unitBrowserProbe.state.visuals.get(id);
    return visual?.unitPanel?.states.get('external1')?.properties['duty-pct'] > 0 && visual?.shell?.driveActivities.get('grove/rotor')?.active === true;
  }, sessionId, {timeout: 30000});
  const activeBefore = await snapshot(); await page.waitForTimeout(250); const activeAfter = await snapshot();
  assert.equal(activeBefore.active, true); assert.equal(activeAfter.active, true);
  assert.notEqual(activeBefore.angle, activeAfter.angle);
  assert.equal(activeAfter.rpmState, 0, 'qualitative cadence never becomes a modeled RPM');
  report.active_observations = [activeBefore, activeAfter];
  report.checks.observed_guest_pwm_enables_graphical_activity = true;
  await page.locator(`[data-session-id="${sessionId}"]`).screenshot({path: `${output}/drive-active-browser.png`});
  await page.waitForFunction(id => {
    const visual = window.__unitBrowserProbe.state.visuals.get(id);
    return visual?.unitPanel?.states.get('external1')?.properties['duty-pct'] === 0 && visual?.shell?.driveActivities.get('grove/rotor')?.active === false;
  }, sessionId, {timeout: 30000});
  const idleBefore = await snapshot(); await page.waitForTimeout(250); const idleAfter = await snapshot();
  assert.equal(idleBefore.active, false); assert.equal(idleAfter.active, false);
  assert.equal(idleBefore.angle, idleAfter.angle);
  report.zero_duty_observations = [idleBefore, idleAfter];
  report.checks.zero_pwm_stops_graphical_activity = true;
  await page.locator(`[data-session-id="${sessionId}"]`).screenshot({path: `${output}/drive-idle-browser.png`});
  await writeFile(`${output}/frame.png`, Buffer.from(await (await fetch(`${base}/api/v1/sessions/${sessionId}/frame.png`)).arrayBuffer()));
  const zip = Buffer.from(await (await fetch(`${base}/api/v1/sessions/${sessionId}/evidence`)).arrayBuffer());
  await writeFile(`${output}/evidence.zip`, zip);
  report.evidence_sha256 = createHash('sha256').update(zip).digest('hex');
  report.checks.evidence_before_stop = true;
  await api(`sessions/${sessionId}?purge=0`, {method: 'DELETE'});
  await page.waitForFunction(id => {
    const visual = window.__unitBrowserProbe.state.visuals.get(id);
    return !visual || !visual.shell || visual.shell.driveActivities.get('grove/rotor')?.active !== true;
  }, sessionId, {timeout: 15000});
  report.checks.terminal_state_stops_or_disposes_graphical_activity = true;
  assert.deepEqual(report.page_errors, []);
  assert.deepEqual(await hashes(), report.source_sha256);
  report.status = 'PASS';
} catch (error) { report.error = error.stack || String(error); }
finally {
  if (sessionId) {
    try {
      await writeFile(`${output}/serial.txt`, (await api(`sessions/${sessionId}/serial?limit=262144`)).data);
      if (!report.checks.evidence_before_stop) { const zip = Buffer.from(await (await fetch(`${base}/api/v1/sessions/${sessionId}/evidence`)).arrayBuffer()); await writeFile(`${output}/evidence.zip`, zip); }
      const current = await api(`sessions/${sessionId}`);
      if (!['stopped', 'failed'].includes(current.state)) await api(`sessions/${sessionId}?purge=0`, {method: 'DELETE'});
      const history = await api(`sessions/${sessionId}`);
      assert.ok(['stopped', 'failed'].includes(history.state));
      assert.equal(history.last_frame_available, true);
      report.checks.stopped_with_history = true;
    } catch (error) { report.cleanup_error = String(error); report.status = 'FAIL'; }
  }
  if (browser) await browser.close();
  await writeFile(`${output}/report.json`, JSON.stringify(report, null, 2) + '\n');
}
console.log(`UNIT_FAN_BROWSER_${report.status} ${output}/report.json`);
if (report.status !== 'PASS') { console.error(report.error || report.cleanup_error); process.exitCode = 1; }
