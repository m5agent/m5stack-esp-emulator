// Deterministic browser protocol/lifecycle fixtures only. No guest or firmware.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {resolve, dirname, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = process.env.M5_PREVIEW_UNIT_PANEL_OUT || '/tmp/m5-preview-unit-panel-test';
await mkdir(output, {recursive: true});
const catalog = JSON.parse(await readFile(resolve(root, 'platform/units/catalog.json'), 'utf8'));
const profiles = JSON.parse(await readFile(resolve(root, 'platform/units/runtime-profiles.json'), 'utf8')).units;
const hosts = JSON.parse(await readFile(resolve(root, 'platform/units/host-ports.json'), 'utf8')).hosts;
const definitions = catalog.units.filter(unit => ['button', 'key', 'fan'].includes(unit.id))
  .map(unit => ({...unit, runtime: profiles[unit.id]}));
const inventory = {units: definitions, hosts};
const exitInputs = [];
const server = createServer(async (request, response) => {
  const pathname = new URL(request.url, 'http://localhost').pathname;
  if (pathname === '/audit-input' && request.method === 'POST') {
    let body = ''; for await (const chunk of request) body += chunk;
    const payload = JSON.parse(body); exitInputs.push(payload.request);
    response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(payload.receipt));
    return;
  }
  if (pathname === '/harness') {
    response.setHeader('Content-Type', 'text/html');
    response.end('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><link rel="stylesheet" href="/platform/web/m5-tokens.css"><link rel="stylesheet" href="/platform/web/unit-panel.css"></head><body><main id="panel"></main></body></html>');
    return;
  }
  const path = resolve(root, `.${decodeURIComponent(pathname)}`);
  if (!path.startsWith(root + '/')) { response.writeHead(403).end(); return; }
  try {
    response.setHeader('Content-Type', {'.js': 'text/javascript', '.css': 'text/css'}[extname(path)] || 'application/octet-stream');
    response.end(await readFile(path));
  } catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
const page = await browser.newPage({viewport: {width: 900, height: 900}});
const checks = [], errors = [];
page.on('pageerror', error => errors.push(error.message));
const run = async (name, action) => { await action(); checks.push(name); };
try {
  await page.goto(`http://127.0.0.1:${server.address().port}/harness`);
  await page.clock.install({time: new Date('2026-10-27T12:00:00Z')});
  await page.clock.pauseAt(new Date('2026-10-27T12:00:01Z'));
  await page.evaluate(inventory => { window.fixtureInventory = inventory; }, inventory);
  async function setup(options = {}) {
    await page.evaluate(async options => {
      window.f?.panel.dispose();
      const {createUnitPanel} = await import('/platform/web/unit-panel.js');
      const clone = value => structuredClone(value);
      const freeze = value => { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };
      const f = window.f = {legacy: [], reads: [], inputs: [], listeners: new Set(), gates: [], readGates: [], inputGates: [], commands: [], annotations: [], mounts: [], detaches: [], clientDisposed: 0,
        values: {A: !!options.initialPressed, B: false, C: false}, mode: 'running', run: options.start === undefined ? 'A' : options.start};
      f.flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
      f.session = {session_id: '1'.repeat(32), device_id: 'cores3', state: 'running', units: [
        {id: 'button1', unit_id: 'button', port_id: 'port-a', visual_port: 'grove'},
        {id: 'key1', unit_id: 'key', port_id: 'port-a', visual_port: 'fixture-key'},
        {id: 'fan1', unit_id: 'fan', port_id: 'port-a', visual_port: 'fixture-fan'},
      ], ...(options.binding === false ? {} : {management_binding: {preview_id: '2'.repeat(32), owner_epoch: '3'.repeat(32), expected_reference_sha256: '4'.repeat(64)}})};
      f.payload = (name, pressed = f.values[name] ?? true) => ({session_id: f.session.session_id, source: 'live', definitions: clone(window.fixtureInventory.units), units: f.session.units.map(attachment => ({...attachment,
        available: true, errors: {}, properties: attachment.unit_id === 'button' ? {pressed, 'input-level': Number(!pressed)}
          : attachment.unit_id === 'key' ? {pressed, 'led-rgb': name === 'A' ? 0xFF0000 : 0x0000FF} : {'duty-pct': name === 'A' ? 37 : 0}}))});
      f.context = () => !f.run ? null : freeze({key: 'owner:' + f.run + ':' + f.mode, previewId: '2'.repeat(32), ownerEpoch: '3'.repeat(32), sessionId: f.session.session_id,
        runId: ({A: 'a', B: 'b', C: 'c'})[f.run].repeat(32), executionId: ({A: 'a0', B: 'b0', C: 'c0'})[f.run].repeat(16), revisionId: ({A: 'a', B: 'b', C: 'c'})[f.run].repeat(64), name: f.run});
      f.defer = type => {
        let resolve, reject;
        const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
        const gate = {promise, resolve, reject, entered: false};
        f.gates.push(gate); (type === 'read' ? f.readGates : f.inputGates).push(gate);
        return f.gates.length - 1;
      };
      f.client = {
        snapshot() { const context = f.context(); return freeze({managed: true, frameContext: context, inputContext: f.mode === 'running' ? context : null}); },
        subscribe(listener) { f.listeners.add(listener); listener(this.snapshot()); return () => f.listeners.delete(listener); },
        captureInput() { return this.snapshot().inputContext; },
        matches(context, kind = 'input') { const current = this.snapshot()[kind === 'frame' ? 'frameContext' : 'inputContext']; return !!current && !!context && ['key', 'previewId', 'ownerEpoch', 'sessionId', 'runId', 'executionId', 'revisionId'].every(key => context[key] === current[key]); },
        async readSession(context, action) {
          f.reads.push({context: clone(context), action});
          const answer = f.payload(context.name), gate = f.readGates.shift();
          if (gate) { gate.entered = true; const override = await gate.promise; return override || answer; }
          return answer;
        },
        async input(context, kind, command, options) {
          f.inputs.push({context: clone(context), kind, command: clone(command), options: clone(options), frozen: Object.isFrozen(context)});
          if (f.dropRelease && command.values.pressed === false) { f.dropRelease = false; throw new Error('uncertain release effect'); }
          if (typeof command.values.pressed === 'boolean') f.values[context.name] = command.values.pressed;
          const receipt = {preview_id: context.previewId, run_id: context.runId, execution_id: context.executionId, revision_id: context.revisionId,
            captured_at: '2026-10-27T00:00:00Z', result: f.payload(context.name)};
          if (f.corruptReceipt) { if (f.corruptReceipt === 'session_id') receipt.result.session_id = '9'.repeat(32); else receipt[f.corruptReceipt] = '9'.repeat(64); f.corruptReceipt = null; }
          const gate = f.inputGates.shift();
          if (gate) { gate.entered = true; const override = await gate.promise; return override || receipt; }
          return receipt;
        },
        dispose() { f.clientDisposed++; },
      };
      f.setRun = async (name, mode = 'running') => { f.run = name; f.mode = mode; for (const listener of [...f.listeners]) listener(f.client.snapshot()); await f.flush(); };
      f.api = async (path, options = {}) => {
        f.legacy.push({path, method: options.method || 'GET'});
        if (options.method === 'POST') throw new Error('legacy mutation forbidden in this managed fixture');
        if (path.startsWith('/api/v1/units?')) return clone(window.fixtureInventory);
        return f.payload('UNOWNED', true);
      };
      const shell = {attachUnit: async (unit, {port}) => { f.mounts.push({unit, port}); return {}; }, detachUnit: port => f.detaches.push(port),
        applyVisualState: commands => f.commands.push(...clone(commands)), updateUnitAnnotation: (unit, options) => f.annotations.push({unit: clone(unit), source: options.source})};
      f.panel = await createUnitPanel(document.querySelector('#panel'), {session: f.session, shell, api: f.api, ...(options.withClient === false ? {} : {previewClient: f.client})});
      await f.flush();
      f.drain = async () => { await Promise.all([...f.panel.queues.values()]); await f.flush(); };
    }, options);
  }

  async function setupRealClient() {
    await setup({start: null});
    await page.evaluate(async () => {
      f.panel.dispose();
      const {createPreviewClient} = await import('/platform/web/preview-client.js');
      const {createUnitPanel} = await import('/platform/web/unit-panel.js');
      const clone = value => structuredClone(value), date = '2026-10-27T11:00:00Z';
      Object.assign(f.session, {created_at: date, pid: 1234, firmware_sha256: 'e'.repeat(64), program_transport: 'uart-repl'});
      f.realRun = name => {
        const generation = name === 'A' ? 1 : 2, run_id = (name === 'A' ? 'a' : 'b').repeat(32), revision_id = (name === 'A' ? 'a' : 'b').repeat(64);
        return {preview_id: '2'.repeat(32), run_id, execution_id: (name === 'A' ? 'a0' : 'b0').repeat(16), revision_id,
          source_kind: 'uiflow2-package', generation, state: 'running', request: {revision_id, expected_generation: generation - 1, expected_owner_epoch: '3'.repeat(32)},
          client_generation: null, timeout_seconds: 120, cancel_intent: false, interrupt_ack: 'unknown', application_ready: 'unknown',
          execution_mode: 'same-guest-uart-repl', cleanup_mode: 'interrupt-only', error: null, created_at: date, updated_at: date,
          last_observation: {execution_id: (name === 'A' ? 'a0' : 'b0').repeat(16), revision_id, firmware_sha256: f.session.firmware_sha256,
            pid: f.session.pid, execution_mode: 'same-guest-uart-repl', state: 'running', acknowledged: true}};
      };
      f.realName = 'A'; f.realCalls = []; f.realDrop = null; f.realRuns = new Map(['A', 'B'].map(name => [f.realRun(name).run_id, f.realRun(name)]));
      const active = f.realRun('A');
      f.realPreview = {preview_id: '2'.repeat(32), owner: 'local-control', owner_epoch: '3'.repeat(32), generation: 1, state: 'ready',
        session_id: f.session.session_id, session_identity: {session_id: f.session.session_id, firmware_sha256: f.session.firmware_sha256},
        request: {device_id: f.session.device_id}, session_request: {device_id: f.session.device_id, reference_sha256: '4'.repeat(64)},
        allocation_state: 'bound', allocation_key: `preview:${'2'.repeat(32)}:allocation:1`, created_at: date, updated_at: date,
        expires_at: '2026-10-28T12:00:00Z', active_run_id: active.run_id, desired_run_id: active.run_id, transition_run_id: null,
        error: null, capabilities: {execution_mode: 'same-guest-uart-repl', cleanup_mode: 'interrupt-only', latest_wins: true, run_cancellation: true,
          input: true, frame: 'on-demand', events: 'polling', application_ready: 'unknown', main_mpy: false, hotplug: false, gc_enabled: false,
          principal_mode: 'shared-control-bearer-local-control'}, limits: {max_previews: 128, max_runs_per_preview: 256, gc_enabled: false, retention_mode: 'retention-only'}};
      f.realApi = async (path, options = {}) => {
        const method = options.method || 'GET', body = options.body ? JSON.parse(options.body) : null;
        f.realCalls.push({path, method, body, pressed: f.values[f.realName]});
        if (path === `/api/v1/previews/${'2'.repeat(32)}`) return clone(f.realPreview);
        if (path.includes('/runs/')) return clone(f.realRuns.get(path.split('/').at(-1)));
        if (path.endsWith('/input')) {
          const command = body.unit_input, run = f.realRuns.get(body.expected_run_id), name = run.generation === 1 ? 'A' : 'B';
          const shouldDrop = f.realDrop === 'press' && command.values.pressed === true || f.realDrop === 'release' && command.values.pressed === false;
          if (!shouldDrop || f.realDrop === 'press' || f.realApplyDropRelease) f.values[name] = command.values.pressed;
          if (shouldDrop) { f.realDrop = null; throw new TypeError('fixture ACK lost'); }
          if (f.realInputGate) { const gate = f.realInputGate; f.realInputGate = null; await gate; }
          const receipt = {preview_id: run.preview_id, run_id: run.run_id, execution_id: run.execution_id, revision_id: run.revision_id,
            captured_at: date, result: f.payload(name)};
          if (f.realNetwork) return fetch('/audit-input', {method: 'POST', keepalive: options.keepalive === true,
            body: JSON.stringify({request: body, receipt})}).then(response => response.json());
          return receipt;
        }
        if (path.startsWith('/api/v1/units?')) return clone(window.fixtureInventory);
        if (path.endsWith('/units')) return f.payload(f.realName);
        throw new Error('unexpected real-client fixture request: ' + path);
      };
      f.client = createPreviewClient({session: f.session, api: f.realApi});
      await f.client.refresh();
      f.panel = await createUnitPanel(document.querySelector('#panel'), {session: f.session, shell: null, api: f.realApi, previewClient: f.client});
      await f.flush();
      if (!f.client.captureInput()) throw new Error('real client fixture did not synchronize');
      f.resync = async (name = 'A') => {
        f.realName = name;
        const run = f.realRun(name);
        Object.assign(f.realPreview, {generation: run.generation, active_run_id: run.run_id, desired_run_id: run.run_id});
        await f.client.refresh(); await f.flush();
        if (f.panel.refreshing) await f.flush();
        await f.panel.refresh(); await f.drain();
      };
    });
  }

  await run('no-run-frozen-definitions-without-unowned-live-values', async () => {
    await setup({start: null});
    assert.equal(await page.locator('[data-unit-id]').count(), 3);
    assert.equal(await page.locator('[data-unit-values] dd').count(), 0);
    assert.equal(await page.locator('[data-unit-id="button1"] button').isDisabled(), true);
    await page.evaluate(async () => { await f.panel.send('button1', {pressed: true}); f.panel.setPressed('button1', 'fixture', true); });
    assert.deepEqual(await page.evaluate(() => ({inputs: f.inputs.length, reads: f.reads.length, mutations: f.legacy.filter(call => call.method === 'POST').length})), {inputs: 0, reads: 0, mutations: 0});
    await page.screenshot({path: `${output}/managed-no-run.png`, fullPage: true});
  });
  await run('non-null-malformed-binding-without-client-never-falls-back', async () => {
    await setup({withClient: false});
    await page.evaluate(async () => { f.panel.updateSession({...f.session, management_binding: {}}); await f.flush(); await f.panel.send('button1', {pressed: true}); });
    assert.equal(await page.locator('[data-unit-values] dd').count(), 0);
    assert.equal(await page.evaluate(() => f.legacy.filter(call => call.method === 'POST').length), 0);
  });
  await run('same-id-late-management-binding-fails-closed-without-client', async () => {
    await setup({binding: false, withClient: false});
    assert.ok(await page.locator('[data-unit-values] dd').count());
    await page.evaluate(async () => { f.panel.updateSession({...f.session, management_binding: {preview_id: '2'.repeat(32)}}); await f.flush(); await f.panel.send('button1', {pressed: true}); });
    assert.equal(await page.locator('[data-unit-values] dd').count(), 0);
    assert.equal(await page.locator('[data-unit-id="button1"] button').isDisabled(), true);
    assert.equal(await page.evaluate(() => f.legacy.filter(call => call.method === 'POST').length), 0);
  });
  await run('owned-read-bracket-and-frozen-context-input-receipt-result', async () => {
    await setup();
    await page.evaluate(async () => { await f.panel.send('button1', {pressed: true}); await f.drain(); });
    assert.equal(await page.locator('[data-unit-id="button1"] [data-unit-values] dd').first().textContent(), 'true');
    assert.deepEqual(await page.evaluate(() => f.inputs.map(call => ({kind: call.kind, key: call.context.key, frozen: call.frozen}))), [{kind: 'unit_input', key: 'owner:A:running', frozen: true}]);
    assert.equal(await page.evaluate(() => f.reads.every(call => call.action === 'units')), true);
    assert.equal(await page.evaluate(() => f.legacy.filter(call => call.method === 'POST').length), 0);
  });
  await run('wrong-receipt-identities-never-apply-or-fallback', async () => {
    for (const field of ['preview_id', 'run_id', 'execution_id', 'revision_id', 'session_id']) {
      await setup();
      await page.evaluate(async field => { f.corruptReceipt = field; await f.panel.send('button1', {pressed: true}); }, field);
      assert.equal(await page.evaluate(() => f.panel.states.get('button1').properties.pressed), false, field);
      assert.match(await page.locator('[data-unit-id="button1"] [data-unit-note]').textContent(), /收据.*不匹配/);
      assert.equal(await page.evaluate(() => f.legacy.filter(call => call.method === 'POST').length), 0);
    }
  });
  await run('old-post-and-ordinary-queued-input-cannot-cross-run', async () => {
    await setup();
    await page.evaluate(async () => {
      f.gate = f.defer('input'); f.oldPost = f.panel.send('button1', {pressed: true}); f.queued = f.panel.send('button1', {pressed: false}); await f.flush();
      if (!f.gates[f.gate].entered) throw new Error('input gate not entered');
      await f.setRun('B'); f.gates[f.gate].resolve(); await Promise.all([f.oldPost, f.queued]); await f.flush();
    });
    assert.deepEqual(await page.evaluate(() => f.inputs.map(call => call.context.name)), ['A']);
    assert.equal(await page.evaluate(() => f.panel.states.get('button1').properties.pressed), false);
  });
  await run('late-get-success-and-error-cannot-change-new-run', async () => {
    for (const failure of [false, true]) {
      await setup({initialPressed: true});
      await page.evaluate(async failure => {
        f.gate = f.defer('read'); f.oldRead = f.panel.refresh(); await f.flush();
        if (!f.gates[f.gate].entered) throw new Error('read gate not entered');
        await f.setRun('B'); f.newSnapshot = structuredClone(f.panel.states.get('button1'));
        if (failure) f.gates[f.gate].reject(new Error('old read failure')); else f.gates[f.gate].resolve();
        await f.oldRead; await f.flush();
      }, failure);
      assert.deepEqual(await page.evaluate(() => f.panel.states.get('button1')), await page.evaluate(() => f.newSnapshot));
    }
  });
  await run('context-withdraw-and-return-same-key-still-fences-old-read', async () => {
    await setup({initialPressed: true});
    await page.evaluate(async () => {
      f.gate = f.defer('read'); f.oldRead = f.panel.refresh(); await f.flush();
      await f.setRun(null); f.values.A = false; await f.setRun('A');
      f.gates[f.gate].resolve(); await f.oldRead; await f.flush();
    });
    assert.equal(await page.evaluate(() => f.panel.states.get('button1').properties.pressed), false);
  });
  await run('run-switch-withdraws-held-release-values-and-known-visuals', async () => {
    await setup();
    await page.evaluate(async () => { f.panel.setPressed('button1', 'fixture', true); await f.drain(); f.mountedBefore = f.mounts.length; f.commandOffset = f.commands.length; await f.setRun(null); f.panel.setPressed('button1', 'fixture', false); await f.drain(); });
    assert.equal(await page.locator('[data-unit-values] dd').count(), 0);
    assert.deepEqual(await page.evaluate(() => ({held: f.panel.pressSources.size, releases: f.panel.releaseIntents.size, pending: f.panel.pending.size, mounts: f.mounts.length, before: f.mountedBefore})), {held: 0, releases: 0, pending: 0, mounts: 3, before: 3});
    assert.equal(await page.evaluate(() => f.inputs.length), 1, 'old release must not move to another Run');
    const commands = await page.evaluate(() => f.commands.slice(f.commandOffset));
    assert.ok(commands.some(command => command.type === 'led' && command.known === false));
    assert.ok(commands.some(command => command.type === 'drive-activity' && command.active === false));
    assert.ok(commands.some(command => command.type === 'button-state' && command.pressed === false));
    assert.equal(commands.some(command => ['joint', 'position'].includes(command.type)), false, 'no guessed reset angle/detent');
    assert.equal(await page.evaluate(() => f.annotations.at(-1).unit.available), false);
  });
  await run('same-run-multiple-sources-and-blur-release-use-original-owner', async () => {
    await setup();
    await page.evaluate(async () => {
      f.panel.setPressed('button1', 'fixture-one', true); f.panel.setPressed('button1', 'fixture-two', true); await f.drain();
      f.panel.setPressed('button1', 'fixture-one', false); await f.drain(); window.dispatchEvent(new Event('blur')); await f.drain();
    });
    assert.deepEqual(await page.evaluate(() => f.inputs.map(call => ({owner: call.context.name, pressed: call.command.values.pressed}))), [{owner: 'A', pressed: true}, {owner: 'A', pressed: false}]);
    assert.equal(await page.evaluate(() => f.panel.releaseIntents.size), 0);
    assert.equal(await page.evaluate(() => f.inputs.at(-1).options.keepalive), true);
  });
  await run('same-run-uncertain-release-uses-fresh-bracket-once', async () => {
    await setup();
    await page.evaluate(async () => {
      f.panel.setPressed('button1', 'fixture', true); await f.drain(); f.dropRelease = true; f.panel.setPressed('button1', 'fixture', false); await f.drain();
      if (![...f.panel.releaseIntents.values()].some(intent => intent.uncertain)) throw new Error('uncertain release intent was lost');
      await f.panel.refresh(); await f.drain();
    });
    assert.deepEqual(await page.evaluate(() => f.inputs.map(call => call.command.values.pressed)), [true, false, false]);
    assert.equal(await page.evaluate(() => f.panel.releaseIntents.size), 0);
  });
  await run('queued-release-recovery-cannot-dispatch-into-new-run', async () => {
    await setup();
    await page.evaluate(async () => {
      f.panel.setPressed('button1', 'fixture', true); await f.drain(); f.dropRelease = true; f.panel.setPressed('button1', 'fixture', false); await f.drain();
      let unblock; f.blocker = new Promise(resolve => { unblock = resolve; }); f.panel.queues.set('button1', f.blocker);
      await f.panel.refresh(); f.recovery = f.panel.queues.get('button1'); await f.setRun('B'); unblock(); await f.recovery; await f.flush();
    });
    assert.deepEqual(await page.evaluate(() => f.inputs.map(call => call.context.name)), ['A', 'A']);
    assert.equal(await page.evaluate(() => f.panel.releaseIntents.size), 0);
  });
  await run('dispose-keeps-only-same-run-necessary-release-and-unsubscribes', async () => {
    await setup();
    await page.evaluate(async () => {
      f.gate = f.defer('input'); f.panel.setPressed('button1', 'fixture', true); f.held = f.panel.queues.get('button1'); f.ordinary = f.panel.send('button1', {pressed: true}); await f.flush();
      f.panel.dispose(); f.release = f.panel.queues.get('button1'); f.gates[f.gate].resolve(); await Promise.all([f.held, f.ordinary, f.release]); await f.flush();
    });
    assert.deepEqual(await page.evaluate(() => f.inputs.map(call => ({owner: call.context.name, pressed: call.command.values.pressed}))), [{owner: 'A', pressed: true}, {owner: 'A', pressed: false}]);
    assert.deepEqual(await page.evaluate(() => ({listeners: f.listeners.size, disposed: f.clientDisposed})), {listeners: 0, disposed: 0});
    assert.equal(await page.locator('#panel').textContent(), '');
  });
  await run('disposed-release-is-dropped-if-shared-client-switches-owner', async () => {
    await setup();
    await page.evaluate(async () => {
      f.gate = f.defer('input'); f.panel.setPressed('button1', 'fixture', true); f.held = f.panel.queues.get('button1'); await f.flush();
      f.panel.dispose(); f.release = f.panel.queues.get('button1'); await f.setRun('B'); f.gates[f.gate].resolve(); await Promise.all([f.held, f.release]);
    });
    assert.deepEqual(await page.evaluate(() => f.inputs.map(call => call.context.name)), ['A']);
  });
  await run('bad-owned-state-identity-withdraws-without-promoting-unowned-values', async () => {
    await setup();
    await page.evaluate(async () => {
      f.gate = f.defer('read'); f.read = f.panel.refresh(); await f.flush(); f.gates[f.gate].resolve({...f.payload('A', true), session_id: '9'.repeat(32)}); await f.read;
      f.unownedApplied = f.panel.apply(f.payload('A', true));
    });
    assert.equal(await page.evaluate(() => f.unownedApplied), false);
    assert.equal(await page.locator('[data-unit-values] dd').count(), 0);
    assert.equal(await page.locator('[data-unit-id="button1"] button').isDisabled(), true);
  });
  await run('partial-or-wrong-unit-identity-never-remains-current-observation', async () => {
    for (const mode of ['missing', 'duplicate', 'wrong-unit', 'persisted']) {
      await setup();
      await page.evaluate(async mode => {
        f.gate = f.defer('read'); f.read = f.panel.refresh(); await f.flush(); const value = f.payload('A', true);
        if (mode === 'missing') value.units.pop();
        if (mode === 'duplicate') value.units[1] = value.units[0];
        if (mode === 'wrong-unit') value.units[0].unit_id = 'relay';
        if (mode === 'persisted') value.source = 'persisted';
        f.gates[f.gate].resolve(value); await f.read;
      }, mode);
      assert.equal(await page.locator('[data-unit-values] dd').count(), 0, mode);
      assert.equal(await page.locator('[data-unit-id="button1"] button').isDisabled(), true, mode);
    }
  });
  await run('real-client-lost-press-ack-recovers-release-only-after-fresh-same-run-read', async () => {
    await setupRealClient();
    await page.evaluate(async () => {
      f.realDrop = 'press'; f.panel.setPressed('button1', 'fixture', true); await f.drain();
      if (f.client.captureInput() !== null) throw new Error('lost ACK did not withdraw real client context');
      f.panel.setPressed('button1', 'fixture', false);
      f.recoveryOffset = f.realCalls.length;
      await f.resync();
    });
    const calls = await page.evaluate(() => f.realCalls);
    const inputs = calls.filter(call => call.path.endsWith('/input'));
    assert.deepEqual(inputs.map(call => call.body.unit_input.values.pressed), [true, false]);
    assert.equal(inputs.every(call => call.body.expected_run_id === 'a'.repeat(32)), true);
    const recovery = calls.slice(await page.evaluate(() => f.recoveryOffset));
    const inputIndex = recovery.findIndex(call => call.path.endsWith('/input'));
    assert.ok(inputIndex >= 3, 'same-Run Preview + Run + bracketed units GET must precede release');
    assert.ok(recovery.slice(0, inputIndex).some(call => call.path.endsWith('/units') && call.pressed === true));
    assert.equal(await page.evaluate(() => f.values.A), false);
    await page.evaluate(() => f.client.dispose());
  });
  await run('real-client-lost-release-ack-recovers-once-and-new-run-never-receives-old-release', async () => {
    for (const name of ['A', 'B']) {
      await setupRealClient();
      await page.evaluate(async name => {
        f.panel.setPressed('button1', 'fixture', true); await f.drain();
        f.realDrop = 'release'; f.panel.setPressed('button1', 'fixture', false); await f.drain();
        await f.resync(name); await f.resync(name);
      }, name);
      const inputs = await page.evaluate(() => f.realCalls.filter(call => call.path.endsWith('/input')));
      assert.deepEqual(inputs.map(call => call.body.unit_input.values.pressed), name === 'A' ? [true, false, false] : [true, false]);
      assert.equal(inputs.every(call => call.body.expected_run_id === 'a'.repeat(32)), true);
      assert.equal(await page.evaluate(() => f.panel.parkedReleases.size), 0);
      await page.evaluate(() => f.client.dispose());
    }
  });
  await run('real-client-already-applied-release-is-confirmed-without-replay', async () => {
    await setupRealClient();
    await page.evaluate(async () => {
      f.panel.setPressed('button1', 'fixture', true); await f.drain();
      f.realDrop = 'release'; f.realApplyDropRelease = true; f.panel.setPressed('button1', 'fixture', false); await f.drain();
      await f.resync(); await f.resync();
    });
    assert.deepEqual(await page.evaluate(() => f.realCalls.filter(call => call.path.endsWith('/input')).map(call => call.body.unit_input.values.pressed)), [true, false]);
    assert.deepEqual(await page.evaluate(() => [f.panel.parkedReleases.size, f.panel.releaseIntents.size]), [0, 0]);
    await page.evaluate(() => f.client.dispose());
  });
  await run('real-client-uncertain-compensation-is-never-replayed-in-a-loop', async () => {
    await setupRealClient();
    await page.evaluate(async () => {
      f.realDrop = 'press'; f.panel.setPressed('button1', 'fixture', true); await f.drain();
      f.realDrop = 'release'; await f.resync(); await f.resync(); await f.resync();
    });
    assert.deepEqual(await page.evaluate(() => f.realCalls.filter(call => call.path.endsWith('/input')).map(call => call.body.unit_input.values.pressed)), [true, false]);
    assert.equal(await page.evaluate(() => [...f.panel.releaseIntents.values()].every(intent => intent.retried)), true);
    assert.match(await page.locator('[data-unit-id="button1"] [data-unit-note]').textContent(), /松开仍未确认/);
    await page.evaluate(() => f.client.dispose());
  });
  await run('real-client-dispose-dispatches-acknowledged-release-synchronously-and-drains-idempotently', async () => {
    await setupRealClient();
    await page.evaluate(async () => {
      f.panel.setPressed('button1', 'fixture', true); await f.drain();
      const pending = f.panel.dispose();
      f.sameDisposePromise = pending === f.panel.dispose();
      f.synchronousInputs = f.realCalls.filter(call => call.path.endsWith('/input')).map(call => call.body.unit_input.values.pressed);
      await pending; f.client.dispose();
    });
    assert.deepEqual(await page.evaluate(() => f.synchronousInputs), [true, false]);
    assert.equal(await page.evaluate(() => f.sameDisposePromise), true);
    assert.equal(await page.evaluate(() => f.values.A), false);
  });
  await run('real-client-dispose-drains-pending-down-before-release-and-drops-ordinary-queue', async () => {
    await setupRealClient();
    await page.evaluate(async () => {
      f.realInputGate = new Promise(resolve => { f.releaseRealInputGate = resolve; });
      f.panel.setPressed('button1', 'fixture', true); await f.flush();
      f.ordinary = f.panel.send('button1', {pressed: true});
      const pending = f.panel.dispose();
      f.synchronousInputs = f.realCalls.filter(call => call.path.endsWith('/input')).map(call => call.body.unit_input.values.pressed);
      f.releaseRealInputGate(); await pending; f.client.dispose();
    });
    assert.deepEqual(await page.evaluate(() => f.synchronousInputs), [true]);
    assert.deepEqual(await page.evaluate(() => f.realCalls.filter(call => call.path.endsWith('/input')).map(call => call.body.unit_input.values.pressed)), [true, false]);
    assert.equal(await page.evaluate(() => f.values.A), false);
  });
  await run('real-pagehide-dispatches-same-run-keepalive-release-to-local-http-server', async () => {
    await setupRealClient(); exitInputs.length = 0;
    await page.evaluate(async () => {
      f.realNetwork = true; f.panel.setPressed('button1', 'fixture', true); await f.drain();
      window.addEventListener('pagehide', () => { f.panel.dispose().finally(() => f.client.dispose()); }, {once: true});
    });
    assert.deepEqual(exitInputs.map(request => request.unit_input.values.pressed), [true]);
    await page.goto(`http://127.0.0.1:${server.address().port}/harness?after-pagehide`);
    for (let i = 0; i < 100 && exitInputs.length < 2; i++) await new Promise(done => setTimeout(done, 10));
    assert.deepEqual(exitInputs.map(request => request.unit_input.values.pressed), [true, false]);
    assert.equal(exitInputs.every(request => request.expected_run_id === 'a'.repeat(32)), true);
  });
  assert.deepEqual(errors, []);
  const source_sha256 = Object.fromEntries(await Promise.all(['platform/web/unit-panel.js', 'platform/web/preview-client.js', 'platform/tests/test_preview_unit_panel.mjs'].map(async path => [path, createHash('sha256').update(await readFile(resolve(root, path))).digest('hex')])));
  await writeFile(`${output}/report.json`, JSON.stringify({category: 'preview-unit-browser-contract', status: 'PASS', firmware_execution: 'NOT RUN', browser_version: browser.version(), checks, source_sha256, errors}, null, 2) + '\n');
  console.log(`PASS ${checks.length} Preview Unit browser contract checks`);
} finally {
  await browser.close();
  await new Promise(done => server.close(done));
}
