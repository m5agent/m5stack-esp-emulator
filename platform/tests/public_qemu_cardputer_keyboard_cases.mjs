// Independent original-driver ASCII oracle; no values are read from the guest
// to construct expectations. The model table supplies physical routes only.
import assert from 'node:assert/strict';
import {CARDPUTER_ADV_KEYS} from '../web/cardputer-adv-keymap.js';

export const CARDPUTER_KEYBOARD_SOURCE = Object.freeze({
  repository:'https://github.com/m5stack/uiflow-micropython',
  commit:'50e440780492aa847378c7d3477ab912f7063bac',
  files:{
    'm5stack/libs/hardware/matrix_keyboard.py':'3d62f15337c5be53b32228f007fbbac94cdd6df88f2a1ecd7a6b56e5d39e5172',
    'm5stack/libs/hardware/keyboard/__init__.py':'ca22657f704da629e9659ba50b769f169af077aca16d9dae1c94b269ae85fd33',
    'm5stack/libs/hardware/keyboard/asciimap.py':'8da6502d5e16b8f82c99984ef6499b32c89a2ffa6047811f079d1c64919b893b',
    'm5stack/libs/driver/tca8418.py':'2e875c9c2951aeb0df0f3eab87fa6c91e514b689499c8da10cc0d5b7645086d6',
  },
});

// KeyEvent / _key_value_map / asciimap, not desktop ASCII conventions.
// In this driver Tab is 43 and Enter is 10. Fn's standalone code is 0 due
// to KeyEvent.convert's (0,2) exemption; only the public Fn+grave -> ESC
// behavior establishes its function here. Code 0 by itself is insufficient.
const codes = [
  [96,49,50,51,52,53,54,55,56,57,48,45,61,8],
  [43,113,119,101,114,116,121,117,105,111,112,91,93,92],
  [0,129,97,115,100,102,103,104,106,107,108,59,39,10],
  [128,254,130,122,120,99,118,98,110,109,44,46,47,32],
];
export const CARDPUTER_KEYBOARD_CASES = Object.freeze(CARDPUTER_ADV_KEYS.map(key => Object.freeze({
  ...key, keycode:codes[key.row][key.col],
  expectedCodes:Object.freeze(key.physical==='COMPOSE'?[0,27]:[codes[key.row][key.col]]),
  companion:key.physical==='COMPOSE'?'GRAVE_ACCENT':null,
})));
export const CARDPUTER_KEYBOARD_CODES = Object.freeze([...new Set(CARDPUTER_KEYBOARD_CASES.flatMap(key=>key.expectedCodes))]);

// Host evidence evaluator. It never injects data or supplies a driver event.
export function requireCardputerKeyboardObservation({item,afterSeq,events}) {
  const rows=events.filter(row=>row.seq>afterSeq);
  const observations=item.expectedCodes.map(code=>{
    const callback=rows.find(row=>row.kind==='callback'&&row.codes.includes(code));
    const pressed=rows.find(row=>row.kind==='state'&&row.code===code&&row.pressed===true);
    const released=rows.find(row=>row.kind==='state'&&row.code===code&&row.pressed===false&&row.seq>pressed?.seq);
    assert.ok(callback,`${item.physical}: missing original public callback/get_key code ${code}`);
    assert.ok(pressed,`${item.physical}: missing public is_key_pressed(${code}) press`);
    assert.ok(released,`${item.physical}: missing public is_key_pressed(${code}) release`);
    return {code,callback,pressed,released};
  });
  const allowed=new Set(item.expectedCodes);
  assert.ok(rows.filter(row=>row.kind==='callback').every(row=>row.codes.every(code=>allowed.has(code))),
    `${item.physical}: unrelated or incorrectly modified callback code`);
  assert.ok(rows.filter(row=>row.kind==='state'&&row.pressed).every(row=>allowed.has(row.code)),
    `${item.physical}: unexpected key remains pressed`);
  return observations;
}
