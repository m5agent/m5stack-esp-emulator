// Official UIFlow2 firmware with an explicit programming startup, composed in
// browser memory. The original MicroPython runtime executes all user programs.
import {assetUrl, siteRoot} from './public-config.js';
import {loadQemuBrowserProfiles, getQemuBrowserProfile, validateQemuProfile, validateQemuFirmware,
  ATOM_MATRIX_WORKBENCH_FLASH_SHA256, ATOM_MATRIX_ICOUNT_MAX_PER_CPU_NS} from './public-qemu-profiles.js';
import {qemuProbeVfs} from './public-qemu-probe-firmware.js';
import {sha256Buffer} from './public-firmware.js';
import {loadVerifiedRuntimeAsset} from './public-verified-assets.js';

export const UIFLOW_WORKBENCH_READY = 'M5_UIFLOW_WORKBENCH_READY';
const COMPOSER_COMMIT = '6cb4e86540eca0d9ba62500a298385c9d863c8be';
const HASH = /^[a-f0-9]{64}$/;
const CONFIG = {block_size:4096, read_size:128, prog_size:32, lookahead_size:128,
  block_cycles:100, cache_size:128, name_max:255, disk_version:0};
const registryCache = new Map();
const STARTUP_DIR = 'tests/browser-qemu/uiflow_workbench/';
const CORE_S3_LVGL_SOURCE_PATH = 'tests/browser-qemu/cores3_lvgl_wallclock/candidate_lvgl_loop.py';
const CORE_S3_DISPLAY_SOURCE_PATH = STARTUP_DIR + 'cores3_display_example.py';
const OFFICIAL_BASE_URL = /^https:\/\/m5burner-cdn\.m5stack\.com\/community\/1\/\d+\/\d+\/bin\/\d+\.bin$/;
const check = (ok, message) => { if (!ok) throw new Error(message); };
const abort = signal => { if (signal?.aborted) throw signal.reason || new DOMException('Cancelled', 'AbortError'); };

export function validateUIFlowWorkbenchRegistry(registry) {
  check(registry?.schema_version === 1 && registry.kind === 'm5stack-browser-uiflow-workbench'
    && registry.readyMarker === UIFLOW_WORKBENCH_READY && registry.firmware_bundled === false
    && registry.composer_commit === COMPOSER_COMMIT && Array.isArray(registry.profiles), 'Invalid UIFlow programming registry');
  const seen = new Set();
  for (const row of registry.profiles) {
    const cores3 = row.deviceId === 'cores3';
    const sourcePaths = {
      'boot.py': [STARTUP_DIR + 'boot_uart.py', STARTUP_DIR + 'boot_native.py'],
      'main.py': [STARTUP_DIR + (cores3 ? 'main_cores3.py' : 'main.py')],
      ...(cores3 ? {'candidate_lvgl_loop.py': [CORE_S3_LVGL_SOURCE_PATH]} : {}),
    };
    const boardMatches = row.deviceId === 'corematrix'
      ? row.chip === 'esp32c61' && row.board === 'esp32c61,m5corematrix=on' && row.flashBytes === 16 * 1048576
      : /^[a-z0-9-]+$/.test(row.board) && ['esp32', 'esp32s3'].includes(row.chip);
    check(/^[a-z0-9-]+$/.test(row.deviceId) && !seen.has(row.deviceId) && HASH.test(row.baseSHA256)
      && HASH.test(row.firmwareSHA256) && Number.isSafeInteger(row.baseBytes) && row.baseBytes > 0
      && Number.isSafeInteger(row.flashBytes) && row.flashBytes >= row.baseBytes && row.flashBytes <= 64 * 1048576
      && boardMatches
      && Number.isSafeInteger(row.vfsOffset) && row.vfsOffset >= 4096 && row.vfsOffset % 4096 === 0
      && Number.isSafeInteger(row.vfsSize) && row.vfsSize >= 8192 && row.vfsSize % 4096 === 0
      && row.vfsOffset + row.vfsSize <= row.baseBytes
      && Number.isSafeInteger(row.baseFileCount) && row.baseFileCount >= 2
      && row.baseDiskVersion === 131072 && row.derivedDiskVersion === 131073
      && row.packaging === 'COMPOSED_NOT_EXECUTED' && row.readyMarker === UIFLOW_WORKBENCH_READY
      && Object.keys(row.files || {}).sort().join(',') === Object.keys(sourcePaths).sort().join(','), 'Invalid UIFlow programming firmware identity');
    for (const [name, source] of Object.entries(row.files)) {
      check(typeof source.text === 'string' && source.text.length > 0 && source.text.length <= 4096
        && !source.text.includes('\0') && HASH.test(source.sha256) && Number.isSafeInteger(source.bytes)
        && source.bytes === new TextEncoder().encode(source.text).length
        && sourcePaths[name].includes(source.path), 'Invalid UIFlow programming startup source');
    }
    seen.add(row.deviceId);
  }
  if (registry.examples !== undefined) {
    check(Array.isArray(registry.examples) && registry.examples.length <= 1, 'Invalid UIFlow programming examples');
    for (const example of registry.examples) {
      const base = registry.profiles.find(row => row.deviceId === 'cores3');
      check(example?.id === 'cores3-display' && example.deviceId === 'cores3' && example.version === '2.5.5'
        && base && typeof example.baseUrl === 'string' && OFFICIAL_BASE_URL.test(example.baseUrl)
        && HASH.test(example.baseSHA256) && example.baseSHA256 !== base.baseSHA256
        && HASH.test(example.firmwareSHA256) && example.firmwareSHA256 !== base.firmwareSHA256
        && Number.isSafeInteger(example.baseBytes) && example.baseBytes >= base.vfsOffset + base.vfsSize
        && example.baseBytes <= base.flashBytes
        && Number.isSafeInteger(example.baseFileCount) && example.baseFileCount >= 2
        && example.source?.path === CORE_S3_DISPLAY_SOURCE_PATH && HASH.test(example.source.sha256)
        && Number.isSafeInteger(example.source.bytes) && example.source.bytes > 0 && example.source.bytes <= 4096,
      'Invalid UIFlow programming example identity');
    }
  }
  return registry;
}

