// Opt-in real browser LittleFS execution; this test starts no firmware guest.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const args = new Map(); for (let i = 2; i < process.argv.length; i += 2) args.set(process.argv[i], process.argv[i + 1]);
if (!args.get('--runtime') || !args.get('--base') || !args.get('--device')) {
  console.log('SKIP: explicit --runtime, --base and --device required'); process.exit(0);
}
const runtime = path.resolve(args.get('--runtime')), base = await fs.readFile(path.resolve(args.get('--base')));
const registry = JSON.parse(await fs.readFile(path.join(root, 'platform/web/qemu-browser-profiles.json')));
const profile = registry.profiles.find(row => row.deviceId === args.get('--device'));
assert.ok(profile?.fixture?.firmwareSHA256, 'the selected board must have an explicit probe fixture');
const manifest = JSON.parse(await fs.readFile(path.join(runtime, 'manifest.json'))), allowed = new Set(['manifest.json', ...Object.values(manifest.assets).map(row => row.path)]);
const server = http.createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/') { response.setHeader('content-type', 'text/html'); response.end('<!doctype html><title>QEMU probe composition</title>'); return; }
    if (pathname === '/base.bin') { response.end(base); return; }
    const web = /^\/platform\/web\/(public-qemu-probe-firmware|public-qemu-profiles|public-config|public-firmware|sha256)\.js$/.exec(pathname);
    if (web) { response.setHeader('content-type', 'text/javascript'); response.end(await fs.readFile(path.join(root, 'platform/web', web[1] + '.js'))); return; }
    const source = /^\/platform\/runtime\/qemu-probe\/fixture\/(boot|main|core2_boot|stopwatch_main|papercolor_main|papermono_main|cardputer_adv_main)\.py$/.exec(pathname);
    if (source) { response.end(await fs.readFile(path.join(root, 'tests/browser-qemu/board_display', source[1] + '.py'))); return; }
    const name = pathname.replace('/platform/runtime/littlefs/', '');
    if (!pathname.startsWith('/platform/runtime/littlefs/') || !allowed.has(name)) { response.writeHead(404).end(); return; }
    response.setHeader('content-type', name.endsWith('.json') ? 'application/json' : name.endsWith('.mjs') ? 'text/javascript' : 'application/octet-stream');
    response.end(await fs.readFile(path.join(runtime, name)));
  } catch (error) { response.writeHead(500).end(error.message); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const modules = process.env.M5_WASM_NODE_MODULES || path.join(root, 'platform/tests/node_modules');
const {chromium} = await import(pathToFileURL(path.join(modules, 'playwright/index.mjs')));
let browser;
try {
  browser = await chromium.launch({headless:true, ...(process.env.M5_WASM_CHROME ? {executablePath:process.env.M5_WASM_CHROME} : {})});
  const page = await browser.newPage(), errors = []; page.on('pageerror', error => errors.push(error.message)); await page.goto(origin);
  const result = await page.evaluate(async ({profile, origin}) => {
    const {composeQemuProbeFirmware} = await import('/platform/web/public-qemu-probe-firmware.js');
    const base = new Uint8Array(await (await fetch('/base.bin')).arrayBuffer());
    const composed = await composeQemuProbeFirmware({profile, root:origin + '/', baseBytes:base});
    const failures = [];
    for (const kind of ['wrong-base', 'changed-layout', 'changed-source', 'changed-boot', 'cancelled']) {
      const settings = {profile:structuredClone(profile), root:origin + '/', baseBytes:base.slice()};
      if (kind === 'wrong-base') settings.baseBytes[settings.baseBytes.length - 1] ^= 1;
      if (kind === 'changed-layout') settings.profile.fixture.vfsOffset += 4096;
      if (kind === 'changed-source') settings.profile.fixture.sources['main.py'].sha256 = '0'.repeat(64);
      if (kind === 'changed-boot') settings.profile.fixture.sources['boot.py'].path = 'platform/runtime/qemu-probe/fixture/' + (profile.deviceId === 'core2' ? 'boot.py' : 'core2_boot.py');
      if (kind === 'cancelled') { const controller = new AbortController(); controller.abort(); settings.signal = controller.signal; }
      try { await composeQemuProbeFirmware(settings); failures.push({kind,rejected:false}); }
      catch (error) { failures.push({kind,rejected:true,error:error.message}); }
    }
    return {sha256:composed.sha256, size:composed.bytes.length, provenance:composed.provenance, failures};
  }, {profile, origin});
  assert.equal(result.sha256, profile.fixture.firmwareSHA256); assert.equal(result.size, profile.flashMb * 1048576);
  assert.ok(Number.isSafeInteger(result.provenance.preserved_file_count) && result.provenance.preserved_file_count >= 0, 'preserved file count must be explicit');
  assert.equal(result.provenance.preserved_file_count, profile.fixture.preservedFileCount); assert.equal(result.provenance.source_readback_verified, true);
  assert.ok(result.failures.every(row => row.rejected)); assert.deepEqual(errors, []);
  const report = {kind:'browser-qemu-probe-composition', device:profile.deviceId, browser:browser.version(), guest_execution:'NOT RUN', status:'PASS', ...result};
  if (args.get('--out-dir')) {
    const output = path.resolve(args.get('--out-dir')); assert.ok(path.relative(root, output).startsWith('.work/'));
    await fs.mkdir(output, {recursive:false}); await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  }
  console.log(JSON.stringify(report, null, 2));
} finally { await browser?.close(); await new Promise(resolve => server.close(resolve)); }
