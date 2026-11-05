// Deterministic configuration/model ownership contracts; no browser or guest.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createPublicUnitAssembly, validateUnitAssemblyDraft} from '../web/public-unit-assembly.js';

const clone = value => structuredClone(value);
const deferred = () => { let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve}; };
const tests = [];
const test = async (name, action) => { await action(); tests.push(name); };
const rejects = (promise, code) => assert.rejects(promise, error => error.code === code);
const throws = (action, code) => assert.throws(action, error => error.code === code);
const port = (id = 'port-a', visual = 'grove') => ({id, visual_port: visual, label: id,
  wiring_status: 'confirmed', physical_presence: 'main-device', pins: {yellow: 2, white: 1}});
const unit = (id, {bus = 'i2c', address = 32, status = 'implemented', hosts = ['host-a', 'host-b']} = {}) =>
  ({id, name: id, interface: {bus, address_7bit: [address]}, runtime: {status, hosts}, inputs: {}});
const catalog = () => ({units: [unit('hub', {address: 0}), unit('sensor'), unit('other', {address: 33}),
  unit('button', {bus: 'gpio'}), unit('planned', {status: 'planned'}), unit('foreign', {hosts: ['elsewhere']})],
hosts: [{device_id: 'host-a', ports: [port()]}, {device_id: 'host-b', ports: [port()]}]});
const root = (unitId = 'sensor') => ({id: 'external1', unit_id: unitId, port_id: 'port-a'});
const leaf = (unitId = 'sensor', slot = 1) => ({id: `external1-${slot}`, unit_id: unitId, parent_id: 'external1', port_id: `grove-${slot}`});

