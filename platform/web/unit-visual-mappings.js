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
  if (unit?.unit_id === 'vibrator') {
    // U059's frozen rotor joint is explicitly external eccentric/shaft motion
    // only; observed LEDC duty drives the graphical cadence, not vibration force.
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
  vibrator: {activity: ['duty-pct'], note: 'U059 positive observed LEDC duty enables the frozen rotor joint activity cadence; zero, unavailable or terminal state stops it. Vibration force, frequency optimum and eccentric mechanics remain unmodeled.'},
  ssr: {note: 'U122 has no frozen visual indicator component; output-level stays panel-only and is not a contact, load or isolation measurement.'},
  earth: {note: 'U019 analog/digital probe channels are panel-only; the mechanical trim joint has no electrical binding and is never driven from controller state.'},
  hall: {note: 'U084 low-active magnetic output is panel-only; the frozen asset has no status LED component and the A3144E/74HC08D spatial logic is not visualizable.'},
  'reflective-ir': {note: 'U175 analog/digital reflectance channels are panel-only; the sensitivity trim has no confirmed electrical mapping.'},
  limit: {input: ['pressed'], readback: ['pressed']},
  cardkb: {input: ['keys'], readback: ['keys', 'led-rgb'], extra: {keys: '50 bool matrix in fixtures/cardkb-keymap.json order; requires current controller baseline.', 'led-rgb': 'Packed RGB emitted by the controller modifier-state machine.'}},
  key: {input: ['pressed'], readback: ['pressed', 'led-rgb']},
  '8encoder': {input: ['pressed'], readback: ['pressed'], binding: {counters: 'Each count/revolution, zero and direction requires calibration.', 'switch-on': 'Electrical state to physical slide detent requires a confirmed truth table.', 'led-rgb': 'Uniform colors map by permutation invariance; distinct schematic LED colors to nine physical light pipes remain unconfirmed.'}},
  dlight: {note: 'U136 illuminance-lx is a QOM fixture converted inside the future 0119 BH1750 transaction model; the frozen asset has no indicator component bound to the two-byte raw read, so the value stays panel-only and no photometric behavior is inferred.'},
  accel: {note: 'U056 accel-x/y/z g fixtures and int-source are panel-only; the frozen asset has no orientation binding, and physical acceleration/tilt behavior is not inferred from register bytes.'},
  '4relay': {note: 'U097 per-channel relay/led levels stay panel-only until guest evidence confirms the driver-compatible bit order; frozen relay indicators are qualitative and contacts/loads are not visualizable.'},
  'weight-i2c': {note: 'U180 weight/adc fixtures are panel-only; no frozen display component is bound to 0x10/0x60/0x70 readings and load-cell mechanics are not modeled.'},
  ncir2: {note: 'U150 temperature/chip-temperature/RGB/buzzer are QOM fixtures and register readback only; the STM32 alarm state machine and infrared optics cannot be visualized from this contract.'},
  extio2: {note: 'U011-B eight-channel mode/output/servo/RGB are register-readback values only; ADC full scale, servo units and chip-internal RGB order remain unresolved, so no motion or color binding is inferred.'},
  hbridge: {note: 'U160 direction/PWM duty/frequency are register readbacks only; motor rotation, torque, current and RZ7899 protection behavior are not modeled.'},
  joystick: {binding: {'x-raw': 'Raw axis to tilt joint orientation/range requires calibration.', 'y-raw': 'Raw axis to tilt joint orientation/range requires calibration.'}, note: 'U024 reuses the joystick-v11 0x52 snapshot; button byte polarity stays unresolved and the 0x52 address conflicts with joystick-v11.'},
  watering: {note: 'U101 soil analog-mv and PUMP_EN pad level are panel-only: pump flow/head and soil-moisture physics are not modeled, so no water animation binding is inferred.'},
  fader: {note: 'U123 14-LED SK6812 frames are captured raw (G,R,B) and stay panel-only; palette/mechanical feel and optical output are not modeled and the neopixel driver SHA must be pinned.'},
  dac: {note: 'U012 dac-raw/eeprom state is panel-only; the physical 0..3.3V analog output and EEPROM retention are not modeled.'},
  bps: {note: 'U090 temperature/pressure fixtures are panel-only; altitude depends on the driver sea-level assumption and QMP6988 variants are not modeled.'},
  'adc-v11': {binding: {'voltage-mv': 'Input divider/PGA mapping and ADS1100-vs-ADS1110 identity remain unresolved; no physical voltage accuracy is inferred.'}},
  env: {binding: {'temperature-c': 'DHT12/BMP280 fixtures are synthetic; sensor accuracy, self-heating and ENV-II/III/IV variants are not modeled.', 'humidity-pct': 'DHT12 0.1-unit quantization and checksum are model-side only; no hygrometer accuracy is inferred.', 'pressure-pa': 'BMP280 compensation uses synthetic-but-valid coefficients; no barometric accuracy is inferred.'}, note: 'U001 DHT12 0x5C + BMP280 0x76 are two device-local slaves on one Grove pair; their values stay panel-only and the driver requires an explicit ENV-I type.'},
  ameter: {binding: {'current-a': 'Synthetic current fixture inverse-encoded into ADS1115 counts; factory calibration, isolation and fuse behavior are not modeled.'}, note: 'U086 ADS1115 0x48 + read-only EEPROM 0x51 stay panel-only; adc-raw/config-word/eeprom-writes are transaction observations, not a measurement accuracy claim.'},
  extencoder: {binding: {counter: 'Counter units per external encoder revolution, AB/ABZ decoding, zero and direction are unconfirmed; counter writes never imply shaft motion.'}, note: 'U161 4-byte little-endian register bank is readback only; the product-page protocol table is corrupt and 0x20/0x30 semantics stay unresolved.'},
  'ain4-20ma': {binding: {'current-ma': '4-20mA loop accuracy, isolation and jumper wiring are not modeled; the fixture is a synthetic current source.', 'adc-raw': '12-bit vs raw16 width is unresolved; the raw fixture is not a calibrated ADC reading.'}, note: 'U162 raw/current/calibration registers are panel-only; page 0xF0 vs driver 0xFE/0xFF remains a documented conflict.'},
  acssr: {note: 'U139 relay/RGB are I2C transaction state only. AC 24-480V/10A mains switching, zero-cross, leakage and lifetime are NOT modeled; never visualize this as a mains-capable switch.'},
  gesture: {binding: {gesture: 'Gesture flag fixtures are synthetic; IR optics, recognition distance and gesture physics are not modeled.'}, note: 'U127 PAJ7620 0x43/0x44 flags are QOM fixtures; the 219-entry init sequence and bank switching are accepted transaction state only.'},
  rfid: {note: 'U031 reuses the rfid2 MFRC522 transaction model at 0x28; UID/sector state is panel-only, RF field/antenna/range and real card data are not modeled, and 0x28 conflicts with rfid2.'},
  'tube-pressure': {input: ['analog-mv'], readback: ['analog-mv', 'adc-samples', 'pressure-kpa'], note: 'U130 only supplies the white analog wire; pressure-kpa repeats the driver formula for observability, not a physical pressure measurement. Sensor linearity/temperature compensation are NOT RUN.'},
  'laser-rx': {input: ['digital-level'], readback: ['input-level'], note: 'U065 white DOUT is a digital input fixture; UART mode and the optical link (beam, 140-205kHz, 900nm) are not modeled.'},
  extio: {input: ['input-levels'], readback: ['output-levels', 'polarity', 'config'], note: 'U011 PCA9554 register transactions only; INT output, A0-A2 pad addressing and pull-up/open-drain electrical behavior are not modeled.'},
  dac2: {readback: ['range', 'voltage-0-v', 'voltage-1-v', 'dac-0-raw', 'dac-1-raw'], note: 'U012-B stores guest-written 16-bit codes; the page 15-bit vs driver 16-bit full scale stays unresolved and no analog output/short-circuit behavior is inferred.'},
  scales: {input: ['weight-g', 'adc-raw', 'button-status'], readback: ['led-rgb', 'led-sync'], note: 'U108 register/fixture model only; HX711 sampling, weighing mechanics and RGB optics are not modeled, and 0x26 conflicts with 4relay/weight-i2c.'},
  vmeter: {binding: {'voltage-v': 'Divider/PGA calibration and +/-36V isolation are unresolved; no physical voltage accuracy is inferred.'}, note: 'U087 ADS1115 0x49 + synthetic factor-1.0 EEPROM at 0x53; the factory calibration is not real and 0x53 conflicts with accel.'},
  adc: {binding: {'voltage-v': 'ADS1100 reference/PGA and the ADS1100-vs-ADS1110 identity remain unresolved; no physical voltage accuracy is inferred.'}, note: 'U013 ADS1100 transaction model distinct from adc-v11; 0x48 conflicts with adc-v11/ameter and master/snapshot get_raw_value() length differs.'},
  'env-iv': {binding: {'temperature-c': 'SHT40/BMP280 fixtures are synthetic; the snapshot SHT4x getter bug must be fixed by pinning the master driver, and sensor accuracy/self-heating are not modeled.', 'humidity-pct': 'SHT40 CRC frames are model-side only; no hygrometer accuracy is inferred.', 'pressure-pa': 'BMP280 compensation uses synthetic-but-valid coefficients; no barometric accuracy is inferred.'}, note: 'U001-D SHT40 0x44 + BMP280 0x76 are two device-local slaves on one Grove pair; values stay panel-only and ENVUnit requires an explicit ENV-IV type.'},
  co2: {binding: {'co2-ppm': 'Synthetic CO2 fixture through SCD4x CRC words; gas-sensor accuracy and the 5s measurement cycle are not modeled. The driver temperature decode bug keeps guest temperature unassertable.'}, note: 'U103 SCD40/SCD41 identity and asyncio-vs-sync driver rewrite stay unresolved; only CO2 and humidity are assertable in the current driver family.'},
  pbhub: {note: 'U041 six channels live in one 0x61 command space (channel_base|offset register byte), not separate bus addresses; RGB wire order is GRB per the pinned master driver and PWM/servo/RGB electrical behavior is not modeled.'},
  'ultrasonic-io': {binding: {'distance-mm': 'Synthetic distance fixture drives a model echo pulse; time_pulse_us timeout semantics, acoustics, temperature compensation and ±2% accuracy are not modeled.'}, note: 'U098-B2 page PinMap labels PORT.A as SDA/SCL while the driver is GPIO trigger/echo; the label conflict and >3.5m delayed response stay unresolved.'},
  'rs485-iso': {input: ['rx-hex'], readback: ['tx-hex'], note: 'U094 reuses the registered rs485 UART transaction model; isolation withstand, ESD, fail-safe and 500Kbps/256-node behavior are NOT modeled. PORT.C conflicts with midi/gps/uhf-rfid.'},
  'laser-tx': {readback: ['output-level'], note: 'U066 DIN is a GPIO output observation only. Laser optical power, wavelength, modulation and eye safety are NOT modeled; never aim the emitter at people or animals.'},
  co2l: {binding: {'co2-ppm': 'Synthetic CO2 fixture through SCD4x CRC words; gas-sensor accuracy and the 5s cycle are not modeled. The driver temperature decode bug keeps guest temperature unassertable.'}, note: 'U104 SCD41 0x62 reuses the US_SCD40 model with chip-id 0x41; 0x62 conflicts with co2, and SCD40-vs-SCD41 identity stays unresolved.'},
  neco: {input: ['button-pressed'], readback: ['led-rgb', 'led-frames', 'incomplete-frames'], note: 'U163 models 35 WS2812 LEDs per the product page (driver defaults to 70; unresolved) and an active-low button; the two Grove ports are collapsed to one attachment, and LED optics/power are NOT modeled.'},
  midi: {input: ['rx-hex'], readback: ['tx-hex'], note: 'U187 captures the guest MIDI byte stream only; SAM2695 audio synthesis, voices and effects are NOT modeled, and the 31250/31520 baud conflict stays unresolved. PORT.C conflicts with gps/uhf-rfid/rs485-iso.'},
  tof4m: {binding: {'distance-mm': 'Synthetic distance fixture encoded into the VL53L1X register file; 4m range, resolution, laser safety and optics are not modeled.'}, note: 'U172 uses 16-bit register addresses and model id 0xEA/0xCC/0x10; 0x29 conflicts with tof and color, and the VL53L1CX-vs-VL53L1X page naming stays unresolved.'},
  weight: {input: ['adc-raw', 'channel'], readback: ['weight-g', 'conversions', 'ready-level'], note: 'U030 HX711 bit-pulse model only; weighing mechanics, load cell, 10SPS timing and electrical behavior are NOT modeled. The page FAQ I2C wording conflicts with the PinMap/driver GPIO path and weight-i2c (U180) is a different protocol.'},
  'bldc-driver': {binding: {'rpm': 'Synthetic motor fixture through the STM32/DRV11873 register file; motor electrical behavior, stall protection and the 5V output are not modeled.', 'frequency-hz': 'Synthetic rpm/60 convention: the real pole-pair/electrical-frequency relation has no driver anchor and stays unresolved.'}, note: 'U181 I2C 0x65 register model only; RPM float/int/ASCII views are derived from the same fixture and 0xF0 flash persistence is unresolved.'},
  'ac-measure': {binding: {'voltage-v': 'Synthetic AC measurement fixture; mains voltage/current, isolation, overcurrent and metering accuracy are NOT RUN.', 'energy-kwh': 'Synthetic energy fixture only; no real metering integration is claimed.'}, note: 'U164 AC 100-240V@10A is a MEASUREMENT INPUT, never a switchable load; ASCII/byte views are model-side conventions, the page STM32G030 vs I2C-index STM32F030 conflict is unresolved.'},
  dds: {input: ['waveform', 'frequency-hz', 'phase-deg', 'freq-reg', 'phase-reg'], readback: ['ctrl-word', 'active-freq-reg', 'active-phase-reg'], note: 'U105 AD9833 register encoding only; analog waveform, 0-0.6V amplitude and output impedance are NOT modeled.'},
  gps: {input: ['nmea-lines'], readback: ['injected-lines', 'tx-hex'], note: 'U032 injects synthetic NMEA sentences into the guest UART RX when routed; GNSS RF/satellite/accuracy are NOT RUN, the driver does not validate checksums and the page is EOL.'},
  'uhf-rfid': {input: ['responses-hex'], readback: ['tx-hex', 'rx-frames-hex', 'frames-sent', 'frames-injected'], note: 'U107 JRD4035 frame capture/injection only; RF 840-960MHz, Gen2 air protocol, read range and kill/lock/password security are NOT modeled and no real tag capability is claimed.'},
  'pbhub-v11': {input: ['digital-inputs', 'analog-inputs'], readback: ['digital-outputs', 'pwm-outputs', 'rgb-frames', 'rgb-mode', 'fw-version'], note: 'U041-B reuses the single 0x61 PbHub command space with a firmware v2 fixture; the v1-vs-v2 behavior difference beyond the version byte is unresolved and PWM/servo/RGB electrical behavior is not modeled.'},
  op90: {input: ['digital-level'], readback: ['blocked'], note: 'U057 white digital input on PORT.B only; active polarity is UNRESOLVED (the model treats blocked as active-low) and IR optics/object detection are NOT modeled. PORT.B is unavailable on atoms3r/sticks3/stopwatch.'},
  'rgb-led-10cm': {readback: ['led-rgb', 'led-frames', 'incomplete-frames'], note: 'A035 15-SK6812 strip captured through RMT on the yellow PORT.B line; LED optics/power/expansion are NOT modeled and PORT.B host availability is a blocker.'},
  '8angle': {input: ['adc12-raw', 'adc8-raw', 'switch-pressed'], readback: ['led-rgb'], note: 'U154 I2C 0x43 register model only; potentiometer hardware, ADC reference and switch mechanics are NOT modeled, and the 9 SK6812 channels are readback state.'},
  'kmeter-iso-v11': {binding: {'thermocouple-temperature-c': 'Synthetic thermocouple temperature through MAX31855-derived int32le registers; thermocouple physics, cold-junction compensation and isolation are NOT RUN.'}, note: 'U133-V11 I2C 0x66 exposes int32le/100 and 8-byte ASCII views of the same fixture; ±2C accuracy and the -200..1350C range are NOT RUN.'},
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