export async function loadUIFlowWorkbenchProfiles({root = siteRoot(), signal, fetchImpl = globalThis.fetch} = {}) {
  abort(signal);
  const url = assetUrl('platform/web/uiflow-workbench-profiles.json', new URL(root));
  if (fetchImpl === globalThis.fetch && registryCache.has(url)) return structuredClone(registryCache.get(url));
  const response = await fetchImpl(url, {signal, credentials:'omit', cache:'no-cache'});
  check(response.ok, `UIFlow programming registry returned HTTP ${response.status}`);
  const text = await response.text(); check(new TextEncoder().encode(text).length <= 131072, 'UIFlow programming registry is too large');
  const registry = validateUIFlowWorkbenchRegistry(JSON.parse(text)); abort(signal);
  if (fetchImpl === globalThis.fetch) registryCache.set(url, structuredClone(registry));
  return registry;
}

// Lookups also support browser modes launched without a workbench registry.
export function getUIFlowWorkbenchExample(registry, deviceId, exampleId) {
  const example = registry?.examples?.find(row => row.deviceId === deviceId && row.id === exampleId);
  return example ? structuredClone(example) : null;
}

function exampleWorkbench(row, example) {
  const {id:exampleId, version, baseUrl, baseSHA256, baseBytes, baseFileCount, firmwareSHA256, source} = example;
  return {...row, exampleId, version, baseUrl, baseSHA256, baseBytes, baseFileCount, firmwareSHA256, source};
}

export function getUIFlowWorkbenchFirmware(registry, deviceId, firmwareSHA256) {
  const row = registry?.profiles?.find(item => item.deviceId === deviceId);
  if (!row) return null;
  if (row.firmwareSHA256 === firmwareSHA256) return structuredClone(row);
  const example = registry.examples?.find(item => item.deviceId === deviceId && item.firmwareSHA256 === firmwareSHA256);
  return example ? structuredClone(exampleWorkbench(row, example)) : null;
}

function boundWorkbench(profile, registry, exampleId) {
  validateQemuProfile(profile); validateUIFlowWorkbenchRegistry(registry);
  const row = registry.profiles.find(item => item.deviceId === profile.deviceId);
  check(row && row.board === profile.board && row.chip === profile.chip && row.flashBytes === profile.flashMb * 1048576
    && row.baseSHA256 === profile.reference.sha256 && row.baseBytes === profile.reference.bytes
    && row.vfsOffset === profile.fixture.vfsOffset && row.vfsSize === profile.fixture.vfsSize,
  'This board has no matching UIFlow programming firmware');
  if (exampleId === undefined) return row;
  const example = registry.examples?.find(item => item.deviceId === row.deviceId && item.id === exampleId);
  check(example, 'This board has no matching UIFlow programming example');
  return exampleWorkbench(row, example);
}

/** Bind readiness to the exact composed programming image. An explicitly
 * registered source-code variant must also match this workbench's main source,
 * ready marker and fixture. Other images do not inherit its execution policy. */
