// Browser geometry/input contract only. No service, guest or hardware execution.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, extname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = resolve(process.env.M5_CAMERA_FIT_OUT || '/tmp/m5-model-camera-fit');
const baselineOnly = process.env.M5_CAMERA_FIT_BASELINE === '1';
const profiles = JSON.parse(await readFile(resolve(root, 'devices/catalog.source.json'), 'utf8')).devices;
const owned = ['platform/web/model-shell.js', 'platform/tests/test_model_camera_fit.mjs'];
await mkdir(output, {recursive: true});
const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
${['app', 'sessions', 'three-device-viewer', 'm5-tokens', 'm5-brand'].map(name => `<link rel="stylesheet" href="/platform/web/${name}.css">`).join('')}
<script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script>
</head><body><main class="sessions-layout"><aside class="panel sessions-side">Camera fixture</aside><section class="sessions-main"><div class="session-list"><article class="panel session-card"><div id="host" class="session-visual is-three"></div><div class="session-body">Geometry and input evidence only</div></article></div></section></main></body></html>`;
const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/fixture') {response.setHeader('Content-Type', 'text/html'); response.end(html); return;}
    if (pathname === '/favicon.ico') {response.writeHead(204).end(); return;}
    const path = resolve(root, '.' + decodeURIComponent(pathname));
    if (!path.startsWith(root + '/')) {response.writeHead(403).end(); return;}
    response.setHeader('Content-Type', {'.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png'}[extname(path)] || 'application/octet-stream');
    response.end(await readFile(path));
  } catch {response.writeHead(404).end();}
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
const page = await browser.newPage({viewport: {width: 1440, height: 900}});
const errors = [], missing = [];
page.on('pageerror', error => errors.push(error.message));
page.on('response', response => {if (response.status() >= 400) missing.push({status: response.status(), path: new URL(response.url()).pathname});});
const report = {category: 'browser-model-camera-fit', status: 'FAIL', guest_execution: 'NOT RUN', hardware_execution: 'NOT RUN',
  browser_version: browser.version(), captured_at: new Date().toISOString(), negative_controls: [], breakpoints: [], checks: [], errors, missing};
async function settle() {
  await page.evaluate(async () => {for (let i = 0; i < 4; i++) await new Promise(requestAnimationFrame);});
}
async function viewport(width) {await page.setViewportSize({width, height: 900}); await settle();}
async function setup(deviceId, unitId, native = false) {
  await page.evaluate(async ({profile, unitId, native}) => {
    window.shell?.dispose();
    const THREE = await import('three');
    const {createModelShell} = await import('/platform/web/model-shell.js');
    const {DeviceViewer} = await import('/platform/web/vendor/m5stack-models/src/core/DeviceViewer.js');
    const shell = window.shell = await createModelShell(document.querySelector('#host'), profile, {live: true});
    if (native) {
      shell.viewer.fit = DeviceViewer.prototype.fit.bind(shell.viewer);
      shell.viewer.resize = DeviceViewer.prototype.resize.bind(shell.viewer);
    }
    window.events = [];
    shell.on('model-input', event => window.events.push({id: event.id, action: event.action, source: event.source}));
    if (unitId) await shell.attachUnit(unitId, {cableLength: 70});
    window.events = [];
    window.snapshot = () => {
      const viewer = shell.viewer, box = new THREE.Box3().setFromObject(shell.model.root), projected = [];
      viewer.camera.updateMatrixWorld(true);
      for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) projected.push(new THREE.Vector3(x, y, z).project(viewer.camera));
      return {width: innerWidth, stage: [shell.stage.clientWidth, shell.stage.clientHeight], canvas: [viewer.renderer.domElement.width, viewer.renderer.domElement.height],
        bounds: {min: box.min.toArray(), max: box.max.toArray()}, ndc: {min: ['x','y','z'].map(axis => Math.min(...projected.map(p => p[axis]))), max: ['x','y','z'].map(axis => Math.max(...projected.map(p => p[axis])))},
        distance: viewer.distance, target: viewer.target.toArray(), quaternion: shell.model.root.quaternion.toArray(), events: window.events.slice()};
    };
  }, {profile: profiles.find(profile => profile.id === deviceId), unitId, native});
  await settle();
}
async function snapshot() {return page.evaluate(() => window.snapshot());}
function visible(frame, label) {
  for (const axis of [0, 1]) {
    assert.ok(frame.ndc.min[axis] >= -0.96 && frame.ndc.max[axis] <= 0.96, `${label} clips axis ${axis}: ${JSON.stringify(frame.ndc)}`);
  }
  assert.ok(frame.ndc.min[2] >= -1 && frame.ndc.max[2] <= 1, `${label} clips camera depth`);
}
function close(actual, expected, label, epsilon = 1e-6) {assert.ok(Math.abs(actual - expected) < epsilon, `${label}: ${actual} != ${expected}`);}
try {
  await page.goto(`http://127.0.0.1:${server.address().port}/fixture`);
  for (const unit of ['pir', 'relay']) {
    await viewport(1440); await setup('cores3', unit, true);
    const before = await snapshot();
    await viewport(390); const after = await snapshot();
    const cropped = after.ndc.min[0] < -1 || after.ndc.max[0] > 1;
    assert.ok(cropped, `${unit}: old resize must reproduce horizontal clipping`);
    await page.locator('#host').screenshot({path: resolve(output, `negative-${unit}-390.png`)});
    report.negative_controls.push({unit, before, after, clipping_reproduced: cropped});
  }
  if (!baselineOnly) {
    for (const unit of ['pir', 'relay']) {
      await viewport(1440); await setup('cores3', unit);
      for (const width of [1440, 1024, 768, 390, 1440]) {
        await viewport(width); const frame = await snapshot(); visible(frame, `${unit}/${width}`);
        assert.deepEqual(frame.events, [], 'fit/resize must not create runtime input');
        assert.equal(frame.canvas[0], frame.stage[0]); assert.equal(frame.canvas[1], frame.stage[1]);
        const filename = `${unit}-${width}${report.breakpoints.some(row => row.unit === unit && row.width === width) ? '-return' : ''}.png`;
        await page.locator('#host').screenshot({path: resolve(output, filename)});
        report.breakpoints.push({unit, width, filename, ...frame});
      }
    }
    await setup('cores3', 'hub');
    for (const [index, unit] of ['env-iii', 'tof', 'button'].entries()) {
      await page.evaluate(({index, unit}) => window.shell.attachUnit(unit, {port: `grove/grove-${index + 1}`}), {index, unit});
      await settle(); visible(await snapshot(), `hub-attach-${unit}`);
    }
    for (const width of [1440, 1024, 768, 390]) {
      await viewport(width); const frame = await snapshot(); visible(frame, `hub/${width}`);
      const filename = `hub-${width}.png`; await page.locator('#host').screenshot({path: resolve(output, filename)});
      report.breakpoints.push({unit: 'hub+env-iii+tof+button', width, filename, ...frame});
    }
    await page.evaluate(() => window.shell.detachUnit('grove/grove-2'));
    await settle(); visible(await snapshot(), 'hub-leaf-detach');
    await page.evaluate(() => window.shell.detachUnit()); await settle(); visible(await snapshot(), 'hub-detach');
    report.checks.push('direct-and-hub-assembly-attach-detach-fit');

    // The vendor rotation clock caps each RAF delta at 100ms. A wall-clock
    // camera tween can finish during a stalled frame while rotation is still
    // nearly side-on, then crop the eventual front pose. Keep that algorithm
    // executable as a negative control rather than relying on a timing claim.
    report.long_dt_reset = [];
    for (const negative of [true, false]) {
      await viewport(390); await setup('cores3', 'pir');
      await page.evaluate(() => window.shell.viewer.setView('left', {duration: 0}));
      await settle();
      await page.evaluate(negative => {
        const shell = window.shell, viewer = shell.viewer;
        viewer.fit();
        window.wallClockFitComplete = false;
        if (negative) viewer.fit = ({padding = 1.15, duration = 0} = {}) => {
          const target = viewer.target.clone(), distance = viewer.distance, started = performance.now();
          const animate = now => {
            const progress = duration ? Math.min(1, (now - started) / duration) : 1;
            const eased = progress < 0.5 ? 4 * progress ** 3 : 1 - (-2 * progress + 2) ** 3 / 2;
            const current = shell.assemblyCameraFrame(padding);
            shell.applyAssemblyCamera(target.clone().lerp(current.target, eased), distance + (current.distance - distance) * eased);
            if (progress < 1) requestAnimationFrame(animate);
            else window.wallClockFitComplete = true;
          };
          requestAnimationFrame(animate);
        };
        viewer.resetView({duration: 400});
        const until = performance.now() + 1200;
        while (performance.now() < until) { /* deliberate blocked browser RAF */ }
      }, negative);
      // The first render after the stall must keep the fixed camera animation
      // pending while the vendor still has >100ms of rotation left to consume.
      await page.evaluate(() => new Promise(requestAnimationFrame));
      const stalled = await page.evaluate(() => ({...window.snapshot(), wall_clock_complete: window.wallClockFitComplete, camera_pending: !!window.shell.cameraAnimation}));
      assert.ok(Math.abs(stalled.quaternion[3] - 1) > 1e-4, 'long RAF stall left the capped rotation pending');
      if (negative) assert.equal(stalled.wall_clock_complete, true);
      else assert.equal(stalled.camera_pending, true, 'camera must share the vendor render clock');
      await page.waitForFunction(() => Math.abs(window.shell.model.root.quaternion.w - 1) < 1e-9 && !window.shell.cameraAnimation);
      await settle(); const frame = await snapshot();
      const clipped = frame.ndc.min[0] < -1 || frame.ndc.max[0] > 1 || frame.ndc.min[1] < -1 || frame.ndc.max[1] > 1;
      if (negative) assert.ok(clipped, 'old wall-clock fit must crop the final pose after a long RAF delta');
      else visible(frame, 'long-dt-reset-final-pose');
      const filename = `${negative ? 'negative' : 'fixed'}-reset-long-dt.png`;
      await page.locator('#host').screenshot({path: resolve(output, filename)});
      report.long_dt_reset.push({negative_control: negative, blocked_ms: 1200, duration_ms: 400, stalled, final: frame, clipping_reproduced: clipped, filename});
    }
    report.checks.push('blocked-raf-old-clock-negative-control-and-final-pose-fit');

    // Use actual pointer orbit, wheel and pan, then preserve their intent while
    // changing FOV. User-selected cropping is allowed in this part of the test.
    await viewport(1440); await setup('cores3', 'pir');
    await page.evaluate(() => {window.shell.viewer.opts.inertia = false;});
    const stage = await page.locator('canvas').boundingBox();
    await page.mouse.move(stage.x + 10, stage.y + 20); await page.mouse.down();
    await page.mouse.move(stage.x + 43, stage.y + 41, {steps: 3}); await page.mouse.up();
    await page.mouse.wheel(0, -110); await settle();
    await page.keyboard.down('Shift');
    await page.mouse.move(stage.x + 10, stage.y + 20); await page.mouse.down();
    await page.mouse.move(stage.x + 27, stage.y + 30, {steps: 2}); await page.mouse.up(); await page.keyboard.up('Shift');
    const manual = await snapshot();
    assert.ok(Math.abs(manual.quaternion[0]) + Math.abs(manual.quaternion[1]) > 0.05, 'pointer orbit was exercised');
    const relative = await page.evaluate(() => {
      const viewer = window.shell.viewer, target = viewer.target.clone(), distance = viewer.distance;
      viewer.fit(); const reference = {distance: viewer.distance, target: viewer.target.toArray()};
      viewer.target.copy(target); viewer.distance = distance; viewer.camera.position.set(target.x, target.y, target.z + distance); viewer.camera.lookAt(target); viewer.camera.updateMatrixWorld(true); viewer.requestRender();
      return {ratio: distance / reference.distance, offset: target.toArray().map((value, index) => value - reference.target[index])};
    });
    assert.ok(relative.ratio < 1, 'wheel zoom was exercised'); assert.ok(relative.offset.some(value => Math.abs(value) > 1), 'pointer pan was exercised');
    await viewport(390); const resized = await snapshot();
    const resizedRelative = await page.evaluate(() => {
      const viewer = window.shell.viewer, target = viewer.target.clone(), distance = viewer.distance;
      viewer.fit(); const reference = {distance: viewer.distance, target: viewer.target.toArray()};
      viewer.target.copy(target); viewer.distance = distance; viewer.camera.position.set(target.x, target.y, target.z + distance); viewer.camera.lookAt(target); viewer.camera.updateMatrixWorld(true); viewer.requestRender();
      return {ratio: distance / reference.distance, offset: target.toArray().map((value, index) => value - reference.target[index])};
    });
    close(resizedRelative.ratio, relative.ratio, 'resize retains relative zoom');
    relative.offset.forEach((value, index) => close(resizedRelative.offset[index], value, `resize retains pan ${index}`));
    assert.deepEqual(resized.quaternion, manual.quaternion, 'resize retains pointer orbit');
    await page.evaluate(() => {
      const shell = window.shell, pixels = new Uint8Array(shell.display.width * shell.display.height * 2);
      for (let i = 0; i < 8; i++) {
        shell.setFrame(pixels, shell.display.width, shell.display.height);
        shell.setDeviceState({available: true, visual_commands: [{type: 'button-state', target: 'power', pressed: i % 2 === 0}]});
      }
    });
    await settle(); const polled = await snapshot();
    for (const key of ['distance', 'target', 'quaternion']) assert.deepEqual(polled[key], resized[key], `frame/state polling preserves ${key}`);
    assert.deepEqual(polled.events, [], 'orbit/zoom/pan/fit/readback must not echo runtime input');
    report.manual_view = {before: manual, after: resized, relative, resized_relative: resizedRelative};
    report.checks.push('pointer-orbit-wheel-zoom-pan-retained-on-resize', 'frame-state-poll-does-not-fit-or-echo');
    await page.evaluate(() => window.shell.viewer.resetView({duration: 60}));
    await page.waitForFunction(() => !window.shell.cameraAnimation && Math.abs(window.shell.model.root.quaternion.w - 1) < 1e-9);
    visible(await snapshot(), 'animated-reset-from-manual-pose');
    report.checks.push('animated-reset-fits-final-pose');

    await setup('sticks3', 'button');
    await page.locator('canvas').focus(); await page.keyboard.down('a');
    await viewport(768); await page.keyboard.up('a');
    const keys = (await snapshot()).events.filter(event => ['down', 'up'].includes(event.action));
    assert.deepEqual(keys.map(event => `${event.id}:${event.action}`), ['btnA:down', 'btnA:up']);
    await page.evaluate(() => {window.events = [];});
    const buttonPoint = await page.evaluate(async () => {
      const THREE = await import('three'), shell = window.shell, button = shell.model.list('button').find(button => button.path.startsWith('grove/'));
      const point = new THREE.Box3().setFromObject(button.cap || button.object3d).getCenter(new THREE.Vector3()).project(shell.viewer.camera);
      const rect = shell.viewer.renderer.domElement.getBoundingClientRect();
      const result = {x: rect.left + (point.x + 1) * rect.width / 2, y: rect.top + (1 - point.y) * rect.height / 2};
      if (shell.viewer.pick({clientX: result.x, clientY: result.y})?.component !== button) throw Error('Unit button pointer target is occluded');
      return result;
    });
    await page.mouse.click(buttonPoint.x, buttonPoint.y); await settle();
    const pointer = (await snapshot()).events;
    assert.deepEqual(pointer.map(event => event.action), ['down', 'up', 'click']);
    assert.ok(pointer.every(event => event.id.startsWith('grove/')));
    await viewport(390); await page.evaluate(() => window.shell.viewer.fit()); await settle();
    assert.deepEqual((await snapshot()).events, pointer, 'fit/resize must not repeat pointer input');
    report.input = {keys, pointer}; report.checks.push('focused-keyboard-resize-matching-release', 'unit-pointer-exactly-once-no-camera-echo');
    const disposed = await page.evaluate(() => {
      window.shell.viewer.resetView({duration: 1000});
      window.shell.dispose();
      return {target: window.shell.viewer.target.toArray(), distance: window.shell.viewer.distance};
    });
    await viewport(1440);
    assert.deepEqual(await page.evaluate(() => ({target: window.shell.viewer.target.toArray(), distance: window.shell.viewer.distance})), disposed, 'dispose cancels camera animation');
    assert.equal(await page.locator('#host canvas').count(), 0); report.checks.push('reset-view-and-dispose');
  }
  assert.deepEqual(errors, []); assert.deepEqual(missing, []);
  report.status = baselineOnly ? 'BASELINE_CLIPPING_REPRODUCED' : 'PASS';
  console.log(baselineOnly ? 'MODEL_CAMERA_BASELINE_CLIPPING_REPRODUCED' : 'MODEL_CAMERA_FIT_BROWSER_OK');
} catch (error) {report.failure = error.stack; throw error;}
finally {
  report.source_sha256 = Object.fromEntries(await Promise.all(owned.map(async path => [path, createHash('sha256').update(await readFile(resolve(root, path))).digest('hex')])));
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  await browser.close(); await new Promise(done => server.close(done));
}
