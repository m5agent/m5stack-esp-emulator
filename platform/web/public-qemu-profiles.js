import {assetUrl, siteRoot} from './public-config.js';

export const QEMU_BROWSER_SOURCE_COMMIT = '40edccac415693c5130f91c01d84176ae6008566';
const MIB = 1024 * 1024;
const identity = /^[a-f0-9]{64}$/;
const S3_ADC_CALIBRATION_FIELDS = Object.freeze([
  [2, 128, 2, 1], [2, 149, 8, 0], [2, 157, 6, 0], [2, 163, 6, 0],
  [2, 169, 6, 0], [2, 175, 8, 0], [2, 183, 6, 0], [2, 189, 6, 0],
  [2, 195, 6, 0], [2, 201, 8, 79], [2, 209, 8, 96], [2, 217, 8, 66],
  [2, 225, 8, 223], [2, 233, 8, 40], [2, 241, 7, 10], [2, 248, 7, 20],
  [1, 186, 6, 15],
].map(row => Object.freeze(row)));
function check(ok, message) { if (!ok) throw new Error(message); }

/** Validate the narrow browser bridge contract, including iframe messages. */
export function validateQemuProfile(profile) {
  check(profile && /^[a-z0-9-]+$/.test(profile.deviceId) && /^m5[a-z0-9]+$/.test(profile.board), 'Invalid QEMU browser board');
  check(profile.target === 'xtensa-softmmu' && ['esp32s3', 'esp32'].includes(profile.chip), 'Unsupported QEMU browser CPU target');
  check(profile.imageChipId === (profile.chip === 'esp32s3' ? 9 : 0), 'QEMU image chip profile mismatch');
  check([4, 8, 16].includes(profile.flashMb) && [0, 2, 4, 8].includes(profile.psramMb), 'Invalid QEMU browser memory profile');
  check(profile.bootloaderOffset === (profile.chip === 'esp32s3' ? 0 : 0x1000) && profile.partitionTableOffset === 0x8000, 'Invalid QEMU merged-image layout');
  const display = profile.display;
  check(display && Number.isInteger(display.width) && display.width > 0 && display.width <= 2048 && Number.isInteger(display.height) && display.height > 0 && display.height <= 2048
    && display.coordinateSpace === 'qemu-physical-frame' && display.hostRotation === 0, 'Invalid QEMU framebuffer coordinate profile');
  check([1, 8].includes(profile.clockDivisor) && /^[a-z0-9-]+$/.test(profile.profile) && ['public', 'candidate'].includes(profile.admission), 'Invalid QEMU execution profile');
  if (profile.accelerator !== undefined) {
    check(profile.clockDivisor === 1 && profile.accelerator?.kind === 'tcg-icount'
      && profile.accelerator.thread === 'single' && profile.accelerator.tbSizeMb === 128
      && profile.accelerator.icountShift === 5, 'Invalid QEMU deterministic accelerator profile');
  }
  check(profile.readyMarker === null && profile.readyFirmwareSHA256 === null || typeof profile.readyMarker === 'string' && profile.readyMarker.length > 0 && profile.readyMarker.length <= 128
    && !/[\x00-\x1f]/.test(profile.readyMarker) && identity.test(profile.readyFirmwareSHA256), 'Invalid QEMU ready marker');
  const names = profile.chip === 'esp32s3' ? ['esp32s3_rev0_rom.bin'] : ['esp32-v3-rom.bin', 'esp32-v3-rom-app.bin'];
  check(Array.isArray(profile.roms) && profile.roms.length === names.length, 'Invalid QEMU ROM profile');
  for (const [index, rom] of profile.roms.entries()) {
    const url = new URL(rom.url);
    check(rom.name === names[index] && identity.test(rom.sha256) && Number.isSafeInteger(rom.bytes) && rom.bytes > 0 && rom.bytes <= 1024 * 1024
      && url.href === `https://raw.githubusercontent.com/espressif/qemu/${QEMU_BROWSER_SOURCE_COMMIT}/pc-bios/${rom.name}` && rom.bundled === false, 'Invalid QEMU ROM identity');
  }
  check(profile.chip === 'esp32' ? profile.efuse === null : profile.efuse?.driver === 'nvram.esp32s3.efuse' && profile.efuse.bytes === 4096 && [0, 1].includes(profile.efuse.packageVersion), 'Invalid QEMU eFuse profile');
  const input = profile.inputs;
  check(input && typeof input.touch === 'boolean' && input.uart === false && input.buttons && typeof input.buttons === 'object'
    && !Array.isArray(input.buttons) && Object.values(input.buttons).every(code => /^[a-z0-9]+$/.test(code)) && Array.isArray(input.keyboard)
    && input.keyboard.every(code => /^[a-z0-9_]+$/.test(code)), 'Invalid QEMU input profile');
  check(input.pir === null || input.pir?.path === '/machine/units/pir' && input.pir.property === 'motion', 'Invalid QEMU Unit endpoint');
  check(profile.units?.schema_version === 1 && Array.isArray(profile.units.attachments)
    && profile.units.attachments.length === (input.pir ? 1 : 0), 'Invalid QEMU Unit wiring');
  if (input.pir) {
    const unit = profile.units.attachments[0];
    check(unit.id === 'pir' && unit.unit_id === 'pir' && unit.port_id === 'port-a' && unit.pins?.yellow === 2 && unit.pins?.white === 1
      && unit.visual_port === 'grove' && unit.initial?.motion === false, 'Unreviewed QEMU PIR wiring');
  }
  const reference = profile.reference;
  const url = new URL(reference?.url);
  check(reference?.kind === 'official-base' && url.protocol === 'https:' && url.hostname === 'm5burner-cdn.m5stack.com' && !url.username && !url.password && !url.search && !url.hash
    && identity.test(reference.sha256) && Number.isSafeInteger(reference.bytes) && reference.bytes > 0 && reference.bytes <= profile.flashMb * MIB, 'Invalid QEMU reference firmware');
  if(profile.fixture?.frameOracle!==undefined){
    const oracle=profile.fixture.frameOracle,r=oracle?.rect;
    check(r && ['x','y','width','height'].every(key=>Number.isInteger(r[key]))
      && r.x>=0 && r.y>=0 && r.width>0 && r.height>0 && r.x+r.width<=display.width && r.y+r.height<=display.height
      && [oracle.before,oracle.after].every(color=>Number.isInteger(color)&&color>=0&&color<=65535)
      && oracle.before!==oracle.after,'Invalid QEMU panel frame oracle');
    check(oracle.encoding===undefined||oracle.encoding==='sdk-quality-pattern-v1'
      && ['papercolor','papermono'].includes(profile.deviceId),'Invalid QEMU panel oracle encoding');
  }
  if(profile.fixture?.logicalDisplay!==undefined){
    check(['width','height'].every(key=>Number.isInteger(profile.fixture.logicalDisplay[key])
      && profile.fixture.logicalDisplay[key]>0 && profile.fixture.logicalDisplay[key]<=2048),'Invalid QEMU logical display');
  }
  for(const key of ['touchPoint','negativeTouchPoint'])if(profile.fixture?.[key]!==undefined){
    const point=profile.fixture[key];
    check(input.touch && Number.isInteger(point.x) && Number.isInteger(point.y)
      && point.x>=0 && point.x<display.width && point.y>=0 && point.y<display.height,'Invalid QEMU fixture touch point');
  }
  if (profile.fixture?.coordinateSource !== undefined) {
    check(profile.deviceId === 'papermono' && input.touch
      && profile.fixture.coordinateSource === 'official-raw-point'
      && profile.fixture.logicalTouchStatus === 'known-sdk-calibration-gap'
      && profile.fixture.releaseCoordinates === 'last-pressed-raw-point', 'Invalid QEMU raw touch fixture');
  }
  if (profile.firmwareProfiles !== undefined) {
    check(Array.isArray(profile.firmwareProfiles) && profile.firmwareProfiles.length <= 16, 'Invalid QEMU firmware execution variants');
    const hashes = new Set(), fields = ['firmwareSHA256', 'profile', 'clockDivisor', 'readyMarker', 'fixture', 'sourceSHA256', 'schedulerCandidate'];
    for (const variant of profile.firmwareProfiles) {
      check(variant && Object.keys(variant).length === fields.length && fields.every(key => Object.hasOwn(variant, key))
        && identity.test(variant.firmwareSHA256) && !hashes.has(variant.firmwareSHA256) && identity.test(variant.sourceSHA256)
        && /^[a-z0-9-]+$/.test(variant.profile) && [1, 8].includes(variant.clockDivisor)
        && typeof variant.readyMarker === 'string' && variant.readyMarker.length > 0 && variant.readyMarker.length <= 128 && !/[\x00-\x1f]/.test(variant.readyMarker)
        && /^[a-z0-9-]+$/.test(variant.fixture) && /^[a-z0-9-]+$/.test(variant.schedulerCandidate), 'Invalid or duplicate QEMU firmware execution variant');
      hashes.add(variant.firmwareSHA256);
    }
  }
  return profile;
}

