// Host-only asynchronous API fixtures. No firmware, browser, guest or service.
import assert from 'node:assert/strict';
import {setImmediate as tick} from 'node:timers/promises';
import {createPreviewClient} from '../web/preview-client.js';

const id = number => number.toString(16).padStart(32, '0');
const revision = character => character.repeat(64);
const copy = value => structuredClone(value);
const canonical = value => JSON.stringify(value, (_key, child) => child && typeof child === 'object' && !Array.isArray(child)
  ? Object.fromEntries(Object.keys(child).sort().map(key => [key, child[key]])) : child);
const cap = {execution_mode: 'same-guest-uart-repl', cleanup_mode: 'interrupt-only', latest_wins: true, run_cancellation: true,
  input: true, frame: 'on-demand', events: 'polling', application_ready: 'unknown', main_mpy: false,
  hotplug: false, gc_enabled: false, principal_mode: 'shared-control-bearer-local-control'};
const clients = new Set();
const results = [];
let clock = Date.now();
const stamp = () => new Date(clock += 10).toISOString();
const future = () => new Date(Date.now() + 600_000).toISOString();
function verifiedLoader(session) {
  const nonce = id(99), canary = '0713a25c1bdfb35a2ba0ebf431ec1ccccaa32846eb0dd74f3ebb230ffeac9420';
  return {schema_version: 1, status: 'verified', mpy_entrypoint: true, loader: 'micropython-override-main-v1', mpy: 11014, small_int_bits: 31,
    identity: {session_id: session.session_id, device_id: session.device_id, firmware_sha256: session.firmware_sha256,
      pid: session.pid, runtime: session.runtime, worker_generation: session.worker.generation, process_start_token: 'host-only-start-token'},
    probe: {kind: 'uiflow-main-mpy-canary-v1', nonce, status: 'PASS', owner_restored: true, cleanup_complete: true, body_entered: true,
      canary_sha256: canary, file_sha256: canary, file_bytes: 375, owner_before_id: 123, owner_after_id: 123,
      source_sha256: 'e21b73a791266cea38d5c2050e0d4ae48180f4e3908bf748db4b10995908ed78',
      compiler_sha256: 'c8646ebb97047c1c56a9d164474729a1bf13508e49d4cd3b1e5c6f00c509911b',
      actual_identity: {if_main: true, name: '__main__', file: `/flash/.m5-loader-probe-${nonce}/main.mpy`, real_main_name: 'main',
        nonce, main_id: 456, sys_main_id: 456, import_main_id: 456}}};
}
function gate() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
async function until(test) {
  for (let i = 0; i < 200; i++) { if (test()) return; await tick(); }
  assert.fail('fixture did not reach asynchronous boundary');
}
async function test(name, action) {
  try { await action(); results.push(name); }
  finally { for (const client of clients) client.dispose(); clients.clear(); }
}
function service() {
  const session = {session_id: id(1), created_at: stamp(), device_id: 'cores3', state: 'running', pid: 1234,
    runtime: 'qemu', worker: {generation: 44},
    firmware_sha256: revision('e'), program_transport: 'uart-repl',
    management_binding: {preview_id: id(2), owner_epoch: id(3), expected_reference_sha256: revision('f')}};
  const runs = new Map(), replays = new Map(), calls = [];
  function makeRun(generation, source = revision('a'), state = 'running', request = null) {
    const time = stamp();
    const run = {preview_id: id(2), run_id: id(10 + generation), execution_id: id(20 + generation), revision_id: source,
      source_kind: 'uiflow2-package', generation, state, request: request || {revision_id: source, expected_generation: generation - 1, expected_owner_epoch: id(3)},
      client_generation: request?.client_generation ?? null, timeout_seconds: request?.timeout_seconds ?? 120,
      cancel_intent: false, interrupt_ack: 'unknown', application_ready: 'unknown', execution_mode: 'same-guest-uart-repl',
      cleanup_mode: 'interrupt-only', error: null, created_at: time, updated_at: time};
    if (['running', 'completed'].includes(state)) run.last_observation = {execution_id: run.execution_id, revision_id: source,
      firmware_sha256: session.firmware_sha256, pid: session.pid, execution_mode: 'same-guest-uart-repl', state, acknowledged: true};
    return run;
  }
  const first = makeRun(1); runs.set(first.run_id, first);
  const preview = {preview_id: id(2), owner: 'local-control', owner_epoch: id(3), generation: 1, state: 'ready',
    session_id: id(1), session_identity: {session_id: id(1), firmware_sha256: session.firmware_sha256},
    request: {device_id: 'cores3'}, session_request: {device_id: 'cores3', reference_sha256: revision('f')},
    allocation_state: 'bound', allocation_key: `preview:${id(2)}:allocation:1`, created_at: stamp(), updated_at: stamp(),
    expires_at: future(), active_run_id: first.run_id, desired_run_id: first.run_id, transition_run_id: null,
    error: null, capabilities: copy(cap), limits: {max_previews: 128, max_runs_per_preview: 256, gc_enabled: false, retention_mode: 'retention-only'}};
  function activate(source = revision('b')) {
    for (const run of runs.values()) if (!['completed', 'cancelled'].includes(run.state)) {
      run.state = 'cancelled'; run.cancel_intent = true; run.interrupt_ack = 'confirmed'; run.updated_at = stamp();
    }
    const run = makeRun(++preview.generation, source);
    runs.set(run.run_id, run); preview.active_run_id = preview.desired_run_id = run.run_id;
    preview.transition_run_id = null; preview.updated_at = stamp();
    return run;
  }
  const server = {session, preview, runs, calls, makeRun, activate, hook: null};
  server.api = async (path, options = {}) => {
    const method = options.method || 'GET';
    const body = options.body ? JSON.parse(options.body) : null;
    const request = {path, method, body, headers: options.headers, keepalive: options.keepalive};
    calls.push(request);
    const reply = () => {
      if (path === `/api/v1/previews/${id(2)}` && method === 'GET') return copy(preview);
      const runPath = path.match(/\/runs\/([0-9a-f]{32})$/);
      if (runPath && method === 'GET') return copy(runs.get(runPath[1]));
      if (path.endsWith('/runs') && method === 'POST') {
        const key = options.headers['Idempotency-Key'];
        if (replays.has(key)) {
          const cached = replays.get(key);
          if (canonical(cached.body) !== canonical(body)) throw Object.assign(new Error('idem conflict'), {status: 409, effectPossible: false});
          return copy(cached.receipt);
        }
        if (body.expected_generation !== preview.generation) throw Object.assign(new Error('generation conflict'), {status: 409, code: 'preview_generation_conflict', effectPossible: false});
        const running = activate(body.revision_id);
        running.request = copy(body); running.client_generation = body.client_generation ?? null;
        const receipt = {...copy(running), state: 'queued'}; delete receipt.last_observation;
        // Real store canonicalizes request field order.
        receipt.request = JSON.parse(canonical(body));
        replays.set(key, {body: copy(body), receipt});
        return copy(receipt);
      }
      if (path.endsWith('/cancel')) {
        const run = runs.get(path.split('/').at(-2));
        run.state = 'cancelled'; run.cancel_intent = true; run.interrupt_ack = 'confirmed'; run.updated_at = stamp();
        if (preview.active_run_id === run.run_id) preview.active_run_id = null;
        if (preview.transition_run_id === run.run_id) preview.transition_run_id = null;
        preview.updated_at = stamp();
        return copy(run);
      }
      if (path.endsWith('/renew')) { preview.expires_at = future(); preview.updated_at = stamp(); return copy(preview); }
      if (path.endsWith('/close')) { preview.state = 'closed'; preview.active_run_id = preview.desired_run_id = preview.transition_run_id = null; preview.updated_at = stamp(); return copy(preview); }
      if (path.endsWith('/input')) {
        const run = runs.get(body.expected_run_id);
        return {preview_id: preview.preview_id, run_id: run.run_id, execution_id: run.execution_id, revision_id: run.revision_id,
          captured_at: stamp(), result: {session_id: session.session_id, applied: true}};
      }
      if (path.endsWith('/units') || path.endsWith('/device-state')) return {session_id: session.session_id, source: 'live', units: []};
      throw new Error('unexpected fixture request: ' + path);
    };
    return server.hook ? server.hook(request, reply) : reply();
  };
  return server;
}
async function ready(server = service()) {
  const client = createPreviewClient({session: server.session, api: server.api}); clients.add(client);
  await client.refresh();
  assert.equal(client.snapshot().synchronized, true);
  return {server, client};
}
const posts = server => server.calls.filter(x => x.method === 'POST' && x.path.endsWith('/runs'));

