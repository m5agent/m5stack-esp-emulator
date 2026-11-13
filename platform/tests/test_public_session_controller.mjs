import {SerialChannelState} from '../web/serial-channel-state.js';
import assert from 'node:assert/strict';
import {PublicDeviceService} from '../web/public-service.js';
import {PublicSessionController} from '../web/public-session-controller.js';

const deferred = () => {let resolve, reject; const promise = new Promise((yes, no) => {resolve = yes; reject = no;}); return {promise, resolve, reject};};
const tick = () => new Promise(resolve => setImmediate(resolve));
async function until(predicate) {
  const deadline = performance.now() + 2000;
  while (!predicate()) {
    assert.ok(performance.now() < deadline, 'Polling contract did not reach its next phase');
    await new Promise(resolve => setTimeout(resolve, 1));
  }
}
const result = session_id => ({session_id, device_id: 'cores3', state: 'running', display: {width: 320, height: 240}});
const stopped = session_id => ({...result(session_id), state: 'stopped', worker: {lease_active: false}});
function fakeService() {
  const calls = [], pendingSession = deferred();
  return {calls, pendingSession,
    create: async () => result('own1'),
    session: () => pendingSession.promise,
    serial: async () => ({next_offset: 1, data: 'x'}),
    fetch: async () => new Response(new Blob(['frame']), {headers: {'ETag': 'frame1'}}),
    input: async (id, command) => {calls.push(['input', id, command]); return {session_id: id};},
    evidence: async id => {calls.push(['evidence', id]); return new Blob(['zip']);},
    stop: async id => {calls.push(['stop', id]); return stopped(id);},
    request: async path => {calls.push(['request', path]); return {};},
  };
}

// Credentials are sent only to the explicitly chosen API, without cookies or
// redirects; this path never receives arbitrary firmware URL destinations.
{
  const calls = [];
  const service = new PublicDeviceService('https://service.example/lab', {token: 'test-only', fetchImpl: async (url, options) => {
    calls.push({url, options}); return Response.json({devices: []});
  }});
  await service.devices();
  assert.equal(calls[0].url, 'https://service.example/lab/api/v1/devices');
  assert.equal(calls[0].options.headers.get('Authorization'), 'Bearer test-only');
  assert.equal(calls[0].options.credentials, 'omit');
  assert.equal(calls[0].options.redirect, 'error');
  assert.throws(() => service.fetch('https://other.example/api/v1/devices'));
  assert.throws(() => service.fetch('/api/v1/../../private'));
  await service.evidence('own1');
  assert.match(calls[1].url, /\/sessions\/own1\/evidence$/);
}

// A late frame/session response cannot paint a stopped or replaced model.
{
  const service = fakeService(), frames = [], serial = [];
  const controller = new PublicSessionController({service, shell: {setImage: async () => {frames.push('paint');}}, onSerial: text => serial.push(text)});
  await controller.start({deviceId: 'cores3'});
  await controller.stop();
  service.pendingSession.resolve(result('own1'));
  await tick();
  assert.deepEqual(frames, []);
  assert.deepEqual(serial, []);
  assert.deepEqual(service.calls.map(row => row.slice(0, 2)), [['evidence', 'own1'], ['stop', 'own1']]);
}

// A create that succeeds after cancellation is still owned and cleaned up.
{
  const service = fakeService(), created = deferred();
  service.create = () => created.promise;
  const controller = new PublicSessionController({service});
  const abort = new AbortController();
  const start = controller.start({deviceId: 'cores3', signal: abort.signal});
  const rejection = assert.rejects(start, error => error.name === 'AbortError');
  abort.abort();
  const stop = controller.stop();
  created.resolve(result('late1'));
  await Promise.all([stop, rejection]);
  assert.deepEqual(service.calls.map(row => row.slice(0, 2)), [['evidence', 'late1'], ['stop', 'late1']]);
}

// A frame decoding before stop still has to check its owner before commit.
{
  const service = fakeService(), decode = deferred();
  let guard, painted = false;
  const controller = new PublicSessionController({service, shell: {async setImage(blob, sequence, current) {
    guard = current; await decode.promise; if (current()) painted = true; return painted;
  }}});
  await controller.start({deviceId: 'cores3'});
  service.pendingSession.resolve(result('own1'));
  while (!guard) await tick();
  await controller.stop();
  decode.resolve();
  await tick();
  assert.equal(guard(), false);
  assert.equal(painted, false);
}

