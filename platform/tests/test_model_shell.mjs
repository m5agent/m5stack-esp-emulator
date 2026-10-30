// Browser integration/geometry evidence only. No guest, firmware or hardware PASS.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve, extname } from 'node:path';
import { chromium } from 'playwright';
import {installModelProbe, decodeAssetBatch} from './model_shell_probe_helpers.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = process.env.M5_MODEL_TEST_OUT || '/tmp/m5-model-shell-test';
const settings = {batchSize: 4, assetBatchSize: 12, decodeConcurrency: 3, timeoutMs: 20000, cases: []};
for (let i = 2; i < process.argv.length; i++) {
  const option = process.argv[i], value = process.argv[++i];
  assert.ok(value, `Missing value for ${option}`);
  if (option === '--case') {settings.cases.push(value); continue;}
  const spec = {'--batch-size': ['batchSize', 1, 12], '--asset-batch-size': ['assetBatchSize', 2, 24],
    '--decode-concurrency': ['decodeConcurrency', 2, 4], '--timeout-ms': ['timeoutMs', 1000, 60000]}[option];
  assert.ok(spec, `Unknown option ${option}`);
  assert.ok(/^\d+$/.test(value) && Number(value) >= spec[1] && Number(value) <= spec[2], `Invalid ${option}`);
  settings[spec[0]] = Number(value);
}
await mkdir(output, {recursive: true});
const catalog = JSON.parse(await readFile(resolve(root, 'devices/catalog.source.json'), 'utf8'));
const vendorPath = 'platform/web/vendor/m5stack-models/';
const manifest = JSON.parse(await readFile(resolve(root, vendorPath + 'vendor-manifest.json'), 'utf8'));
const products = JSON.parse(await readFile(resolve(root, vendorPath + 'catalog/products.json'), 'utf8')).products;
const assetPaths = Object.keys(manifest.runtime_assets.files);
const runtimeControllers = catalog.devices.map(device => device.id);
assert.ok(runtimeControllers.every(id => manifest.controllers.includes(id)), 'A runtime controller lost its visual model');
// A visual catalog entry is independently browsable; it does not admit a new
// firmware/device profile into the Device Service catalog.
const controllerDevices = manifest.controllers.map(id => catalog.devices.find(device => device.id === id) ||
  {id, name: products.find(product => product.id === id)?.name || id, hardware: {}, visual_only: true});
const modelCases = [...controllerDevices.map(device => ({kind: 'controller', id: device.id})), ...manifest.units.map(id => ({kind: 'unit', id})),
  ...[...manifest.controllers, ...manifest.units].map(id => ({kind: 'preview', id}))]
  .map(test => ({...test, key: `${test.kind}:${test.id}`, configuration: 'default', options: {}}));
const full = settings.cases.length === 0;
const selected = full ? modelCases : settings.cases.filter(key => !['assets', 'interactions', 'interfaces'].includes(key)).map(key => {
  const [identity, configuration] = key.split('#'), test = modelCases.find(test => test.key === identity);
  assert.ok(test, `Unknown model case ${key}`);
  if (!configuration) return {...test};
  const config = products.find(product => product.id === test.id)?.configurations?.find(config => config.id === configuration);
  assert.ok(config, `Unknown catalog configuration ${key}`);
  return {...test, key, configuration, options: config.options};
});
assert.equal(new Set(selected.map(test => test.key)).size, selected.length, 'Duplicate model case');
const expectedArtwork = test => {
  const product = products.find(product => product.id === test.id);
  const prefix = product.entry.slice(0, product.entry.lastIndexOf('/') + 1);
  // One PNG can project onto several surfaces. This is a non-vacuity minimum,
  // not a fabricated equality between image count and material layer count.
  const eligible = assetPaths.filter(path => path.startsWith(prefix) && (test.options.stickerVariant === 'education-cn'
    ? path.includes('education-cn') : !path.includes('education-cn')));
  return eligible.length ? 1 : 0;
};
const harness = `<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;background:#fff}#host{width:900px;height:700px}.three-device-root,.three-device-stage{min-height:700px!important}.three-device-hint{color:#ccc}</style>
<link rel="stylesheet" href="/platform/web/three-device-viewer.css">
<script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script>
</head><body><div id="host"></div></body></html>`;
const mime = {'.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.png': 'image/png'};
const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/__test__') {response.setHeader('Content-Type', 'text/html'); response.end(harness); return;}
    if (pathname === '/favicon.ico') {response.writeHead(204); response.end(); return;}
    const path = resolve(root, '.' + decodeURIComponent(pathname));
    if (!path.startsWith(root + '/')) {response.writeHead(403); response.end(); return;}
    const data = await readFile(path); response.setHeader('Content-Type', mime[extname(path)] || 'application/octet-stream'); response.end(data);
  } catch {response.writeHead(404); response.end();}
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
const integrationFiles = ['platform/web/model-shell.js', 'platform/web/device-shell-factory.js', 'platform/web/unit-annotations.js',
  'platform/web/unit-assembly-layout.js', 'platform/tools/sync_visual_models.py',
  'platform/tests/test_model_shell.mjs', 'platform/tests/model_shell_probe_helpers.mjs', vendorPath + 'vendor-manifest.json', vendorPath + 'catalog/products.json'];