await test('invalid non-null bindings remain managed, inert and never fall back', async () => {
  for (const binding of [null, {}, [], 'legacy', {preview_id: id(2), owner_epoch: id(3)},
    {preview_id: [id(2)], owner_epoch: id(3), expected_reference_sha256: revision('f')}]) {
    const server = service(); server.session.management_binding = binding;
    const client = createPreviewClient({session: server.session, api: server.api}); clients.add(client);
    assert.equal(client.snapshot().managed, true); assert.equal(client.snapshot().canSubmit, false);
    assert.equal(client.captureInput(), null); await assert.rejects(client.refresh());
    await assert.rejects(client.runRevision(revision('b'))); assert.equal(server.calls.length, 0);
  }
});

await test('one immediate subscription, detached deep-freeze, unique Run GET and completed frame only', async () => {
  const {client, server} = await ready(); let count = 0, first;
  const unsubscribe = client.subscribe(value => { first ||= value; count++; });
  assert.equal(count, 1); assert.ok(Object.isFrozen(first.preview.capabilities));
  assert.throws(() => { first.preview.generation = 999; }, TypeError);
  assert.notEqual(first, client.snapshot());
  assert.equal(server.calls.filter(x => x.path.includes('/runs/')).length, 1);
  const run = server.runs.get(server.preview.active_run_id); run.state = 'completed'; run.last_observation.state = 'completed'; run.updated_at = stamp();
  await client.refresh(); assert.ok(client.snapshot().frameContext); assert.equal(client.captureInput(), null);
  unsubscribe(); const previous = count; await client.refresh(); assert.equal(count, previous);
});

