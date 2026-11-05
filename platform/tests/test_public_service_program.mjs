// Host-only deterministic protocol fixtures, not guest/device validation.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {PublicServiceProgram} from '../web/public-service-program.js';
import {PublicSessionController} from '../web/public-session-controller.js';
import {createPreviewClient} from '../web/preview-client.js';

const id = n => n.toString(16).padStart(32, '0'), hash = text => createHash('sha256').update(text).digest('hex');
const clone = value => structuredClone(value), tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => {let resolve; const promise = new Promise(done => {resolve = done;}); return {promise, resolve};};
async function until(test) {for (let i = 0; i < 300; i++) {if (test()) return; await new Promise(resolve => setTimeout(resolve, 1));} assert.fail('fixture boundary not reached');}
const caps = {execution_mode: 'same-guest-uart-repl', cleanup_mode: 'interrupt-only', latest_wins: true, run_cancellation: true,
  input: true, frame: 'on-demand', events: 'polling', application_ready: 'unknown', main_mpy: false, hotplug: false,
  gc_enabled: false, principal_mode: 'shared-control-bearer-local-control'};
function fixture({running = false} = {}) {
  const now = () => new Date().toISOString(), calls = [], runs = new Map();
  const session = {session_id: id(1), device_id: 'cores3', firmware_sha256: 'a'.repeat(64), created_at: now(),
    runtime: 'qemu', state: 'running', pid: 1234, program_transport: 'uart-repl', units: [], worker: {generation: 1, lease_active: true},
    management_binding: {preview_id: id(2), owner_epoch: id(3), expected_reference_sha256: 'b'.repeat(64)}};
  const preview = {preview_id: id(2), owner_epoch: id(3), owner: 'local-control', state: 'ready', generation: 0,
    request: {device_id: 'cores3'}, session_request: {device_id: 'cores3', reference_sha256: 'b'.repeat(64)},
    session_id: id(1), session_identity: {session_id: id(1), firmware_sha256: session.firmware_sha256}, allocation_state: 'bound',
    allocation_key: `preview:${id(2)}:allocation:1`, active_run_id: null, desired_run_id: null, transition_run_id: null,
    created_at: now(), updated_at: now(), expires_at: new Date(Date.now() + 600000).toISOString(), error: null,
    capabilities: caps, limits: {max_previews: 128, max_runs_per_preview: 256, gc_enabled: false, retention_mode: 'retention-only'}};
  const f = {session, preview, calls, runs, running, serial: '', nextOffset: 0};
  const service = f.service = {
    async request(path, options = {}) {
      const method = options.method || 'GET', body = options.body;
      calls.push({path, method, body: clone(body), headers: options.headers});
      if (f.hook) {const reply = await f.hook(path, options); if (reply !== undefined) return reply;}
      if (path === '/api/v1/devices') return {devices: [{device_id: 'cores3', creatable: true, program_modes: ['uiflow-live']},
        {device_id: 'tab5', creatable: true, program_modes: []}]};
      if (path === '/api/v1/previews' && method === 'POST') {f.creationCount = (f.creationCount || 0) + 1; preview.request = {...clone(body), runtime: 'qemu'}; return clone(preview);}
      if (path === `/api/v1/previews/${id(2)}` && method === 'GET') return clone(preview);
      if (path === `/api/v1/sessions/${id(1)}`) return clone(session);
      if (path.endsWith('/program')) {
        if (method === 'POST') {
          assert.equal(body.expected_execution_id, f.plainProgram?.execution_id ?? null);
          f.plainGeneration = (f.plainGeneration || 0) + 1;
          f.plainProgram = {execution_id: id(80 + f.plainGeneration), revision_id: hash(body.source), source_sha256: hash(body.source),
            state: f.running ? 'running' : 'completed', firmware_sha256: session.firmware_sha256, pid: session.pid, serial_offset: 0};
          f.serial = `__M5_EXEC_${f.plainProgram.execution_id}__:START\nplain output\n${f.running ? '' : `__M5_EXEC_${f.plainProgram.execution_id}__:DONE\n`}`;
          f.readSerialOnce = false;
        }
        return {session_id: session.session_id, program_transport: 'uart-repl', program: clone(f.plainProgram ?? null)};
      }
      if (path === '/api/v1/program-revisions') {
        const source = body.files['main.py'].data, fileHash = hash(source), hashes = {'main.py': fileHash};
        return {revision: {source_kind: body.source_kind, entrypoint: body.entrypoint, total_file_bytes: Buffer.byteLength(source),
          revision_id: hash(JSON.stringify({entrypoint: body.entrypoint, files: hashes, source_kind: body.source_kind})),
          files: [{path: 'main.py', sha256: fileHash, size: Buffer.byteLength(source), kind: 'python'}]}};
      }
      if (path.endsWith('/runs') && method === 'POST') {
        assert.equal(body.expected_owner_epoch, preview.owner_epoch); assert.equal(body.expected_generation, preview.generation);
        const generation = ++preview.generation;
        const run = {preview_id: id(2), run_id: id(10 + generation), execution_id: id(20 + generation), revision_id: body.revision_id,
          request: clone(body), generation, source_kind: 'uiflow2-package', state: f.running ? 'running' : 'completed',
          client_generation: body.client_generation ?? null, timeout_seconds: 120, created_at: now(), updated_at: now(),
          cancel_intent: false, interrupt_ack: 'unknown', application_ready: 'unknown', error: null,
          execution_mode: 'same-guest-uart-repl', cleanup_mode: 'interrupt-only'};
        run.last_observation = {execution_id: run.execution_id, revision_id: run.revision_id, firmware_sha256: session.firmware_sha256,
          pid: session.pid, state: run.state, acknowledged: true, execution_mode: 'same-guest-uart-repl', serial_offset: 0};
        runs.set(run.run_id, run); preview.active_run_id = preview.desired_run_id = run.run_id; preview.updated_at = now();
        f.serial = `old application\n__M5_EXEC_${run.execution_id}__:START\r\nhello 中文\r\n${f.running ? '' : `__M5_EXEC_${run.execution_id}__:DONE\r\n`}`;
        const receipt = {...clone(run), state: 'queued'}; delete receipt.last_observation; return receipt;
      }
      if (/\/runs\/[0-9a-f]{32}$/.test(path)) return clone(runs.get(path.split('/').at(-1)));
      if (path.endsWith('/cancel')) {
        const run = runs.get(path.split('/').at(-2));
        run.state = 'cancelled'; run.cancel_intent = true; run.interrupt_ack = 'confirmed'; run.updated_at = now();
        preview.active_run_id = null; preview.updated_at = now(); return clone(run);
      }
      if (path.includes('/serial?')) {return {data: f.readSerialOnce ? '' : (f.readSerialOnce = true, f.serial), next_offset: Buffer.byteLength(f.serial)};}
      if (path.endsWith('/close')) {
        preview.state = 'closed'; preview.active_run_id = preview.desired_run_id = preview.transition_run_id = null; preview.updated_at = now();
        session.state = 'stopped'; session.worker.lease_active = false; return clone(preview);
      }
      if (path.endsWith('/input')) return {preview_id: id(2), run_id: body.expected_run_id,
        execution_id: runs.get(body.expected_run_id).execution_id, revision_id: runs.get(body.expected_run_id).revision_id,
        captured_at: now(), result: {session_id: id(1), applied: true}};
      throw new Error('unexpected request ' + method + ' ' + path);
    },
    async evidence() {calls.push({path: 'evidence', method: 'GET'}); return new Blob(['zip']);},
    session: async () => clone(session), serial: async () => ({data: '', next_offset: 0}),
  };
  f.adopter = {current: null, setManagedStop(stop) {this.stop = stop;}, async adoptSession(s, options) {this.current = clone(s); this.stop = options.stop;}, async adoptManagedSession(s, client, options) {
    this.current = clone(s); this.client = client; this.stop = options.stop;
  }};
  f.program = new PublicServiceProgram({service, controller: f.adopter, pollIntervalMs: 1, createKey: () => 'fixture-create'});
  return f;
}
const checks = [];
async function test(name, action) {await action(); checks.push(name);}

