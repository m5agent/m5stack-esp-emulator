/* SPDX-License-Identifier: MIT
 * Compose the fixed demo in browser memory. No firmware/ROM is bundled.
 */

export const DEMO_FIRMWARE = Object.freeze({
  deviceId: 'cores3',
  fixture: 'cores3-wasm-lvgl-pir-v1',
  baseURL: 'https://m5burner-cdn.m5stack.com/community/1/1897200000000001950/2102696305989775362/bin/2102696305989775363.bin',
  rawBaseSize: 16121856,
  rawBaseSHA256: '1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264',
  normalizedBaseSHA256: 'ddad233fb05925421de7a2aad1b0c18ce0e947d5820b318eaca2b1e82464ac73',
  firmwareSHA256: '78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f',
  flashSize: 16777216,
  vfsOffset: 11141120,
  vfsSize: 4980736,
});

// Explicit SDK candidate; the original demo identity and API stay stable.
export const WALLCLOCK_DEMO_FIRMWARE = Object.freeze({
  ...DEMO_FIRMWARE,
  fixture: 'cores3-wasm-lvgl-wallclock-v1',
  firmwareSHA256: 'e9500994f4c0e1708ec35f5a46146225ac330d210a2427e1fc537c33635d9554',
  sourceSHA256: '4d60594952ef5af609084fc519e85b7064349b0782da35836b8c1673cdd73ecf',
  clockDivisor: 1,
  schedulerCandidate: 'sdk-python-single-schedule-v1',
});

const SOURCE_COMMIT = '6cb4e86540eca0d9ba62500a298385c9d863c8be';
const SOURCE_FILES = Object.freeze({
  'boot.py': {bytes: 214, sha256: '8fc4849761e7bdc252c71759006736f1e5dba98ed486bd934031ac4a08647c33'},
  'main.py': {bytes: 2301, sha256: '7672397edc3bff5256015c5d857fa3b4c53cba814bac6a982fb7eeb521cef3cb'},
});
const WALLCLOCK_SOURCE_FILES = Object.freeze({
  'boot.py': {bytes: 214, sha256: '8fc4849761e7bdc252c71759006736f1e5dba98ed486bd934031ac4a08647c33'},
  'candidate_lvgl_loop.py': {bytes: 3055, sha256: '0a460dbbd04838811238dd9022044f4b5e85f76629e44f8b7ba8fb057710363e'},
  'main.py': {bytes: 3491, sha256: 'e793b5ded4dc81510022723b8e10696a93d0cc4122c6cb5e58000a8ce9b84858'},
});
const CONFIG = Object.freeze({block_size: 4096, read_size: 128, prog_size: 32,
  lookahead_size: 128, block_cycles: 100, cache_size: 128, name_max: 255, disk_version: 0});

function checkAbort(signal) {
  if (signal?.aborted) throw signal.reason || new DOMException('Cancelled', 'AbortError');
}

function safeURL(value, base, sameOrigin = false) {
  const url = new URL(value, base);
  const origin = new URL(base).origin;
  if (url.username || url.password || url.hash || !['http:', 'https:'].includes(url.protocol)
      || (sameOrigin && url.origin !== origin)
      || (url.protocol === 'http:' && url.origin !== origin)) {
    throw new Error('Composer URL must use HTTPS or the current local origin without credentials');
  }
  return url;
}

async function bytesFromResponse(response, maximum, signal) {
  if (!response.ok) throw new Error(`Composer download returned HTTP ${response.status}`);
  const advertised = response.headers.get('content-length');
  if (advertised && (!/^\d+$/.test(advertised) || Number(advertised) > maximum)) {
    throw new Error('Composer download exceeds the expected size');
  }
  if (!response.body?.getReader) {
    const data = new Uint8Array(await response.arrayBuffer());
    if (data.length > maximum) throw new Error('Composer download exceeds the expected size');
    return data;
  }
  const reader = response.body.getReader(), chunks = [];
  let size = 0, completed = false;
  try {
    while (true) {
      checkAbort(signal);
      const next = await reader.read();
      if (next.done) break;
      size += next.value.byteLength;
      if (size > maximum) throw new Error('Composer download exceeds the expected size');
      chunks.push(next.value);
    }
    completed = true;
  } finally {
    if (!completed) await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  const data = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.length; }
  return data;
}