// Stop releases held controls, requests evidence first, and retains history.
{
  const service = fakeService();
  const controller = new PublicSessionController({service});
  await controller.start({deviceId: 'cores3'});
  await controller.input({kind: 'key', key: 'a', action: 'down'});
  await controller.stop();
  assert.deepEqual(service.calls.map(row => row[0]), ['input', 'input', 'evidence', 'stop']);
  assert.equal(service.calls[1][2].action, 'up');
}
// A failed DELETE must retain ownership and support retry, including dispose.
{
  const service = fakeService(), states = [];
  let attempts = 0, creates = 0;
  service.create = async () => {creates++; return result('retry1');};
  service.stop = async id => {attempts++; if (attempts < 3) throw new Error('503 offline'); return stopped(id);};
  const controller = new PublicSessionController({service, onState: state => states.push(state)});
  await controller.start({deviceId: 'cores3'});
  await assert.rejects(controller.stop(), /503/);
  assert.equal(controller.current.session_id, 'retry1');
  assert.equal(states.at(-1).status, 'stop_pending');
  await assert.rejects(controller.start({deviceId: 'cores3'}), /503/);
  assert.equal(creates, 1, 'a failed stop must prevent replacement creates');
  await controller.dispose();
  assert.equal(controller.current, null);
  assert.equal(controller.disposed, true);
}

// Concurrent stops share the request and retain the ID until confirmation.
{
  const service = fakeService(), confirmation = deferred();
  let attempts = 0;
  service.stop = async () => {attempts++; return confirmation.promise;};
  const controller = new PublicSessionController({service});
  await controller.start({deviceId: 'cores3'});
  const first = controller.stop(), second = controller.stop();
  await tick();
  assert.equal(attempts, 1);
  assert.equal(controller.current.session_id, 'own1');
  confirmation.resolve(stopped('own1'));
  await Promise.all([first, second]);
  assert.equal(controller.current, null);
}

// Late-create cancellation cleanup can fail without losing the new guest.
{
  const service = fakeService(), created = deferred();
  let attempts = 0;
  service.create = () => created.promise;
  service.stop = async id => {if (++attempts === 1) throw new Error('offline'); return stopped(id);};
  const controller = new PublicSessionController({service});
  const abort = new AbortController();
  const start = controller.start({deviceId: 'cores3', signal: abort.signal});
  const rejected = assert.rejects(start, /offline/);
  abort.abort();
  created.resolve(result('late-retry'));
  await rejected;
  assert.equal(controller.current.session_id, 'late-retry');
  await controller.stop();
  assert.equal(controller.current, null);
}
// A committed create whose response is lost is recovered with the same immutable
// request. Caller edits cannot alter the replay or create a second guest.
{
  const service = fakeService(), requests = [], allocated = new Map();
  const units = [{unit_id: 'pir', port_id: 'A'}];
  service.create = async ({signal, ...request}) => {
    requests.push(structuredClone(request));
    if (!allocated.has(request.idempotencyKey)) allocated.set(request.idempotencyKey, result('lost1'));
    if (requests.length === 1) throw new TypeError('response lost');
    return allocated.get(request.idempotencyKey);
  };
  const controller = new PublicSessionController({service, createKey: () => 'stable-request'});
  await assert.rejects(controller.start({deviceId: 'cores3', firmwareId: 'fw1', units}), /response lost/);
  units[0].port_id = 'B';
  assert.ok(controller.createIntent);
  await Promise.all([controller.stop(), controller.stop()]);
  assert.equal(allocated.size, 1);
  assert.equal(requests.length, 2);
  assert.deepEqual(requests[0], requests[1]);
  assert.equal(requests[1].units[0].port_id, 'A');
  assert.equal(controller.createIntent, null);
  assert.equal(controller.current, null);
  assert.deepEqual(service.calls.map(row => row.slice(0, 2)), [['evidence', 'lost1'], ['stop', 'lost1']]);
}

// If the first POST never arrived, cancellation recovery may allocate the same
// intent once, then immediately clean it up; it never changes the key.
{
  const service = fakeService(), requests = [];
  service.create = async ({signal, ...request}) => {
    requests.push(request);
    if (requests.length === 1) throw new TypeError('offline before dispatch');
    return result('canceled-new');
  };
  const controller = new PublicSessionController({service, createKey: () => 'not-dispatched'});
  await assert.rejects(controller.start({deviceId: 'cores3'}));
  await controller.dispose();
  assert.deepEqual(requests[0], requests[1]);
  assert.equal(controller.current, null);
  assert.equal(controller.disposed, true);
}

// A lost cloud-startup receipt replays the captured reference even if the
// directory or selected startup mode changes before cancellation cleanup.
{
  const service=fakeService(),requests=[];
  const uiflowStartup={mode:'cloud',reference_sha256:'a'.repeat(64)};
  service.create=async({signal,...request})=>{
    requests.push(request);
    if(requests.length===1)throw new TypeError('cloud receipt lost');
    return result('cloud-lost');
  };
  const controller=new PublicSessionController({service,createKey:()=> 'cloud-stable'});
  await assert.rejects(controller.start({deviceId:'cores3',uiflowStartup}),/receipt lost/);
  uiflowStartup.reference_sha256='b'.repeat(64);uiflowStartup.mode='local';
  await controller.stop();
  assert.deepEqual(requests[0],requests[1]);
  assert.deepEqual(requests[1].uiflowStartup,{mode:'cloud',reference_sha256:'a'.repeat(64)});
  assert.equal(requests[1].firmwareId,undefined);
  assert.deepEqual(service.calls.map(row=>row.slice(0,2)),[['evidence','cloud-lost'],['stop','cloud-lost']]);
}

