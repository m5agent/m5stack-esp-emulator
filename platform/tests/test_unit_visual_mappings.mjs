// Pure bridge contract. These tests never launch a runtime or execute firmware.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {CARDKB_KEY_IDS, arrayLedFeedback, physicalInput, visualCommands, visualMappingCoverage} from '../web/unit-visual-mappings.js';
import {KEYS as visualKeys} from '../web/vendor/m5stack-models/src/units/cardkb/dimensions.js';
import {spec as relay2Spec} from '../web/vendor/m5stack-models/src/units/2relay/dimensions.js';
import {spec as flashlightSpec} from '../web/vendor/m5stack-models/src/units/flashlight/dimensions.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const catalog = JSON.parse(await readFile(resolve(root, 'platform/units/catalog.json'), 'utf8'));
const keymap = JSON.parse(await readFile(resolve(root, 'platform/units/fixtures/cardkb-keymap.json'), 'utf8'));
const snapshot = (unit_id, properties, extra = {}) => ({unit_id, available: true, properties, errors: {}, ...extra});
const input = (unit_id, id, action, options = {}) => physicalInput({kind: 'button', id: `grove/${id}`, action, source: 'pointer'}, {unit_id}, {port: 'grove', ...options});
const checks = [];

const relay2Binding = JSON.parse(await readFile(resolve(root, 'platform/units/fixtures/2relay-binding.json'), 'utf8'));
assert.equal(relay2Spec.sku, relay2Binding.sku);
for (const channel of relay2Binding.channels) {
  const visual = relay2Spec.channels.find(row => row.number === channel.number);
  assert.equal(visual.led[1], channel.model_spec_led_y);
  assert.equal(channel.visual_led, `led-${channel.number}`);
  assert.equal(channel.wire, channel.number === 1 ? 'white' : 'yellow');
}
for (const a of [false, true]) for (const b of [false, true]) {
  assert.deepEqual(visualCommands(snapshot('2relay', {'output-1-level': a, 'output-2-level': b}), 'grove'), [
    {type: 'led', target: 'grove/led-1', color: 0x247CFF, on: a},
    {type: 'led', target: 'grove/led-2', color: 0x247CFF, on: b},
  ]);
}
const unknownRelay2 = [1, 2].map(channel => ({type: 'led', target: `grove/led-${channel}`, known: false}));
for (const unit of [snapshot('2relay', {}), snapshot('2relay', {'output-1-level': 1, 'output-2-level': 0}),
  snapshot('2relay', {'output-1-level': true, 'output-2-level': false}, {available: false}),
  snapshot('2relay', {'output-1-level': true, 'output-2-level': false}, {errors: {read: 'failed'}})]) {
  assert.deepEqual(visualCommands(unit, 'grove'), unknownRelay2);
}
assert.equal(input('2relay', 'led-1', 'down'), null, 'Indicators are not writable Unit inputs');
checks.push('u131-two-independent-pad-indicators-exact-asset-numbering-and-unknown-withdrawal');

const flashlightState = {'output-known': true, 'pad-synchronized': true, 'gpio-route-supported': true,
  'flash-mode': true, 'en-level': true, active: true, 'flash-level-pct': 100, 'timeout-ms': 220};
