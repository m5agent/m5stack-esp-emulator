import { chromium } from 'playwright';

const base = process.env.M5_SIM_BASE || 'http://127.0.0.1:8080';
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));

await page.goto(`${base}/platform/web/`, { waitUntil: 'networkidle' });
await page.waitForFunction(() => document.querySelectorAll('.device-card').length > 0);
const cards = await page.$$eval('.device-card', items => items.map(item => item.innerText));
if (cards.length !== 14) throw new Error(`expected 14 devices, got ${cards.length}`);

await page.goto(`${base}/platform/web/device.html?device=esp32-s3/sticks3`, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.m5emu?.ready === true);
const stick = await page.evaluate(() => ({ preset: document.querySelector('.device-body')?.dataset.preset, state: window.m5emu.getState() }));
if (stick.preset !== 'stick' || stick.state.deviceId !== 'sticks3') throw new Error('StickS3 profile failed');

await page.goto(`${base}/platform/web/device.html?device=linux-arm64/cardputer-zero`, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.m5emu?.ready === true);
const zero = await page.evaluate(() => document.querySelector('#runtimeNotice')?.textContent);
if (!zero.includes('Linux')) throw new Error('CardputerZero backend status missing');

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