// A later 401 must not erase an already ambiguous allocation. Replacement
// starts remain blocked until the original key is recovered and stopped.
{
  const service = fakeService(), requests = [];
  service.create = async ({signal, ...request}) => {
    requests.push(request);
    if (requests.length === 1) throw new TypeError('lost');
    if (requests.length === 2) throw Object.assign(new Error('expired token'), {status:401, code:'unauthorized'});
    return result('recover-after-auth');
  };
  const controller = new PublicSessionController({service, createKey: () => 'never-replace'});
  await assert.rejects(controller.start({deviceId: 'cores3', firmwareId: 'original'}));
  await assert.rejects(controller.start({deviceId: 'cores3', firmwareId: 'replacement'}), /expired token/);
  assert.ok(controller.createIntent);
  await controller.stop();
  assert.ok(requests.every(request => request.firmwareId === 'original' && request.idempotencyKey === 'never-replace'));
}

// Explicit first-attempt pre-allocation errors do not invent an orphan guest.
for (const [status,code] of [[429,'capacity_exhausted'],[400,'invalid_uiflow_startup'],
  [409,'uiflow_startup_conflict'],[409,'uiflow_startup_unavailable'],[409,'uiflow_startup_reference_mismatch']]) {
  const service = fakeService(); let creates = 0;
  service.create = async () => {creates++; throw Object.assign(new Error('preallocation rejection'), {status,code});};
  const controller = new PublicSessionController({service});
  await assert.rejects(controller.start({deviceId: 'cores3'}), /preallocation/);
  assert.equal(controller.createIntent, null);
  await controller.stop();
  assert.equal(creates, 1);
}

// A malformed success receipt is ambiguous, never permission to stop an ID
// belonging to another device.
{
  const service = fakeService(); let creates = 0;
  service.create = async () => ++creates === 1 ? {...result('other'),device_id:'core2'} : result('verified');
  const controller = new PublicSessionController({service});
  await assert.rejects(controller.start({deviceId:'cores3'}), /收据/);
  assert.equal(controller.current, null);
  await controller.stop();
  assert.ok(service.calls.every(row => row[1] === 'verified'));
}

// HTTP 200/stopping is not terminal. Keep ownership until the service confirms
// stopped/failed and releases its worker lease.
{
  const service = fakeService(), confirmation = deferred();
  service.stop = async id => ({...result(id),state:'stopping',stop_pending:true,worker:{lease_active:true}});
  service.session = () => confirmation.promise;
  const controller = new PublicSessionController({service,stopPollIntervalMs:0});
  await controller.start({deviceId:'cores3'});
  const closing = controller.stop();
  await tick();
  assert.equal(controller.current.session_id, 'own1');
  confirmation.resolve(stopped('own1'));
  await closing;
  assert.equal(controller.current, null);
}

// A stop confirmation timeout keeps the same ID available for a later retry.
{
  const service = fakeService(); let stopCalls = 0;
  service.stop = async id => ++stopCalls === 1 ? {...result(id),state:'stopping',stop_pending:true} : stopped(id);
  service.session = async id => ({...result(id),state:'failed',worker:{lease_active:true}});
  const controller = new PublicSessionController({service,stopConfirmAttempts:2,stopPollIntervalMs:0});
  await controller.start({deviceId:'cores3'});
  await assert.rejects(controller.stop(), /尚未确认停止/);
  assert.equal(controller.current.session_id, 'own1');
  await controller.stop();
  assert.equal(controller.current, null);
}

// A hung request is bounded, retains its key, and cannot regain UI ownership
// after recovery has already stopped the same guest.
{
  const service = fakeService(), late = deferred(), requests = [];
  service.create = ({signal, ...request}) => {requests.push(request); return requests.length === 1 ? late.promise : Promise.resolve(result('timeout1'));};
  const controller = new PublicSessionController({service,createTimeoutMs:5,createKey:()=> 'timeout-key'});
  await assert.rejects(controller.start({deviceId:'cores3'}), /创建收据超时/);
  assert.ok(controller.createIntent);
  await controller.stop();
  late.resolve(result('timeout1'));
  await tick();
  assert.deepEqual(requests[0],requests[1]);
  assert.equal(controller.current,null);
}
// Unknown or malformed worker receipts never prove the lease was released.
for (const worker of [undefined, {}, {lease_active: null}, {lease_active: 'false'}]) {
  const service = fakeService();
  service.stop = async id => ({...result(id), state:'stopped', worker});
  service.session = async id => ({...result(id), state:'stopped', worker});
  const controller = new PublicSessionController({service,stopConfirmAttempts:1,stopPollIntervalMs:0});
  await controller.start({deviceId:'cores3'});
  await assert.rejects(controller.stop(), /尚未确认停止/);
  assert.equal(controller.current.session_id,'own1');
  service.stop = async id => stopped(id);
  await controller.stop();
}

