// These original CoreS3 example BINs bind their reviewed browser Unit route.
const examples = {
  'ultrasonic-i2c': {
    firmwareInputSHA256:'0bb888aeb6fdde9200b7f81ab15ea314d75303ed6917aea58ff2a507c195e221',
    attachment:{id:'ultrasonic',unit_id:'ultrasonic-i2c',port_id:'port-a',pins:{yellow:2,white:1},
      visual_port:'grove',initial:{'distance-mm':1000}},
  },
  relay: {
    firmwareInputSHA256:'a645e2a79947a01227c69ee565545838722ef0ebd7805d15705039bddcef84ca',
    attachment:{id:'relay',unit_id:'relay',port_id:'port-b',pins:{yellow:9,white:8},
      visual_port:'grove',initial:{}},
  },
};
const ultrasonicPath = '/machine/units/ultrasonic';
const ultrasonicChip = `${ultrasonicPath}/chip`;
const relayPath = '/machine/units/relay';
const dualKmeterPath = '/machine/dual-kmeter';
export const DUAL_KMETER_EXAMPLE_ID = 'cores3-dual-kmeter';
export const DUAL_KMETER_FIRMWARE_SHA256 = 'b9fe8334023c1b1f95e7c51b3a63724e621a6789812083848ed3ea7eaa332d49';
export const DUAL_KMETER_RUNTIME_PATCH = Object.freeze({
  path:'patches/qemu-wasm-probe/0050-cores3-dual-kmeter-example.patch',
  sha256:'e412ebb45fb7fc171f5059d57a04b443f3d014e6441297c3583cb621001dfdd1',
});
const dualKmeterSource = Object.freeze({
  path:'platform/runtime/qemu-probe/fixture/cores3_dual_kmeter_example.py',bytes:774,
  sha256:'6765c65ac5e3a6219d762fe2cbc4639301714719646a79b115cc794e2b44fb37',
});

function coreS3(profile) {
  return profile?.deviceId === 'cores3' && profile.board === 'm5cores3' && profile.chip === 'esp32s3'
    && profile.target === 'xtensa-softmmu' && profile.flashMb === 16 && profile.psramMb === 8
    && profile.display?.width === 320 && profile.display.height === 240 && profile.inputs?.touch === true;
}

function hasFields(value, fields) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === fields.length && fields.every(field => Object.hasOwn(value, field));
}

/** Bind a private run profile after the caller computes the validated upload hash. */
export function resolveQemuUnitExample(profile, firmwareInputSHA256, requestedExample) {
  if (requestedExample !== undefined) {
    if (requestedExample !== DUAL_KMETER_EXAMPLE_ID || firmwareInputSHA256 !== DUAL_KMETER_FIRMWARE_SHA256)
      throw new Error('DualKmeter requires the selected preset and exact CoreS3 workbench firmware');
    return validateQemuUnitExampleProfile({...profile,unitExample:DUAL_KMETER_EXAMPLE_ID,
      unitExampleFirmwareInputSHA256:firmwareInputSHA256,
      inputs:{...profile.inputs,pir:null},units:{schema_version:1,attachments:[]}});
  }
  if (profile && (Object.hasOwn(profile, 'unitExample') || Object.hasOwn(profile, 'unitExampleFirmwareInputSHA256'))) {
    validateQemuUnitExampleProfile(profile);
    if (profile.unitExampleFirmwareInputSHA256 !== firmwareInputSHA256) throw new Error('QEMU Unit example firmware changed');
    return profile;
  }
  if (!coreS3(profile)) return profile;
  const match = Object.entries(examples).find(([, example]) => example.firmwareInputSHA256 === firmwareInputSHA256);
  if (!match) return profile;
  const [unitExample, {attachment}] = match;
  return validateQemuUnitExampleProfile({...profile,unitExample,unitExampleFirmwareInputSHA256:firmwareInputSHA256,
    inputs:{...profile.inputs,pir:null},units:{schema_version:1,attachments:[structuredClone(attachment)]}});
}

