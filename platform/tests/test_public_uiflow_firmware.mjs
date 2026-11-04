import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {composeUIFlowWorkbenchImage, validateUIFlowWorkbenchRegistry, resolveUIFlowWorkbenchProfile,
  UIFLOW_WORKBENCH_READY} from '../web/public-uiflow-firmware.js';
import {validateQemuBrowserProfiles, resolveQemuFirmwareProfile, validateQemuRuntimeRequirements,
  QEMU_ONE_INSN_RUNTIME_PATCH} from '../web/public-qemu-profiles.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const registry = validateUIFlowWorkbenchRegistry(JSON.parse(await fs.readFile(path.join(root, 'platform/web/uiflow-workbench-profiles.json'))));
const qemu = validateQemuBrowserProfiles(JSON.parse(await fs.readFile(path.join(root, 'platform/web/qemu-browser-profiles.json'))));
const originalQemu = structuredClone(qemu);
assert.deepEqual(registry.profiles.map(row => row.deviceId).sort(), qemu.profiles.filter(row => row.admission === 'public').map(row => row.deviceId).sort());
for (const row of registry.profiles) {
  const profile = qemu.profiles.find(profile => profile.deviceId === row.deviceId);
  for (const source of Object.values(row.files)) {
    const bytes = await fs.readFile(path.join(root, source.path));
    assert.equal(bytes.toString('utf8'), source.text); assert.equal(bytes.length, source.bytes); assert.equal(sha(bytes), source.sha256);
  }
  assert.equal(row.files['boot.py'].path.endsWith('/boot_native.py'), profile.fixture.sources?.['boot.py']?.path.endsWith('/core2_boot.py') === true);
  assert.equal(row.files['main.py'].text, 'import M5\n\nM5.begin()\nprint("M5_UIFLOW_WORKBENCH_READY")\n');
  const resolved = resolveUIFlowWorkbenchProfile(resolveQemuFirmwareProfile(profile, row.firmwareSHA256), row.firmwareSHA256, registry);
  assert.equal(resolved.readyMarker, UIFLOW_WORKBENCH_READY); assert.equal(resolved.readyFirmwareSHA256, row.firmwareSHA256);
  if (row.deviceId === 'cores3') {
    assert.equal(resolved.clockDivisor, 1); assert.equal(resolved.oneInsnPerTb, true);
    assert.equal(resolved.profile, 'cores3-wasm-uiflow-workbench-wallclock-candidate');
    assert.deepEqual(resolved.requiredRuntimePatch, QEMU_ONE_INSN_RUNTIME_PATCH);
    assert.equal(resolved.firmwareVariant.firmwareSHA256, row.firmwareSHA256);
    assert.equal(resolved.firmwareVariant.sourceSHA256, row.files['main.py'].sha256);
    assert.equal(resolved.firmwareVariant.fixture, 'uiflow-workbench-v1');
    assert.equal(resolved.firmwareVariant.schedulerCandidate, 'qemu-tci-mmio-blocks-v1');
    assert.equal(resolved.accelerator, undefined);
  } else {
    assert.equal(resolved.clockDivisor, profile.clockDivisor, `${row.deviceId} cannot inherit the CoreS3 execution policy`);
    assert.deepEqual(resolved.accelerator, profile.accelerator);
    assert.equal(resolved.oneInsnPerTb, undefined); assert.equal(resolved.firmwareVariant, undefined);
  }
  assert.deepEqual(profile, qemu.profiles.find(profile => profile.deviceId === row.deviceId), 'resolution must not mutate the base registry');
  assert.deepEqual(resolveUIFlowWorkbenchProfile(profile, 'f'.repeat(64), registry), profile, 'unknown Flash cannot acquire programming readiness');
  const mismatch = structuredClone(profile); mismatch.reference.sha256 = '0'.repeat(64);
  assert.throws(() => resolveUIFlowWorkbenchProfile(mismatch, row.firmwareSHA256, registry), /no matching/);
}
const cores3 = qemu.profiles.find(profile => profile.deviceId === 'cores3');
const workbench = registry.profiles.find(row => row.deviceId === 'cores3');
const exactVariant = cores3.firmwareProfiles.find(row => row.firmwareSHA256 === workbench.firmwareSHA256);
const resolveWorkbench = (profile = cores3, workbenchRegistry = registry) => resolveUIFlowWorkbenchProfile(
  resolveQemuFirmwareProfile(profile, workbench.firmwareSHA256), workbench.firmwareSHA256, workbenchRegistry);
