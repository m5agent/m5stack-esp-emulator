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
  encoder: {press: 'pressed'}, scroll: {press: 'pressed'}, 'dual-button': {red: 'red-pressed', blue: 'blue-pressed'},
  joystick2: {press: 'button-pressed'},
};
const JOINTS = {
  angle: {'voltage-mv': ['rotation']},
  encoder: {counter: ['rotation']},
  // The physical source is separate from writable/resettable guest counters.
  // It still needs a verified count/revolution and orientation binding.
  scroll: {'source-count': ['rotation']},
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

function flashlightCommand(unit, port) {
  const unknown = {type: 'led', target: path(port, 'light'), known: false};
  const state = unit.properties || {};
  if (!observed(unit) || !['output-known', 'pad-synchronized', 'gpio-route-supported'].every(field => state[field] === true)
      || !['flash-mode', 'en-level', 'active'].every(field => typeof state[field] === 'boolean')) return unknown;
  const flash = state['flash-mode'], active = state.active, en = state['en-level'];
  const pct = state['flash-level-pct'], timeout = state['timeout-ms'];
  const decodedFlash = Number.isInteger(pct) && pct >= 30 && pct <= 100 && pct % 10 === 0 && [220, 1300].includes(timeout);
  const reset = pct === 0 && timeout === 0;
  // Timeout keeps the decoded Flash code while EN stays high. We never infer
  // expiry from a browser clock: active is the observed controller result.
  const consistent = active ? en && (flash ? decodedFlash : reset)
    : flash ? (en ? decodedFlash : reset) : !en && reset;
  if (!consistent) return unknown;
  // Flash brightness is only the relative digital code. Torch has no decoded
  // Flash percentage, so its fixed appearance is qualitative, not photometry.
  return {type: 'led', target: path(port, 'light'), color: 0xFFFAF0, on: active,
    brightness: active ? flash ? pct / 100 : 1 : 0};
}

// Uniform colors are invariant under every unknown electrical-to-physical
// permutation. Distinct colors still require an explicit, evidenced mapping.
export function arrayLedFeedback(unit, bindings) {
  const targets = ARRAY_LEDS[unit?.unit_id];
  if (!targets) return null;
  if (!observed(unit)) return {known: false, targets, reason: 'unavailable'};
  const colors = unit.properties?.['led-rgb'];
  if (!Array.isArray(colors) || colors.length !== targets.length || !targets.every((_, index) => rgb(colors[index]))) {
    return {known: false, targets, reason: 'invalid'};
  }
  const mapped = bindings?.ledTargets;
  if (hasEvidence(bindings) && Array.isArray(mapped) && mapped.length === targets.length &&
      new Set(mapped).size === targets.length && targets.every((_, index) => targets.includes(mapped[index]))) {
    return {known: true, targets: mapped, colors, mapping: 'explicit'};
  }
  if (colors.every(color => color === colors[0])) return {known: true, targets, colors, mapping: 'uniform'};
  return {known: false, targets, reason: 'unmapped'};
}

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
  if (unit?.unit_id === 'flashlight') return [flashlightCommand(unit, port)];
  if (unit?.unit_id === '2relay') {
    // U131 schematic + fixed asset channel numbering, recorded in
    // platform/units/fixtures/2relay-binding.json. Nominal powered indication
    // follows each observed GPIO pad; this is not a contact/load measurement.
    return [1, 2].map(channel => {
      const value = unit.properties?.[`output-${channel}-level`];
      return observed(unit) && typeof value === 'boolean'
        ? {...ledCommand(port, `led-${channel}`, 0x247CFF), on: value}
        : {type: 'led', target: path(port, `led-${channel}`), known: false};
    });
  }
  if (unit?.unit_id === 'fan') {
    const duty = unit.properties?.['duty-pct'];
    return [{type: 'drive-activity', target: path(port, 'rotor'), active: running && observed(unit) && Number.isFinite(duty) && duty > 0 && duty <= 100}];
  }
  const leds = arrayLedFeedback(unit, bindings);
  const ledCommands = leds ? leds.targets.map((target, index) => leds.known
    ? ledCommand(port, target, leds.colors[index]) : {type: 'led', target: path(port, target), known: false}) : [];
  if (!observed(unit)) return ledCommands;
  const state = unit.properties || {}, unitId = unit.unit_id, commands = [];
  for (const [component, field] of Object.entries(MOMENTARY[unitId] || {})) {
    if (typeof state[field] === 'boolean') commands.push(pressCommand(port, component, state[field]));
  }
  if (unitId === 'cardkb') {
    if (bools(state.keys, 50)) CARDKB_KEY_IDS.forEach((id, index) => commands.push(pressCommand(port, id, state.keys[index])));
    if (rgb(state['led-rgb'])) commands.push(ledCommand(port, 'rgb', state['led-rgb']));
  }
  if (['key', 'scroll'].includes(unitId) && rgb(state['led-rgb'])) commands.push(ledCommand(port, 'rgb', state['led-rgb']));
  if (unitId === '8encoder') {
    if (bools(state.pressed, 8)) state.pressed.forEach((pressed, index) => commands.push(pressCommand(port, `press-${index + 1}`, pressed)));
    if (typeof state['switch-on'] === 'boolean' && hasEvidence(bindings) && validSwitch(bindings.switchPositions)) {
      commands.push({type: 'position', target: path(port, 'switch'), position: bindings.switchPositions[state['switch-on'] ? 'on' : 'off']});
    }
  }
  if (unitId === 'joystick-v11' && hasEvidence(bindings) && [0, 1].includes(bindings.joystickPressedRaw) && [0, 1].includes(state['button-raw'])) {
    commands.push(pressCommand(port, 'press', state['button-raw'] === bindings.joystickPressedRaw));
  }
  commands.push(...ledCommands);
  commands.push(...calibratedJoints(unitId, state, port, bindings));
  return commands;
}

