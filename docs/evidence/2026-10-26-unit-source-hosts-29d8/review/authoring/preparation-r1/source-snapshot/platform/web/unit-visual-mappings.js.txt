// Pure controller-state <-> visual-component mappings. No DOM, demo state,
// timers, host-side sensor answers, or assumed electrical/mechanical scaling.
// The generic Unit panel remains the presentation for nonvisual/raw fields.

export const CARDKB_KEY_IDS = Object.freeze([
  'esc', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 'backspace',
  'tab', 'q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', 'fn',
  'shift', 'a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'enter',
  'sym', 'z', 'x', 'c', 'v', 'b', 'n', 'm', 'comma', 'period', 'space',
  'up', 'left', 'right', 'down',
].map(id => `key-${id}`));

const MOMENTARY = {
  button: {press: 'pressed'}, limit: {press: 'pressed'}, key: {press: 'pressed'},
  encoder: {press: 'pressed'}, 'dual-button': {red: 'red-pressed', blue: 'blue-pressed'},
};
const JOINTS = {
  angle: {'voltage-mv': ['rotation']},
  encoder: {counter: ['rotation']},
  'joystick-v11': {'x-raw': ['tilt-x', 'tilt-y'], 'y-raw': ['tilt-x', 'tilt-y']},
  '8encoder': Object.fromEntries(Array.from({length: 8}, (_, i) => [`counters:${i}`, [`rotation-${i + 1}`]])),
};
const ARRAY_LEDS = {rgb: ['led0', 'led1', 'led2'], encoder: ['led0', 'led1'], '8encoder': Array.from({length: 9}, (_, i) => `rgb-${i + 1}`)};
const hasEvidence = bindings => typeof bindings?.evidence === 'string' && bindings.evidence.trim().length > 0;
const bools = (value, count) => Array.isArray(value) && value.length === count && value.every(item => typeof item === 'boolean');
const rgb = value => Number.isInteger(value) && value >= 0 && value <= 0xFFFFFF;
const observed = unit => unit?.available === true && (!unit.errors || Object.keys(unit.errors).length === 0);
const path = (port, component) => `${port}/${component}`;
const pressCommand = (port, component, pressed) => ({type: 'button-state', target: path(port, component), pressed});
const ledCommand = (port, component, color) => ({type: 'led', target: path(port, component), color, on: color !== 0});
const sourceValue = (state, field) => {
  const [name, index] = field.split(':');
  return index === undefined ? state[name] : state[name]?.[Number(index)];
};

function componentId(event, port) {
  const id = String(event?.id || '');
  if (port !== undefined) {
    const prefix = `${port}/`;
    if (!id.startsWith(prefix)) return null;
    const component = id.slice(prefix.length);
    return component.includes('/') ? null : component;
  }
  return id.slice(id.lastIndexOf('/') + 1);
}

// Array input updates require the current controller snapshot. Never invent an
// all-released baseline: that could release another source's held key/channel.
export function physicalInput(event, attachment, {port, properties = {}, bindings} = {}) {
  if (!event || event.source === 'runtime-readback' || event.kind !== 'button') return null;
  if (!['down', 'up', 'cancel'].includes(event.action)) return null;
  const id = componentId(event, port);
  if (!id) return null;
  const down = event.action === 'down';
  const unitId = attachment?.unit_id;
  const field = MOMENTARY[unitId]?.[id];
  if (field) return {[field]: down};
  if (unitId === 'cardkb') {
    const index = CARDKB_KEY_IDS.indexOf(id);
    if (index < 0 || !bools(properties.keys, 50)) return null;
    const keys = [...properties.keys];
    keys[index] = down;
    return {keys};
  }
  if (unitId === '8encoder') {
    const match = /^press-([1-8])$/.exec(id);
    if (match && bools(properties.pressed, 8)) {
      const pressed = [...properties.pressed];
      pressed[Number(match[1]) - 1] = down;
      return {pressed};
    }
    // A stable switch event must carry its detent. A momentary release must
    // never turn the switch off. Uncalibrated left/right != electrical on/off.
    const positions = bindings?.switchPositions;
    if (id === 'switch' && down && hasEvidence(bindings) && validSwitch(positions) && [0, 1].includes(event.position)) {
      return {'switch-on': event.position === positions.on};
    }
  }
  if (unitId === 'joystick-v11' && id === 'press' && hasEvidence(bindings) && [0, 1].includes(bindings.joystickPressedRaw)) {
    return {'button-raw': down ? bindings.joystickPressedRaw : 1 - bindings.joystickPressedRaw};
  }
  return null;
}

