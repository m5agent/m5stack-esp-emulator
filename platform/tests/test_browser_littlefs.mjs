#!/usr/bin/env node
/** Opt-in real Chromium packaging test. Runs no firmware, QEMU or service. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import crypto from 'node:crypto';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const options = new Map();
for (let index = 2; index < process.argv.length; index += 2) options.set(process.argv[index], process.argv[index + 1]);
if (!options.get('--runtime') || !options.get('--base')) {
  console.log('SKIP: pass --runtime <composer output> --base <explicit official raw base>');
  process.exit(0);
}
const runtime = path.resolve(options.get('--runtime'));
const raw = await fs.readFile(path.resolve(options.get('--base')));
assert.equal(crypto.createHash('sha256').update(raw).digest('hex'), '1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264');
const manifest = JSON.parse(await fs.readFile(path.join(runtime, 'manifest.json')));
for (const row of Object.values(manifest.assets)) {
  const data = await fs.readFile(path.join(runtime, row.path));
  assert.equal(data.length, row.bytes);
  assert.equal(crypto.createHash('sha256').update(data).digest('hex'), row.sha256);
}
const permitted = new Set(['manifest.json', ...Object.values(manifest.assets).map(row => row.path)]);
let browser;
const requests = [];
const server = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url, 'http://localhost');
    requests.push(url.pathname);
    if (url.pathname === '/') { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><title>LittleFS packaging test</title>'); return; }
    if (url.pathname === '/base.bin') { response.end(raw); return; }
    if (url.pathname === '/public-demo-firmware.js') {
      response.setHeader('Content-Type', 'text/javascript');
      response.end(await fs.readFile(path.join(root, 'platform/web/public-demo-firmware.js'))); return;
    }
    const match = /^\/(normal|bad-source|bad-module|bad-manifest|escape)\/(.+)$/.exec(url.pathname);
    if (!match || !permitted.has(match[2])) { response.writeHead(404).end(); return; }
    const [mode, name] = match.slice(1);
    if (name === 'manifest.json') {
      const data = structuredClone(manifest);
      if (mode === 'bad-manifest') data.source.commit = '0'.repeat(40);
      if (mode === 'escape') data.assets.module.path = '../public-demo-firmware.js';
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(data)); return;
    }
    const data = await fs.readFile(path.join(runtime, name));
    if ((mode === 'bad-source' && name === 'fixture/main.py') || (mode === 'bad-module' && name === 'littlefs.mjs')) data[0] ^= 1;
    response.end(data);
  } catch (error) { response.writeHead(500).end(String(error)); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const report = {kind: 'browser-littlefs-composition-test', guest_execution: 'NOT RUN', cases: []};
try {
  const modules = process.env.M5_WASM_NODE_MODULES || path.join(root, 'platform/tests/node_modules');
  const {chromium} = await import(pathToFileURL(path.join(modules, 'playwright/index.mjs')));
  browser = await chromium.launch({headless: true, ...(process.env.M5_WASM_CHROME ? {executablePath: process.env.M5_WASM_CHROME} : {})});
  report.browser = browser.version();
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.goto(origin);
  for (const mode of ['download', 'local', 'cancelled', 'wrong-base', 'truncated', 'bad-source', 'bad-module', 'bad-manifest', 'escape']) {
    const actual = await page.evaluate(async ({mode, origin}) => {
      const {composeDemoFirmware, DEMO_FIRMWARE} = await import('/public-demo-firmware.js');
      const phases = [];
      const input = {manifestURL: `${origin}/${['bad-source', 'bad-module', 'bad-manifest', 'escape'].includes(mode) ? mode : 'normal'}/manifest.json`,
        baseURL: `${origin}/base.bin`, onProgress: update => phases.push(update.phase)};
      if (['local', 'wrong-base', 'truncated'].includes(mode)) {
        input.baseBytes = new Uint8Array(await (await fetch('/base.bin')).arrayBuffer());
        if (mode === 'wrong-base') input.baseBytes[input.baseBytes.length - 1] ^= 1;
        if (mode === 'truncated') input.baseBytes = input.baseBytes.subarray(1);
      }
      if (mode === 'cancelled') { const controller = new AbortController(); controller.abort(); input.signal = controller.signal; }
      try {
        const result = await composeDemoFirmware(input);
        // Keep the derived Flash only in this browser's memory.
        globalThis.__composedLittlefs = result.bytes;
        return {ok: true, sha256: result.sha256, size: result.bytes.length, provenance: result.provenance,
          baseUntouched: !input.baseBytes || await crypto.subtle.digest('SHA-256', input.baseBytes).then(hash =>
            [...new Uint8Array(hash)].map(value => value.toString(16).padStart(2, '0')).join('')) === DEMO_FIRMWARE.rawBaseSHA256, phases};
      } catch (error) { return {ok: false, name: error.name, error: error.message, phases}; }
    }, {mode, origin});
    if (['download', 'local'].includes(mode)) {
      assert.equal(actual.ok, true, JSON.stringify(actual));
      assert.equal(actual.sha256, '78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f');
      assert.equal(actual.size, 16777216);
      assert.equal(actual.baseUntouched, true);
      assert.equal(actual.provenance.preserved_file_count, 15);
      assert.equal(actual.provenance.source_readback_verified, true);
      assert.equal(actual.provenance.disk_version_before, 0x20000);
      assert.equal(actual.provenance.disk_version_after, 0x20001);
    } else {
      assert.equal(actual.ok, false, mode);
      if (mode === 'cancelled') assert.equal(actual.name, 'AbortError');
      if (mode === 'wrong-base') assert.match(actual.error, /base SHA256 mismatch/);
      if (mode === 'truncated') assert.match(actual.error, /size mismatch/);
      if (mode === 'bad-source') assert.match(actual.error, /asset SHA256 mismatch: main.py/);
      if (mode === 'bad-module') assert.match(actual.error, /asset SHA256 mismatch: module/);
      if (mode === 'bad-manifest') assert.match(actual.error, /manifest does not match/);
      if (mode === 'escape') assert.match(actual.error, /Invalid composer asset identity/);
    }
    report.cases.push({mode, status: 'PASS', ...actual});
  }
  assert.deepEqual(errors, []);
  report.page_errors = errors;
  report.status = 'PASS';
  report.request_count = requests.length;
  if (options.get('--out-dir')) {
    const out = path.resolve(options.get('--out-dir'));
    if (out === root || !path.relative(root, out).startsWith('.work/')) throw new Error('test report must use a new .work output directory');
    await fs.mkdir(out, {recursive: false});
    await fs.writeFile(path.join(out, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  }
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
