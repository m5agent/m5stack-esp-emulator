// Packaging only. Never starts a QEMU/MicroPython guest or executes the sources.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath, pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {composeUIFlowWorkbenchImage, resolveUIFlowWorkbenchProfile, validateUIFlowWorkbenchRegistry,
  UIFLOW_WORKBENCH_READY} from '../../../platform/web/public-uiflow-firmware.js';
import {resolveQemuFirmwareProfile} from '../../../platform/web/public-qemu-profiles.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const args = new Map();
for (let i = 2; i < process.argv.length; i++) {
  const key = process.argv[i];
  args.set(key, ['--write-registry', '--download', '--check'].includes(key) ? true : process.argv[++i]);
}
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const registryPath = path.join(root, 'platform/web/uiflow-workbench-profiles.json');
const stored = validateUIFlowWorkbenchRegistry(JSON.parse(await fs.readFile(registryPath)));
const profiles = JSON.parse(await fs.readFile(path.join(root, 'platform/web/qemu-browser-profiles.json'))).profiles
  .filter(row => row.admission === 'public' || row.firmwareProfiles?.some(variant => variant.fixture === 'uiflow-workbench-v1'));
const sourceFiles = {};
for (const file of [
  'tests/browser-qemu/uiflow_workbench/boot_native.py',
  'tests/browser-qemu/uiflow_workbench/boot_uart.py',
  'tests/browser-qemu/uiflow_workbench/main.py',
  'tests/browser-qemu/uiflow_workbench/main_cores3.py',
  'tests/browser-qemu/cores3_lvgl_wallclock/candidate_lvgl_loop.py',
]) {
  const bytes = await fs.readFile(path.join(root, file));
  sourceFiles[path.basename(file)] = {path:file, text:bytes.toString('utf8'), bytes:bytes.length, sha256:sha(bytes)};
}
const rows = profiles.map(profile => ({
  deviceId:profile.deviceId, board:profile.board, chip:profile.chip,
  baseSHA256:profile.reference.sha256, baseBytes:profile.reference.bytes,
  flashBytes:profile.flashMb * 1048576, vfsOffset:profile.fixture.vfsOffset, vfsSize:profile.fixture.vfsSize,
  baseFileCount:profile.fixture.baseFileCount ?? 17,
  baseDiskVersion:profile.fixture.baseDiskVersion ?? 131072,
  derivedDiskVersion:profile.fixture.derivedDiskVersion ?? 131073,
  firmwareSHA256:'0'.repeat(64), readyMarker:UIFLOW_WORKBENCH_READY, packaging:'COMPOSED_NOT_EXECUTED',
  files:{'boot.py':sourceFiles[profile.fixture.sources?.['boot.py']?.path.endsWith('/core2_boot.py') ? 'boot_native.py' : 'boot_uart.py'], 'main.py':sourceFiles[profile.deviceId === 'cores3' ? 'main_cores3.py' : 'main.py'],
    ...(profile.deviceId === 'cores3' ? {'candidate_lvgl_loop.py':sourceFiles['candidate_lvgl_loop.py']} : {})},

}));
const registry = {schema_version:1, kind:'m5stack-browser-uiflow-workbench', firmware_bundled:false,
  composer_commit:'6cb4e86540eca0d9ba62500a298385c9d863c8be', readyMarker:UIFLOW_WORKBENCH_READY,
  scope:'Official UIFlow2 runtime plus explicit programming startup; packaging identities do not grant browser functional acceptance.',
  ...(stored.examples === undefined ? {} : {examples:stored.examples}),
  profiles:rows};
