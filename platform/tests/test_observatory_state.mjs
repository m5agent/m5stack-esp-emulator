import assert from 'node:assert/strict';
import {ObservatoryState, duration, sessionIdentity} from '../web/observatory-state.js';
import {ObservatoryAPI, ReadPool} from '../web/observatory-client.js';

let now = Date.parse('2026-11-06T02:00:00Z');
const row = (id, state = 'running', extra = {}) => ({session_id: id, device_id: 'cores3', state,
  firmware_sha256: 'a'.repeat(64), created_at: new Date(now - 2000).toISOString(),
  completed_at: state === 'running' ? null : new Date(now).toISOString(), serial_bytes: 0, ...extra});
const snapshot = (active = [], recent = [], cursor = 0) => ({journal_id: 'journal-a', cursor, active, recent,
  status: {state: 'ok'}, jobs: {available: true, counts: {queued: 3}}, capacity: {active_sessions: active.length, max_sessions: 12}});
const store = new ObservatoryState({clock: () => now});
store.snapshot(snapshot());
const quick = row('quick', 'stopped', {purged: true, serial_bytes: 123});
store.events({journal_id: 'journal-a', events: [{seq: 1, session: row('quick')}, {seq: 2, session: quick}], next_cursor: 2});
assert.equal(store.visible().length, 1);
assert.equal(store.visible()[0].state, 'stopped');
assert.deepEqual(store.counts(), {running: 0, starting: 0, ending: 0, ended: 1, failed: 0});
const deadline = store.entries.get('quick').terminalUntil;
now += 3000;
store.events({journal_id: 'journal-a', events: [{seq: 2, session: quick}], next_cursor: 2});
store.snapshot(snapshot([], [quick], 2));
assert.equal(store.entries.get('quick').terminalUntil, deadline, 'repeated events/snapshots never extend terminal dwell');
now += 5001;
assert.equal(store.visible().length, 0);
assert.equal(store.recent().length, 1, 'expired models remain in the real activity history');
assert.equal(store.events({journal_id: 'other-journal', events: [], next_cursor: 0}), false);
assert.equal(store.cursor, 2);
assert.throws(() => store.events({journal_id: 'journal-a', events: [{seq: 4, session: quick}, {seq: 3, session: quick}], next_cursor: 4}), /顺序/);

const pressure = new ObservatoryState({clock: () => now});
const rows = Array.from({length: 64}, (_, i) => row(`device-${i}`, 'running', {device_id: i < 40 ? 'cores3' : 'atoms3r'}));
pressure.snapshot(snapshot(rows));
assert.equal(pressure.visible().length, 64);
assert.equal(new Set(pressure.visible().map(x => x.session_id)).size, 64);
assert.equal(pressure.counts().running, 64);
const ended = rows.slice(0, 20).map(x => ({...x, state: 'stopped', completed_at: new Date(now).toISOString()}));
for (const x of ended) pressure.apply(x);
assert.equal(pressure.visible('ended').length, 12, 'bounded terminal model budget');
assert.equal(pressure.counts().ended, 20, 'display budget does not change real counts');
pressure.apply(row('failed', 'failed'));
now += 8001;
assert.equal(pressure.visible('ended').length, 1, 'failed task retains 30s terminal dwell');
now += 22000;
assert.equal(pressure.visible('ended').length, 0);
const fresh = new ObservatoryState({clock: () => now});
fresh.snapshot(snapshot([], [quick]));
assert.equal(fresh.visible().length, 0, 'fresh page does not restage old completed tasks');
fresh.snapshot(snapshot([row('managed', 'running', {pid: 15, management_binding: {preview_id: 'preview'}})]));
const managed = fresh.entries.get('managed').session;
fresh.apply({...managed, serial_bytes: 4});
fresh.apply({session_id: 'managed', device_id: managed.device_id, state: 'running', created_at: managed.created_at,
  firmware_sha256: managed.firmware_sha256, management_binding: managed.management_binding});
