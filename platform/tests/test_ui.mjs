import { chromium } from 'playwright';

const base = process.env.M5_SIM_BASE || 'http://127.0.0.1:8787';
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));

await page.goto(`${base}/platform/web/`, { waitUntil: 'networkidle' });
await page.waitForFunction(() => document.querySelectorAll('.device-card').length > 0);
const cards = await page.$$eval('.device-card', items => items.map(item => item.innerText));
if (cards.length !== 14) throw new Error(`expected 14 devices, got ${cards.length}`);
const catalogChip = await page.locator('#catalogChip').textContent();
if (!catalogChip.includes('13/14 peripheral-complete')) {
  throw new Error(`catalog completeness chip failed: ${catalogChip}`);
}
const peripheralBadges = await page.$$eval('.peripheral-badge', items => items.length);
if (peripheralBadges !== 14) throw new Error(`expected 14 peripheral badges, got ${peripheralBadges}`);

await page.goto(`${base}/platform/web/firmware.html`, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.m5Firmware?.getState && document.querySelectorAll('#deviceSelect option').length >= 13);
const firmwareUi = await page.evaluate(() => ({
  devices: document.querySelectorAll('#deviceSelect option').length,
  fileInput: Boolean(document.querySelector('#firmwareFile')),
  start: Boolean(document.querySelector('#startBtn')),
  state: window.m5Firmware.getState(),
}));
if (!firmwareUi.fileInput || !firmwareUi.start || firmwareUi.devices < 13) {
  throw new Error(`WebBurner UI failed: ${JSON.stringify(firmwareUi)}`);
}

await page.goto(`${base}/platform/web/device.html?device=esp32-s3/sticks3`, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.m5emu?.ready === true);
const stick = await page.evaluate(() => ({
  renderer: document.querySelector('.three-device-root')?.dataset.renderer,
  peripheralSummary: document.querySelector('#peripheralSummary')?.textContent,
  peripheralCount: document.querySelectorAll('.peripheral-item').length,
  state: window.m5emu.getState()
}));
if (stick.renderer !== 'sticks3-three' || stick.state.deviceId !== 'sticks3') throw new Error('StickS3 profile failed');
if (!stick.peripheralSummary?.includes('外设闭环') || stick.peripheralCount !== 8) {
  throw new Error(`StickS3 peripheral panel failed: ${JSON.stringify(stick)}`);
}
const stickViewer = await page.evaluate(async () => {
  const { StickS3ThreeShell } = await import('/platform/web/sticks3-viewer.js?probe=20261022a');
  const device = await fetch('/devices/esp32-s3/sticks3/device.json', { cache: 'no-store' }).then(response => response.json());
  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;left:-1200px;top:0;width:360px;height:640px';
  document.body.append(host);
  const shell = new StickS3ThreeShell(host, device);
  const events = [];
  shell.on('control', event => events.push(`${event.id}:${event.down ? 'down' : 'up'}:${event.gpio}`));
  const pixels = new Uint8Array(shell.display.width * shell.display.height * 2);
  pixels[0] = 0xf8;
  pixels[1] = 0x00;
  shell.setFrame(pixels, shell.display.width, shell.display.height, 7);
  const pixel = shell.display.getPixel(0, 0);
  shell.model.button('btnA').press('sim');
  shell.model.button('btnA').release('sim');
  shell.model.button('btnB').press('sim');
  shell.model.button('btnB').release('sim');
  shell.model.button('btnPWR').press('sim');
  shell.model.button('btnPWR').release('sim');
  shell.dispose();
  host.remove();
  return { pixel, events, frameSeq: shell.frameSeq };
});
if (stickViewer.pixel.join(',') !== '255,0,0' || stickViewer.frameSeq !== 7) {
  throw new Error(`StickS3 framebuffer bridge failed: ${JSON.stringify(stickViewer)}`);
}
if (stickViewer.events.join(',') !== [
  'a:down:11', 'a:up:11',
  'b:down:12', 'b:up:12',
  'power:down:null', 'power:up:null'
].join(',')) {
  throw new Error(`StickS3 input bridge failed: ${JSON.stringify(stickViewer)}`);
}

