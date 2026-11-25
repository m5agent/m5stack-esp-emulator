export const GNSS_EXAMPLE_ID = 'cardputer-adv-cap-gnss';
const workbenchSha256 = 'b6255f6af5ad10236380eae09a76b44ca174b5c4de391aef16413bdc590952bd';
const fixtures = {
  'position-a': [
    '$GNGGA,123519.00,4807.0380,N,01131.0000,E,1,09,0.9,546.0,M,46.9,M,,*71\r\n',
    '$GNRMC,123519.00,A,4807.0380,N,01131.0000,E,0.6,309.6,250426,,,A*42\r\n',
  ],
  'position-b': [
    '$GNGGA,163347.00,3351.5400,S,15112.5940,E,1,09,0.9,546.0,M,46.9,M,,*6C\r\n',
    '$GNRMC,163347.00,A,3351.5400,S,15112.5940,E,0.6,309.6,250426,,,A*5F\r\n',
  ],
};

export function supportsQemuGnssWorkbench(row) {
  return row?.deviceId==='cardputer-adv' && row.firmwareSHA256===workbenchSha256;
}

export function validateQemuGnssExample(profile) {
  if (profile?.gnssExample !== GNSS_EXAMPLE_ID || profile.deviceId !== 'cardputer-adv'
    || profile.board !== 'm5cardputeradv' || profile.chip !== 'esp32s3' || profile.flashMb !== 8
    || profile.clockDivisor !== 1 || profile.oneInsnPerTb !== true
    || profile.firmwareVariant?.fixture !== 'uiflow-workbench-v1'
    || profile.firmwareVariant.firmwareSHA256 !== workbenchSha256
    || profile.readyFirmwareSHA256 !== workbenchSha256) {
    throw new Error('Invalid Cardputer-Adv GNSS example profile');
  }
}

export function bindQemuGnssExample(profile, exampleId, inputSha256) {
  if (exampleId === undefined) return profile;
  if (inputSha256 !== workbenchSha256) throw new Error('Cardputer-Adv GNSS requires its verified UIFlow2 firmware');
  const bound = {...profile, gnssExample:exampleId};
  validateQemuGnssExample(bound);
  return bound;
}

export function qemuGnssFixBytes(profile, fix) {
  validateQemuGnssExample(profile);
  if (typeof fix !== 'string' || !Object.hasOwn(fixtures,fix)) throw new Error('Unknown GNSS example position');
  return new TextEncoder().encode(fixtures[fix].join('').repeat(3));
}
