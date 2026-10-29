import {assetUrl, siteRoot} from './public-config.js';
import {validateQemuProfile, validateQemuFirmware} from './public-qemu-profiles.js';
import {sha256Bytes} from './sha256.js';

const SOURCE_COMMIT = '6cb4e86540eca0d9ba62500a298385c9d863c8be';
const SOURCES = Object.freeze({
  "boot.py": {
    "bytes": 214,
    "sha256": "8fc4849761e7bdc252c71759006736f1e5dba98ed486bd934031ac4a08647c33"
  },
  "main.py": {
    "bytes": 1692,
    "sha256": "4dd53fcb19394ac43ea606e414baf8720b64c69c8caf3cda452fb2a805d1aed0"
  },
  "core2_boot.py": {
    "bytes": 24,
    "sha256": "b69ee8814a8188b541bcb90f78d987ae9ed554e7109db0849600fb40b7ea6ca9"
  },
  "atoms3_lite_main.py": {
    "bytes": 1085,
    "sha256": "b686ad8c42f14c0df2bec244e2a96f2cfde00195b640d7be765d082c5f890ca3"
  },
  "stickc_plus2_main.py": {
    "bytes": 2341,
    "sha256": "3d8cbeb1b05cf6e205294798c728e94e90ecfbe97903138c5b748d332a89551a"
  },
  "stopwatch_main.py": {
    "bytes": 1732,
    "sha256": "67daad6cd3680fda6379d5fb79b6c18bf42feda2d38fdb1197a42ecba4814406"
  },
  "papercolor_main.py": {
    "bytes": 2826,
    "sha256": "c18b09c5290562fcea2071faf5b9e7984f2b36b8a347fa76a85d4fdb2997448a"
  },
  "papermono_main.py": {
    "bytes": 4297,
    "sha256": "9ec71a31dfe6ad2d359e48a9bc1bdd9ce5eccb0080271fe819e3cfce109d403e"
  },
  "cardputer_adv_main.py": {
    "bytes": 3320,
    "sha256": "ff2d229274ac7b59ff70ef702b26a3c26415573063e4a31203f4024eed4ef6b8"
  }
});
const SOURCE_NAMES = Object.freeze({
  "atoms3": {
    "boot.py": "core2_boot.py"
  },
  "atoms3-lite": {
    "main.py": "atoms3_lite_main.py"
  },
  "core2": {
    "boot.py": "core2_boot.py"
  },
  "stickc-plus2": {
    "boot.py": "core2_boot.py",
    "main.py": "stickc_plus2_main.py"
  },
  "stickc": {"boot.py": "core2_boot.py"},
  "stickc-plus-se": {"boot.py": "core2_boot.py"},
  "dial": {
    "boot.py": "core2_boot.py"
  },
  "stopwatch": {
    "main.py": "stopwatch_main.py"
  },
  "papercolor": {
    "main.py": "papercolor_main.py"
  },
  "papermono": {
    "main.py": "papermono_main.py"
  },
  "cardputer-adv": {
    "main.py": "cardputer_adv_main.py"
  }
});
const CONFIG = {block_size:4096, read_size:128, prog_size:32, lookahead_size:128, block_cycles:100, cache_size:128, name_max:255, disk_version:0};
function check(ok, message) { if (!ok) throw new Error(message); }
function abort(signal) { if (signal?.aborted) throw signal.reason || new DOMException('Cancelled', 'AbortError'); }
function localURL(path, root) {
  const url = new URL(path, root);
  check(url.origin === new URL(root).origin && ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password && !url.hash, 'Invalid local probe asset URL');
  return url;
}
async function download(url, maximum, {signal, fetchImpl}) {
  abort(signal);
  const response = await fetchImpl(url, {signal, credentials:'omit', cache:'no-cache'});
  check(response.ok, `Probe download returned HTTP ${response.status}`);
  const chunks = [], reader = response.body.getReader(); let length = 0;
  try {
    while (true) {
      abort(signal); const next = await reader.read(); if (next.done) break;
      length += next.value.length; check(length <= maximum, 'Probe asset exceeds its expected size'); chunks.push(next.value);
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
  const bytes = new Uint8Array(length); let at = 0; for (const chunk of chunks) { bytes.set(chunk, at); at += chunk.length; } return bytes;
}

/** Bind composition to the actual unique, unencrypted UIFlow2 VFS partition. */
export function qemuProbeVfs(flash, profile) {
  const view = new DataView(flash.buffer, flash.byteOffset, flash.byteLength), found = [];
  for (let at = profile.partitionTableOffset; at + 32 <= profile.partitionTableOffset + 4096; at += 32) {
    if (view.getUint16(at, true) !== 0x50aa) break;
    const end = flash.subarray(at + 12, at + 28).indexOf(0);
    const label = new TextDecoder().decode(flash.subarray(at + 12, at + 12 + (end < 0 ? 16 : end)));
    if (label === 'vfs') found.push({type:flash[at + 2], subtype:flash[at + 3], offset:view.getUint32(at + 4, true), size:view.getUint32(at + 8, true), flags:view.getUint32(at + 28, true)});
  }
  check(found.length === 1, 'Probe needs exactly one named VFS partition');
  const vfs = found[0];
  check(vfs.type === 1 && vfs.subtype === 0x81 && vfs.flags === 0 && vfs.size >= 8192 && vfs.size <= 16777216
    && vfs.offset % 4096 === 0 && vfs.size % 4096 === 0 && vfs.offset + vfs.size <= flash.length
    && vfs.offset === profile.fixture.vfsOffset && vfs.size === profile.fixture.vfsSize, 'Probe VFS layout is not the reviewed unencrypted partition');
  return vfs;
}

/** Compose an explicit board probe; never substitutes the CoreS3 PIR example. */
export async function composeQemuProbeFirmware({profile, baseBytes, root = siteRoot(), manifestURL,
  signal, fetchImpl = globalThis.fetch, onProgress = () => {}} = {}) {
  validateQemuProfile(profile); abort(signal);
  const fixture = profile.fixture;
  check(fixture?.id === (profile.display===null?'xtensa-board-led-v1':'xtensa-board-display-v1') && ['button', 'touch', 'keyboard'].includes(fixture.inputMode)
    && Number.isInteger(fixture.uiRotation) && fixture.uiRotation >= 0 && fixture.uiRotation <= 3
    && /^[a-f0-9]{64}$/.test(fixture.firmwareSHA256), 'This board has no reviewed browser probe fixture');
  const options = {signal, fetchImpl};
  const location = localURL(manifestURL || assetUrl('platform/runtime/littlefs/manifest.json', new URL(root)), root);
  onProgress({phase:'load-composer'});
  const manifest = JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(await download(location, 65536, options)));
  check(manifest.kind === 'm5stack-browser-littlefs' && manifest.schema_version === 1 && manifest.source?.commit === SOURCE_COMMIT
    && manifest.build?.kind === 'source-build' && manifest.build.emscripten === '3.1.50'
    && manifest.firmware_bundled === false && manifest.rom_bundled === false && manifest.partition_mount?.export === '_m5_lfs_mount_sized'
    && Object.entries(CONFIG).every(([key, value]) => manifest.fs_config?.[key] === value), 'Probe composer source/configuration mismatch');
  const asset = async key => {
    const row = manifest.assets?.[key], name = key === 'module' ? 'littlefs.mjs' : 'littlefs.wasm';
    check(row?.path === name && Number.isSafeInteger(row.bytes) && row.bytes > 0 && row.bytes <= 1048576 && /^[a-f0-9]{64}$/.test(row.sha256), 'Invalid probe composer asset');
    const bytes = await download(localURL(name, location), row.bytes, options);
    check(bytes.length === row.bytes && sha256Bytes(bytes) === row.sha256, 'Probe composer asset hash mismatch'); return bytes;
  };
  const source = async name => {
    const sourceName = SOURCE_NAMES[profile.deviceId]?.[name] || name;
    const row = fixture.sources?.[name], pinned = SOURCES[sourceName];
    const path = `platform/runtime/qemu-probe/fixture/${sourceName}`;
    check(row?.path === path && row.bytes === pinned.bytes && row.sha256 === pinned.sha256, 'Probe source identity mismatch');
    const bytes = await download(localURL(assetUrl(path, new URL(root)), root), row.bytes, options);
    check(bytes.length === row.bytes && sha256Bytes(bytes) === row.sha256, 'Probe source asset hash mismatch'); return bytes;
  };
  const [moduleBytes, wasm, boot, main, raw] = await Promise.all([asset('module'), asset('wasm'), source('boot.py'), source('main.py'),
    baseBytes === undefined ? download(profile.reference.url, profile.reference.bytes, options) : Promise.resolve(baseBytes instanceof ArrayBuffer ? new Uint8Array(baseBytes).slice() : new Uint8Array(baseBytes).slice())]);
  check(raw.length === profile.reference.bytes && sha256Bytes(raw) === profile.reference.sha256, 'Probe official base hash or size mismatch');
  const image = validateQemuFirmware(raw, profile), vfs = qemuProbeVfs(image, profile);
  const config = new TextEncoder().encode(`DEVICE_ID = ${JSON.stringify(profile.deviceId)}\nROTATION = ${fixture.uiRotation}\nINPUT_MODE = ${JSON.stringify(fixture.inputMode)}\n`);
  check(sha256Bytes(config) === fixture.configSHA256, 'Probe board configuration hash mismatch');
  const files = [['boot.py', boot], ['browser_probe_config.py', config], ['main.py', main]];
  const blob = URL.createObjectURL(new Blob([moduleBytes], {type:'text/javascript'})), allocations = [];
  let engine, mounted = false;
  const call = (name, ...args) => { const result = engine[name](...args); check(result >= 0, `Probe LittleFS ${name} failed (${result}); image was not formatted`); return result; };
  try {
    const {default:factory} = await import(blob); engine = await factory({wasmBinary:wasm, locateFile:name => localURL(name, location).href, print(){}, printErr(){}});
    const allocate = bytes => { const ptr = engine._malloc(Math.max(1, bytes.length)); check(ptr, 'Probe composition allocation failed'); allocations.push(ptr); engine.HEAPU8.set(bytes, ptr); return ptr; };
    const region = allocate(image.subarray(vfs.offset, vfs.offset + vfs.size));
    call('_m5_lfs_mount_sized', region, vfs.size); mounted = true;
    const beforeCount = call('_m5_lfs_scan'), beforeVersion = call('_m5_lfs_disk_version');
    check(beforeCount === fixture.baseFileCount && beforeVersion === fixture.baseDiskVersion, 'Probe base filesystem identity mismatch');
    onProgress({phase:'compose'});
    const pointers = files.map(([name, bytes]) => ({name, bytes, path:allocate(new TextEncoder().encode('/' + name + '\0')), data:allocate(bytes)}));
    for (const file of pointers) call('_m5_lfs_write', file.path, file.data, file.bytes.length);
    call('_m5_lfs_unmount'); mounted = false;
    call('_m5_lfs_mount_sized', region, vfs.size); mounted = true;
    for (const file of pointers) {
      const readback = allocate(new Uint8Array(file.bytes.length + 1));
      check(call('_m5_lfs_read', file.path, readback, file.bytes.length + 1) === file.bytes.length
        && file.bytes.every((byte, index) => engine.HEAPU8[readback + index] === byte), 'Probe source readback mismatch');
    }
    check(call('_m5_lfs_scan') === beforeCount + 1 && call('_m5_lfs_disk_version') === fixture.derivedDiskVersion, 'Probe derived filesystem membership/version mismatch');
    call('_m5_lfs_unmount'); mounted = false;
    image.set(engine.HEAPU8.subarray(region, region + vfs.size), vfs.offset);
    const digest = sha256Bytes(image); check(digest === fixture.firmwareSHA256, 'Probe composed firmware SHA256 mismatch'); abort(signal);
    return {bytes:image, sha256:digest, fileName:`${profile.deviceId}-browser-${profile.display===null?'led':'display'}-probe.bin`, provenance:{kind:'browser-local-littlefs-composition', fixture:fixture.id,
      base_sha256:profile.reference.sha256, firmware_sha256:digest, composer_commit:SOURCE_COMMIT, composer_wasm_sha256:manifest.assets.wasm.sha256,
      files:Object.fromEntries(files.map(([name, bytes]) => [name, sha256Bytes(bytes)])), source_readback_verified:true,
      preserved_file_count:fixture.preservedFileCount, outside_vfs_unchanged:true, disk_version_before:beforeVersion, disk_version_after:fixture.derivedDiskVersion}};
  } finally {
    if (mounted) engine._m5_lfs_unmount(); for (const ptr of allocations) engine._free(ptr); URL.revokeObjectURL(blob);
  }
}