const flashlight = (values = {}, extra = {}) => visualCommands(snapshot('flashlight', {...flashlightState, ...values}, extra), 'grove');
const lamp = (on, brightness) => [{type: 'led', target: 'grove/light', color: flashlightSpec.light.color, on, brightness}];
const unknownLamp = [{type: 'led', target: 'grove/light', known: false}];
assert.equal(flashlightSpec.sku, 'U152');
assert.equal(flashlightSpec.light.color, 0xFFFAF0);
for (const pct of [100, 90, 80, 70, 60, 50, 40, 30]) for (const timeout of [220, 1300]) {
  assert.deepEqual(flashlight({'flash-level-pct': pct, 'timeout-ms': timeout}), lamp(true, pct / 100));
  assert.deepEqual(flashlight({active: false, 'flash-level-pct': pct, 'timeout-ms': timeout}), lamp(false, 0), 'controller timeout retains code without retaining light');
}
assert.deepEqual(flashlight({active: false, 'en-level': false, 'flash-level-pct': 0, 'timeout-ms': 0}), lamp(false, 0), 'reset idle has no decoded Flash code');
assert.deepEqual(flashlight({'flash-mode': false, 'flash-level-pct': 0, 'timeout-ms': 0}), lamp(true, 1), 'Torch is a qualitative continuous indicator with zero Flash code/deadline');
assert.deepEqual(flashlight({'flash-mode': false, active: false, 'en-level': false, 'flash-level-pct': 0, 'timeout-ms': 0}), lamp(false, 0));
for (const field of Object.keys(flashlightState)) {
  const properties = {...flashlightState};
  delete properties[field];
  assert.deepEqual(visualCommands(snapshot('flashlight', properties), 'grove'), unknownLamp, `missing ${field} withdraws the old light`);
}
for (const field of ['output-known', 'pad-synchronized', 'gpio-route-supported']) for (const value of [false, 1, 'true', null]) {
  assert.deepEqual(flashlight({[field]: value}), unknownLamp);
}
for (const field of ['flash-mode', 'en-level', 'active']) for (const value of [0, 1, 'true', null]) {
  assert.deepEqual(flashlight({[field]: value}), unknownLamp);
}
for (const pct of [0, 29, 31, 99, 101, 50.5, NaN, Infinity, '100']) assert.deepEqual(flashlight({'flash-level-pct': pct}), unknownLamp);
for (const timeout of [0, 219, 221, 1299, 1301, 220.1, Infinity, '220']) assert.deepEqual(flashlight({'timeout-ms': timeout}), unknownLamp);
for (const values of [
  {'en-level': false},
  {active: false, 'en-level': false},
  {active: false, 'flash-level-pct': 0, 'timeout-ms': 0},
  {'flash-mode': false},
  {'flash-mode': false, active: false, 'flash-level-pct': 0, 'timeout-ms': 0},
]) assert.deepEqual(flashlight(values), unknownLamp, 'inconsistent pad/mode/active/code snapshots never become an off observation');
for (const extra of [{available: false}, {available: undefined}, {errors: {read: 'failed'}}]) assert.deepEqual(flashlight({}, extra), unknownLamp);
assert.deepEqual(flashlight({'output-known': false, brightness: 100, 'duty-pct': 100}), unknownLamp, 'request values and PWM duty cannot override qualification');
assert.deepEqual(flashlight(), lamp(true, 1), 'the converter has no host timer or retained previous code');
assert.equal(input('flashlight', 'mode', 'down', {bindings: {evidence: 'synthetic fixture', switchPositions: {on: 0, off: 1}}}), null, 'S1 detent does not authorize live mode input');
checks.push('u152-qualified-code-and-torch-readback-timing-consistency-and-unknown-withdrawal');

assert.deepEqual(CARDKB_KEY_IDS, keymap.keys.map(key => key.id), 'matrix order must match the official-table fixture');
assert.deepEqual(CARDKB_KEY_IDS, visualKeys.map(key => key.id), 'all 50 visual controls must match the matrix IDs');
checks.push('cardkb-official-fixture-and-visual-key-identity');

for (const unit of ['button', 'key', 'limit', 'encoder', 'scroll']) {
  assert.deepEqual(input(unit, 'press', 'down'), {pressed: true});
  assert.deepEqual(input(unit, 'press', 'up'), {pressed: false});
  assert.deepEqual(input(unit, 'press', 'cancel'), {pressed: false});
  assert.equal(input(unit, 'press', 'click'), null, 'click must not duplicate a down edge');
}
assert.deepEqual(input('dual-button', 'red', 'down'), {'red-pressed': true});
assert.deepEqual(input('dual-button', 'blue', 'up'), {'blue-pressed': false});
assert.equal(physicalInput({kind: 'button', id: 'other/press', action: 'down'}, {unit_id: 'button'}, {port: 'grove'}), null);
assert.equal(physicalInput({kind: 'button', id: 'grove/press', action: 'down', source: 'runtime-readback'}, {unit_id: 'button'}), null);
checks.push('momentary-down-up-cancel-port-and-feedback-isolation');

const keys = Array(50).fill(false);
keys[25] = true;
const keyInput = input('cardkb', 'key-q', 'down', {properties: {keys}});
assert.equal(keyInput.keys[13], true);
assert.equal(keyInput.keys[25], true, 'another held key must survive');
assert.equal(keys[13], false, 'snapshot is immutable');
assert.equal(input('cardkb', 'key-q', 'down'), null, 'missing baseline must fail closed');
assert.equal(input('cardkb', 'key-q', 'down', {properties: {keys: Array(50).fill(0)}}), null);
const channels = [true, false, true, false, false, false, false, false];
assert.deepEqual(input('8encoder', 'press-8', 'down', {properties: {pressed: channels}}), {pressed: [true, false, true, false, false, false, false, true]});
assert.equal(channels[7], false);
assert.equal(input('8encoder', 'press-1', 'down'), null);
checks.push('array-key-and-channel-updates-preserve-authoritative-baseline');

