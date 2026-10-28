// Opt-in development regression for the browser backend. This runs a real
// Chromium Worker/WASM; it never launches QEMU or contacts the user's service.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {resolve, dirname, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {chromium} from 'playwright';

if (!process.argv.includes('--execute')) {
  console.log('NOT RUN: pass --execute --device papers3|stopwatch --runtime <built-dir> --firmware <official.bin> --out <ignored-dir>');
  process.exit(0);
}
const args = process.argv.slice(2), option = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const device = option('--device', 'papers3');
assert.ok(['papers3', 'stopwatch'].includes(device));
assert.ok(option('--runtime') && option('--firmware'));
const runtimeDirectory = resolve(option('--runtime')), firmwarePath = resolve(option('--firmware'));
const output = resolve(option('--out', `.work/public-browser-guest-${device}`));
await mkdir(output, {recursive: true});
const manifest = JSON.parse(await readFile(resolve(runtimeDirectory, 'runtime.json')));
assert.equal(manifest.build.kind, 'source-build', 'This acceptance requires a rebuilt source runtime.');
const firmware = await readFile(firmwarePath);
const expected = device === 'papers3' ? 'd6733a0ca378f95335fa5fba4d4d992fb1dd97c17557b20e9aebfca08ba6d624' : '6395799089341e0ae96072c2a3418d469d6797b2ab8ee0cab1c9ed24a42acbbe';
assert.equal(createHash('sha256').update(firmware).digest('hex'), expected);
const harness = '<!doctype html><meta charset="utf-8"><title>Browser guest regression</title><style>body{margin:0;background:white}canvas{max-height:850px;max-width:100%;image-rendering:pixelated}</style><canvas id="frame"></canvas>';
const mime = {'.mjs':'text/javascript', '.js':'text/javascript', '.json':'application/json', '.wasm':'application/wasm', '.html':'text/html'};
let apiRequests = 0;
const server = createServer(async (request, response) => {
  const path = new URL(request.url, 'http://localhost').pathname;
  try {
    if (path.startsWith('/api/')) {apiRequests++; response.writeHead(403); response.end(); return;}
    if (path === '/__guest__') {response.setHeader('Content-Type', 'text/html'); response.end(harness); return;}
    if (path === '/firmware.bin') {response.setHeader('Content-Type', 'application/octet-stream'); response.end(firmware); return;}
    if (path === '/favicon.ico') {response.writeHead(204); response.end(); return;}
    const runtimePrefix = '/platform/runtime/esp32sim/';
    const file = path.startsWith(runtimePrefix) ? resolve(runtimeDirectory, path.slice(runtimePrefix.length)) : resolve(root, '.' + decodeURIComponent(path));
    const allowed = path.startsWith(runtimePrefix) ? file.startsWith(runtimeDirectory + '/') : file.startsWith(root + '/platform/web/');
    if (!allowed) {response.writeHead(403); response.end(); return;}
    response.setHeader('Content-Type', mime[extname(file)] || 'application/octet-stream');
    response.end(await readFile(file));
  } catch {response.writeHead(404); response.end();}
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
const page = await browser.newPage({viewport: {width: 1100, height: 900}});
const pageErrors = [], consoleErrors = [];
page.on('pageerror', error => pageErrors.push(error.message));
page.on('console', message => {if (message.type() === 'error') consoleErrors.push(message.text());});
const receipt = {schema_version: 1, category:'browser-virtual-device-regression', device, status:'FAIL', checked_at:new Date().toISOString(),
  firmware_sha256:expected, runtime:manifest, browser:browser.version(), hardware_validation:'NOT RUN', checkpoints:[], api_requests:0};
const started = Date.now();
async function wait(predicate, timeout = 180000) {
  await page.waitForFunction(predicate, null, {timeout});
}
async function clock() {
  return page.evaluate(async () => {
    const inputId = ++window.clockId;
    return (await window.guest.ask(`input:${inputId}`, {op:'text', data:'{}', inputId})).time;
  });
}
async function advance(seconds) {
  const target = await clock() + seconds, deadline = Date.now() + 180000;
  while (await clock() < target) {assert.ok(Date.now() < deadline, 'Guest clock deadline'); await new Promise(resolve => setTimeout(resolve, 20));}
}
async function checkpoint(name) {
  await page.evaluate(() => window.guest.pause());
  const info = await page.evaluate(async () => {
    const frame = window.lastFrame;
    if (!frame) throw new Error('No controller output frame');
    const hash = data => crypto.subtle.digest('SHA-256', data).then(bytes => Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join(''));
    let dark = 0, light = 0;
    for (let i = 0; i < frame.pixels.length; i += 2) {const v = frame.pixels[i] | frame.pixels[i + 1] << 8; if (v < 0x1082) dark++; if (v > 0xef7d) light++;}
    const crop = new Uint8Array(160 * 160 * 2);
    const x = frame.width === 540 ? 30 : 80, y = frame.width === 540 ? 270 : 90;
    for (let row = 0; row < 160; row++) crop.set(frame.pixels.subarray(((y+row)*frame.width+x)*2,((y+row)*frame.width+x+160)*2),row*320);
    return {width:frame.width,height:frame.height,sequence:frame.sequence,dark_pixels:dark,light_pixels:light,sha256:await hash(frame.pixels),region_sha256:await hash(crop),observe:window.guest.observe()};
  });
  assert.ok(info.dark_pixels > 100 && info.light_pixels > 100, 'Application frame must contain real contrasting content');
  receipt.checkpoints.push({name, ...info});
  await page.locator('#frame').screenshot({path:resolve(output, name+'.png')});
  console.log(JSON.stringify({phase:name,guest_seconds:info.observe.stats.time,sequence:info.sequence,width:info.width,height:info.height}));
  return info;
}
async function tap(x, y) {
  await page.evaluate(({x,y}) => window.guest.input({type:'touch',x,y,down:true}), {x,y});
  await advance(0.15);
  await page.evaluate(({x,y}) => window.guest.input({type:'touch',x,y,down:false}), {x,y});
  await advance(device === 'papers3' ? 4.5 : 1.5);
}
try {
  await page.goto(base+'/__guest__');
  await page.evaluate(async ({device}) => {
    const {PublicBrowserRuntime} = await import('/platform/web/public-browser-runtime.js');
    window.serial = ''; window.runtimeErrors = []; window.clockId = 1000000;
    window.guest = new PublicBrowserRuntime({onSerial:text => {window.serial=(window.serial+text).slice(-200000);}, onError:error=>window.runtimeErrors.push(error.message), onFrame:frame=>{
      window.lastFrame = frame;
      const canvas=document.getElementById('frame');canvas.width=frame.width;canvas.height=frame.height;
      const ctx=canvas.getContext('2d'), image=ctx.createImageData(frame.width,frame.height);
      for(let i=0,j=0;i<frame.pixels.length;i+=2,j+=4){const v=frame.pixels[i]|frame.pixels[i+1]<<8;image.data[j]=(v>>11&31)*255/31;image.data[j+1]=(v>>5&63)*255/63;image.data[j+2]=(v&31)*255/31;image.data[j+3]=255;}
      ctx.putImageData(image,0,0);
    }});
    await window.guest.start({device,firmware:await (await fetch('/firmware.bin')).arrayBuffer()});
  }, {device});
  console.log('phase: real browser Worker/ROM boot started');
  if (device === 'papers3') await wait(() => window.serial.includes('AppWifi') && window.guest.observe().stats.time > 14);
  else {await wait(() => window.lastFrame?.sequence > 0); await advance(15);}
  receipt.first_application_wall_ms = Date.now()-started;
  const boot = await checkpoint('official-boot');
  if (device === 'papers3') {
    assert.equal(boot.width, 540); assert.equal(boot.height, 960);
    await page.evaluate(() => window.guest.resume()); await tap(116,330);
    const toggle = await checkpoint('touch-toggle');
    assert.notEqual(toggle.region_sha256,boot.region_sha256,'GT911 touch must change the official application icon');
    await page.evaluate(() => window.guest.resume()); await tap(116,330);
    await checkpoint('touch-return');
  } else {
    assert.equal(boot.width,468); assert.equal(boot.height,466);
    await page.evaluate(() => window.guest.resume());
    await page.evaluate(async () => {await window.guest.input({type:'button',id:'a',down:true});await window.guest.input({type:'button',id:'b',down:true});});
    await advance(1.5);
    await page.evaluate(async () => {await window.guest.input({type:'button',id:'a',down:false});await window.guest.input({type:'button',id:'b',down:false});});
    await advance(2);
    const menu = await checkpoint('button-menu');
    assert.notEqual(menu.region_sha256, boot.region_sha256,'A+B must change the official menu content');
    await page.evaluate(() => window.guest.resume()); await tap(234,233);
    await checkpoint('touch-open-app');
  }
  const before = await page.evaluate(() => window.guest.observe().sequence);
  await new Promise(resolve => setTimeout(resolve,300));
  assert.equal(await page.evaluate(() => window.guest.observe().sequence),before,'Paused guest must stop publishing frames');
  assert.deepEqual(await page.evaluate(() => window.runtimeErrors),[]);
  assert.deepEqual(pageErrors,[]); assert.deepEqual(consoleErrors,[]);
  assert.equal(apiRequests,0,'Browser execution must not use a server simulation API');
  receipt.status='PASS';
} catch (error) {
  receipt.error={name:error.name,message:error.message};
  console.error(error.stack); process.exitCode=1;
} finally {
  receipt.elapsed_ms=Date.now()-started;
  receipt.api_requests=apiRequests;
  receipt.page_errors=pageErrors;
  const serial=await page.evaluate(() => window.serial || '').catch(()=>'');
  await writeFile(resolve(output,'serial.log'),serial);
  await page.evaluate(() => window.guest?.stop()).catch(()=>{});
  receipt.stopped=await page.evaluate(() => window.guest?.observe().status).catch(()=>null);
  await writeFile(resolve(output,'report.json'),JSON.stringify(receipt,null,2)+'\n');
  await browser.close(); await new Promise(resolve=>server.close(resolve));
}
