// Compare the same workbench fixture on both browser engines.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdir,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {chromium} from 'playwright';

const site = new URL(process.env.M5_BROWSER_SITE);
const out = process.env.M5_BROWSER_EVIDENCE || '.work/browser-backend-comparison';
const args = process.argv.slice(2);
const ids = args.length ? args : [
  'cardputer','sticks3','stopwatch','stackchan','paperdiy','papermono','papercolor','papers3',
  'atoms3r','atom-matrix','atom-matrix-v11','core2','stickc-plus2',
];
const fetchAsset = async path => {
  const response = await fetch(new URL(path,site));
  assert(response.ok, `HTTP ${response.status} for ${path}`);
  return Buffer.from(await response.arrayBuffer());
};
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const manifest = digest(await fetchAsset('public-site-manifest.json'));
const registry = JSON.parse(await fetchAsset('platform/web/qemu-browser-profiles.json'));
const browser = await chromium.launch({
  executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  args:['--use-gl=angle','--use-angle=metal','--ignore-gpu-blocklist'],
});
const cdp = await browser.newBrowserCDPSession();
const workers = async () => (await cdp.send('Target.getTargets')).targetInfos
  .filter(target => target.type === 'worker');
const report = {kind:'browser-WASM virtual-device validation',chrome:browser.version(),manifest,devices:[]};
await mkdir(out,{recursive:true});