// Explicit audit for every visual product. "panel-only" is intentional where
// the frozen asset has no corresponding actuator/display/audio component.
// requires-binding stays open until a verified orientation/scaling is supplied.
const AUDIT = {
  'env-iii': {}, pir: {}, 'ultrasonic-i2c': {},
  rgb: {binding: {'led-rgb': 'Uniform colors map by permutation invariance; distinct electrical LED colors require physical-location evidence.'}},
  angle: {binding: {'voltage-mv': 'Potentiometer mechanical travel, zero, direction and voltage/angle calibration are unconfirmed.'}},
  color: {}, tof: {}, light: {}, relay: {},
  '2relay': {readback: ['output-1-level', 'output-2-level'], note: 'U131 white=Relay1=led-1, yellow=Relay2=led-2. Fixed-blue nominal powered indication; GPIO pads are not contacts or load measurements.'},
  flashlight: {readback: ['output-known', 'pad-synchronized', 'gpio-route-supported', 'flash-mode', 'en-level', 'active', 'flash-level-pct', 'timeout-ms'], note: 'U152 D1 fixed-white appearance requires qualified controller readback. Flash brightness represents a relative digital code; Torch appearance is qualitative. No photometry or S1 visual-detent mapping.'},
  'joystick-v11': {binding: {'x-raw': 'Raw axis to tilt joint orientation/range requires calibration.', 'y-raw': 'Raw axis to tilt joint orientation/range requires calibration.', 'button-raw': 'Catalog preserves raw button byte; pressed polarity is unconfirmed.'}},
  joystick2: {readback: ['button-pressed'], binding: {'x-position': 'Mapped signed axis to tilt orientation/range requires mechanical calibration.', 'y-position': 'Mapped signed axis to tilt orientation/range requires mechanical calibration.'}, note: 'The official driver reports pressed as a boolean; analog range, center, direction and mechanical travel remain unmodeled.'},
  '8servos': {binding: {modes: 'Mode registers do not establish a physical actuator state.', angles: 'Guest angle registers do not prove mechanical angle, servo type or direction.', pulses: 'Pulse request does not prove output timing or servo response.', 'pwm-duty': 'Duty register does not prove output waveform or connected load.'}, note: 'All visual motions remain panel-only without a device-local servo calibration.'},
  'servo8-hat': {readback: ['power-state'], binding: {angles: 'Guest angle registers do not prove mechanical angle or servo response.', pulses: 'Pulse request does not prove output timing or servo response.'}, note: 'Power register is observed controller state; rail current and servo motion are not modeled.'},
  nfc: {note: 'UID and I2C transaction state are panel-only; no NFC field, antenna, range or card-electrical visualization is inferred.'},
  'dual-button': {input: ['red-pressed', 'blue-pressed'], readback: ['red-pressed', 'blue-pressed']},
  button: {input: ['pressed'], readback: ['pressed']}, ncir: {}, heart: {},
  encoder: {input: ['pressed'], readback: ['pressed'], binding: {counter: 'Counter units per physical revolution, zero and direction are unconfirmed.', 'led-rgb': 'Uniform colors map by permutation invariance; distinct LED index 1/2 colors require physical-location evidence.'}},
  scroll: {input: ['pressed'], readback: ['pressed', 'led-rgb'], binding: {'source-count': 'EC10E pulse specification alone does not establish decoded count/revolution and physical direction. Logical counter writes/reset never imply shaft motion.'}},
  thermal: {}, tvoc: {}, ir: {}, hub: {}, rfid2: {}, rs485: {}, buzzer: {},
  fan: {activity: ['duty-pct'], note: 'Positive observed PWM enables a fixed graphical activity cadence; zero, unavailable or terminal state stops it. Shaft speed and electromechanical response remain unmodeled.'},
  limit: {input: ['pressed'], readback: ['pressed']},
  cardkb: {input: ['keys'], readback: ['keys', 'led-rgb'], extra: {keys: '50 bool matrix in fixtures/cardkb-keymap.json order; requires current controller baseline.', 'led-rgb': 'Packed RGB emitted by the controller modifier-state machine.'}},
  key: {input: ['pressed'], readback: ['pressed', 'led-rgb']},
  '8encoder': {input: ['pressed'], readback: ['pressed'], binding: {counters: 'Each count/revolution, zero and direction requires calibration.', 'switch-on': 'Electrical state to physical slide detent requires a confirmed truth table.', 'led-rgb': 'Uniform colors map by permutation invariance; distinct schematic LED colors to nine physical light pipes remain unconfirmed.'}},
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