export function validateQemuUnitExampleProfile(profile) {
  const kind = profile?.unitExample;
  if (kind === DUAL_KMETER_EXAMPLE_ID) {
    if (!coreS3(profile) || profile.unitExampleFirmwareInputSHA256 !== DUAL_KMETER_FIRMWARE_SHA256
      || profile.readyFirmwareSHA256 !== DUAL_KMETER_FIRMWARE_SHA256 || profile.clockDivisor !== 1
      || profile.profile !== 'cores3-wasm-uiflow-workbench-lvgl-wallclock-candidate'
      || profile.oneInsnPerTb !== true || profile.inputs.pir !== null
      || !hasFields(profile.units,['schema_version','attachments']) || profile.units.schema_version !== 1
      || !Array.isArray(profile.units.attachments) || profile.units.attachments.length)
      throw new Error('Invalid QEMU DualKmeter example binding');
    return profile;
  }
  const example = typeof kind === 'string' && Object.hasOwn(examples, kind) ? examples[kind] : null;
  if (!coreS3(profile) || !example || profile.unitExampleFirmwareInputSHA256 !== example.firmwareInputSHA256
    || profile.inputs.pir !== null) throw new Error('Invalid QEMU Unit example binding');
  const units = profile.units, unit = units?.attachments?.[0], expected = example.attachment;
  const fields = ['id','unit_id','port_id','visual_port'];
  if (!hasFields(units, ['schema_version','attachments']) || units.schema_version !== 1
    || !Array.isArray(units.attachments) || units.attachments.length !== 1
    || !hasFields(unit, [...fields,'pins','initial']) || fields.some(field => unit[field] !== expected[field])
    || !hasFields(unit.pins, ['yellow','white']) || unit.pins.yellow !== expected.pins.yellow || unit.pins.white !== expected.pins.white
    || !hasFields(unit.initial, Object.keys(expected.initial))
    || Object.keys(expected.initial).some(field => unit.initial[field] !== expected.initial[field])) {
    throw new Error('Invalid QEMU Unit example wiring');
  }
  return profile;
}

const get = (path, property) => ({execute:'qom-get',arguments:{path,property}});
const distanceInRange = value => Number.isSafeInteger(value) && value >= 20 && value <= 4500;
const temperatureInRange = value => Number.isSafeInteger(value) && value >= -20000 && value <= 135000;
const nonnegativeCount = value => Number.isSafeInteger(value) && value >= 0;

export function dualKmeterExampleSource(profile, workbench, source) {
  if (!coreS3(profile) || workbench?.deviceId !== 'cores3' || workbench.firmwareSHA256 !== DUAL_KMETER_FIRMWARE_SHA256
    || !hasFields(source,Object.keys(dualKmeterSource))
    || Object.keys(dualKmeterSource).some(field => source[field] !== dualKmeterSource[field])) return null;
  return dualKmeterSource;
}

/** Read only fixed properties backed by the virtual I2C chip or GPIO listener. */
export function qemuUnitExampleQueries(profile) {
  if (profile?.unitExample === undefined) return {};
  validateQemuUnitExampleProfile(profile);
  if (profile.unitExample === 'relay') {
    return {level:get(relayPath, 'output-level'),transitions:get(relayPath, 'output-transitions')};
  }
  if (profile.unitExample === DUAL_KMETER_EXAMPLE_ID) {
    return {temperatureCentiC:get(dualKmeterPath,'temperature-centi-c'),transactions:get(dualKmeterPath,'transactions'),
      bytesRead:get(dualKmeterPath,'read-bytes'),bytesWritten:get(dualKmeterPath,'written-bytes')};
  }
  return {distanceMm:get(ultrasonicPath, 'distance-mm'),transactions:get(ultrasonicChip, 'transactions'),
    bytesRead:get(ultrasonicChip, 'read-bytes'),bytesWritten:get(ultrasonicChip, 'written-bytes')};
}

export function validateQemuUnitExampleState(profile, state) {
  validateQemuUnitExampleProfile(profile);
  const kind = profile.unitExample;
  let valid;
  if (kind === 'relay') {
    valid = hasFields(state, ['kind','level','transitions']) && typeof state.level === 'boolean' && nonnegativeCount(state.transitions);
  } else {
    const field = kind === DUAL_KMETER_EXAMPLE_ID ? 'temperatureCentiC' : 'distanceMm';
    const inRange = kind === DUAL_KMETER_EXAMPLE_ID ? temperatureInRange : distanceInRange;
    valid = hasFields(state, ['kind',field,'transactions','bytesRead','bytesWritten']) && inRange(state[field])
      && [state.transactions,state.bytesRead,state.bytesWritten].every(nonnegativeCount);
  }
  if (!valid || state.kind !== kind) throw new Error('Invalid QEMU Unit example state');
  return state;
}

export function qemuUnitExampleDistanceCommand(profile, event) {
  if (profile.unitExample !== 'ultrasonic-i2c' || !hasFields(event, ['type','millimeters'])
    || event.type !== 'example-distance' || !distanceInRange(event.millimeters)) {
    throw new Error('Distance input is not admitted by the selected QEMU Unit example');
  }
  const readback = qemuUnitExampleQueries(profile).distanceMm;
  return {execute:'qom-set',arguments:{...readback.arguments,value:event.millimeters},readback,readbackResult:'distanceMm'};
}

export function qemuUnitExampleTemperatureCommand(profile, event) {
  if (profile.unitExample !== DUAL_KMETER_EXAMPLE_ID || !hasFields(event, ['type','temperatureCentiC'])
    || event.type !== 'example-temperature' || !temperatureInRange(event.temperatureCentiC)) {
    throw new Error('Temperature input is not admitted by the selected QEMU Unit example');
  }
  const readback = qemuUnitExampleQueries(profile).temperatureCentiC;
  return {execute:'qom-set',arguments:{...readback.arguments,value:event.temperatureCentiC},readback,readbackResult:'temperatureCentiC'};
}
