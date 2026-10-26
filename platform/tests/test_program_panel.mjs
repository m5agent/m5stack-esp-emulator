// Browser/API orchestration fixtures only; no firmware, Device Service or QEMU.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, extname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = process.env.M5_PROGRAM_PANEL_OUT || '/tmp/m5-program-panel-test';
await mkdir(output, {recursive: true});
const checks = [], errors = [], creationPosts = [], programPosts = [];
const sessions = [], programs = new Map();
const catalogGates = new Map();
const inventory = {
  units: [{id: 'pir', name: 'PIR fixture', interface: {bus: 'gpio'}, runtime: {status: 'validated', hosts: ['atoms3r']}}],
  hosts: [{device_id: 'atoms3r', ports: [{id: 'port-a', label: 'Grove', wiring_status: 'confirmed', physical_presence: 'main-device'}]}],
};
const programPayload = (id, program = null) => ({session_id: id, program_transport: 'uart-repl', program, history_error: null});
const json = (response, body, status = 200) => { response.writeHead(status, {'Content-Type': 'application/json'}); response.end(JSON.stringify(body)); };
const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, 'http://localhost');
    const pathname = url.pathname;
    if (pathname === '/harness') {
      response.setHeader('Content-Type', 'text/html');
      response.end('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/platform/web/app.css"><link rel="stylesheet" href="/platform/web/m5-tokens.css"><link rel="stylesheet" href="/platform/web/m5-brand.css"><link rel="stylesheet" href="/platform/web/program-panel.css"><style>main{max-width:760px;padding:12px;margin:auto}</style></head><body><main id="panel"></main></body></html>');
      return;
    }
    if (pathname === '/devices/catalog.json') return json(response, {devices: []});
    if (pathname === '/api/v1/devices') return json(response, {devices: [
      {device_id: 'atoms3r', name: 'AtomS3R fixture', creatable: true, program_modes: ['uiflow-live']},
      {device_id: 'tab5', name: 'Tab5 fixture', creatable: true, program_modes: []},
      {device_id: 'cores3', name: 'CoreS3 fixture', creatable: true, program_modes: ['uiflow-live']},
    ]});
    if (pathname === '/api/v1/units') {
      const gate = catalogGates.get(url.searchParams.get('device_id'));
      if (gate) { gate.responses.push(response); gate.started(); return; }
      return json(response, inventory);
    }
    if (pathname === '/api/v1/capacity') return json(response, {active_sessions: sessions.filter(item => item.state === 'running').length, max_sessions: 4, available_sessions: 4 - sessions.length});
    if (pathname === '/api/v1/sessions' && request.method === 'GET') return json(response, {sessions});
    if (pathname === '/api/v1/sessions' && request.method === 'POST') {
      let body = ''; for await (const chunk of request) body += chunk;
      const payload = JSON.parse(body); creationPosts.push(payload);
      const id = `page-session-${sessions.length + 1}`;
      const session = {session_id: id, device_id: payload.device_id, state: 'running', created_at: new Date().toISOString(), serial_bytes: 0, units: [], display: null,
        ...(payload.program_mode === 'uiflow-live' ? {program_transport: 'uart-repl', program: null} : {})};
      sessions.push(session); return json(response, session, 202);
    }
    const serial = pathname.match(/^\/api\/v1\/sessions\/([^/]+)\/serial$/);
    if (serial) return json(response, {session_id: decodeURIComponent(serial[1]), offset: 0, next_offset: 0, data: '', bytes: 0});
    const match = pathname.match(/^\/api\/v1\/sessions\/([^/]+)(?:\/(program))?$/);
    if (match) {
      const id = decodeURIComponent(match[1]);
      const session = sessions.find(item => item.session_id === id);
      if (!session) return json(response, {error: {message: 'fixture session missing'}}, 404);
      if (request.method === 'DELETE') {
        session.state = 'stopped'; session.completed_at = new Date().toISOString();
        if (session.program) session.program = {...session.program, state: 'interrupted'};
        return json(response, session);
      }
      if (match[2] === 'program') {
        if (request.method === 'POST') {
          let body = ''; for await (const chunk of request) body += chunk;
          const payload = JSON.parse(body); programPosts.push({id, ...payload});
          session.program = {execution_id: `page-execution-${programPosts.length}`, state: 'completed'};
          programs.set(id, session.program);
        }
        return json(response, programPayload(id, session.program || null));
      }
    }
    const path = resolve(root, `.${decodeURIComponent(pathname)}`);
    if (!path.startsWith(root + '/')) { response.writeHead(403).end(); return; }
    response.setHeader('Content-Type', {'.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.png': 'image/png', '.json': 'application/json'}[extname(path)] || 'application/octet-stream');
    response.end(await readFile(path));
  } catch { if (!response.headersSent) response.writeHead(404); response.end(); }
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
const base = `http://127.0.0.1:${server.address().port}`;
const page = await browser.newPage({viewport: {width: 1024, height: 900}});
page.on('pageerror', error => errors.push(error.message));
async function test(name, run) { await run(); checks.push(name); }
function catalogGate(deviceId) {
  let started;
  const entered = new Promise(done => { started = done; });
  const gate = {deviceId, responses: [], started, entered};
  catalogGates.set(deviceId, gate);
  return gate;
}
async function catalogEntered(gate) {
  let timer;
  try { await Promise.race([gate.entered, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`catalog ${gate.deviceId} did not start`)), 5000); })]); }
  finally { clearTimeout(timer); }
}
function releaseCatalog(gate, body) {
  catalogGates.delete(gate.deviceId);
  for (const response of gate.responses) json(response, body);
}
async function setup(options = {}) {
  await page.evaluate(async options => {
    window.fixture?.panel.dispose();
    const {createProgramPanel} = await import('/platform/web/program-panel.js');
    const f = window.fixture = {
      calls: [], gates: [], nextGets: [], nextPosts: [], programs: new Map(), counter: 0,
      session(id = 'owner-a', extra = {}) { return {session_id: id, created_at: '2026-10-26T00:00:00Z', device_id: 'atoms3r', state: 'running', program_transport: 'uart-repl', ...extra}; },
      payload(id, program = this.programs.get(id) || null) { return {session_id: id, program_transport: 'uart-repl', program, history_error: null}; },
      block(method = 'GET') {
        let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
        const gate = {promise, resolve, reject}; this.gates.push(gate);
        (method === 'POST' ? this.nextPosts : this.nextGets).push(gate);
        return this.gates.length - 1;
      },
      release(index, payload, message) { const gate = this.gates[index]; if (message) gate.reject(new Error(message)); else gate.resolve(payload); },
      bind(id, extra = {}) { this.panel.updateSession(this.session(id, extra)); },
    };
    f.api = async (path, request = {}) => {
      const id = decodeURIComponent(path.split('/')[4]);
      const method = request.method || 'GET';
      f.calls.push({id, path, method, body: request.body ? JSON.parse(request.body) : null});
      const gate = (method === 'POST' ? f.nextPosts : f.nextGets).shift();
      let payload;
      if (gate) payload = await gate.promise;
      else if (method === 'POST') payload = f.payload(id, {execution_id: `execution-${++f.counter}`, state: 'running'});
      else payload = f.payload(id);
      if (method === 'POST' && payload?.session_id === id) f.programs.set(id, payload.program);
      return structuredClone(payload);
    };
    const id = options.id || 'owner-a';
    if (options.program) f.programs.set(id, options.program);
    if (options.blockInitial) f.initial = f.block();
    f.panel = createProgramPanel(document.querySelector('#panel'), {session: f.session(id, options.session || {}), api: f.api});
  }, options);
  if (!options.blockInitial && options.session?.state !== 'booting' && options.session?.program_transport !== null) {
    await page.waitForFunction(() => window.fixture.panel.synchronized);
  }
}
const source = page.locator('[data-program-source]');
const runButton = page.locator('[data-program-run]');
try {
  await page.goto(`${base}/harness`);
  await page.clock.install({time: new Date('2026-10-26T12:00:00Z')});
  await page.clock.pauseAt(new Date('2026-10-26T12:00:01Z'));
  await test('initial-get-gates-first-run-cas-source-snapshot-and-double-click', async () => {
    await setup({blockInitial: true});
    assert.equal(await runButton.isDisabled(), true); assert.equal(await source.isDisabled(), true);
    await page.evaluate(() => { const f = window.fixture; f.release(f.initial, f.payload('owner-a')); });
    await page.waitForFunction(() => window.fixture.panel.synchronized);
    const draft = 'print("温度 \\\"Unit\\\"", 42)\n';
    await source.fill(draft);
    const gate = await page.evaluate(() => window.fixture.block('POST'));
    await page.evaluate(() => { window.fixture.firstRun = window.fixture.panel.run(); void window.fixture.panel.run(); });
    assert.equal(await runButton.isDisabled(), true); assert.equal(await source.isDisabled(), true);
    assert.deepEqual(await page.evaluate(() => window.fixture.calls.filter(call => call.method === 'POST').map(call => call.body)), [{source: draft, expected_execution_id: null}]);
    await page.evaluate(gate => { const f = window.fixture; f.release(gate, f.payload('owner-a', {execution_id: 'accepted-1', state: 'running'})); return f.firstRun; }, gate);
    await page.waitForFunction(() => window.fixture.panel.synchronized && !window.fixture.panel.pending);
    assert.equal(await source.inputValue(), draft);
    await page.evaluate(() => window.fixture.panel.run());
    assert.equal(await page.evaluate(() => window.fixture.calls.filter(call => call.method === 'POST').at(-1).body.expected_execution_id), 'accepted-1');
  });
  await test('old-get-success-null-and-error-cannot-roll-back-new-execution', async () => {
    for (const outcome of ['old', 'null', 'error']) {
      await setup({program: {execution_id: 'previous', state: 'running'}});
      const gate = await page.evaluate(() => { const f = window.fixture; const gate = f.block(); f.oldGet = f.panel.refresh(); return gate; });
      await source.fill(`print('${outcome} draft')\n`);
      await page.evaluate(() => window.fixture.panel.run());
      const accepted = await page.evaluate(() => window.fixture.panel.program.execution_id);
      await page.evaluate(({gate, outcome}) => { const f = window.fixture; f.release(gate, f.payload('owner-a', outcome === 'null' ? null : {execution_id: 'previous', state: 'completed'}), outcome === 'error' ? '503: stale GET failure' : null); return f.oldGet; }, {gate, outcome});
      assert.equal(await page.evaluate(() => window.fixture.panel.program.execution_id), accepted);
      assert.equal(await runButton.isDisabled(), false);
      assert.equal(await source.inputValue(), `print('${outcome} draft')\n`);
      assert.equal(await page.locator('[data-program-error]').textContent(), '');
    }
  });
  await test('polling-preserves-editor-focus-selection-and-draft', async () => {
    await setup(); await source.fill('print("draft")\n'); await source.focus();
    await source.evaluate(node => node.setSelectionRange(2, 8));
    await page.evaluate(() => window.fixture.panel.refresh());
    assert.deepEqual(await source.evaluate(node => ({value: node.value, start: node.selectionStart, end: node.selectionEnd, focused: document.activeElement === node})), {value: 'print("draft")\n', start: 2, end: 8, focused: true});
  });
  await test('old-get-success-and-error-fenced-across-owner-and-reused-session-id', async () => {
    for (const fail of [false, true]) {
      await setup();
      const gate = await page.evaluate(() => { const f = window.fixture; const gate = f.block(); f.oldGet = f.panel.refresh(); f.bind('owner-b'); return gate; });
      await page.waitForFunction(() => window.fixture.panel.synchronized);
      await page.evaluate(() => window.fixture.bind('owner-a', {created_at: '2026-10-26T00:02:00Z'}));
      await page.waitForFunction(() => window.fixture.panel.synchronized);
      await source.fill('print("new GET owner draft")\n');
      await page.evaluate(({gate, fail}) => { const f = window.fixture; f.release(gate, f.payload('owner-a', {execution_id: 'old-get-owner', state: 'failed'}), fail ? '503: old owner GET failure' : null); return f.oldGet; }, {gate, fail});
      assert.equal(await page.evaluate(() => window.fixture.panel.program), null);
      assert.equal(await page.locator('[data-program-error]').textContent(), '');
      assert.equal(await source.inputValue(), 'print("new GET owner draft")\n');
      assert.equal(await runButton.isDisabled(), false);
    }
  });
  await test('old-post-success-error-and-finally-cannot-affect-reused-owner-or-new-pending', async () => {
    for (const fail of [false, true]) {
      await setup(); const oldGate = await page.evaluate(() => window.fixture.block('POST'));
      await page.evaluate(() => { const f = window.fixture; f.oldPost = f.panel.run(); f.bind('owner-b'); });
      await page.waitForFunction(() => window.fixture.panel.synchronized);
      await page.evaluate(() => window.fixture.bind('owner-a', {created_at: '2026-10-26T00:01:00Z'}));
      await page.waitForFunction(() => window.fixture.panel.synchronized);
      await source.fill('print("new owner draft")\n');
      const newGate = await page.evaluate(() => { const f = window.fixture; const gate = f.block('POST'); f.newPost = f.panel.run(); return gate; });
      await page.evaluate(({oldGate, fail}) => { const f = window.fixture; f.release(oldGate, f.payload('owner-a', {execution_id: 'old-post', state: 'failed'}), fail ? '409: old owner failure' : null); return f.oldPost; }, {oldGate, fail});
      assert.equal(await page.evaluate(() => !!window.fixture.panel.pending), true);
      assert.equal(await runButton.isDisabled(), true);
      assert.equal(await source.inputValue(), 'print("new owner draft")\n');
      assert.equal(await page.locator('[data-program-error]').textContent(), '');
      await page.evaluate(newGate => { const f = window.fixture; f.release(newGate, f.payload('owner-a', {execution_id: 'new-owner', state: 'completed'})); return f.newPost; }, newGate);
      assert.equal(await page.evaluate(() => window.fixture.panel.program.execution_id), 'new-owner');
    }
  });
  await test('inactive-and-pending-block-handlers-and-old-get-cannot-reactivate', async () => {
    await setup(); const gate = await page.evaluate(() => { const f = window.fixture; const gate = f.block(); f.oldGet = f.panel.refresh(); f.bind('owner-a', {state: 'stopped'}); return gate; });
    const count = await page.evaluate(() => window.fixture.calls.length);
    await page.evaluate(() => window.fixture.panel.run());
    await page.evaluate(gate => { const f = window.fixture; f.release(gate, f.payload('owner-a', {execution_id: 'late', state: 'running'})); return f.oldGet; }, gate);
    assert.equal(await page.evaluate(() => window.fixture.calls.length), count);
    assert.equal(await runButton.isDisabled(), true); assert.equal(await source.isDisabled(), true);
    await setup({session: {state: 'booting'}});
    assert.equal(await runButton.isDisabled(), true); assert.equal(await page.evaluate(() => window.fixture.calls.length), 0);
    await setup({session: {program_transport: null}});
    assert.equal(await page.locator('[data-program-panel-root]').isHidden(), true);
    assert.equal(await page.evaluate(() => window.fixture.calls.length), 0);
  });
  await test('actual-api-error-retained-while-resync-recovers-generation', async () => {
    await setup(); await source.fill('print("keep this draft")\n');
    const gate = await page.evaluate(() => { const f = window.fixture; const gate = f.block('POST'); f.post = f.panel.run(); f.programs.set('owner-a', {execution_id: 'external-new', state: 'running'}); return gate; });
    await page.evaluate(gate => { const f = window.fixture; f.release(gate, null, '409: expected_execution_id is stale'); return f.post; }, gate);
    await page.waitForFunction(() => window.fixture.panel.synchronized);
    assert.match(await page.locator('[data-program-error]').textContent(), /409: expected_execution_id is stale/);
    assert.equal(await source.inputValue(), 'print("keep this draft")\n');
    await page.evaluate(() => window.fixture.panel.run());
    assert.equal(await page.evaluate(() => window.fixture.calls.filter(call => call.method === 'POST').at(-1).body.expected_execution_id), 'external-new');
  });
  await test('wrong-session-and-history-error-fail-closed-and-utf8-limit-is-real-bytes', async () => {
    await setup({blockInitial: true});
    await page.evaluate(() => { const f = window.fixture; f.release(f.initial, f.payload('foreign-owner', {execution_id: 'foreign', state: 'running'})); });
    await page.waitForFunction(() => !!window.fixture.panel.pollError);
    assert.equal(await runButton.isDisabled(), true);
    assert.equal(await page.evaluate(() => window.fixture.panel.program), null);
    const gate = await page.evaluate(() => { const f = window.fixture; const gate = f.block(); f.refresh = f.panel.refresh(); return gate; });
    await page.evaluate(gate => { const f = window.fixture; f.release(gate, {...f.payload('owner-a'), history_error: 'program history could not be verified'}); return f.refresh; }, gate);
    assert.equal(await runButton.isDisabled(), true); assert.equal(await source.isDisabled(), true);
    assert.match(await page.locator('[data-program-error]').textContent(), /history could not be verified/);
    await setup(); await source.fill('中'.repeat(21846));
    assert.equal(await runButton.isDisabled(), true); assert.match(await page.locator('[data-program-error]').textContent(), /64 KiB/);
  });
  await test('dispose-fences-late-get-and-post-without-clearing-new-dom-owner', async () => {
    for (const method of ['GET', 'POST']) {
      await setup();
      const gate = await page.evaluate(method => { const f = window.fixture; const gate = f.block(method); f.late = method === 'POST' ? f.panel.run() : f.panel.refresh(); f.oldPanel = f.panel; f.panel.dispose(); return gate; }, method);
      await page.evaluate(async () => { const f = window.fixture; const {createProgramPanel} = await import('/platform/web/program-panel.js'); f.panel = createProgramPanel(document.querySelector('#panel'), {session: f.session('replacement'), api: f.api}); });
      await page.waitForFunction(() => window.fixture.panel.synchronized);
      await source.fill('print("replacement draft")\n');
      const before = await page.evaluate(() => window.fixture.calls.length);
      await page.evaluate(gate => { const f = window.fixture; f.oldPanel.dispose(); f.release(gate, f.payload('owner-a', {execution_id: 'disposed-result', state: 'completed'})); return f.late; }, gate);
      assert.equal(await page.locator('[data-program-panel-root]').count(), 1);
      assert.equal(await source.inputValue(), 'print("replacement draft")\n');
      assert.equal(await page.evaluate(() => window.fixture.calls.length), before);
      assert.equal(await page.evaluate(() => window.fixture.panel.program), null);
    }
  });
  await test('real-poll-timer-and-dispose-stop-further-requests', async () => {
    await setup(); const before = await page.evaluate(() => window.fixture.calls.length);
    await page.clock.runFor(1100);
    assert.equal(await page.evaluate(() => window.fixture.calls.length), before + 1);
    await page.evaluate(() => window.fixture.panel.dispose());
    await page.clock.runFor(4000);
    assert.equal(await page.evaluate(() => window.fixture.calls.length), before + 1);
  });
  await test('responsive-editor-and-keyboard-focus', async () => {
    await setup(); await source.fill('print("UIFlow realtime preview")\n');
    for (const width of [1440, 1024, 768, 390]) {
      await page.setViewportSize({width, height: 900});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.screenshot({path: `${output}/program-panel-${width}.png`});
    }
    await source.focus(); await page.keyboard.press('Tab'); assert.equal(await runButton.evaluate(node => document.activeElement === node), true);
  });
  await test('actual-sessions-page-creation-capability-unit-payload-run-and-stop', async () => {
    const livePage = await browser.newPage({viewport: {width: 1440, height: 1000}});
    livePage.on('pageerror', error => errors.push(error.message));
    try {
      await livePage.goto(`${base}/platform/web/sessions.html`);
      const mode = livePage.locator('#programModeInput');
      await livePage.waitForFunction(() => !document.querySelector('#programModeInput').disabled);
      await livePage.locator('#createBtn').click();
      await livePage.waitForFunction(() => document.querySelectorAll('.session-card').length === 1);
      assert.equal(creationPosts[0].program_mode, undefined);
      assert.equal(await livePage.locator('[data-program-panel-root]').isHidden(), true);
      await mode.check(); await livePage.locator('#deviceSelect').selectOption('tab5');
      assert.equal(await mode.isDisabled(), true); assert.equal(await mode.isChecked(), false);
      await livePage.locator('#deviceSelect').selectOption('atoms3r'); await mode.check();
      await livePage.locator('#unitModelSelect').selectOption('pir');
      await livePage.locator('#createBtn').click();
      await livePage.waitForFunction(() => document.querySelectorAll('.session-card').length === 2);
      assert.equal(creationPosts[1].program_mode, 'uiflow-live');
      assert.deepEqual(creationPosts[1].units, [{id: 'external1', unit_id: 'pir', port_id: 'port-a'}]);
      assert.equal(creationPosts[1].firmware_id, undefined); assert.equal(creationPosts[1].uiflow_source_sha256, undefined);
      const card = livePage.locator('[data-session-id="page-session-2"]');
      await card.locator('[data-program-source]').fill('print("actual page route")\n');
      await card.locator('[data-program-run]').click();
      await livePage.waitForFunction(() => document.querySelector('[data-session-id="page-session-2"] [data-program-state]').textContent === '已完成');
      assert.deepEqual(programPosts.at(-1), {id: 'page-session-2', source: 'print("actual page route")\n', expected_execution_id: null});
      assert.equal(await livePage.locator('#errorBanner').isHidden(), true);
      await livePage.screenshot({path: `${output}/sessions-program.png`, fullPage: true});
      await card.locator('[data-action="stop"]').click();
      await livePage.waitForFunction(() => document.querySelector('[data-session-id="page-session-2"] [data-program-source]').disabled);
      assert.equal(await card.locator('[data-program-run]').isDisabled(), true);
    } finally { await livePage.close(); }
  });
  await test('actual-page-initial-picker-and-device-switch-fenced-in-both-return-orders', async () => {
    for (const oldFirst of [true, false]) {
      const old = catalogGate('atoms3r'), latest = catalogGate('cores3');
      const racePage = await browser.newPage({viewport: {width: 1440, height: 1000}});
      racePage.on('pageerror', error => errors.push(error.message));
      const hostInventory = (deviceId, portId) => ({units: inventory.units.map(unit => ({...unit, runtime: {...unit.runtime, hosts: [deviceId]}})),
        hosts: [{device_id: deviceId, ports: [{id: portId, label: 'Grove', wiring_status: 'confirmed', physical_presence: 'main-device'}]}]});
      try {
        await racePage.goto(`${base}/platform/web/sessions.html`, {waitUntil: 'domcontentloaded'});
        await catalogEntered(old);
        assert.equal(await racePage.locator('#createBtn').isDisabled(), true);
        await racePage.selectOption('#deviceSelect', 'cores3');
        await catalogEntered(latest);
        assert.equal(await racePage.locator('#createBtn').isDisabled(), true);
        assert.equal(await racePage.locator('#unitModelSelect').count(), 0);
        const before = creationPosts.length;
        await racePage.locator('#createBtn').evaluate(node => node.click());
        assert.equal(creationPosts.length, before, 'unready selected host must not send any create request');
        if (oldFirst) {
          releaseCatalog(old, hostInventory('atoms3r', 'custom'));
          await racePage.waitForFunction(() => document.querySelector('#serviceSummary').textContent.includes('API online'));
          assert.equal(await racePage.locator('#createBtn').isDisabled(), true, 'old initial finally must not unlock the pending new host');
          assert.equal(await racePage.locator('#unitModelSelect').count(), 0, 'old initial loader must not paint its custom port');
        }
        releaseCatalog(latest, hostInventory('cores3', 'port-a'));
        await racePage.locator('#unitModelSelect option[value="pir"]').waitFor({state: 'attached'});
        await racePage.selectOption('#unitModelSelect', 'pir');
        await racePage.check('#programModeInput');
        if (!oldFirst) {
          releaseCatalog(old, hostInventory('atoms3r', 'custom'));
          await racePage.waitForFunction(() => document.querySelector('#serviceSummary').textContent.includes('API online'));
        }
        assert.equal(await racePage.locator('#unitModelSelect').inputValue(), 'pir', 'late old dispose must preserve the selected new-host assembly');
        assert.equal(await racePage.locator('#unitPicker > [data-unit-picker-device-id]').getAttribute('data-unit-picker-device-id'), 'cores3');
        assert.equal(await racePage.locator('#createBtn').isDisabled(), false);
        const created = racePage.waitForResponse(response => response.url().endsWith('/api/v1/sessions') && response.request().method() === 'POST');
        await racePage.click('#createBtn');
        assert.equal((await created).status(), 202);
        assert.deepEqual(creationPosts.at(-1), {device_id: 'cores3', ttl_seconds: 600, program_mode: 'uiflow-live', units: [{id: 'external1', unit_id: 'pir', port_id: 'port-a'}]});
      } finally {
        for (const gate of [old, latest]) {
          catalogGates.delete(gate.deviceId);
          for (const response of gate.responses) if (!response.writableEnded) response.destroy();
        }
        await racePage.close();
      }
    }
  });
  assert.deepEqual(errors, []);
  const source_sha256 = {};
  for (const path of ['platform/web/program-panel.js', 'platform/web/program-panel.css', 'platform/web/sessions.js', 'platform/web/sessions.html', 'platform/web/unit-panel.js']) source_sha256[path] = createHash('sha256').update(await readFile(resolve(root, path))).digest('hex');
  await writeFile(`${output}/report.json`, JSON.stringify({category: 'browser-program-orchestration-contract', status: 'PASS', captured_at: new Date().toISOString(), browser_version: browser.version(), source_sha256, checks, firmware_execution: 'NOT RUN', hardware_execution: 'NOT RUN', errors}, null, 2) + '\n');
  console.log(`PROGRAM_PANEL_BROWSER_OK ${checks.length} checks`);
} catch (error) {
  await page.screenshot({path: `${output}/failure.png`});
  await writeFile(`${output}/failure.json`, JSON.stringify({status: 'FAIL', checks, errors, error: error.stack}, null, 2) + '\n');
  throw error;
} finally { await browser.close(); await new Promise(done => server.close(done)); }