await test('all authoritative identity, CAS, capability and enum failures close contexts', async () => {
  const mutations = [
    s => { s.preview.owner_epoch = id(90); }, s => { s.preview.session_identity.firmware_sha256 = revision('d'); },
    s => { s.preview.generation = 1.5; }, s => { s.preview.state = 'new-state'; }, s => { s.preview.allocation_state = 'other'; },
    s => { s.preview.expires_at = 'tomorrow'; }, s => { s.preview.session_id = id(88); },
    s => { s.preview.capabilities = {...s.preview.capabilities, input: false}; },
    s => { s.preview.limits.retention_mode = 'other'; }, s => { s.preview.session_request.reference_sha256 = revision('c'); },
    s => { s.runs.get(s.preview.active_run_id).request.expected_generation = 7; },
    s => { s.runs.get(s.preview.active_run_id).execution_id = [id(21)]; },
    s => { s.runs.get(s.preview.active_run_id).last_observation.pid = 999; },
    s => { s.runs.get(s.preview.active_run_id).application_ready = 'ready'; },
    s => { s.runs.get(s.preview.active_run_id).state = 'new-state'; },
    s => { s.runs.get(s.preview.active_run_id).cancel_intent = 0; },
    s => { delete s.runs.get(s.preview.active_run_id).last_observation; },
  ];
  for (const mutate of mutations) {
    const {client, server} = await ready(); mutate(server);
    await assert.rejects(client.refresh()); assert.equal(client.captureInput(), null); assert.equal(client.snapshot().synchronized, false);
    client.dispose(); clients.delete(client);
  }
});