export function validateQemuBrowserProfiles(registry) {
  check(registry?.schema_version === 1 && registry.engine === 'qemu-wasm' && registry.target === 'xtensa-softmmu'
    && registry.source?.commit === QEMU_BROWSER_SOURCE_COMMIT && Array.isArray(registry.profiles), 'Invalid QEMU browser profile registry');
  const seen = new Set();
  for (const profile of registry.profiles) {
    validateQemuProfile(profile);
    check(!seen.has(profile.deviceId), 'Duplicate QEMU browser profile'); seen.add(profile.deviceId);
  }
  return registry;
}

export async function loadQemuBrowserProfiles({root = siteRoot(), fetchImpl = globalThis.fetch, signal} = {}) {
  const response = await fetchImpl(assetUrl('platform/web/qemu-browser-profiles.json', new URL(root)), {signal, credentials:'omit', referrerPolicy:'no-referrer'});
  check(response.ok, 'QEMU browser profile registry unavailable');
  return validateQemuBrowserProfiles(await response.json());
}

/** A machine in a compiled binary does not by itself admit a browser device. */
export function getQemuBrowserProfile(deviceId, registry, {allowCandidateProfiles = false} = {}) {
  validateQemuBrowserProfiles(registry);
  const profile = registry.profiles.find(row => row.deviceId === deviceId);
  return profile && (profile.admission === 'public' || allowCandidateProfiles) ? structuredClone(profile) : null;
}