// A stalled ZIP must not prevent DELETE. The actual request is aborted, and
// a late ZIP cannot overwrite the evidence of a subsequent session.
{
  const service = fakeService(), zip = deferred(), errors = [];
  let evidenceSignal;
  service.evidence = (id, {signal}) => {evidenceSignal=signal; return zip.promise;};
  const controller = new PublicSessionController({service,stopRequestTimeoutMs:5,onError:error=>errors.push(error)});
  await controller.start({deviceId:'cores3'});
  await controller.stop();
  assert.equal(evidenceSignal.aborted,true);
  assert.equal(controller.current,null);
  assert.ok(errors.some(error=>/证据 ZIP 未取得/.test(error.message)));
  assert.ok(service.calls.some(row=>row[0]==='stop'));
  zip.resolve(new Blob(['late-zip']));
  await tick();
  assert.equal(controller.lastEvidence,undefined);
}

// Hung DELETE/status reads end in a retryable failure retaining the identity.
for (const phase of ['delete','confirmation']) {
  const service = fakeService(), pending = deferred();
  let stopSignal;
  service.stop = async (id, {signal}) => {
    if (phase==='delete') {stopSignal=signal; return pending.promise;}
    return {...result(id),state:'stopping',stop_pending:true,worker:{lease_active:true}};
  };
  service.session = (id, {signal}={}) => {
    if (signal && phase==='confirmation') stopSignal=signal;
    return pending.promise;
  };
  const controller = new PublicSessionController({service,stopRequestTimeoutMs:5,stopPollIntervalMs:0});
  await controller.start({deviceId:'cores3'});
  await assert.rejects(controller.stop(), /超时/);
  assert.equal(stopSignal.aborted,true);
  assert.equal(controller.current.session_id,'own1');
  assert.equal(controller.stopOperation,null);
  service.stop = async id=>stopped(id);
  await controller.stop();
  pending.resolve(stopped('own1'));
  await tick();
  assert.equal(controller.current,null);
}

// Hung old inputs neither prevent stop nor poison the next session's queues.
{
  const service = fakeService(), oldInput = deferred(), errors=[];
  service.input = async id=>id==='own1' ? oldInput.promise : {session_id:id};
  const controller = new PublicSessionController({service,stopRequestTimeoutMs:5,onError:error=>errors.push(error)});
  await controller.start({deviceId:'cores3'});
  void controller.input({kind:'key',key:'a',action:'down'});
  await tick();
  await controller.stop();
  assert.equal(controller.inputQueues.size,0);
  assert.ok(errors.some(error=>/输入释放超时/.test(error.message)));
  service.create = async ()=>result('own2');
  await controller.start({deviceId:'cores3'});
  assert.deepEqual(await controller.input({kind:'key',key:'a',action:'down'}),{session_id:'own2'});
  await controller.stop();
  oldInput.resolve({session_id:'own1'});
  await tick();
}

// Slow session metadata no longer holds display delivery behind a serial GET
// and the 350ms metadata cadence. Every frame still comes from the owned guest.
{
  const service = fakeService(), frames = [], requests = [];
  let fetches = 0;
  service.fetch = async (path, options) => {
    requests.push({path, options});
    return new Response(new Blob([String(++fetches)]), {headers: {ETag: `frame-${fetches}`}});
  };
  const controller = new PublicSessionController({service, shell: {setImage: async () => true}, onFrame: value => frames.push(value)});
  await controller.start({deviceId: 'cores3'});
  await until(() => frames.length >= 3);
  assert.equal(controller.metadataFlight?.generation, controller.generation, 'the original session GET is still pending');
  assert.equal(controller.serialOffset, 0);
  assert.ok(requests.every(row => row.path === '/api/v1/sessions/own1/frame.png?max_age_ms=1'));
  assert.ok(requests.every(row => row.options.cache === 'no-store'));
  assert.equal(requests[1].options.headers['If-None-Match'], 'frame-1');
  assert.deepEqual(frames.slice(0, 3).map(frame => frame.sequence), [1, 2, 3]);
  await controller.stop();
  const count = fetches;
  service.pendingSession.resolve(result('own1'));
  await new Promise(resolve => setTimeout(resolve, 45));
  assert.equal(fetches, count, 'stop clears both loops, including a scheduled display read');
}

// A stalled frame fetch neither delays serial/state progress nor starts more
// frame requests. Stop aborts that fetch and a late response cannot regain UI.
{
  const service = fakeService(), pending = deferred(), painted = [], states = [], serial = [];
  let fetches = 0, frameSignal, sessions = 0;
  service.session = async id => {sessions++; return result(id);};
  service.serial = async () => ({next_offset: sessions, data: String(sessions)});
  service.fetch = (path, {signal}) => {fetches++; frameSignal = signal; return pending.promise;};
  const controller = new PublicSessionController({service, pollIntervalMs: 1, frameIntervalMs: 1,
    shell: {setImage: async () => {painted.push('paint'); return true;}}, onSerial: value => serial.push(value), onState: value => states.push(value)});
  await controller.start({deviceId: 'cores3'});
  await until(() => serial.length >= 3);
  await controller.pollFrames(controller.generation, 'own1');
  assert.equal(fetches, 1, 'one display request remains in flight');
  assert.ok(states.length >= 3);
  await controller.stop();
  assert.equal(frameSignal.aborted, true);
  pending.resolve(new Response(new Blob(['late']), {headers: {ETag: 'late'}}));
  await tick();
  assert.deepEqual(painted, []);
  assert.equal(controller.etag, null);
}

