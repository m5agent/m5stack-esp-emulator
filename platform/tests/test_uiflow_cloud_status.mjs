// Host UI contracts only. Protocol/firmware evidence is collected separately.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {uiflowCloudStatusView, renderUIFlowCloudStatus} from '../web/uiflow-cloud-status.js';

const session = (webrepl = {}, extras = {}) => ({
  state: 'running', uiflow_startup: {mode: 'cloud'},
  uiflow_cloud_status: {source: 'guest-pcap', state: 'observed',
    pairing: {state: 'code_received'},
    webrepl: {state: 'identity_rejected', reason: 'mac_not_bound', handshakes: 2, disconnects: 2, ...webrepl},
    observation: {status: 'complete'}, ...extras},
});
const text = value => value ? [value.heading, ...value.lines].join('\n') : '';

assert.equal(uiflowCloudStatusView({state: 'running'}), null, 'ordinary firmware has no inferred cloud verdict');
assert.match(text(uiflowCloudStatusView(null, {cloudExpected: true})), /服务未提供诊断状态/);
assert.match(text(uiflowCloudStatusView({uiflow_startup: {mode: 'cloud'}})), /服务未提供诊断状态/);
const rejected = text(uiflowCloudStatusView(session()));
assert.match(rejected, /已收到配对码（不代表已完成绑定）/);
assert.match(rejected, /云端拒绝设备身份/);
assert.match(rejected, /设备尚未绑定/);
assert.match(rejected, /握手 2 次 · 断开 2 次/);
assert.doesNotMatch(rejected, /已就绪|连接成功|执行成功/);
assert.match(text(uiflowCloudStatusView(session({state: 'heartbeat_observed', reason: null}))), /心跳往返（尚未验证远程代码执行）/);
assert.match(text(uiflowCloudStatusView(session({state: 'handshake_observed', reason: null}))), /尚未观测到心跳往返/);
assert.match(text(uiflowCloudStatusView(session({state: 'disconnected', reason: null}))), /已观测到连接断开/);
const disconnected = text(uiflowCloudStatusView(session({state: 'disconnected', reason: null, device_registered: true, heartbeat_roundtrips: 5})));
assert.match(disconnected, /曾观测到云端设备登记回执/);
assert.match(disconnected, /曾观测到心跳往返 5 次/);
assert.match(disconnected, /尚未验证远程代码执行/);
assert.match(text(uiflowCloudStatusView(session({reason: 'mac_not_found'}))), /云端未找到该设备/);
const serverError = uiflowCloudStatusView(session({state:'server_error',reason:'server_error'}));
assert.match(text(serverError), /云端返回业务错误/);
assert.doesNotMatch(text(serverError), /拒绝设备身份|设备尚未绑定|云端未找到该设备/);
assert.equal(serverError.tone,'warning');
for (const state of ['stopped', 'failed']) assert.match(text(uiflowCloudStatusView({...session(), state})), /末次观测/);
const reset = session({state: 'not_observed', reason: null, handshakes: 0, disconnects: 0}, {state: 'not_observed', pairing: {state: 'not_observed'}});
assert.match(text(uiflowCloudStatusView(reset)), /尚未观测到配对码/);
assert.doesNotMatch(text(uiflowCloudStatusView(reset)), /已收到配对码|尚未绑定/);
for (const state of ['unavailable', 'future', undefined]) {
  const unavailable = text(uiflowCloudStatusView(session({}, {state})));
  assert.match(unavailable, /暂无法判断/);
  assert.doesNotMatch(unavailable, /已收到配对码|尚未绑定/);
}
const untrusted = text(uiflowCloudStatusView(session({state: '__proto__', reason: '<img src=x onerror=alert(1)>', handshakes: -1, disconnects: '2'}, {pairing: {state: 'future'}})));
assert.match(untrusted, /状态未知/);
assert.doesNotMatch(untrusted, /<img|累计观测|\[object Object\]/);
assert.match(text(uiflowCloudStatusView(session({}, {observation: {status: 'partial'}}))), /观测尚不完整/);

let writes = 0, content = '';
const element = {hidden: true, dataset: {}, get textContent() {return content;}, set textContent(value) {content = value; writes++;}};
renderUIFlowCloudStatus(element, session());
assert.equal(element.hidden, false); assert.equal(element.dataset.cloudState, 'warning');
renderUIFlowCloudStatus(element, session()); assert.equal(writes, 1, 'unchanged polling must not repeat aria-live text');
renderUIFlowCloudStatus(element, reset); assert.doesNotMatch(element.textContent, /尚未绑定/);
renderUIFlowCloudStatus(element, {state: 'running'});
assert.equal(element.hidden, true); assert.equal(element.textContent, ''); assert.equal(element.dataset.cloudState, '');

// Exercise the actual session-card updater to ensure history and polling use
// the same renderer as the workbench rather than relying on HTML snapshots.
const source = await readFile(new URL('../web/sessions.js', import.meta.url), 'utf8');
const updater = source.slice(source.indexOf('function updateSessionCard('), source.indexOf('\nfunction render()'));
const fields = new Map();
const field = key => {if (!fields.has(key)) fields.set(key, {dataset: {}, textContent: '', hidden: false}); return fields.get(key);};
const card = {querySelector: selector => field(selector)};
class SerialFixture {update() {}}
const update = new Function('deviceFor', 'statusClass', 'SerialChannelState', 'renderSerialChannelSelect', 'state', 'formatTime', 'ACTIVE_STATES', 'updateDeviceStateUi', 'renderUIFlowCloudStatus', updater + '\nreturn updateSessionCard;')(
  () => ({}), value => value, SerialFixture, () => {}, {serial: new Map(), visuals: new Map(), deviceStates: new Map()}, value => value,
  new Set(['running']), () => {}, renderUIFlowCloudStatus);
update(card, {...session(), session_id: 'cloud-fixture', state: 'failed'});
assert.match(field('[data-field="uiflow-cloud"]').textContent, /末次观测/);
update(card, {session_id: 'plain-fixture', state: 'running'});
assert.equal(field('[data-field="uiflow-cloud"]').hidden, true);
console.log('UIFlow independent pairing/WebREPL, unknown states, history and safe rendering contracts passed');
