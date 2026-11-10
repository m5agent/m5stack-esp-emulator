import {validateQemuServoOutputProfile,validateQemuServoState} from './public-qemu-servo.js';
import {assetUrl, siteRoot} from './public-config.js';

export const QEMU_BROWSER_SOURCE_COMMIT = '40edccac415693c5130f91c01d84176ae6008566';
export const QEMU_C61_BROWSER_SOURCE_COMMIT = '8fd40d7f1a5151c1747375b920c3e2d5cff0b0dc';
const C61_BOARD = 'esp32c61,m5corematrix=on';
export const CORE_MATRIX_STOCK_FLASH_SHA256 = '5562f685a8f3ed07d04ec7d7f58fa4435be8438fbf135c6fd61ff6e906783c07';
export const ATOM_MATRIX_WORKBENCH_FLASH_SHA256 = 'f553ad2c9d84e22591d8da8d32a7517c9e378eb5439214a9e0b2075bf31844ed';
export const ATOM_MATRIX_ICOUNT_MAX_PER_CPU_NS = 10000;

export function qemuRuntimeIdentity(profile) {
  return profile.target === 'riscv32-softmmu'
    ? {directory:'qemu-c61',commit:QEMU_C61_BROWSER_SOURCE_COMMIT}
    : {directory:'qemu',commit:QEMU_BROWSER_SOURCE_COMMIT};
}
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

export const QEMU_ONE_INSN_RUNTIME_PATCH = Object.freeze({
  path:'patches/qemu-wasm-probe/0027-gpio-bounded-transactions.patch',
  sha256:'43685da86d9b959b2e769cd9cda5785a5c4039b5076f73f3b9d6033d1d161bdf',
});
export const QEMU_ICOUNT_FAIRNESS_RUNTIME_PATCH = Object.freeze({
  path:'patches/qemu-wasm-probe/0038-icount-percpu-fairness-cap.patch',
  sha256:'7942e09a3459c768d7c76bada20bc808b3142c7421465c2db40037680434a49b',
});
export const QEMU_CARDPUTER_BOOT_RUNTIME_PATCH = Object.freeze({
  path:'patches/qemu-wasm-probe/0029-cardputer-adv-boot-button.patch',
  sha256:'04d7a7e5b29e3e3b4729fb14520afe43e422f0df5371c9fcbbfde5644de88b85',
});
const QEMU_CARDPUTER_K132_RUNTIME_PATCH = Object.freeze({
  path:'patches/qemu-wasm-probe/0034-cardputer-k132-board.patch',
  sha256:'6c854c75cfd248ff145a794240212a8a1de017113d9d72360b9a844181ab40af',
});
const variantFields = ['firmwareSHA256', 'profile', 'clockDivisor', 'readyMarker', 'fixture', 'sourceSHA256', 'schedulerCandidate'];
const variantOptions = ['oneInsnPerTb', 'requiredRuntimePatch', 'sourceKind'];
// Published BIN provenance is distinct from a matching source-code revision.
// Full Flash hashes admit execution; sourceSHA256 identifies the unpadded BIN.
const publishedFirmwareVariants = Object.freeze([
  {deviceId:'stopwatch',board:'m5stopwatch',fixture:'stopwatch-vendor-factory-ff-pad-v1',
    firmwareSHA256:'d231d8523c8b448e8b920777d298c575989dbafc57fc3f432851bcaeb61b1898',
    sourceSHA256:'6395799089341e0ae96072c2a3418d469d6797b2ab8ee0cab1c9ed24a42acbbe'},
]);
function validateRuntimePatch(patch) {
  check(patch && Object.keys(patch).length === 2
    && patch.path === QEMU_ONE_INSN_RUNTIME_PATCH.path && patch.sha256 === QEMU_ONE_INSN_RUNTIME_PATCH.sha256,
    'Invalid QEMU required runtime patch');
}
function validateFirmwareVariant(variant, profile) {
  check(variant && variantFields.every(key => Object.hasOwn(variant,key))
    && Object.keys(variant).every(key => variantFields.includes(key) || variantOptions.includes(key))
    && identity.test(variant.firmwareSHA256) && identity.test(variant.sourceSHA256)
    && /^[a-z0-9-]+$/.test(variant.profile) && [1,6,8].includes(variant.clockDivisor)
    && /^[a-z0-9-]+$/.test(variant.fixture) && /^[a-z0-9-]+$/.test(variant.schedulerCandidate), 'Invalid QEMU firmware execution variant');
  const published = Object.hasOwn(variant,'sourceKind');
  if (published) {
    check(variant.sourceKind === 'published-firmware-binary' && variant.readyMarker === null
      && variant.oneInsnPerTb === true && variant.clockDivisor === 1
      && variant.schedulerCandidate === 'qemu-tci-mmio-blocks-v1'
      && profile.chip === 'esp32s3' && profile.flashMb === 16 && profile.psramMb === 8
      && publishedFirmwareVariants.some(row => row.deviceId === profile.deviceId && row.board === profile.board
        && ['firmwareSHA256','sourceSHA256','fixture'].every(key => row[key] === variant[key])),
      'Invalid QEMU published firmware binary provenance');
  } else {
    check(typeof variant.readyMarker === 'string' && variant.readyMarker.length > 0 && variant.readyMarker.length <= 128
      && !/[\x00-\x1f]/.test(variant.readyMarker)
      && !publishedFirmwareVariants.some(row => row.firmwareSHA256 === variant.firmwareSHA256 || row.fixture === variant.fixture),
      'Invalid QEMU source-code firmware ready marker or provenance');
  }
  const oneInsn = Object.hasOwn(variant,'oneInsnPerTb'), requiredPatch = Object.hasOwn(variant,'requiredRuntimePatch');
  check(oneInsn === requiredPatch && (!oneInsn || variant.oneInsnPerTb === true && variant.clockDivisor === 1),
    'Invalid QEMU one-instruction firmware variant');
  if (requiredPatch) validateRuntimePatch(variant.requiredRuntimePatch);
}

