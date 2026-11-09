// Explicit opt-in, real public-UI/browser-WASM programming acceptance.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname, extname} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createHash, randomUUID} from 'node:crypto';
import {capturePublicQemuProvenance, QEMU_EXECUTED_WEB_PATHS} from './public_qemu_artifacts.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';
import {stopwatchRedCircleOracle} from './public_qemu_stopwatch_frame_oracle.mjs';
import {papercolorRedFrameOracle} from './public_qemu_papercolor_frame_oracle.mjs';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const site = process.env.M5_PUBLIC_SITE && resolve(process.env.M5_PUBLIC_SITE);
if (!site) { console.log('SKIP: explicit M5_PUBLIC_SITE export required'); process.exit(0); }
const device = process.env.M5_QEMU_DEVICE || 'cores3', basePath = process.env.M5_PUBLIC_BASE_PATH || '/showcase/';
const output = resolve(process.env.M5_PUBLIC_QEMU_OUT || resolve(repo, '.work/public-uiflow-' + device));
assert.ok(output.startsWith(resolve(repo, '.work') + '/'), 'raw evidence must remain in ignored .work storage');
await mkdir(output, {recursive:false});
const readyTimeout = Number(process.env.M5_QEMU_READY_TIMEOUT_MS || 300000);
assert.ok(Number.isSafeInteger(readyTimeout) && readyTimeout >= 30000 && readyTimeout <= 600000);
const smokeOnly = process.env.M5_UIFLOW_SMOKE_ONLY === '1';
const unitPreview = process.env.M5_UIFLOW_UNIT_PREVIEW === '1';
if (unitPreview) assert.ok(device === 'cores3' && !smokeOnly, 'Unit preview acceptance requires the complete CoreS3 editor case');
const modules = process.env.M5_WASM_NODE_MODULES || resolve(repo, 'platform/tests/node_modules');
const {chromium} = await import(pathToFileURL(resolve(modules, 'playwright/index.mjs')));
const nonce = randomUUID().replaceAll('-', ''), hash = bytes => createHash('sha256').update(bytes).digest('hex');
const checks = [], errors = [], requests = [];
const report = {kind:'browser-local-uiflow-programming', device, status:'FAIL', started_at:new Date().toISOString(),
  evidence_level:'virtual-device validation', hardware_validation:'NOT RUN', checks, errors, nonce, programs:[],
  smoke_only:smokeOnly, scope:'Actual public default UIFlow startup, editor input, UART0 raw-paste, guest output and normal Worker cleanup.'};
if (unitPreview) report.unit_preview = {environment:'M5_UIFLOW_UNIT_PREVIEW=1', unit_id:'pir',
  scope:'Independent catalog model alongside the actual CoreS3 browser guest; no Unit is added or granted a guest controller binding.'};
const check = (name, ok, details) => { checks.push({name, ok, details}); assert.ok(ok, name); console.log(name); };
let server, browser, page, workers;
const mime = {'.html':'text/html', '.js':'text/javascript', '.mjs':'text/javascript', '.json':'application/json',
  '.wasm':'application/wasm', '.css':'text/css', '.png':'image/png', '.webp':'image/webp', '.svg':'image/svg+xml', '.woff2':'font/woff2'};

async function waitForGuest(predicate, description, timeout = readyTimeout) {
  const deadline = Date.now() + timeout;
  let nextReceipt = 0;
  for (;;) {
    const current = await page.evaluate(() => ({status:globalThis.uiflowRuntime?.status, console_epoch:globalThis.uiflowRuntime?.consoleEpoch,
      guest_ready:globalThis.uiflowRuntime?.guestReady(),
      serial:globalThis.uiflowRuntime?.serial || '', banner:document.querySelector('#errorBanner')?.hidden ? '' : document.querySelector('#errorBanner')?.textContent,
      python:document.querySelector('#pythonStatus')?.textContent, output:document.querySelector('#pythonOutput')?.textContent,
      executions:globalThis.uiflowExecutions || []}));
    if (Date.now() >= nextReceipt) {
      await writeFile(resolve(output, 'progress.json'), JSON.stringify({waiting_for:description, at:new Date().toISOString(), ...current}, null, 2) + '\n');
      nextReceipt = Date.now() + 10000;
    }
    if (current.banner) throw new Error(current.banner);
    if (/Guru Meditation Error|Interrupt wdt timeout|A fatal error occurred/.test(current.serial)) throw new Error('Guest panic while ' + description);
    if (predicate(current)) return current;
    if (Date.now() >= deadline) throw new Error('Guest observation timed out: ' + description);
    await page.waitForTimeout(100);
  }
}

