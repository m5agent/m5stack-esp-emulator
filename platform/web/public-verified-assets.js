import {downloadFirmware, normalizeFirmwareUrl, sha256Buffer} from './public-firmware.js';

const CACHE_NAME = 'm5-verified-runtime-assets-v1';
function active(signal) {
  if (signal?.aborted) throw signal.reason || new DOMException('下载已取消。', 'AbortError');
}
function check(ok) { if (!ok) throw new Error('运行资源 SHA-256 或长度不匹配。'); }

// Cache only immutable, explicitly hash-bound runtime/ROM assets. Mutable Flash
// and user firmware never enter this cache. Returned buffers have their own
// ownership: transferring one to an engine must not detach the cached copy.
export function createVerifiedAssetLoader({downloadImpl = downloadFirmware,
  cacheStorage = () => globalThis.caches, maxMemoryBytes = 96 * 1024 * 1024,
  maxStorageBytes = 128 * 1024 * 1024} = {}) {
  const memory = new Map();
  let memoryBytes = 0;
  const remember = (key, bytes) => {
    if (bytes.byteLength > maxMemoryBytes) return;
    if (memory.has(key)) memoryBytes -= memory.get(key).byteLength;
    memory.delete(key); memory.set(key, bytes.slice(0)); memoryBytes += bytes.byteLength;
    while (memoryBytes > maxMemoryBytes) {
      const oldest = memory.keys().next().value;
      memoryBytes -= memory.get(oldest).byteLength; memory.delete(oldest);
    }
  };
  const openCache = async () => {
    try { return await (typeof cacheStorage === 'function' ? cacheStorage() : cacheStorage)?.open(CACHE_NAME); }
    catch { return null; } // Cache access/quota is optional; integrity is not.
  };
  const trimCache = async cache => {
    const keys = await cache.keys();
    let total = keys.reduce((sum, key) => sum + Number(new URL(key.url).searchParams.get('__m5_verified_bytes') || 0), 0);
    for (const key of keys) {
      if (total <= maxStorageBytes) break;
      const size = Number(new URL(key.url).searchParams.get('__m5_verified_bytes') || 0);
      await cache.delete(key); total -= size;
    }
  };
  return async function loadAsset(value, {expectedSha256, expectedBytes, maxBytes, signal, fetchImpl, pageUrl} = {}) {
    const url = normalizeFirmwareUrl(value, {pageUrl});
    check(/^[a-f0-9]{64}$/.test(expectedSha256) && Number.isSafeInteger(expectedBytes)
      && expectedBytes > 0 && expectedBytes <= maxBytes);
    const key = new URL(url);
    key.searchParams.set('__m5_verified_sha256', expectedSha256);
    key.searchParams.set('__m5_verified_bytes', String(expectedBytes));
    const cacheKey = key.href;
    active(signal);
    const hit = memory.get(cacheKey);
    if (hit) {
      memory.delete(cacheKey); memory.set(cacheKey, hit);
      return {bytes:hit.slice(0), size:expectedBytes, sha256:expectedSha256, url, cache:'memory'};
    }
    const cache = await openCache(); active(signal);
    if (cache) {
      let cached;
      try { cached = await cache.match(cacheKey); } catch { /* Use the network. */ }
      active(signal);
      if (cached) {
        let bytes;
        try {
          if (cached.ok && Number(cached.headers.get('content-length')) === expectedBytes) {
            bytes = await cached.arrayBuffer(); active(signal);
            if (bytes.byteLength !== expectedBytes || await sha256Buffer(bytes, {signal}) !== expectedSha256) bytes = null;
          }
        } catch { bytes = null; active(signal); }
        active(signal);
        if (bytes) {
          remember(cacheKey, bytes);
          return {bytes, size:expectedBytes, sha256:expectedSha256, url, cache:'storage'};
        }
        try { await cache.delete(cacheKey); } catch { /* A corrupt entry is never used. */ }
      }
    }
    active(signal);
    const result = await downloadImpl(url, {signal, expectedSha256, maxBytes, fetchImpl, pageUrl});
    active(signal);
    check(result.sha256 === expectedSha256 && result.size === expectedBytes
      && result.bytes instanceof ArrayBuffer && result.bytes.byteLength === expectedBytes);
    if (cache) {
      try {
        await cache.put(cacheKey, new Response(result.bytes.slice(0), {headers:{
          'Content-Type':'application/octet-stream', 'Content-Length':String(expectedBytes),
        }}));
        await trimCache(cache);
      } catch { /* An unavailable/quota-limited cache must not prevent startup. */ }
      if (signal?.aborted) {
        try { await cache.delete(cacheKey); } catch { /* Never retain this cancelled write. */ }
        active(signal);
      }
    }
    active(signal); remember(cacheKey, result.bytes);
    return {...result, cache:'download'};
  };
}

export const loadVerifiedRuntimeAsset = createVerifiedAssetLoader();

// Keep compiled code only, never an Instance, Memory, guest Flash or filesystem.
// The identity includes the verified engine/glue manifest as well as the WASM
// SHA, so a different deployment cannot reuse an unrelated engine compilation.
export function createVerifiedModuleCompiler({compile = bytes => WebAssembly.compile(bytes),
  maxModules = 2, maxSourceBytes = 64 * 1024 * 1024} = {}) {
  const modules = new Map();
  let sourceBytes = 0;
  return async function compileModule(bytes, {sha256, engineKey, signal} = {}) {
    check(bytes instanceof ArrayBuffer && /^[a-f0-9]{64}$/.test(sha256)
      && typeof engineKey === 'string' && engineKey.length > 0);
    active(signal);
    const key = engineKey + ':' + sha256;
    const hit = modules.get(key);
    if (hit) {
      modules.delete(key); modules.set(key, hit);
      return {module:hit.module, cache:'memory'};
    }
    const module = await compile(bytes);
    active(signal); check(module instanceof WebAssembly.Module);
    if (maxModules > 0 && bytes.byteLength <= maxSourceBytes) {
      if (modules.has(key)) sourceBytes -= modules.get(key).bytes;
      modules.delete(key);
      modules.set(key, {module, bytes:bytes.byteLength}); sourceBytes += bytes.byteLength;
      while (modules.size > maxModules || sourceBytes > maxSourceBytes) {
        const oldest = modules.keys().next().value;
        sourceBytes -= modules.get(oldest).bytes; modules.delete(oldest);
      }
    }
    return {module, cache:'compiled'};
  };
}

export const compileVerifiedRuntimeModule = createVerifiedModuleCompiler();