// Minimal DOM/picker seam: createUnitPicker itself has its existing browser
// contracts. These tests exercise this module's actual lifecycle and handlers.
class Node {
  constructor(tag, doc) { this.tagName = tag; this.ownerDocument = doc; this.children = []; this.dataset = {};
    this.listeners = new Map(); this.className = ''; this.value = ''; this.label = ''; this._text = '';
    this.classList = {add: value => { this.className += ' ' + value; }}; }
  get childElementCount() { return this.children.length; }
  append(...children) { for (const child of children) { child.parentNode = this; this.children.push(child); } }
  replaceChildren(...children) { for (const child of this.children) child.parentNode = null; this.children = []; this._text = ''; this.append(...children); }
  set textContent(value) { this.replaceChildren(); this._text = value; }
  get textContent() { return this._text + this.children.map(x => x.textContent).join(''); }
  setAttribute(key, value) { this[key] = value; }
  addEventListener(type, fn) { const list = this.listeners.get(type) || []; list.push(fn); this.listeners.set(type, list); }
  removeEventListener(type, fn) { this.listeners.set(type, (this.listeners.get(type) || []).filter(x => x !== fn)); }
  dispatchEvent(event) { for (const fn of this.listeners.get(event.type) || []) fn(event); if (event.bubbles) this.parentNode?.dispatchEvent(event); return true; }
  querySelectorAll(selector) {
    const matches = node => selector.startsWith('.') ? node.className.split(' ').includes(selector.slice(1))
      : selector === '[data-creation-field]' ? 'creationField' in node.dataset : node.tagName === selector;
    return this.children.flatMap(child => [...(matches(child) ? [child] : []), ...child.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  focus() { this.ownerDocument.activeElement = this; }
  scrollIntoView() {}
}
function documentFixture() { const doc = {createElement: tag => new Node(tag, doc)}; return doc; }
function pickerFactory({gates = [], calls = []} = {}) {
  return async (mount, {deviceId, api}) => {
    const inventory = await api('/api/v1/units?device_id=' + deviceId); calls.push({deviceId, inventory});
    const gate = gates.shift(); if (gate) await gate.promise;
    const doc = mount.ownerDocument, rows = [];
    for (const p of inventory.hosts.find(host => host.device_id === deviceId)?.ports || []) {
      if (p.wiring_status !== 'confirmed' || p.physical_presence !== 'main-device') continue;
      const row = doc.createElement('div'); row.className = 'unit-picker-port';
      for (let n = 0; n < 4; n++) {
        const select = doc.createElement('select'); row.append(select);
        const fixtures = doc.createElement('div'); fixtures.className = 'unit-picker-fixtures'; row.append(fixtures);
      }
      rows.push({port: p, row}); mount.append(row);
    }
    const group = doc.createElement('optgroup'); group.label = '可运行 · 当前设备'; mount.append(group);
    const badge = doc.createElement('span'); badge.className = 'unit-capability'; badge.textContent = '可运行'; mount.append(badge);
    const results = doc.createElement('p'); results.className = 'unit-picker-results'; results.textContent = '6 个匹配 · 4 个可运行'; mount.append(results);
    return {attachments(id) {
      assert.equal(id, deviceId);
      return rows.flatMap(({port, row}, index) => {
        const selects = row.querySelectorAll('select'), id = `external${index + 1}`;
        return selects[0].value ? [{id, unit_id: selects[0].value, port_id: port.id},
          ...(selects[0].value === 'hub' ? selects.slice(1).flatMap((select, n) => select.value
            ? [{id: `${id}-${n + 1}`, unit_id: select.value, parent_id: id, port_id: `grove-${n + 1}`}] : []) : [])] : [];
      });
    }, dispose() { mount.replaceChildren(); }};
  };
}
async function fixture(options = {}) {
  const doc = documentFixture(), container = doc.createElement('div'), changes = [], errors = [], calls = [];
  const panel = await createPublicUnitAssembly(container, {deviceId: 'host-a', catalog: catalog(),
    onChange: value => changes.push(value), onError: error => errors.push(error), pickerFactory: pickerFactory({calls}), ...options});
  return {panel, container, doc, changes, errors, calls};
}
const shell = () => ({calls: [], async attachUnit(id, {port}) { this.calls.push(['attach', port, id]); return {}; },
  async detachUnit(port) { this.calls.push(['detach', port]); }});

await test('real-frozen-host-contract-hub-positive-and-address-negative', async () => {
  const read = name => readFile(new URL(`../units/${name}.json`, import.meta.url), 'utf8').then(JSON.parse);
  const [units, hosts, profiles] = await Promise.all(['catalog', 'host-ports', 'runtime-profiles'].map(read));
  const actual = {units: units.units.map(u => ({...u, runtime: profiles.units[u.id] || {}})), hosts: hosts.hosts};
  assert.equal(validateUnitAssemblyDraft(actual, 'cores3', [root('hub'), leaf('env-iii'), leaf('ncir', 2)]).length, 3);
  throws(() => validateUnitAssemblyDraft(actual, 'cores3', [root('hub'), leaf('env-iii'), leaf('env-iii', 2)]), 'assembly_address_conflict');
});
await test('unknown-planned-foreign-and-wrong-port-fail-closed', () => {
  for (const id of ['planned', 'foreign']) throws(() => validateUnitAssemblyDraft(catalog(), 'host-a', [root(id)]), 'assembly_incompatible');
  throws(() => validateUnitAssemblyDraft(catalog(), 'host-a', [root('missing')]), 'assembly_unit_unknown');
  throws(() => validateUnitAssemblyDraft(catalog(), 'host-a', [{...root(), port_id: 'absent'}]), 'assembly_incompatible');
});
await test('topology-identity-connectors-and-bus-conflicts', () => {
  throws(() => validateUnitAssemblyDraft(catalog(), 'host-a', [root(), root()]), 'assembly_invalid');
  throws(() => validateUnitAssemblyDraft(catalog(), 'host-a', [leaf()]), 'assembly_topology_invalid');
  throws(() => validateUnitAssemblyDraft(catalog(), 'host-a', [root('hub'), leaf(), {...leaf('other'), id: 'another'}]), 'assembly_port_conflict');
  throws(() => validateUnitAssemblyDraft(catalog(), 'host-a', [root('hub'), leaf('button'), leaf('sensor', 2)]), 'assembly_bus_conflict');
});
await test('port-admission-and-incomplete-wiring-are-not-overridden', () => {
  for (const mutate of [c => c.hosts[0].ports[0].admitted_unit_ids = ['other'], c => c.hosts[0].ports[0].pins.yellow = null,
    c => c.units[1].host_admission = {device_id: 'host-a', port_ids: []}]) {
    const c = catalog(); mutate(c); throws(() => validateUnitAssemblyDraft(c, 'host-a', [root()]), 'assembly_incompatible');
  }
});
await test('offline-picker-uses-catalog-without-granting-execution', async () => {
  const f = await fixture(); await f.panel.addUnit('sensor');
  assert.equal(f.calls.length, 1); assert.equal(f.calls[0].inventory.units[1].runtime.status, 'implemented');
  assert.equal(f.panel.mount.querySelector('optgroup').label, '草稿可连接 · 执行能力另验');
  assert.equal(f.panel.mount.querySelector('.unit-capability').textContent, '连接草稿');
  assert.match(f.panel.note.textContent, /实际执行.*另行确认/); assert.equal(f.changes.at(-1).scope, 'assembly-draft');
  assert.deepEqual(f.panel.attachments(), [root()]); await f.panel.dispose();
});
await test('explorer-add-focus-never-replaces-occupied-unit', async () => {
  const f = await fixture(); await f.panel.addUnit('sensor'); const count = f.changes.length;
  await f.panel.addUnit('sensor'); assert.equal(f.changes.length, count); assert.equal(f.doc.activeElement.value, 'sensor');
  await rejects(f.panel.addUnit('other'), 'assembly_no_compatible_port'); assert.deepEqual(f.panel.attachments(), [root()]);
  await rejects(f.panel.addUnit('missing'), 'assembly_unit_unknown'); await f.panel.dispose();
});
await test('attachments-and-change-receipts-are-independent-copies', async () => {
  const f = await fixture(); await f.panel.addUnit('sensor'); const rows = f.panel.attachments(); rows[0].unit_id = 'other';
  f.changes.at(-1).attachments.length = 0; assert.deepEqual(f.panel.attachments(), [root()]);
  throws(() => f.panel.attachments('host-b'), 'assembly_device_mismatch'); await f.panel.dispose();
});
await test('per-device-draft-restores-on-the-current-picker', async () => {
  const f = await fixture(); await f.panel.addUnit('sensor'); await f.panel.setDevice('host-b'); assert.deepEqual(f.panel.attachments(), []);
  await f.panel.addUnit('other'); await f.panel.setDevice('host-a'); assert.deepEqual(f.panel.attachments(), [root()]);
  assert.equal(f.panel.mount.querySelector('select').value, 'sensor'); await f.panel.dispose();
});
await test('same-shell-hub-children-attach-parent-first-and-detach-child-first', async () => {
  const f = await fixture(), model = shell(); await f.panel.attachShell(model); await f.panel.addUnit('hub');
  await f.panel.addUnit('sensor', {parentId: 'external1'}); assert.deepEqual(model.calls.slice(0, 2), [['attach', 'grove', 'hub'], ['attach', 'grove/grove-1', 'sensor']]);
  await f.panel.attachShell(null); assert.deepEqual(model.calls.slice(-2), [['detach', 'grove/grove-1'], ['detach', 'grove']]); await f.panel.dispose();
});
await test('model-load-errors-propagate-without-changing-configuration', async () => {
  const f = await fixture(); await f.panel.addUnit('sensor');
  await assert.rejects(f.panel.attachShell({attachUnit: async () => { throw Error('load failed'); }}), /load failed/);
  assert.deepEqual(f.panel.attachments(), [root()]); await f.panel.attachShell(null); await f.panel.dispose();
});
await test('locked-config-and-shell-handoff-never-touch-active-unitpanel', async () => {
  const f = await fixture(), model = shell(); await f.panel.attachShell(model); await f.panel.addUnit('sensor'); await f.panel.setLocked(true);
  const previous = clone(model.calls); await rejects(f.panel.addUnit('other'), 'assembly_locked'); await rejects(f.panel.setDevice('host-b'), 'assembly_locked');
  await f.panel.attachShell(model); await f.panel.dispose(); assert.deepEqual(model.calls, previous);
});
await test('inventory-change-is-pending-for-the-entire-running-lock', async () => {
  const f = await fixture(), model = shell(); await f.panel.attachShell(model); await f.panel.addUnit('sensor'); await f.panel.setLocked(true);
  const changed = catalog(); changed.units[1].runtime.status = 'planned'; await f.panel.updateInventory(changed);
  assert.deepEqual(f.panel.attachments(), [root()]); assert.equal(f.panel.snapshot().valid, true);
  await f.panel.setLocked(false); assert.equal(f.panel.snapshot().valid, false);
  throws(() => f.panel.attachments(), 'assembly_incompatible'); await f.panel.dispose();
});
await test('device-switch-during-async-picker-load-cannot-install-old-picker', async () => {
  const gate = deferred(), calls = []; const f = await fixture();
  f.panel.pickerFactory = pickerFactory({gates: [gate], calls});
  const old = f.panel.setDevice('host-b'); await Promise.resolve(); const current = f.panel.setDevice('host-a');
  await current; gate.resolve(); await old; assert.equal(f.panel.deviceId, 'host-a');
  assert.equal(f.panel.picker.attachments('host-a').length, 0); await f.panel.dispose();
});
await test('lock-drains-inflight-model-load-before-runtime-ownership-handoff', async () => {
  const f = await fixture(), gate = deferred(), model = shell(); await f.panel.addUnit('sensor');
  model.attachUnit = async (id, {port}) => { model.calls.push(['attach', port, id]); await gate.promise; return {}; };
  const attaching = f.panel.attachShell(model); await Promise.resolve(); let locked = false;
  const locking = f.panel.setLocked(true).then(() => locked = true); await Promise.resolve(); assert.equal(locked, false);
  gate.resolve(); await Promise.all([attaching, locking]); const calls = clone(model.calls); await f.panel.dispose(); assert.deepEqual(model.calls, calls);
});
await test('shell-replacement-cleans-only-old-draft-owned-ports', async () => {
  const f = await fixture(), first = shell(), second = shell(); await f.panel.addUnit('sensor');
  await f.panel.attachShell(first); await f.panel.attachShell(second);
  assert.deepEqual(first.calls, [['attach', 'grove', 'sensor'], ['detach', 'grove']]); assert.deepEqual(second.calls, [['attach', 'grove', 'sensor']]); await f.panel.dispose();
});
await test('disposed-and-malformed-catalog-fail-without-creating-a-guest', async () => {
  const f = await fixture(); await assert.rejects(f.panel.updateInventory({units: []}), /真实 Unit/);
  await f.panel.dispose(); throws(() => f.panel.attachments(), 'assembly_disposed');
  await rejects(f.panel.addUnit('sensor'), 'assembly_disposed');
});
await test('actual-createUnitPicker-offline-add-restores-creation-only-defaults-and-children', async () => {
  const doc = documentFixture(), previousDocument = globalThis.document, previousOption = globalThis.Option;
  globalThis.document = doc;
  globalThis.Option = class extends Node { constructor(text, value) { super('option', doc); this.textContent = text; this.value = value; } };
  let panel;
  try {
    const c = catalog(); c.units[1].inputs = {enabled: {type: 'boolean', default: true, creation_only: true}};
    c.units[1].runtime.inputs = {enabled: {property: 'enabled', creation_only: true}};
    c.hosts[0].ports[0].admitted_unit_ids = ['hub'];
    panel = await createPublicUnitAssembly(doc.createElement('div'), {deviceId: 'host-a', catalog: c});
    assert.equal(panel.mount.querySelector('select').querySelectorAll('option').find(option => option.value === 'sensor').disabled, true);
    await panel.addUnit('hub'); await panel.addUnit('sensor', {parentId: 'external1'});
    assert.equal(panel.attachments()[1].initial.enabled, true, 'real picker creation default must be retained');
    const control = panel.mount.querySelector('[data-creation-field]'); control.checked = false;
    control.dispatchEvent(new Event('change', {bubbles: true}));
    assert.equal(panel.attachments()[1].initial.enabled, false);
    await panel.setDevice('host-b'); await panel.setDevice('host-a');
    assert.equal(panel.mount.querySelectorAll('select')[1].value, 'sensor');
    assert.equal(panel.mount.querySelectorAll('[data-creation-field]')[0].checked, false);
    assert.ok(panel.mount.querySelectorAll('optgroup').every(group => !group.label.startsWith('可运行')));
    await panel.dispose();
  } finally { await panel?.dispose(); globalThis.document = previousDocument; globalThis.Option = previousOption; }
});
await test('picker-load-failure-is-not-reported-as-a-ready-empty-assembly', async () => {
  await assert.rejects(fixture({pickerFactory: async () => ({loadError: 'catalog unavailable', dispose() {}})}), error => error.code === 'assembly_picker_unavailable');
});
await test('programmatic-picker-events-cannot-edit-a-locked-configuration', async () => {
  const f = await fixture(); await f.panel.addUnit('sensor'); await f.panel.setLocked(true); const changes = f.changes.length;
  const select = f.panel.mount.querySelector('select'); select.value = 'other'; select.dispatchEvent(new Event('change', {bubbles: true}));
  assert.deepEqual(f.panel.attachments(), [root()]); assert.equal(f.changes.length, changes);
  await f.panel.setLocked(false); assert.equal(f.panel.mount.querySelector('select').value, 'sensor'); await f.panel.dispose();
});
console.log(`Public Unit assembly: ${tests.length} host configuration/ownership contracts passed; no browser, HTTP or guest execution.`);