// Slow image decoding is part of the display lane's single in-flight work.
// Switching away and back to the same shell still fences that old decoder.
{
  const service = fakeService(), decode = deferred(), observations = [], guards = [];
  let fetches = 0, paints = 0;
  const shell = {async setImage(blob, sequence, current) {
    guards.push(current);
    if (sequence === 1) await decode.promise;
    if (!current()) return false;
    paints++; return true;
  }};
  service.fetch = async () => {fetches++; return new Response(new Blob(['frame']), {headers: {ETag: `etag-${fetches}`}});};
  const controller = new PublicSessionController({service, shell, frameIntervalMs: 1, onFrame: value => observations.push(value)});
  await controller.start({deviceId: 'cores3'});
  await until(() => guards.length === 1);
  await controller.pollFrames(controller.generation, 'own1');
  assert.equal(fetches, 1, 'decode cannot queue another capture');
  controller.setShell({setImage: async () => true});
  controller.setShell(shell);
  assert.equal(guards[0](), false, 'shell epoch fences a swap back to the same object');
  decode.resolve();
  await until(() => observations.length >= 1);
  assert.equal(observations[0].sequence, 2, 'the old decode is never published');
  assert.equal(paints, observations.length);
  assert.notEqual(controller.etag, 'etag-1');
  await controller.stop();
}

// Conditional responses keep the current texture, while a failed image commit
// must not cache an ETag that would suppress the missing texture on retry.
{
  const service = fakeService(), requests = [], frames = [];
  let attempt = 0;
  service.fetch = async (path, options) => {
    requests.push(options.headers);
    if (++attempt === 3) return new Response(null, {status: 304});
    return new Response(new Blob(['frame']), {headers: {ETag: 'same-frame'}});
  };
  const controller = new PublicSessionController({service, frameIntervalMs: 60000,
    shell: {setImage: async () => attempt !== 1}, onFrame: value => frames.push(value)});
  await controller.start({deviceId: 'cores3'});
  await until(() => frames.length === 1);
  assert.equal(controller.frameReady, false);
  assert.equal(controller.etag, null);
  clearTimeout(controller.frameTimer);
  await controller.pollFrames(controller.generation, 'own1');
  clearTimeout(controller.frameTimer);
  assert.equal(requests[1]['If-None-Match'], undefined);
  assert.equal(controller.frameReady, true);
  await controller.pollFrames(controller.generation, 'own1');
  clearTimeout(controller.frameTimer);
  assert.equal(requests[2]['If-None-Match'], 'same-frame');
  assert.equal(frames.length, 2, '304 never decodes or republishes a stale frame');
  assert.equal(controller.frameReady, true);
  await controller.stop();
}

// Reset aborts both old lanes and discards a pre-reset image even when a
// noncompliant transport resolves it after the new generation is displaying.
{
  const service = fakeService(), beforeReset = deferred(), reset = deferred(), frames = [];
  let fetches = 0, oldSignal;
  service.fetch = (path, {signal}) => {
    if (++fetches === 1) {oldSignal = signal; return beforeReset.promise;}
    return Promise.resolve(new Response(new Blob(['new']), {headers: {ETag: 'after-reset'}}));
  };
  service.request = () => reset.promise;
  const controller = new PublicSessionController({service, shell: {setImage: async () => true}, onFrame: value => frames.push(value)});
  await controller.start({deviceId: 'cores3'});
  const resetting = controller.reset();
  await tick();
  assert.equal(oldSignal.aborted, true);
  assert.equal(fetches, 1, 'polling stays paused until reset acknowledges');
  reset.resolve({});
  await resetting;
  await until(() => frames.length === 1);
  beforeReset.resolve(new Response(new Blob(['old']), {headers: {ETag: 'before-reset'}}));
  await tick();
  assert.equal(frames.length, 1);
  assert.equal(controller.etag, 'after-reset');
  await controller.stop();
}

// A terminal session update fences an already decoding image and ends both
// polling lanes without waiting for the display response to finish.
{
  const service = fakeService(), decode = deferred(), guards = [], frames = [];
  const controller = new PublicSessionController({service, shell: {async setImage(blob, sequence, current) {
    guards.push(current); await decode.promise; return current();
  }}, onFrame: value => frames.push(value)});
  await controller.start({deviceId: 'cores3'});
  await until(() => guards.length === 1);
  service.pendingSession.resolve(stopped('own1'));
  await tick();
  assert.equal(controller.current.state, 'stopped');
  assert.equal(guards[0](), false);
  decode.resolve();
  await tick();
  assert.deepEqual(frames, []);
  assert.equal(controller.frameFlight, null);
  assert.equal(controller.metadataFlight, null);
  await controller.stop();
}

