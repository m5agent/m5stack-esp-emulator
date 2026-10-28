import assert from 'node:assert/strict';
import { assetUrl, siteRoot, resolveDevice, parseLaunchConfig, buildShareUrl, normalizeServiceUrl } from '../web/public-config.js';
import { downloadFirmware, normalizeFirmwareUrl } from '../web/public-firmware.js';
import { sha256Bytes } from '../web/sha256.js';

const pageUrl = 'https://m5agent.github.io/m5stack-esp-emulator/';
const catalog = { devices: [{id:'cores3',path:'esp32-s3/cores3'}, {id:'papermono',path:'esp32-s3/papermono'}] };
const root = siteRoot(new URL('platform/web/public-config.js', pageUrl));
assert.equal(root.href, pageUrl);
for (const path of ['/platform/web/app.css', 'platform/web/app.css', '/m5stack-esp-emulator/platform/web/app.css']) {
  assert.equal(assetUrl(path, root), `${pageUrl}platform/web/app.css`);
}
for (const path of ['../private', '%2e%2e/private', '//other.test/x', 'https://other.test/x']) assert.throws(() => assetUrl(path, root));
assert.equal(resolveDevice('M5CoreS3', catalog).id, 'cores3');
assert.equal(resolveDevice('devices/esp32-s3/cores3', catalog).id, 'cores3');
assert.throws(() => resolveDevice('m5papers3', catalog), {code:'unknown_device'});
const browserCatalog = {devices:[...catalog.devices,{id:'papers3',path:null}]};
for(const alias of ['m5papers3','paper-s3','m5stack-c139']) assert.equal(resolveDevice(alias,browserCatalog).id,'papers3');
const browserLaunch = parseLaunchConfig('?device=m5papers3&mode=browser&autostart=0',browserCatalog,{pageUrl});
assert.equal(browserLaunch.device.id,'papers3');
assert.equal(browserLaunch.mode,'browser');
assert.equal(browserLaunch.autostart,false);
assert.equal(parseLaunchConfig('?mode=model',catalog).autostart,false);
assert.equal(parseLaunchConfig('',catalog).autostart,true);
assert.throws(()=>parseLaunchConfig('?autostart=yes',catalog),{code:'invalid_autostart'});
assert.equal(new URL(buildShareUrl({deviceId:'papers3',mode:'browser',autostart:false},pageUrl)).searchParams.get('mode'),'browser');
assert.equal(normalizeFirmwareUrl('http://www.github.com/user/project/blob/main/firmware.bin?raw=true'), 'https://raw.githubusercontent.com/user/project/main/firmware.bin');
for (const url of ['javascript:alert(1)', 'data:text/html,a', 'https://user:secret@example.test/a.bin', 'https://example.test/a?token=private', 'https://example.test/a#<script>', 'http://example.test/a.bin']) assert.throws(() => normalizeFirmwareUrl(url, {pageUrl}));
assert.throws(() => normalizeServiceUrl('https://service.test/?token=secret'), {code:'service_credentials'});
assert.throws(() => normalizeServiceUrl('http://service.test'), {code:'insecure_service_url'});
assert.equal(normalizeServiceUrl('https://service.test/prefix/api/v1/'), 'https://service.test/prefix');
const launch = parseLaunchConfig('?device=core-s3&token=private&firmware=https%3A%2F%2Fexample.test%2Fa.bin', catalog, {pageUrl});
assert.equal(launch.device.id, 'cores3');
assert.equal(launch.warnings.length, 1);
assert.equal(JSON.stringify(launch).includes('private'), false);
assert.throws(() => parseLaunchConfig('?device=cores3&device=papermono', catalog), {code:'duplicate_parameter'});
assert.throws(() => parseLaunchConfig('?sha256=<img>', catalog), {code:'invalid_sha256'});
const share = buildShareUrl({deviceId:'cores3',firmware:'https://example.test/a.bin'}, `${pageUrl}?token=private#secret`);
assert.equal(share.includes('private'), false);
assert.equal(share.includes('secret'), false);

const payload = new Uint8Array([0xe9, 3, 2, 1]);
const calls = [];
const progress = [];
const result = await downloadFirmware('https://example.test/a.bin', {
  expectedSha256: sha256Bytes(payload), onProgress: value => progress.push(value),
  fetchImpl: async (url, options) => { calls.push(options); return new Response(payload); },
});
assert.deepEqual(new Uint8Array(result.bytes), payload);
assert.equal(result.sha256, sha256Bytes(payload));
assert.equal(result.name, 'a.bin');
assert.equal(progress.at(-1).phase, 'downloaded');
assert.equal(calls[0].credentials, 'omit');
assert.equal(calls[0].referrerPolicy, 'no-referrer');
await assert.rejects(downloadFirmware('https://example.test/a.bin', {expectedSha256:'0'.repeat(64),fetchImpl:async()=>new Response(payload)}), {code:'sha256_mismatch'});
await assert.rejects(downloadFirmware('https://example.test/a.bin', {fetchImpl:async()=>{throw new TypeError('private debug text');}}), {code:'firmware_cors_or_network'});
await assert.rejects(downloadFirmware('https://example.test/a.bin', {fetchImpl:async()=>new Response('<html>',{headers:{'content-type':'text/html'}})}), {code:'firmware_html'});
await assert.rejects(downloadFirmware('https://example.test/a.bin', {fetchImpl:async()=>new Response(new Uint8Array())}), {code:'empty_firmware'});
await assert.rejects(downloadFirmware('https://example.test/a.bin', {maxBytes:3,fetchImpl:async()=>new Response(payload)}), {code:'firmware_too_large'});
await assert.rejects(downloadFirmware('https://example.test/a.bin', {maxBytes:3,fetchImpl:async()=>new Response(payload,{headers:{'content-length':'4'}})}), {code:'firmware_too_large'});
const cancel = new AbortController();
cancel.abort();
let requested = false;
await assert.rejects(downloadFirmware('https://example.test/a.bin', {signal:cancel.signal,fetchImpl:async()=>{requested=true;}}), {name:'AbortError'});
assert.equal(requested, false);
const during = new AbortController();
await assert.rejects(downloadFirmware('https://example.test/a.bin', {
  signal:during.signal, onProgress:()=>during.abort(), fetchImpl:async()=>new Response(payload),
}), {name:'AbortError'});
console.log('public URL, credential, streaming, hash, CORS and cancellation contracts passed');