const validSwitch = positions => positions && [0, 1].includes(positions.on) && [0, 1].includes(positions.off) && positions.on !== positions.off;

function calibratedJoints(unitId, state, port, bindings) {
  if (!hasEvidence(bindings) || !Array.isArray(bindings.joints)) return [];
  const commands = [], used = new Set();
  for (const binding of bindings.joints) {
    if (!binding || !JOINTS[unitId]?.[binding.field]?.includes(binding.target)) continue;
    const value = sourceValue(state, binding.field);
    if (!Number.isFinite(value) || !Number.isFinite(binding.scale) || binding.scale === 0 || !Number.isFinite(binding.offset)) continue;
    const angle = value * binding.scale + binding.offset;
    if (!Number.isFinite(angle) || used.has(binding.target)) continue;
    if (binding.minimum !== undefined && (!Number.isFinite(binding.minimum) || angle < binding.minimum)) continue;
    if (binding.maximum !== undefined && (!Number.isFinite(binding.maximum) || angle > binding.maximum)) continue;
    used.add(binding.target);
    commands.push({type: 'joint', target: path(port, binding.target), angleDeg: angle});
  }
  return commands;
}

export function visualCommands(unit, port, {bindings, running = true} = {}) {
  if (typeof port !== 'string' || !port) return [];
  if (unit?.unit_id === 'fan') {
    const duty = unit.properties?.['duty-pct'];
    return [{type: 'drive-activity', target: path(port, 'rotor'), active: running && observed(unit) && Number.isFinite(duty) && duty > 0 && duty <= 100}];
  }
  if (!observed(unit)) return [];
  const state = unit.properties || {}, unitId = unit.unit_id, commands = [];
  for (const [component, field] of Object.entries(MOMENTARY[unitId] || {})) {
    if (typeof state[field] === 'boolean') commands.push(pressCommand(port, component, state[field]));
  }
  if (unitId === 'cardkb') {
    if (bools(state.keys, 50)) CARDKB_KEY_IDS.forEach((id, index) => commands.push(pressCommand(port, id, state.keys[index])));
    if (rgb(state['led-rgb'])) commands.push(ledCommand(port, 'rgb', state['led-rgb']));
  }
  if (unitId === 'key' && rgb(state['led-rgb'])) commands.push(ledCommand(port, 'rgb', state['led-rgb']));
  if (unitId === '8encoder') {
    if (bools(state.pressed, 8)) state.pressed.forEach((pressed, index) => commands.push(pressCommand(port, `press-${index + 1}`, pressed)));
    if (typeof state['switch-on'] === 'boolean' && hasEvidence(bindings) && validSwitch(bindings.switchPositions)) {
      commands.push({type: 'position', target: path(port, 'switch'), position: bindings.switchPositions[state['switch-on'] ? 'on' : 'off']});
    }
  }
  if (unitId === 'joystick-v11' && hasEvidence(bindings) && [0, 1].includes(bindings.joystickPressedRaw) && [0, 1].includes(state['button-raw'])) {
    commands.push(pressCommand(port, 'press', state['button-raw'] === bindings.joystickPressedRaw));
  }
  const ledTargets = bindings?.ledTargets, expected = ARRAY_LEDS[unitId], colors = state['led-rgb'];
  if (expected && hasEvidence(bindings) && Array.isArray(ledTargets) && ledTargets.length === expected.length &&
      new Set(ledTargets).size === expected.length && ledTargets.every(target => expected.includes(target)) &&
      Array.isArray(colors) && colors.length === expected.length && colors.every(rgb)) {
    ledTargets.forEach((target, index) => commands.push(ledCommand(port, target, colors[index])));
  }
  commands.push(...calibratedJoints(unitId, state, port, bindings));
  return commands;
}