/** Only a complete Flash hash selects execution metadata; hardware is fixed. */
export function resolveQemuFirmwareProfile(profile, firmwareSHA256) {
  validateQemuProfile(profile);
  check(identity.test(firmwareSHA256), 'Invalid QEMU firmware SHA256');
  const resolved = structuredClone(profile);
  delete resolved.firmwareVariant;
  const variant = profile.firmwareProfiles?.find(row => row.firmwareSHA256 === firmwareSHA256);
  if (variant) {
    resolved.profile = variant.profile; resolved.clockDivisor = variant.clockDivisor;
    resolved.readyMarker = variant.readyMarker; resolved.readyFirmwareSHA256 = firmwareSHA256;
    resolved.firmwareVariant = structuredClone(variant);
  }
  return resolved;
}

/** Validate a full merged image and return a private, FF-padded Flash copy. */
export function validateQemuFirmware(firmware, profile) {
  validateQemuProfile(profile);
  const bytes = firmware instanceof ArrayBuffer ? new Uint8Array(firmware) : firmware;
  check(bytes instanceof Uint8Array && bytes.length > 0, 'Firmware must be binary data');
  const flashBytes = profile.flashMb * MIB, table = profile.partitionTableOffset;
  check(bytes.length <= flashBytes, 'Firmware exceeds selected Flash capacity');
  check(bytes.length > table + 32, 'Complete merged firmware is required');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const image = (at, end) => {
    check(at + 24 <= end && bytes[at] === 0xe9 && bytes[at + 1] > 0 && bytes[at + 1] <= 16, 'Invalid or truncated ESP image');
    check(view.getUint16(at + 12, true) === profile.imageChipId, 'Firmware chip does not match selected QEMU profile');
    let offset = at + 24;
    for (let segment = 0; segment < bytes[at + 1]; segment++) {
      check(offset + 8 <= end, 'Truncated ESP segment header');
      const length = view.getUint32(offset + 4, true); offset += 8;
      check(length <= end - offset, 'Truncated ESP segment'); offset += length;
    }
  };
  image(profile.bootloaderOffset, table);
  check(view.getUint16(table, true) === 0x50aa, 'Merged firmware lacks its partition table');
  let applications = 0;
  for (let at = table; at + 32 <= Math.min(bytes.length, table + 0x1000); at += 32) {
    if (view.getUint16(at, true) !== 0x50aa) break;
    const offset = view.getUint32(at + 4, true), size = view.getUint32(at + 8, true);
    check(size > 0 && offset >= table + 0x1000 && offset <= flashBytes && size <= flashBytes - offset, 'Partition exceeds selected Flash');
    if (bytes[at + 2] === 0 && offset < bytes.length && bytes[offset] === 0xe9) { image(offset, Math.min(bytes.length, offset + size)); applications++; }
  }
  check(applications > 0, 'Merged firmware lacks a complete application');
  const flash = new Uint8Array(flashBytes); flash.fill(255); flash.set(bytes); return flash;
}

