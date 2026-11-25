// Only these two original CoreS3 example BINs have a reviewed browser Unit route.
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
export function resolveQemuUnitExample(profile, firmwareInputSHA256) {
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
const nonnegativeCount = value => Number.isSafeInteger(value) && value >= 0;

/** Read only fixed properties backed by the virtual I2C chip or GPIO listener. */
export function qemuUnitExampleQueries(profile) {
  if (profile?.unitExample === undefined) return {};
  validateQemuUnitExampleProfile(profile);
  if (profile.unitExample === 'relay') {
    return {level:get(relayPath, 'output-level'),transitions:get(relayPath, 'output-transitions')};
  }
  return {distanceMm:get(ultrasonicPath, 'distance-mm'),transactions:get(ultrasonicChip, 'transactions'),
    bytesRead:get(ultrasonicChip, 'read-bytes'),bytesWritten:get(ultrasonicChip, 'written-bytes')};
}

export function validateQemuUnitExampleState(profile, state) {
  validateQemuUnitExampleProfile(profile);
  const valid = profile.unitExample === 'relay'
    ? hasFields(state, ['kind','level','transitions']) && typeof state.level === 'boolean' && nonnegativeCount(state.transitions)
    : hasFields(state, ['kind','distanceMm','transactions','bytesRead','bytesWritten']) && distanceInRange(state.distanceMm)
      && [state.transactions,state.bytesRead,state.bytesWritten].every(nonnegativeCount);
  if (!valid || state.kind !== profile.unitExample) throw new Error('Invalid QEMU Unit example state');
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