/** Execution metadata may require a source patch absent from an older cache. */
export function validateQemuRuntimeRequirements(profile, manifest) {
  validateQemuProfile(profile);
  if (profile.accelerator?.icountMaxPerCpuNs !== undefined) {
    const patches=manifest?.source?.patches;
    const matches=Array.isArray(patches)?patches.filter(row=>row?.path===QEMU_ICOUNT_FAIRNESS_RUNTIME_PATCH.path):[];
    check(matches.length===1&&matches[0].sha256===QEMU_ICOUNT_FAIRNESS_RUNTIME_PATCH.sha256,
      'QEMU runtime lacks the required per-CPU icount scheduling patch');
  }
  if (profile.oneInsnPerTb === true) {
    const patches = manifest?.source?.patches;
    const matches = Array.isArray(patches) ? patches.filter(row => row?.path === profile.requiredRuntimePatch.path) : [];
    check(matches.length === 1 && matches[0].sha256 === profile.requiredRuntimePatch.sha256,
      'QEMU runtime lacks the firmware variant required source patch');
  }
  if (profile.requiredInputPatch !== undefined) {
    const patches=manifest?.source?.patches;
    const matches=Array.isArray(patches)?patches.filter(row=>row?.path===profile.requiredInputPatch.path):[];
    check(matches.length===1&&matches[0].sha256===profile.requiredInputPatch.sha256,
      'QEMU runtime lacks the physical input required source patch');
  }
  return profile;
}