try {
  for (const id of ids) {
    const profile = registry.profiles.find(row=>row.deviceId===id);
    const device = {id,engines:[]};
    report.devices.push(device);
    if (!profile?.fixture) {
      device.status = 'NOT RUN';
      device.reason = 'This export has no admitted QEMU fixture for the board.';
      continue;
    }
    for (const [engine,module,controller] of [
      ['esp32sim','public-browser-runtime.js','PublicBrowserRuntime'],
      ['qemu-wasm','public-qemu-runtime.js','PublicQemuRuntime'],
    ]) {
      const page = await browser.newPage({viewport:{width:1380,height:1000}});
      const row = {engine};
      device.engines.push(row);
      const url = new URL(site);
      url.search = new URLSearchParams({device:id,engine,mode:'browser',autostart:'0'});
      const workerBaseline = await workers();
      const newWorkers = async () => (await workers()).filter(target=>!workerBaseline.some(item=>item.targetId===target.targetId));
      const uart = kind => page.waitForFunction(kind => globalThis.backendProbe.serial.includes(`"kind": "${kind}"`),kind,{timeout:240000});
      const press = async down => {
        const [type,value] = profile.fixture.input.split(':');
        if (type === 'key') {
          const key = id==='cardputer' ? 'F12' : /^(atom|atoms)/.test(id) ? 'Space' : value;
          if (down) {
            await page.locator('#deviceMount canvas').first().focus();
            await page.evaluate(() => {backendProbe.input = performance.now();});
          }
          return page.keyboard[down?'down':'up'](key);
        }
        const [x,y] = value.split(',').map(Number);
        if (down) {
          if (!await page.locator('#rawFramePanel').isVisible()) await page.locator('#nativeScreenBtn').click();
          const canvas = page.locator('#rawFrameCanvas');
          await canvas.scrollIntoViewIfNeeded();
          const bounds = await canvas.boundingBox();
          const size = await canvas.evaluate(c => [c.width,c.height]);
          await page.mouse.move(bounds.x+(x+0.5)*bounds.width/size[0],bounds.y+(y+0.5)*bounds.height/size[1]);
          await page.evaluate(() => {backendProbe.input = performance.now();});
        }
        await page.mouse[down?'down':'up']();
      };
      const frame = () => page.evaluate(async () => {
        const {width,height,pixels} = globalThis.backendProbe.frame;
        const hash = await crypto.subtle.digest('SHA-256',pixels);
        return {width,height,sha256:Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join('')};
      });
      try {
        await page.goto(url.href);
        await page.locator('#referenceExample').selectOption('probe',{timeout:30000});
        await page.evaluate(async ({base,module,controller}) => {
          const Runtime = (await import(new URL(`platform/web/${module}`,base).href))[controller];
          const probe = globalThis.backendProbe = {serial:'',firstFrameMs:null};
          const original = Runtime.prototype.start;
          Runtime.prototype.start = function (...args) {
            probe.runtime = this;
            probe.start = performance.now();
            const onFrame = this.onFrame, onSerial = this.onSerial;
            const onLeds = this.onLeds, onDeviceState = this.onDeviceState;
            if (onLeds) this.onLeds = event => {
              (probe.leds ||= {})[event.target] = event.color;
              return onLeds(event);
            };
            if (onDeviceState) this.onDeviceState = value => {
              if (Array.isArray(value.led_rgb)) probe.qemuLeds = value.led_rgb;
              return onDeviceState(value);
            };
            this.onFrame = (frame,...rest) => {
              probe.frame = frame;
              probe.firstFrameMs ??= performance.now()-probe.start;
              return onFrame(frame,...rest);
            };
            this.onSerial = (chunk,...rest) => {
              probe.serial = (probe.serial + chunk).slice(-64000);
              for (const marker of ['ready','count','released']) {
                if (probe.serial.includes(`"kind": "${marker}"`)) probe[marker] ??= performance.now();
              }
              return onSerial(chunk,...rest);
            };
            return original.apply(this,args);
          };
        },{base:site.href,module,controller});
        await page.locator('#startBtn').click();
        await uart('ready');
        row.bootMs = await page.evaluate(() => backendProbe.ready-backendProbe.start);
        row.firmwareSHA256 = await page.locator('#firmwareRuntimeSha256').textContent();
        assert.equal(row.firmwareSHA256,profile.fixture.firmwareSHA256);
        const workerTargets = await newWorkers();
        row.workersBefore = workerTargets.length;
        assert(row.workersBefore > 0);
        if (profile.display) {
          await page.waitForFunction(() => globalThis.backendProbe.frame?.pixels.some(Boolean),null,{timeout:45000});
          row.before = await frame();
          row.firstFrameMs = await page.evaluate(()=>backendProbe.firstFrameMs);
        } else {
          row.beforeLeds = await page.evaluate(() => backendProbe.qemuLeds || Object.values(backendProbe.leds || {}));
          assert.equal(row.beforeLeds.length,25);
        }
        await press(true);
        try {
          await uart('count');
          if (!profile.display) {
            const sample = await page.waitForFunction(before => {
              const colors = backendProbe.qemuLeds || Object.values(backendProbe.leds || {});
              return colors.length===before.length && colors.some((color,i)=>color!==before[i]) ? colors : null;
            },row.beforeLeds,{timeout:15000});
            row.afterLeds = await sample.jsonValue();
          }
        }
        finally { await press(false); }
        await uart('released');
        row.inputMs = await page.evaluate(() => backendProbe.count-backendProbe.input);
        if (profile.display) {
          const deadline = Date.now()+45000;
          do {
            row.after = await frame();
            if (row.after.sha256 !== row.before.sha256) break;
            await page.waitForTimeout(100);
          } while (Date.now()<deadline);
          assert.notEqual(row.after.sha256,row.before.sha256);
        }
        row.status = 'PASS';
      } catch (error) {
        row.status = 'FAIL';
        row.error = error.message.slice(0,400);
      } finally {
        if (await page.locator('#stopBtn').isVisible()) await page.locator('#stopBtn').click().catch(()=>{});
        const deadline = Date.now()+30000;
        do {
          row.workersAfter = (await newWorkers()).length;
          if (!row.workersAfter) break;
          await page.waitForTimeout(100);
        } while (Date.now()<deadline);
        if (row.workersAfter) row.status = 'FAIL';
        row.lastMarkers = await page.evaluate(() => ['ready','count','released'].filter(
          key => Boolean(globalThis.backendProbe?.[key]))).catch(()=>[]);
        console.log(id,engine,row.status,row.bootMs,row.inputMs,row.error || '');
        await page.close();
      }
    }
    const [a,b] = device.engines;
    device.sameFrames = Boolean(a.before && b.before && a.before.sha256===b.before.sha256 && a.after?.sha256===b.after?.sha256);
    if (a.beforeLeds && b.beforeLeds && a.afterLeds && b.afterLeds)
      device.sameLeds = JSON.stringify(a.beforeLeds)===JSON.stringify(b.beforeLeds)
        && JSON.stringify(a.afterLeds)===JSON.stringify(b.afterLeds);
    await writeFile(join(out,'report.json'),JSON.stringify(report,null,2)+'\n');
  }
} finally { await browser.close(); }
