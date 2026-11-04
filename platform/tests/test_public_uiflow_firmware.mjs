import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {composeUIFlowWorkbenchImage, validateUIFlowWorkbenchRegistry, resolveUIFlowWorkbenchProfile,
  UIFLOW_WORKBENCH_READY} from '../web/public-uiflow-firmware.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const registry = validateUIFlowWorkbenchRegistry(JSON.parse(await fs.readFile(path.join(root, 'platform/web/uiflow-workbench-profiles.json'))));
const qemu = JSON.parse(await fs.readFile(path.join(root, 'platform/web/qemu-browser-profiles.json')));
assert.deepEqual(registry.profiles.map(row => row.deviceId).sort(), qemu.profiles.filter(row => row.admission === 'public').map(row => row.deviceId).sort());
for (const row of registry.profiles) {
  const profile = qemu.profiles.find(profile => profile.deviceId === row.deviceId);
  for (const source of Object.values(row.files)) {
    const bytes = await fs.readFile(path.join(root, source.path));
    assert.equal(bytes.toString('utf8'), source.text); assert.equal(bytes.length, source.bytes); assert.equal(sha(bytes), source.sha256);
  }
  assert.equal(row.files['boot.py'].path.endsWith('/boot_native.py'), profile.fixture.sources?.['boot.py']?.path.endsWith('/core2_boot.py') === true);
  assert.equal(row.files['main.py'].text, 'import M5\n\nM5.begin()\nprint("M5_UIFLOW_WORKBENCH_READY")\n');
  const resolved = resolveUIFlowWorkbenchProfile(profile, row.firmwareSHA256, registry);
  assert.equal(resolved.readyMarker, UIFLOW_WORKBENCH_READY); assert.equal(resolved.readyFirmwareSHA256, row.firmwareSHA256);
  assert.equal(resolved.clockDivisor, profile.clockDivisor); assert.deepEqual(resolved.accelerator, profile.accelerator);
  assert.equal(resolved.oneInsnPerTb, undefined); assert.equal(resolved.firmwareVariant, undefined);
  assert.deepEqual(profile, qemu.profiles.find(profile => profile.deviceId === row.deviceId), 'resolution must not mutate the base registry');
  assert.deepEqual(resolveUIFlowWorkbenchProfile(profile, 'f'.repeat(64), registry), profile, 'unknown Flash cannot acquire programming readiness');
  const mismatch = structuredClone(profile); mismatch.reference.sha256 = '0'.repeat(64);
  assert.throws(() => resolveUIFlowWorkbenchProfile(mismatch, row.firmwareSHA256, registry), /no matching/);
}
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