await test('rapid admissions serialize CAS, close contexts synchronously and retain original receipts', async () => {
  const {client, server} = await ready(); const blocked = gate(); let receipt;
  server.hook = (request, reply) => {
    if (request.method === 'POST' && request.path.endsWith('/runs') && !receipt) { receipt = reply(); return blocked.promise; }
    return reply();
  };
  const a = client.runRevision(revision('b'), {clientGeneration: 'first'});
  assert.equal(client.snapshot().pending, true); assert.equal(client.captureInput(), null); assert.equal(client.snapshot().canSubmit, true);
  await until(() => receipt);
  const b = client.runRevision(revision('c'), {clientGeneration: 'second'});
  await tick(); assert.equal(posts(server).length, 1);
  blocked.resolve(receipt); const receipts = await Promise.all([a, b]); await client.refresh();
  assert.deepEqual(receipts.map(x => x.state), ['queued', 'queued']);
  assert.deepEqual(posts(server).map(x => x.body.expected_generation), [1, 2]);
  assert.notEqual(posts(server)[0].headers['Idempotency-Key'], posts(server)[1].headers['Idempotency-Key']);
  assert.equal(client.snapshot().activeRun.revision_id, revision('c'));
});

await test('cancel bypasses blocked admission and late queued receipt cannot resurrect cancelled Run', async () => {
  const {client, server} = await ready(); const blocked = gate(); let receipt;
  server.hook = (request, reply) => {
    if (request.method === 'POST' && request.path.endsWith('/runs') && !receipt) { receipt = reply(); return blocked.promise; }
    return reply();
  };
  const admission = client.runRevision(revision('b')); await until(() => receipt);
  await client.refresh(); const target = client.snapshot().cancelRunId;
  const cancelled = await client.cancel(); assert.equal(cancelled.run_id, target); assert.equal(cancelled.state, 'cancelled');
  assert.equal(server.calls.filter(x => x.path.endsWith('/cancel')).length, 1);
  blocked.resolve(receipt); assert.equal((await admission).state, 'queued'); await client.refresh();
  assert.equal(client.snapshot().desiredRun.state, 'cancelled'); assert.equal(client.snapshot().activeRun, null); assert.equal(client.captureInput(), null);
});

await test('late old Preview GET is rejected after a newer admission, even when transport ignores AbortSignal', async () => {
  const {client, server} = await ready(); const blocked = gate(); let old;
  server.hook = (request, reply) => {
    if (request.method === 'GET' && request.path === `/api/v1/previews/${id(2)}` && !old) { old = reply(); return blocked.promise; }
    return reply();
  };
  const staleRead = client.refresh(); const rejected = assert.rejects(staleRead, {code: 'preview_context_changed'});
  await until(() => old); await client.runRevision(revision('b')); await client.refresh();
  blocked.resolve(old); await rejected;
  assert.equal(client.snapshot().preview.generation, 2); assert.equal(client.snapshot().activeRun.revision_id, revision('b'));
});

await test('generation rewind and terminal/cancelled Run revival are never published', async () => {
  const {client, server} = await ready(); await client.runRevision(revision('b')); await client.refresh();
  server.preview.generation = 1; await assert.rejects(client.refresh()); assert.equal(client.captureInput(), null);
  server.preview.generation = 2; await client.refresh(); await client.cancel(); await client.refresh();
  const run = server.runs.get(server.preview.desired_run_id); run.state = 'running'; run.cancel_intent = false; run.updated_at = stamp(); server.preview.active_run_id = run.run_id;
  await assert.rejects(client.refresh()); assert.equal(client.captureInput(), null);
});

await test('ambiguous admission has no automatic retry; explicit same-key replay preserves original CAS', async () => {
  const {client, server} = await ready(); let failed = false;
  const failure = Object.assign(new Error('response stream closed'), {effectPossible: true});
  server.hook = (request, reply) => {
    if (request.method === 'POST' && request.path.endsWith('/runs') && !failed) { failed = true; reply(); throw failure; }
    return reply();
  };
  await assert.rejects(client.runRevision(revision('b'), {idempotencyKey: 'stable-key'}), error => error === failure);
  await client.refresh(); assert.equal(posts(server).length, 1);
  const result = await client.runRevision(revision('b'), {idempotencyKey: 'stable-key'});
  assert.equal(result.generation, 2); assert.equal(result.state, 'queued'); await client.refresh();
  assert.equal(server.preview.generation, 2); assert.deepEqual(posts(server).map(x => x.body.expected_generation), [1, 1]);
});

