// Managed editor consumer contracts only: no firmware, guest or Device Service.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, extname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = process.env.M5_PREVIEW_PROGRAM_OUT || '/tmp/m5-preview-program-panel-test';
await mkdir(output, {recursive: true});
const checks = [], errors = [];
const compare = (a, b) => {
  const left = [...a], right = [...b];
  for (let i = 0; i < Math.min(left.length, right.length); i += 1) {
    const delta = left[i].codePointAt(0) - right[i].codePointAt(0); if (delta) return delta;
  }
  return left.length - right.length;
};
const canonical = row => Array.isArray(row) ? `[${row.map(canonical).join(',')}]`
  : row && typeof row === 'object' ? `{${Object.keys(row).sort(compare).map(key => `${JSON.stringify(key)}:${canonical(row[key])}`).join(',')}}` : JSON.stringify(row);
const digest = row => createHash('sha256').update(row).digest('hex');
function packageOf(files) {
  const hashes = {}, rows = [], encoded = {}; let total = 0;
  for (const path of Object.keys(files).sort(compare)) {
    const file = files[path], bytes = Buffer.from(file.data, file.encoding === 'utf8' ? 'utf8' : 'base64');
    hashes[path] = digest(bytes); total += bytes.length;
    rows.push({path, sha256: hashes[path], size: bytes.length, kind: path.endsWith('.py') ? 'python' : path.endsWith('.mpy') ? 'mpy' : 'resource'});
    encoded[path] = {encoding: 'base64', data: bytes.toString('base64')};
  }
  return {revision: {revision_id: digest(canonical({source_kind: 'uiflow2-package', entrypoint: 'main.py', files: hashes})),
    source_sha256: digest(canonical(hashes)), source_kind: 'uiflow2-package', entrypoint: 'main.py', total_file_bytes: total, files: rows,
    created_at: '2026-10-27T00:00:00Z'}, files: encoded};
}
const filesOf = (main = 'print("package")\n') => ({
  'main.py': {encoding: 'utf8', data: main},
  'helper.mpy': {encoding: 'base64', data: Buffer.from([77, 6, 0, 31, 128, 255]).toString('base64')},
  'lib/模块.py': {encoding: 'utf8', data: 'value = "模块"\n'},
  'assets/raw.bin': {encoding: 'base64', data: Buffer.from([0, 255, 0, 13, 10, 128]).toString('base64')},
});
const original = packageOf(filesOf()), external = packageOf(filesOf('print("external")\n'));
const json = (res, value) => { res.writeHead(200, {'Content-Type': 'application/json'}); res.end(JSON.stringify(value)); };
const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, 'http://localhost').pathname;
    if (path === '/harness') {
      res.setHeader('Content-Type', 'text/html');
      res.end('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/platform/web/app.css"><link rel="stylesheet" href="/platform/web/m5-tokens.css"><link rel="stylesheet" href="/platform/web/m5-brand.css"><link rel="stylesheet" href="/platform/web/program-panel.css"><style>main{max-width:760px;padding:12px;margin:auto}</style></head><body><main id="panel"></main></body></html>'); return;
    }
    if (path === '/fixture/package') { let body = ''; for await (const part of req) body += part; return json(res, packageOf(JSON.parse(body))); }
    const file = resolve(root, `.${path}`);
    if (!file.startsWith(root + '/')) { res.writeHead(403).end(); return; }
    res.setHeader('Content-Type', {'.js': 'text/javascript', '.css': 'text/css'}[extname(file)] || 'application/octet-stream');
    res.end(await readFile(file));
  } catch { res.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
const page = await browser.newPage({viewport: {width: 1024, height: 900}});
page.on('pageerror', error => errors.push(error.message));
const base = `http://127.0.0.1:${server.address().port}`;
const source = page.locator('[data-program-source]'), run = page.locator('[data-program-run]'), cancel = page.locator('[data-program-cancel]');
async function test(name, action) { await action(); checks.push(name); }
async function settle() { await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 0))); }
async function setup(options = {}) {
  await page.evaluate(async ({options, original, external}) => {
    window.fixture?.panel.dispose();
    const {createProgramPanel} = await import('/platform/web/program-panel.js');
    const f = window.fixture = {calls: [], runCalls: [], cancelCalls: [], runIntents: [], subscriptions: new Set(),
      saves: [], loads: [], admissions: [], receipts: [], gates: [], refreshes: 0,
      packages: new Map([original, external].map(pack => [pack.revision.revision_id, pack])),
      session: {session_id: 'session-a', device_id: 'atoms3r', state: 'running', created_at: '2026-10-27T00:00:00Z',
        firmware_sha256: 'a'.repeat(64), program_transport: 'uart-repl',
        management_binding: {preview_id: 'preview-a', owner_epoch: 'epoch-a', expected_reference_sha256: 'a'.repeat(64)}},
      makeRun(id, revision, state = 'running', generation = null) { return {run_id: id, execution_id: `execution-${id}`,
        revision_id: revision, state, request: {client_generation: generation}}; },
      block(queue) { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
        const gate = {promise, resolve, reject}; this.gates.push(gate); this[queue].push(gate); return this.gates.length - 1; },
      release(index, value, error) { if (error) this.gates[index].reject(new Error(error)); else this.gates[index].resolve(value); },
      emit(patch = {}) { this.state = {...this.state, ...patch}; for (const listener of this.subscriptions) listener(structuredClone(this.state)); },
      external(state = 'running') { const row = this.makeRun('external', external.revision.revision_id, state);
        this.emit({desiredRun: row, cancelRunId: row.run_id, canCancel: true, preview: {...this.state.preview, generation: 2}}); },
    };
    f.state = {managed: true, synchronized: !options.unsynchronized, pending: false, error: '', canSubmit: true, canCancel: false,
      cancelRunId: null, preview: {preview_id: 'preview-a', owner_epoch: 'epoch-a', session_id: 'session-a', state: 'ready', generation: options.existing ? 1 : 0},
      activeRun: options.existing ? f.makeRun('original', original.revision.revision_id) : null, desiredRun: null, transitionRun: null};
    if (options.existing) { f.state.canCancel = true; f.state.cancelRunId = 'original'; }
    f.client = {
      subscribe(listener) { f.subscriptions.add(listener); listener(structuredClone(f.state)); return () => f.subscriptions.delete(listener); },
      async refresh() { f.refreshes += 1; if (f.refreshError) throw new Error(f.refreshError); return structuredClone(f.state); },
      async runRevision(revision, options) {
        f.runIntents.push({revision, clientGeneration: options.clientGeneration});
        const admission = f.admissions.shift(); if (admission) await admission.promise;
        options.beforeAdmission?.(structuredClone(f.state));
        f.runCalls.push({revision, clientGeneration: options.clientGeneration});
        const receipt = f.receipts.shift(); if (receipt) return await receipt.promise;
        return {revision_id: revision, run_id: `own-${f.runCalls.length}`};
      },
      async cancel(id) { f.cancelCalls.push(id); if (f.cancelError) throw new Error(f.cancelError); },
    };
    f.api = async (path, request = {}) => {
      const method = request.method || 'GET', body = request.body ? JSON.parse(request.body) : null;
      f.calls.push({path, method, body});
      const gate = (method === 'POST' ? f.saves : f.loads).shift();
      if (gate) { const value = await gate.promise; if (value) return structuredClone(value); }
      if (method === 'POST') {
        const response = await fetch('/fixture/package', {method: 'POST', body: JSON.stringify(body.files)}); return await response.json();
      }
      const id = path.split('/').at(-2); return structuredClone(f.packages.get(id));
    };
    if (options.randomUnavailable) Object.defineProperty(globalThis.crypto, 'getRandomValues', {configurable: true, value: undefined});
    f.panel = createProgramPanel(document.querySelector('#panel'), {session: options.invalidBinding ? {...f.session, management_binding: options.invalidBinding} : f.session,
      api: f.api, ...(options.noClient ? {} : {previewClient: f.client})});
    if (options.randomUnavailable) delete globalThis.crypto.getRandomValues;
  }, {options, original, external});
  await settle();
}
async function load() { await page.locator('[data-program-load]').click(); await page.waitForFunction(() => !window.fixture.panel.loadPending); }
async function waitSave(count = 1) { await page.waitForFunction(count => window.fixture.calls.filter(row => row.method === 'POST').length >= count, count); }
async function setupRealCancellation(options) {
  await setup({existing: true});
  await page.evaluate(async ({options, original, external}) => {
    const f = fixture; f.panel.dispose();
    const {createPreviewClient} = await import('/platform/web/preview-client.js');
    const {createProgramPanel} = await import('/platform/web/program-panel.js');
    const id = number => number.toString(16).padStart(32, '0'), now = () => new Date().toISOString();
    f.session = {...f.session, session_id: id(1), pid: 1234, firmware_sha256: 'e'.repeat(64),
      management_binding: {preview_id: id(2), owner_epoch: id(3), expected_reference_sha256: 'f'.repeat(64)}};
    f.runs = new Map(); f.calls = []; f.cancelled = []; f.receipt = null; f.b = null; f.c = null; f.localRuns = [];
    f.gate = (() => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return {promise, resolve, reject}; })();
    f.makeRun = (generation, revision, request = null) => ({preview_id: id(2), run_id: id(10 + generation), execution_id: id(20 + generation),
      revision_id: revision, generation, source_kind: 'uiflow2-package', state: 'running', request: request || {
        revision_id: revision, expected_owner_epoch: id(3), expected_generation: generation - 1},
      client_generation: request?.client_generation ?? null, timeout_seconds: 120, cancel_intent: false, interrupt_ack: 'unknown',
      application_ready: 'unknown', execution_mode: 'same-guest-uart-repl', cleanup_mode: 'interrupt-only', error: null, created_at: now(), updated_at: now(),
      last_observation: {execution_id: id(20 + generation), revision_id: revision, firmware_sha256: f.session.firmware_sha256,
        pid: f.session.pid, execution_mode: 'same-guest-uart-repl', state: 'running', acknowledged: true}});
    const first = f.makeRun(1, original.revision.revision_id); f.runs.set(first.run_id, first);
    f.preview = {preview_id: id(2), owner: 'local-control', owner_epoch: id(3), generation: 1, state: 'ready',
      session_id: id(1), session_identity: {session_id: id(1), firmware_sha256: f.session.firmware_sha256}, request: {device_id: 'atoms3r'},
      session_request: {device_id: 'atoms3r', reference_sha256: 'f'.repeat(64)}, allocation_state: 'bound', allocation_key: `preview:${id(2)}:allocation:1`,
      created_at: now(), updated_at: now(), expires_at: new Date(Date.now() + 600000).toISOString(), active_run_id: first.run_id,
      desired_run_id: first.run_id, transition_run_id: null, error: null,
      capabilities: {execution_mode: 'same-guest-uart-repl', cleanup_mode: 'interrupt-only', latest_wins: true, run_cancellation: true,
        input: true, frame: 'on-demand', events: 'polling', application_ready: 'unknown', main_mpy: false, hotplug: false, gc_enabled: false,
        principal_mode: 'shared-control-bearer-local-control'},
      limits: {max_previews: 128, max_runs_per_preview: 256, gc_enabled: false, retention_mode: 'retention-only'}};
    f.activate = (revision, request = null) => {
      for (const row of f.runs.values()) if (['running', 'queued', 'preparing', 'starting'].includes(row.state)) {
        Object.assign(row, {state: 'cancelled', cancel_intent: true, interrupt_ack: 'confirmed', updated_at: now()});
      }
      const row = f.makeRun(++f.preview.generation, revision, request); f.runs.set(row.run_id, row);
      f.preview.active_run_id = f.preview.desired_run_id = row.run_id; f.preview.updated_at = now(); return row;
    };
    f.api = async (path, request = {}) => {
      const method = request.method || 'GET', body = request.body ? JSON.parse(request.body) : null;
      f.calls.push({path, method, body});
      if (path === '/api/v1/program-revisions') {
        const response = await fetch('/fixture/package', {method: 'POST', body: JSON.stringify(body.files)}); return await response.json();
      }
      if (path.endsWith('/files')) return structuredClone(original);
      if (path === `/api/v1/previews/${id(2)}`) {
        if (f.externalOnRefresh && f.b) { f.externalOnRefresh = false; f.c = f.activate(external.revision.revision_id); }
        return structuredClone(f.preview);
      }
      if (path.endsWith('/runs') && method === 'POST') {
        f.dispatched = true;
        if (options.window === 'pre-commit') await f.gate.promise;
        if (body.expected_generation !== f.preview.generation) throw Object.assign(new Error('generation conflict'), {effectPossible: false, status: 409});
        const admitted = f.activate(body.revision_id, body); f.b ||= admitted; f.localRuns.push(admitted);
        const receipt = {...structuredClone(admitted), state: 'queued'}; delete receipt.last_observation; f.receipt ||= receipt;
        if (options.window !== 'pre-commit') await f.gate.promise;
        if (options.failReceipt) throw Object.assign(new Error('Run response stream lost'), {effectPossible: true});
        return structuredClone(receipt);
      }
      const target = path.match(/\/runs\/([0-9a-f]{32})(\/cancel)?$/);
      if (target) {
        const row = f.runs.get(target[1]);
        if (target[2]) {
          f.cancelled.push(row.run_id); Object.assign(row, {state: 'cancelled', cancel_intent: true, interrupt_ack: 'confirmed', updated_at: now()});
          if (f.preview.active_run_id === row.run_id) f.preview.active_run_id = null;
          f.preview.updated_at = now();
        }
        return structuredClone(row);
      }
      throw new Error('Unexpected real-client fixture path: ' + path);
    };
    f.client = createPreviewClient({session: f.session, api: f.api}); await f.client.refresh();
    f.panel = createProgramPanel(document.querySelector('#panel'), {session: f.session, api: f.api, previewClient: f.client});
  }, {options, original, external});
  await load();
}
try {
  await page.goto(`${base}/harness`);
  await test('empty-preview-main-only-checkpoint-and-authoritative-status', async () => {
    await setup(); assert.equal(await run.isEnabled(), true);
    await source.fill('print("first")\n'); await run.click();
    await page.waitForFunction(() => window.fixture.runCalls.length === 1 && !window.fixture.panel.saving);
    const result = await page.evaluate(() => ({call: fixture.calls[0], run: fixture.runCalls[0], state: fixture.panel.status.textContent}));
    assert.equal(result.call.path, '/api/v1/program-revisions');
    assert.deepEqual(result.call.body, {source_kind: 'uiflow2-package', entrypoint: 'main.py', files: {'main.py': {encoding: 'utf8', data: 'print("first")\n'}}});
    assert.match(result.run.revision, /^[a-f0-9]{64}$/); assert.equal(result.state, '尚未运行');
    assert.match(await page.locator('[data-program-detail]').innerText(), /以同步状态为准/);
  });
  await test('existing-package-requires-explicit-load-and-preserves-mpy-resources-and-modules', async () => {
    await setup({existing: true}); assert.equal(await run.isDisabled(), true); assert.equal(await source.isEnabled(), true);
    await load(); assert.equal(await source.inputValue(), 'print("package")\n');
    await source.fill('print("edited")\n'); await run.click();
    await page.waitForFunction(() => fixture.runCalls.length === 1 && !fixture.panel.saving);
    const saved = await page.evaluate(() => fixture.calls.find(row => row.method === 'POST').body.files);
    assert.equal(saved['main.py'].data, 'print("edited")\n');
    for (const [path, file] of Object.entries(original.files)) if (path !== 'main.py') assert.deepEqual(saved[path], file);
  });
  await test('dirty-load-has-explicit-adopt-and-merge-choices', async () => {
    await setup({existing: true}); await source.fill('print("draft")\n'); await load();
    assert.equal(await source.inputValue(), 'print("draft")\n'); assert.equal(await run.isDisabled(), true);
    await page.locator('[data-program-merge]').click(); assert.equal(await source.inputValue(), 'print("draft")\n'); assert.equal(await run.isEnabled(), true);
    await load(); await page.locator('[data-program-adopt]').click(); assert.equal(await source.inputValue(), 'print("package")\n');
  });
  await test('editing-during-download-never-overwrites-draft', async () => {
    await setup({existing: true});
    const gate = await page.evaluate(() => fixture.block('loads'));
    await page.locator('[data-program-load]').click(); await source.fill('print("during download")\n');
    await page.evaluate(({gate, original}) => fixture.release(gate, original), {gate, original});
    await page.waitForFunction(() => !!fixture.panel.staged);
    assert.equal(await source.inputValue(), 'print("during download")\n');
  });
  await test('external-revision-never-overwrites-draft-and-requires-explicit-dependency-sync', async () => {
    await setup({existing: true}); await load(); await source.fill('print("local")\n');
    await page.evaluate(() => fixture.external());
    assert.equal(await source.inputValue(), 'print("local")\n'); assert.equal(await run.isDisabled(), true);
    await load(); await page.locator('[data-program-merge]').click(); assert.equal(await run.isEnabled(), true);
    await run.click(); await page.waitForFunction(() => fixture.runCalls.length === 1);
    assert.equal(await source.inputValue(), 'print("local")\n');
  });
  await test('two-checkpoint-saves-complete-out-of-order-latest-click-only', async () => {
    await setup();
    const gates = await page.evaluate(() => [fixture.block('saves'), fixture.block('saves')]);
    await source.fill('print("A")\n'); await run.click(); await source.fill('print("B")\n'); await run.click(); await waitSave(2);
    await page.evaluate(gate => fixture.release(gate), gates[1]); await page.waitForFunction(() => fixture.runCalls.length === 1);
    await page.evaluate(gate => fixture.release(gate), gates[0]); await settle();
    assert.equal(await page.evaluate(() => fixture.runCalls.length), 1);
    assert.equal(await page.evaluate(() => fixture.panel.workspace.main), 'print("B")\n');
    assert.equal(await source.inputValue(), 'print("B")\n');
  });
  await test('new-edit-during-save-is-preserved-and-remains-dirty', async () => {
    await setup(); const gate = await page.evaluate(() => fixture.block('saves'));
    await source.fill('print("snapshot")\n'); await run.click(); await source.fill('print("new edit")\n');
    await page.evaluate(gate => fixture.release(gate), gate); await page.waitForFunction(() => !fixture.panel.saving);
    assert.equal(await source.inputValue(), 'print("new edit")\n');
    assert.equal(await page.evaluate(() => fixture.panel.workspace.main), 'print("snapshot")\n');
    assert.match(await page.locator('[data-program-draft]').innerText(), /本地修改/);
  });
  await test('fresh-before-admission-external-package-fence-does-not-post-run', async () => {
    await setup({existing: true}); await load(); const gate = await page.evaluate(() => fixture.block('admissions'));
    await run.click(); await page.waitForFunction(() => fixture.runIntents.length === 1);
    await page.evaluate(gate => { fixture.external(); fixture.release(gate); }, gate); await page.waitForFunction(() => !fixture.panel.saving);
    assert.equal(await page.evaluate(() => fixture.runCalls.length), 0);
    assert.match(await page.locator('[data-program-error]').innerText(), /外部完整包已变化/);
  });
  await test('newer-click-fences-already-queued-old-admission', async () => {
    await setup(); const gate = await page.evaluate(() => fixture.block('admissions'));
    await source.fill('print("old")\n'); await run.click(); await page.waitForFunction(() => fixture.runIntents.length === 1);
    await source.fill('print("new")\n'); await run.click(); await page.waitForFunction(() => fixture.runCalls.length === 1);
    await page.evaluate(gate => fixture.release(gate), gate); await settle();
    assert.equal(await page.evaluate(() => fixture.runCalls.length), 1);
    assert.equal(await page.evaluate(() => fixture.panel.workspace.main), 'print("new")\n');
  });
  await test('cancel-is-independent-of-slow-save-and-does-not-claim-interrupt-success', async () => {
    await setup({existing: true}); await load(); const gate = await page.evaluate(() => fixture.block('saves'));
    await run.click(); await waitSave(); await cancel.click();
    assert.deepEqual(await page.evaluate(() => fixture.cancelCalls), ['original']);
    assert.equal(await page.locator('[data-program-state]').innerText(), '运行中');
    assert.match(await page.locator('[data-program-detail]').innerText(), /需要服务器确认中断/);
    await page.evaluate(gate => fixture.release(gate), gate); await settle(); assert.equal(await page.evaluate(() => fixture.runCalls.length), 0);
    await page.evaluate(() => fixture.emit({activeRun: {...fixture.state.activeRun, state: 'cancelling'}}));
    assert.equal(await page.locator('[data-program-state]').innerText(), '等待中断确认');
  });
  await test('cancel-fences-waiting-run-admission-and-slow-receipt', async () => {
    for (const queue of ['admissions', 'receipts']) {
      await setup({existing: true}); await load(); const gate = await page.evaluate(queue => fixture.block(queue), queue);
      await run.click(); await page.waitForFunction(() => fixture.runIntents.length === 1); await cancel.click();
      await page.evaluate(({gate, original}) => fixture.release(gate, {revision_id: original.revision.revision_id}), {gate, original}); await settle();
      assert.equal(await page.evaluate(() => fixture.panel.workspace.revisionId), original.revision.revision_id);
      assert.equal(await page.evaluate(() => fixture.runCalls.length), queue === 'admissions' ? 0 : 1);
    }
  });
  await test('real-shared-client-cancels-exact-generation-before-commit-and-with-blocked-receipt', async () => {
    for (const window of ['pre-commit', 'late-receipt']) {
      await setupRealCancellation({window}); await source.fill(`print("${window}")\n`); await run.click();
      await page.waitForFunction(() => fixture.dispatched && (fixture.b || !fixture.receipt));
      if (window === 'late-receipt') await page.waitForFunction(() => !!fixture.b);
      await cancel.click();
      if (window === 'pre-commit') {
        assert.equal(await page.evaluate(() => !!fixture.b), false);
        await page.evaluate(() => fixture.gate.resolve());
      }
      await page.waitForFunction(() => fixture.b?.state === 'cancelled' && fixture.cancelled.includes(fixture.b.run_id));
      if (window === 'late-receipt') await page.evaluate(() => fixture.gate.resolve());
      await page.evaluate(() => fixture.client.refresh());
      assert.equal(await page.evaluate(() => fixture.client.snapshot().desiredRun.state), 'cancelled');
      assert.equal(await page.locator('[data-program-state]').innerText(), '已取消');
      await page.evaluate(() => fixture.client.dispose());
    }
  });
  await test('negative-control-old-captured-run-only-cancel-leaves-admitted-late-receipt-run-running', async () => {
    await setupRealCancellation({window: 'late-receipt'}); await source.fill('print("negative B")\n'); await run.click();
    await page.waitForFunction(() => !!fixture.b);
    await page.evaluate(async () => {
      const f = fixture; clearTimeout(f.client.timer);
      // Retain the old algorithm as an executable negative control. It drops
      // the late receipt and cancels only A, without retaining B's generation.
      const target = f.panel.state.cancelRunId;
      if (target === f.b.run_id) throw new Error('negative fixture missed stale-A window');
      f.panel.click += 1; f.panel.saving = null;
      await f.client.cancel(target); await f.client.refresh();
    });
    assert.equal(await page.evaluate(() => fixture.b.state), 'running');
    assert.equal(await page.evaluate(() => fixture.cancelled.includes(fixture.b.run_id)), false);
    await page.evaluate(() => fixture.gate.resolve()); await page.evaluate(() => fixture.client.dispose());
  });
  await test('real-shared-client-lost-receipt-still-resolves-cancel-intent-from-poll', async () => {
    await setupRealCancellation({window: 'pre-commit', failReceipt: true}); await source.fill('print("lost receipt")\n'); await run.click();
    await page.waitForFunction(() => fixture.dispatched); await cancel.click(); await page.evaluate(() => fixture.gate.resolve());
    await page.waitForFunction(() => fixture.b?.state === 'cancelled' && fixture.cancelled.includes(fixture.b.run_id));
    await page.evaluate(() => fixture.client.refresh()); assert.equal(await page.locator('[data-program-state]').innerText(), '已取消');
    await page.evaluate(() => fixture.client.dispose());
  });
  await test('real-shared-client-pending-cancel-never-retargets-later-external-run', async () => {
    await setupRealCancellation({window: 'late-receipt'}); await source.fill('print("B")\n'); await run.click();
    await page.waitForFunction(() => !!fixture.b); await page.evaluate(() => { fixture.externalOnRefresh = true; }); await cancel.click();
    await page.waitForFunction(() => !!fixture.c); await page.evaluate(() => fixture.gate.resolve()); await page.evaluate(() => fixture.client.refresh());
    assert.equal(await page.evaluate(() => fixture.c.state), 'running');
    assert.equal(await page.evaluate(() => fixture.cancelled.includes(fixture.c.run_id)), false);
    assert.equal(await page.evaluate(() => fixture.client.snapshot().activeRun.run_id === fixture.c.run_id), true);
    await page.evaluate(() => fixture.client.dispose());
  });
  await test('real-shared-client-later-local-run-does-not-inherit-earlier-cancel-intent', async () => {
    await setupRealCancellation({window: 'late-receipt'}); await source.fill('print("B")\n'); await run.click();
    await page.waitForFunction(() => !!fixture.b); await cancel.click();
    await page.waitForFunction(() => fixture.b.state === 'cancelled');
    await source.fill('print("later C")\n'); await run.click();
    await page.waitForFunction(() => fixture.calls.filter(row => row.path === '/api/v1/program-revisions').length === 2);
    await page.evaluate(() => fixture.gate.resolve());
    await page.waitForFunction(() => fixture.localRuns.length === 2); await page.evaluate(() => fixture.client.refresh());
    assert.equal(await page.evaluate(() => fixture.localRuns[1].state), 'running');
    assert.equal(await page.evaluate(() => fixture.cancelled.includes(fixture.localRuns[1].run_id)), false);
    await page.evaluate(() => fixture.client.dispose());
  });
  await test('source-remains-editable-for-all-server-transition-states', async () => {
    await setup({existing: true}); await load();
    for (const state of ['queued', 'preparing', 'starting', 'running', 'cancelling', 'unknown']) {
      await page.evaluate(state => fixture.emit({activeRun: {...fixture.state.activeRun, state}, pending: state === 'preparing'}), state);
      assert.equal(await source.isEnabled(), true); await source.fill(`print("${state}")\n`);
    }
  });
  await test('ambiguous-save-run-and-cancel-errors-preserve-source-and-never-retry', async () => {
    for (const queue of ['saves', 'receipts']) {
      await setup(); const gate = await page.evaluate(queue => fixture.block(queue), queue);
      await source.fill('print("keep")\n'); await run.click();
      if (queue === 'receipts') await page.waitForFunction(() => fixture.runCalls.length === 1); else await waitSave();
      await page.evaluate(gate => fixture.release(gate, null, 'connection lost'), gate); await page.waitForFunction(() => !fixture.panel.saving);
      assert.equal(await source.inputValue(), 'print("keep")\n'); assert.match(await page.locator('[data-program-error]').innerText(), /未确认.*不会自动重试/);
      assert.equal(await page.evaluate(() => fixture.calls.filter(row => row.method === 'POST').length), 1);
    }
    await setup({existing: true}); await page.evaluate(() => { fixture.cancelError = 'connection lost'; }); await cancel.click();
    assert.match(await page.locator('[data-program-error]').innerText(), /取消结果未确认/); assert.equal(await page.locator('[data-program-state]').innerText(), '运行中');
  });
  await test('owner-change-and-dispose-fence-late-load-save-and-subscriptions', async () => {
    await setup({existing: true}); const gate = await page.evaluate(() => fixture.block('loads'));
    await page.locator('[data-program-load]').click(); await source.fill('print("owner draft")\n');
    await page.evaluate(() => fixture.panel.updateSession({...fixture.session, session_id: 'session-b'}));
    await page.evaluate(({gate, original}) => fixture.release(gate, original), {gate, original}); await settle();
    assert.equal(await source.inputValue(), 'print("owner draft")\n'); assert.equal(await run.isDisabled(), true);
    await page.evaluate(() => fixture.emit()); assert.equal(await run.isDisabled(), true); assert.match(await page.locator('[data-program-error]').innerText(), /不属于当前会话/);
    await setup(); const save = await page.evaluate(() => fixture.block('saves')); await run.click();
    await page.evaluate(() => fixture.panel.dispose()); await page.evaluate(gate => fixture.release(gate), save); await settle();
    assert.equal(await page.evaluate(() => fixture.subscriptions.size), 0); assert.equal(await page.evaluate(() => fixture.runCalls.length), 0);
  });
  await test('malformed-non-null-binding-never-falls-back-to-legacy', async () => {
    for (const binding of [1, {}, 'invalid']) {
      await setup({invalidBinding: binding, noClient: true}); assert.equal(await run.isDisabled(), true);
      await page.evaluate(() => fixture.panel.run()); assert.deepEqual(await page.evaluate(() => fixture.calls), []);
    }
  });
  await test('legacy-instance-that-later-receives-binding-closes-old-mutation-path', async () => {
    await page.evaluate(async () => {
      fixture.panel.dispose(); const {createProgramPanel} = await import('/platform/web/program-panel.js');
      fixture.calls = []; fixture.api = async (path, options = {}) => { fixture.calls.push({path, method: options.method || 'GET'});
        return {session_id: 'session-a', program_transport: 'uart-repl', program: null}; };
      const legacy = {...fixture.session}; delete legacy.management_binding;
      fixture.panel = createProgramPanel(document.querySelector('#panel'), {session: legacy, api: fixture.api});
    });
    await page.waitForFunction(() => fixture.panel.synchronized);
    await page.evaluate(() => { fixture.calls = []; fixture.panel.updateSession({...fixture.session, management_binding: 0}); });
    await page.evaluate(() => fixture.panel.run()); assert.deepEqual(await page.evaluate(() => fixture.calls), []); assert.equal(await run.isDisabled(), true);
  });
  await test('secure-random-failure-closes-run-without-legacy-or-weak-key-fallback', async () => {
    await setup({randomUnavailable: true}); assert.equal(await run.isDisabled(), true);
    assert.match(await page.locator('[data-program-error]').innerText(), /安全随机源不可用/);
  });
  await test('package-download-validation-fails-closed-for-tampering-and-path-format-limits', async () => {
    const invalid = [];
    const altered = structuredClone(original); altered.files['assets/raw.bin'].data = 'AP8A'; invalid.push(['hash', altered]);
    const metadata = structuredClone(original); metadata.revision.files[0].size += 1; invalid.push(['metadata-size', metadata]);
    const base64 = structuredClone(original); base64.files['assets/raw.bin'].data = 'AB=='; invalid.push(['noncanonical-base64', base64]);
    const utf8 = structuredClone(original); utf8.files['main.py'] = {encoding: 'utf8', data: 'print(1)'}; invalid.push(['download-utf8-not-base64', utf8]);
    const make = (label, files) => invalid.push([label, packageOf(files)]);
    make('traversal', {'main.py': {encoding: 'utf8', data: ''}, '../escape': {encoding: 'utf8', data: ''}});
    make('reserved', {'main.py': {encoding: 'utf8', data: ''}, 'lib/BOOT.py': {encoding: 'utf8', data: ''}});
    make('case-collision', {'main.py': {encoding: 'utf8', data: ''}, 'Data': {encoding: 'utf8', data: ''}, 'data': {encoding: 'utf8', data: ''}});
    make('parent-file', {'main.py': {encoding: 'utf8', data: ''}, 'lib': {encoding: 'utf8', data: ''}, 'lib/a': {encoding: 'utf8', data: ''}});
    make('directory-case-collision', {'main.py': {encoding: 'utf8', data: ''}, 'Dir/a': {encoding: 'utf8', data: ''}, 'dir/b': {encoding: 'utf8', data: ''}});
    make('non-nfc', {'main.py': {encoding: 'utf8', data: ''}, 'e\u0301.txt': {encoding: 'utf8', data: ''}});
    make('nul-python', {'main.py': {encoding: 'utf8', data: '\0'}});
    make('bad-mpy-header', {'main.py': {encoding: 'utf8', data: ''}, 'helper.mpy': {encoding: 'base64', data: 'TQaAHw=='}});
    make('file-limit', {'main.py': {encoding: 'utf8', data: 'x'.repeat(262145)}});
    make('count-limit', Object.fromEntries([['main.py', {encoding: 'utf8', data: ''}], ...Array.from({length: 64}, (_, i) => [`${i}.txt`, {encoding: 'utf8', data: ''}])]));
    make('total-limit', Object.fromEntries([['main.py', {encoding: 'utf8', data: ''}], ...Array.from({length: 5}, (_, i) => [`${i}.txt`, {encoding: 'utf8', data: 'x'.repeat(262144)}])]));
    for (const [label, pack] of invalid) {
      await setup({existing: true}); await page.evaluate(pack => { const f = fixture;
        f.packages.set(pack.revision.revision_id, pack); f.emit({activeRun: f.makeRun('invalid', pack.revision.revision_id)}); }, pack);
      await load(); assert.equal(await run.isDisabled(), true, label); assert.match(await page.locator('[data-program-error]').innerText(), /加载完整包失败/, label);
      assert.equal(await page.evaluate(() => fixture.panel.workspace), null, label);
    }
  });
  await test('bom-unicode-codepoint-and-numeric-filename-hashes-preserve-exact-bytes-on-http', async () => {
    const pack = packageOf({'main.py': {encoding: 'utf8', data: '\ufeffprint("BOM")\n'}, '2': {encoding: 'utf8', data: 'two'}, '10': {encoding: 'utf8', data: 'ten'},
      '\ue000.txt': {encoding: 'utf8', data: 'private'}, '😀.txt': {encoding: 'utf8', data: 'emoji'}});
    // Golden digest from the host Python program_packages._snapshot(), whose
    // canonical JSON sorts Unicode code points rather than UTF-16 units.
    assert.equal(pack.revision.revision_id, 'c17c0682c4eb471ba52a240378c15dc652be702bcc1725f72e413877de80c3af');
    await setup({existing: true}); await page.evaluate(pack => { fixture.packages.set(pack.revision.revision_id, pack);
      fixture.emit({activeRun: fixture.makeRun('unicode', pack.revision.revision_id)}); }, pack);
    await load(); assert.equal(await source.inputValue(), '\ufeffprint("BOM")\n'); await run.click();
    await page.waitForFunction(() => fixture.runCalls.length === 1 && !fixture.panel.saving);
    assert.equal(await page.evaluate(() => fixture.runCalls[0].revision), pack.revision.revision_id);
    assert.equal(new URL(page.url()).protocol, 'http:');
  });
  await test('main-byte-limit-does-not-disable-editor-and-notice-is-authoritative', async () => {
    await setup(); await source.fill('中'.repeat(87382)); assert.equal(await source.isEnabled(), true); assert.equal(await run.isDisabled(), true);
    assert.match(await page.locator('[data-program-error]').innerText(), /256 KiB/);
  });
  await test('untouched-main-preserves-original-crlf-bytes-through-textarea-normalization', async () => {
    const pack = packageOf(filesOf('print("CRLF")\r\nprint("tail")\r'));
    await setup({existing: true}); await page.evaluate(pack => { fixture.packages.set(pack.revision.revision_id, pack);
      fixture.emit({activeRun: fixture.makeRun('crlf', pack.revision.revision_id)}); }, pack);
    await load(); assert.equal(await source.inputValue(), 'print("CRLF")\nprint("tail")\n');
    assert.equal(await page.evaluate(() => fixture.panel.dirty()), false); await run.click();
    await page.waitForFunction(() => fixture.runCalls.length === 1 && !fixture.panel.saving);
    assert.equal(await page.evaluate(() => fixture.runCalls[0].revision), pack.revision.revision_id);
    assert.equal(await page.evaluate(() => fixture.calls.find(row => row.method === 'POST').body.files['main.py'].data), 'print("CRLF")\r\nprint("tail")\r');
  });
  await test('four-responsive-viewports-and-keyboard-focus', async () => {
    await setup({existing: true}); await load(); await source.fill('print("本地草稿与依赖包")\n');
    for (const width of [1440, 1024, 768, 390]) {
      await page.setViewportSize({width, height: 1000});
      await page.evaluate(() => new Promise(done => { scrollTo(0, 0); requestAnimationFrame(() => requestAnimationFrame(done)); }));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `overflow at ${width}`);
      assert.equal(await page.locator('[data-program-panel-root]').count(), 1);
      assert.equal(await source.isVisible(), true); await page.locator('#panel').screenshot({path: `${output}/preview-editor-${width}.png`});
    }
    await source.focus(); await page.keyboard.press('Tab'); assert.equal(await run.evaluate(node => node === document.activeElement), true);
  });
  assert.deepEqual(errors, []);
  const source_sha256 = {};
  for (const path of ['platform/web/program-panel.js', 'platform/web/program-panel.css', 'platform/web/preview-client.js', 'platform/web/sha256.js', 'platform/tests/test_preview_program_panel.mjs']) source_sha256[path] = digest(await readFile(resolve(root, path)));
  await writeFile(`${output}/report.json`, JSON.stringify({category: 'preview-editor-browser-consumer-contract', status: 'PASS',
    captured_at: new Date().toISOString(), browser_version: browser.version(), source_sha256, checks, errors,
    shared_client: 'deterministic editor fixtures plus real shared-client cancellation race integration; no live service', firmware_execution: 'NOT RUN', hardware_execution: 'NOT RUN'}, null, 2) + '\n');
  console.log(`PREVIEW_PROGRAM_PANEL_BROWSER_OK ${checks.length} checks`);
} catch (error) {
  await page.screenshot({path: `${output}/failure.png`});
  await writeFile(`${output}/failure.json`, JSON.stringify({status: 'FAIL', checks, errors, error: error.stack}, null, 2) + '\n'); throw error;
} finally { await browser.close(); await new Promise(done => server.close(done)); }
