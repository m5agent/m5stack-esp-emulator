// Offline semantic controls against the actual annotation function and Panel.
// No browser, Three runtime, network, firmware or QEMU is started.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const sourceRoot = resolve(process.argv[2] || root);
const output = process.argv[3];
const annotationSource = await readFile(resolve(sourceRoot, 'platform/web/unit-annotations.js'), 'utf8');
const panelSource = await readFile(resolve(sourceRoot, 'platform/web/unit-panel.js'), 'utf8');
const mappingSource = await readFile(resolve(sourceRoot, 'platform/web/unit-visual-mappings.js'), 'utf8');
const {arrayLedFeedback} = await import(pathToFileURL(resolve(sourceRoot, 'platform/web/unit-visual-mappings.js')).href);
const modelSource = await readFile(resolve(sourceRoot, 'platform/web/model-shell.js'), 'utf8');
const catalog = JSON.parse(await readFile(resolve(root, 'platform/units/catalog.json'), 'utf8'));
const catalogUnit = id => structuredClone(catalog.units.find(unit => unit.id === id));
const annotationBody = annotationSource.replace(/^import[^\n]*\n/gm, '').replace(/^export /gm, '');
const {annotationReadback, UnitAnnotations} = new Function(
  `${annotationBody}\nreturn {annotationReadback, UnitAnnotations};`,
)();
const panelClass = panelSource.slice(panelSource.indexOf('class UnitPanel {'),
  panelSource.indexOf('\nexport async function createUnitPanel'));
const summaryHelpers = panelSource.slice(panelSource.indexOf('function readoutSource('),
  panelSource.indexOf('\nfunction observedValue('));
const valueFormatter = panelSource.match(/^const text = .*$/m)[0];

function node() {
  return {dataset: {}, textContent: '', children: [], append(...children) {this.children.push(...children);},
    replaceChildren(...children) {this.children = children;}, querySelectorAll() {return [];}};
}
const Panel = new Function('window', 'document', 'copy', 'ACTIVE', 'clearTimeout', 'setTimeout',
  'visualCommands', 'element', 'observedValue', 'arrayLedFeedback', `${valueFormatter}\n${summaryHelpers}\n${panelClass}\nreturn UnitPanel;`)(
  {addEventListener() {}, removeEventListener() {}}, {hidden: false}, structuredClone,
  new Set(['booting', 'running']), () => {}, () => 1, () => [], () => node(), () => node(), arrayLedFeedback,
);
const frozen = {running: true, source: 'live', frozenDefinitions: true};
const env = catalogUnit('env-iii');
const state = (unitId = 'env-iii', properties = {'temperature-c': 18.75, 'humidity-pct': 45.5, 'pressure-pa': 103200}) => ({
  id: 'u', unit_id: unitId, source: 'guest-qom', available: true, errors: {}, properties,
});
const rows = result => result?.groups.flatMap(group => group.rows) || [];
const read = (unit = state(), definition = env, options = frozen) => annotationReadback(unit, definition, options);
const field = (result, name) => rows(result).find(row => row.field === name);
const cases = [];
async function test(name, run) {
  try {await run(); cases.push({name, status: 'PASS'});}
  catch (error) {cases.push({name, status: 'FAIL', error: error.stack});}
}

