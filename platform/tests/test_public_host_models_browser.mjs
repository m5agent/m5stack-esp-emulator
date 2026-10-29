// Real public-page model/input integration only; no guest or hardware PASS.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {chromium} from 'playwright';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const site = resolve(process.env.M5_PUBLIC_SITE || resolve(repo, '.work/expanded-host-models-site-v1'));
const out = resolve(process.env.M5_PUBLIC_HOST_OUT || resolve(repo, '.work/public-host-models-browser'));
const manifestPath = 'platform/web/vendor/m5stack-models/vendor-manifest.json';
const catalogPath = 'platform/web/vendor/m5stack-models/catalog/products.json';
const manifest = JSON.parse(await readFile(resolve(site, manifestPath), 'utf8'));
const products = JSON.parse(await readFile(resolve(site, catalogPath), 'utf8')).products;
const runtimeDevices = JSON.parse(await readFile(resolve(site, 'devices/catalog.json'), 'utf8')).devices;
const config = JSON.parse(await readFile(resolve(site, 'platform/web/site-config.json'), 'utf8'));
const browserProfiles = JSON.parse(await readFile(resolve(site, 'platform/web/browser-profiles.json'), 'utf8')).devices;
const requested = [];
for (let i = 2; i < process.argv.length; i += 2) {
  const option = process.argv[i], value = process.argv[i + 1];
  assert.ok(value, `Missing value for ${option}`);
  if (option === '--source-commit') assert.equal(manifest.source_commit, value, 'Exported public model Git identity');
  else if (option === '--case') requested.push(value);
  else throw new Error(`Unknown option ${option}`);
}
const visualOnly = manifest.visual_only_controllers.filter(id => !requested.length || requested.includes(id));
assert.ok(visualOnly.length > 0, 'No visual-only host cases');
for (const id of requested) assert.ok(visualOnly.includes(id), `Not a visual-only controller: ${id}`);
const sources = ['platform/web/public.js', 'platform/web/model-shell.js', 'platform/web/device-shell-factory.js',
  'platform/tests/test_public_host_models_browser.mjs'];
const fingerprints = async (root, names) => Object.fromEntries(await Promise.all(names.map(async name =>
  [name, createHash('sha256').update(await readFile(resolve(root, name))).digest('hex')])));
const sourceHashes = await fingerprints(repo, sources);
const exportedHashes = await fingerprints(site, sources.slice(0, 3));
assert.deepEqual(exportedHashes, Object.fromEntries(sources.slice(0, 3).map(name => [name, sourceHashes[name]])), 'Export uses current integration code');
await mkdir(out, {recursive: true});
const mime = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.json': 'application/json',
  '.css': 'text/css', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.wasm': 'application/wasm'};
const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost');
  if (url.pathname === '/favicon.ico') {response.writeHead(204).end(); return;}
  if (!url.pathname.startsWith('/showcase/')) {response.writeHead(404).end(); return;}
  const file = resolve(site, decodeURIComponent(url.pathname.slice('/showcase/'.length)) || 'index.html');
  if (!file.startsWith(site + '/')) {response.writeHead(403).end(); return;}
  try {
    let bytes = await readFile(file);
    response.setHeader('Content-Type', mime[extname(file)] || 'application/octet-stream');
    // Observe the actual page-owned shell. Never replace its model or inputs.
    if (file === resolve(site, 'platform/web/public.js'))
      bytes = Buffer.concat([bytes, Buffer.from('\nwindow.__publicHostProbe = state;\n')]);
    response.end(bytes);
  } catch {response.writeHead(404).end();}
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const errors = [], requests = [], blocked = [], failures = [];
let context, page;
const report = {status: 'FAIL', category: 'public-host-model-browser-integration', source_commit: manifest.source_commit,
  source_sha256: sourceHashes, exported_source_sha256: exportedHashes, browser: browser.version(), visual_only: [], runtime_entries: [],
  guest_execution: 'NOT RUN', hardware_execution: 'NOT RUN', scope: 'Public model discovery, graphics and input intent; no firmware admission', errors, blocked};