async function runProgram(name, source, {stdout, stderr, upload = false, preserveEditor = false} = {}) {
  const index = await page.evaluate(() => uiflowExecutions.length);
  if (preserveEditor) {
    assert.equal(await page.locator('#pythonSource').inputValue(),source,'the untouched editor must retain its original source');
  } else if (upload) {
    await page.locator('#pythonFile').setInputFiles({name:'program.py', mimeType:'text/x-python', buffer:Buffer.from(source)});
    await page.waitForFunction(source => document.querySelector('#pythonSource').value === source, source);
  } else await page.locator('#pythonSource').fill(source);
  await page.locator('#pythonRunBtn').click();
  const state = await waitForGuest(state => state.executions[index]?.finished_at, name, 90000);
  const execution = state.executions[index];
  report.programs.push({name, source, source_sha256:hash(source), ...execution, ui_output:state.output, ui_status:state.python});
  check(name + '-source-reached-same-guest', execution.source === source && execution.result?.sessionId === report.session_id
    && execution.generation === report.generation && execution.result?.consoleEpoch === report.current_console_epoch && !execution.error, execution);
  if (stdout) check(name + '-stdout', execution.result.stdout.includes(stdout) && state.output.includes(stdout), execution.result);
  if (stderr) check(name + '-stderr', execution.result.stderr.includes(stderr) && state.output.includes(stderr), execution.result);
  else check(name + '-no-stderr', execution.result.stderr === '', execution.result);
  check(name + '-run-reenabled', await page.locator('#pythonRunBtn').isEnabled());
  return execution;
}

async function unitPreviewSnapshot() {
  return page.evaluate(() => {
    const mount = document.querySelector('#unitModelMount'), model = mount?.querySelector('[data-model-source]'),
      canvas = mount?.querySelector('canvas'), bounds = canvas?.getBoundingClientRect();
    return {explorer_open:document.querySelector('#unitExplorer').open,
      selected_unit_id:mount?.dataset.unitId, model_unit_id:model?.dataset.device,
      model_source:model?.dataset.modelSource, visual_only:model?.dataset.visualOnly,
      selected_catalog_button:document.querySelector('[data-unit-model="pir"]')?.getAttribute('aria-pressed'),
      canvases:mount?.querySelectorAll('canvas').length, width:bounds?.width, height:bounds?.height,
      same_model_root:!globalThis.uiflowUnitPreviewRoot || globalThis.uiflowUnitPreviewRoot === model,
      host_unit_models:uiflowShell.model.list('port').filter(port => port.module).length,
      host_picker_selections:[...document.querySelectorAll('#unitAssemblyPanel select')].filter(select => select.value).map(select => select.value),
      runtime_status:globalThis.uiflowRuntime?.status || null};
  });
}
function validUnitPreview(snapshot) {
  return snapshot.explorer_open && snapshot.selected_unit_id === 'pir' && snapshot.model_unit_id === 'pir'
    && snapshot.model_source === 'm5stack-models' && snapshot.visual_only === 'true' && snapshot.selected_catalog_button === 'true'
    && snapshot.canvases === 1 && snapshot.width > 100 && snapshot.height > 100 && snapshot.same_model_root
    && snapshot.host_unit_models === 0 && snapshot.host_picker_selections.length === 0;
}