const fingerprints = async () => Object.fromEntries(await Promise.all(integrationFiles.map(async name =>
  [name, createHash('sha256').update(await readFile(resolve(root, name))).digest('hex')])));
const report = {status: 'FAIL', category: 'browser-visual-integration', captured_at: new Date().toISOString(),
  guest_validation: 'NOT RUN', hardware_validation: 'NOT RUN', browser_version: browser.version(), source_commit: manifest.source_commit,
  scope: full ? 'complete-default-models-and-all-assets' : 'explicit-cases', settings,
  integration_sha256: await fingerprints(), controllers: [], units: [], previews: [], interface_census: [], runtime_assets: [], contexts: [],
  catalog_configurations: products.filter(product => product.configurations?.length).map(product => ({id: product.id,
    default: 'constructor options {} tested separately; no configuration alias inferred', configurations: product.configurations.map(config =>
      ({id: config.id, options: config.options, status: selected.some(test => test.id === product.id && test.configuration === config.id) ? 'SELECTED' : 'NOT RUN'}))})),
  limits: ['Browser visual components do not grant Device Service runtime admission', 'Default instances do not cover optional catalog configurations',
    'Printed layer geometry and decoded textures do not prove optical registration, dimensions or electrical behavior', 'Slider output bridge is unsupported; Fader is shell-only'],
};
const errors = [], missing = [];
let context, page, activeLabel;
async function evaluate(callback, argument) {
  let timer;
  try {
    return await Promise.race([page.evaluate(callback, argument), new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Browser case deadline exceeded: ${activeLabel}`)), settings.timeoutMs);
    })]);
  } finally {clearTimeout(timer);}
}
async function assetFingerprints() {
  const values = {};
  for (const path of assetPaths) {
    const bytes = await readFile(resolve(root, vendorPath, path));
    const sha256 = createHash('sha256').update(bytes).digest('hex'), expected = manifest.runtime_assets.files[path];
    assert.equal(bytes.length, expected.bytes, `PNG byte count: ${path}`); assert.equal(sha256, expected.sha256, `PNG SHA256: ${path}`);
    values[path] = sha256;
  }
  return values;
}
async function closePage() {
  if (!context) return;
  if (page && !page.isClosed()) await evaluate(() => window.modelProbe.disposeShell());
  await context.close(); report.contexts.at(-1).closed = true; context = page = null;
}
async function openPage(label) {
  await closePage(); activeLabel = label;
  context = await browser.newContext({viewport: {width: 1000, height: 760}}); page = await context.newPage(); page.setDefaultTimeout(settings.timeoutMs);
  page.on('pageerror', error => errors.push({case: activeLabel, message: error.message}));
  page.on('response', response => {if (response.status() >= 400) missing.push({case: activeLabel, status: response.status(), url: response.url().replace(base, '')});});
  report.contexts.push({label, closed: false});
  await page.goto(`${base}/__test__`, {waitUntil: 'networkidle', timeout: settings.timeoutMs});
  await evaluate(installModelProbe, {assetPaths, timeoutMs: settings.timeoutMs});
}
async function stickShell() {
  await evaluate(async device => {
    window.modelProbe.disposeShell();
    const {createModelShell} = await import('/platform/web/model-shell.js');
    window.testShell = await createModelShell(document.querySelector('#host'), device, {live: true});
  }, catalog.devices.find(device => device.id === 'sticks3'));
}
async function screenshot(name) {
  await evaluate(() => window.modelProbe.rendered(window.testShell));
  const bytes = await page.screenshot({path: `${output}/${name}.png`});
  return {path: name + '.png', sha256: createHash('sha256').update(bytes).digest('hex')};
}
try {
  report.runtime_asset_sha256 = await assetFingerprints();
  // Diagnostic census before a new vendor regression. This inventories every
  // public LED/joint/slider contract without calling it a functional output PASS.
  if (settings.cases.includes('interfaces')) {
    for (const [index, id] of manifest.units.entries()) {
      if (index % settings.batchSize === 0) {await openPage(`interfaces-${Math.floor(index / settings.batchSize)}`); await stickShell();}
      activeLabel = `interfaces:${id}`;
      const record = await evaluate(async ({id, expectedMinimum}) => {
        const shell = window.testShell, module = await shell.attachUnit(id, {cableLength: 70});
        const artwork = await window.modelProbe.artwork(module, expectedMinimum);
        const interfaces = window.modelProbe.interfaces(module);
        shell.detachUnit();
        return {unit_id: id, options: {}, interfaces, artwork, output_validation: 'NOT RUN'};
      }, {id, expectedMinimum: expectedArtwork({id, options: {}})});
      report.interface_census.push(record);
    }
    assert.equal(report.interface_census.length, manifest.units.length);
    console.log(`MODEL_INTERFACE_CENSUS_PASS ${report.interface_census.length}; output validation NOT RUN`);
  }
  if (full || settings.cases.includes('assets')) {
    for (let i = 0; i < assetPaths.length; i += settings.assetBatchSize) {
      await openPage(`asset-batch-${i / settings.assetBatchSize}`);
      const batch = await evaluate(decodeAssetBatch, {paths: assetPaths.slice(i, i + settings.assetBatchSize), concurrency: settings.decodeConcurrency, timeoutMs: settings.timeoutMs});
      assert.ok(batch.peak_concurrency <= settings.decodeConcurrency); assert.equal(batch.final_active, 0);
      report.runtime_assets.push(...batch.rows); report.contexts.at(-1).peak_decode_concurrency = batch.peak_concurrency;
      await closePage();
    }
    assert.equal(report.runtime_assets.length, assetPaths.length); assert.equal(new Set(report.runtime_assets.map(asset => asset.path)).size, assetPaths.length);
    console.log(`MODEL_ASSETS_PASS ${report.runtime_assets.length} bounded concurrency=${settings.decodeConcurrency}`);
  }
  const controllerCases = selected.filter(test => test.kind === 'controller');
  for (const [index, test] of controllerCases.entries()) {
    if (index % settings.batchSize === 0) await openPage(`controllers-${Math.floor(index / settings.batchSize)}`);
    activeLabel = test.key;
    const device = controllerDevices.find(device => device.id === test.id);
    const result = await evaluate(async ({device, options, expectedMinimum}) => {
      window.modelProbe.disposeShell();
      const { createDeviceShell } = await import('/platform/web/device-shell-factory.js');
      const shell = await createDeviceShell(document.querySelector('#host'), device, { live: true, modelOptions: options });
      window.testShell = shell;
      shell.setViewMode('shell');
      const controls = [], touches = [], raw = [];
      let resets = 0;
      shell.on('control', event => controls.push(event));
      shell.on('touch', event => touches.push(event));
      shell.on('model-input', event => raw.push(event));
      shell.on('reset', () => resets++);
      const display = shell.display;
      let frame = null;
      if (display) {
        // StamPLC's runtime is landscape, its explicit native panel is rotated.
        const rotated = display.meta.nativeRasterRotation === 90;
        const width = rotated ? display.height : display.width, height = rotated ? display.width : display.height;
        const bytes = new Uint8Array(width * height * 2);
        bytes[0] = 0xf8; bytes[1] = 0;
        shell.setFrame(bytes, width, height, 7);
        frame = { pixel: display.getPixel(rotated ? display.width - 1 : 0, 0), sequence: shell.frameSeq };
        // Exercise PNG decoding on the same external-frame route as sessions.
        const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
        const ctx = canvas.getContext('2d'); ctx.fillStyle = '#0282cb'; ctx.fillRect(0, 0, width, height);
        const blob = await new Promise(resolve => canvas.toBlob(resolve));
        await shell.setImage(blob, 8);
        frame.pngPixel = display.getPixel(rotated ? display.width - 1 : 0, 0);
        frame.pngSequence = shell.frameSeq;
        const littleEndian = new Uint8Array(width * height * 2);
        littleEndian.set([0x00, 0xf8, 0xe0, 0x07, 0x1f, 0x00]);
        shell.setFrameLE(littleEndian, width, height, 9);
        frame.littleEndianPixels = [0, 1, 2].map(x => display.getPixel(rotated ? display.width - 1 : x, rotated ? x : 0));
        frame.littleEndianSequence = shell.frameSeq;
        if (display.touchEnabled) { display.touch('start', 12, 34, 1); display.touch('end', 12, 34, 1); }
      }
      const button = shell.model.list('button').find(component => component.meta.electricalBehavior !== false);
      if (button) { button.press('integration-probe'); button.release('integration-probe'); }
      const physicalAliases=[];
      if(device.id==='cardputer-adv')for(const id of ['key-Fn','key-CapsLock','key-AltLeft','key-AltRight','key-Escape']){
        const component=shell.model.find(id,'button'),start=controls.length;
        if(!component)throw new Error('Missing physical keyboard alias '+id);
        component.press('integration-probe');component.release('integration-probe');
        physicalAliases.push({id,events:controls.splice(start).map(event=>[event.key,event.down])});
        if(id==='key-Escape'){
          component.press('key:Escape');component.release('key:Escape');
          physicalAliases.push({id:'pc-Escape',events:controls.splice(start).map(event=>[event.key,event.down])});
          for(const sources of [['integration-probe','key:Escape'],['key:Escape','integration-probe']]){
            component.press(sources[0]);component.press(sources[1]);
            component.release(sources[0]);component.release(sources[1]);
            physicalAliases.push({id:'mixed-Escape-'+sources[0],events:controls.splice(start).map(event=>[event.key,event.down])});
          }
        }
      }
      const pcAliases=[];
      if(device.id==='cardputer-adv'){
        const canvas=shell.viewer.renderer.domElement;
        canvas.focus();
        for(const code of ['ShiftLeft','ShiftRight','AltLeft','AltRight','Backquote']){
          const start=controls.length;
          canvas.dispatchEvent(new KeyboardEvent('keydown',{code,key:code,bubbles:true,shiftKey:code.startsWith('Shift'),altKey:code.startsWith('Alt')}));
          canvas.dispatchEvent(new KeyboardEvent('keyup',{code,key:code,bubbles:true}));
          pcAliases.push({code,component:shell.model.keymap[code],events:controls.splice(start).map(event=>[event.key,event.down])});
        }
        const start=controls.length;
        for(const code of ['ShiftLeft','ShiftRight'])canvas.dispatchEvent(new KeyboardEvent('keydown',{code,bubbles:true,shiftKey:true}));
        canvas.dispatchEvent(new KeyboardEvent('keyup',{code:'ShiftLeft',bubbles:true,shiftKey:true}));
        if(controls.length!==start+1)throw new Error('Releasing one Shift alias released the still-held physical switch');
        canvas.dispatchEvent(new KeyboardEvent('keyup',{code:'ShiftRight',bubbles:true}));
        pcAliases.push({code:'two-shift-holds',events:controls.splice(start).map(event=>[event.key,event.down])});
      }
      const before = raw.length;
      const presentationRotation = {
        initial: shell.presentationRotationDeg ?? 0,
        applied: shell.setDeviceRotation(-90),
        portrait: shell.presentationRotationDeg,
        reset: shell.setDeviceRotation(0),
      };
      const ownership = window.modelProbe.ownership(shell, shell.model);
      const outputs = window.modelProbe.outputs(shell, shell.model);
      const artwork = await window.modelProbe.artwork(shell.model, expectedMinimum);
      await window.modelProbe.rendered(shell);
      return {
        id: device.id, visual_only: Boolean(device.visual_only), source: shell.root?.dataset.modelSource, ports: shell.listPorts(),
        display: display ? [display.width, display.height] : null,
        frame, controls, physicalAliases, pcAliases, touches, resets, presentationRotation,
        ownership, outputs, artwork, outputEcho: raw.length - before,
      };
    }, {device, options: test.options, expectedMinimum: expectedArtwork(test)});
    assert.equal(result.source, 'm5stack-models', `${device.id} fell back to the old renderer`);
    if (result.frame) {
      assert.deepEqual(result.frame.pixel, [255, 0, 0], `${device.id} RGB565 mapping`);
      assert.deepEqual(result.frame.pngPixel, [2, 130, 203], `${device.id} PNG mapping`);
      assert.equal(result.frame.sequence, 7); assert.equal(result.frame.pngSequence, 8);
      assert.deepEqual(result.frame.littleEndianPixels, [[255, 0, 0], [0, 255, 0], [0, 0, 255]], `${device.id} RGB565LE mapping`);
      assert.equal(result.frame.littleEndianSequence, 9);
    }
    assert.equal(result.outputEcho, 0, `${device.id} output echoed as input`);
    assert.deepEqual(result.presentationRotation,
      {initial:0,applied:true,portrait:270,reset:true}, `${device.id} presentation rotation`);
    if (device.hardware.display?.touch) {
      assert.deepEqual(result.touches.map(event => [event.x, event.y, event.down]), [[12, 34, true], [12, 34, false]]);
    }
    const firstKeys = { sticks3: 'a', cores3: 'p', stopwatch: 'a', 'cardputer-adv': 'grave_accent',
      'cardputer-zero': 'f1', papermono: 'a', core2: 'a', papercolor: 'a',
      nanoc6: 'a', stackchan: 'p', atoms3r: 'a', stamplc: 'a', stickc:'a', 'stickc-plus-se':'a' };
    if (firstKeys[device.id]) assert.deepEqual(result.controls.map(event => [event.key, event.down]), [[firstKeys[device.id], true], [firstKeys[device.id], false]], `${device.id} runtime input mapping`);
    if(device.id==='cardputer-adv')assert.deepEqual(result.physicalAliases.map(row=>row.events),
      ['compose','shift','meta_l','alt','grave_accent','esc','grave_accent','esc'].map(code=>[[code,true],[code,false]]),'ADV physical matrix aliases and mixed-source Escape holds retain matching input edges');
    if(device.id==='cardputer-adv')assert.deepEqual(result.pcAliases.map(row=>row.events),
      ['shift','shift','alt','alt','grave_accent','shift'].map(code=>[[code,true],[code,false]]),'Focused PC aliases reach the original physical switch and preserve overlapping Shift holds');
    if (device.id === 'tab5') assert.equal(result.resets, 1);
    result.case = test.key; result.configuration = test.configuration; result.options = test.options;
    report.controllers.push(result);
    const filename = test.configuration === 'default' ? test.id : test.key.replaceAll(':', '-').replaceAll('#', '-');
    result.screenshots = [await screenshot(filename)];
    await evaluate(() => window.testShell.viewer.setView('back', {duration: 0}));
    result.screenshots.push(await screenshot(filename + '-back'));
    result.disposal = await evaluate(() => window.modelProbe.disposeShell());
    console.log(`MODEL_CONTROLLER_PASS ${test.key} artwork=${result.artwork.layers}`);
  }
  const previewCases = selected.filter(test => test.kind === 'preview');
  for (const [index, test] of previewCases.entries()) {
    if (index % settings.batchSize === 0) await openPage(`previews-${Math.floor(index / settings.batchSize)}`);
    activeLabel = test.key;
    const result = await evaluate(async ({test, expectedMinimum}) => {
      window.modelProbe.disposeShell();
      const {createVisualModelShell} = await import('/platform/web/model-shell.js');
      const shell = window.testShell = await createVisualModelShell(document.querySelector('#host'), test.id, {modelOptions: test.options});
      const runtimeEvents = [], inputs = [];
      for (const type of ['control', 'touch', 'reset', 'unit-input']) shell.on(type, event => runtimeEvents.push({type, event}));
      shell.on('model-input', event => inputs.push(event));
      const button = shell.model.list('button')[0];
      if (button) {button.press('standalone-preview'); button.release('standalone-preview');}
      for (const display of shell.model.list('display')) if (display.touchEnabled) {
        display.touch('start', 1, 1, 1); display.touch('end', 1, 1, 1);
      }
      const ownership = window.modelProbe.ownership(shell, shell.model);
      const artwork = await window.modelProbe.artwork(shell.model, expectedMinimum);
      const outputs = window.modelProbe.outputs(shell, shell.model);
      shell.resetView();
      await window.modelProbe.rendered(shell);
      return {id: test.id, category: shell.root.dataset.modelCategory, visualOnly: shell.root.dataset.visualOnly,
        standalone: !shell.model.parentHost && !shell.model.attachedTo, ownership, artwork, outputs,
        inputs: inputs.map(({id, kind, action}) => ({id, kind, action})), runtimeEvents, ports: shell.listPorts()};
    }, {test, expectedMinimum: expectedArtwork(test)});
    assert.equal(result.visualOnly, 'true'); assert.equal(result.standalone, true);
    assert.deepEqual(result.runtimeEvents, [], `${test.key} acquired a runtime input route`);
    assert.equal(result.category, products.find(product => product.id === test.id).category);
    result.disposal = await evaluate(() => window.modelProbe.disposeShell());
    report.previews.push(result);
    console.log(`MODEL_PREVIEW_PASS ${test.key} artwork=${result.artwork.layers}`);
  }
  if (full || settings.cases.includes('interactions')) {
    await openPage('legacy-input-readback-interactions');
    await stickShell();
  const stick = catalog.devices.find(device => device.id === 'sticks3');
  await evaluate(async device => {
    window.modelProbe.disposeShell();
    const { createModelShell } = await import('/platform/web/model-shell.js');
    window.testShell = await createModelShell(document.querySelector('#host'), device, { live: true });
  }, stick);
  const readback = await evaluate(async () => {
    const shell = window.testShell;
    await shell.attachUnit('button');
    const events = [], listener = event => events.push(`${event.action}:${event.source}`);
    shell.on('unit-input', listener);
    const button = shell.model.button('grove/press');
    button.press('pointer-probe');
    shell.applyVisualState({type: 'button-state', target: 'grove/press', pressed: true});
    shell.model.update(1, 1);
    const downMotion = button.getActuationState();
    button.release('pointer-probe');
    // A second user gesture must still work while readback visually holds down.
    button.press('pointer-second'); button.release('pointer-second');
    const heldVisually = button.getState().pressed;
    const count = events.length;
    await new Promise(resolve => setTimeout(resolve, button.longPressMs + 50));
    const delayedEcho = events.length - count;
    shell.applyVisualState({type: 'button-state', target: 'grove/press', pressed: false});
    shell.model.update(1, 2);
    const upMotion = button.getActuationState();
    const releasedVisually = !button.getState().pressed;
    shell.off('unit-input', listener); shell.detachUnit();
    return { events, heldVisually, releasedVisually, delayedEcho, downMotion, upMotion };
  });
  assert.deepEqual(readback.events, ['down:pointer-probe', 'up:pointer-probe', 'click:pointer-probe', 'down:pointer-second', 'up:pointer-second', 'click:pointer-second']);
  assert.equal(readback.heldVisually, true); assert.equal(readback.releasedVisually, true); assert.equal(readback.delayedEcho, 0);
  assert.equal(readback.downMotion.depthMm, readback.downMotion.targetDepthMm);
  assert.ok(readback.downMotion.depthMm > 0);
  assert.equal(readback.upMotion.depthMm, 0);
  report.button_readback_release = readback;

  for (const unitId of ['button', 'env-iii', 'fan', 'encoder']) {
    await evaluate(async unitId => {
      await window.testShell.attachUnit(unitId, { cableLength: 70 });
      window.testShell.viewer.setView('iso', { duration: 0 });
      window.testShell.viewer.fit();
    }, unitId);
    await page.screenshot({ path: `${output}/unit-${unitId}.png` });
    await evaluate(() => window.testShell.detachUnit());
  }

  // Focused keyboard presses and blur must produce one matching release.
  await evaluate(async device => {
    window.modelProbe.disposeShell();
    const { createModelShell } = await import('/platform/web/model-shell.js');
    window.testShell = await createModelShell(document.querySelector('#host'), device, { live: true });
    window.inputEvents = [];
    window.testShell.on('control', event => window.inputEvents.push(event));
  }, stick);
  await page.locator('canvas').focus();
  await page.keyboard.down('a');
  await evaluate(() => document.querySelector('canvas').blur());
  await page.keyboard.up('a');
  const held = await evaluate(() => window.inputEvents.map(event => `${event.key}:${event.down}`));
  assert.deepEqual(held, ['a:true', 'a:false']);
  report.focused_keyboard = 'PASS';

  }
  const unitCases = selected.filter(test => test.kind === 'unit');
  for (const [index, test] of unitCases.entries()) {
    if (index % settings.batchSize === 0) {await openPage(`units-${Math.floor(index / settings.batchSize)}`); await stickShell();}
    activeLabel = test.key;
    const result = await evaluate(async ({test, expectedMinimum}) => {
      const shell = window.testShell;
      const module = await shell.attachUnit(test.id, {cableLength: 70, ...test.options});
      const ownership = window.modelProbe.ownership(shell, module);
      const artwork = await window.modelProbe.artwork(module, expectedMinimum);
      const events = [], onInput = event => events.push(event);
      shell.on('unit-input', onInput);
      try {
        const button = module.list('button')[0];
        if (button) {button.press('unit-probe'); button.release('unit-probe');}
        const before = events.length;
        const interfaces = window.modelProbe.interfaces(module);
        const outputs = window.modelProbe.outputs(shell, module);
        let driveActivity = null;
        if (test.id === 'fan') {
          const joint = module.list('joint')[0];
          shell.applyVisualState({type: 'drive-activity', target: joint.path, active: true});
          const before = joint.getState().angleDeg; joint.update(0.1); const moving = joint.getState();
          shell.applyVisualState({type: 'drive-activity', target: joint.path, active: false}); joint.update(0.1);
          driveActivity = {moves: moving.angleDeg !== before, stops: moving.angleDeg === joint.getState().angleDeg, rpmUnmodeled: moving.rpm === 0};
        }
        shell.viewer.setView('iso', {duration: 0}); shell.viewer.fit();
        await window.modelProbe.rendered(shell);
        window.currentModule = module;
        return {unit_id: test.id, case: test.key, configuration: test.configuration, options: test.options,
          attached: shell.model.port('grove').module === module && module.parentHost === shell.model,
          paths: module.list().map(component => component.path), components: ownership, interfaces, artwork, outputs,
          input: events.map(event => ({id: event.id, kind: event.kind, action: event.action})),
          ...(driveActivity ? {driveActivity} : {}), outputEcho: events.length - before};
      } finally {shell.off('unit-input', onInput);}
    }, {test, expectedMinimum: expectedArtwork(test)});
    result.screenshots = [await screenshot(test.key.replaceAll(':', '-').replaceAll('#', '-'))];
    Object.assign(result, await evaluate(() => {
      const shell = window.testShell, module = window.currentModule;
      const components = module.list(), finish = window.modelProbe.watchDisposal(module.root);
      shell.detachUnit();
      const disposal = finish(); window.currentModule = null;
      return {detached: shell.model.port('grove').module === null && module.parentHost === null && module.attachedTo === null,
        disposed: module.components.size === 0 && components.every(component => component.host === null),
        activityReleased: shell.driveActivities.size === 0, disposal};
    }));
    assert.equal(result.attached, true, `${test.key} attach`); assert.equal(result.detached, true, `${test.key} detach`);
    assert.equal(result.disposed, true, `${test.key} dispose`); assert.equal(result.outputEcho, 0, `${test.key} output echoed as input`);
    assert.equal(result.activityReleased, true, `${test.key} activity state disposed with its module`);
    if (test.id === 'fan') assert.deepEqual(result.driveActivity, {moves: true, stops: true, rpmUnmodeled: true});
    assert.ok(result.input.every(event => event.id.startsWith('grove/')));
    report.units.push(result);
    console.log(`MODEL_UNIT_PASS ${test.key} artwork=${result.artwork.layers} leds=${result.outputs.leds.length} joints=${result.outputs.joints.length}`);
  }
  if (full || settings.cases.includes('interactions')) {
    await openPage('legacy-attachment-and-fallback'); await stickShell();
    const stick = catalog.devices.find(device => device.id === 'sticks3');
  const race = await evaluate(async () => {
    const shell = window.testShell;
    const first = shell.attachUnit('button'), second = shell.attachUnit('fan');
    const [stale, current] = await Promise.all([first, second]);
    const result = { stale: stale === null, current: shell.model.port('grove').module === current };
    shell.detachUnit();
    return result;
  });
  assert.deepEqual(race, { stale: true, current: true });
  report.async_attachment_race = 'PASS';

  const nested = await evaluate(async () => {
    const shell = window.testShell;
    const hub = await shell.attachUnit('hub');
    const children = [];
    for (const [index, id] of ['env-iii', 'encoder', 'cardkb'].entries()) children.push(await shell.attachUnit(id, {port: `grove/grove-${index + 1}`}));
    const events = [];
    const onInput = event => events.push(event);
    shell.on('unit-input', onInput);
    const key = shell.model.find('grove/grove-3/key-q', 'button');
    key.press('nested-probe'); key.release('nested-probe');
    const paths = children.map((module, index) => shell.model.port(`grove/grove-${index + 1}`).module === module);
    shell.off('unit-input', onInput);
    shell.detachUnit('grove');
    return {paths, input: events.map(event => event.id), parentDisposed: hub.components.size === 0, childrenDisposed: children.every(module => module.components.size === 0)};
  });
  assert.deepEqual(nested.paths, [true, true, true]);
  assert.ok(nested.input.length >= 2 && nested.input.every(id => id === 'grove/grove-3/key-q'));
  assert.equal(nested.parentDisposed, true); assert.equal(nested.childrenDisposed, true);
  report.nested_hub_attachment_input_and_dispose = nested;

  // A failed WebGL context must still leave a usable legacy DOM shell.
  const fallback = await evaluate(async device => {
    window.modelProbe.disposeShell();
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      return type.startsWith('webgl') ? null : original.call(this, type, ...args);
    };
    try {
      const { createDeviceShell } = await import('/platform/web/device-shell-factory.js');
      window.testShell = await createDeviceShell(document.querySelector('#host'), device, { live: true });
      const available = Boolean(document.querySelector('.device-body'));
      const canvas = document.createElement('canvas'); canvas.width = 135; canvas.height = 240;
      const ctx = canvas.getContext('2d'); ctx.fillStyle = '#0282cb'; ctx.fillRect(0, 0, 135, 240);
      await window.testShell.setImage(await new Promise(resolve => canvas.toBlob(resolve)), 19);
      const pixel = Array.from(window.testShell.canvas.getContext('2d').getImageData(0, 0, 1, 1).data).slice(0, 3);
      window.testShell.dispose();
      return { available, pixel, sequence: window.testShell.frameSeq, disposed: document.querySelector('#host').children.length === 0 };
    } finally { HTMLCanvasElement.prototype.getContext = original; }
  }, stick);
  assert.deepEqual(fallback, { available: true, pixel: [2, 130, 203], sequence: 19, disposed: true });
  report.webgl_fallback = 'PASS';
  }
  await closePage();
  assert.deepEqual(errors, []); assert.deepEqual(missing, []);
  assert.deepEqual(await fingerprints(), report.integration_sha256, 'Integration source changed during browser run');
  assert.deepEqual(await assetFingerprints(), report.runtime_asset_sha256, 'PNG source changed during browser run');
  if (full) {assert.equal(report.controllers.length, manifest.controllers.length); assert.equal(report.units.length, manifest.units.length);
    assert.equal(report.previews.length, manifest.controllers.length + manifest.units.length);}
  for (const entry of report.catalog_configurations) for (const config of entry.configurations) {
    if (config.status === 'SELECTED') config.status = 'PASS';
  }
  report.status = 'PASS';
} catch (error) {
  report.error = error.stack || String(error); report.failed_case = activeLabel;
} finally {
  try {await closePage();} catch (error) {report.status = 'FAIL'; report.cleanup_error = String(error);}
  await browser.close(); await new Promise(resolve => server.close(resolve));
}
report.page_errors = errors; report.missing_imports = missing;
await writeFile(`${output}/report.json`, JSON.stringify(report, null, 2) + '\n');
console.log(`${report.status} browser shells=${report.controllers.length} units=${report.units.length} previews=${report.previews.length} assets=${report.runtime_assets.length}; ${output}/report.json`);
if (report.status !== 'PASS') {console.error(report.error || report.cleanup_error); process.exitCode = 1;}