const servoProfile = {deviceId: 'stackchan', board: 'm5stackchan', firmwareSHA256: 'a'.repeat(64), outputs: {kind: 'stackchan-scs-qom-v1', path: '/machine/scs_servo', property: 'state',
  calibration: {yawZeroTicks: 460, pitchZeroTicks: 620, tickDegrees: 5 / 16, yawDirection: 1, pitchDirection: 1}}};
const servoState = (packets = 1) => ({schema_version: 1, source: 'qemu-uart1-scs-controller', powered: true, packets, rejected_packets: 0,
  motion_model: 'command-time-position-v1', pwm_motion_modelled: false,
  servos: [470, 650].map((position, index) => ({id: index + 1, present_position: position, goal_position: position + 10,
    torque: 1, mode: 'position', moving: true, goal_time_ms: 100, goal_speed: 0, pwm: 0}))});
const servoReceipt = (packets = 1) => ({session_id: 'own1', path: '/machine/scs_servo', property: 'state', value: servoState(packets)});
const servoCapability = () => ({session_id: 'own1', path: '/machine/scs_servo', properties: [{name: 'state', type: 'any'}]});
function servoService() {
  const service = fakeService();
  service.create = async () => ({...result('own1'), device_id: 'stackchan', firmware_sha256: 'a'.repeat(64)});
  service.stop = async id => ({...stopped(id), device_id: 'stackchan'});
  return service;
}

// Native output is the same owned guest's validated controller readback.
// It progresses independently of metadata and never turns goal into present.
{
  const service = servoService(), outputs = [], availability = [], requests = [];
  let packets = 0;
  service.request = async (path, options) => {
    requests.push({path, options});
    return path.includes('/qom/list?') ? servoCapability() : servoReceipt(++packets);
  };
  const controller = new PublicSessionController({service, outputProfile: servoProfile, outputIntervalMs: 1,
    onDeviceState: value => outputs.push(value), onOutputState: value => availability.push(value)});
  await controller.start({deviceId: 'stackchan'});
  await until(() => outputs.length >= 3);
  assert.ok(controller.metadataFlight, 'the native QOM lane does not await session polling');
  assert.equal(requests.filter(row => row.path.includes('/qom/list?')).length, 1);
  assert.ok(requests.every(row => row.path.startsWith('/api/v1/sessions/own1/qom') && row.path.includes('path=%2Fmachine%2Fscs_servo')));
  assert.ok(requests.every(row => row.options.signal instanceof AbortSignal));
  assert.equal(outputs[0].device_id, 'stackchan');
  assert.equal(outputs[0].servos[0].present_position, 470);
  assert.equal(outputs[0].servos[0].goal_position, 480);
  assert.equal(controller.outputObservation.transport, 'native-service-qom-v1');
  assert.equal(controller.outputObservation.session_id, 'own1');
  assert.equal(controller.outputObservation.firmware_sha256, 'a'.repeat(64));
  assert.deepEqual(availability.map(row => row.status), ['available']);
  assert.equal(controller.profile, undefined, 'native readback does not invent a browser runtime receipt/profile');
  await controller.stop();
}

// Unsupported old backends stay explicitly unknown after one capability read.
// Display delivery remains live, with no repeated QOM request or error spam.
{
  const service = servoService(), outputs = [], availability = [], errors = [];
  let requests = 0, frames = 0;
  service.request = async () => {requests++; return {...servoCapability(), properties: []};};
  const controller = new PublicSessionController({service, outputProfile: servoProfile, outputIntervalMs: 1, frameIntervalMs: 1,
    shell: {setImage: async () => true}, onFrame: () => frames++, onDeviceState: value => outputs.push(value),
    onOutputState: value => availability.push(value), onError: value => errors.push(value)});
  await controller.start({deviceId: 'stackchan'});
  await until(() => availability.length === 1 && frames >= 3);
  await controller.pollOutputs(controller.generation, 'own1');
  assert.equal(requests, 1);
  assert.equal(controller.outputStatus, 'unavailable');
  assert.deepEqual(outputs, []);
  assert.deepEqual(errors, []);
  assert.equal(availability[0].transport, 'native-service-qom-v1');
  await controller.stop();
}