for (const example of registry.examples || []) {
  const source = await fs.readFile(path.join(root, example.source.path));
  assert.equal(source.length,example.source.bytes);
  assert.equal(sha(source),example.source.sha256);
  const profile = profiles.find(item => item.deviceId === example.deviceId);
  const resolved = resolveQemuFirmwareProfile(profile, example.firmwareSHA256);
  resolveUIFlowWorkbenchProfile(resolved, example.firmwareSHA256, stored);
}
if (args.get('--check')) {
  assert.equal(stored.profiles.length, rows.length);
  for (const expected of rows) {
    const actual = stored.profiles.find(row => row.deviceId === expected.deviceId);
    assert.ok(actual, expected.deviceId);
    assert.deepEqual({...actual, firmwareSHA256:'0'.repeat(64)}, expected, expected.deviceId);
  }
  console.log('UIFlow programming registry matches public and explicit candidate startup sources. Guest execution: NOT RUN.');
  process.exit(0);
}
assert.ok(args.get('--runtime') && args.get('--firmware-cache') && args.get('--out-dir'), 'explicit --runtime, --firmware-cache and --out-dir are required');
const exampleId = args.get('--example');
const example = registry.examples?.find(item => item.id === exampleId);
assert.ok(!args.has('--example') || (example && !args.has('--write-registry')), 'Choose a reviewed example without --write-registry');
const runtime = path.resolve(args.get('--runtime')), cache = path.resolve(args.get('--firmware-cache')), output = path.resolve(args.get('--out-dir'));
assert.ok(path.relative(root, output).startsWith('.work/'), 'image output must be ignored .work storage in this checkout');
await fs.mkdir(cache, {recursive:true}); await fs.mkdir(output, {recursive:true});
const manifest = JSON.parse(await fs.readFile(path.join(runtime, 'manifest.json')));
assert.equal(manifest.source.commit, registry.composer_commit); assert.equal(manifest.kind, 'm5stack-browser-littlefs');
for (const key of ['module', 'wasm']) {
  const row = manifest.assets[key], bytes = await fs.readFile(path.join(runtime, row.path));
  assert.equal(bytes.length, row.bytes); assert.equal(sha(bytes), row.sha256);
}
const {default:factory} = await import(pathToFileURL(path.join(runtime, manifest.assets.module.path)).href);
const wasm = await fs.readFile(path.join(runtime, manifest.assets.wasm.path));
const engine = await factory({wasmBinary:wasm, print(){}, printErr(){}});
const selected = args.get('--devices') ? new Set(args.get('--devices').split(',')) : null;
if (selected) for (const id of selected) assert.ok(profiles.some(row => row.deviceId === id), `board has no reviewed workbench configuration: ${id}`);
if (example && selected) assert.ok(selected.has(example.deviceId), 'The selected example must use a selected device');
const results = [];
for (const row of rows) {
  if (selected && !selected.has(row.deviceId)) continue;
  if (example && row.deviceId !== example.deviceId) continue;
  const {baseBytes,baseSHA256} = example || row;
  const profile = profiles.find(profile => profile.deviceId === row.deviceId), file = path.join(cache, baseSHA256 + '.bin');
  let base;
  try { base = await fs.readFile(file); }
  catch (error) {
    if (error.code !== 'ENOENT' || !args.get('--download')) throw error;
    const url = new URL(example?.baseUrl || profile.reference.url);
    assert.equal(url.protocol, 'https:'); assert.equal(url.hostname, 'm5burner-cdn.m5stack.com');
    const response = await fetch(url, {redirect:'error', signal:AbortSignal.timeout(120000)});
    assert.ok(response.ok, `official firmware HTTP ${response.status}`);
    base = Buffer.from(await response.arrayBuffer());
    assert.equal(base.length, baseBytes); assert.equal(sha(base), baseSHA256);
    await fs.writeFile(file, base, {flag:'wx'});
  }
  assert.equal(base.length, baseBytes); assert.equal(sha(base), baseSHA256);
  const composed = await composeUIFlowWorkbenchImage({profile, registry, baseBytes:base, engine,
    exampleId, verifyResult:example !== undefined});
  if (!example) row.firmwareSHA256 = composed.sha256;
  const name = example?.id || row.deviceId;
  await fs.writeFile(path.join(output, name + '.bin'), composed.bytes);
  results.push({deviceId:row.deviceId, ...(example ? {exampleId:example.id} : {}), sha256:composed.sha256,
    provenance:composed.provenance, guest_execution:'NOT RUN'});
  console.log(`${name}: ${composed.sha256} (composed/readback verified; guest NOT RUN)`);
}
const text = JSON.stringify(registry, null, 2) + '\n';
await fs.writeFile(path.join(output, 'profiles.json'), text);
await fs.writeFile(path.join(output, 'composition.json'), JSON.stringify({kind:'uiflow-workbench-packaging', guest_execution:'NOT RUN', composer_wasm_sha256:manifest.assets.wasm.sha256, results}, null, 2) + '\n');
if (args.get('--write-registry')) {
  assert.equal(selected, null, 'partial builds cannot write the public registry');
  validateUIFlowWorkbenchRegistry(registry); await fs.writeFile(registryPath, text);
}