await test('conflict is not rebased/retried and beforeAdmission guards final fresh package baseline', async () => {
  const {client, server} = await ready(); let race = true;
  server.hook = (request, reply) => { if (race && request.method === 'POST' && request.path.endsWith('/runs')) { race = false; server.activate(revision('c')); } return reply(); };
  await assert.rejects(client.runRevision(revision('b')), {code: 'preview_generation_conflict'}); await client.refresh(); assert.equal(posts(server).length, 1);
  let seen;
  await assert.rejects(client.runRevision(revision('d'), {beforeAdmission: snapshot => { seen = snapshot.activeRun.revision_id; throw Object.assign(new Error('workspace changed'), {code: 'preview_package_changed'}); }}), {code: 'preview_package_changed'});
  assert.equal(seen, revision('c')); assert.equal(posts(server).length, 1);
  await assert.rejects(client.runRevision(revision('d'), {beforeAdmission: () => Promise.resolve()})); assert.equal(posts(server).length, 1);
});

await test('input does not invalidate its own context, returns frozen receipt and forwards captured release only', async () => {
  const {client, server} = await ready(); const context = client.captureInput(), blocked = gate(); let receipt;
  assert.equal(client.matches({...context, executionId: id(99)}), false);
  server.hook = (request, reply) => { if (request.path.endsWith('/input')) { receipt = reply(); return blocked.promise; } return reply(); };
  const operation = client.input(context, 'unit_input', {id: 'external1', values: {motion: true}}, {keepalive: true});
  await until(() => receipt); assert.equal(client.snapshot().pending, false); assert.equal(client.matches(context), true);
  blocked.resolve(receipt); const response = await operation; assert.ok(Object.isFrozen(response.result));
  const request = server.calls.find(x => x.path.endsWith('/input'));
  assert.equal(request.body.expected_run_id, context.runId); assert.equal(request.keepalive, true);
  assert.equal(response.result.session_id, server.session.session_id);
});

await test('unknown input effect and wrong receipt close contexts without replay', async () => {
  for (const wrongIdentity of [false, true]) {
    const {client, server} = await ready(); const captured = client.captureInput(); let attempts = 0;
    server.hook = (request, reply) => {
      if (request.path.endsWith('/input')) { attempts++; if (!wrongIdentity) throw new Error('truncated input response'); return {...reply(), execution_id: id(99)}; }
      return reply();
    };
    await assert.rejects(client.input(captured, 'input', {kind: 'key', key: 'a', action: 'down'}), cause => cause.effectPossible === true);
    assert.equal(client.captureInput(), null); assert.equal(attempts, 1);
    await client.refresh(); assert.equal(attempts, 1); assert.ok(client.captureInput());
    client.dispose(); clients.delete(client);
  }
});

await test('late input receipt cannot affect a newer Run and captured old release is not retargeted', async () => {
  const {client, server} = await ready(); const context = client.captureInput(), blocked = gate(); let receipt;
  server.hook = (request, reply) => { if (request.path.endsWith('/input')) { receipt = reply(); return blocked.promise; } return reply(); };
  const input = client.input(context, 'input', {kind: 'key', key: 'a', action: 'down'});
  const rejected = assert.rejects(input, cause => cause.code === 'preview_context_changed' && cause.effectPossible === true);
  await until(() => receipt); await client.runRevision(revision('b')); await client.refresh();
  blocked.resolve(receipt); await rejected;
  assert.equal(client.snapshot().activeRun.revision_id, revision('b')); assert.ok(client.captureInput());
  await assert.rejects(client.input(context, 'input', {kind: 'key', key: 'a', action: 'up'}));
  assert.equal(server.calls.filter(x => x.path.endsWith('/input')).length, 1);
});

await test('readSession brackets stable identity with fresh Preview reads and rejects mid-read external Run change', async () => {
  const {client, server} = await ready(); const before = server.calls.length;
  const result = await client.readSession(client.captureInput(), 'units'); assert.equal(result.session_id, server.session.session_id);
  const paths = server.calls.slice(before).map(x => x.path);
  assert.equal(paths.filter(x => x === `/api/v1/previews/${id(2)}`).length, 2);
  assert.equal(paths[2], `/api/v1/sessions/${id(1)}/units`);
  const blocked = gate(); let captured;
  server.hook = (request, reply) => { if (request.path.endsWith('/units')) { captured = reply(); return blocked.promise; } return reply(); };
  const read = client.readSession(client.captureInput(), 'units'); const rejected = assert.rejects(read, {code: 'preview_context_changed'});
  await until(() => captured); server.activate(revision('b')); blocked.resolve(captured); await rejected;
  assert.equal(client.snapshot().activeRun.revision_id, revision('b'));
});