async function fetchBytes(url, maximum, signal) {
  checkAbort(signal);
  const response = await fetch(url, {signal, credentials: 'omit', cache: 'no-cache'});
  return bytesFromResponse(response, maximum, signal);
}

async function sha256(bytes) {
  const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  return Array.from(hash, value => value.toString(16).padStart(2, '0')).join('');
}

function validateManifest(manifest, wallclock = false) {
  const demo = wallclock ? WALLCLOCK_DEMO_FIRMWARE : DEMO_FIRMWARE;
  const sourceFiles = wallclock ? WALLCLOCK_SOURCE_FILES : SOURCE_FILES;
  const fixture = wallclock ? manifest?.fixtures?.[demo.fixture] : manifest?.fixture;
  if (manifest?.kind !== 'm5stack-browser-littlefs' || manifest.schema_version !== 1
      || manifest.source?.commit !== SOURCE_COMMIT || manifest.source?.license !== 'BSD-3-Clause'
      || manifest.build?.kind !== 'source-build' || manifest.build?.emscripten !== '3.1.50'
      || manifest.firmware_bundled !== false || manifest.rom_bundled !== false
      || fixture?.id !== demo.fixture
      || fixture.base_url !== demo.baseURL
      || fixture.raw_base?.size !== demo.rawBaseSize
      || fixture.raw_base?.sha256 !== demo.rawBaseSHA256
      || fixture.normalized_base?.size !== demo.flashSize
      || fixture.normalized_base?.sha256 !== demo.normalizedBaseSHA256
      || fixture.composed_firmware?.size !== demo.flashSize
      || fixture.composed_firmware?.sha256 !== demo.firmwareSHA256
      || fixture.vfs?.offset !== demo.vfsOffset || fixture.vfs?.size !== demo.vfsSize
      || Object.entries(CONFIG).some(([key, value]) => manifest.fs_config?.[key] !== value)) {
    throw new Error('Composer manifest does not match the reviewed CoreS3 fixture');
  }
  if (wallclock && (fixture.source_sha256 !== demo.sourceSHA256
      || fixture.clock_divisor !== demo.clockDivisor || fixture.scheduler_candidate !== demo.schedulerCandidate
      || fixture.base_file_count !== 17 || fixture.derived_file_count !== 18 || fixture.preserved_file_count !== 15
      || Object.keys(fixture.source_files || {}).sort().join() !== Object.keys(sourceFiles).sort().join()
      || Object.keys(fixture.source_assets || {}).sort().join() !== Object.keys(sourceFiles).sort().join())) {
    throw new Error('Composer wallclock candidate identity mismatch');
  }
  const expectedPaths = {module: 'littlefs.mjs', wasm: 'littlefs.wasm',
    ...Object.fromEntries(Object.keys(sourceFiles).map(name => [wallclock ? 'wallclock.' + name : name,
      wallclock ? 'fixtures/cores3-lvgl-wallclock/' + name : 'fixture/' + name]))};
  for (const [key, path] of Object.entries(expectedPaths)) {
    const row = manifest.assets?.[key];
    if (row?.path !== path || !Number.isSafeInteger(row.bytes) || row.bytes < 1 || row.bytes > 1024 * 1024
        || !/^[a-f0-9]{64}$/.test(row.sha256)) throw new Error('Invalid composer asset identity');
    const name = wallclock ? key.replace(/^wallclock\./, '') : key;
    if (sourceFiles[name] && (row.bytes !== sourceFiles[name].bytes || row.sha256 !== sourceFiles[name].sha256
        || fixture.source_files?.[name] !== sourceFiles[name].sha256
        || wallclock && fixture.source_assets[name] !== key)) {
      throw new Error('Composer source differs from the reviewed fixture');
    }
  }
}

