// Browser integration/geometry evidence only. No QEMU, firmware or hardware PASS.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve, extname } from 'node:path';
import { chromium } from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = process.env.M5_MODEL_TEST_OUT || '/tmp/m5-model-shell-test';
await mkdir(output, { recursive: true });
const catalog = JSON.parse(await readFile(resolve(root, 'devices/catalog.source.json'), 'utf8'));
const manifest = JSON.parse(await readFile(resolve(root, 'platform/web/vendor/m5stack-models/vendor-manifest.json'), 'utf8'));
assert.deepEqual(manifest.controllers.slice().sort(), catalog.devices.map(device => device.id).sort());
const harness = `<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;background:#fff}#host{width:900px;height:700px}.three-device-root,.three-device-stage{min-height:700px!important}.three-device-hint{color:#ccc}</style>
<link rel="stylesheet" href="/platform/web/three-device-viewer.css">
<script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script>
</head><body><div id="host"></div></body></html>`;
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.png': 'image/png' };
const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/__test__') { response.setHeader('Content-Type', 'text/html'); response.end(harness); return; }
    const path = resolve(root, '.' + decodeURIComponent(pathname));
    if (!path.startsWith(root + '/')) { response.writeHead(403); response.end(); return; }
    const data = await readFile(path);
    response.setHeader('Content-Type', mime[extname(path)] || 'application/octet-stream');
    response.end(data);
  } catch { response.writeHead(404); response.end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({ viewport: { width: 1000, height: 760 } });
const errors = [], missing = [];
page.on('pageerror', error => errors.push(error.message));
page.on('response', response => { if (response.status() >= 400 && !response.url().endsWith('/favicon.ico')) missing.push(response.url()); });
const integrationFiles = ['platform/web/model-shell.js', 'platform/web/device-shell-factory.js',
  'platform/web/unit-annotations.js', 'platform/web/unit-assembly-layout.js',
  'platform/web/sessions.js', 'platform/web/sessions.html', 'platform/tools/sync_visual_models.py',
  'platform/tests/test_model_shell.mjs'];
const integrationSha256 = Object.fromEntries(await Promise.all(integrationFiles.map(async name =>
  [name, createHash('sha256').update(await readFile(resolve(root, name))).digest('hex')])));
const report = { category: 'browser-visual-integration', captured_at: new Date().toISOString(),
  browser_version: browser.version(), source_commit: manifest.source_commit,
  integration_sha256: integrationSha256, controllers: [], units: [] };

try {
  await page.goto(`${base}/__test__`, { waitUntil: 'networkidle' });
  // Decode every reviewed PNG, including optional education variants. Module
  // loading alone would miss broken new URL() paths or absent raster assets.
  report.runtime_assets = await page.evaluate(async paths => Promise.all(paths.map(async path => {
    const image = new Image();
    image.src = `/platform/web/vendor/m5stack-models/${path}`;
    await image.decode();
    return {path, width: image.naturalWidth, height: image.naturalHeight};
  })), Object.keys(manifest.runtime_assets.files));
  assert.ok(report.runtime_assets.every(asset => asset.width > 0 && asset.height > 0));
  assert.equal(report.runtime_assets.length, Object.keys(manifest.runtime_assets.files).length);
  for (const device of catalog.devices) {
    const result = await page.evaluate(async device => {
      window.testShell?.dispose();
      const { createDeviceShell } = await import('/platform/web/device-shell-factory.js');
      const shell = await createDeviceShell(document.querySelector('#host'), device, { live: true });
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
        if (display.touchEnabled) { display.touch('start', 12, 34, 1); display.touch('end', 12, 34, 1); }
      }
      const button = shell.model.list('button').find(component => component.meta.electricalBehavior !== false);
      if (button) { button.press('integration-probe'); button.release('integration-probe'); }
      const before = raw.length;
      const led = shell.model.list('led')[0];
      if (led) shell.applyVisualState({ type: 'led', target: led.path, color: '#ff0000', brightness: 0.25 });
      shell.viewer.renderer.render(shell.viewer.scene, shell.viewer.camera);
      return {
        id: device.id, source: shell.root?.dataset.modelSource, ports: shell.listPorts(),
        display: display ? [display.width, display.height] : null,
        frame, controls, touches, resets, outputEcho: raw.length - before,
      };
    }, device);
    assert.equal(result.source, 'm5stack-models', `${device.id} fell back to the old renderer`);
    if (result.frame) {
      assert.deepEqual(result.frame.pixel, [255, 0, 0], `${device.id} RGB565 mapping`);
      assert.deepEqual(result.frame.pngPixel, [2, 130, 203], `${device.id} PNG mapping`);
      assert.equal(result.frame.sequence, 7); assert.equal(result.frame.pngSequence, 8);
    }
    assert.equal(result.outputEcho, 0, `${device.id} output echoed as input`);
    if (device.hardware.display?.touch) {
      assert.deepEqual(result.touches.map(event => [event.x, event.y, event.down]), [[12, 34, true], [12, 34, false]]);
    }
    const firstKeys = { sticks3: 'a', cores3: 'p', stopwatch: 'a', 'cardputer-adv': 'esc',
      'cardputer-zero': 'f1', papermono: 'a', core2: 'a', papercolor: 'a',
      nanoc6: 'a', stackchan: 'p', atoms3r: 'a', stamplc: 'a' };
    if (firstKeys[device.id]) assert.deepEqual(result.controls.map(event => [event.key, event.down]), [[firstKeys[device.id], true], [firstKeys[device.id], false]], `${device.id} runtime input mapping`);
    if (device.id === 'tab5') assert.equal(result.resets, 1);
    await page.waitForFunction(() => {
      const statuses = [];
      window.testShell.model.root.traverse(object => {
        if (object.userData.artworkKind?.startsWith('official-raster')) statuses.push(object.userData.textureStatus);
      });
      return statuses.every(status => status !== 'pending');
    });
    result.artwork = await page.evaluate(() => {
      const statuses = [];
      window.testShell.model.root.traverse(object => {
        if (object.userData.artworkKind?.startsWith('official-raster')) statuses.push(object.userData.textureStatus);
      });
      return {layers: statuses.length, ready: statuses.filter(status => status === 'ready').length};
    });
    assert.equal(result.artwork.ready, result.artwork.layers, `${device.id} model material raster loading`);
    report.controllers.push(result);
    await page.screenshot({ path: `${output}/${device.id}.png` });
    await page.evaluate(() => window.testShell.viewer.setView('back', { duration: 0 }));
    await page.screenshot({ path: `${output}/${device.id}-back.png` });
  }

  const stick = catalog.devices.find(device => device.id === 'sticks3');
  await page.evaluate(async device => {
    window.testShell.dispose();
    const { createModelShell } = await import('/platform/web/model-shell.js');
    window.testShell = await createModelShell(document.querySelector('#host'), device, { live: true });
  }, stick);
  const readback = await page.evaluate(async () => {
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
    await page.evaluate(async unitId => {
      await window.testShell.attachUnit(unitId, { cableLength: 70 });
      window.testShell.viewer.setView('iso', { duration: 0 });
      window.testShell.viewer.fit();
    }, unitId);
    await page.screenshot({ path: `${output}/unit-${unitId}.png` });
    await page.evaluate(() => window.testShell.detachUnit());
  }

  // Focused keyboard presses and blur must produce one matching release.
  await page.evaluate(async device => {
    window.testShell.dispose();
    const { createModelShell } = await import('/platform/web/model-shell.js');
    window.testShell = await createModelShell(document.querySelector('#host'), device, { live: true });
    window.inputEvents = [];
    window.testShell.on('control', event => window.inputEvents.push(event));
  }, stick);
  await page.locator('canvas').focus();
  await page.keyboard.down('a');
  await page.evaluate(() => document.querySelector('canvas').blur());
  await page.keyboard.up('a');
  const held = await page.evaluate(() => window.inputEvents.map(event => `${event.key}:${event.down}`));
  assert.deepEqual(held, ['a:true', 'a:false']);
  report.focused_keyboard = 'PASS';

  for (const unitId of manifest.units) {
    const result = await page.evaluate(async unitId => {
      const shell = window.testShell;
      const module = await shell.attachUnit(unitId, { cableLength: 70 });
      const events = [];
      const onInput = event => events.push(event);
      shell.on('unit-input', onInput);
      const button = module.list('button')[0];
      if (button) { button.press('unit-probe'); button.release('unit-probe'); }
      const before = events.length;
      const led = module.list('led')[0];
      if (led) shell.applyVisualState({ type: 'led', target: led.path, color: '#00ff00', brightness: 0.5 });
      const joint = module.list('joint')[0];
      if (joint) shell.applyVisualState({ type: 'joint', target: joint.path, angleDeg: 15 });
      let driveActivity = null;
      if (unitId === 'fan') {
        shell.applyVisualState({type: 'drive-activity', target: joint.path, active: true});
        const before = joint.getState().angleDeg;
        joint.update(0.1);
        const moving = joint.getState();
        shell.applyVisualState({type: 'drive-activity', target: joint.path, active: false});
        joint.update(0.1);
        driveActivity = {moves: moving.angleDeg !== before, stops: moving.angleDeg === joint.getState().angleDeg, rpmUnmodeled: moving.rpm === 0};
      }
      shell.viewer.renderer.render(shell.viewer.scene, shell.viewer.camera);
      const result = { unit_id: unitId, attached: shell.model.port('grove').module === module,
        paths: module.list().map(component => component.path), input: events.map(event => ({ id: event.id, kind: event.kind, action: event.action })),
        components: module.list().map(component => ({path: component.path, kind: component.kind, meta: component.meta})),
        ...(driveActivity ? {driveActivity} : {}),
        outputEcho: events.length - before };
      shell.off('unit-input', onInput);
      shell.detachUnit();
      result.detached = shell.model.port('grove').module === null;
      result.disposed = module.components.size === 0;
      result.activityReleased = shell.driveActivities.size === 0;
      return result;
    }, unitId);
    assert.equal(result.attached, true, `${unitId} attach`);
    assert.equal(result.detached, true, `${unitId} detach`);
    assert.equal(result.disposed, true, `${unitId} dispose`);
    assert.equal(result.outputEcho, 0, `${unitId} output echoed as input`);
    assert.equal(result.activityReleased, true, `${unitId} activity state disposed with its module`);
    if (unitId === 'fan') assert.deepEqual(result.driveActivity, {moves: true, stops: true, rpmUnmodeled: true});
    assert.ok(result.input.every(event => event.id.startsWith('grove/')));
    report.units.push(result);
  }

  const race = await page.evaluate(async () => {
    const shell = window.testShell;
    const first = shell.attachUnit('button'), second = shell.attachUnit('fan');
    const [stale, current] = await Promise.all([first, second]);
    const result = { stale: stale === null, current: shell.model.port('grove').module === current };
    shell.detachUnit();
    return result;
  });
  assert.deepEqual(race, { stale: true, current: true });
  report.async_attachment_race = 'PASS';

  const nested = await page.evaluate(async () => {
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
  const fallback = await page.evaluate(async device => {
    window.testShell.dispose();
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
  assert.deepEqual(errors, []);
  assert.deepEqual(missing, []);
  report.page_errors = errors; report.missing_imports = missing;
  await writeFile(`${output}/report.json`, JSON.stringify(report, null, 2) + '\n');
  console.log(`PASS browser shells=${report.controllers.length} units=${report.units.length}; focus/frame/input/output/lifecycle/fallback verified; ${output}/report.json`);
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
