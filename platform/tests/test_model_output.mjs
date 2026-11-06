import assert from 'node:assert/strict';
import {setModelImage, applyModelVisualState, clearModelDriveActivities} from '../web/model-output.js';

// Host contracts for output-only semantics; these are not guest evidence.
const events = [];
function led(id, {fixed = false} = {}) {
  return {id, path: id, fixedColor: fixed ? 0x247cff : undefined, meta: {}, object3d: {userData: {}},
    color: {clone: () => ({r: 0, g: 0, b: 0, set(value) { if (value === 'invalid') return; this.r = this.g = this.b = 1; }})},
    set(value) { events.push(['led', id, value]); return value; }};
}
const rgb = led('rgb'), blue = led('blue', {fixed: true});
let originalTicks = 0;
const rotor = {continuous: true, object3d: {userData: {}}, runtimeKnown: true,
  update() { originalTicks++; return false; }, getState: () => ({angleDeg: 24}),
  setAngle(value) { events.push(['angle', value]); }, requestRender() { events.push(['render']); }};
const button = {latching: false, press: source => events.push(['press', source]),
  cancel: source => events.push(['cancel', source]), getState: () => ({pressed: true})};
const components = new Map([['rgb', rgb], ['blue', blue], ['grove/rotor', rotor], ['button', button]]);
const surface = {disposed: false, feedbackDepth: 0, driveActivities: new Map(), model: {
  find: id => components.get(id), button: id => components.get(id),
  handle(command) { events.push(['handle', command]); return command; },
}};

applyModelVisualState(surface, [{type: 'led', target: 'rgb', known: false}, {type: 'led', target: 'blue', known: false}]);
assert.deepEqual(events.slice(0, 2), [['led', 'rgb', {color: 0, brightness: 0}], ['led', 'blue', {brightness: 0}]]);
assert.equal(rgb.runtimeKnown, false); assert.equal(blue.object3d.userData.runtimeKnown, false);
applyModelVisualState(surface, {type: 'led', target: 'rgb', color: 0xff0088});
assert.equal(rgb.runtimeKnown, true);
assert.throws(() => applyModelVisualState(surface, {type: 'led', target: 'rgb', color: 'invalid'}), /invalid/);
assert.throws(() => applyModelVisualState(surface, {type: 'tone', target: 'speaker'}), /output-only/);
assert.equal(surface.feedbackDepth, 0, 'errors must release the input-echo suppression depth');

applyModelVisualState(surface, {type: 'joint', target: 'grove/rotor', known: false});
assert.equal(rotor.runtimeKnown, false);
assert.ok(!events.some(([type, command]) => type === 'handle' && command.type === 'joint'), 'unknown pose must not command home');
applyModelVisualState(surface, {type: 'button-state', target: 'button', pressed: true});
applyModelVisualState(surface, {type: 'button-state', target: 'button', pressed: false});
assert.deepEqual(events.slice(-2), [['press', 'runtime-readback'], ['cancel', 'runtime-readback']]);
const originalUpdate = rotor.update;
const result = applyModelVisualState(surface, {type: 'drive-activity', target: 'grove/rotor', active: true});
assert.equal(result[0].semantics, 'drive-activity-only; shaft-speed-unmodeled');
rotor.update(0.1); assert.ok(events.some(([type]) => type === 'angle'));
applyModelVisualState(surface, {type: 'drive-activity', target: 'grove/rotor', active: false});
rotor.update(0.1); assert.equal(originalTicks, 1);
clearModelDriveActivities(surface, 'grove'); assert.equal(rotor.update, originalUpdate); assert.equal(surface.driveActivities.size, 0);

const draw = [], context = Object.fromEntries(['clearRect', 'save', 'translate', 'rotate', 'drawImage', 'restore']
  .map(method => [method, (...args) => draw.push([method, ...args])]));
surface.display = {width: 135, height: 240, meta: {nativeRasterRotation: 90}, getContext2D: () => context,
  present: () => draw.push(['present'])};
surface.frameSeq = 0; surface.showOverlay = (...args) => draw.push(['overlay', ...args]); surface.hideOverlay = () => draw.push(['hide']);
let bitmapClosed = 0;
globalThis.createImageBitmap = async image => ({...image, close: () => bitmapClosed++});
assert.equal(await setModelImage(surface, {width: 240, height: 135}, 7), true);
assert.equal(surface.frameSeq, 7); assert.equal(bitmapClosed, 1);
assert.ok(draw.some(([type, x, y]) => type === 'translate' && x === 135 && y === 0));
assert.ok(draw.some(([type, value]) => type === 'rotate' && value === Math.PI / 2));
assert.equal(await setModelImage(surface, {width: 1, height: 1}, 8), false);
assert.equal(surface.frameSeq, 7); assert.equal(bitmapClosed, 2);
let resolveBitmap;
globalThis.createImageBitmap = () => new Promise(resolve => { resolveBitmap = resolve; });
let valid = true;
const stale = setModelImage(surface, {}, 9, () => valid); valid = false;
resolveBitmap({width: 135, height: 240, close: () => bitmapClosed++});
assert.equal(await stale, false); assert.equal(bitmapClosed, 3); assert.equal(surface.frameSeq, 7);
surface.disposed = true; assert.deepEqual(applyModelVisualState(surface, {type: 'tone'}), []);
assert.equal(await setModelImage(surface, {}, 10), false);
console.log('model-output contracts passed');