export function resolveUIFlowWorkbenchProfile(profile, firmwareSHA256, registry) {
  validateQemuProfile(profile); validateUIFlowWorkbenchRegistry(registry);
  if (!registry.profiles.some(row => row.deviceId === profile.deviceId)) return structuredClone(profile);
  const base = boundWorkbench(profile, registry);
  const example = registry.examples?.find(row => row.deviceId === profile.deviceId && row.firmwareSHA256 === firmwareSHA256);
  const row = example ? exampleWorkbench(base, example) : base;
  if (firmwareSHA256 !== row.firmwareSHA256) return structuredClone(profile);
  const variant = profile.firmwareVariant;
  check(variant ? variant.firmwareSHA256 === row.firmwareSHA256
    && variant.sourceSHA256 === row.files['main.py'].sha256 && variant.readyMarker === row.readyMarker
    && variant.fixture === 'uiflow-workbench-v1' && variant.sourceKind === undefined
    && (!example || (variant.clockDivisor === 1 && variant.oneInsnPerTb === true
      && variant.schedulerCandidate === 'qemu-tci-mmio-blocks-v1'))
    : !example && profile.oneInsnPerTb === undefined && profile.requiredRuntimePatch === undefined,
  'UIFlow programming firmware requires its exact workbench source, fixture and ready binding');
  const result = structuredClone(profile);
  result.readyMarker = UIFLOW_WORKBENCH_READY; result.readyFirmwareSHA256 = row.firmwareSHA256;
  // Limit round-robin CPU slices on this exact dual-core image so the peer
  // can complete Flash IPC promptly. The guest clock and WDT are unchanged.
  if (profile.deviceId === 'atom-matrix' && firmwareSHA256 === ATOM_MATRIX_WORKBENCH_FLASH_SHA256)
    result.accelerator.icountMaxPerCpuNs = ATOM_MATRIX_ICOUNT_MAX_PER_CPU_NS;
  validateQemuProfile(result); return result;
}

/** Filesystem-only core, shared by the browser and reproducible WASM builder.
 * `engine` is the real source-built LittleFS module, never a guest interpreter. */
export async function composeUIFlowWorkbenchImage({profile, registry, baseBytes, engine, signal, verifyResult = true, exampleId}) {
  abort(signal); const row = boundWorkbench(profile, registry, exampleId);
  const raw = baseBytes instanceof Uint8Array ? baseBytes : new Uint8Array(baseBytes);
  check(raw.length === row.baseBytes && await sha256Buffer(raw, {signal}) === row.baseSHA256, 'UIFlow official base SHA256 or size mismatch');
  const image = validateQemuFirmware(raw, profile), vfs = qemuProbeVfs(image, profile), allocations = [];
  for (const source of Object.values(row.files)) check(await sha256Buffer(new TextEncoder().encode(source.text), {signal}) === source.sha256, 'UIFlow startup source SHA256 mismatch');
  let mounted = false;
  const call = (name, ...args) => { const result = engine[name](...args); check(result >= 0, `UIFlow LittleFS ${name} failed (${result}); image was not formatted`); return result; };
  const allocate = bytes => { const ptr = engine._malloc(Math.max(1, bytes.length)); check(ptr, 'UIFlow composition allocation failed'); allocations.push(ptr); engine.HEAPU8.set(bytes, ptr); return ptr; };
  try {
    const region = allocate(image.subarray(vfs.offset, vfs.offset + vfs.size));
    call('_m5_lfs_mount_sized', region, vfs.size); mounted = true;
    const beforeCount = call('_m5_lfs_scan'), beforeVersion = call('_m5_lfs_disk_version');
    check(beforeCount === row.baseFileCount && beforeVersion === row.baseDiskVersion, 'UIFlow base filesystem identity mismatch');
    const files = Object.entries(row.files).sort(([a], [b]) => a.localeCompare(b)).map(([name, source]) => {
      const bytes = new TextEncoder().encode(source.text);
      return {bytes, path:allocate(new TextEncoder().encode('/' + name + '\0')), data:allocate(bytes)};
    });
    for (const file of files) call('_m5_lfs_write', file.path, file.data, file.bytes.length);
    call('_m5_lfs_unmount'); mounted = false;
    call('_m5_lfs_mount_sized', region, vfs.size); mounted = true;
    for (const file of files) {
      const readback = allocate(new Uint8Array(file.bytes.length + 1));
      check(call('_m5_lfs_read', file.path, readback, file.bytes.length + 1) === file.bytes.length
        && file.bytes.every((byte, index) => engine.HEAPU8[readback + index] === byte), 'UIFlow startup source readback mismatch');
    }
    const afterCount = call('_m5_lfs_scan'), afterVersion = call('_m5_lfs_disk_version');
    const addedFiles = Object.hasOwn(row.files, 'candidate_lvgl_loop.py') ? 1 : 0;
    check(afterCount === beforeCount + addedFiles && afterVersion === row.derivedDiskVersion, 'UIFlow derived filesystem membership/version mismatch');
    call('_m5_lfs_unmount'); mounted = false;
    image.set(engine.HEAPU8.subarray(region, region + vfs.size), vfs.offset);
    const digest = await sha256Buffer(image, {signal});
    if (verifyResult) check(digest === row.firmwareSHA256, 'UIFlow composed firmware SHA256 mismatch');
    abort(signal);
    return {bytes:image, sha256:digest, fileName:`${row.exampleId || profile.deviceId}-uiflow-workbench.bin`,
      provenance:{kind:'browser-local-uiflow-workbench', base_sha256:row.baseSHA256, firmware_sha256:digest,
        ...(row.exampleId ? {example_id:row.exampleId, sdk_version:row.version} : {}),
        composer_commit:COMPOSER_COMMIT, source_readback_verified:true, outside_vfs_unchanged:true,
        preserved_file_count:row.baseFileCount - 2, disk_version_before:beforeVersion, disk_version_after:afterVersion,
        files:Object.fromEntries(Object.entries(row.files).map(([name, source]) => [name, source.sha256]))}};
  } finally {
    if (mounted) engine._m5_lfs_unmount();
    for (const ptr of allocations) engine._free(ptr);
  }
}

