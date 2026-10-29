// Opt-in browser validation for a user-supplied Cardputer-ADV merged image.
// It executes the selected firmware and does not grant hardware validation.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, extname, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const site = process.env.M5_PUBLIC_SITE && resolve(process.env.M5_PUBLIC_SITE);
const firmwarePath = process.env.M5_USER_FIRMWARE && resolve(process.env.M5_USER_FIRMWARE);
if (!site || !firmwarePath) {
  console.log('SKIP: M5_PUBLIC_SITE and M5_USER_FIRMWARE are required');
  process.exit(0);
}
const expectedSha256 = process.env.M5_USER_FIRMWARE_SHA256;
assert.ok(!expectedSha256 || /^[a-f0-9]{64}$/.test(expectedSha256), 'M5_USER_FIRMWARE_SHA256 must be lowercase SHA-256');
const basePath = process.env.M5_PUBLIC_BASE_PATH || '/m5stack-esp-emulator/';
const output = resolve(process.env.M5_PUBLIC_QEMU_OUT || resolve(repo, '.work/public-qemu-cardputer-legacy-user'));
assert.ok(output.startsWith(resolve(repo, '.work') + '/'), 'raw browser evidence must stay in ignored .work');
await mkdir(output, {recursive:false});
const firmwareBytes = await readFile(firmwarePath);
const firmwareSha256 = createHash('sha256').update(firmwareBytes).digest('hex');
if (expectedSha256) assert.equal(firmwareSha256, expectedSha256);

const modules = process.env.M5_WASM_NODE_MODULES || resolve(repo, 'platform/tests/node_modules');
const {chromium} = await import(pathToFileURL(resolve(modules, 'playwright/index.mjs')));
const mime = {'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json',
  '.wasm':'application/wasm','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp'};
const server = createServer(async (request, response) => {
  try {
    const path = new URL(request.url, 'http://localhost').pathname;
    if (!path.startsWith(basePath)) { response.writeHead(404).end(); return; }
    const file = resolve(site, decodeURIComponent(path.slice(basePath.length)) || 'index.html');
    if (!file.startsWith(site + '/')) { response.writeHead(403).end(); return; }
    response.writeHead(200, {'content-type':mime[extname(file)] || 'application/octet-stream', 'cache-control':'no-cache'});
    response.end(await readFile(file));
  } catch { response.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}${basePath}`;
let browser;
try {
  browser = await chromium.launch({headless:true,args:['--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
  const page = await browser.newPage({viewport:{width:1200,height:900}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(origin, {waitUntil:'domcontentloaded'});
  await page.waitForFunction(() => crossOriginIsolated, {}, {timeout:45000});
  await page.evaluate(async root => {
    const {PublicQemuRuntime} = await import(new URL('platform/web/public-qemu-runtime.js', root));
    const start = PublicQemuRuntime.prototype.start;
    PublicQemuRuntime.prototype.start = function(...args) {
      globalThis.__cardputer = {runtime:this};
      return start.apply(this, args);
    };
  }, origin);
  await page.locator('button[data-device-id="cardputer-adv"]').click();
  await page.waitForFunction(() => document.querySelector('#deviceMount')?.dataset.deviceId === 'cardputer-adv', {}, {timeout:45000});
  await page.locator('.advanced-options > summary').click();
  await page.locator('#runtimeMode').selectOption('browser');
  await page.locator('input[name="firmwareSource"][value="local"]').check();
  await page.locator('#firmwareFile').setInputFiles(firmwarePath);
  await page.waitForFunction(() => !document.querySelector('#startBtn').disabled);
  await page.locator('#startBtn').click();
  await page.waitForFunction(() => globalThis.__cardputer?.runtime?.display?.orientation === 'portrait'
    && globalThis.__cardputer.runtime.lastFrame?.width === 240, {}, {timeout:60000});
  if (await page.locator('#rawFramePanel').evaluate(panel => panel.hidden)) await page.locator('#nativeScreenBtn').click();
  await page.waitForFunction(() => {
    const canvas = document.querySelector('#rawFrameCanvas');
    return canvas.width === 135 && canvas.height === 240;
  }, {}, {timeout:15000});
  const snapshot = () => page.evaluate(async () => {
    const runtime = globalThis.__cardputer.runtime;
    const canvas = document.querySelector('#rawFrameCanvas');
    const digest = await crypto.subtle.digest('SHA-256', canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data);
    return {
      display:runtime.display,
      serial:runtime.serial,
      adc_errors:(runtime.serial.match(/adc_cali:/g) || []).length,
      frame:runtime.lastFrame.sequence,
      canvas:[canvas.width,canvas.height],
      sha256:[...new Uint8Array(digest)].map(value => value.toString(16).padStart(2,'0')).join(''),
    };
  });
  const before = await snapshot();
  await page.locator('#rawFrameCanvas').screenshot({path:resolve(output,'before-input.png')});
  assert.deepEqual(before.display,{orientation:'portrait',deviceRotationDeg:-90});
  assert.deepEqual(before.canvas,[135,240]);
  assert.equal(before.adc_errors,0);
  assert.doesNotMatch(before.serial,/Guru Meditation Error|Interrupt wdt timeout|A fatal error occurred/);
  await page.locator('#deviceMount .three-device-stage canvas').focus();
  await page.keyboard.down('Enter');
  await page.waitForTimeout(500);
  await page.keyboard.up('Enter');
  await page.waitForTimeout(1200);
  const after = await snapshot();
  await page.locator('#rawFrameCanvas').screenshot({path:resolve(output,'after-input.png')});
  await page.screenshot({path:resolve(output,'after-input-page.png'),fullPage:true});
  assert.equal(after.adc_errors,0);
  assert.notEqual(after.sha256,before.sha256,'Enter must cause an observable framebuffer change');
  const report = {kind:'browser-local-cardputer-adv-user-firmware',status:'PASS',validation:'virtual-device validation',
    hardware_validation:'NOT RUN',firmware_sha256:firmwareSha256,site,base_path:basePath,before,after,
    input_frame_delta:after.frame-before.frame,browser:browser.version(),errors};
  await writeFile(resolve(output,'report.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