await test('backend capability gates create without assuming browser admission', async () => {
  const f = fixture(); await assert.rejects(f.program.start({deviceId: 'tab5'}), /未开放/);
  assert.equal(f.calls.filter(x => x.method === 'POST').length, 0); await f.program.stop();
});
await test('same session source revision run output and evidence-before-close', async () => {
  const f = fixture(), output = [], phases = [];
  const {session, previewClient} = await f.program.start({deviceId: 'cores3', units: [{id: 'external1', unit_id: 'pir', port_id: 'port-a'}]});
  assert.equal(session.session_id, f.adopter.current.session_id); assert.equal(previewClient, f.adopter.client); assert.equal(f.program.ready, true);
  const result = await f.program.run('print("hello 中文")\n', {onOutput: text => output.push(text), onPhase: value => phases.push(value)});
  assert.equal(result.state, 'completed'); assert.equal(result.output, 'hello 中文\r\n'); assert.deepEqual(phases, ['uploading', 'complete']);
  assert.equal(output.join(''), result.output); assert.equal(f.program.busy, false);
  assert.equal(f.calls.filter(x => x.path === '/api/v1/previews' && x.method === 'POST').length, 1);
  assert.equal(f.calls.find(x => x.path === '/api/v1/previews').body.units[0].unit_id, 'pir');
  await f.program.stop();
  assert.ok(f.calls.findIndex(x => x.path === 'evidence') < f.calls.findIndex(x => x.path.endsWith('/close')));
  assert.equal(f.session.worker.lease_active, false); assert.equal(f.program.snapshot().session, null);
});
await test('concurrent interrupts cancel only the captured run once', async () => {
  const f = fixture({running: true}), phases = [];
  await f.program.start({deviceId: 'cores3'});
  const running = f.program.run('while True: pass\n', {onPhase: value => phases.push(value)});
  await until(() => phases.includes('running'));
  await Promise.all([f.program.interrupt(), f.program.interrupt()]);
  assert.equal((await running).state, 'cancelled');
  assert.equal(f.calls.filter(x => x.path.endsWith('/cancel')).length, 1); await f.program.stop();
});
await test('wrong revision bytes are rejected before Run admission', async () => {
  const f = fixture(); await f.program.start({deviceId: 'cores3'});
  f.hook = path => path === '/api/v1/program-revisions' ? {revision: {revision_id: 'f'.repeat(64)}} : undefined;
  await assert.rejects(f.program.run('print(1)\n'), /revision/);
  assert.equal(f.calls.filter(x => x.path.endsWith('/runs') && x.method === 'POST').length, 0); await f.program.stop();
});
await test('late create after controller stop preserves identity and cleanup', async () => {
  const f = fixture(), pending = deferred();
  f.program.controller = new PublicSessionController({service: f.service});
  f.hook = (path, options) => path === '/api/v1/previews' && options.method === 'POST' ? pending.promise : undefined;
  const starting = f.program.start({deviceId: 'cores3'}), rejected = assert.rejects(starting, e => e.name === 'AbortError');
  await until(() => f.calls.some(x => x.path === '/api/v1/previews'));
  const stopping = f.program.controller.stop(); pending.resolve(clone(f.preview));
  await Promise.all([stopping, rejected]); assert.equal(f.session.state, 'stopped');
});
await test('ambiguous create recovery reuses exact body and idempotency key', async () => {
  const f = fixture(); let first = true;
  f.hook = (path, options) => {if (path === '/api/v1/previews' && options.method === 'POST' && first) {first = false; throw new Error('receipt lost');}};
  await assert.rejects(f.program.start({deviceId: 'cores3'}), /receipt lost/); await f.program.stop();
  const posts = f.calls.filter(x => x.path === '/api/v1/previews' && x.method === 'POST');
  assert.equal(posts.length, 2); assert.deepEqual(posts[0].body, posts[1].body); assert.deepEqual(posts[0].headers, posts[1].headers);
});
await test('only initial source-proven pre-allocation auth rejections retire create intent', async () => {
  for (const [status, code] of [[401, 'unauthorized'], [503, 'preview_auth_unavailable']]) {
    const f = fixture();
    f.hook = (path, options) => {if (path === '/api/v1/previews' && options.method === 'POST')
      throw Object.assign(new Error('pre-allocation rejection'), {status, code, outcomeUnknown: status >= 500});};
    await assert.rejects(f.program.start({deviceId: 'cores3'}), /pre-allocation/);
    assert.equal(f.program.snapshot().createPending, false); await f.program.stop();
    assert.equal(f.calls.filter(x => x.path === '/api/v1/previews' && x.method === 'POST').length, 1);
  }
});
await test('other 5xx and wrong-status auth names retain uncertain create identity', async () => {
  for (const [status, code] of [[500, 'internal_error'], [503, 'backend_not_ready'], [500, 'preview_auth_unavailable'], [503, 'unauthorized']]) {
    const f = fixture();
    f.hook = (path, options) => {if (path === '/api/v1/previews' && options.method === 'POST')
      throw Object.assign(new Error('unknown allocation'), {status, code});};
    await assert.rejects(f.program.start({deviceId: 'cores3'}), /unknown allocation/);
    assert.equal(f.program.snapshot().createPending, true); assert.equal(f.program.createIntent.uncertain, true);
    // This host fixture never allocated a VM; retire only the fixture object.
  }
});
await test('known rejection on recovery cannot erase a prior ambiguous create', async () => {
  const f = fixture(); let calls = 0;
  f.hook = (path, options) => {if (path === '/api/v1/previews' && options.method === 'POST') {
    if (++calls === 1) throw new Error('lost original receipt');
    throw Object.assign(new Error('control unavailable on recovery'), {status: 503, code: 'preview_auth_unavailable', outcomeUnknown: true});
  }};
  await assert.rejects(f.program.start({deviceId: 'cores3'}), /lost original/);
  await assert.rejects(f.program.stop(), /on recovery/);
  assert.equal(f.program.snapshot().createPending, true); assert.equal(f.program.createIntent.attempts, 2);
  assert.equal(calls, 2, 'no automatic recovery retry');
});
await test('attaching existing managed session never closes its Preview', async () => {
  const f = fixture(); await f.program.attach(f.session); await f.program.stop();
  assert.equal(f.calls.filter(x => x.method === 'POST').length, 0); assert.equal(f.session.state, 'running');
});
await test('controller owner change fences pending code before mutation', async () => {
  const f = fixture(); await f.program.start({deviceId: 'cores3'});
  f.adopter.current = {...f.adopter.current, session_id: id(99)};
  await assert.rejects(f.program.run('print(1)'), e => e.name === 'AbortError');
  assert.equal(f.calls.filter(x => x.path === '/api/v1/program-revisions').length, 0); await f.program.stop();
});
await test('plain existing UART session uses actual GET and POST CAS without fake interrupt', async () => {
  const f = fixture(); delete f.session.management_binding;
  await f.program.attach(f.session); assert.equal(f.program.canInterrupt, false);
  const result = await f.program.run('print("plain")\n');
  assert.equal(result.state, 'completed'); assert.equal(result.output, 'plain output\n');
  await assert.rejects(f.program.interrupt(), /不提供独立中断/);
  assert.equal(f.calls.find(x => x.path.endsWith('/program') && x.method === 'POST').body.expected_execution_id, null);
  await f.program.stop(); assert.equal(f.session.state, 'running'); assert.equal(f.calls.some(x => x.path.endsWith('/close')), false);
});
await test('plain running replacement abandons only old observation and preserves new CAS', async () => {
  const f = fixture({running: true}); delete f.session.management_binding;
  await f.program.attach(f.session);
  const first = f.program.run('while True: pass\n'); await until(() => f.program.canReplace);
  const firstId = f.plainProgram.execution_id; f.running = false;
  const second = f.program.run('print("new")\n');
  assert.equal((await first).state, 'superseded'); assert.equal((await second).state, 'completed');
  const posts = f.calls.filter(x => x.path.endsWith('/program') && x.method === 'POST');
  assert.equal(posts[1].body.expected_execution_id, firstId); assert.equal(f.calls.some(x => x.path.endsWith('/cancel')), false);
  await f.program.stop();
});