export async function composeUIFlowWorkbenchFirmware({profile, deviceId = profile?.deviceId, root = siteRoot(),
  signal, fetchImpl = globalThis.fetch, onProgress = () => {}, baseBytes, registry, exampleId} = {}) {
  abort(signal); onProgress({phase:'load-composer'});
  if (!profile) profile = getQemuBrowserProfile(deviceId, await loadQemuBrowserProfiles({root, signal, fetchImpl}));
  registry ||= await loadUIFlowWorkbenchProfiles({root, signal, fetchImpl});
  const row = boundWorkbench(profile, registry, exampleId), manifestURL = assetUrl('platform/runtime/littlefs/manifest.json', new URL(root));
  const response = await fetchImpl(manifestURL, {signal, credentials:'omit', cache:'no-cache'});
  check(response.ok, `UIFlow composer manifest returned HTTP ${response.status}`);
  const manifest = await response.json();
  check(manifest.kind === 'm5stack-browser-littlefs' && manifest.schema_version === 1
    && manifest.source?.commit === COMPOSER_COMMIT && manifest.build?.kind === 'source-build'
    && manifest.build.emscripten === '3.1.50' && manifest.firmware_bundled === false && manifest.rom_bundled === false
    && manifest.partition_mount?.export === '_m5_lfs_mount_sized'
    && Object.entries(CONFIG).every(([key, value]) => manifest.fs_config?.[key] === value), 'UIFlow composer source/configuration mismatch');
  const asset = async key => {
    const identity = manifest.assets?.[key], name = key === 'module' ? 'littlefs.mjs' : 'littlefs.wasm';
    check(identity?.path === name && HASH.test(identity.sha256) && Number.isSafeInteger(identity.bytes)
      && identity.bytes > 0 && identity.bytes <= 1048576, 'Invalid UIFlow composer asset');
    const result = await loadVerifiedRuntimeAsset(new URL(name, manifestURL).href, {signal, fetchImpl,
      expectedSha256:identity.sha256, expectedBytes:identity.bytes, maxBytes:identity.bytes});
    return new Uint8Array(result.bytes);
  };
  const [moduleBytes, wasm, raw] = await Promise.all([asset('module'), asset('wasm'), baseBytes !== undefined
    ? Promise.resolve(baseBytes) : loadVerifiedRuntimeAsset(row.baseUrl || profile.reference.url, {signal, fetchImpl,
      expectedSha256:row.baseSHA256, expectedBytes:row.baseBytes, maxBytes:row.baseBytes}).then(result => new Uint8Array(result.bytes))]);
  abort(signal); onProgress({phase:'compose'});
  const blob = URL.createObjectURL(new Blob([moduleBytes], {type:'text/javascript'}));
  try {
    const {default:factory} = await import(blob);
    const engine = await factory({wasmBinary:wasm, locateFile:name => new URL(name, manifestURL).href, print(){}, printErr(){}});
    const result = await composeUIFlowWorkbenchImage({profile, registry, baseBytes:raw, engine, signal, exampleId});
    result.provenance.composer_wasm_sha256 = manifest.assets.wasm.sha256;
    onProgress({phase:'ready'}); return result;
  } finally { URL.revokeObjectURL(blob); }
}
