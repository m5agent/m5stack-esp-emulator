// Cardputer-ADV exposes a 7x8 TCA8418 matrix to the firmware, while the
// product keyboard is presented as four rows of fourteen logical keys.
// Keep the complete translation here so browser input, model presses and tests
// cannot drift into separate partial mappings.
const PHYSICAL_ROWS = [
  ['GRAVE_ACCENT', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 'MINUS', 'EQUAL', 'BACKSPACE'],
  ['TAB', 'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', 'BRACKET_LEFT', 'BRACKET_RIGHT', 'BACKSLASH'],
  ['COMPOSE', 'SHIFT', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'SEMICOLON', 'APOSTROPHE', 'RET'],
  ['CTRL', 'META_L', 'ALT', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', 'COMMA', 'DOT', 'SLASH', 'SPC'],
];

// These are the model's CAD component suffixes. The upstream model inherited
// several desktop key names, but each index still represents the physical key
// in PHYSICAL_ROWS.
const MODEL_ROWS = [
  ['Escape', 'Digit1', 'Digit2', 'Digit3', 'Digit4', 'Digit5', 'Digit6', 'Digit7', 'Digit8', 'Digit9', 'Digit0', 'Minus', 'Equal', 'Backspace'],
  ['Tab', 'KeyQ', 'KeyW', 'KeyE', 'KeyR', 'KeyT', 'KeyY', 'KeyU', 'KeyI', 'KeyO', 'KeyP', 'BracketLeft', 'BracketRight', 'Backslash'],
  ['Fn', 'CapsLock', 'KeyA', 'KeyS', 'KeyD', 'KeyF', 'KeyG', 'KeyH', 'KeyJ', 'KeyK', 'KeyL', 'Semicolon', 'Quote', 'Enter'],
  ['ControlLeft', 'AltLeft', 'AltRight', 'KeyZ', 'KeyX', 'KeyC', 'KeyV', 'KeyB', 'KeyN', 'KeyM', 'Comma', 'Period', 'Slash', 'Space'],
];

const LEGEND_ROWS = [
  ['`', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '=', 'Backspace'],
  ['Tab', 'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', '[', ']', '\\'],
  ['Fn', 'Shift', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ';', "'", 'Enter'],
  ['Ctrl', 'Opt', 'Alt', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '/', 'Space'],
];

// Standard KeyboardEvent.code values for the keys that have a direct PC
// counterpart. Modifier and navigation aliases are added below.
const BROWSER_ROWS = [
  ['Backquote', 'Digit1', 'Digit2', 'Digit3', 'Digit4', 'Digit5', 'Digit6', 'Digit7', 'Digit8', 'Digit9', 'Digit0', 'Minus', 'Equal', 'Backspace'],
  ['Tab', 'KeyQ', 'KeyW', 'KeyE', 'KeyR', 'KeyT', 'KeyY', 'KeyU', 'KeyI', 'KeyO', 'KeyP', 'BracketLeft', 'BracketRight', 'Backslash'],
  [null, 'ShiftLeft', 'KeyA', 'KeyS', 'KeyD', 'KeyF', 'KeyG', 'KeyH', 'KeyJ', 'KeyK', 'KeyL', 'Semicolon', 'Quote', 'Enter'],
  ['ControlLeft', 'MetaLeft', 'AltLeft', 'KeyZ', 'KeyX', 'KeyC', 'KeyV', 'KeyB', 'KeyN', 'KeyM', 'Comma', 'Period', 'Slash', 'Space'],
];

const assertShape = (rows) => {
  if (rows.length !== 4 || rows.some(row => row.length !== 14))
    throw new Error('Cardputer-ADV keyboard must be four rows of fourteen keys');
};
assertShape(PHYSICAL_ROWS);
assertShape(MODEL_ROWS);
assertShape(LEGEND_ROWS);
assertShape(BROWSER_ROWS);

export const CARDPUTER_ADV_KEYS = Object.freeze(PHYSICAL_ROWS.flatMap((physicalRow, row) =>
  physicalRow.map((physical, col) => Object.freeze({
    row,
    col,
    physical,
    label: LEGEND_ROWS[row][col],
    component: `key-${MODEL_ROWS[row][col]}`,
    browserCode: BROWSER_ROWS[row][col],
    qcode: physical.toLowerCase(),
    nativeRow: Math.floor(col / 2),
    nativeCol: row + (col % 2 ? 4 : 0),
    nativeEvent: Math.floor(col / 2) * 10 + row + (col % 2 ? 4 : 0) + 1,
  }))));

export const CARDPUTER_ADV_MODEL_QCODE = Object.freeze(Object.fromEntries(
  CARDPUTER_ADV_KEYS.map(key => [key.component, key.qcode])));

const physicalKeymap = Object.fromEntries(
  CARDPUTER_ADV_KEYS.filter(key => key.browserCode)
    .map(key => [key.browserCode, key.component]));

// One physical switch can carry a left/right PC alias. Logical QKeyCodes stay
// distinct through CARDPUTER_PC_QCODE while the TCA8418 sees one real switch.
export const CARDPUTER_PC_KEYMAP = Object.freeze({
  ...physicalKeymap,
  Escape: 'key-Escape',
  ShiftRight: 'key-CapsLock',
  ControlRight: 'key-ControlLeft',
  MetaLeft: 'key-AltLeft',
  MetaRight: 'key-AltLeft',
  AltLeft: 'key-AltRight',
  AltRight: 'key-AltRight',
  Delete: 'key-Backspace',
  ArrowUp: 'key-Semicolon',
  ArrowDown: 'key-Period',
  ArrowLeft: 'key-Comma',
  ArrowRight: 'key-Slash',
  // ADV has a physical Shift key, not CapsLock. Do not turn a PC CapsLock
  // press into a Shift event merely because the CAD component inherited that
  // legacy name.
  CapsLock: null,
});

export const CARDPUTER_PC_QCODE = Object.freeze({
  'key:Escape': 'esc',
  'key:Backquote': 'grave_accent',
  'key:ShiftRight': 'shift_r',
  'key:ControlRight': 'ctrl_r',
  'key:MetaRight': 'meta_r',
  'key:AltRight': 'alt_r',
  'key:Delete': 'delete',
  'key:ArrowUp': 'up',
  'key:ArrowDown': 'down',
  'key:ArrowLeft': 'left',
  'key:ArrowRight': 'right',
});

export function cardputerAdvQcode(component, source) {
  const physical = CARDPUTER_ADV_MODEL_QCODE[component];
  if (!physical) return null;
  return CARDPUTER_PC_QCODE[source] ?? physical;
}
