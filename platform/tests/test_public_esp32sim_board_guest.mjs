// Real browser workbench acceptance. Firmware stays outside the export.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {chromium} from 'playwright';
import {getBrowserProfile} from '../web/public-browser-runtime.js';

const site = process.env.M5_BROWSER_SITE;
if (!site) throw new Error('Set M5_BROWSER_SITE to the exported workbench URL.');
const out = process.env.M5_BROWSER_EVIDENCE || '.work/esp32sim-board-guests';
const docs = {
  dial: {file:process.env.M5_DIAL_TOUCH_FIRMWARE,sha256:'8a7136d47e9f569684ccd85e190f031535008cb990b33cd6baa2825ef07a9022'},
  nanoc6: {file:process.env.M5_NANOC6_BUTTON_FIRMWARE,sha256:'d1246ce3912d47bcb92ffc525aac853eea44754fd281ae5eac51893f70f4d8d5'},
};
const keys = {
  cardputer:'F12', 'atom-lite':'Space', atoms3:'Space', 'atoms3-lite':'Space',
  sticks3:'a', paperdiy:'a', stickc:'a', 'stickc-plus':'a', 'stickc-plus-se':'a', nanoc6:'Space',
};
const fixed = [...Object.keys(keys).filter(id => id !== 'nanoc6'), 'stopwatch','stackchan','papermono','papers3'];
const requested = process.argv.slice(2);
const cases = requested.length ? requested : fixed;
for (const id of cases) assert(fixed.includes(id) || docs[id]?.file, `No fixture supplied for ${id}`);

const sha = data => createHash('sha256').update(data).digest('hex');
const fetchAsset = async path => {
  const response = await fetch(new URL(path,site));
  assert(response.ok, `HTTP ${response.status} for ${path}`);
  return Buffer.from(await response.arrayBuffer());
};
const runtime = JSON.parse(await fetchAsset('platform/runtime/esp32sim/runtime.json'));
const registry = JSON.parse(await fetchAsset('platform/web/qemu-browser-profiles.json'));
const manifestSha256 = sha(await fetchAsset('public-site-manifest.json'));
assert.equal(sha(await fetchAsset(`platform/runtime/esp32sim/${runtime.wasm.path}`)),runtime.wasm.sha256);
await mkdir(out,{recursive:true});
const browser = await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const cdp = await browser.newBrowserCDPSession();
const targets = async () => (await cdp.send('Target.getTargets')).targetInfos
  .filter(target => target.type === 'worker' && target.url.includes('/vendor/esp32sim/'));