assert.deepEqual(exactVariant, {
  firmwareSHA256:'52f38f562f6e3749357a2ed4834efd72d16870046ea052f2f31691743cb5384d',
  profile:'cores3-wasm-uiflow-workbench-wallclock-candidate', clockDivisor:1,
  readyMarker:UIFLOW_WORKBENCH_READY, fixture:'uiflow-workbench-v1',
  sourceSHA256:'a109d9c11c09b4aa649e1a0a2d0929136fe7083f75bf2452e9c17b57f8b13ab0',
  schedulerCandidate:'qemu-tci-mmio-blocks-v1', oneInsnPerTb:true,
  requiredRuntimePatch:QEMU_ONE_INSN_RUNTIME_PATCH,
});
for (const [field, value] of [['sourceSHA256', '0'.repeat(64)], ['fixture', 'unrelated-fixture-v1'],
  ['readyMarker', 'UNRELATED_READY']]) {
  const copy = structuredClone(cores3);
  copy.firmwareProfiles.find(row => row.firmwareSHA256 === workbench.firmwareSHA256)[field] = value;
  assert.throws(() => resolveWorkbench(copy), /exact workbench source, fixture and ready binding/, `reject workbench ${field} mismatch`);
}
const changedMain = structuredClone(registry);
changedMain.profiles.find(row => row.deviceId === 'cores3').files['main.py'].sha256 = '0'.repeat(64);
assert.throws(() => resolveWorkbench(cores3, changedMain), /exact workbench source, fixture and ready binding/, 'main source registry cannot inherit a prior exact variant');
for (const other of cores3.firmwareProfiles.filter(row => row.firmwareSHA256 !== workbench.firmwareSHA256)) {
  const resolved = resolveQemuFirmwareProfile(cores3, other.firmwareSHA256);
  assert.throws(() => resolveUIFlowWorkbenchProfile(resolved, workbench.firmwareSHA256, registry), /exact workbench/, 'another exact image cannot acquire workbench readiness');
  assert.deepEqual(resolveUIFlowWorkbenchProfile(resolved, other.firmwareSHA256, registry), resolved, 'other images keep their separately bound policy');
  assert.notEqual(resolved.readyMarker, workbench.readyMarker);
}
const unknownCoreS3 = resolveQemuFirmwareProfile(cores3, 'f'.repeat(64));
assert.deepEqual(resolveUIFlowWorkbenchProfile(unknownCoreS3, 'f'.repeat(64), registry), unknownCoreS3);
assert.equal(unknownCoreS3.clockDivisor, 8); assert.equal(unknownCoreS3.oneInsnPerTb, undefined);
assert.equal(unknownCoreS3.firmwareVariant, undefined);
const conservative = resolveUIFlowWorkbenchProfile(cores3, workbench.firmwareSHA256, registry);
assert.equal(conservative.clockDivisor, 8); assert.equal(conservative.oneInsnPerTb, undefined);
const requiredRuntime = {source:{patches:[structuredClone(QEMU_ONE_INSN_RUNTIME_PATCH)]}};
validateQemuRuntimeRequirements(resolveWorkbench(), requiredRuntime);
for (const kind of ['missing', 'wrong', 'duplicate']) {
  const copy = structuredClone(requiredRuntime);
  if (kind === 'missing') copy.source.patches = [];
  if (kind === 'wrong') copy.source.patches[0].sha256 = '0'.repeat(64);
  if (kind === 'duplicate') copy.source.patches.push(structuredClone(QEMU_ONE_INSN_RUNTIME_PATCH));
  assert.throws(() => validateQemuRuntimeRequirements(resolveWorkbench(), copy), /required source patch/, `reject ${kind} runtime patch`);
}
for (const change of [variant => delete variant.requiredRuntimePatch, variant => variant.requiredRuntimePatch.sha256 = '0'.repeat(64),
  variant => variant.requiredRuntimePatch.path = 'patches/qemu-wasm-probe/unrelated.patch']) {
  const copy = structuredClone(cores3);
  change(copy.firmwareProfiles.find(row => row.firmwareSHA256 === workbench.firmwareSHA256));
  assert.throws(() => resolveWorkbench(copy), /runtime patch|one-instruction/, 'invalid patch identity fails before execution');
}
assert.deepEqual(qemu, originalQemu, 'resolving exact, unknown or invalid firmware must not mutate the registry');
const candidate = qemu.profiles.find(row => row.admission === 'candidate');
if (candidate) assert.deepEqual(resolveUIFlowWorkbenchProfile(candidate, 'f'.repeat(64), registry), candidate, 'programming registry must not admit candidate boards');
for (const change of [copy => copy.profiles.push(copy.profiles[0]), copy => copy.profiles[0].files['main.py'].path = '../main.py',
  copy => copy.profiles[0].files['main.py'].bytes++, copy => copy.profiles[0].vfsSize = copy.profiles[0].flashBytes,
  copy => copy.readyMarker = 'unrelated']) {
  const copy = structuredClone(registry); change(copy); assert.throws(() => validateUIFlowWorkbenchRegistry(copy));
}