async function open() {
  await context?.close();
  context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  // Fail before any request can touch the user's two services.
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (['8787', '8830'].includes(url.port)) {blocked.push(url.origin + url.pathname); return route.abort('blockedbyclient');}
    return route.continue();
  });
  page = await context.newPage();
  page.setDefaultTimeout(30000);
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  page.on('response', response => {if (response.status() >= 400) failures.push({status: response.status(), path: new URL(response.url()).pathname});});
  await page.goto(`${base}/showcase/?device=cores3&autostart=0`);
  await page.waitForFunction(() => window.__publicHostProbe?.shell?.model && window.__publicHostProbe.selected.id === 'cores3');
  await page.locator('.advanced-options > summary').click();
}
async function choose(id) {
  await page.locator('#search').fill('');
  await page.locator(`[data-device-id="${id}"]`).click();
  await page.waitForFunction(id => window.__publicHostProbe?.selected.id === id && window.__publicHostProbe.shell?.model
    && document.querySelector('#deviceMount').dataset.deviceId === id, id);
}
async function buttonInteraction() {
  const binding = await page.evaluate(async () => {
    const shell = window.__publicHostProbe.shell;
    window.__hostInputEvents = {model: [], runtime: []};
    shell.on('model-input', event => window.__hostInputEvents.model.push({id: event.id, kind: event.kind, action: event.action, source: event.source}));
    for (const type of ['control', 'touch', 'reset', 'unit-input'])
      shell.on(type, event => window.__hostInputEvents.runtime.push({type, id: event.id}));
    const keyboard = Object.entries(shell.model.keymap).find(([, path]) => shell.model.find(path, 'button'));
    const button = keyboard ? shell.model.button(keyboard[1]) : shell.model.list('button')[0];
    if (!button) return null;
    if (keyboard) return {kind: 'keyboard', code: keyboard[0], path: button.path};
    // Side-reset variants intentionally have no keyboard shortcut. Orient the
    // camera only, then raycast the actual cap and use real pointer events.
    const THREE = await import(new URL('platform/web/vendor/three/three.module.js', document.baseURI));
    shell.viewer.setView(button.meta.surfaceFace || 'front', {duration: 0});
    shell.viewer.fit({duration: 0});
    await new Promise(resolve => {const off = shell.viewer.on('render', () => {off(); resolve();}); shell.viewer.requestRender();});
    const box = shell.viewer.renderer.domElement.getBoundingClientRect();
    const point = button.meta.surfaceCenter ? shell.model.root.localToWorld(new THREE.Vector3(...button.meta.surfaceCenter))
      : button.object3d.getWorldPosition(new THREE.Vector3());
    point.project(shell.viewer.camera);
    const x = box.left + (point.x + 1) * box.width / 2, y = box.top + (1 - point.y) * box.height / 2;
    for (const dy of [0, -2, 2, -4, 4, -8, 8]) for (const dx of [0, -2, 2, -4, 4, -8, 8]) {
      const hit = shell.viewer.pick({clientX: x + dx, clientY: y + dy});
      if (hit?.component === button) return {kind: 'pointer', path: button.path, x: x + dx, y: y + dy};
    }
    throw new Error(`Actual button surface is not pickable: ${shell.device.id}/${button.path}`);
  });
  if (!binding) return {kind: 'none', reason: 'No modeled button'};
  if (binding.kind === 'keyboard') {await page.locator('#deviceMount canvas').focus(); await page.keyboard.down(binding.code);}
  else {await page.mouse.move(binding.x, binding.y); await page.mouse.down();}
  await page.waitForFunction(path => {
    const button = window.__publicHostProbe.shell.model.button(path);
    return button.getState().pressed && button.getActuationState().depthMm > 0;
  }, binding.path);
  const down = await page.evaluate(path => {
    const button = window.__publicHostProbe.shell.model.button(path);
    return {state: button.getState(), motion: button.getActuationState()};
  }, binding.path);
  if (binding.kind === 'keyboard') await page.keyboard.up(binding.code); else await page.mouse.up();
  await page.waitForFunction(path => {
    const button = window.__publicHostProbe.shell.model.button(path);
    return !button.getState().pressed && button.getActuationState().settled;
  }, binding.path);
  const result = await page.evaluate(() => window.__hostInputEvents);
  assert.deepEqual(result.runtime, [], 'Visual-only input cannot reach a runtime route');
  assert.deepEqual(result.model.filter(event => event.id === binding.path && ['down', 'up'].includes(event.action)).map(event => event.action), ['down', 'up']);
  return {...binding, down, ...result};
}
async function rotaryInteraction() {
  const binding = await page.evaluate(async () => {
    const shell = window.__publicHostProbe.shell;
    const rotary = shell.model.list('joint').find(component => component.interactive && component.meta.role === 'visual-rotary-input');
    if (!rotary) return null;
    const THREE = await import(new URL('platform/web/vendor/three/three.module.js', document.baseURI));
    const normal = rotary.axis.clone().applyQuaternion(rotary.restQuaternion).toArray();
    const axis = normal.map(Math.abs).indexOf(Math.max(...normal.map(Math.abs)));
    const view = [['right', 'left'], ['top', 'bottom'], ['front', 'back']][axis][normal[axis] < 0 ? 1 : 0];
    shell.viewer.setView(view, {duration: 0});
    shell.viewer.fit({duration: 0});
    await new Promise(resolve => {const off = shell.viewer.on('render', () => {off(); resolve();}); shell.viewer.requestRender();});
    const box = new THREE.Box3().setFromObject(rotary.object3d), rectangle = shell.viewer.renderer.domElement.getBoundingClientRect();
    const pixel = point => {
      point.project(shell.viewer.camera);
      return {x: rectangle.left + (point.x + 1) * rectangle.width / 2, y: rectangle.top + (1 - point.y) * rectangle.height / 2};
    };
    const center = pixel(box.getCenter(new THREE.Vector3())), edge = pixel(new THREE.Vector3(box.max.x, box.max.y, box.max.z));
    const rx = Math.abs(edge.x - center.x), ry = Math.abs(edge.y - center.y);
    for (const radius of [0.99, 0.975, 0.95, 0.925, 0.9, 0.8, 0.7, 0.6]) for (let i = 0; i < 32; i++) {
      const angle = i * Math.PI / 16, x = center.x + Math.cos(angle) * rx * radius, y = center.y + Math.sin(angle) * ry * radius;
      if (shell.viewer.pick({clientX: x, clientY: y})?.component !== rotary) continue;
      const turn = angle + Math.PI / 6;
      return {path: rotary.path, view, from: {x, y}, to: {x: center.x + Math.cos(turn) * rx * radius,
        y: center.y + Math.sin(turn) * ry * radius}, before: rotary.getState(), quaternion: rotary.object3d.quaternion.toArray()};
    }
    throw new Error(`Actual rotary ring is not pickable: ${shell.device.id}/${rotary.path}`);
  });
  if (!binding) return null;
  await page.mouse.move(binding.from.x, binding.from.y);
  await page.mouse.down();
  await page.mouse.move(binding.to.x, binding.to.y, {steps: 8});
  await page.mouse.up();
  const result = await page.evaluate(path => {
    const rotary = window.__publicHostProbe.shell.model.find(path, 'joint');
    return {state: rotary.getState(), quaternion: rotary.object3d.quaternion.toArray(), events: window.__hostInputEvents};
  }, binding.path);
  assert.ok(Math.abs(result.state.angleDeg - binding.before.angleDeg) > 1, 'Actual pointer drag changes modeled rotary angle');
  assert.notDeepEqual(result.quaternion, binding.quaternion, 'Rotary geometry changes orientation');
  assert.ok(result.events.model.some(event => event.id === binding.path && event.action === 'rotate' && event.source === 'pointer'));
  assert.deepEqual(result.events.runtime, [], 'Rotary input intent cannot reach a runtime route');
  return {...binding, ...result};
}