// Cross-session, wrong-path, wrong-property and untrusted controller payloads
// all fail closed before any angle reaches the model callback.
for (const corrupt of [
  receipt => {receipt.session_id = 'other';}, receipt => {receipt.path = '/machine/other';},
  receipt => {receipt.property = 'goal';}, receipt => {receipt.value.source = 'host-fake';},
  receipt => {receipt.value.servos[0].present_position = NaN;},
]) {
  const service = servoService(), outputs = [], availability = [];
  service.request = async path => {
    if (path.includes('/qom/list?')) return servoCapability();
    const receipt = servoReceipt(); corrupt(receipt); return receipt;
  };
  const controller = new PublicSessionController({service, outputProfile: servoProfile,
    onDeviceState: value => outputs.push(value), onOutputState: value => availability.push(value)});
  await controller.start({deviceId: 'stackchan'});
  await until(() => availability.length === 1);
  assert.equal(availability[0].status, 'unavailable');
  assert.deepEqual(outputs, []);
  assert.equal(controller.lastDeviceState, null);
  await controller.stop();
}

// Legacy QMP errors and restricted native APIs disable the optional output
// lane once, preserving frame/session control and explicit unknown state.
for (const [status, code] of [[404, 'not_found'], [500, 'qmp_error'], [403, 'runtime_acl_denied']]) {
  const service = servoService(), availability = [], errors = [];
  let requests = 0;
  service.request = async () => {requests++; throw Object.assign(new Error('Unavailable controller fixture'), {status, code});};
  const controller = new PublicSessionController({service, outputProfile: servoProfile,
    onOutputState: value => availability.push(value), onError: error => errors.push(error)});
  await controller.start({deviceId: 'stackchan'});
  await until(() => availability.length === 1);
  await controller.pollOutputs(controller.generation, 'own1');
  assert.equal(requests, 1);
  assert.equal(availability[0].status, 'unavailable');
  assert.deepEqual(errors, []);
  await controller.stop();
}

// A hung capability response cannot block frames, queue more probes, or begin
// reading controller state after its session has already stopped.
{
  const service = servoService(), capability = deferred(), outputs = [];
  let requests = 0, signal, frames = 0;
  service.request = (path, options) => {requests++; signal = options.signal; return capability.promise;};
  const controller = new PublicSessionController({service, outputProfile: servoProfile, frameIntervalMs: 1,
    shell: {setImage: async () => true}, onFrame: () => frames++, onDeviceState: value => outputs.push(value)});
  await controller.start({deviceId: 'stackchan'});
  await until(() => frames >= 3);
  await controller.pollOutputs(controller.generation, 'own1');
  assert.equal(requests, 1);
  await controller.stop();
  assert.equal(signal.aborted, true);
  capability.resolve(servoCapability());
  await tick();
  assert.equal(requests, 1);
  assert.deepEqual(outputs, []);
}

// Reset invalidates an in-flight state reply, repeats capability discovery,
// and publishes only the new native generation's controller observation.
{
  const service = servoService(), oldState = deferred(), outputs = [];
  let capabilities = 0, reads = 0;
  service.request = async path => {
    if (path.endsWith('/reset')) return {};
    if (path.includes('/qom/list?')) {capabilities++; return servoCapability();}
    return ++reads === 1 ? oldState.promise : servoReceipt(20);
  };
  const controller = new PublicSessionController({service, outputProfile: servoProfile,
    onDeviceState: value => outputs.push(value)});
  await controller.start({deviceId: 'stackchan'});
  await until(() => reads === 1);
  await controller.reset();
  await until(() => outputs.length === 1);
  oldState.resolve(servoReceipt(2));
  await tick();
  assert.equal(capabilities, 2);
  assert.equal(outputs.length, 1);
  assert.equal(outputs[0].packets, 20);
  await controller.stop();
}

// Replacing the shell forces a fresh application of even an unchanged state;
// the old in-flight reply cannot paint a shell swapped away and back.
{
  const service = servoService(), oldState = deferred(), outputs = [], shell = {};
  let reads = 0;
  service.request = async path => path.includes('/qom/list?') ? servoCapability() : ++reads === 1 ? oldState.promise : servoReceipt(5);
  const controller = new PublicSessionController({service, shell, outputProfile: servoProfile, outputIntervalMs: 1,
    onDeviceState: value => outputs.push(value)});
  await controller.start({deviceId: 'stackchan'});
  await until(() => reads === 1);
  controller.setShell({}); controller.setShell(shell);
  oldState.resolve(servoReceipt(1));
  await until(() => outputs.length === 1);
  assert.equal(outputs[0].packets, 5);
  controller.setShell({});
  await until(() => outputs.length === 2);
  assert.equal(outputs[1].packets, 5);
  await controller.stop();
}

// Pending reset and a failed post-reset capability read cannot expose the
// previous generation's validated position/timestamp as a current observation.
{
  const service = servoService(), resetAck = deferred();
  let afterReset = false;
  service.request = async path => {
    if (path.endsWith('/reset')) return resetAck.promise;
    if (path.includes('/qom/list?')) {
      if (afterReset) throw Object.assign(new Error('post-reset QMP unavailable'), {code: 'qmp_error'});
      return servoCapability();
    }
    return servoReceipt(7);
  };
  const controller = new PublicSessionController({service, outputProfile: servoProfile});
  await controller.start({deviceId: 'stackchan'});
  await until(() => controller.lastDeviceState !== null);
  assert.ok(controller.outputObservation.observed_at);
  afterReset = true;
  const resetting = controller.reset();
  await tick();
  assert.equal(controller.outputStatus, 'pending');
  assert.equal(controller.lastDeviceState, null);
  assert.equal(controller.outputObservation, null);
  resetAck.resolve({});
  await resetting;
  await until(() => controller.outputStatus === 'unavailable');
  assert.equal(controller.lastDeviceState, null);
  assert.equal(controller.outputObservation, null);
  await controller.stop();
}