/** Validate the narrow browser bridge contract, including iframe messages. */
export function validateQemuProfile(profile) {
  const c61 = profile?.target === 'riscv32-softmmu';
  check(profile && /^[a-z0-9-]+$/.test(profile.deviceId) && (c61
    ? profile.deviceId === 'corematrix' && profile.board === C61_BOARD
    : /^m5[a-z0-9]+$/.test(profile.board)), 'Invalid QEMU browser board');
  check(c61 ? profile.chip === 'esp32c61'
    : profile.target === 'xtensa-softmmu' && ['esp32s3', 'esp32'].includes(profile.chip), 'Unsupported QEMU browser CPU target');
  check(profile.imageChipId === (c61 ? 20 : profile.chip === 'esp32s3' ? 9 : 0), 'QEMU image chip profile mismatch');
  check([4, 8, 16].includes(profile.flashMb) && [0, 2, 4, 8].includes(profile.psramMb), 'Invalid QEMU browser memory profile');
  check(profile.bootloaderOffset === (profile.chip === 'esp32' ? 0x1000 : 0) && profile.partitionTableOffset === 0x8000, 'Invalid QEMU merged-image layout');
  const display = profile.display;
  if (c61) {
    check((profile.stockFirmwareSHA256 === CORE_MATRIX_STOCK_FLASH_SHA256
        || profile.admission === 'candidate' && profile.stockFirmwareSHA256 === undefined)
      && profile.flashMb === 16 && profile.psramMb === 0
      && display?.width === 16 && display?.height === 16 && profile.clockDivisor === 1
      && profile.efuse === null && !profile.outputs, 'Invalid CoreMatrix browser profile');
  }
  if (display === null) {
    const output=profile.outputs, matrix=['atom-matrix','atom-matrix-v11'].includes(profile.deviceId);
    const identity=profile.deviceId==='atoms3-lite'&&profile.board==='m5atoms3lite'&&profile.chip==='esp32s3'&&profile.flashMb===8
      || profile.deviceId==='atom-lite'&&profile.board==='m5atomlite'&&profile.chip==='esp32'&&profile.flashMb===4
      || matrix&&profile.chip==='esp32'&&profile.flashMb===4
        &&profile.board===({'atom-matrix':'m5atommatrix','atom-matrix-v11':'m5atommatrixv11'}[profile.deviceId]);
    check(identity&&profile.psramMb===0&&output&&Object.keys(output).length===(matrix?6:5)
      && output.kind===(matrix?'matrix-ws2812-qom-v1':'single-ws2812-qom-v1')&&output.path==='/machine/onboard_io'
      && Array.isArray(output.properties)&&output.properties.length===3
      && output.properties.every((property,index)=>property===['led-rgb','led-frames','pressed'][index])
      &&output.buttonTarget==='button'&&(matrix?output.spatialMapping==='uniform-only-v1'
        &&Array.isArray(output.ledTargets)&&output.ledTargets.length===25
        &&output.ledTargets.every((target,index)=>target===`led${index}`):output.ledTarget==='rgb'), 'Invalid QEMU headless output profile');
  } else {
    check(display && Number.isInteger(display.width) && display.width > 0 && display.width <= 2048 && Number.isInteger(display.height) && display.height > 0 && display.height <= 2048
      && display.coordinateSpace === 'qemu-physical-frame' && display.hostRotation === 0, 'Invalid QEMU framebuffer coordinate profile');
    if (profile.outputs !== undefined) validateQemuServoOutputProfile(profile);
  }
  const clockDivisors = profile.firmwareVariant ? [1, 6, 8] : [1, 8];
  check(clockDivisors.includes(profile.clockDivisor) && /^[a-z0-9-]+$/.test(profile.profile) && ['public', 'candidate'].includes(profile.admission), 'Invalid QEMU execution profile');
  if (profile.firmwareVariant) {
    validateFirmwareVariant(profile.firmwareVariant,profile);
    const variant = profile.firmwareVariant, known = profile.firmwareProfiles?.find(row => row.firmwareSHA256 === variant.firmwareSHA256);
    check(profile.firmwareVariant.profile === profile.profile
      && profile.firmwareVariant.clockDivisor === profile.clockDivisor
      && profile.firmwareVariant.readyMarker === profile.readyMarker
      && profile.readyFirmwareSHA256 === profile.firmwareVariant.firmwareSHA256
      && known && [...variantFields,...variantOptions].every(key => Object.hasOwn(known,key) === Object.hasOwn(variant,key)
        && (key === 'requiredRuntimePatch' || known[key] === variant[key])),
      'Invalid resolved QEMU firmware variant');
  }
  const oneInsn = Object.hasOwn(profile,'oneInsnPerTb'), requiredPatch = Object.hasOwn(profile,'requiredRuntimePatch');
  check(oneInsn === requiredPatch && (!oneInsn || profile.oneInsnPerTb === true
    && profile.clockDivisor === 1 && profile.accelerator === undefined
    && profile.firmwareVariant?.oneInsnPerTb === true && identity.test(profile.readyFirmwareSHA256)),
    'Invalid QEMU one-instruction execution binding');
  check(profile.firmwareVariant?.oneInsnPerTb !== true || oneInsn, 'Missing QEMU one-instruction execution binding');
  if (requiredPatch) validateRuntimePatch(profile.requiredRuntimePatch);
  if (profile.accelerator !== undefined) {
    const cap=Object.hasOwn(profile.accelerator||{},'icountMaxPerCpuNs');
    check(profile.clockDivisor === 1 && profile.accelerator && Object.keys(profile.accelerator).length === (cap?5:4)
        && profile.accelerator.kind === 'tcg-icount'
        && profile.accelerator.thread === 'single' && profile.accelerator.tbSizeMb === 128
        && profile.accelerator.icountShift === 5, 'Invalid QEMU deterministic accelerator profile');
    check(!cap || profile.deviceId==='atom-matrix' && profile.board==='m5atommatrix'
      && profile.profile==='atom-matrix-wasm-deterministic-icount'
      && profile.readyFirmwareSHA256===ATOM_MATRIX_WORKBENCH_FLASH_SHA256
      && profile.accelerator.icountMaxPerCpuNs===ATOM_MATRIX_ICOUNT_MAX_PER_CPU_NS,
      'Invalid QEMU per-CPU icount scheduling binding');
  }
  const publishedWithoutMarker = profile.firmwareVariant?.sourceKind === 'published-firmware-binary'
    && profile.readyMarker === null && profile.readyFirmwareSHA256 === profile.firmwareVariant.firmwareSHA256;
  check(profile.readyMarker === null && profile.readyFirmwareSHA256 === null || publishedWithoutMarker
    || typeof profile.readyMarker === 'string' && profile.readyMarker.length > 0 && profile.readyMarker.length <= 128
    && !/[\x00-\x1f]/.test(profile.readyMarker) && identity.test(profile.readyFirmwareSHA256), 'Invalid QEMU ready marker');
  const names = c61 ? ['esp32c61-rom.bin'] : profile.chip === 'esp32s3' ? ['esp32s3_rev0_rom.bin'] : ['esp32-v3-rom.bin', 'esp32-v3-rom-app.bin'];
  const {commit} = qemuRuntimeIdentity(profile);
  check(Array.isArray(profile.roms) && profile.roms.length === names.length, 'Invalid QEMU ROM profile');
  for (const [index, rom] of profile.roms.entries()) {
    const url = new URL(rom.url);
    check(rom.name === names[index] && identity.test(rom.sha256) && Number.isSafeInteger(rom.bytes) && rom.bytes > 0 && rom.bytes <= 1024 * 1024
      && url.href === `https://raw.githubusercontent.com/espressif/qemu/${commit}/pc-bios/${rom.name}` && rom.bundled === false, 'Invalid QEMU ROM identity');
  }
  const classicEfuse = profile.deviceId === 'stickc-plus2' && profile.board === 'm5stickcplus2'
    && profile.flashMb === 8 && profile.psramMb === 2 && profile.efuse?.driver === 'nvram.esp32.efuse'
    && profile.efuse.bytes === 4096 && profile.efuse.packageVersion === 6;
  const classicCompactEfuse = (profile.deviceId === 'stickc' && profile.board === 'm5stickc'
      && display?.width === 80 && display?.height === 160
    || profile.deviceId === 'stickc-plus' && profile.board === 'm5stickcplus'
      && display?.width === 135 && display?.height === 240
    || profile.deviceId === 'stickc-plus-se' && profile.board === 'm5stickcplusse'
      && display?.width === 135 && display?.height === 240)
    && profile.flashMb === 4 && profile.psramMb === 0 && profile.efuse?.driver === 'nvram.esp32.efuse'
    && profile.efuse.bytes === 4096 && profile.efuse.packageVersion === 5;
  const classicHeadlessEfuse = ['atom-lite','atom-matrix','atom-matrix-v11'].includes(profile.deviceId)
    && display===null&&profile.efuse?.driver==='nvram.esp32.efuse'&&profile.efuse.bytes===4096&&profile.efuse.packageVersion===5;
  const classicNoEfuse = profile.deviceId === 'core2' && profile.board === 'm5core2' && profile.efuse === null;
  check(c61 || (profile.chip === 'esp32' ? classicNoEfuse || classicEfuse || classicCompactEfuse || classicHeadlessEfuse
    : profile.efuse?.driver === 'nvram.esp32s3.efuse' && profile.efuse.bytes === 4096 && [0, 1].includes(profile.efuse.packageVersion)), 'Invalid QEMU eFuse profile');
  if (display === null) check(profile.efuse.packageVersion === (profile.chip==='esp32'?5:0), 'Invalid QEMU headless eFuse package');
  const input = profile.inputs;
  check(input?.reset === undefined || input.reset === true, 'Invalid hardware reset admission');
  if (input?.capacitiveTouch !== undefined) check(profile.deviceId === 'stackchan' && profile.board === 'm5stackchan'
    && Object.keys(input.capacitiveTouch).length === 3
    && input.capacitiveTouch.path === '/machine/si12t' && input.capacitiveTouch.property === 'touch-bits'
    && Array.isArray(input.capacitiveTouch.masks) && input.capacitiveTouch.masks.length === 3
    && input.capacitiveTouch.masks.every((mask,index) => mask === [48,12,3][index]), 'Invalid StackChan body touch route');
  check(input && typeof input.touch === 'boolean' && typeof input.uart === 'boolean' && input.buttons && typeof input.buttons === 'object'
    && !Array.isArray(input.buttons) && Object.values(input.buttons).every(code => /^[a-z0-9]+$/.test(code)) && Array.isArray(input.keyboard)
    && input.keyboard.every(code => /^[a-z0-9_]+$/.test(code)), 'Invalid QEMU input profile');
  if (c61) check(!input.touch && input.uart && input.pir === null && !input.keyboard.length
    && Object.keys(input.buttons).sort().join(',') === 'a,b,c'
    && ['a','b','c'].every(key => input.buttons[key] === key), 'Invalid CoreMatrix browser input route');
  const bootInput=Object.hasOwn(input.buttons,'boot');
  const originalCardputer=profile.deviceId==='cardputer';
  if(bootInput||originalCardputer||profile.requiredInputPatch!==undefined){
    const patch=profile.requiredInputPatch;
    const expectedPatch=originalCardputer?QEMU_CARDPUTER_K132_RUNTIME_PATCH:QEMU_CARDPUTER_BOOT_RUNTIME_PATCH;
    const boardMatches=originalCardputer
      ? profile.board==='m5cardputer'&&profile.chip==='esp32s3'&&profile.flashMb===8&&profile.psramMb===0
        &&display?.width===240&&display.height===135&&input.buttons.f12==='f12'
      : profile.deviceId==='cardputer-adv'&&profile.board==='m5cardputeradv';
    check(boardMatches&&bootInput
      &&input.buttons.boot==='f12'&&!input.keyboard.includes('f12')
      &&patch&&Object.keys(patch).length===2
      &&patch.path===expectedPatch.path&&patch.sha256===expectedPatch.sha256,
      'Invalid QEMU physical input patch binding');
  }
  if (display === null) check(!input.touch && input.pir === null && input.keyboard.length === 0
    && Object.keys(input.buttons).sort().join(',') === 'a,button' && Object.values(input.buttons).every(code => code === 'a'), 'Invalid QEMU headless input profile');
  if (input.encoder !== undefined) {
    const encoder = input.encoder;
    check(profile.deviceId === 'dial' && profile.board === 'm5dial' && profile.chip === 'esp32s3'
      && profile.flashMb === 8 && profile.psramMb === 0 && encoder && Object.keys(encoder).length === 4
      && encoder.path === '/machine/encoder' && encoder.property === 'detents'
      && encoder.minimum === -4096 && encoder.maximum === 4096, 'Invalid QEMU encoder endpoint');
  }
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
    check(display && r && ['x','y','width','height'].every(key=>Number.isInteger(r[key]))
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
    const hashes = new Set();
    for (const variant of profile.firmwareProfiles) {
      validateFirmwareVariant(variant,profile);
      check(!hashes.has(variant.firmwareSHA256) && (!variant.oneInsnPerTb || profile.accelerator === undefined),
        'Invalid or duplicate QEMU firmware execution variant');
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
  delete resolved.oneInsnPerTb; delete resolved.requiredRuntimePatch;
  if (resolved.accelerator?.icountMaxPerCpuNs !== undefined) delete resolved.accelerator.icountMaxPerCpuNs;
  const variant = profile.firmwareProfiles?.find(row => row.firmwareSHA256 === firmwareSHA256);
  if (variant) {
    resolved.profile = variant.profile; resolved.clockDivisor = variant.clockDivisor;
    resolved.readyMarker = variant.readyMarker; resolved.readyFirmwareSHA256 = firmwareSHA256;
    resolved.firmwareVariant = structuredClone(variant);
    if (variant.oneInsnPerTb === true) {
      resolved.oneInsnPerTb = true; resolved.requiredRuntimePatch = structuredClone(variant.requiredRuntimePatch);
    }
  }
  return validateQemuProfile(resolved);
}

/** A diagnostic override cannot inherit an admitted variant's execution flags. */
export function clearQemuFirmwareExecutionBinding(profile) {
  delete profile.firmwareVariant; delete profile.oneInsnPerTb; delete profile.requiredRuntimePatch;
  if (profile.accelerator?.icountMaxPerCpuNs !== undefined) delete profile.accelerator.icountMaxPerCpuNs;
  // A publisher BIN with no app-ready marker must not retain a ready identity
  // outside its explicit provenance branch. Real source-code markers remain.
  if (profile.readyMarker === null) profile.readyFirmwareSHA256 = null;
  return profile;
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
  // C61 exposes three hardware UARTs before the USB Serial/JTAG chardev.
  // Keep ROM UART diagnostics and the stock MicroPython USB input distinct.
  const serials = profile.target === 'riscv32-softmmu'
    ? ['file:/bridge/uart.out','file:/bridge/serial1','null','pipe:/bridge/usb']
    : [profile.inputs.uart?'pipe:/bridge/uart':'file:/bridge/uart.out','file:/bridge/serial1'];
  const args = ['-M', profile.board, '-drive', 'file=/flash.bin,if=mtd,format=raw', '-L', '/rom', '-display', 'none',
    ...serials.flatMap(device=>['-serial',device]), '-qmp', 'stdio'];
  if (profile.efuse) args.push('-drive', 'if=none,id=efuse,file=/efuse.bin,format=raw', '-global', `driver=${profile.efuse.driver},property=drive,value=efuse`);
  if (profile.oneInsnPerTb === true) {
    args.push('-accel', 'tcg,thread=multi,one-insn-per-tb=on');
  } else if (profile.accelerator) {
    args.push('-accel', `tcg,thread=${profile.accelerator.thread},tb-size=${profile.accelerator.tbSizeMb}`);
    if (profile.accelerator.kind === 'tcg-icount') args.push('-icount', `shift=${profile.accelerator.icountShift},align=off,sleep=off`);
  }
  return args;
}

export function buildQemuEfuse(profile) {
  validateQemuProfile(profile);
  if (!profile.efuse) return null;
  const bytes = new Uint8Array(profile.efuse.bytes);
  const offset = profile.chip === 'esp32' ? 12 : 36, shift = profile.chip === 'esp32' ? 9 : 21;
  new DataView(bytes.buffer).setUint32(offset, profile.efuse.packageVersion << shift, true);
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
  const input = profile.inputs, {width, height} = profile.display || {};
  if (event?.type === 'reset') {
    check(input.reset === true && event.down === true && Object.keys(event).sort().join(',') === 'down,type', 'Hardware reset is not admitted');
    return {execute:'system_reset',arguments:{}};
  }
  if (event?.type === 'capacitive-touch') {
    const touch=input.capacitiveTouch;
    check(touch && Number.isInteger(event.zone) && event.zone>=1 && event.zone<=3 && typeof event.down === 'boolean'
      && Object.keys(event).sort().join(',')==='down,type,zone', 'Capacitive touch is not admitted');
    return {bitInput:{path:touch.path,property:touch.property,mask:touch.masks[event.zone-1],down:event.down}};
  }
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
  if (event?.type === 'encoder') {
    const endpoint = input.encoder;
    check(endpoint && Object.keys(event).sort().join(',') === 'detents,type'
      && Number.isInteger(event.detents) && event.detents >= endpoint.minimum
      && event.detents <= endpoint.maximum, 'Encoder target is not admitted by the selected QEMU profile');
    const target = {path:endpoint.path, property:endpoint.property};
    return {execute:'qom-set', arguments:{...target, value:event.detents},
      readback:{execute:'qom-get', arguments:target}, readbackResult:'detents'};
  }
  if (event?.type === 'pir') {
    check(input.pir && typeof event.motion === 'boolean', 'PIR is not attached to the selected profile');
    return {execute:'qom-set',arguments:{...input.pir,value:event.motion},readback:{execute:'qom-get',arguments:{...input.pir}}};
  }
  throw new Error('Input is not admitted by the selected QEMU browser profile');
}

/** Convert the reviewed visual Dial ring gesture to a physical input target.
 * The 16 positions per turn are the model's UI gesture scale, not measured
 * encoder waveform timing. The guest alone owns its RotaryIRQ counter.
 */
export function advanceQemuEncoderTarget(profile, state, deltaDegrees) {
  validateQemuProfile(profile);
  const endpoint = profile.inputs.encoder, degreesPerPosition = 360 / 16;
  check(endpoint && state && Object.keys(state).sort().join(',') === 'remainderDegrees,target'
    && Number.isInteger(state.target) && state.target >= endpoint.minimum && state.target <= endpoint.maximum
    && Number.isFinite(state.remainderDegrees) && Math.abs(state.remainderDegrees) < degreesPerPosition
    && Number.isFinite(deltaDegrees) && Math.abs(deltaDegrees) <= 180, 'Invalid QEMU encoder gesture');
  const angle = state.remainderDegrees + deltaDegrees, steps = Math.trunc(angle / degreesPerPosition);
  const target = state.target + steps;
  check(target >= endpoint.minimum && target <= endpoint.maximum, 'QEMU encoder gesture exceeds its physical target range');
  return {state:{target, remainderDegrees:angle - steps * degreesPerPosition},
    command:steps ? {type:'encoder', detents:target} : null};
}

/** A fixed read-only observation path; callers cannot supply QOM paths or properties. */
export function qemuOnboardOutputQueries(profile) {
  validateQemuProfile(profile);
  check(profile.display === null && profile.outputs, 'This QEMU profile has no admitted onboard output readback');
  return profile.outputs.properties.map(property => ({execute:'qom-get', arguments:{path:profile.outputs.path, property}}));
}

export function validateQemuOnboardState(profile, state) {
  if (profile.outputs?.kind === 'stackchan-scs-qom-v1') return validateQemuServoState(profile,state);
  qemuOnboardOutputQueries(profile);
  check(state && Object.keys(state).length === 7 && state.schema_version === 1 && state.device_id === profile.deviceId
    && state.source === 'qemu-rmt-qom-readback' && state.path === profile.outputs.path
    && (profile.outputs.kind==='matrix-ws2812-qom-v1'
      ? Array.isArray(state.led_rgb)&&state.led_rgb.length===25&&state.led_rgb.every(color=>Number.isSafeInteger(color)&&color>=0&&color<=0xFFFFFF)
      : Number.isSafeInteger(state.led_rgb)&&state.led_rgb>=0&&state.led_rgb<=0xFFFFFF)
    && Number.isSafeInteger(state.led_frames) && state.led_frames >= 0 && typeof state.pressed === 'boolean', 'Invalid QEMU onboard output state');
  return state;
}
