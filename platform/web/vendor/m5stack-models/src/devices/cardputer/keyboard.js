import {cadButton} from '../../modeling/actuators.js';
import {DIM} from './dimensions.js';

// Physical row order, viewed from the front. Browser aliases for Fn and OPT
// are added below, leaving a single model control per switch.
export const KEYS = [
  [['Backquote', '`'], ['Digit1', '1'], ['Digit2', '2'], ['Digit3', '3'], ['Digit4', '4'], ['Digit5', '5'], ['Digit6', '6'], ['Digit7', '7'], ['Digit8', '8'], ['Digit9', '9'], ['Digit0', '0'], ['Minus', '-'], ['Equal', '='], ['Backspace', 'Backspace']],
  [['Tab', 'Tab'], ['KeyQ', 'Q'], ['KeyW', 'W'], ['KeyE', 'E'], ['KeyR', 'R'], ['KeyT', 'T'], ['KeyY', 'Y'], ['KeyU', 'U'], ['KeyI', 'I'], ['KeyO', 'O'], ['KeyP', 'P'], ['BracketLeft', '['], ['BracketRight', ']'], ['Backslash', '\\']],
  [['Fn', 'Fn'], ['ShiftLeft', 'Aa / Shift'], ['KeyA', 'A'], ['KeyS', 'S'], ['KeyD', 'D'], ['KeyF', 'F'], ['KeyG', 'G'], ['KeyH', 'H'], ['KeyJ', 'J'], ['KeyK', 'K'], ['KeyL', 'L'], ['Semicolon', ';'], ['Quote', "'"], ['Enter', 'Enter']],
  [['ControlLeft', 'Ctrl'], ['AltRight', 'Opt'], ['AltLeft', 'Alt'], ['KeyZ', 'Z'], ['KeyX', 'X'], ['KeyC', 'C'], ['KeyV', 'V'], ['KeyB', 'B'], ['KeyN', 'N'], ['KeyM', 'M'], ['Comma', ','], ['Period', '.'], ['Slash', '/'], ['Space', 'Space']],
];

export const KEYMAP = {
  ...Object.fromEntries(KEYS.flat().map(([code]) => [code, `key-${code}`])),
  Escape: 'key-Backquote',
  ShiftRight: 'key-ShiftLeft',
  ControlRight: 'key-ControlLeft',
};

export const MATRIX = {
  decoderGpio: [8, 9, 11], // A0, A1, A2
  senseGpio: [13, 15, 3, 4, 5, 6, 7],
  senseActiveLow: true,
};

export function addKeyboard(host, membrane) {
  const {x0, dx, dy, z} = DIM.keyboard;
  KEYS.forEach((row, r) => row.forEach(([code, label], c) => {
    const address = 3 - r + (c % 2 === 0 ? 4 : 0);
    cadButton(host, {
      source: membrane,
      id: `key-${code}`,
      label,
      position: [x0 + c * dx, -r * dy, z],
      w: 5.4, h: 3.55, r: 0.7, depth: 1.7, travel: 0.25,
      meta: {
        role: 'keyboard-key',
        matrix: [r, c],
        scan: {decoderAddress: address, senseGpio: MATRIX.senseGpio[Math.floor(c / 2)]},
      },
    });
  }));
}