const args = new Map(); for (let i = 2; i < process.argv.length; i += 2) args.set(process.argv[i], process.argv[i + 1]);
if (args.get('--runtime') && args.get('--firmware-cache')) {
  const runtime = path.resolve(args.get('--runtime')), cache = path.resolve(args.get('--firmware-cache'));
  const manifest = JSON.parse(await fs.readFile(path.join(runtime, 'manifest.json')));
  const {default:factory} = await import(pathToFileURL(path.join(runtime, manifest.assets.module.path)).href);
  const engine = await factory({wasmBinary:await fs.readFile(path.join(runtime, manifest.assets.wasm.path)), print(){}, printErr(){}});
  for (const device of (args.get('--devices') || 'cores3,stickc-plus,atom-matrix').split(',')) {
    const row = registry.profiles.find(row => row.deviceId === device), profile = qemu.profiles.find(row => row.deviceId === device);
    assert.ok(row && profile);
    const base = await fs.readFile(path.join(cache, row.baseSHA256 + '.bin'));
    const result = await composeUIFlowWorkbenchImage({profile, registry, baseBytes:base, engine});
    assert.equal(result.sha256, row.firmwareSHA256); assert.equal(result.provenance.source_readback_verified, true);
    assert.deepEqual(result.bytes.slice(0, row.vfsOffset), new Uint8Array(base.subarray(0, row.vfsOffset)));
    assert.deepEqual(result.bytes.slice(row.vfsOffset + row.vfsSize, base.length), new Uint8Array(base.subarray(row.vfsOffset + row.vfsSize)));
    assert.ok(result.bytes.slice(base.length).every(byte => byte === 255), 'Flash padding must remain erased');
    const bad = Buffer.from(base); bad[0] ^= 1;
    await assert.rejects(composeUIFlowWorkbenchImage({profile, registry, baseBytes:bad, engine}), /official base SHA256/);
    const changed = structuredClone(registry); changed.profiles.find(row => row.deviceId === device).files['main.py'].text = 'print("altered")\n';
    changed.profiles.find(row => row.deviceId === device).files['main.py'].bytes = new TextEncoder().encode('print("altered")\n').length;
    await assert.rejects(composeUIFlowWorkbenchImage({profile, registry:changed, baseBytes:base, engine}), /startup source SHA256/);
    const abort = new AbortController(); abort.abort();
    await assert.rejects(composeUIFlowWorkbenchImage({profile, registry, baseBytes:base, engine, signal:abort.signal}), /abort/i);
    console.log(`${device}: real LittleFS WASM composition and negative controls PASS; guest execution NOT RUN`);
  }
}
console.log('UIFlow programming firmware contracts PASS. Firmware guest execution: NOT RUN.');
