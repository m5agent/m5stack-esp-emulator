// Host loading/cache contracts. These checks do not execute QEMU or firmware.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createVerifiedAssetLoader, createVerifiedModuleCompiler} from '../web/public-verified-assets.js';
import {downloadFirmware, sha256Buffer} from '../web/public-firmware.js';

const payload = new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]);
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const sha = hash(payload), url = 'https://example.test/runtime.wasm';
const config = {expectedSha256:sha, expectedBytes:payload.length, maxBytes:64};
function storage() {
  const rows = new Map();
  const cache = {
    async match(key) { return rows.get(String(key))?.clone(); },
    async put(key, response) { rows.set(String(key), response.clone()); },
    async delete(key) { return rows.delete(typeof key === 'string' ? key : key.url); },
    async keys() { return [...rows.keys()].map(key => new Request(key)); },
  };
  return {rows, cache, async open() { return cache; }};
}
const cache = storage();
let downloads = 0;
const fetchImpl = async () => { downloads++; return new Response(payload); };
const load = createVerifiedAssetLoader({cacheStorage:cache});
const first = await load(url, {...config, fetchImpl});
assert.equal(first.cache, 'download'); assert.equal(downloads, 1);
// A transfer detaches the caller's bytes but must leave the cached copy intact.
structuredClone(first.bytes, {transfer:[first.bytes]});
assert.equal(first.bytes.byteLength, 0);
const warm = await load(url, {...config, fetchImpl});
assert.equal(warm.cache, 'memory'); assert.deepEqual(new Uint8Array(warm.bytes), payload);
new Uint8Array(warm.bytes).fill(255);
assert.deepEqual(new Uint8Array((await load(url, {...config, fetchImpl})).bytes), payload);
assert.equal(downloads, 1);

const reopened = createVerifiedAssetLoader({cacheStorage:cache});
assert.equal((await reopened(url, {...config, fetchImpl})).cache, 'storage');
assert.equal(downloads, 1, 'verified assets survive a new loader without another download');
const key = [...cache.rows.keys()][0];
cache.rows.set(key, new Response(new Uint8Array(payload.length), {headers:{'content-length':String(payload.length)}}));
const repaired = await createVerifiedAssetLoader({cacheStorage:cache})(url, {...config, fetchImpl});
assert.equal(repaired.cache, 'download'); assert.equal(downloads, 2, 'corrupt cache bytes are re-downloaded, not accepted');

const changed = new Uint8Array([1, 2, 3, 4]);
assert.equal((await load(url, {expectedSha256:hash(changed), expectedBytes:4, maxBytes:64,
  fetchImpl:async()=>{downloads++;return new Response(changed);}})).cache, 'download');
assert.equal(downloads, 3, 'a changed SHA at the same URL must miss the old cache');

const badCache = storage();
let failures = 0;
const failLoad = createVerifiedAssetLoader({cacheStorage:badCache});
const wrong = {...config, fetchImpl:async()=>{failures++;return new Response(changed);}};
for(let i=0;i<2;i++) await assert.rejects(failLoad(url, wrong), {code:'sha256_mismatch'});
assert.equal(failures, 2); assert.equal(badCache.rows.size, 0, 'failed integrity checks never populate either cache');

const cancelCache = storage(), cancel = new AbortController();
const cancelledLoad = createVerifiedAssetLoader({cacheStorage:cancelCache});
await assert.rejects(cancelledLoad(url, {...config, signal:cancel.signal,
  fetchImpl:async()=>{cancel.abort();return new Response(payload);}}), {name:'AbortError'});
assert.equal(cancelCache.rows.size, 0);
assert.equal((await cancelledLoad(url, {...config, fetchImpl})).cache, 'download', 'cancelled downloads are not memoized');
const cancelledHit = new AbortController(); cancelledHit.abort();
await assert.rejects(cancelledLoad(url, {...config, signal:cancelledHit.signal, fetchImpl}), {name:'AbortError'});

const writeCache = storage(), writeAbort = new AbortController();
const originalPut = writeCache.cache.put;
writeCache.cache.put = async (...args) => { await originalPut(...args); writeAbort.abort(); };
const writeLoad = createVerifiedAssetLoader({cacheStorage:writeCache});
await assert.rejects(writeLoad(url, {...config, signal:writeAbort.signal, fetchImpl}), {name:'AbortError'});
assert.equal(writeCache.rows.size, 0, 'cancellation during a cache write removes that write');
writeCache.cache.put = originalPut;
assert.equal((await writeLoad(url, {...config, fetchImpl})).cache, 'download');