/** Return only the exact reviewed Flash, after local composition and SHA256.
 * onProgress receives {phase}; baseBytes permits an explicit local file import.
 */
export async function composeDemoFirmware({baseBytes, baseURL = DEMO_FIRMWARE.baseURL,
  manifestURL = new URL('../runtime/littlefs/manifest.json', import.meta.url), signal,
  onProgress = () => {}} = {}) {
  return composeFixedDemoFirmware({baseBytes, baseURL, manifestURL, signal, onProgress}, false);
}

/** Compose only the named, hash-pinned SDK wallclock candidate. */
export async function composeWallclockDemoFirmware({baseBytes, baseURL = WALLCLOCK_DEMO_FIRMWARE.baseURL,
  manifestURL = new URL('../runtime/littlefs/manifest.json', import.meta.url), signal,
  onProgress = () => {}} = {}) {
  return composeFixedDemoFirmware({baseBytes, baseURL, manifestURL, signal, onProgress}, true);
}

async function composeFixedDemoFirmware({baseBytes, baseURL, manifestURL, signal, onProgress}, wallclock) {
  const demo = wallclock ? WALLCLOCK_DEMO_FIRMWARE : DEMO_FIRMWARE;
  const sourceFiles = wallclock ? WALLCLOCK_SOURCE_FILES : SOURCE_FILES;
  checkAbort(signal);
  const manifestLocation = safeURL(manifestURL, import.meta.url, true);
  onProgress({phase: 'load-composer'});
  const manifest = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(
    await fetchBytes(manifestLocation, 65536, signal)));
  validateManifest(manifest, wallclock);
  const loadAsset = async key => {
    const row = manifest.assets[key];
    const data = await fetchBytes(safeURL(row.path, manifestLocation, true), row.bytes, signal);
    if (data.length !== row.bytes || await sha256(data) !== row.sha256) {
      throw new Error(`Composer asset SHA256 mismatch: ${key}`);
    }
    return data;
  };
  let raw;
  if (baseBytes !== undefined) {
    if (baseBytes instanceof ArrayBuffer) raw = new Uint8Array(baseBytes).slice();
    else if (ArrayBuffer.isView(baseBytes)) raw = new Uint8Array(baseBytes.buffer, baseBytes.byteOffset, baseBytes.byteLength).slice();
    else throw new TypeError('baseBytes must be an ArrayBuffer or typed array');
    if (raw.byteLength !== demo.rawBaseSize) throw new Error('CoreS3 raw base size mismatch');
  }
  onProgress({phase: raw ? 'verify-base' : 'download-base'});
  const [moduleBytes, wasmBytes, files, base] = await Promise.all([
    loadAsset('module'), loadAsset('wasm'),
    Promise.all(Object.keys(sourceFiles).sort().map(async name => [name, await loadAsset(wallclock ? 'wallclock.' + name : name)])),
    raw || fetchBytes(safeURL(baseURL, import.meta.url), demo.rawBaseSize, signal),
  ]);
  if (base.length !== demo.rawBaseSize || await sha256(base) !== demo.rawBaseSHA256) {
    throw new Error('CoreS3 raw base SHA256 mismatch');
  }
  checkAbort(signal);
  const image = new Uint8Array(demo.flashSize).fill(255);
  image.set(base);
  if (await sha256(image) !== demo.normalizedBaseSHA256) throw new Error('Normalized base SHA256 mismatch');
  const blob = URL.createObjectURL(new Blob([moduleBytes], {type: 'text/javascript'}));
  let engine, imagePointer = 0, mounted = false;
  const allocations = [];
  const call = (name, ...args) => {
    const result = engine[name](...args);
    if (result < 0) throw new Error(`LittleFS ${name} failed (${result}); image was not formatted`);
    return result;
  };
  try {
    const {default: factory} = await import(blob);
    engine = await factory({wasmBinary: wasmBytes,
      locateFile: name => safeURL(name, manifestLocation, true).href,
      print() {}, printErr() {}});
    checkAbort(signal);
    const allocate = bytes => {
      const pointer = engine._malloc(Math.max(1, bytes.length));
      if (!pointer) throw new Error('Composer memory allocation failed');
      allocations.push(pointer);
      engine.HEAPU8.set(bytes, pointer);
      return pointer;
    };
    imagePointer = allocate(image.subarray(demo.vfsOffset, demo.vfsOffset + demo.vfsSize));
    onProgress({phase: 'compose'});
    call('_m5_lfs_mount', imagePointer, demo.vfsSize);
    mounted = true;
    const beforeCount = call('_m5_lfs_scan');
    const beforeVersion = call('_m5_lfs_disk_version');
    if (beforeCount !== 17 || beforeVersion !== 0x20000) throw new Error('Unexpected existing CoreS3 filesystem');
    const pointers = files.map(([name, bytes]) => ({name, bytes,
      path: allocate(new TextEncoder().encode('/' + name + '\0')), data: allocate(bytes)}));
    for (const file of pointers) call('_m5_lfs_write', file.path, file.data, file.bytes.length);
    call('_m5_lfs_unmount');
    mounted = false;
    call('_m5_lfs_mount', imagePointer, demo.vfsSize);
    mounted = true;
    const afterVersion = call('_m5_lfs_disk_version');
    for (const file of pointers) {
      const readback = allocate(new Uint8Array(file.bytes.length + 1));
      if (call('_m5_lfs_read', file.path, readback, file.bytes.length + 1) !== file.bytes.length
          || file.bytes.some((value, index) => engine.HEAPU8[readback + index] !== value)) {
        throw new Error('LittleFS fixture readback mismatch');
      }
    }
    const afterCount = call('_m5_lfs_scan');
    call('_m5_lfs_unmount');
    mounted = false;
    if (afterCount !== beforeCount + (wallclock ? 1 : 0) || afterVersion !== 0x20001) throw new Error('Unexpected composed CoreS3 filesystem');
    image.set(engine.HEAPU8.subarray(imagePointer, imagePointer + demo.vfsSize), demo.vfsOffset);
    onProgress({phase: 'verify-result'});
    const resultSHA = await sha256(image);
    if (resultSHA !== demo.firmwareSHA256) throw new Error('Composed firmware SHA256 mismatch');
    checkAbort(signal);
    return {bytes: image, sha256: resultSHA, fileName: wallclock ? 'cores3-wasm-lvgl-wallclock-candidate.bin' : 'cores3-wasm-lvgl-pir.bin',
      provenance: {kind: 'browser-local-littlefs-composition', fixture: demo.fixture,
        ...(wallclock ? {source_sha256:demo.sourceSHA256,clock_divisor:demo.clockDivisor,scheduler_candidate:demo.schedulerCandidate} : {}),
        base_sha256: demo.rawBaseSHA256, firmware_sha256: resultSHA,
        composer_commit: SOURCE_COMMIT, composer_wasm_sha256: manifest.assets.wasm.sha256,
        files: Object.fromEntries(Object.entries(sourceFiles).map(([name, row]) => [name, row.sha256])),
        preserved_file_count: beforeCount - 2, source_readback_verified: true,
        outside_vfs_unchanged: true, disk_version_before: beforeVersion, disk_version_after: afterVersion}};
  } finally {
    if (mounted) engine._m5_lfs_unmount();
    for (const pointer of allocations) engine._free(pointer);
    URL.revokeObjectURL(blob);
  }
}
