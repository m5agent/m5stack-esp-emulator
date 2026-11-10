// Host scheduling contracts. These message/latency fixtures execute no guest.
import assert from 'node:assert/strict';
import {PublicQemuRuntime} from '../web/public-qemu-runtime.js';

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {resolve = yes; reject = no;});
  return {promise, resolve, reject};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
async function until(predicate) {
  const deadline = performance.now() + 2000;
  while (!predicate()) {
    assert.ok(performance.now() < deadline, 'Independent polling did not reach the expected phase');
    await new Promise(resolve => setTimeout(resolve, 2));
  }
}
function fixture({deviceId = 'stackchan', headless = false, outputs = true, request = async () => ({})} = {}) {
  const calls = [], errors = [], states = [], active = new Map(), maximum = new Map();
  const runtime = new PublicQemuRuntime({root: 'https://example.test/', storage: {},
    onError: error => errors.push(error), onState: value => states.push(value)});
  runtime.generation = 1;
  runtime.profile = {deviceId, display: headless ? null : {width: 320, height: 240}, ...(outputs ? {outputs: {}} : {})};
  runtime.status = 'running'; runtime.serial = ''; runtime.waiters = new Map();
  runtime.engineOwner = {observe:()=>({enginePortTransferred:true}),release(){}};
  runtime.port = {close() {}}; runtime.iframe = {remove() {}}; runtime.abort = new AbortController();
  runtime.ask = async op => {
    calls.push({op, generation: runtime.generation});
    if (op === 'quit') {
      queueMicrotask(() => runtime.receive({type: 'exit', value: {code: 0, workersCreated: 5, workersRemaining: 0}}, runtime.generation));
      return;
    }
    if (op === 'dispose') return {workersRemaining: 0};
    active.set(op, (active.get(op) || 0) + 1);
    maximum.set(op, Math.max(maximum.get(op) || 0, active.get(op)));
    try {return await request(op,runtime);}
    finally {active.set(op, active.get(op) - 1);}
  };
  return {runtime, calls, errors, states, maximum, count: op => calls.filter(row => row.op === op).length};
}

// The SCS QOM reply can stall while shared framebuffer reads continue. Calling
// poll again cannot add a second request to a lane or queue old snapshots.
{
  const output = deferred();
  const f = fixture({request: op => op === 'outputs' ? output.promise : Promise.resolve({})});
  f.runtime.poll(1);
  await until(() => f.count('frame') >= 4);
  f.runtime.poll(1);
  assert.equal(f.count('outputs'), 1);
  assert.equal(f.maximum.get('frame'), 1);
  assert.equal(f.maximum.get('outputs'), 1);
  await f.runtime.stop();
  const count = f.calls.length;
  output.resolve({});
  await new Promise(resolve => setTimeout(resolve, 60));
  assert.equal(f.calls.length, count, 'a pending output response cannot restart polling after stop');
  assert.equal(f.runtime.pollLanes.size, 0);
  assert.deepEqual(f.errors, []);
}

// Orientation uses QMP but never gates Cardputer framebuffer delivery. A late
// orientation response cannot change the stopped run's display or emit state.
{
  const display = deferred();
  const f = fixture({deviceId: 'cardputer-adv', outputs: false, request: op => op === 'display' ? display.promise : Promise.resolve({})});
  f.runtime.poll(1);
  await until(() => f.count('frame') >= 4);
  assert.equal(f.count('display'), 1);
  assert.equal(f.maximum.get('display'), 1);
  await f.runtime.stop();
  const count = f.calls.length, stateCount = f.states.length;
  display.resolve({orientation: 'portrait', deviceRotationDeg: -90});
  await tick();
  assert.equal(f.runtime.display, null);
  assert.equal(f.states.length, stateCount);
  assert.equal(f.calls.length, count);
}

// The reverse boundary also holds: a slow frame request cannot suppress
// actual actuator observations, and there is no second in-flight frame.
{
  const frame = deferred();
  const f = fixture({request: op => op === 'frame' ? frame.promise : Promise.resolve({})});
  f.runtime.poll(1);
  await until(() => f.count('outputs') >= 3);
  assert.equal(f.count('frame'), 1);
  assert.equal(f.maximum.get('outputs'), 1);
  await f.runtime.stop();
  const count = f.calls.length;
  frame.resolve({});
  await tick();
  assert.equal(f.calls.length, count);
  assert.deepEqual(f.errors, []);
}

// Replacing both generation and private channel invalidates old timers and
// orientation replies even when the old transport eventually succeeds.
{
  const displays = [deferred(), deferred()];
  let requested = 0;
  const f = fixture({deviceId: 'cardputer-adv', outputs: false, request: op => op === 'display' ? displays[requested++].promise : Promise.resolve({})});
  f.runtime.poll(1);
  f.runtime.generation = 2;
  f.runtime.port = {close() {}};
  f.runtime.poll(2);
  displays[0].resolve({orientation: 'portrait', deviceRotationDeg: -90});
  await tick();
  assert.equal(f.runtime.display, null);
  displays[1].resolve({orientation: 'landscape', deviceRotationDeg: 0});
  await until(() => f.runtime.display?.orientation === 'landscape');
  assert.equal(f.states.filter(state=>state.display?.orientation==='landscape').length, 1, 'only the current channel publishes orientation');
  await f.runtime.stop();
  assert.deepEqual(f.errors, []);
}

// Headless devices keep the admitted 250ms output cadence, produce no display
// request, and do not wake the stopped guest with a scheduled read.
{
  const f = fixture({deviceId: 'atoms3-lite', headless: true});
  f.runtime.poll(1);
  await new Promise(resolve => setTimeout(resolve, 170));
  assert.equal(f.count('outputs'), 1);
  assert.equal(f.count('frame'), 0);
  assert.equal(f.count('display'), 0);
  await until(() => f.count('outputs') === 2);
  await f.runtime.stop();
  const count = f.calls.length;
  await new Promise(resolve => setTimeout(resolve, 275));
  assert.equal(f.calls.length, count);
}

// Paused guests perform no frame/QOM reads, but owner failure still reaches a
// terminal state. Separate lane errors must not produce repeated stop work.
{
  const f = fixture();
  f.runtime.status = 'paused';
  let failed = false;
  f.runtime.readEngineOwnership = () => failed ? {engineOwnerLive: false, engineFallbackTerminations: 1} : null;
  f.runtime.poll(1);
  await tick();
  assert.equal(f.count('frame')+f.count('outputs')+f.count('display'), 0);
  assert.equal(f.calls.length,0,'paused guests do not create host metrics or QMP requests');
  failed = true;
  await until(() => f.runtime.status === 'stopped');
  assert.equal(f.errors.length, 1);
  assert.match(f.errors[0].message, /执行线程异常停止/);
  assert.equal(f.runtime.pollLanes.size, 0);
}

// One failed lane stops its peers. A different lane's late rejection is
// observed, but cannot report another error or schedule a replacement request.
{
  const output = deferred(), frame = deferred();
  const f = fixture({request: op => op === 'outputs' ? output.promise : frame.promise});
  f.runtime.poll(1);
  output.reject(new Error('QOM timeout fixture'));
  await until(() => f.runtime.status === 'stopped');
  const count = f.calls.length;
  frame.reject(new Error('late frame failure'));
  await tick();
  assert.equal(f.errors.length, 1);
  assert.equal(f.errors[0].message, 'QOM timeout fixture');
  assert.equal(f.calls.length, count);
}

console.log('PUBLIC_QEMU_POLLING_OK: independent frame/QOM/orientation lanes, bounded in-flight work, headless cadence, ownership/generation/stop fences; no guest executed');