const coreViewer = await page.evaluate(async () => {
  const { CoreS3ThreeShell } = await import('/platform/web/cores3-viewer.js?probe=20261022c');
  const THREE = await import('three');
  const device = await fetch('/devices/esp32-s3/cores3/device.json', { cache: 'no-store' }).then(response => response.json());
  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;left:-1600px;top:0;width:420px;height:720px';
  document.body.append(host);
  const shell = new CoreS3ThreeShell(host, device);
  const controls = [];
  const touches = [];
  shell.on('control', event => controls.push(`${event.id}:${event.down ? 'down' : 'up'}:${event.gpio}`));
  shell.on('touch', event => touches.push(`${event.x}:${event.y}:${event.down}`));
  const pixels = new Uint8Array(shell.display.width * shell.display.height * 2);
  pixels[0] = 0xf8;
  pixels[1] = 0x00;
  shell.setFrame(pixels, shell.display.width, shell.display.height, 9);
  const pixel = shell.display.getPixel(0, 0);
  shell.model.button('power').press('sim');
  shell.model.button('power').release('sim');
  shell.display.touch('start', 12, 34, 1);
  shell.display.touch('end', 12, 34, 1);
  const bounds = new THREE.Box3().setFromObject(shell.model.root).getSize(new THREE.Vector3());
  shell.dispose();
  host.remove();
  return {
    pixel,
    controls,
    touches,
    frameSeq: shell.frameSeq,
    bounds: { x: bounds.x, y: bounds.y, z: bounds.z }
  };
});
if (coreViewer.pixel.join(',') !== '255,0,0' || coreViewer.frameSeq !== 9) {
  throw new Error(`CoreS3 framebuffer bridge failed: ${JSON.stringify(coreViewer)}`);
}
if (coreViewer.controls.join(',') !== 'power:down:null,power:up:null') {
  throw new Error(`CoreS3 power bridge failed: ${JSON.stringify(coreViewer)}`);
}
if (coreViewer.touches.join(',') !== '12:34:true,12:34:false') {
  throw new Error(`CoreS3 touch bridge failed: ${JSON.stringify(coreViewer)}`);
}
if (Math.abs(coreViewer.bounds.y - 62) > .05 || Math.abs(coreViewer.bounds.z - 32.05) > .2) {
  throw new Error(`CoreS3 physical bounds failed: ${JSON.stringify(coreViewer.bounds)}`);
}
await page.goto(`${base}/platform/web/device.html?device=esp32-s3/cores3`, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.m5emu?.ready === true);
const coreRenderer = await page.evaluate(() => document.querySelector('.three-device-root')?.dataset.renderer);
if (coreRenderer !== 'cores3-three') throw new Error(`CoreS3 renderer failed: ${coreRenderer}`);

await page.goto(`${base}/platform/web/device.html?device=linux-arm64/cardputer-zero`, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.m5emu?.ready === true);
const zero = await page.evaluate(() => document.querySelector('#runtimeNotice')?.textContent);
if (!zero.includes('Linux')) throw new Error('CardputerZero backend status missing');

await page.goto(`${base}/platform/web/device.html?device=esp32-p4/tab5`, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.m5emu?.ready === true);
const tab5 = await page.evaluate(() => ({
  summary: document.querySelector('#peripheralSummary')?.textContent,
  count: document.querySelectorAll('.peripheral-item').length,
  blockers: document.querySelectorAll('.peripheral-item-blocker').length
}));
if (!tab5.summary?.includes('外设未闭环') || !tab5.summary.includes('临时豁免至 2026-12-31')) {
  throw new Error(`Tab5 exemption summary failed: ${JSON.stringify(tab5)}`);
}
if (tab5.count !== 17 || tab5.blockers !== 15) {
  throw new Error(`Tab5 blocker panel failed: ${JSON.stringify(tab5)}`);
}

await page.goto(`${base}/platform/web/sessions.html`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => document.querySelectorAll('#deviceSelect option').length >= 13);
const sessionsUi = await page.evaluate(() => ({
  service: document.querySelector('#serviceSummary')?.textContent,
  devices: document.querySelectorAll('#deviceSelect option').length,
  hasSessionList: Boolean(document.querySelector('#sessionList')),
}));
if (!sessionsUi.service?.includes('API online') || !sessionsUi.hasSessionList) {
  throw new Error(`sessions dashboard failed: ${JSON.stringify(sessionsUi)}`);
}
const firstCard = page.locator('.session-card').first();
if (await firstCard.count()) {
  const canvas = firstCard.locator('canvas');
  if (await canvas.count()) {
    await canvas.scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollBy(0, 120));
    const before = await page.evaluate(() => window.scrollY);
    const box = await canvas.boundingBox();
    if (!box) throw new Error('sessions canvas has no bounding box');
    await page.mouse.move(box.x + box.width * .15, box.y + box.height * .5);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * .35, box.y + box.height * .35, { steps: 6 });
    await page.mouse.up();
    await page.waitForTimeout(2300);
    const after = await page.evaluate(() => window.scrollY);
    if (Math.abs(after - before) > 2) {
      throw new Error(`sessions drag reset scroll: before=${before} after=${after}`);
    }
  }
}

await page.goto(`${base}/devices/esp32-s3/stopwatch/web/index.html`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => window.m5emu?.ready !== undefined || window.m5emu);
let stopwatch;
const fixtureUrl = process.env.M5_STOPWATCH_FIXTURE_URL;
if (fixtureUrl) {
  await page.evaluate(url => window.m5emu.loadFirmwareUrl(url), fixtureUrl);
  await page.waitForFunction(() => (window.__frames || 0) >= 2, null, { timeout: 180000 });
  stopwatch = await page.evaluate(() => window.m5emu.getState());
  if (!stopwatch.sha256) throw new Error('StopWatch reference runtime missing firmware SHA');
} else {
  stopwatch = await page.evaluate(() => window.m5emu.getState());
  if (!stopwatch.status.includes('等待固件')) throw new Error('StopWatch fixture fallback missing');
}
if (errors.length) throw new Error(`page errors: ${errors.join('; ')}`);

console.log(JSON.stringify({ cards: cards.length, stick, stopwatch }, null, 2));
await browser.close();