try {
  for (const [index, id] of visualOnly.entries()) {
    // Bound WebGL resource accumulation while retaining actual navigation
    // between several hosts inside each page.
    if (index % 4 === 0) await open();
    const product = products.find(row => row.id === id);
    assert.ok(product?.name && product.sku, `Host metadata: ${id}`);
    for (const query of [product.name, product.sku]) {
      await page.locator('#search').fill(query);
      assert.equal(await page.locator(`[data-device-id="${id}"]`).count(), 1, `${id} discoverable by ${query}`);
    }
    await choose(id);
    assert.equal(await page.locator('#stageTitle').textContent(), product.name);
    assert.match(await page.locator(`[data-device-id="${id}"] small`).textContent(), /仅模型/);
    assert.equal(await page.locator('#deviceMount [data-visual-only="true"]').count(), 1);
    assert.equal(await page.locator('#deviceMount [data-model-source="m5stack-models"]').count(), 1);
    assert.equal(await page.locator('#startBtn').isDisabled(), true);
    assert.equal(await page.locator('#capabilityTitle').textContent(), '仅浏览模型');
    assert.match(await page.locator('#capabilityText').textContent(), /本型号尚未接入固件运行/);
    assert.equal(await page.locator('#openServiceBtn').isVisible(), false);
    await page.waitForFunction(() => {
      const rows = [];
      window.__publicHostProbe.shell.model.root.traverse(object => {if (object.userData.role === 'printed-artwork') rows.push(object);});
      return rows.every(object => object.userData.textureStatus === 'ready');
    });
    const artwork = await page.evaluate(() => {
      const rows = [];
      window.__publicHostProbe.shell.model.root.traverse(object => {
        if (object.userData.role !== 'printed-artwork') return;
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        rows.push({name: object.name, status: object.userData.textureStatus,
          maps: materials.map(material => ({url: material.map?.image?.currentSrc || material.map?.image?.src,
            width: material.map?.image?.naturalWidth || material.map?.image?.width || 0,
            height: material.map?.image?.naturalHeight || material.map?.image?.height || 0}))});
      });
      return rows;
    });
    const prefix = product.entry.slice(0, product.entry.lastIndexOf('/') + 1);
    const expectedArtwork = Object.keys(manifest.runtime_assets.files).filter(path => path.startsWith(prefix));
    if (expectedArtwork.length) assert.ok(artwork.length > 0, `${id} printed artwork is not absent`);
    for (const layer of artwork) for (const map of layer.maps) {
      assert.ok(map.width > 0 && map.height > 0, `${id} decoded artwork size`);
      const assetPath = decodeURIComponent(new URL(map.url).pathname).split('/platform/web/vendor/m5stack-models/')[1];
      assert.ok(manifest.runtime_assets.files[assetPath], `${id} artwork belongs to the reviewed PNG allowlist`);
    }
    const input = await buttonInteraction();
    const rotary = await rotaryInteraction();
    for (const mode of ['browser', 'service']) {
      await page.locator('#runtimeMode').selectOption(mode);
      assert.equal(await page.locator('#startBtn').isDisabled(), true);
      assert.match(await page.locator('#capabilityText').textContent(), /本型号尚未接入固件运行/);
    }
    await page.locator('#runtimeMode').selectOption('auto');
    const screenshot = `${id}.png`;
    const bytes = await page.screenshot({path: resolve(out, screenshot)});
    report.visual_only.push({id, name: product.name, sku: product.sku, artwork, input, rotary,
      screenshot: {path: screenshot, sha256: createHash('sha256').update(bytes).digest('hex')}});
    console.log(`PUBLIC_HOST_MODEL_PASS ${id} artwork=${artwork.length} input=${input.kind}`);
  }
  await open();
  for (const device of runtimeDevices) {
    await choose(device.id);
    assert.equal(await page.locator('#deviceMount [data-visual-only="true"]').count(), 0, `${device.id} retains runtime identity`);
    assert.doesNotMatch(await page.locator('#capabilityText').textContent(), /本型号尚未接入固件运行/);
    const browser = config.browser_runtime_engine === 'qemu-wasm'
      ? browserProfiles.some(profile => profile.id === device.id) : device.id === 'stopwatch';
    if (browser) assert.equal(await page.locator('#startBtn').isEnabled(), true, `${device.id} browser run entry remains enabled`);
    report.runtime_entries.push({id: device.id, browser_entry: browser, started: false});
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(failures, []);
  assert.deepEqual(blocked, []);
  assert.equal(requests.some(url => /\/api\/v1\//.test(new URL(url).pathname)), false, 'Browsing hosts must not contact a Device Service');
  report.status = 'PASS';
  report.api_requests = 0;
  console.log(`PUBLIC_HOST_MODELS_BROWSER_OK ${report.visual_only.length} visual hosts; ${report.runtime_entries.length} runtime entries; no guest executed`);
} catch (error) {
  report.error = error.stack;
  await page?.screenshot({path: resolve(out, 'failure.png')}).catch(() => {});
  throw error;
} finally {
  await writeFile(resolve(out, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  await browser.close();
  await new Promise(done => server.close(done));
}