await test('wrong session read body fails closed and dispose/rebinding invalidate outstanding operations', async () => {
  const {client, server} = await ready(); server.hook = (request, reply) => request.path.endsWith('/units') ? {session_id: id(99)} : reply();
  await assert.rejects(client.readSession(client.captureInput(), 'units')); assert.equal(client.captureInput(), null);
  server.hook = null; await client.refresh(); const blocked = gate(); let receipt;
  server.hook = (request, reply) => { if (request.path.endsWith('/input')) { receipt = reply(); return blocked.promise; } return reply(); };
  const operation = client.input(client.captureInput(), 'input', {kind: 'key', key: 'a'});
  const rejected = assert.rejects(operation, {code: 'preview_context_changed'}); await until(() => receipt);
  client.updateSession({...server.session, management_binding: {}}); blocked.resolve(receipt); await rejected;
  assert.equal(client.snapshot().managed, true); assert.equal(client.captureInput(), null);
  client.dispose(); await assert.rejects(client.refresh());
  assert.ok(server.calls.every(x => !x.path.includes('/sessions/') || ['units'].some(action => x.path.endsWith('/' + action))));
});

await test('coalesced polling never overlaps and hidden/active delays follow contract', async () => {
  const {client, server} = await ready(); const blocked = gate(); let count = 0;
  server.hook = (request, reply) => { if (request.path === `/api/v1/previews/${id(2)}`) { count++; return blocked.promise; } return reply(); };
  const a = client.refresh(), b = client.refresh(); assert.equal(a, b); await until(() => count === 1);
  blocked.resolve(copy(server.preview)); await Promise.all([a, b]); assert.equal(count, 1);
  const originalTimer = globalThis.setTimeout, originalDocument = globalThis.document;
  const delays = [];
  globalThis.setTimeout = (fn, delay, ...args) => { delays.push(delay); return originalTimer(fn, delay, ...args); };
  try { globalThis.document = {hidden: true}; server.hook = null; await client.refresh(); assert.equal(delays.at(-1), 3000);
    globalThis.document = {hidden: false}; await client.refresh(); assert.equal(delays.at(-1), 500); }
  finally { globalThis.setTimeout = originalTimer; if (originalDocument === undefined) delete globalThis.document; else globalThis.document = originalDocument; }
});

await test('polling continues during a slow admission response and discovers the server desired Run', async () => {
  const {client, server} = await ready(); const blocked = gate(); let receipt;
  const originalTimer = globalThis.setTimeout; const timers = [];
  globalThis.setTimeout = (fn, delay, ...args) => { timers.push({fn, delay}); return originalTimer(fn, delay, ...args); };
  try {
    server.hook = (request, reply) => { if (request.method === 'POST' && request.path.endsWith('/runs') && !receipt) { receipt = reply(); return blocked.promise; } return reply(); };
    const operation = client.runRevision(revision('b')); await until(() => receipt);
    assert.equal(timers.at(-1).delay, 500); timers.at(-1).fn();
    await until(() => client.snapshot().preview.generation === 2);
    assert.equal(client.snapshot().pending, true); assert.equal(client.snapshot().cancelRunId, receipt.run_id); assert.equal(client.captureInput(), null);
    blocked.resolve(receipt); await operation;
  } finally { globalThis.setTimeout = originalTimer; }
});

await test('a late old Run GET cannot overwrite a newer complete refresh', async () => {
  const {client, server} = await ready(); const blocked = gate(); let captured;
  server.hook = (request, reply) => { if (request.method === 'GET' && request.path.includes('/runs/') && !captured) { captured = reply(); return blocked.promise; } return reply(); };
  const old = client.refresh(); const rejected = assert.rejects(old, {code: 'preview_context_changed'});
  await until(() => captured); await client.runRevision(revision('b')); await client.refresh();
  blocked.resolve(captured); await rejected; assert.equal(client.snapshot().activeRun.revision_id, revision('b'));
});