// Controller managed routing is exercised with the real PreviewClient; ordinary
// lifecycle behavior remains covered by test_public_session_controller.mjs.
await test('managed controller input uses Preview and external detach does not delete', async () => {
  const f = fixture({running: true}); await f.program.start({deviceId: 'cores3'});
  const execution = f.program.run('while True: pass\n'); await until(() => f.program.execution?.phase === 'running');
  const controller = new PublicSessionController({service: f.service});
  const observingClient = createPreviewClient({session: f.session, api: f.program.api});
  await observingClient.refresh();
  await controller.adoptManagedSession(f.session, observingClient, {owned: false});
  await controller.input({kind: 'key', key: 'a', action: 'down'});
  await assert.rejects(controller.reset(), /Preview/);
  await controller.stop();
  assert.ok(f.calls.some(x => x.path.endsWith('/input') && x.body.input?.key === 'a'));
  assert.equal(f.calls.filter(x => x.path.includes('/sessions/') && x.method !== 'GET').length, 0);
  // Replacing only this detached observer does not alter the underlying VM.
  assert.equal(f.session.state, 'running');
  await f.program.interrupt().catch(() => {}); await execution.catch(() => {}); await f.program.stop();
});
await test('managed frames require exact Run headers and real pixel blob hash without session fallback', async () => {
  const f = fixture(); await f.program.start({deviceId: 'cores3'}); await f.program.run('print(1)');
  const client = createPreviewClient({session: f.session, api: f.program.api}); await client.refresh();
  const painted = [], requested = [], controller = new PublicSessionController({service: f.service, shell: {setImage: async () => {painted.push(1); return true;}}});
  await controller.adoptManagedSession(f.session, client, {owned: false});
  const context = client.snapshot().frameContext, body = new Blob(['actual fixture frame']); let wrongHeader = true, wrongHash = false;
  f.service.fetch = async path => {
    requested.push(path); return new Response(body, {headers: {'X-Preview-ID': context.previewId,
      'X-Run-ID': wrongHeader ? id(99) : context.runId, 'X-Frame-Execution-ID': context.executionId,
      'X-Frame-Revision-ID': context.revisionId, 'X-Frame-SHA256': wrongHash ? '0'.repeat(64) : hash('actual fixture frame')}});
  };
  await assert.rejects(controller.readFrame(controller.generation, f.session.session_id, new AbortController().signal), /身份不匹配/);
  wrongHeader = false; wrongHash = true;
  await assert.rejects(controller.readFrame(controller.generation, f.session.session_id, new AbortController().signal), /摘要不匹配/);
  wrongHash = false; await controller.readFrame(controller.generation, f.session.session_id, new AbortController().signal);
  assert.equal(painted.length, 1); assert.ok(requested.every(path => path.startsWith('/api/v1/previews/') && !path.includes('/sessions/')));
  await controller.stop(); await f.program.stop();
});
await tick();
console.log(JSON.stringify({status: 'PASS', scope: 'host-only protocol fixtures; no guest validation', checks}));