const cardState = snapshot('cardkb', {keys: keyInput.keys, 'led-rgb': 0x123456});
const cardCommands = visualCommands(cardState, 'grove');
assert.equal(cardCommands.length, 51);
assert.deepEqual(cardCommands.find(command => command.target === 'grove/key-q'), {type: 'button-state', target: 'grove/key-q', pressed: true});
assert.deepEqual(cardCommands.at(-1), {type: 'led', target: 'grove/rgb', color: 0x123456, on: true});
assert.equal(visualCommands(snapshot('cardkb', {keycode: 65}), 'grove').length, 0, 'a consumed byte cannot identify a held key');
assert.deepEqual(visualCommands(snapshot('key', {pressed: false, 'led-rgb': 0}), 'grove'), [
  {type: 'button-state', target: 'grove/press', pressed: false},
  {type: 'led', target: 'grove/rgb', color: 0, on: false},
]);
assert.deepEqual(visualCommands(snapshot('button', {pressed: 1}), 'grove'), []);
assert.deepEqual(visualCommands({...cardState, available: false}, 'grove'), []);
assert.deepEqual(visualCommands({...cardState, errors: {keys: 'qmp failed'}}, 'grove'), []);
checks.push('observed-readback-only-strict-types-no-keycode-pose-guess');

const eightState = snapshot('8encoder', {pressed: channels, counters: [1, 2, 3, 4, 5, 6, 7, 8], 'switch-on': true, 'led-rgb': Array(9).fill(0xABCDEF)});
assert.equal(visualCommands(eightState, 'grove').length, 17, 'uniform colors need no index permutation; rotations/switch remain uncalibrated');
for (const [id, properties] of [
  ['angle', {'voltage-mv': 1250}],
  ['joystick-v11', {'x-raw': 255, 'y-raw': 0, 'button-raw': 1}],
  ['relay', {'output-level': true}], ['buzzer', {'frequency-hz': 1000, 'duty-pct': 50}],
]) assert.deepEqual(visualCommands(snapshot(id, properties), 'grove'), [], `${id} must not invent a physical conversion`);
assert.equal(input('joystick-v11', 'press', 'down'), null, 'raw pressed polarity requires evidence');
checks.push('uncalibrated-angle-count-axis-led-switch-and-rpm-fail-closed');

const unknownEncoder = ['led0', 'led1'].map(target => ({type: 'led', target: `grove/${target}`, known: false}));
for (const [unit, targets] of [['rgb', ['led0', 'led1', 'led2']], ['encoder', ['led0', 'led1']], ['8encoder', Array.from({length: 9}, (_, i) => `rgb-${i + 1}`)]]) {
  for (const color of [0, 0x123456, 0xFF0000]) {
    const state = snapshot(unit, {'led-rgb': Array(targets.length).fill(color)});
    assert.equal(arrayLedFeedback(state).mapping, 'uniform');
    assert.deepEqual(visualCommands(state, 'grove'), targets.map(target => ({type: 'led', target: `grove/${target}`, color, on: color !== 0})));
  }
  for (const colors of [[], Array(targets.length - 1).fill(0), Array(targets.length).fill(-1), Array(targets.length).fill(true), new Array(targets.length), [1, ...Array(targets.length - 1).fill(2)]]) {
    assert.deepEqual(visualCommands(snapshot(unit, {'led-rgb': colors}), 'grove'), targets.map(target => ({type: 'led', target: `grove/${target}`, known: false})));
  }
  for (const extra of [{available: false}, {errors: {read: 'failed'}}]) {
    assert.deepEqual(visualCommands(snapshot(unit, {'led-rgb': Array(targets.length).fill(0xFF0000)}, extra), 'grove'), targets.map(target => ({type: 'led', target: `grove/${target}`, known: false})));
  }
}
checks.push('uniform-arrays-permutation-invariant-and-unknown-withdraws-all-targets');