await test('expired leases and stopped actual sessions close all current contexts', async () => {
  const {client, server} = await ready(); server.preview.expires_at = new Date(Date.now() - 1).toISOString();
  await client.refresh(); assert.equal(client.snapshot().canSubmit, false); assert.equal(client.captureInput(), null); assert.equal(client.snapshot().canClose, true);
  server.preview.expires_at = future(); await client.refresh();
  client.updateSession({...server.session, state: 'stopped'}); await client.refresh();
  assert.equal(client.snapshot().canSubmit, false); assert.equal(client.snapshot().frameContext, null);
});

await test('LAN randomness uses getRandomValues without SubtleCrypto or Math.random and fails closed without crypto', async () => {
  const {client, server} = await ready(); const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  const oldRandom = Math.random;
  try {
    Math.random = () => { throw new Error('insecure random used'); };
    Object.defineProperty(globalThis, 'crypto', {configurable: true, value: {getRandomValues: bytes => { bytes.fill(0x37); return bytes; }}});
    await client.runRevision(revision('b')); assert.equal(posts(server)[0].headers['Idempotency-Key'], '37'.repeat(24));
    await client.refresh(); Object.defineProperty(globalThis, 'crypto', {configurable: true, value: {}});
    await assert.rejects(client.runRevision(revision('c')), {code: 'preview_random_unavailable'}); assert.equal(posts(server).length, 1);
  } finally { Math.random = oldRandom; if (descriptor) Object.defineProperty(globalThis, 'crypto', descriptor); else delete globalThis.crypto; }
});

await test('malformed successful mutation receipt is uncertain and only fresh GET can publish the actual Run', async () => {
  const {client, server} = await ready(); let malformed = true;
  server.hook = (request, reply) => { const body = reply(); if (malformed && request.method === 'POST' && request.path.endsWith('/runs')) { malformed = false; return {...body, revision_id: revision('d')}; } return body; };
  await assert.rejects(client.runRevision(revision('b')), cause => cause.code === 'preview_response_invalid' && cause.effectPossible === true);
  await client.refresh(); assert.equal(client.snapshot().activeRun.revision_id, revision('b')); assert.equal(posts(server).length, 1);
});

await test('post-read server bracket never reuses a Preview GET started before the data response', async () => {
  const {client, server} = await ready(); const unitsGate = gate(), pollGate = gate(); let units, oldPoll;
  server.hook = (request, reply) => {
    if (request.path.endsWith('/units')) { units = reply(); return unitsGate.promise; }
    if (units && !oldPoll && request.path === `/api/v1/previews/${id(2)}`) { oldPoll = reply(); return pollGate.promise; }
    return reply();
  };
  const dataRead = client.readSession(client.captureInput(), 'units'); const rejected = assert.rejects(dataRead, {code: 'preview_context_changed'});
  await until(() => units); const oldRead = client.refresh(); const oldRejected = assert.rejects(oldRead);
  await until(() => oldPoll); server.activate(revision('b')); unitsGate.resolve(units); await tick();
  pollGate.resolve(oldPoll); await oldRejected; await rejected; assert.equal(client.snapshot().activeRun.revision_id, revision('b'));
});

await test('before-read bracket never reuses an earlier poll and two panel readers cannot abort-starve each other', async () => {
  const {client, server} = await ready(); const blocked = gate(); let oldPoll;
  server.hook = (request, reply) => { if (request.path === `/api/v1/previews/${id(2)}` && !oldPoll) { oldPoll = reply(); return blocked.promise; } return reply(); };
  const poll = client.refresh(); await until(() => oldPoll);
  const oldCount = server.calls.filter(x => x.path === `/api/v1/previews/${id(2)}`).length;
  const context = client.captureInput();
  const units = client.readSession(context, 'units'), state = client.readSession(context, 'device-state');
  await tick(); assert.equal(server.calls.filter(x => x.path.endsWith('/units') || x.path.endsWith('/device-state')).length, 0);
  blocked.resolve(oldPoll); await poll; const payloads = await Promise.all([units, state]);
  assert.equal(payloads.length, 2); assert.ok(payloads.every(x => x.session_id === server.session.session_id));
  assert.ok(server.calls.filter(x => x.path === `/api/v1/previews/${id(2)}`).length > oldCount);
  assert.ok(client.captureInput());
});