// Explicit audit for every visual product. "panel-only" is intentional where
// the frozen asset has no corresponding actuator/display/audio component.
// requires-binding stays open until a verified orientation/scaling is supplied.
const AUDIT = {
  'env-iii': {}, pir: {}, 'ultrasonic-i2c': {},
  rgb: {binding: {'led-rgb': 'Electrical LED chain order to visual led0/1/2 locations requires evidence.'}},
  angle: {binding: {'voltage-mv': 'Potentiometer mechanical travel, zero, direction and voltage/angle calibration are unconfirmed.'}},
  color: {}, tof: {}, light: {}, relay: {},
  'joystick-v11': {binding: {'x-raw': 'Raw axis to tilt joint orientation/range requires calibration.', 'y-raw': 'Raw axis to tilt joint orientation/range requires calibration.', 'button-raw': 'Catalog preserves raw button byte; pressed polarity is unconfirmed.'}},
  'dual-button': {input: ['red-pressed', 'blue-pressed'], readback: ['red-pressed', 'blue-pressed']},
  button: {input: ['pressed'], readback: ['pressed']}, ncir: {}, heart: {},
  encoder: {input: ['pressed'], readback: ['pressed'], binding: {counter: 'Counter units per physical revolution, zero and direction are unconfirmed.', 'led-rgb': 'LED index 1/2 to the two physical locations requires evidence.'}},
  thermal: {}, tvoc: {}, ir: {}, hub: {}, rfid2: {}, rs485: {}, buzzer: {},
  fan: {activity: ['duty-pct'], note: 'Positive observed PWM enables a fixed graphical activity cadence; zero, unavailable or terminal state stops it. Shaft speed and electromechanical response remain unmodeled.'},
  limit: {input: ['pressed'], readback: ['pressed']},
  cardkb: {input: ['keys'], readback: ['keys', 'led-rgb'], extra: {keys: '50 bool matrix in fixtures/cardkb-keymap.json order; requires current controller baseline.', 'led-rgb': 'Packed RGB emitted by the controller modifier-state machine.'}},
  key: {input: ['pressed'], readback: ['pressed', 'led-rgb']},
  '8encoder': {input: ['pressed'], readback: ['pressed'], binding: {counters: 'Each count/revolution, zero and direction requires calibration.', 'switch-on': 'Electrical state to physical slide detent requires a confirmed truth table.', 'led-rgb': 'Schematic LED chain order to nine physical light pipes is unconfirmed.'}},
};

export function visualMappingCoverage(catalog) {
  const units = Array.isArray(catalog) ? catalog : catalog?.units || [];
  return {
    schema_version: 1,
    category: 'browser-visual-mapping-contract',
    firmware_execution: 'NOT RUN',
    hardware_execution: 'NOT RUN',
    units: units.map(unit => {
      const audit = AUDIT[unit.id];
      if (!audit) return {unit_id: unit.id, status: 'unregistered', fields: []};
      const fields = new Set([...Object.keys(unit.inputs || {}), ...Object.keys(unit.outputs || {}), ...Object.keys(audit.extra || {})]);
      const rows = [...fields].map(field => ({
        field,
        input: audit.input?.includes(field) ? 'mapped' : Object.hasOwn(unit.inputs || {}, field) || audit.extra?.[field] && field === 'keys' ? 'panel-only' : 'read-only',
        readback: audit.readback?.includes(field) ? 'mapped' : audit.activity?.includes(field) ? 'activity-only' : audit.binding?.[field] ? 'requires-binding' : 'panel-only',
        ...(audit.binding?.[field] ? {blocker: audit.binding[field]} : {}),
        ...(audit.extra?.[field] ? {note: audit.extra[field]} : {}),
      }));
      const binding = rows.some(row => row.readback === 'requires-binding');
      return {
        unit_id: unit.id,
        status: binding ? 'requires-binding' : rows.some(row => row.readback === 'mapped') ? 'mapped' : audit.activity?.length ? 'activity-only' : rows.length ? 'panel-only' : 'passive',
        fields: rows,
        ...(audit.note ? {note: audit.note} : {}),
      };
    }),
    registered_unit_ids: Object.keys(AUDIT),
  };
}