// Output metadata cannot point at another device/controller or bypass its
// explicit firmware binding. Devices without a profile never probe SCS.
{
  const invalid = structuredClone(servoProfile); invalid.outputs.path = '/machine/other';
  assert.throws(() => new PublicSessionController({service: servoService(), outputProfile: invalid}), /output profile/);
  for (const firmwareSHA256 of [undefined, null, '', 'short', 'A'.repeat(64), 'g'.repeat(64), 123]) {
    assert.throws(() => new PublicSessionController({service: servoService(), outputProfile: {...servoProfile, firmwareSHA256}}), /explicit firmware SHA-256/);
  }
  const service = servoService(), availability = []; let reads = 0;
  service.request = async () => {reads++; return servoCapability();};
  const controller = new PublicSessionController({service, outputProfile: {...servoProfile, firmwareSHA256: 'b'.repeat(64)}, onOutputState: value => availability.push(value)});
  await assert.rejects(controller.start({deviceId: 'cores3'}), /不属于/);
  await controller.start({deviceId: 'stackchan'});
  await until(() => availability.length === 1);
  assert.equal(availability[0].status, 'unavailable');
  assert.equal(reads, 0, 'wrong firmware cannot use the declared geometry/readback binding');
  await controller.stop();
  const plain = new PublicSessionController({service});
  await plain.start({deviceId: 'stackchan'});
  await plain.pollOutputs(plain.generation, 'own1');
  assert.equal(reads, 0, 'unbound outputs never probe an arbitrary native backend');
  await plain.stop();
}

console.log('PUBLIC_SESSION_CONTROLLER_OK: independent single-flight frame/metadata/native-SCS lanes, fresh conditional frames, validated capability/receipt/firmware binding, unknown unsupported outputs, generation/shell/reset/stop fences and create recovery');

// Stream ownership rejects delayed A/B/A responses and never combines logs.
{
  const channels = [{channel:'console',transport:'console',bytes:4},{channel:'usb-serial-jtag',transport:'usb-serial-jtag',bytes:3}];
  const state = new SerialChannelState('own1'); state.update({...result('own1'),serial_channels:channels});
  const consoleRequest=state.request(); state.select('usb-serial-jtag'); const usbRequest=state.request();
  assert.equal(state.accept(consoleRequest,{session_id:'own1',channel:'console',data:'UART',next_offset:4}),null);
  state.accept(usbRequest,{session_id:'own1',channel:'usb-serial-jtag',data:'USB',next_offset:3});
  assert.equal(state.view().text,'USB');state.select('console');
  assert.equal(state.accept(consoleRequest,{data:'late UART',next_offset:9}),null);
  const request=state.request(); state.accept(request,{data:'UART',next_offset:4});
  assert.equal(state.accept(request,{data:'UART',next_offset:4}),null,'duplicate concurrent response is discarded');
  assert.equal(state.view().text,'UART');state.select('usb-serial-jtag');assert.equal(state.view().text,'USB');
  assert.throws(()=>state.accept(state.request(),{session_id:'other',channel:'usb-serial-jtag',data:'x',next_offset:4}));
  assert.throws(()=>state.accept(state.request(),{channel:'console',data:'x',next_offset:4}));
  state.update({...result('own1'),serial_channels:[]});assert.equal(state.request(),null);
}
// The actual controller carries channel and cursor to the service, fences late
// output on a switch, and restores the previous channel's separate cursor.
{
  const service=fakeService(), pending=deferred(), views=[], calls=[];
  const session={...result('own1'),serial_channels:[{channel:'console',transport:'console',bytes:4},{channel:'usb-serial-jtag',transport:'usb-serial-jtag',bytes:3}]};
  service.create=async()=>session;service.session=async()=>session;
  service.serial=async(id,offset,options)=>{calls.push([id,offset,options.channel]);return calls.length===1?pending.promise:{session_id:id,channel:options.channel,data:offset?'':'USB',next_offset:3};};
  const controller=new PublicSessionController({service,pollIntervalMs:1,onSerialView:view=>views.push(view)});
  await controller.start({deviceId:'cores3'});await until(()=>calls.length===1);
  controller.selectSerialChannel('usb-serial-jtag');pending.resolve({session_id:'own1',channel:'console',data:'UART',next_offset:4});
  await until(()=>views.some(view=>view.text==='USB'));
  assert.ok(calls.some(row=>row[2]==='usb-serial-jtag'&&row[1]===0));assert.ok(!views.some(view=>view.text.includes('UART')));
  await controller.stop();
}
