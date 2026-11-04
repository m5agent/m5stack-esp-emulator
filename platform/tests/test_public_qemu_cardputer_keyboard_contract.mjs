// Host-only negative controls for acceptance, not execution of a guest driver.
import assert from 'node:assert/strict';
import {CARDPUTER_ADV_KEYS,CARDPUTER_ADV_MODEL_QCODE} from '../web/cardputer-adv-keymap.js';
import {CARDPUTER_KEYBOARD_CASES,CARDPUTER_KEYBOARD_CODES,CARDPUTER_KEYBOARD_SOURCE,
  requireCardputerKeyboardObservation} from './public_qemu_cardputer_keyboard_cases.mjs';

assert.equal(CARDPUTER_KEYBOARD_CASES.length,56);
assert.equal(new Set(CARDPUTER_KEYBOARD_CASES.map(row=>row.component)).size,56);
assert.equal(new Set(CARDPUTER_KEYBOARD_CASES.map(row=>`${row.row},${row.col}`)).size,56);
assert.deepEqual(CARDPUTER_KEYBOARD_CASES.map(row=>row.component),CARDPUTER_ADV_KEYS.map(row=>row.component));
assert.ok(CARDPUTER_KEYBOARD_CASES.every(row=>row.qcode===CARDPUTER_ADV_MODEL_QCODE[row.component]));
assert.equal(CARDPUTER_KEYBOARD_CASES.find(row=>row.physical==='TAB').keycode,43);
assert.equal(CARDPUTER_KEYBOARD_CASES.find(row=>row.physical==='RET').keycode,10);
assert.equal(CARDPUTER_KEYBOARD_CODES.length,57);
assert.equal(Object.keys(CARDPUTER_KEYBOARD_SOURCE.files).length,4);
assert.ok(Object.values(CARDPUTER_KEYBOARD_SOURCE.files).every(value=>/^[a-f0-9]{64}$/.test(value)));
const item=CARDPUTER_KEYBOARD_CASES.find(row=>row.physical==='A');
const positive=[
  {seq:11,kind:'callback',codes:[97]},
  {seq:12,kind:'state',code:97,pressed:true},
  {seq:13,kind:'state',code:97,pressed:false},
];
assert.equal(requireCardputerKeyboardObservation({item,afterSeq:10,events:positive})[0].code,97);
const reject=(events,afterSeq=10)=>assert.throws(()=>requireCardputerKeyboardObservation({item,afterSeq,events}));
reject([]); // model/controller acknowledgement cannot replace a guest event
reject(positive.slice(1)); // state edges without original callback
reject(positive.slice(0,2)); // missing release
reject(positive.filter(row=>row.seq!==12)); // release without press
reject(positive,13); // previous trial's event cannot pass the next trial
reject(positive.map(row=>({...row,...(row.kind==='callback'?{codes:[98]}:{code:98})}))); // wrong key
reject([...positive,{seq:14,kind:'state',code:129,pressed:true}]); // unexpected modifier
const fn=CARDPUTER_KEYBOARD_CASES.find(row=>row.physical==='COMPOSE');
assert.deepEqual(fn.expectedCodes,[0,27]);assert.equal(fn.companion,'GRAVE_ACCENT');
const chord=[
  {seq:11,kind:'callback',codes:[0]},
  {seq:12,kind:'state',code:0,pressed:true},
  {seq:13,kind:'callback',codes:[27]},
  {seq:14,kind:'state',code:27,pressed:true},
  {seq:15,kind:'state',code:27,pressed:false},
  {seq:16,kind:'state',code:0,pressed:false},
];
assert.equal(requireCardputerKeyboardObservation({item:fn,afterSeq:10,events:chord}).length,2);
assert.throws(()=>requireCardputerKeyboardObservation({item:fn,afterSeq:10,events:chord.filter(row=>row.code!==27&&!row.codes?.includes(27))}));
assert.throws(()=>requireCardputerKeyboardObservation({item:fn,afterSeq:10,events:chord.filter(row=>row.seq!==16)}));
console.log('Cardputer keyboard host acceptance controls passed; guest NOT RUN');