export function buildQemuArguments(profile) {
  validateQemuProfile(profile);
  const args = ['-M', profile.board, '-drive', 'file=/flash.bin,if=mtd,format=raw', '-L', '/rom', '-display', 'none',
    '-serial', 'file:/bridge/uart.out', '-serial', 'file:/bridge/serial1', '-qmp', 'stdio'];
  if (profile.efuse) args.push('-drive', 'if=none,id=efuse,file=/efuse.bin,format=raw', '-global', `driver=${profile.efuse.driver},property=drive,value=efuse`);
  if (profile.accelerator) args.push('-accel',
    `tcg,thread=${profile.accelerator.thread},tb-size=${profile.accelerator.tbSizeMb}`,
    '-icount', `shift=${profile.accelerator.icountShift},align=off,sleep=off`);
  return args;
}

export function buildQemuEfuse(profile) {
  validateQemuProfile(profile);
  if (!profile.efuse) return null;
  const bytes = new Uint8Array(profile.efuse.bytes);
  new DataView(bytes.buffer).setUint32(36, profile.efuse.packageVersion << 21, true);
  if (profile.chip === 'esp32s3') {
    // Synthetic calibration populated on production S3 silicon. It keeps
    // ESP-IDF's curve-fitting ADC path usable in QEMU without fabricating a
    // physical measurement or changing identity/security eFuse fields.
    const blockOffsets = [0, 24, 48];
    for (const [block, bitStart, bitCount, value] of S3_ADC_CALIBRATION_FIELDS) {
      for (let bit = 0; bit < bitCount; bit++) {
        const at = blockOffsets[block] * 8 + bitStart + bit;
        const mask = 1 << (at & 7);
        if ((value >> bit) & 1) bytes[at >> 3] |= mask;
        else bytes[at >> 3] &= ~mask;
      }
    }
  }
  return bytes;
}

/** Coordinates are already in the QEMU physical frame; do not rotate twice. */
export function qemuInputCommand(profile, event) {
  validateQemuProfile(profile);
  const input = profile.inputs, {width, height} = profile.display;
  if (event?.type === 'touch') {
    check(input.touch && Number.isInteger(event.x) && event.x >= 0 && event.x < width && Number.isInteger(event.y) && event.y >= 0 && event.y < height && typeof event.down === 'boolean', 'Touch is unsupported or outside the selected framebuffer');
    return {execute:'input-send-event', arguments:{events:[
      {type:'abs',data:{axis:'x',value:Math.ceil(event.x * 32767 / Math.max(1, width - 1))}},
      {type:'abs',data:{axis:'y',value:Math.ceil(event.y * 32767 / Math.max(1, height - 1))}},
      {type:'btn',data:{button:'left',down:event.down}},
    ]}};
  }
  if (event?.type === 'button' || event?.type === 'key') {
    // The shared 3D/fallback shell normalizes controls and keyboard keys to
    // qcodes on its control event before public.js calls this bridge.
    const code = event.type === 'button' ? Object.hasOwn(input.buttons, event.id) ? input.buttons[event.id] : input.keyboard.includes(event.id) && event.id
      : input.keyboard.includes(event.key) && event.key;
    const down = event.down ?? event.pressed;
    check(code && typeof down === 'boolean', 'Keyboard/button input is not admitted by the selected profile');
    return {execute:'input-send-event',arguments:{events:[{type:'key',data:{down,key:{type:'qcode',data:code}}}]}};
  }
  if (event?.type === 'pir') {
    check(input.pir && typeof event.motion === 'boolean', 'PIR is not attached to the selected profile');
    return {execute:'qom-set',arguments:{...input.pir,value:event.motion},readback:{execute:'qom-get',arguments:{...input.pir}}};
  }
  throw new Error('Input is not admitted by the selected QEMU browser profile');
}