const optional = createVerifiedAssetLoader({cacheStorage:()=>{throw new DOMException('disabled', 'SecurityError');}});
assert.equal((await optional(url, {...config, fetchImpl})).sha256, sha, 'blocked cache access cannot block a verified download');
const boundedCache = storage();
const bounded = createVerifiedAssetLoader({cacheStorage:boundedCache, maxMemoryBytes:8, maxStorageBytes:8});
await bounded(url, {...config, fetchImpl});
await bounded('https://example.test/other.wasm', {expectedSha256:hash(changed), expectedBytes:4, maxBytes:64, fetchImpl:async()=>new Response(changed)});
assert.equal(boundedCache.rows.size, 1, 'old content-bound versions cannot grow persistent storage without bound');
assert.equal((await bounded(url, {...config, fetchImpl})).cache, 'download', 'evicted memory/storage entries are fetched and verified again');

let digestCalls = 0;
const subtle = {async digest(algorithm, bytes) { digestCalls++; assert.equal(algorithm, 'SHA-256'); return createHash('sha256').update(bytes).digest(); }};
assert.equal(await sha256Buffer(payload, {subtle}), sha); assert.equal(digestCalls, 1);
assert.equal(await sha256Buffer(payload, {subtle:null}), sha, 'environments without WebCrypto keep the same digest');
assert.equal(await sha256Buffer(payload, {subtle:{digest:async()=>{throw new Error('unavailable');}}}), sha);
const hashAbort = new AbortController();
await assert.rejects(sha256Buffer(payload, {signal:hashAbort.signal, subtle:{async digest(){hashAbort.abort();return payload;}}}), {name:'AbortError'});
const result = await downloadFirmware(url, {expectedSha256:sha, fetchImpl:async()=>new Response(payload)});
assert.equal(result.sha256, sha); assert.deepEqual(new Uint8Array(result.bytes), payload);

let compilations = 0;
const compileModule = createVerifiedModuleCompiler({compile:bytes=>{compilations++;return WebAssembly.compile(bytes);}, maxModules:2, maxSourceBytes:16});
const moduleConfig = {sha256:sha, engineKey:'verified-manifest-a'};
const compiled = await compileModule(payload.buffer, moduleConfig);
assert.equal(compiled.cache, 'compiled');
const cloned = structuredClone(compiled.module);
assert.ok(cloned instanceof WebAssembly.Module); assert.ok(new WebAssembly.Instance(cloned) instanceof WebAssembly.Instance);
assert.equal((await compileModule(payload.buffer, moduleConfig)).module, compiled.module);
assert.equal(compilations, 1, 'restarts reuse compiled code rather than guest memory/state');
await compileModule(payload.buffer, {...moduleConfig,engineKey:'verified-manifest-b'});
await compileModule(payload.buffer, {...moduleConfig,engineKey:'verified-manifest-c'});
assert.equal(compilations, 3, 'different engine manifests cannot share a cache identity');
await compileModule(payload.buffer, moduleConfig);
assert.equal(compilations, 4, 'the compiled cache evicts old modules at the configured bound');
let invalidCompiles = 0;
const invalidCompiler = createVerifiedModuleCompiler({compile:async()=>{invalidCompiles++;throw new WebAssembly.CompileError('invalid fixture');}});
for(let i=0;i<2;i++)await assert.rejects(invalidCompiler(payload.buffer,moduleConfig),WebAssembly.CompileError);
assert.equal(invalidCompiles, 2, 'compilation failures are explicit and never cached');
const compileAbort = new AbortController(); let cancelledCompiles = 0;
const cancelCompiler = createVerifiedModuleCompiler({compile:async bytes=>{cancelledCompiles++;if(cancelledCompiles===1)compileAbort.abort();return WebAssembly.compile(bytes);}});
await assert.rejects(cancelCompiler(payload.buffer,{...moduleConfig,signal:compileAbort.signal}),{name:'AbortError'});
assert.equal((await cancelCompiler(payload.buffer,moduleConfig)).cache,'compiled');assert.equal(cancelledCompiles,2,'a compilation completed after cancellation cannot populate the cache');
console.log('verified assets/native SHA and compiled module identity, transfer/clone ownership, bounded cache, corruption recovery and cancellation contracts passed; no guest executed');
