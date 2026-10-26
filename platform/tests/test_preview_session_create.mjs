// Actual sessions page creation/recovery orchestration; deterministic HTTP only.
// The allocation counter models idempotency, not a real guest or backend proof.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, extname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = process.env.M5_PREVIEW_CREATE_OUT || '/tmp/m5-preview-session-create-test';
await mkdir(output, {recursive: true});
const checks = [], errors = [];
let scenario;
function reset(extra = {}) {
  scenario = {posts: [], legacy: [], reads: [], deviceReads: [], unitReads: [], catalogReads: 0,
    ledger: new Map(), allocations: 0, state: 'preparing',
    dropOnce: false, dropGetOnce: false, malformedOnce: false, ...extra};
}
const json = (res, value, status = 200) => { res.writeHead(status, {'Content-Type': 'application/json'}); res.end(JSON.stringify(value)); };
// Deliver response headers before truncation so Chromium cannot transparently
// retry an apparently unused TCP connection and hide the ambiguous outcome.
const truncate = res => { res.writeHead(202, {'Content-Type': 'application/json', 'Content-Length': '4096'});
  res.write('{"preview_id":'); setTimeout(() => res.destroy(), 10); };
const inventory = {units: [{id: 'pir', name: 'PIR fixture', interface: {bus: 'gpio'}, runtime: {status: 'validated', hosts: ['atoms3r']}}],
  hosts: [{device_id: 'atoms3r', ports: [{id: 'port-a', label: 'Grove', wiring_status: 'confirmed', physical_presence: 'main-device'}]}]};
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost'), path = url.pathname;
    if (path === '/devices/catalog.json') { scenario.catalogReads += 1; return json(res, {devices: []}); }
    const authorized = req.headers.authorization === 'Bearer browser-fixture-control';
    if (path === '/api/v1/devices') scenario.deviceReads.push({authorized, status: scenario.requireToken && !authorized ? 401 : 200});
    if (path === '/api/v1/units') scenario.unitReads.push({authorized, device_id: url.searchParams.get('device_id')});
    if (scenario.requireToken && path.startsWith('/api/v1/') && !authorized)
      return json(res, {error: {code: 'unauthorized', message: 'control token required'}}, 401);
    if (path === '/api/v1/devices') return json(res, {devices: [
      {device_id: 'atoms3r', name: 'AtomS3R fixture', creatable: true, program_modes: ['uiflow-live']},
      {device_id: 'tab5', name: 'Tab5 fixture', creatable: true, program_modes: []},
    ]});
    if (path === '/api/v1/units') return json(res, inventory);
    if (path === '/api/v1/capacity') return json(res, {active_sessions: 0, max_sessions: 4, available_sessions: 4});
    if (path === '/api/v1/sessions' && req.method === 'GET') return json(res, {sessions: []});
    if (path === '/api/v1/sessions' && req.method === 'POST') {
      let body = ''; for await (const part of req) body += part;
      scenario.legacy.push(JSON.parse(body)); return json(res, {session_id: 'legacy-fixture', state: 'running'}, 202);
    }
    if (path === '/api/v1/previews' && req.method === 'POST') {
      let raw = ''; for await (const part of req) raw += part;
      const body = JSON.parse(raw), key = req.headers['idempotency-key'];
      scenario.posts.push({key, raw, body, authorized: req.headers.authorization === 'Bearer browser-fixture-control'});
      if (!scenario.ledger.has(key)) { scenario.allocations += 1; scenario.ledger.set(key, {body: raw, preview_id: `preview-fixture-${scenario.allocations}`}); }
      const row = scenario.ledger.get(key);
      if (row.body !== raw) return json(res, {error: {code: 'idempotency_conflict', message: 'same key changed payload'}}, 409);
      if (scenario.dropOnce) { scenario.dropOnce = false; truncate(res); return; }
      if (scenario.malformedOnce) { scenario.malformedOnce = false; return json(res, {preview_id: '/bad-preview'}, 202); }
      return json(res, {preview_id: row.preview_id, state: 'preparing', session_id: null}, 202);
    }
    const preview = path.match(/^\/api\/v1\/previews\/(preview-fixture-\d+)$/);
    if (preview) {
      scenario.reads.push(preview[1]);
      if (scenario.dropGetOnce) { scenario.dropGetOnce = false; truncate(res); return; }
      return json(res, {preview_id: preview[1], state: scenario.state, session_id: scenario.state === 'ready' ? 'fixture-session' : null,
        error: scenario.state === 'failed' ? {message: 'allocation fixture failed'} : null});
    }
    const file = resolve(root, `.${path}`);
    if (!file.startsWith(root + '/')) { res.writeHead(403).end(); return; }
    res.setHeader('Content-Type', {'.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.png': 'image/png', '.json': 'application/json'}[extname(file)] || 'application/octet-stream');
    res.end(await readFile(file));
  } catch { if (!res.headersSent) res.writeHead(404); res.end(); }
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
let context, page;
async function setup({token = true, expectUnauthorized = false, ...options} = {}) {
  await context?.close(); reset(options); context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  if (token) await context.addInitScript(() => sessionStorage.setItem('m5-service-token', 'browser-fixture-control'));
  page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${base}/platform/web/sessions.html`);
  if (expectUnauthorized) await page.waitForFunction(() => document.querySelector('#errorBanner').textContent.includes('401'));
  else await page.waitForFunction(() => !document.querySelector('#createBtn').disabled);
}
async function choosePreview() {
  await page.check('#programModeInput'); await page.check('#previewModeInput');
  await page.locator('#unitModelSelect option[value="pir"]').waitFor({state: 'attached'});
  await page.selectOption('#unitModelSelect', 'pir');
}
async function pending() { return await page.evaluate(() => JSON.parse(sessionStorage.getItem('m5-pending-preview-create') || 'null')); }
async function waitUnknown() { await page.waitForFunction(() => !document.querySelector('#createBtn').disabled && document.querySelector('#previewCreateStatus').textContent.includes('未确认')); }
async function ready() { scenario.state = 'ready'; await page.waitForFunction(() => sessionStorage.getItem('m5-pending-preview-create') === null); }
async function test(name, action) { await action(); checks.push(name); }
try {
  await test('first-token-save-recovers-401-catalog-and-current-device-unit-picker-before-preview-create', async () => {
    await setup({token: false, requireToken: true, expectUnauthorized: true});
    assert.equal(await page.evaluate(() => sessionStorage.getItem('m5-service-token')), null);
    assert.deepEqual(scenario.deviceReads, [{authorized: false, status: 401}]);
    assert.ok(scenario.catalogReads >= 1, 'public static catalog remains readable before control token');
    assert.equal(await page.locator('#deviceSelect option').count(), 0);
    assert.equal(await page.locator('#programModeInput').isDisabled(), true);
    assert.equal(await page.locator('#previewModeInput').isDisabled(), true);
    assert.equal(await page.locator('#createBtn').isDisabled(), true);
    assert.deepEqual(scenario.posts, []);
    const catalogReload = page.waitForResponse(res => res.url().endsWith('/api/v1/devices') && res.status() === 200);
    await page.fill('#tokenInput', 'browser-fixture-control');
    await page.click('#saveTokenBtn'); await catalogReload;
    await page.waitForFunction(() => !document.querySelector('#createBtn').disabled);
    assert.deepEqual(scenario.deviceReads, [{authorized: false, status: 401}, {authorized: true, status: 200}]);
    assert.equal(await page.locator('#deviceSelect').inputValue(), 'atoms3r');
    assert.equal(await page.locator('#unitPicker > [data-unit-picker-device-id]').getAttribute('data-unit-picker-device-id'), 'atoms3r');
    assert.deepEqual(scenario.unitReads.at(-1), {authorized: true, device_id: 'atoms3r'});
    assert.equal(await page.locator('#errorBanner').isHidden(), true);
    await choosePreview(); await page.click('#createBtn');
    await page.waitForFunction(() => document.querySelector('#previewCreateStatus').textContent.includes('preparing'));
    assert.equal(scenario.posts.length, 1); assert.equal(scenario.posts[0].authorized, true);
    assert.equal(scenario.allocations, 1); assert.equal(scenario.legacy.length, 0);
    await page.screenshot({path: `${output}/first-token-bootstrap-recovered.png`, fullPage: true});
    await ready();
  });
  await test('preview-option-requires-token-and-device-program-capability', async () => {
    await setup({token: false}); await page.check('#programModeInput'); assert.equal(await page.locator('#previewModeInput').isDisabled(), true);
    await page.fill('#tokenInput', 'browser-fixture-control'); await page.click('#saveTokenBtn'); assert.equal(await page.locator('#previewModeInput').isEnabled(), true);
    await page.selectOption('#deviceSelect', 'tab5'); assert.equal(await page.locator('#programModeInput').isDisabled(), true); assert.equal(await page.locator('#previewModeInput').isDisabled(), true);
    assert.deepEqual(scenario.posts, []);
  });
  await test('legacy-program-checkbox-still-posts-sessions-with-uiflow-live', async () => {
    await setup(); await page.check('#programModeInput'); assert.equal(await page.locator('#previewModeInput').isChecked(), false);
    await Promise.all([page.waitForResponse(res => res.url().endsWith('/api/v1/sessions') && res.request().method() === 'POST'), page.click('#createBtn')]);
    assert.deepEqual(scenario.legacy, [{device_id: 'atoms3r', ttl_seconds: 600, program_mode: 'uiflow-live'}]); assert.equal(scenario.posts.length, 0);
  });
  await test('preview-202-polls-preparing-ready-retains-key-and-unit-body', async () => {
    await setup(); await choosePreview(); await page.click('#createBtn');
    await page.waitForFunction(() => document.querySelector('#previewCreateStatus').textContent.includes('preparing'));
    assert.equal(scenario.posts.length, 1); assert.equal(scenario.allocations, 1); assert.equal(scenario.posts[0].authorized, true);
    assert.match(scenario.posts[0].key, /^web-preview-[a-f0-9]{32}$/);
    assert.deepEqual(scenario.posts[0].body, {device_id: 'atoms3r', ttl_seconds: 600, units: [{id: 'external1', unit_id: 'pir', port_id: 'port-a'}]});
    assert.equal((await pending()).previewId, 'preview-fixture-1'); assert.equal(await page.locator('#createBtn').isDisabled(), true);
    await page.screenshot({path: `${output}/preview-preparing.png`, fullPage: true}); await ready();
    assert.equal(await pending(), null, 'ready Preview must clear the persisted creation intent');
    assert.equal(await page.locator('#createBtn').isEnabled(), true, 'ready Preview must release the creation control');
    assert.equal(await page.locator('#createBtn').innerText(), '创建持续预览', 'ready Preview must restore the selected creation mode label');
    assert.ok(scenario.reads.length >= 2); assert.equal(scenario.posts.length, 1); assert.equal(scenario.legacy.length, 0);
  });
  await test('unknown-network-create-retry-reuses-exact-key-body-despite-ui-edits', async () => {
    await setup({dropOnce: true}); await choosePreview(); await page.click('#createBtn'); await waitUnknown();
    const record = await pending(); assert.equal(record.previewId, undefined); assert.equal(scenario.allocations, 1);
    await page.fill('#ttlInput', '1200'); await page.selectOption('#deviceSelect', 'tab5');
    await page.click('#createBtn'); await page.waitForFunction(() => document.querySelector('#previewCreateStatus').textContent.includes('preparing'));
    assert.equal(scenario.posts.length, 2); assert.equal(scenario.posts[0].key, scenario.posts[1].key); assert.equal(scenario.posts[0].raw, scenario.posts[1].raw);
    assert.equal(scenario.allocations, 1); await ready();
  });
  await test('refresh-recovers-unknown-create-and-retries-same-persisted-intent', async () => {
    await setup({dropOnce: true}); await choosePreview(); await page.click('#createBtn'); await waitUnknown(); const before = await pending();
    await page.reload(); await waitUnknown(); assert.deepEqual(await pending(), before); assert.equal(scenario.posts.length, 1);
    await page.click('#createBtn'); await page.waitForFunction(() => document.querySelector('#previewCreateStatus').textContent.includes('preparing'));
    assert.equal(scenario.posts.length, 2); assert.equal(scenario.posts[0].key, scenario.posts[1].key); assert.equal(scenario.posts[0].raw, scenario.posts[1].raw); assert.equal(scenario.allocations, 1);
    await ready();
  });
  await test('refresh-recovers-known-preview-by-get-without-reposting-allocation', async () => {
    await setup(); await choosePreview(); await page.click('#createBtn');
    await page.waitForFunction(() => !!JSON.parse(sessionStorage.getItem('m5-pending-preview-create') || 'null')?.previewId); const before = await pending();
    await page.reload(); await page.waitForFunction(() => document.querySelector('#previewCreateStatus').textContent.includes('preparing'));
    assert.deepEqual(await pending(), before); assert.equal(scenario.posts.length, 1); assert.equal(scenario.allocations, 1); assert.ok(scenario.reads.length >= 2); await ready();
  });
  await test('uncertain-poll-retries-get-of-same-preview-and-terminal-failure-clears-intent', async () => {
    await setup({dropGetOnce: true}); await choosePreview(); await page.click('#createBtn');
    await page.waitForFunction(() => document.querySelector('#previewCreateStatus').textContent.includes('暂未确认'));
    assert.equal((await pending()).previewId, 'preview-fixture-1'); assert.equal(scenario.posts.length, 1);
    scenario.state = 'failed'; await page.waitForFunction(() => sessionStorage.getItem('m5-pending-preview-create') === null);
    assert.match(await page.locator('#previewCreateStatus').innerText(), /allocation fixture failed/);
    assert.ok(scenario.reads.every(id => id === 'preview-fixture-1')); assert.equal(scenario.allocations, 1);
  });
  await test('malformed-create-receipt-keeps-original-intent-for-explicit-retry', async () => {
    await setup({malformedOnce: true}); await choosePreview(); await page.click('#createBtn'); await waitUnknown();
    assert.equal((await pending()).previewId, undefined); await page.click('#createBtn');
    await page.waitForFunction(() => document.querySelector('#previewCreateStatus').textContent.includes('preparing'));
    assert.equal(scenario.posts.length, 2); assert.equal(scenario.posts[0].key, scenario.posts[1].key); assert.equal(scenario.posts[0].raw, scenario.posts[1].raw); assert.equal(scenario.allocations, 1); await ready();
  });
  assert.deepEqual(errors, []);
  const source_sha256 = {};
  for (const path of ['platform/web/sessions.js', 'platform/web/sessions.html', 'platform/web/preview-client.js', 'platform/tests/test_preview_session_create.mjs']) source_sha256[path] = createHash('sha256').update(await readFile(resolve(root, path))).digest('hex');
  await writeFile(`${output}/report.json`, JSON.stringify({category: 'actual-sessions-page-preview-create-recovery', status: 'PASS', captured_at: new Date().toISOString(),
    browser_version: browser.version(), source_sha256, checks, errors, allocation_model: 'fixture-only idempotency ledger', firmware_execution: 'NOT RUN', hardware_execution: 'NOT RUN'}, null, 2) + '\n');
  console.log(`PREVIEW_SESSION_CREATE_BROWSER_OK ${checks.length} checks`);
} catch (error) {
  await page?.screenshot({path: `${output}/failure.png`, fullPage: true});
  await writeFile(`${output}/failure.json`, JSON.stringify({status: 'FAIL', checks, errors, error: error.stack,
    fixture: {posts: scenario.posts, reads: scenario.reads, deviceReads: scenario.deviceReads, unitReads: scenario.unitReads,
      catalogReads: scenario.catalogReads, allocations: scenario.allocations}}, null, 2) + '\n'); throw error;
} finally { await context?.close(); await browser.close(); await new Promise(done => server.close(done)); }