function panelFixture({unitId = 'env-iii', annotationThrows = false, lostReleases = 0,
  payloadDefinitions = true, inventoryDefinition = catalogUnit(unitId)} = {}) {
  let guest = unitId === 'button' ? {pressed: false} : structuredClone(state().properties);
  let failures = lostReleases;
  const definition = catalogUnit(unitId), posts = [], notes = [], annotations = [], visuals = [];
  const attachment = {id: 'u', unit_id: unitId, port_id: 'port-a', visual_port: 'grove'};
  const payload = () => ({session_id: 'offline-annotation-contract', state: 'running', source: 'live',
    units: [{...attachment, ...state(unitId, structuredClone(guest))}],
    ...(payloadDefinitions ? {definitions: [structuredClone(definition)]} : {})});
  const api = async (path, options) => {
    if (options?.method === 'POST') {
      const values = JSON.parse(options.body).values;
      posts.push(structuredClone(values));
      if (unitId === 'button' && guest.pressed && values.pressed === false && failures > 0) {
        failures--;
        throw Error('injected release transport failure');
      }
      guest = {...guest, ...structuredClone(values)};
      return payload();
    }
    return path.includes('/sessions/') ? payload() : {units: [inventoryDefinition], hosts: []};
  };
  const shell = {
    updateUnitAnnotation(unit, options) {
      if (annotationThrows) throw Error('injected optional annotation layout failure');
      annotations.push(annotationReadback(unit, options.definition, options));
    },
    applyVisualState(commands) {visuals.push(commands);}, detachUnit() {},
  };
  const panel = new Panel({replaceChildren() {}}, {session: {session_id: 'offline-annotation-contract',
    device_id: 'cores3', state: 'running', units: [attachment]}, shell, api});
  const card = node(), values = node();
  card.querySelector = () => values;
  panel.cards.set('u', card);
  panel.definitions.set(unitId, definition);
  panel.frozenDefinitions = true;
  panel.stateSource = 'live';
  panel.states.set('u', payload().units[0]);
  panel.mounted.set('u', {shell, port: 'grove'});
  panel.note = (id, message) => notes.push(message);
  panel.render = () => {};
  panel.setShell = async () => {};
  panel.schedule = () => {};
  return {panel, posts, notes, annotations, visuals, definition, payload,
    get guest() {return guest;},
    hold(pressed) {panel.setHeld('u', 'pressed', undefined, 'form:pointer:1', pressed);},
    async drain() {
      for (let attempt = 0; attempt < 5; attempt++) {
        const queue = panel.queues.get('u');
        await queue;
        if (queue === panel.queues.get('u')) return;
      }
      throw Error('unexpected input queue churn');
    }};
}