const report = {kind:'browser virtual-device validation',browser:browser.version(),manifestSha256,runtime,cases:[]};
try {
  for (const id of cases) {
    const profile = getBrowserProfile(id,runtime.profiles);
    assert(profile, `${id} is outside this export`);
    const page = await browser.newPage({viewport:{width:1380,height:1000}});
    const row = {id,profile,errors:[]};
    const rom = profile.chip === 'esp32s3' ? runtime.rom : runtime.extra_roms[profile.chip];
    assert.equal(sha(await fetchAsset(`platform/runtime/esp32sim/${rom.path}`)),rom.sha256);
    row.romSha256 = rom.sha256;
    report.cases.push(row);
    page.on('pageerror',error => row.errors.push(error.message));
    await page.addInitScript(() => {
      const observed = window.observedGuest = {frames:0,serial:'',leds:[],input:[]};
      window.Worker = class extends Worker {
        constructor(url,options) {
          super(url,options);
          if (!String(url).includes('/vendor/esp32sim/')) return;
          this.addEventListener('message', ({data}) => {
            if (data.bin) {
              const pixels = new Uint8Array(data.bin);
              if (pixels[0] === 1) {
                observed.frames++;
                observed.dimensions = [pixels[1]+256*pixels[2],pixels[3]+256*pixels[4]];
              }
            }
            if (!data.text) return;
            let message;
            try { message = JSON.parse(data.text); } catch { return; }
            if (message.t === 'serial') observed.serial = (observed.serial + message.data).slice(-64000);
            if (message.t === 'stat') observed.guestTime = message.time;
            if (message.t === 'ring') observed.leds.push(message.leds);
          });
        }
        postMessage(message,transfer) {
          if (message.op === 'create') observed.create = message;
          if (message.op === 'text') observed.input.push(JSON.parse(message.data));
          return super.postMessage(message,transfer);
        }
      };
    });
    const canvasImage = () => page.locator('#rawFrameCanvas').evaluate(canvas => canvas.toDataURL());
    const uart = pattern => page.waitForFunction(source => new RegExp(source).test(observedGuest.serial),pattern,{timeout:45000});
    const status = value => page.waitForFunction(expected => document.querySelector('#runtimeStatus').dataset.status === expected,value,{timeout:30000});
    const clickTouch = async (x,y,hold) => {
      if (!await page.locator('#rawFramePanel').isVisible()) await page.locator('#nativeScreenBtn').click();
      const canvas = page.locator('#rawFrameCanvas');
      await canvas.scrollIntoViewIfNeeded();
      const bounds = await canvas.boundingBox();
      assert(bounds);
      await page.mouse.move(bounds.x + (x + 0.5) * bounds.width / profile.display.width,
        bounds.y + (y + 0.5) * bounds.height / profile.display.height);
      await page.mouse.down();
      try { await hold(); } finally { await page.mouse.up(); }
    };
    const press = async (key,hold) => {
      await page.locator('#deviceMount canvas').first().focus();
      await page.keyboard.down(key);
      try { await hold(); } finally { await page.keyboard.up(key); }
    };
    try {
      const url = new URL(site);
      url.search = new URLSearchParams({device:id,engine:'esp32sim',mode:'browser',autostart:'0'});
      await page.goto(url.href);
      if (docs[id]) {
        assert.equal(sha(await readFile(docs[id].file)),docs[id].sha256);
        row.inputSha256 = docs[id].sha256;
        await page.locator('[name=firmwareSource][value=local]').evaluate(input => input.click());
        await page.locator('#firmwareFile').setInputFiles(docs[id].file);
      } else {
        const fixture = registry.profiles.find(profile => profile.deviceId === id)?.fixture;
        assert.equal(profile.probeSha256,fixture?.firmwareSHA256);
        row.inputSha256 = fixture.firmwareSHA256;
        await page.locator('#referenceExample').selectOption('probe');
      }
      await page.locator('#startBtn').click({timeout:90000});
      await status('running');
      await page.waitForFunction(() => observedGuest.guestTime >= 2,null,{timeout:45000});
      row.workersBefore = await targets();
      assert.equal(row.workersBefore.length,1);
      assert.equal(await page.locator('#firmwareInputSha256').textContent(),row.inputSha256);
      row.runtimeFlashSha256 = await page.locator('#firmwareRuntimeSha256').textContent();
      assert.match(row.runtimeFlashSha256,/^[a-f0-9]{64}$/);
      if (!docs[id]) await uart('M5_BROWSER_PROBE .+"kind": "ready"');
      if (profile.display) {
        await page.waitForFunction(() => observedGuest.frames > 0);
        assert.deepEqual(await page.evaluate(() => observedGuest.dimensions),[profile.display.width,profile.display.height]);
        await page.waitForFunction(() => {
          const canvas = document.querySelector('#rawFrameCanvas');
          const pixels = canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
          return pixels.some((value,index) => index % 4 !== 3 && value !== 0);
        });
        row.before = await canvasImage();
      }
      if (id === 'nanoc6') {
        await press('Space',() => uart('Button A was pressed'));
        await uart('Button A was released');
      } else if (id === 'dial') {
        await clickTouch(60,60,() => page.waitForTimeout(500));
        await page.waitForFunction(() => {
          const p = document.querySelector('#rawFrameCanvas').getContext('2d').getImageData(60,60,1,1).data;
          return p[0] === 132 && p[1] === 206 && p[2] === 239;
        },null,{timeout:10000});
      } else {
        const fixture = registry.profiles.find(profile => profile.deviceId === id).fixture;
        const count = () => uart('M5_BROWSER_PROBE .+"kind": "count"');
        if (fixture.inputMode === 'touch') {
          const [x,y] = fixture.input.split(':')[1].split(',').map(Number);
          await clickTouch(x,y,count);
        } else await press(keys[id],count);
        await uart('M5_BROWSER_PROBE .+"kind": "released"');
        if (!profile.display) {
          await page.waitForFunction(() => document.querySelector('#frameStatus').textContent.includes('204060'));
          const colors = await page.evaluate(() => observedGuest.leds.flatMap(frame => frame.slice(0,1)));
          assert.deepEqual(colors.slice(-3),[[32,64,96],[64,160,32],[32,64,96]]);
          row.colors = colors.slice(-3);
        }
      }
      if (profile.display) {
        await page.waitForFunction(before => document.querySelector('#rawFrameCanvas').toDataURL() !== before,row.before,{timeout:15000});
        const after = await canvasImage();
        for (const [label,value] of [['before',row.before],['after',after]]) {
          const bytes = Buffer.from(value.split(',')[1],'base64');
          await writeFile(join(out,`${id}-${label}.png`),bytes);
          row[label] = sha(bytes);
        }
      }
      assert.equal(await page.locator('#errorBanner').textContent(),'');
      assert.deepEqual(row.errors,[]);
      row.status = 'PASS';
    } catch (error) {
      row.status = 'FAIL';
      row.failure = error.message;
    } finally {
      if (await page.locator('#stopBtn').isVisible()) {
        await page.locator('#stopBtn').click().catch(() => {});
        await status('stopped').catch(() => {});
      }
      for (let i=0;i<100 && (await targets()).length;i++) await page.waitForTimeout(50);
      row.workersAfter = await targets();
      row.observed = await page.evaluate(() => window.observedGuest);
      if (row.workersAfter.length) row.status = 'FAIL';
      console.log(id,row.status,row.failure || '');
      await writeFile(join(out,'report.json'),JSON.stringify(report,null,2));
      await page.close();
    }
  }
} finally { await browser.close(); }
assert.equal(report.cases.filter(row => row.status !== 'PASS').length,0);
