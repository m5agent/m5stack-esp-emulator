import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {
  CARDPUTER_ADV_KEYS,
  CARDPUTER_ADV_MODEL_QCODE,
  CARDPUTER_PC_KEYMAP,
  CARDPUTER_PC_QCODE,
  cardputerAdvQcode,
} from '../web/cardputer-adv-keymap.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const fixture = JSON.parse(await readFile(
  resolve(root, 'platform/tests/fixtures/cardputer_qkeycode_40edccac.json'), 'utf8'));

assert.equal(CARDPUTER_ADV_KEYS.length, 56);
assert.deepEqual(
  CARDPUTER_ADV_KEYS.map(key => key.physical),
  fixture.physical_rows.flat(),
  'canonical keys must follow the pinned UIFlow 4x14 matrix');
assert.equal(
  new Set(CARDPUTER_ADV_KEYS.map(key => `${key.row},${key.col}`)).size,
  56,
  'logical 4x14 positions must be unique');
assert.equal(
  new Set(CARDPUTER_ADV_KEYS.map(key => `${key.nativeRow},${key.nativeCol}`)).size,
  56,
  'native TCA8418 7x8 positions must be unique');
for (const key of CARDPUTER_ADV_KEYS) {
  assert.equal(key.component, `key-${[
    ['Escape', 'Digit1', 'Digit2', 'Digit3', 'Digit4', 'Digit5', 'Digit6', 'Digit7', 'Digit8', 'Digit9', 'Digit0', 'Minus', 'Equal', 'Backspace'],
    ['Tab', 'KeyQ', 'KeyW', 'KeyE', 'KeyR', 'KeyT', 'KeyY', 'KeyU', 'KeyI', 'KeyO', 'KeyP', 'BracketLeft', 'BracketRight', 'Backslash'],
    ['Fn', 'CapsLock', 'KeyA', 'KeyS', 'KeyD', 'KeyF', 'KeyG', 'KeyH', 'KeyJ', 'KeyK', 'KeyL', 'Semicolon', 'Quote', 'Enter'],
    ['ControlLeft', 'AltLeft', 'AltRight', 'KeyZ', 'KeyX', 'KeyC', 'KeyV', 'KeyB', 'KeyN', 'KeyM', 'Comma', 'Period', 'Slash', 'Space'],
  ][key.row][key.col]}`);
  assert.equal(key.qcode, key.physical.toLowerCase());
  assert.equal(key.nativeRow, Math.floor(key.col / 2));
  assert.equal(key.nativeCol, key.row + (key.col % 2 ? 4 : 0));
}

assert.equal(CARDPUTER_ADV_MODEL_QCODE['key-Escape'], 'grave_accent');
assert.equal(CARDPUTER_ADV_MODEL_QCODE['key-CapsLock'], 'shift');
assert.equal(CARDPUTER_ADV_MODEL_QCODE['key-AltLeft'], 'meta_l');
assert.equal(CARDPUTER_ADV_MODEL_QCODE['key-AltRight'], 'alt');
assert.equal(CARDPUTER_ADV_MODEL_QCODE['key-Quote'], 'apostrophe');
assert.equal(CARDPUTER_ADV_MODEL_QCODE['key-Period'], 'dot');
assert.deepEqual(
  Object.fromEntries(['key-Escape', 'key-CapsLock', 'key-AltLeft', 'key-AltRight', 'key-Quote', 'key-Period']
    .map(component => [component, CARDPUTER_ADV_KEYS.find(key => key.component === component).label])),
  {
    'key-Escape': '`',
    'key-CapsLock': 'Shift',
    'key-AltLeft': 'Opt',
    'key-AltRight': 'Alt',
    'key-Quote': "'",
    'key-Period': '.',
  },
);

assert.equal(CARDPUTER_PC_KEYMAP.MetaLeft, 'key-AltLeft');
assert.equal(CARDPUTER_PC_KEYMAP.MetaRight, 'key-AltLeft');
assert.equal(CARDPUTER_PC_KEYMAP.AltLeft, 'key-AltRight');
assert.equal(CARDPUTER_PC_KEYMAP.ControlRight, 'key-ControlLeft');
assert.equal(CARDPUTER_PC_KEYMAP.ShiftRight, 'key-CapsLock');
assert.equal(CARDPUTER_PC_KEYMAP.Delete, 'key-Backspace');
assert.equal(CARDPUTER_PC_KEYMAP.ArrowUp, 'key-Semicolon');
assert.equal(CARDPUTER_PC_KEYMAP.ArrowDown, 'key-Period');
assert.equal(CARDPUTER_PC_KEYMAP.ArrowLeft, 'key-Comma');
assert.equal(CARDPUTER_PC_KEYMAP.ArrowRight, 'key-Slash');
assert.equal(CARDPUTER_PC_KEYMAP.Backquote, 'key-Escape');
assert.equal(CARDPUTER_PC_KEYMAP.Escape, 'key-Escape');
assert.ok(Object.hasOwn(CARDPUTER_PC_KEYMAP, 'CapsLock'));
assert.equal(CARDPUTER_PC_KEYMAP.CapsLock, null);

assert.equal(cardputerAdvQcode('key-Escape', 'pointer:probe'), 'grave_accent');
assert.equal(cardputerAdvQcode('key-Escape', 'key:Escape'), 'esc');
assert.equal(cardputerAdvQcode('key-Escape', 'key:Backquote'), 'grave_accent');
assert.equal(cardputerAdvQcode('key-CapsLock', 'key:ShiftRight'), 'shift_r');
assert.equal(cardputerAdvQcode('key-ControlLeft', 'key:ControlRight'), 'ctrl_r');
assert.equal(cardputerAdvQcode('key-AltLeft', 'key:MetaRight'), 'meta_r');
assert.equal(cardputerAdvQcode('key-AltRight', 'key:AltRight'), 'alt_r');
for (const [source, qcode] of [
  ['key:Delete', 'delete'],
  ['key:ArrowUp', 'up'],
  ['key:ArrowDown', 'down'],
  ['key:ArrowLeft', 'left'],
  ['key:ArrowRight', 'right'],
]) assert.equal(CARDPUTER_PC_QCODE[source], qcode);
assert.equal(cardputerAdvQcode('key-Semicolon', 'key:ArrowUp'), 'up');
assert.equal(cardputerAdvQcode('key-Period', 'key:ArrowDown'), 'down');
assert.equal(cardputerAdvQcode('key-Comma', 'key:ArrowLeft'), 'left');
assert.equal(cardputerAdvQcode('key-Slash', 'key:ArrowRight'), 'right');

console.log('Cardputer-ADV 56-key canonical matrix, native positions and PC aliases passed');