await test('MPY capability gains require full same-session canary identity and never freeze the request', async () => {
  const {client, server} = await ready();
  const request = copy(server.preview.session_request);
  server.preview.runtime_capabilities = verifiedLoader(server.session); server.preview.capabilities.main_mpy = true;
  await client.refresh();
  assert.equal(client.snapshot().preview.capabilities.main_mpy, true);
  assert.equal(client.snapshot().canSubmit, true); assert.equal(client.snapshot().canCancel, true);
  assert.deepEqual(client.snapshot().preview.session_request, request);
  assert.equal(Object.isFrozen(client.snapshot().preview.runtime_capabilities.probe.actual_identity), true);
  for (const status of ['unsupported', 'unknown']) {
    server.preview.runtime_capabilities = {schema_version: 1, status, mpy_entrypoint: false}; server.preview.capabilities.main_mpy = false;
    await client.refresh(); assert.equal(client.snapshot().canSubmit, true); assert.equal(client.snapshot().canCancel, true); assert.equal(client.snapshot().canClose, true);
    assert.equal(client.snapshot().preview.capabilities.main_mpy, false);
  }
});

await test('a claimed MPY flag without exact process, ABI and restoration evidence fails closed', async () => {
  const mutations = [row => { delete row.runtime_capabilities; }, row => { row.runtime_capabilities.status = 'unknown'; },
    row => { row.runtime_capabilities.probe.owner_restored = false; }, row => { row.runtime_capabilities.probe.cleanup_complete = false; },
    row => { row.runtime_capabilities.probe.actual_identity.if_main = false; }, row => { row.runtime_capabilities.probe.actual_identity.sys_main_id += 1; },
    row => { row.runtime_capabilities.probe.file_sha256 = revision('0'); }, row => { row.runtime_capabilities.probe.nonce = 'not-a-nonce'; },
    row => { row.runtime_capabilities.mpy = 5; }, row => { row.runtime_capabilities.small_int_bits = 32; },
    row => { row.runtime_capabilities.identity.pid += 1; }, row => { row.runtime_capabilities.identity.worker_generation += 1; },
    row => { row.runtime_capabilities.identity.session_id = id(99); }, row => { row.runtime_capabilities.identity.firmware_sha256 = revision('c'); },
    row => { row.runtime_capabilities.identity.device_id = 'other'; }, row => { row.runtime_capabilities.identity.runtime = 'network'; },
    row => { row.runtime_capabilities.identity.process_start_token = ''; }];
  for (const mutate of mutations) {
    const {client, server} = await ready(); server.preview.runtime_capabilities = verifiedLoader(server.session); server.preview.capabilities.main_mpy = true;
    mutate(server.preview); await assert.rejects(client.refresh()); assert.equal(client.snapshot().synchronized, false);
    client.dispose(); clients.delete(client);
  }
});

await test('a late verified response from a prior worker cannot restore MPY admission', async () => {
  const {client, server} = await ready(); const blocked = gate(); let old;
  server.preview.runtime_capabilities = verifiedLoader(server.session); server.preview.capabilities.main_mpy = true;
  server.hook = (request, reply) => { if (!old && request.path === `/api/v1/previews/${id(2)}`) { old = reply(); return blocked.promise; } return reply(); };
  const reading = client.refresh(), rejected = assert.rejects(reading); await until(() => old);
  server.session.worker.generation += 1;
  server.preview.runtime_capabilities = {schema_version: 1, status: 'unknown', mpy_entrypoint: false}; server.preview.capabilities.main_mpy = false;
  client.updateSession(server.session); await client.refresh(); blocked.resolve(old); await rejected;
  assert.equal(client.snapshot().preview.capabilities.main_mpy, false); assert.equal(client.snapshot().canSubmit, true);
});

console.log(JSON.stringify({status: 'PASS', validation: 'HOST_ONLY_NOT_GUEST', count: results.length, checks: results}, null, 2));
