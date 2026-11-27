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
  tab5: {file:process.env.M5_TAB5_STOCK_FIRMWARE,sha256:'787d5e3c282bc3d200be941a48d7b7ff24acdbe0d9e682a2cfc14796b392feec'},
  'dial-encoder': {file:process.env.M5_DIAL_ENCODER_FIRMWARE,sha256:'932f968f47e4df6d86f2173f0a3309dc2c4b3f6d9a268eabcbadbe800e9f9475'},
};
const matrix = {
  'nesso-n1': {sha256:'d8812d81b3035d8a057c8c1f496e3d62ef1f20a8892908c18ec0338cb1d4a6de',ready:'NESSO_N1_LOOP'},
  atoms3u: {sha256:'2adc6d68254780d28dcf4a6ddfc111a8bf4647281eb6373aed06b3bb6325ecab',ready:'ATOMS3U_RGB 0x204060'},
  'atoms3r-cam': {sha256:'faacd5b1ca9508fe5c3c5ba9e092012c94f9c6bb226419844b6dbfd7e5eb4b6c',ready:'CAM_STATUS ok'},
  'atoms3r-m12': {sha256:'a5c0819cc6f8eb7ce556ed409aa30cffb8a6ce1d51b804fec053cde5bda29f97',ready:'M12_STATUS ok'},
  'atom-echos3r': {sha256:'962f1cd68e6d4f2fe6c305b78628cb544df500ee6a43676d93064cf6d82ffbe9',ready:'VOICES3R_AUDIO_WINDOW_DONE'},
  atomu: {sha256:'e7660eb6cb96440bfb9b76019332b5182c8e5cc9814a856d280dac79af469dbf',ready:'ATOMU_PROBE_READY'},
  'atom-echo': {sha256:'49cb74acfcce9526adf62aa08facb96a082bedeae53ad363010271a6a2629713',ready:'ATOMECHO_PROBE_READY'},
  'basic-v27': {sha256:'fc6592f250ca3f31717eb6c3aa00d811dedf8069163131f48efea044de1014b6',ready:'BASIC27_PROBE_READY'},
  'basic-v27-16mb': {sha256:'f3ed246d70eab8dba118285bece0357ec18360d3395a012c6de487205303d749',ready:'BASIC27_PROBE_READY'},
  'classic-psram-2mb': {sha256:'9c51a6e3fc3594566b4b2d4547a4b6931ff3d7b7a4dafa2c195956b3ddbc7be3',ready:'LX6 memory PASS'},
  'classic-psram-8mb': {sha256:'dd43cdbbdf059aa674202cbdf759e2c158790605b513bf3988b0205ff1d9c866',ready:'LX6 memory PASS'},
  m5stick: {sha256:'13aee21306a73621365a89d2107cd7bcea6d647bb5bb096a6ef6abcf4b3b55f9',ready:'M5STICK_OLED_READY'},
  stickt2: {sha256:'822cc3d86f8d037fbc444ca579d05aab9d9b57c4598628ebc695e700f63c2dce',ready:'STICKT2_BROWSER_READY'},
  'stackchan-body': {sha256:'a09bad10cb0b6f07990cfe42495aec978a3404e881eb6545aafba0ab5dccd3b2',ready:'M5_STACKCHAN_TOUCH.*"kind": "ready"'},
  'core2-mic': {sha256:'006ffc0b5d56f03077f2cc5e90f3b7d0edc45f1dcfa2f27ca872e85029cd974b',ready:'CORE2_BROWSER_MIC_READY'},
  'voices3r-mic': {sha256:'e0dab52e82697fd75089140349f1a879e75c155e93fd56b8c0ec22f5acc2494a',ready:'VOICES3R_BROWSER_MIC_READY'},
};
for (const [id,fixture] of Object.entries(matrix)) {
  if (process.env.M5_BROWSER_MATRIX_FIRMWARE) fixture.file = join(process.env.M5_BROWSER_MATRIX_FIRMWARE,id,'matrix.bin');
}
const keys = {
  cardputer:'F12', 'atom-lite':'Space', atoms3:'Space', 'atoms3-lite':'Space',
  sticks3:'a', paperdiy:'a', stickc:'a', 'stickc-plus':'a', 'stickc-plus-se':'a', nanoc6:'Space',
  atoms3r:'Space', papercolor:'a', stamplc:'a', 'stickc-plus2':'a', 'atom-matrix':'Space', 'atom-matrix-v11':'Space',
};
const fixed = [...Object.keys(keys).filter(id => id !== 'nanoc6'), 'stopwatch','stackchan','papermono','papers3','core2','cardputer-adv'];
const requested = process.argv.slice(2);
const cases = requested.length ? requested : fixed;
for (const id of cases) assert(fixed.includes(id) || docs[id]?.file || matrix[id]?.file, `No fixture supplied for ${id}`);

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
    const deviceId = {'stackchan-body':'stackchan','core2-mic':'core2','voices3r-mic':'atom-echos3r','dial-encoder':'dial',
      'basic-v27-16mb':'basic-v27','classic-psram-2mb':'stickc-plus2','classic-psram-8mb':'core2'}[id] || id;
    const profile = getBrowserProfile(deviceId,runtime.profiles);
    assert(profile, `${id} is outside this export`);
    const page = await browser.newPage({viewport:{width:1380,height:1000}});
    const row = {id,profile,errors:[]};
    const rom = profile.chip === 'esp32s3' ? runtime.rom : runtime.extra_roms[profile.chip];
    assert.equal(sha(await fetchAsset(`platform/runtime/esp32sim/${rom.path}`)),rom.sha256);
    row.romSha256 = rom.sha256;
    report.cases.push(row);
    page.on('pageerror',error => row.errors.push(error.message));
    await page.addInitScript(() => {
      const observed = window.observedGuest = {frames:0,camera:0,audioSamples:0,nonzeroAudio:false,serial:'',logs:[],leds:[],input:[]};
      window.Worker = class extends Worker {
        constructor(url,options) {
          super(url,options);
          if (!String(url).includes('/vendor/esp32sim/')) return;
          this.addEventListener('message', ({data}) => {
            if (data.log) observed.logs.push(String(data.log).slice(0,500));
            if (data.stopped) observed.stopped = data.stopped;
            if (data.bin) {
              const pixels = new Uint8Array(data.bin);
              if (pixels[0] === 1) {
                observed.frames++;
                observed.dimensions = [pixels[1]+256*pixels[2],pixels[3]+256*pixels[4]];
              }
              if (pixels[0] === 2) {
                observed.audioSamples += (pixels.length - 5) / 2;
                observed.nonzeroAudio ||= pixels.subarray(5).some(value=>value !== 0);
              }
              if (pixels[0] === 4) observed.camera++;
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
    const timeout = id === 'papercolor' ? 240000 : 90000;
    const uart = pattern => page.waitForFunction(source => new RegExp(source).test(observedGuest.serial),pattern,{timeout});
    const keyboardEvent = expected => page.waitForFunction(fields => observedGuest.serial.split('\n').some(line => {
      if (!line.startsWith('M5_BROWSER_PROBE ')) return false;
      try {
        const event = JSON.parse(line.slice(17));
        return Object.entries(fields).every(([key,value])=>event[key]===value);
      } catch { return false; }
    }),expected,{timeout:15000});
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
      url.search = new URLSearchParams({device:deviceId,mode:'browser',autostart:'0'});
      if (process.env.M5_BROWSER_USE_DEFAULT !== '1') url.searchParams.set('engine','esp32sim');
      await page.goto(url.href);
      let rotate;
      if (id === 'dial-encoder' || id === 'stickt2') {
        // Exercise the real model-to-workbench rotary event path independently of
        // pointer hit testing. Guest reads remain the success criterion.
        await page.evaluate(async base => {
          const {ModelDeviceShell} = await import(new URL('platform/web/model-shell.js?v=20261026h',base));
          const input = ModelDeviceShell.prototype.handleInput;
          ModelDeviceShell.prototype.handleInput = function (event) {
            globalThis.rotaryShell = this;
            return input.call(this,event);
          };
        },site);
        rotate = async degrees => {
          await page.locator('#deviceMount canvas').first().focus();
          await page.keyboard.press(deviceId==='dial'?'Space':'Enter');
          await page.evaluate(deltaDeg => rotaryShell.model.find('rotation','joint')
            .input('rotate',{deltaDeg,source:'pointer'}),degrees);
        };
      }
      const external = docs[id] || matrix[id];
      if (external) {
        assert.equal(sha(await readFile(external.file)),external.sha256);
        row.inputSha256 = external.sha256;
        await page.locator('[name=firmwareSource][value=local]').evaluate(input => input.click());
        await page.locator('#firmwareFile').setInputFiles(external.file);
      } else {
        const fixture = registry.profiles.find(profile => profile.deviceId === id)?.fixture;
        assert.equal(profile.probeSha256,fixture?.firmwareSHA256);
        row.inputSha256 = fixture.firmwareSHA256;
        await page.locator('#referenceExample').selectOption('probe');
      }
      if (id === 'tab5') await page.locator('#browserSidecarFile').setInputFiles(process.env.M5_TAB5_C6_SIDECAR);
      const starting = Date.now();
      await page.locator('#startBtn').click({timeout:90000});
      await status('running');
      const memoryProbe = id.startsWith('classic-psram-');
      if (!memoryProbe) await page.waitForFunction(() => observedGuest.guestTime >= 2,null,{timeout:45000});
      row.workersBefore = await targets();
      assert.equal(row.workersBefore.length,1);
      assert.equal(await page.locator('#firmwareInputSha256').textContent(),row.inputSha256);
      row.runtimeFlashSha256 = await page.locator('#firmwareRuntimeSha256').textContent();
      assert.match(row.runtimeFlashSha256,/^[a-f0-9]{64}$/);
      if (id === 'tab5') await page.waitForFunction(() => observedGuest.guestTime >= 7,null,{timeout:180000});
      if (matrix[id]) await uart(matrix[id].ready);
      else if (!docs[id]) await uart('M5_BROWSER_PROBE .+"kind": "ready"');
      row.readyMs = Date.now() - starting;
      const observeDisplay = profile.display && !memoryProbe && !['stackchan-body','core2-mic'].includes(id);
      if (observeDisplay) {
        await page.waitForFunction(() => observedGuest.frames > 0);
        assert.deepEqual(await page.evaluate(() => observedGuest.dimensions),[profile.display.width,profile.display.height]);
        await page.waitForFunction(() => {
          const canvas = document.querySelector('#rawFrameCanvas');
          const pixels = canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
          return pixels.some((value,index) => index % 4 !== 3 && value !== 0);
        });
        row.before = await canvasImage();
      }
      if (memoryProbe) {
        assert.equal(await page.evaluate(() => observedGuest.create.psram_mb),profile.psramMb);
        await uart(`LX6 PSRAM physical=${profile.psramMb * 1048576} heap=`);
        if (profile.psramMb === 8) await uart('LX6 HIMEM capacity=4227072 pages=127,128,255 OK');
      } else if (id === 'stackchan-body') {
        for (const [index,key] of ['z','x','c'].entries()) {
          const levels = [0,0,0]; levels[index]=3;
          const previous = await page.evaluate(() => observedGuest.serial.length);
          const state = expected => page.waitForFunction(({previous,expected}) => observedGuest.serial.slice(previous).split('\n').some(line => {
            if (!line.startsWith('M5_STACKCHAN_TOUCH ')) return false;
            try {
              const result = JSON.parse(line.slice('M5_STACKCHAN_TOUCH '.length));
              return result.kind==='state' && String(result.levels)===String(expected);
            } catch { return false; }
          }),{previous,expected},{timeout:15000});
          await press(key,() => state(levels));
          await state([0,0,0]);
        }
      } else if (id === 'core2-mic' || id === 'voices3r-mic') {
        await page.locator('#browserMicFile').setInputFiles(join(process.env.M5_BROWSER_MATRIX_FIRMWARE,'tone.wav'));
        await page.getByText('已将 WAV 送入虚拟麦克风。').waitFor({state:'visible'});
        if (id === 'core2-mic') {
          await clickTouch(160,183,() => uart('CORE2_BROWSER_MIC_SAMPLES [1-9][0-9]+ [1-9][0-9]+'));
        } else {
          await press('Space',() => uart('VOICES3R_BROWSER_MIC_SAMPLES [1-9][0-9]+ [1-9][0-9]+'));
        }
      } else if (id === 'tab5') {
        const adcIndicator = () => page.locator('#rawFrameCanvas').evaluate(canvas =>
          canvas.getContext('2d').getImageData(140,750,1,1).data[0]);
        assert(await adcIndicator() < 150,'ADC must be unselected before the tap');
        await clickTouch(83,755,() => page.waitForTimeout(1800));
        await page.waitForFunction(() => document.querySelector('#rawFrameCanvas')
          .getContext('2d').getImageData(140,750,1,1).data[0] > 240,null,{timeout:15000});
      } else if (id === 'nanoc6') {
        await press('Space',() => uart('Button A was pressed'));
        await uart('Button A was released');
      } else if (id === 'dial') {
        await clickTouch(60,60,() => page.waitForTimeout(500));
        await page.waitForFunction(() => {
          const p = document.querySelector('#rawFrameCanvas').getContext('2d').getImageData(60,60,1,1).data;
          return p[0] === 132 && p[1] === 206 && p[2] === 239;
        },null,{timeout:10000});
      } else if (id === 'dial-encoder') {
        await rotate(67.5);
        await page.waitForFunction(() => observedGuest.input.some(msg=>msg.t==='knob'&&msg.d===3));
      } else if (id === 'nesso-n1') {
        await clickTouch(66,170,() => uart('NESSO_N1_TOUCH .* 1'));
      } else if (profile.camera) {
        await uart('STREAM_DISTINCT (?:[2-9]|[1-9][0-9]+)');
        await page.locator('#browserCameraPanel').waitFor({state:'visible'});
        assert(await page.evaluate(() => observedGuest.camera > 0));
      } else if (id === 'atom-echos3r') {
        await uart('VOICES3R_STATUS ok');
        assert(await page.evaluate(() => observedGuest.nonzeroAudio),'guest PCM must contain nonzero samples');
      } else if (['atoms3u','atomu','atom-echo'].includes(id)) {
        const marker = {atoms3u:'ATOMS3U_BUTTON',atomu:'ATOMU_BUTTON_STATE','atom-echo':'ATOMECHO_BUTTON_STATE'}[id];
        await press('Space',() => uart(`${marker} 1 1`));
        await uart(`${marker} 0 1`);
        await page.waitForFunction(() => observedGuest.leds.some(([rgb])=>String(rgb)==='64,160,32'),null,{timeout:8000});
        if (id === 'atom-echo') assert(await page.evaluate(() => observedGuest.nonzeroAudio));
      } else if (deviceId === 'basic-v27') {
        assert.equal(await page.evaluate(() => observedGuest.create.flash_mb),id === 'basic-v27-16mb' ? 16 : 4);
        for (const [key,pattern] of [['a','1 0 0'],['b','0 1 0'],['c','0 0 1']]) {
          await press(key,() => uart(`BASIC27_BUTTON_STATE ${pattern}`));
          await page.waitForTimeout(250);
        }
      } else if (id === 'm5stick') {
        await press('Space',async () => {
          await uart('M5STICK_OLED_BUTTON 0');
          await page.waitForFunction(before => document.querySelector('#rawFrameCanvas').toDataURL() !== before,row.before,{timeout:10000});
          const pressed = Buffer.from((await canvasImage()).split(',')[1],'base64');
          row.pressedFrame = sha(pressed);
          await writeFile(join(out,`${id}-pressed.png`),pressed);
        });
        await uart('M5STICK_OLED_BUTTON 1');
        row.before = sha(Buffer.from(row.before.split(',')[1],'base64'));
      } else if (id === 'stickt2') {
        await press('Enter',() => uart('STICKT2_BROWSER_INPUT 0 1 1 1'));
        await uart('STICKT2_BROWSER_INPUT 0 0 1 1');
        await press('a',() => uart('STICKT2_BROWSER_INPUT 0 0 0 1'));
        await press('b',() => uart('STICKT2_BROWSER_INPUT 0 0 1 0'));
        await rotate(67.5);
        await uart('STICKT2_BROWSER_INPUT 3 0 1 1');
      } else if (id === 'cardputer-adv') {
        const oracle = registry.profiles.find(profile => profile.deviceId === id).fixture.keyboardOracle;
        const marker = async pressed => page.waitForFunction(({x,y,width,height,rgb}) => {
          const canvas = document.querySelector('#rawFrameCanvas');
          const pixels = canvas.getContext('2d').getImageData(x,y,width,height).data;
          for (let at=0;at<pixels.length;at+=4) {
            const packed = (pixels[at]>>3)<<11 | (pixels[at+1]>>2)<<5 | pixels[at+2]>>3;
            if (packed !== rgb) return false;
          }
          return true;
        },{...oracle.stateMarker,rgb:pressed ? 0xfe68 : 0x23bf},{timeout:15000});
        for (const [index,{domKey,keycode,row:line,col}] of oracle.cases.entries()) {
          const key = domKey.replace(/^(Key|Digit)/,'').toLowerCase();
          const input = {enter:'Enter',space:'Space',backspace:'Backspace'}[key] || key;
          await press(input,async () => {
            await keyboardEvent({kind:'count',keycode,row:line,col,count:index+1});
            await marker(true);
          });
          await keyboardEvent({kind:'released',keycode,row:line,col,count:index+1,driver_pressed:false});
          await marker(false);
        }
        row.keyboardCases = oracle.cases.length;
      } else {
        const fixture = registry.profiles.find(profile => profile.deviceId === id).fixture;
        const count = () => uart('M5_BROWSER_PROBE .+"kind": "count"');
        if (fixture.inputMode === 'touch' || fixture.inputMode === 'longpress') {
          const [x,y] = fixture.input.split(':')[1].split(',').map(Number);
          await clickTouch(x,y,count);
        } else await press(keys[id],count);
        await uart('M5_BROWSER_PROBE .+"kind": "released"');
        if (!profile.display) {
          await page.waitForFunction(() => document.querySelector('#frameStatus').textContent.includes('204060'));
          const colors = await page.evaluate(() => observedGuest.leds.slice(-3));
          const expected = [[32,64,96],[64,160,32],[32,64,96]];
          assert.deepEqual(colors,expected.map(rgb=>Array(profile.ledTargets.length).fill(rgb)));
          row.colors = colors;
        }
      }
      if (observeDisplay && !row.pressedFrame) {
        await page.waitForFunction(before => document.querySelector('#rawFrameCanvas').toDataURL() !== before,row.before,{timeout});
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