// Synthetic calibration is ONLY a converter fixture, never hardware evidence.
const bindings = {
  evidence: 'synthetic converter fixture, not measured hardware calibration',
  ledTargets: ['led1', 'led0'],
  joints: [{field: 'counter', target: 'rotation', scale: 2, offset: -10}],
};
assert.deepEqual(visualCommands(snapshot('encoder', {counter: 20, 'led-rgb': [0x010203, 0x040506]}), 'grove', {bindings}), [
  {type: 'led', target: 'grove/led1', color: 0x010203, on: true},
  {type: 'led', target: 'grove/led0', color: 0x040506, on: true},
  {type: 'joint', target: 'grove/rotation', angleDeg: 30},
]);
assert.deepEqual(visualCommands(snapshot('encoder', {counter: 20, 'led-rgb': [1, 2]}), 'grove', {bindings: {...bindings, evidence: ''}}), unknownEncoder);
assert.deepEqual(visualCommands(snapshot('encoder', {'led-rgb': [1, 2]}), 'grove', {bindings: {...bindings, ledTargets: ['led0', 'led0']}}), unknownEncoder);
assert.deepEqual(visualCommands(snapshot('encoder', {counter: 20}), 'grove', {bindings: {...bindings, joints: [{field: 'counter', target: 'rotation', scale: 2, offset: 0, maximum: 10}]}}), unknownEncoder);
const activeFan = [{type: 'drive-activity', target: 'grove/rotor', active: true}];
assert.deepEqual(visualCommands(snapshot('fan', {'duty-pct': 100}), 'grove', {bindings: {...bindings, joints: [{field: 'duty-pct', target: 'rotor', scale: 50, offset: 0}]}}), activeFan, 'PWM only enables a qualitative activity command, never a scaled angle or RPM');
for (const state of [snapshot('fan', {'duty-pct': 0}), snapshot('fan', {'duty-pct': Infinity}), snapshot('fan', {'duty-pct': 1}, {available: false})]) {
  assert.deepEqual(visualCommands(state, 'grove'), [{...activeFan[0], active: false}]);
}
assert.deepEqual(visualCommands(snapshot('fan', {'duty-pct': 50}), 'grove', {running: false}), [{...activeFan[0], active: false}]);
const switchBinding = {evidence: 'synthetic switch fixture', switchPositions: {on: 0, off: 1}};
assert.equal(visualCommands(eightState, 'grove', {bindings: switchBinding}).find(command => command.type === 'position').position, 0);
assert.equal(input('8encoder', 'switch', 'up', {bindings: switchBinding}), null);
assert.equal(input('8encoder', 'switch', 'down', {bindings: switchBinding}), null, 'switch needs an actual detent in its event');
assert.deepEqual(physicalInput({kind: 'button', id: 'grove/switch', action: 'down', position: 0}, {unit_id: '8encoder'}, {port: 'grove', bindings: switchBinding}), {'switch-on': true});
const joystickBinding = {evidence: 'synthetic polarity fixture', joystickPressedRaw: 0};
assert.deepEqual(input('joystick-v11', 'press', 'down', {bindings: joystickBinding}), {'button-raw': 0});
assert.deepEqual(input('joystick-v11', 'press', 'up', {bindings: joystickBinding}), {'button-raw': 1});
checks.push('evidence-required-calibration-permutation-range-and-detent-validation');

const report = visualMappingCoverage(catalog);
assert.equal(catalog.units.length, 30);
assert.deepEqual([...report.registered_unit_ids].sort(), catalog.units.map(unit => unit.id).sort());
assert.equal(report.units.some(unit => unit.status === 'unregistered'), false);
for (const unit of catalog.units) {
  const row = report.units.find(row => row.unit_id === unit.id);
  for (const field of [...Object.keys(unit.inputs), ...Object.keys(unit.outputs)]) {
    assert.ok(row.fields.some(row => row.field === field), `${unit.id}.${field} must have an explicit audit result`);
  }
}
assert.equal(report.units.find(unit => unit.unit_id === '8encoder').status, 'requires-binding');
assert.equal(report.units.find(unit => unit.unit_id === 'fan').status, 'activity-only');
assert.equal(report.units.find(unit => unit.unit_id === 'hub').status, 'passive');
checks.push('all-30-products-and-every-catalog-field-audited');
report.checks = checks;
report.status = 'PASS';
report.source_sha256 = Object.fromEntries(await Promise.all([
  'platform/web/unit-visual-mappings.js', 'platform/tests/test_unit_visual_mappings.mjs',
  'platform/units/catalog.json', 'platform/units/fixtures/cardkb-keymap.json',
  'platform/web/vendor/m5stack-models/src/units/cardkb/dimensions.js',
  'platform/web/vendor/m5stack-models/src/units/flashlight/dimensions.js',
].map(async path => [path, createHash('sha256').update(await readFile(resolve(root, path))).digest('hex')])));
report.summary = Object.fromEntries(['mapped', 'requires-binding', 'activity-only', 'panel-only', 'passive'].map(status => [status, report.units.filter(unit => unit.status === status).length]));
const reportAt = process.argv.indexOf('--report');
if (reportAt >= 0) {
  assert.ok(process.argv[reportAt + 1], '--report requires a path');
  const output = resolve(process.argv[reportAt + 1]);
  await mkdir(dirname(output), {recursive: true});
  await writeFile(output, JSON.stringify(report, null, 2) + '\n');
}
console.log(`UNIT_VISUAL_MAPPING_OK ${JSON.stringify(report.summary)}`);