assert.equal(fresh.entries.get('managed').session.pid, 15, 'projection updates retain authoritative live-only metadata');
const bindingA = {preview_id: 'preview-a', owner_epoch: 'epoch-a', expected_reference_sha256: 'a'.repeat(64)};
const bindingB = {expected_reference_sha256: 'a'.repeat(64), owner_epoch: 'epoch-a', preview_id: 'preview-a'};
const projectedManaged = row('managed-order', 'running', {management_binding: bindingB});
fresh.snapshot(snapshot([projectedManaged]));
fresh.live([{...projectedManaged, management_binding: bindingA, pid: 23}]);
assert.equal(sessionIdentity({...projectedManaged, management_binding: bindingA}), sessionIdentity(projectedManaged));
assert.equal(fresh.entries.get('managed-order').session.pid, 23, 'SQLite sorted keys cannot prevent managed live enrichment');
assert.deepEqual(Object.keys(fresh.entries.get('managed-order').session.management_binding), Object.keys(bindingB));
assert.equal(duration(quick), '2.0 秒', 'terminal duration does not advance with wall clock');
const drifted = new ObservatoryState({clock: () => now + 10000});
drifted.snapshot({...snapshot([], [row('clock-skew', 'stopped')]), server_time: new Date(now).toISOString()});
assert.equal(drifted.visible().length, 1, 'server time prevents fast client clock from hiding new terminal tasks');
now += 20000;
drifted.snapshot({...snapshot([], [quick, row('reconnected', 'stopped', {completed_at: new Date(now - 12000).toISOString()})]), server_time: new Date(now).toISOString()});
assert.ok(drifted.visible().some(x => x.session_id === 'reconnected'), 'unseen completed task discovered after reconnect receives a clearly terminal dwell');

const pool = new ReadPool(4);
let active = 0, maximum = 0;
await Promise.all(Array.from({length: 40}, () => pool.run(async () => {
  active++; maximum = Math.max(maximum, active);
  await new Promise(resolve => setTimeout(resolve, 1)); active--;
})));
assert.equal(maximum, 4);
pool.dispose();
await assert.rejects(pool.run(() => {}), {name: 'AbortError'});

const calls = [];
const api = new ObservatoryAPI({token: 'test-private-token', fetchImpl: async (path, options) => {
  calls.push({path, options}); return new Response('{"ok":true}', {headers: {'Content-Type': 'application/json'}});
}});
await assert.rejects(api.json('/api/v1/sessions', {method: 'POST', body: '{}'}), /只读/);
await assert.rejects(api.json('//external.example/api/v1/sessions'), /路径/);
await assert.rejects(api.json('/api/v1/../../secret'), /路径/);
assert.equal(calls.length, 0);
assert.deepEqual(await api.json('/api/v1/observatory/snapshot'), {ok: true});
assert.equal(calls[0].options.headers.get('Authorization'), 'Bearer test-private-token');
await api.json('/devices/catalog.json');
assert.equal(calls[1].options.headers.has('Authorization'), false, 'no service token on assets');
assert.ok(calls.every(x => x.options.method === 'GET' && x.options.redirect === 'error'));
api.dispose();
let resolveText, textStarted;
const decoding = new Promise(resolve => { textStarted = resolve; });
const late = new ObservatoryAPI({fetchImpl: async function() {
  assert.equal(this, undefined, 'native fetch must not receive the API instance as receiver');
  return {ok: true, status: 200, headers: new Headers(), blob: async () => ({text: () => { textStarted(); return new Promise(resolve => { resolveText = resolve; }); }})};
}});
const oldRead = late.json('/api/v1/observatory/snapshot');
await decoding; late.invalidate(); resolveText('{"ok":true}');
await assert.rejects(oldRead, {name: 'AbortError'}, 'post-parse generation guard rejects a disposed or reauthenticated read');
late.dispose();
console.log('Observatory state, lifecycle, pressure and read-only transport contracts PASS');