try {
  report.provenance = await capturePublicQemuProvenance({repo, site, testScript:'platform/tests/test_public_uiflow_guest.mjs',
    webPaths:[...QEMU_EXECUTED_WEB_PATHS, 'platform/web/public-uiflow-firmware.js', 'platform/web/uiflow-workbench-profiles.json', 'platform/web/public-micropython.js']});
  server = createServer(async (request, response) => {
    try {
      const pathname = new URL(request.url, 'http://localhost').pathname;
      if (!pathname.startsWith(basePath)) { response.writeHead(404).end(); return; }
      const file = resolve(site, decodeURIComponent(pathname.slice(basePath.length)) || 'index.html');
      if (!file.startsWith(site + '/')) { response.writeHead(403).end(); return; }
      // Deliberately no isolation headers: exercise the exported Pages worker.
      response.writeHead(200, {'content-type':mime[extname(file)] || 'application/octet-stream', 'cache-control':'no-cache'});
      response.end(await readFile(file));
    } catch { response.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}${basePath}`; report.url = origin;
  browser = await chromium.launch({headless:true,
    ...(process.env.M5_WASM_CHROME ? {executablePath:process.env.M5_WASM_CHROME} : {}),
    args:['--enable-webgl', '--use-gl=angle', '--use-angle=metal', '--ignore-gpu-blocklist']});
  workers = await observeWorkerTargets(browser); report.browser = browser.version();
  page = await browser.newPage({viewport:{width:1440, height:1100}});
  await page.route(url => [8787, 8830].includes(Number(url.port)) || /\/api\/v1(?:\/|$)/.test(url.pathname), route => route.abort('blockedbyclient'));
  page.on('pageerror', error => errors.push(error.message)); page.on('request', request => requests.push(request.url()));
  await page.goto(origin, {waitUntil:'domcontentloaded'});
  await page.waitForFunction(() => crossOriginIsolated && document.querySelector('#deviceMount')?.dataset.deviceId === 'cores3', {}, {timeout:45000});
  check('pages-service-worker-isolation', await page.evaluate(() => crossOriginIsolated && typeof SharedArrayBuffer === 'function'));
  await page.evaluate(async ({origin, device}) => {
    const {PublicQemuRuntime} = await import(new URL('platform/web/public-qemu-runtime.js', origin));
    const start = PublicQemuRuntime.prototype.start;
    PublicQemuRuntime.prototype.start = function(...args) {
      if (args[0].device === device) globalThis.uiflowRuntime = this;
      return start.apply(this, args);
    };
    const {ModelDeviceShell} = await import(new URL('platform/web/model-shell.js?v=20261026h', origin));
    const create = ModelDeviceShell.create;
    ModelDeviceShell.create = async function(...args) {
      const shell = await create.apply(this, args);
      if (args[1].id === device) globalThis.uiflowShell = shell;
      return shell;
    };
    globalThis.uiflowExecutions = [];
    const {PublicMicroPythonRunner} = await import(new URL('platform/web/public-micropython.js', origin));
    const run = PublicMicroPythonRunner.prototype.run;
    PublicMicroPythonRunner.prototype.run = async function(source, ...args) {
      const record = {source, started_at:new Date().toISOString(), generation:this.runtime.generation, session_id:this.runtime.sessionId, console_epoch:this.runtime.consoleEpoch};
      uiflowExecutions.push(record);
      try { record.result = await run.call(this, source, ...args); return record.result; }
      catch (error) { record.error = error.message; record.error_name = error.name; throw error; }
      finally { record.finished_at = new Date().toISOString(); }
    };
  }, {origin, device});
  await page.locator(`button[data-device-id="${device}"]`).click();
  await page.waitForFunction(device => document.querySelector('#deviceMount')?.dataset.deviceId === device && globalThis.uiflowShell?.device.id === device, device, {timeout:45000});
  report.renderer = await page.evaluate(() => { const gl = uiflowShell.viewer.renderer.getContext(), debug = gl.getExtension('WEBGL_debug_renderer_info'); return gl.getParameter(debug ? debug.UNMASKED_RENDERER_WEBGL : gl.RENDERER); });
  check('hardware-angle-renderer', !/swiftshader|software/i.test(report.renderer), report.renderer);
  await page.locator('.advanced-options > summary').click();
  await page.locator('#runtimeMode').selectOption('browser');
  await page.locator('input[name="firmwareSource"][value="reference"]').check();
  check('uiflow-is-default-firmware', await page.locator('#referenceExample').inputValue() === 'uiflow');
  check('programming-startup-described-accurately', (await page.locator('#referenceDescription').textContent()).includes('网页编程启动脚本'));
  if (unitPreview) {
    await page.locator('#unitExplorer').evaluate(node => node.open = true);
    await page.locator('#unitSearch').fill('PIR');
    await page.locator('[data-unit-model="pir"]').click();
    await page.waitForFunction(() => document.querySelector('#unitModelMount')?.dataset.unitId === 'pir'
      && document.querySelector('#unitModelMount [data-model-source="m5stack-models"][data-device="pir"] canvas'), {}, {timeout:30000});
    report.unit_preview.before_guest = await unitPreviewSnapshot();
    check('unit-catalog-preview-visible-before-guest', validUnitPreview(report.unit_preview.before_guest)
      && report.unit_preview.before_guest.runtime_status === null, report.unit_preview.before_guest);
    await page.evaluate(() => { globalThis.uiflowUnitPreviewRoot = document.querySelector('#unitModelMount [data-model-source]'); });
    await page.locator('#unitModelMount').screenshot({path:resolve(output, 'unit-preview-before-guest.png')});
  }
  const started = performance.now(); await page.locator('#startBtn').click();
  const ready = await waitForGuest(state => state.status === 'running' && state.serial.includes('M5_UIFLOW_WORKBENCH_READY'), 'UIFlow programming boot');
  report.click_to_ready_ms = performance.now() - started;
  report.initial = await page.evaluate(() => uiflowRuntime.evidence());
  report.session_id = report.initial.session_id; report.generation = await page.evaluate(() => uiflowRuntime.generation);
  report.console_epoch = report.current_console_epoch = report.initial.console_epoch;
  check('actual-programming-startup-marker', ready.serial.includes('M5_UIFLOW_WORKBENCH_READY'), {click_to_ready_ms:report.click_to_ready_ms, receipt:report.initial.receipt});
  const registry = JSON.parse(await readFile(resolve(site, 'platform/web/uiflow-workbench-profiles.json')));
  const expected = registry.profiles.find(row => row.deviceId === device);
  check('exact-uiflow-firmware-and-ready-binding', report.initial.receipt.firmwareSha256 === expected.firmwareSHA256
    && await page.evaluate(() => uiflowRuntime.profile.readyFirmwareSHA256) === expected.firmwareSHA256);
  const initialEditorSource='import M5\nM5.begin()\nprint("Hello, UIFlow!")\n';
  report.initial_editor_source={source:await page.locator('#pythonSource').inputValue(),expected_sha256:hash(initialEditorSource)};
  check('untouched-default-editor-source',report.initial_editor_source.source===initialEditorSource,report.initial_editor_source);
  await runProgram('default-editor-first-run',initialEditorSource,{stdout:'Hello, UIFlow!',preserveEditor:true});
  await runProgram('default-editor-repeat-run',initialEditorSource,{stdout:'Hello, UIFlow!',preserveEditor:true});
  const utf8 = `M5_UTF8_${nonce}:你好，UIFlow 世界`;
  await runProgram('utf8-print', `print(${JSON.stringify(utf8)})\n`, {stdout:utf8});
  await runProgram('multiline-loop', `total = 0\nfor value in range(10):\n    total += value\nprint("M5_SUM_${nonce}", total)\n`, {stdout:`M5_SUM_${nonce} 45`});
  if (!smokeOnly) {
    await runProgram('long-utf8-source', `text = ${JSON.stringify('界'.repeat(1500))}\nprint("M5_LONG_${nonce}", len(text))\n`, {stdout:`M5_LONG_${nonce} 1500`});
    await runProgram('syntax-error', 'if True print("invalid")\n', {stderr:'SyntaxError'});
    await runProgram('runtime-error', `print("M5_BEFORE_ERROR_${nonce}")\nraise RuntimeError("M5_EXPECTED_ERROR_${nonce}")\n`, {stdout:`M5_BEFORE_ERROR_${nonce}`, stderr:`M5_EXPECTED_ERROR_${nonce}`});
    await runProgram('file-import-recovery', `print("M5_IMPORTED_${nonce}")\n`, {stdout:`M5_IMPORTED_${nonce}`, upload:true});
    const index = await page.evaluate(() => uiflowExecutions.length), source = `import time\nprint("M5_LOOP_${nonce}")\nwhile True:\n    time.sleep_ms(10)\n`;
    await page.locator('#pythonSource').fill(source); await page.locator('#pythonRunBtn').click();
    await waitForGuest(state => state.output.includes(`M5_LOOP_${nonce}`), 'infinite program output', 90000);
    check('infinite-program-has-interrupt-control', await page.locator('#pythonInterruptBtn').isEnabled());
    await page.locator('#pauseBtn').click();
    await page.waitForFunction(() => uiflowRuntime.status === 'paused', {}, {timeout:30000});
    await page.waitForTimeout(300);
    check('pause-retains-program-owner', await page.evaluate(index => !uiflowExecutions[index].finished_at
      && !!uiflowRuntime.uartOwner && document.querySelector('#pythonInterruptBtn').disabled
      && document.querySelector('#pythonRunBtn').disabled, index));
    await page.locator('#pauseBtn').click();
    await page.waitForFunction(() => uiflowRuntime.status === 'running', {}, {timeout:30000});
    check('resume-retains-interrupt-control', await page.locator('#pythonInterruptBtn').isEnabled());
    await page.locator('#pythonInterruptBtn').click();
    const interrupted = await waitForGuest(state => state.executions[index]?.finished_at, 'infinite program interruption', 15000);
    report.programs.push({name:'infinite-program-interrupt', source, source_sha256:hash(source), ...interrupted.executions[index], ui_output:interrupted.output});
    check('guest-acknowledged-interruption', interrupted.executions[index].result?.interrupted === true
      && interrupted.executions[index].result.stderr.includes('KeyboardInterrupt') && await page.locator('#pythonRunBtn').isEnabled(), interrupted.executions[index]);
    await runProgram('same-vm-after-interrupt', `print("M5_RECOVERED_${nonce}")\n`, {stdout:`M5_RECOVERED_${nonce}`});
    if(device==='corematrix'){
      const before=await page.evaluate(()=>uiflowRuntime.lastFrame?.sourceSequence??0);
      const marker=`M5_COREMATRIX_FRAME_${nonce}`;
      const source=`import M5\nd = M5.Lcd\nd.setRotation(0)\nd.setBrightness(255)\nd.clear(0)\nd.fillRect(1, 2, 4, 3, 0xFFFFFF)\nprint("${marker}", M5.getBoard(), d.width(), d.height())\n`;
      await runProgram('guest-display-output',source,{stdout:`${marker} 152 16 16`});
      const observed=await page.waitForFunction(after=>{
        const f=uiflowRuntime.lastFrame;
        if(!f||f.width!==16||f.height!==16||f.pixels.length!==512||f.sourceSequence<=after)return false;
        let lit=0;
        for(let y=0;y<16;y++)for(let x=0;x<16;x++){
          const at=(y*16+x)*2,value=f.pixels[at]|(f.pixels[at+1]<<8);
          const white=x>=1&&x<5&&y>=2&&y<5;
          if(value!==(white?0xffff:0))return false;
          lit+=white;
        }
        return {width:f.width,height:f.height,sequence:f.sequence,source_sequence:f.sourceSequence,lit_pixels:lit,
          pattern:'corematrix-white-rectangle-v1'};
      },before,{timeout:30000,polling:250});
      report.frame=await observed.jsonValue();
      await observed.dispose();
      check('corematrix-source-drew-exact-fresh-monochrome-frame',report.frame.lit_pixels===12,report.frame);
      await page.screenshot({path:resolve(output,'program-matrix-frame.png'),fullPage:true});
    } else if (await page.evaluate(() => !!uiflowRuntime.profile.display)) {
      const et047tc1=['papers3','paperdiy'].includes(device),mono=et047tc1||device==='papermono';
      const monoWidth=et047tc1?540:480,monoHeight=et047tc1?960:800;
      const stopwatch=device==='stopwatch',papercolor=device==='papercolor',marker=`M5_${mono?'MONO':'RED'}_FRAME_${nonce}`;
      const beforeFrame=papercolor?await page.evaluate(()=>({afterSequence:uiflowRuntime.lastFrame?.sequence??0,
        afterSourceSequence:uiflowRuntime.lastFrame?.sourceSequence??0})):null;
      // The original SDK's outermost endWrite flushes the real EPD.
      const source=mono?`import M5\nd = M5.Display\nd.setRotation(0)\nwidth, height = d.width(), d.height()\nif (width, height) != (${monoWidth}, ${monoHeight}) or not d.isEPD():\n    raise RuntimeError("EPD dimensions mismatch")\n${et047tc1?'':'d.setEpdMode(d.EPDMode.EPD_QUALITY)\\n'}d.startWrite()\ntry:\n    d.fillScreen(0xFFFFFF)\n    d.fillRect(0, 0, width // 2, height, 0x000000)\nfinally:\n    d.endWrite()\nprint("${marker}", width, height)\n`
        :stopwatch?`import M5\nd = M5.Display\nd.setRotation(0)\nd.setBrightness(255)\nwidth, height = d.width(), d.height()\nif (width, height) != (468, 468) or d.getBrightness() != 255:\n    raise RuntimeError("StopWatch logical display or brightness mismatch")\nd.fillScreen(0xFF0000)\nprint("${marker}", width, height, d.getBrightness())\n`
        :`import M5\nM5.Lcd.fillScreen(0xFF0000)\nprint("${marker}")\n`;
      await runProgram('guest-display-output', source, {stdout:marker});
      if(stopwatch)await page.waitForFunction(stopwatchRedCircleOracle,{}, {timeout:30000,polling:250});
      else if(papercolor)await page.waitForFunction(papercolorRedFrameOracle,beforeFrame,{timeout:30000,polling:250});
      else await page.waitForFunction(({mono,monoWidth,monoHeight})=>{
        const frame=uiflowRuntime.lastFrame;if(!frame)return false;
        if(mono){
          if(frame.width!==monoWidth||frame.height!==monoHeight||frame.pixels.length!==monoWidth*monoHeight*2)return false;
          for(let y=0;y<frame.height;y++)for(let x=0;x<frame.width;x++){
            const at=(y*frame.width+x)*2,color=frame.pixels[at]|frame.pixels[at+1]<<8;
            if(color!==(x<frame.width/2?0x0000:0xffff))return false;
          }
          return true;
        }
        let red=0;for(let i=0;i<frame.pixels.length;i+=2)if((frame.pixels[i]|frame.pixels[i+1]<<8)===0xf800)red++;
        return red>frame.width*frame.height*.95;
      },{mono,monoWidth,monoHeight},{timeout:30000,polling:250});
      if(!papercolor)report.frame=await page.evaluate(async ({mono,redColor})=>{
        const frame=uiflowRuntime.lastFrame,digest=await crypto.subtle.digest('SHA-256',new Uint8Array(frame.pixels));
        let black=0,white=0,red=0;for(let i=0;i<frame.pixels.length;i+=2){const value=frame.pixels[i]|frame.pixels[i+1]<<8;black+=value===0;white+=value===0xffff;red+=value===redColor;}
        return {width:frame.width,height:frame.height,sequence:frame.sequence,pattern:mono?'mono-half-black-white-v1':'red-fill',
          pixels:frame.width*frame.height,black_pixels:black,white_pixels:white,red_pixels:red,
          ...(mono?{}:{expected_red_rgb565:redColor}),
          sha256:[...new Uint8Array(digest)].map(byte=>byte.toString(16).padStart(2,'0')).join('')};
      },{mono,redColor:papercolor?0xb800:0xf800});
      if(papercolor){
        // One immutable actual snapshot binds pixels, hash and oracle to the
        // same display/source sequence; it never writes guest or host pixels.
        const observed=await page.evaluate(()=>{const frame=uiflowRuntime.lastFrame;
          return {...frame,pixels:Array.from(frame.pixels)};});
        let black=0,white=0,red=0;
        for(let at=0;at<observed.pixels.length;at+=2){const value=observed.pixels[at]|observed.pixels[at+1]<<8;
          black+=value===0;white+=value===0xffff;red+=value===0xb800;}
        report.frame={width:observed.width,height:observed.height,sequence:observed.sequence,
          source_sequence:observed.sourceSequence,pattern:'papercolor-spectra6-red-v1',
          pixels:observed.width*observed.height,black_pixels:black,white_pixels:white,red_pixels:red,
          expected_red_rgb565:0xb800,sha256:hash(Uint8Array.from(observed.pixels)),before_draw:beforeFrame,
          oracle:papercolorRedFrameOracle({frame:observed,...beforeFrame,summary:true})};
        report.frame.oracle_source={path:'platform/tests/public_qemu_papercolor_frame_oracle.mjs',
          sha256:hash(await readFile(resolve(repo,'platform/tests/public_qemu_papercolor_frame_oracle.mjs')))};
        check('papercolor-exact-spectra6-red-and-fresh-frame',report.frame.oracle.matches,report.frame.oracle);
      }
      if(stopwatch){
        report.frame.pattern='stopwatch-round-red-brightness255-v1';
        report.frame.oracle=await page.evaluate(stopwatchRedCircleOracle,{summary:true});
        report.frame.oracle_source={path:'platform/tests/public_qemu_stopwatch_frame_oracle.mjs',
          sha256:hash(await readFile(resolve(repo,'platform/tests/public_qemu_stopwatch_frame_oracle.mjs')))};
        check('stopwatch-exact-round-mask-and-full-brightness',report.frame.oracle.matches,report.frame.oracle);
      }
      check('source-drew-actual-guest-framebuffer', report.frame.width > 0 && report.frame.height > 0, report.frame);
      await page.screenshot({path:resolve(output,mono?'program-mono-frame.png':'program-red-frame.png'),fullPage:true});
    }
  }
  check('same-console-through-pre-reset-programs', await page.evaluate(({session, generation, epoch}) => uiflowRuntime.sessionId === session
    && uiflowRuntime.generation === generation && uiflowRuntime.consoleEpoch === epoch
    && !uiflowRuntime.machineEvents.some(row => row.event === 'RESET'), {session:report.session_id, generation:report.generation, epoch:report.console_epoch}));
  if(!smokeOnly && await page.evaluate(()=>uiflowRuntime.profile.inputs.reset===true)){
    const index=await page.evaluate(()=>uiflowExecutions.length);
    const source=`import time\nprint("M5_RESET_RUNNING_${nonce}")\nwhile True:\n    time.sleep_ms(10)\n`;
    await page.locator('#pythonSource').fill(source);await page.locator('#pythonRunBtn').click();
    await waitForGuest(state=>state.output.includes(`M5_RESET_RUNNING_${nonce}`),'program running before hardware reset',90000);
    await page.evaluate(()=>uiflowRuntime.reset());
    const cancelled=await waitForGuest(state=>state.executions[index]?.finished_at,'old program cancelled by hardware reset',15000);
    check('hardware-reset-cancels-old-console-program',cancelled.executions[index].error_name==='AbortError',cancelled.executions[index]);
    const rebooted=await waitForGuest(state=>state.status==='running'&&state.guest_ready&&state.console_epoch>report.console_epoch,'new UIFlow boot after hardware reset');
    report.hardware_reset={before_console_epoch:report.console_epoch,after_console_epoch:rebooted.console_epoch,
      old_execution:cancelled.executions[index],source,source_sha256:hash(source)};
    report.current_console_epoch=rebooted.console_epoch;
    check('hardware-reset-keeps-browser-session-with-new-console',await page.evaluate(({session,generation})=>uiflowRuntime.sessionId===session
      &&uiflowRuntime.generation===generation&&!uiflowRuntime.uartOwner,{session:report.session_id,generation:report.generation}));
    await runProgram('after-hardware-reset',`print("M5_REBOOT_RECOVERED_${nonce}")\n`,{stdout:`M5_REBOOT_RECOVERED_${nonce}`});
  }else if(!smokeOnly){
    report.hardware_reset={status:'NOT RUN',reason:'The exact browser board profile does not admit hardware reset'};
  }
  if (unitPreview) {
    report.unit_preview.after_programs = await unitPreviewSnapshot();
    check('unit-catalog-preview-preserved-with-running-guest', validUnitPreview(report.unit_preview.after_programs)
      && report.unit_preview.after_programs.runtime_status === 'running', report.unit_preview.after_programs);
    await page.locator('#unitModelMount').screenshot({path:resolve(output, 'unit-preview-with-running-guest.png')});
  }
  await page.screenshot({path:resolve(output, 'workbench.png'), fullPage:true});
  report.before_stop = await page.evaluate(() => uiflowRuntime.evidence());
  await page.evaluate(() => { const frame = uiflowRuntime.iframe, remove = frame.remove; globalThis.deferredUIFlowRemoval = {frame, remove, requests:0}; frame.remove = () => { deferredUIFlowRemoval.requests++; }; });
  await page.locator('#stopBtn').click();
  await page.waitForFunction(() => uiflowRuntime.status === 'stopped', {}, {timeout:45000});
  report.stopped = await page.evaluate(() => uiflowRuntime.evidence());
  const cleanup = report.stopped.cleanup, minimum = cleanup.workersCreated + 1;
  check('normal-guest-exit-no-forced-termination', cleanup.gracefulExit && cleanup.exitCode === 0 && cleanup.workersAtExit === 0
    && cleanup.disposal?.workersRemaining === 0 && cleanup.disposal.workersTerminatedByDispose === 0
    && cleanup.disposal.ownerTerminatesAfterAcknowledgement === true
    && cleanup.engineOwnership?.engineCloseNotifications === 1 && cleanup.engineOwnership.engineNormalTerminations === 1
    && cleanup.engineOwnership?.engineFallbackTerminations === 0, cleanup);
  report.pthreads_closed = await workers.waitUntilOnly({minimumObserved:minimum, allowedUrlPart:'/public-qemu-engine.js', timeoutMs:30000});
  check('pthreads-closed-before-iframe-removal', report.pthreads_closed.ok && await page.evaluate(() => deferredUIFlowRemoval.frame.isConnected && deferredUIFlowRemoval.requests === 1));
  await page.evaluate(() => { deferredUIFlowRemoval.remove.call(deferredUIFlowRemoval.frame); delete globalThis.deferredUIFlowRemoval; });
  report.all_workers_closed = await workers.waitUntilClosed({minimumObserved:minimum});
  check('all-cdp-workers-closed-before-context', report.all_workers_closed.ok, report.all_workers_closed);
  check('no-device-service-requests', !requests.some(url => /\/api\/v1|:8787\b|:8830\b/.test(url)));
  check('no-page-errors', errors.length === 0, errors);
  report.status = 'PASS';
} catch (error) {
  report.error = error.stack || error.message; process.exitCode = 1;
  if (page) {
    report.failure = await page.evaluate(() => ({evidence:globalThis.uiflowRuntime?.evidence(), executions:globalThis.uiflowExecutions,
      python:document.querySelector('#pythonStatus')?.textContent, output:document.querySelector('#pythonOutput')?.textContent,
      banner:document.querySelector('#errorBanner')?.textContent})).catch(() => null);
    await page.screenshot({path:resolve(output, 'failure.png'), fullPage:true}).catch(() => {});
    report.failure_stopped_evidence = await page.evaluate(async () => {
      const runtime=globalThis.uiflowRuntime;if(!runtime)return null;
      await runtime.stop();
      const evidence=runtime.evidence(),frame=evidence.last_frame;
      // Keep the actual post-stop/QMP receipt without duplicating raw pixels.
      const {pixels,...frameSummary}=frame||{};
      return {session_id:evidence.session_id,console_epoch:evidence.console_epoch,status:runtime.status,
        stopped_at:evidence.stopped_at,receipt:evidence.receipt,cleanup:evidence.cleanup,
        machine_events:evidence.machine_events,last_frame:frame?frameSummary:null};
    }).catch(error => ({capture_error:String(error?.message||error)}));
    await page.evaluate(() => { if (globalThis.deferredUIFlowRemoval) deferredUIFlowRemoval.remove.call(deferredUIFlowRemoval.frame); }).catch(() => {});
    if (workers) report.failure_cleanup = await workers.waitUntilClosed({minimumObserved:1, timeoutMs:30000}).catch(() => null);
  }
} finally {
  report.finished_at = new Date().toISOString();
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  await workers?.detach(); await browser?.close(); if (server) await new Promise(resolve => server.close(resolve));
  console.log(JSON.stringify({status:report.status, device, output, error:report.error || null, checks:checks.length}));
}