await test('present-readback-keeps-frozen-label-direction-unit-and-value', () => {
  const definition = structuredClone(env);
  definition.inputs['temperature-c'].label = 'Frozen temperature';
  const result = read(state(), definition);
  assert.equal(result.groups.find(group => group.rows.some(row => row.field === 'temperature-c')).label, '模拟输入');
  assert.deepEqual(field(result, 'temperature-c'), {field: 'temperature-c', label: 'Frozen temperature', value: '18.75', unit: '°C'});
  assert.equal(field(result, 'pressure-pa').value, '103200');
  assert.equal(field(result, 'pressure-pa').unit, 'Pa');
});
await test('missing-properties-never-fill-schema-defaults', () => {
  const definition = structuredClone(env);
  definition.inputs['temperature-c'].default = 777;
  assert.deepEqual(rows(read(state('env-iii', {}), definition)), []);
  assert.deepEqual(rows(read({...state(), properties: undefined}, definition)), []);
});
await test('nonfinite-wrong-type-and-fractional-integer-values-are-rejected', () => {
  for (const value of [NaN, Infinity, -Infinity, true, '18.75', null, undefined]) {
    assert.equal(field(read(state('env-iii', {'temperature-c': value})), 'temperature-c'), undefined);
  }
  assert.deepEqual(rows(read(state('heart', {'ir-sample': 1.25}), catalogUnit('heart'))), []);
});
await test('schema-boundaries-reject-values-without-clamping-or-mutating', () => {
  for (const value of [-0.01, 100.01]) {
    const unit = state('env-iii', Object.freeze({'humidity-pct': value}));
    assert.equal(field(read(unit), 'humidity-pct'), undefined);
    assert.equal(unit.properties['humidity-pct'], value);
  }
  assert.equal(field(read(state('env-iii', {'humidity-pct': 0})), 'humidity-pct').value, '0');
  assert.equal(field(read(state('env-iii', {'humidity-pct': 100})), 'humidity-pct').value, '100');
});
await test('schema-enum-is-not-treated-as-an-unrestricted-scalar', () => {
  const definition = structuredClone(env);
  definition.inputs['temperature-c'].enum = [18.75, 20];
  assert.equal(field(read(state('env-iii', {'temperature-c': 19}), definition), 'temperature-c'), undefined);
  assert.equal(field(read(state(), definition), 'temperature-c').value, '18.75');
});
await test('outer-and-unit-source-must-both-be-live-controller-readback', () => {
  for (const source of ['persisted', 'unavailable', 'synthetic', undefined]) {
    assert.deepEqual(rows(read(state(), env, {...frozen, source})), []);
    assert.deepEqual(rows(read({...state(), source})), []);
  }
});
await test('unavailable-errors-terminal-and-unfrozen-contracts-hide-values', () => {
  for (const unit of [{...state(), available: false}, {...state(), errors: {qom: 'failed'}}]) assert.deepEqual(rows(read(unit)), []);
  assert.deepEqual(rows(read(state(), env, {...frozen, running: false})), []);
  for (const frozenDefinitions of [false, undefined]) assert.deepEqual(rows(read(state(), env, {...frozen, frozenDefinitions})), []);
  assert.deepEqual(rows(read(state(), {...env, id: 'different-unit'})), []);
  assert.equal(read(state('button', {pressed: true}), catalogUnit('button')), null);
});
await test('thermal-readiness-and-control-register-have-explicit-origin-labels', () => {
  const result = read(state('thermal', {'control-word': 6400, 'raw-fixture-ready': true}), catalogUnit('thermal'));
  const group = name => result.groups.find(item => item.rows.some(row => row.field === name));
  assert.equal(group('control-word').label, '控制寄存器状态');
  assert.equal(group('raw-fixture-ready').label, '模型状态');
  assert.ok(result.groups.every(item => !item.label.includes('固件输出')));
});
await test('relay-and-buzzer-use-firmware-observation-without-physical-inference', () => {
  const relay = read(state('relay', {'output-level': false}), catalogUnit('relay'));
  assert.equal(relay.groups[0].label, '固件输出');
  assert.equal(field(relay, 'output-level').value, 'false');
  const buzzer = read(state('buzzer', {'frequency-hz': 440, 'duty-pct': 50}), catalogUnit('buzzer'));
  assert.ok(buzzer.groups.every(group => group.label === '固件输出'));
  assert.equal(field(buzzer, 'frequency-hz').unit, 'Hz');
  assert.equal(field(buzzer, 'duty-pct').unit, '%');
});
await test('model-shell-adapter-preserves-the-frozen-definition-and-source-guards', () => {
  const method = modelSource.slice(modelSource.indexOf('  updateUnitAnnotation('),
    modelSource.indexOf('\n  clearDriveActivities('));
  assert.ok(method.includes('updateUnitAnnotation'), 'actual shell adapter is missing');
  const Shell = new Function(`return class {${method}}`)();
  const shell = new Shell(), calls = [];
  shell.unitAnnotations = {set(...args) {calls.push(args);}};
  const unit = state();
  shell.updateUnitAnnotation(unit, {port: 'grove', definition: env, ...frozen});
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'grove');
  assert.equal(calls[0][1], unit);
  assert.equal(calls[0][2], env);
  assert.deepEqual(calls[0][3], frozen);
});
await test('panel-uses-session-definitions-instead-of-mutable-inventory', async () => {
  const inventory = catalogUnit('env-iii');
  inventory.inputs['temperature-c'].unit = 'WRONG INVENTORY UNIT';
  const fixture = panelFixture({inventoryDefinition: inventory});
  await fixture.panel.init();
  fixture.panel.paint(fixture.panel.states.get('u'));
  assert.equal(fixture.panel.frozenDefinitions, true);
  assert.equal(field(fixture.annotations.at(-1), 'temperature-c').unit, '°C');
  fixture.panel.apply({...fixture.payload(), definitions: [inventory]});
  assert.equal(field(fixture.annotations.at(-1), 'temperature-c').unit, '°C');
});
await test('legacy-inventory-fallback-cannot-be-presented-as-frozen-values', async () => {
  const inventory = catalogUnit('env-iii');
  inventory.inputs['temperature-c'].unit = 'MUTABLE INVENTORY UNIT';
  const fixture = panelFixture({payloadDefinitions: false, inventoryDefinition: inventory});
  await fixture.panel.init();
  fixture.panel.paint(fixture.panel.states.get('u'));
  assert.equal(fixture.panel.frozenDefinitions, false);
  assert.deepEqual(rows(fixture.annotations.at(-1)), []);
});
await test('pending-local-input-never-replaces-controller-annotation', () => {
  const fixture = panelFixture();
  fixture.panel.pending.set('u', new Map([['temperature-c', {revision: 1, value: 99}]]));
  fixture.panel.apply(fixture.payload());
  assert.equal(field(fixture.annotations.at(-1), 'temperature-c').value, '18.75');
  assert.equal(fixture.posts.length, 0);
});
await test('persisted-and-terminal-panel-updates-remove-live-values', () => {
  const fixture = panelFixture();
  fixture.panel.apply(fixture.payload());
  assert.ok(rows(fixture.annotations.at(-1)).length);
  fixture.panel.apply({...fixture.payload(), source: 'persisted'});
  assert.deepEqual(rows(fixture.annotations.at(-1)), []);
  fixture.panel.apply(fixture.payload());
  fixture.panel.updateSession({...fixture.panel.session, state: 'stopped'});
  assert.deepEqual(rows(fixture.annotations.at(-1)), []);
});
await test('annotation-fault-does-not-turn-successful-release-ack-into-input-failure', async () => {
  const fixture = panelFixture({unitId: 'button', annotationThrows: true});
  fixture.hold(true); await fixture.drain();
  fixture.hold(false); await fixture.drain();
  assert.deepEqual(fixture.posts, [{pressed: true}, {pressed: false}]);
  assert.equal(fixture.guest.pressed, false);
  assert.equal(fixture.panel.releaseIntents.size, 0);
  assert.equal(fixture.panel.states.get('u').available, true);
  assert.ok(fixture.visuals.length >= 2, 'annotation errors must not suppress the existing visual state path');
  assert.ok(!fixture.notes.some(message => message.startsWith('输入未确认')));
});
await test('annotation-fault-keeps-one-release-retry-and-no-poll-echo', async () => {
  const fixture = panelFixture({unitId: 'button', annotationThrows: true, lostReleases: 1});
  fixture.hold(true); await fixture.drain();
  fixture.hold(false); await fixture.drain();
  assert.equal(fixture.guest.pressed, true);
  await fixture.panel.refresh(); await fixture.drain();
  assert.equal(fixture.guest.pressed, false);
  assert.deepEqual(fixture.posts, [{pressed: true}, {pressed: false}, {pressed: false}]);
  assert.equal(fixture.panel.releaseIntents.size, 0);
  for (let count = 0; count < 3; count++) {await fixture.panel.refresh(); await fixture.drain();}
  assert.equal(fixture.posts.length, 3);
  assert.equal(fixture.notes.filter(message => message.startsWith('输入未确认')).length, 1);
});
await test('nested-clear-preserves-siblings-and-dispose-unsubscribes-once', () => {
  const removed = [], cleanup = [];
  const annotations = Object.create(UnitAnnotations.prototype);
  Object.assign(annotations, {items: new Map(), active() {}, disposed: false,
    offRender() {cleanup.push('render');}, resize: {disconnect() {cleanup.push('resize');}},
    layer: {remove() {cleanup.push('layer');}}, rail: {remove() {cleanup.push('rail');}}});
  for (const port of ['grove/grove-1', 'grove/grove-1/child', 'grove/grove-2']) {
    const item = Object.fromEntries(['marker', 'leader', 'note'].map(name => [name, {remove() {removed.push(`${port}:${name}`);}}]));
    annotations.items.set(port, item);
  }
  annotations.clear('grove/grove-1');
  assert.deepEqual([...annotations.items.keys()], ['grove/grove-2']);
  assert.equal(removed.length, 6);
  annotations.dispose(); annotations.dispose();
  assert.equal(annotations.items.size, 0);
  assert.equal(removed.length, 9);
  assert.deepEqual(cleanup.sort(), ['layer', 'rail', 'render', 'resize']);
});

const report = {schema_version: 1, category: 'offline-unit-annotation-semantic-contract',
  status: cases.every(item => item.status === 'PASS') ? 'PASS' : 'FAIL',
  browser_execution: 'NOT RUN', firmware_execution: 'NOT RUN', hardware_execution: 'NOT RUN',
  source_sha256: Object.fromEntries([
    ['platform/web/unit-annotations.js', annotationSource], ['platform/web/unit-panel.js', panelSource],
    ['platform/web/unit-visual-mappings.js', mappingSource],
    ['platform/web/model-shell.js', modelSource],
  ].map(([path, source]) => [path, createHash('sha256').update(source).digest('hex')])), cases};
if (output) await writeFile(output, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
process.exitCode = report.status === 'PASS' ? 0 : 1;
