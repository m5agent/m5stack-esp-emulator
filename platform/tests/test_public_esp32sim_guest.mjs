// Requires an exported site on a private test port and external firmware fixtures.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {createServer} from 'node:http';

if (!process.env.M5_BROWSER_SITE) {
  console.log('NOT RUN: set M5_BROWSER_SITE, M5_DOCS_FIRMWARE and M5_UIFLOW_FIRMWARE.');
  process.exit(0);
}
const site = new URL(process.env.M5_BROWSER_SITE);
const firmware = process.env.M5_DOCS_FIRMWARE;
const uiflow = process.env.M5_UIFLOW_FIRMWARE;
const out = path.resolve(process.env.M5_BROWSER_EVIDENCE || '.work/esp32sim-browser-evidence');
fs.mkdirSync(out,{recursive:true});
const cases = [
  ['cores3','display'], ['cardputer-adv','display'], ['cores3','touch'],
  ['cardputer-adv','keyboard'], ['cores3','uiflow'], ['cardputer-adv','button'],
];
const advUiflow = process.env.M5_ADV_UIFLOW_FIRMWARE;
if (advUiflow) cases.push(['cardputer-adv','stock-uiflow']);
const cardputerKeyboard = process.env.M5_CARDPUTER_KEYBOARD_FIRMWARE;
if (cardputerKeyboard) cases.push(['cardputer','keyboard']);
const cardputerStock = process.env.M5_CARDPUTER_STOCK_FIRMWARE;
if (cardputerStock) cases.push(['cardputer','stock-uiflow']);
if (process.env.M5_LEGACY_FIRMWARE_DIR) cases.push(['papers3','legacy'],['stopwatch','legacy']);
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const runtimeUrl = new URL('platform/runtime/esp32sim/runtime.json',site);
const runtime = await fetch(runtimeUrl).then(response=>{assert(response.ok);return response.json();});
const wasm = await fetch(new URL(runtime.wasm.path,runtimeUrl)).then(response=>response.arrayBuffer());
assert.equal(sha(Buffer.from(wasm)),runtime.wasm.sha256);
const parent = createServer((request, response) => {
  const child = new URL(request.url,'http://127.0.0.1').searchParams.get('child');
  const source = (child || '').replaceAll('&','&amp;').replaceAll('"','&quot;');
  response.setHeader('Content-Type','text/html; charset=utf-8');
  response.end(`<!doctype html><iframe title="Simulator" style="position:absolute;inset:0;border:0;width:100%;height:100%" src="${source}"></iframe>`);
});
await new Promise(resolve=>parent.listen(0,'127.0.0.1',resolve));
(async () => {
  const browser = await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH, args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const cdp = await browser.newBrowserCDPSession();
  const workers = async () => (await cdp.send('Target.getTargets')).targetInfos.filter(t => t.type === 'worker' && t.url.includes('/vendor/esp32sim/'));
  const report = {browser:browser.version(),runtime,cases:[]};
  const jit = process.env.INTERPRETER !== '1';
  const reportFile = path.join(out, (jit ? 'jit' : 'interpreter') + '.json');
  try {
    for (const [device, example] of cases) {
      const label = device + '-' + example;
      if (process.argv.length > 2 && !process.argv.slice(2).includes(label)) continue;
      console.log('Starting', label, {jit});
      const page = await browser.newPage({viewport:{width:1380,height:1000}});
      const row = {device,example,jit,errors:[]};
      report.cases.push(row);
      page.on('pageerror', error => row.errors.push(error.stack));
      page.on('console', msg => {if(msg.type() === 'error') row.errors.push(msg.text());});
      await page.addInitScript(({jit}) => {
        window.probe = {frames:0, nonblack:0, audio:0, sources:0, messages:[], sent:[], pace:null};
        const create = AudioContext.prototype.createBufferSource;
        AudioContext.prototype.createBufferSource = function() {
          probe.sources++;
          return create.call(this);
        };
        window.Worker = class extends Worker {
          constructor(url, options) {
            super(url,options);
            if(!String(url).includes('/vendor/esp32sim/'))return;
            this.addEventListener('message', ({data}) => {
              if(data.pace)probe.pace=data.pace;
              if(data.text?.includes('"t":"stat"')) {
                const stat=JSON.parse(data.text);
                if (stat.gpio_in) (probe.g0 ??= new Set()).add(Number(BigInt(`0x${stat.gpio_in}`) & 1n));
                if (stat.display_rotation) probe.rotation = stat.display_rotation;
              }
              if(data.text && !data.text.includes('"t":"stat"') && probe.messages.length < 500)probe.messages.push(data.text);
              if(data.bin) {
                const b = new Uint8Array(data.bin);
                if (b[0]===2) probe.audio++;
                if (b[0]===1) {
                  probe.frames++;
                  if(b.subarray(5).some(v=>v)) {
                    probe.nonblack++;
                    probe.last = {width:b[1]+256*b[2],height:b[3]+256*b[4],at:performance.now()};
                  }
                }
              }
            });
          }
          postMessage(data, transfer=[]) {
            if(data.op === 'create') {if (!jit && data.board.startsWith('m5stack-')) data={...data,jit};probe.create=data;}
            if(data.op === 'text') probe.sent.push(JSON.parse(data.data));
            return super.postMessage(data,transfer);
          }
        };
      },{jit});
      try {
        const childUrl = new URL(site);
        childUrl.search = new URLSearchParams({device,mode:'browser',autostart:'0',engine:'esp32sim'});
        const parentUrl = new URL(`http://127.0.0.1:${parent.address().port}/`);
        assert.notEqual(parentUrl.origin,childUrl.origin);
        parentUrl.searchParams.set('child',childUrl.href);
        const childResponse = page.waitForResponse(r=>r.url()===childUrl.href && r.request().isNavigationRequest());
        const topResponse = await page.goto(parentUrl.href);
        assert.equal(topResponse.headers()['cross-origin-opener-policy'],undefined);
        assert.equal(topResponse.headers()['cross-origin-embedder-policy'],undefined);
        const headers = (await childResponse).headers();
        assert.equal(headers['cross-origin-opener-policy'],undefined);
        assert.equal(headers['cross-origin-embedder-policy'],undefined);
        const frame = page.frames().find(f => f.url()===childUrl.href);
        assert(frame);
        row.context = await frame.evaluate(() => ({isolated:crossOriginIsolated,sab:typeof SharedArrayBuffer,embedded:parent!==window}));
        assert.deepEqual(row.context,{isolated:false,sab:'undefined',embedded:true});
        const file = device === 'cardputer' ? (example === 'keyboard' ? cardputerKeyboard : cardputerStock)
          : example === 'uiflow' ? uiflow : example === 'stock-uiflow' ? advUiflow : example === 'legacy'
          ? path.join(process.env.M5_LEGACY_FIRMWARE_DIR,`${device}.bin`) : path.join(firmware,device,example,`${example}.ino.merged.bin`);
        row.firmwareSha256 = sha(fs.readFileSync(file));
        await frame.locator('#startBtn').waitFor();
        await frame.locator('[name=firmwareSource][value=local]').evaluate(input=>input.click());
        await frame.locator('#firmwareFile').setInputFiles(file);
        if (example === 'uiflow') await frame.locator('#browserAudioOptIn').check();
        // Start stays disabled until the model has loaded on a cold HTTPS visit.
        await frame.locator('#startBtn').click({timeout:90000});
        await frame.waitForFunction(serialOnly => (serialOnly ? probe.frames > 0 : probe.nonblack > 0) &&
          document.querySelector('#runtimeStatus').dataset.status==='running', example==='button',{timeout:90000});
        row.firstFrame = await frame.evaluate(()=>probe.last);
        const dimensions = {cores3:[320,240],'cardputer-adv':[240,135],cardputer:[240,135],papers3:[540,960],stopwatch:[468,466]};
        if (example!=='button') assert.deepEqual([row.firstFrame.width,row.firstFrame.height],dimensions[device]);
        assert.equal(await frame.locator('#firmwareInputSha256').textContent(),row.firmwareSha256);
        row.runtimeFlashSha256 = await frame.locator('#firmwareRuntimeSha256').textContent();
        row.workersBefore = (await workers()).length;
        assert.equal(row.workersBefore,1);
        const screenshot = async suffix => {
          const shot = path.join(out,`${jit?'jit':'interp'}-${label}-${suffix}.png`);
          const mount = frame.locator('#deviceMount');
          await mount.evaluate(element=>element.scrollIntoView({block:'center'}));
          const clip = await mount.boundingBox();
          assert(clip,'visible device mount');
          await page.screenshot({path:shot,clip,timeout:30000});
          return path.basename(shot);
        };
        const settle = async () => page.waitForTimeout(example==='uiflow'?2600:550);
        await settle();
        if (example === 'display') {
          await frame.locator('#pauseBtn').click();
          await frame.waitForFunction(() => document.querySelector('#runtimeStatus').dataset.status==='paused');
        } else if (example === 'touch' || example === 'keyboard' || example === 'uiflow') row.before = await screenshot('before');
        const frameToken = () => frame.locator('#rawFrameCanvas').evaluate(c=>c.toDataURL());
        if (example === 'touch') {
          const before = await frameToken();
          const canvas = frame.locator('#deviceMount canvas').first();
          const bounds = await canvas.boundingBox();
          // Front-facing model, x/y still go through the shell raycast.
          await page.mouse.move(bounds.x+bounds.width*0.50,bounds.y+bounds.height*0.50);
          await page.mouse.down();
          await page.waitForTimeout(450);
          await page.mouse.up();
          await frame.waitForFunction(() => probe.sent.some(e=>e.t==='touch'&&e.down===1),null,{timeout:8000});
          await settle();
          row.changed = (await frameToken())!==before;
          assert(row.changed);
          {
            await page.mouse.move(bounds.x+bounds.width*0.44,bounds.y+bounds.height*0.45);
            await page.mouse.down();
            await page.waitForTimeout(300);
            await page.mouse.up();
            await settle();
          }
        }
        if (example === 'uiflow') {
          await frame.locator('#nativeScreenBtn').click();
          const canvas = frame.locator('#rawFrameCanvas');
          await canvas.scrollIntoViewIfNeeded();
          const before = await frameToken();
          const bounds = await canvas.boundingBox();
          await page.mouse.move(bounds.x+bounds.width*(34/320),bounds.y+bounds.height*(47/240));
          await page.mouse.down();
          await page.waitForTimeout(550);
          await page.mouse.up();
          await settle();
          row.changed = (await frameToken())!==before;
          assert(row.changed,'UIFlow2 settings tap must redraw the panel');
          await frame.waitForFunction(() => {
            const canvas = document.querySelector('#rawFrameCanvas');
            const [r,g,b] = canvas.getContext('2d').getImageData(10,45,1,1).data;
            return r < 30 && g > 100 && b > 140;
          },null,{timeout:10000});
          await frame.waitForFunction(() => probe.audio > 0 && probe.sources > 0,null,{timeout:10000});
        }
        if (example === 'button') {
          await frame.locator('#deviceMount canvas').first().focus();
          await page.keyboard.press('F12',{delay:650});
          await frame.waitForFunction(() => {
            const serial=document.querySelector('#serialOutput').textContent;
            return serial.includes('Button A Pressed') && serial.includes('Button A Released');
          },null,{timeout:12000});
        }
        if (example === 'keyboard') {
          const before = await frameToken();
          await frame.locator('#deviceMount canvas').first().focus();
          const inputs = device === 'cardputer' ? ['a','b','Enter','F12'] : ['a','b','Enter','ArrowUp','F12'];
          for (const key of inputs) await page.keyboard.press(key,{delay:220});
          await settle();
          row.changed = (await frameToken())!==before;
          assert(row.changed);
          const inputsSent = await frame.evaluate(() => probe.sent);
          const key = device === 'cardputer' ? 'enter' : 'fn';
          assert(inputsSent.some(event=>event.t==='matrix-key' && event.key===key && event.down===1));
          assert(inputsSent.some(event=>event.t==='matrix-key' && event.key===key && event.down===0));
          if (device === 'cardputer') {
            assert(inputsSent.some(event=>event.t==='btn' && event.pin===0 && event.v===1));
            assert(inputsSent.some(event=>event.t==='btn' && event.pin===0 && event.v===0));
          }
        }
        if (device === 'cardputer' && example === 'stock-uiflow') {
          const before = await frameToken();
          await frame.locator('#deviceMount canvas').first().focus();
          await page.keyboard.press('F12',{delay:450});
          await settle();
          row.changed = (await frameToken()) !== before;
          assert(row.changed,'stock launcher must redraw after GPIO0 input');
          assert(await frame.evaluate(() => probe.sent.some(event => event.t === 'btn' && event.pin === 0 && event.v === 1)));
        }
        if (example === 'touch' || example === 'legacy') {
          await frame.locator('#pauseBtn').click();
          await frame.waitForFunction(() => document.querySelector('#runtimeStatus').dataset.status==='paused');
          await frame.locator('#pauseBtn').click();
          await frame.waitForFunction(() => document.querySelector('#runtimeStatus').dataset.status==='running');
          row.pauseResume = true;
        }
        if (example !== 'button') row.after = await screenshot('after');
        const png = Buffer.from((await frameToken()).split(',')[1],'base64');
        fs.writeFileSync(path.join(out,`${jit?'jit':'interp'}-${label}-lcd.png`), png);
        row.frameSha256 = sha(png);
        row.workbench = await frame.evaluate(() => ({probe:{...probe,g0:[...(probe.g0 || [])]},serial:document.querySelector('#serialOutput').textContent, error:document.querySelector('#errorBanner').textContent,frameStatus:document.querySelector('#frameStatus').textContent}));
        assert.equal(row.workbench.error,'');
        await frame.locator('#stopBtn').click();
        await frame.waitForFunction(() => document.querySelector('#runtimeStatus').dataset.status==='stopped');
        for(let i=0;i<100&&(await workers()).length;i++)await page.waitForTimeout(50);
        row.workersAfter = (await workers()).length;
        assert.equal(row.workersAfter,0);
        row.result = 'PASS';
      } catch (error) {
        row.result = 'FAIL'; row.failure = error.stack;
        row.workbench ??= await page.frames().at(-1).evaluate(() => ({probe:window.probe,serial:document.querySelector('#serialOutput')?.textContent,error:document.querySelector('#errorBanner')?.textContent})).catch(()=>null);
        await page.screenshot({path:path.join(out,`${jit?'jit':'interp'}-${label}-fail.png`),timeout:10000}).catch(()=>{});
      }
      fs.writeFileSync(reportFile, JSON.stringify(report,null,2));
      console.log(label,row.result,row.failure?.split('\n')[0]??'',row.workbench?.error??'',row.workbench?.probe?.create??'');
      await page.close();
    }
  } finally { await browser.close(); }
  if(!report.cases.length || report.cases.some(c=>c.result==='FAIL'))process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>parent.close());
