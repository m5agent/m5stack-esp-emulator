import assert from 'node:assert/strict';
import {PublicDeviceService} from '../web/public-service.js';
import {PublicSessionController} from '../web/public-session-controller.js';

const deferred = () => {let resolve, reject; const promise = new Promise((yes, no) => {resolve = yes; reject = no;}); return {promise, resolve, reject};};
const tick = () => new Promise(resolve => setImmediate(resolve));
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
{
  const service = fakeService(); let creates = 0;
  service.create = async () => {creates++; throw Object.assign(new Error('full'), {status:429,code:'capacity_exhausted'});};
  const controller = new PublicSessionController({service});
  await assert.rejects(controller.start({deviceId: 'cores3'}), /full/);
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
console.log('PUBLIC_SESSION_CONTROLLER_OK: stable create recovery, definite rejections, cancellation, bounded terminal stop, strict lease confirmation, stale-frame fencing and retained evidence');
