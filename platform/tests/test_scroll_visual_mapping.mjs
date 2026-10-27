// Real mounted Scroll/UnitPanel HTTP fixture. Guest/controller/hardware NOT RUN.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, extname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = resolve(process.env.M5_SCROLL_VISUAL_OUT || '/tmp/m5-scroll-visual-fixture');
const device = JSON.parse(await readFile(resolve(root, 'devices/catalog.source.json'), 'utf8')).devices.find(row => row.id === 'sticks3');
const catalog = JSON.parse(await readFile(resolve(root, 'platform/units/catalog.json'), 'utf8'));
const profiles = JSON.parse(await readFile(resolve(root, 'platform/units/runtime-profiles.json'), 'utf8')).units;
const definition = {...catalog.units.find(row => row.id === 'scroll'), runtime: {...profiles.scroll, status: 'implemented', hosts: ['sticks3']}};
const attachment = {id: 'scroll1', unit_id: 'scroll', port_id: 'port-a', visual_port: 'grove'};
const session = {session_id: 'synthetic-scroll-fixture', device_id: 'sticks3', state: 'running', units: [attachment]};
const fixtures = new Map();
const makeFixture = session => {
  const fixture = {session, properties: {'source-count': 0, pressed: false, counter: 0, increments: 0, direction: 1, 'ab-direction': 0, 'led-rgb': 0}, posts: [], postPaths: [], gets: [], rejected: []};
  fixtures.set(session.session_id, fixture);
  return fixture;
};
const initial = makeFixture(session);
const {properties, posts, gets} = initial;
const payload = fixture => ({source: 'browser-test-fixture', session_id: fixture.session.session_id, definitions: [definition], units: [{...attachment, available: true, errors: {}, properties: fixture.properties}]});
const report = {category: 'mounted-scroll-http-browser-fixture', captured_at: new Date().toISOString(), status: 'FAIL', guest_execution: 'NOT RUN', hardware_execution: 'NOT RUN', checks: [], errors: []};
const harness = `<!doctype html><html><head><meta charset="utf-8"><link rel="icon" href="data:,"><link rel="stylesheet" href="/platform/web/three-device-viewer.css"><style>body{margin:0;padding:12px;display:grid;grid-template-columns:900px 320px;gap:16px}#host{width:900px;height:760px}.three-device-root,.three-device-stage{min-height:760px!important}#panel{max-height:760px;overflow:auto;font:13px system-ui}.unit-values{display:grid;grid-template-columns:1fr 1fr;gap:6px}.unit-value-source{display:block;font-size:10px}</style><script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script></head><body><div id="host"></div><div id="panel"></div></body></html>`;
const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, 'http://localhost');
    if (url.pathname === '/harness') {response.setHeader('Content-Type', 'text/html'); response.end(harness); return;}
    if (url.pathname.startsWith('/api/')) {
      response.setHeader('Content-Type', 'application/json');
      if (url.pathname === '/api/v1/units') {response.end(JSON.stringify({units: [definition], hosts: []})); return;}
      const route = /^\/api\/v1\/sessions\/([^/]+)\/(unit-input|units)$/.exec(url.pathname);
      const fixture = fixtures.get(route?.[1]);
      if (!fixture) throw new Error(`unexpected fixture API ${request.method} ${url.pathname}`);
      if (route[2] === 'unit-input' && request.method === 'POST') {
        let raw = ''; for await (const part of request) raw += part;
        const body = JSON.parse(raw);
        assert.equal(body.id, attachment.id);
        const fields = Object.keys(body.values);
        if (!fields.length || !fields.every(key => definition.inputs?.[key] && !definition.inputs[key].readOnly && !Object.hasOwn(definition.outputs || {}, key))) {
          fixture.rejected.push({path: url.pathname, fields, status: 400});
          response.writeHead(400).end(JSON.stringify({error: {code: 'invalid_unit_input', message: 'fixture input schema rejects readonly or unknown fields'}}));
          return;
        }
        fixture.posts.push(structuredClone(body)); fixture.postPaths.push(url.pathname); Object.assign(fixture.properties, body.values);
        if (fixture.holdRelease && body.values.pressed === false) {
          fixture.holdRelease = false;
          fixture.releaseResponse = {response, body: JSON.stringify(payload(fixture))};
          return;
        }
      } else if (route[2] === 'units' && request.method === 'GET') {
        fixture.gets.push(Date.now());
        if (fixture.holdGet) {
          fixture.holdGet = false;
          fixture.getResponse = {response, body: JSON.stringify(payload(fixture))};
          return;
        }
      }
      else throw new Error(`unexpected fixture API ${request.method} ${url.pathname}`);
      response.end(JSON.stringify(payload(fixture))); return;
    }
    const path = resolve(root, '.' + decodeURIComponent(url.pathname));
    if (!path.startsWith(root + '/')) {response.writeHead(403).end(); return;}
    response.setHeader('Content-Type', {'.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.json': 'application/json'}[extname(path)] || 'application/octet-stream');
    response.end(await readFile(path));
  } catch (error) {report.errors.push(error.message); response.writeHead(500).end();}
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
const waitFor = async (predicate, message) => {
  const deadline = Date.now() + 5000;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error(message);
    await new Promise(resolve => setTimeout(resolve, 10));
  }
};
const completeHeldResponse = held => {assert.ok(held, 'expected a captured HTTP response'); held.response.end(held.body);};
try {
  browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  report.browser_version = browser.version();
  const page = await browser.newPage({viewport: {width: 1260, height: 850}});
  page.on('pageerror', error => report.errors.push(error.message));
  const mount = async fixtureSession => {
    await page.goto(`http://127.0.0.1:${server.address().port}/harness`);
    await page.evaluate(async ({device, session}) => {
    const {createModelShell} = await import('/platform/web/model-shell.js');
    const {createUnitPanel} = await import('/platform/web/unit-panel.js');
    window.api = async (url, options) => {const response = await fetch(url, options); if (!response.ok) throw new Error('fixture HTTP ' + response.status); return response.json();};
    window.shell = await createModelShell(document.querySelector('#host'), device, {live: true});
    window.panel = await createUnitPanel(document.querySelector('#panel'), {session, shell: window.shell, api: window.api});
    clearTimeout(window.panel.timer);
    window.events = []; window.trusted = [];
    window.shell.on('unit-input', event => {window.events.push(structuredClone(event)); window.panel.handleInput(event);});
    window.shell.viewer.renderer.domElement.addEventListener('pointerdown', event => window.trusted.push(event.isTrusted));
    window.press = window.shell.model.button('grove/press');
    window.led = window.shell.model.find('grove/rgb', 'led');
    window.joint = window.shell.model.find('grove/rotation', 'joint');
    if (!window.press || !window.led || !window.joint) throw new Error('real Scroll components missing');
    window.visualWrites = [];
    const apply = window.shell.applyVisualState.bind(window.shell);
    window.shell.applyVisualState = (...args) => {window.visualWrites.push(structuredClone(args)); return apply(...args);};
    }, {device, session: fixtureSession});
    return page.evaluate(async () => {
    const {Box3, Vector3} = await import('three'); const viewer = window.shell.viewer;
    const settle = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    // setView uses a public animation even for duration=0. Fit the resulting
    // mounted geometry after it has settled, with a conservative camera margin.
    viewer.setView('front', {duration: 0}); await settle();
    viewer.resize(); viewer.fit({padding: 1.65, duration: 0}); await settle();
    viewer.scene.updateMatrixWorld(true); viewer.camera.updateMatrixWorld(true);
    const canvas = viewer.renderer.domElement.getBoundingClientRect();
    const projectBounds = object => {
      const box = new Box3().setFromObject(object), corners = [];
      for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
        const point = new Vector3(x, y, z).project(viewer.camera);
        corners.push({x: canvas.left + (point.x + 1) * canvas.width / 2, y: canvas.top + (1 - point.y) * canvas.height / 2, z: point.z});
      }
      return {left: Math.min(...corners.map(p => p.x)), right: Math.max(...corners.map(p => p.x)), top: Math.min(...corners.map(p => p.y)), bottom: Math.max(...corners.map(p => p.y)), corners};
    };
    window.framing = {canvas: {left: canvas.left, right: canvas.right, top: canvas.top, bottom: canvas.bottom}, scroll: projectBounds(window.shell.model.port('grove').module.root), assembly: projectBounds(window.shell.model.root), viewport: {width: innerWidth, height: innerHeight}, padding: 1.65};
    const bounds = new Box3().setFromObject(window.press.cap), rect = viewer.renderer.domElement.getBoundingClientRect();
    for (const fx of [.5, .25, .75]) for (const fy of [.5, .25, .75]) {
      const q = new Vector3(bounds.min.x + (bounds.max.x - bounds.min.x) * fx, bounds.min.y + (bounds.max.y - bounds.min.y) * fy, bounds.max.z).project(viewer.camera);
      const p = {clientX: rect.left + (q.x + 1) * rect.width / 2, clientY: rect.top + (1 - q.y) * rect.height / 2};
      if (viewer.pick(p)?.component === window.press) return {x: p.clientX, y: p.clientY, framing: window.framing};
    }
    throw new Error('Scroll wheel is not a visible canvas target');
    });
  };
  const point = await mount(session);
  report.framing = point.framing;
  for (const name of ['scroll', 'assembly']) {
    const {canvas, viewport, [name]: bounds} = point.framing;
    assert.ok(bounds.corners.every(p => Number.isFinite(p.x) && Number.isFinite(p.y) && p.z > -1 && p.z < 1), `${name} projected bounds must be finite and in camera depth`);
    assert.ok(bounds.left >= canvas.left + 8 && bounds.right <= canvas.right - 8 && bounds.top >= canvas.top + 8 && bounds.bottom <= canvas.bottom - 8, `${name} geometry must fit inside the actual canvas with an 8px margin`);
    assert.ok(bounds.left >= 8 && bounds.right <= viewport.width - 8 && bounds.top >= 8 && bounds.bottom <= viewport.height - 8, `${name} must also fit in the screenshot viewport`);
  }
  assert.ok(point.framing.scroll.bottom - point.framing.scroll.top > 100, 'Scroll must remain large enough to inspect');
  report.checks.push('complete-scroll-and-mounted-assembly-projected-inside-canvas-and-screenshot');
  await page.mouse.click(point.x, point.y);
  await page.waitForFunction(() => window.events.some(event => event.action === 'up'));
  await page.evaluate(async () => {await Promise.all([...window.panel.queues.values()]); clearTimeout(window.panel.timer);});
  assert.deepEqual(posts.map(row => row.values), [{pressed: true}, {pressed: false}]);
  assert.equal(await page.evaluate(() => window.trusted.every(Boolean) && window.trusted.length > 0), true);
  report.checks.push('trusted-canvas-press-release-through-real-panel-and-http');
  const beforePosts = posts.length;
  const beforeEvents = await page.evaluate(() => window.events.length);
  report.observations = [];
  await mkdir(output, {recursive: true});
  for (const color of [0x123456, 0x00ff00, 0]) {
    Object.assign(properties, {pressed: color !== 0, 'led-rgb': color, counter: 123456, 'source-count': 100});
    const observation = await page.evaluate(async () => {
      window.panel.apply(await window.api(`/api/v1/sessions/${window.panel.session.session_id}/units`));
      clearTimeout(window.panel.timer);
      return {led: window.led.getState(), glow: window.led.glow.visible, opacity: window.led.glow.material.opacity, emissive: window.led.lensMaterial.emissive.toArray(), pressed: window.press.getState().pressed, joint: window.joint.getState(), events: window.events.length};
    });
    assert.equal(observation.led.color, '#' + color.toString(16).padStart(6, '0'));
    assert.equal(observation.led.brightness, color === 0 ? 0 : 1);
    assert.equal(observation.glow, color !== 0); assert.equal(observation.opacity, color === 0 ? 0 : .85);
    assert.equal(observation.events, beforeEvents, 'readback must not emit physical input events');
    assert.equal(observation.pressed, color !== 0); assert.equal(observation.joint.angleDeg, 0, 'logical counter/source cannot invent a calibrated shaft angle');
    if (color) assert.ok(observation.emissive.some(value => value > 0));
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const screenshot = `scroll-${color.toString(16).padStart(6, '0')}.png`;
    const png = await page.screenshot({path: resolve(output, screenshot)});
    observation.screenshot = {path: screenshot, sha256: createHash('sha256').update(png).digest('hex'), bytes: png.length};
    report.observations.push(observation);
  }
  assert.equal(posts.length, beforePosts, 'readback must not echo inputs');
  report.checks.push('http-readback-drives-real-single-rgb-and-button-with-zero-echo');
  report.checks.push('logical-writes-and-source-count-do-not-invent-uncalibrated-angle');
  const outputs = Object.keys(definition.outputs || {});
  const beforeReadonly = structuredClone(properties);
  report.readonly = await page.evaluate(async ({outputs, sessionId, attachmentId}) => {
    const controls = [...window.panel.container.querySelectorAll('[data-input-field], [data-press-field]')].map(node => node.dataset.inputField || node.dataset.pressField);
    const statuses = [];
    for (const field of outputs) {
      const response = await fetch(`/api/v1/sessions/${sessionId}/unit-input`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: attachmentId, values: {[field]: 0}})});
      statuses.push({field, status: response.status, error: (await response.json()).error?.code});
    }
    // A mixed request must not apply its otherwise writable pressed value.
    const response = await fetch(`/api/v1/sessions/${sessionId}/unit-input`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: attachmentId, values: {pressed: true, 'led-rgb': 0xffffff}})});
    statuses.push({field: 'mixed-input-and-output', status: response.status, error: (await response.json()).error?.code});
    await window.panel.send(attachmentId, {'led-rgb': 0xffffff});
    return {controls, statuses};
  }, {outputs, sessionId: session.session_id, attachmentId: attachment.id});
  assert.ok(outputs.length > 0);
  assert.ok(report.readonly.statuses.every(row => row.status === 400 && row.error === 'invalid_unit_input'));
  assert.ok(outputs.every(field => !report.readonly.controls.includes(field)), 'readonly fields must have no generic panel input');
  assert.ok(['source-count', 'pressed'].every(field => report.readonly.controls.includes(field)), 'the fixture must exercise the actual editable input schema');
  assert.deepEqual(properties, beforeReadonly, 'rejected output writes must not mutate any fixture state');
  assert.equal(posts.length, beforePosts);
  report.readonly.rejected = initial.rejected;
  report.checks.push('readonly-output-fields-have-no-input-and-all-fixture-posts-fail-atomically');
  await page.evaluate(() => {window.panel.dispose(); window.shell.dispose();});

  report.disposal = [];
  for (const first of ['panel', 'shell']) {
    const fixtureSession = {...session, session_id: `synthetic-scroll-held-${first}`};
    const fixture = makeFixture(fixtureSession);
    const heldPoint = await mount(fixtureSession);
    await page.evaluate(() => {window.press.longPressMs = 150;});
    await page.mouse.move(heldPoint.x, heldPoint.y); await page.mouse.down();
    await page.waitForFunction(() => window.events.some(event => event.action === 'down' && event.source.startsWith('pointer:')));
    await page.evaluate(async () => {await Promise.all([...window.panel.queues.values()]); clearTimeout(window.panel.timer);});
    assert.deepEqual(fixture.posts.map(row => row.values), [{pressed: true}]);
    // Capture a stale GET while the original session owns the hold. Keep its
    // response and the release ACK until both public dispose methods finish.
    fixture.properties['led-rgb'] = 0xff00ff;
    fixture.holdGet = true;
    await page.evaluate(() => {window.staleRefresh = window.panel.refresh();});
    await waitFor(() => fixture.getResponse, 'held-session GET was not captured');
    fixture.holdRelease = true;
    const atDispose = await page.evaluate(first => {
      const originalSessionId = window.panel.session.session_id;
      if (first === 'panel') {window.panel.dispose(); window.shell.dispose();}
      else {window.shell.dispose(); window.panel.dispose();}
      window.releaseQueues = [...window.panel.queues.values()];
      return {originalSessionId, panelDisposed: window.panel.disposed, shellDisposed: window.shell.disposed, visualWrites: window.visualWrites.length, eventCount: window.events.length, events: structuredClone(window.events), trusted: structuredClone(window.trusted), ownedPressSources: window.panel.pressSources.size, lastReadbackPressed: window.press.getState().pressed};
    }, first);
    await waitFor(() => fixture.releaseResponse, 'dispose did not submit its owned release');
    assert.deepEqual(fixture.posts.map(row => row.values), [{pressed: true}, {pressed: false}], 'each held dispose must send exactly one matching release');
    assert.ok(fixture.postPaths.every(path => path === `/api/v1/sessions/${fixtureSession.session_id}/unit-input`), 'both queued requests must target the original owning session');
    assert.equal(atDispose.originalSessionId, fixtureSession.session_id);
    assert.equal(atDispose.panelDisposed, true); assert.equal(atDispose.shellDisposed, true);
    assert.equal(atDispose.ownedPressSources, 0);
    assert.equal(fixture.properties.pressed, false, 'the original session fixture must receive the owned release');
    assert.ok(atDispose.trusted.length > 0 && atDispose.trusted.every(Boolean));
    assert.equal(atDispose.events.filter(event => event.action === 'down').length, 1);
    assert.equal(atDispose.events.filter(event => event.action === 'up').length, 1);
    assert.equal(atDispose.events.find(event => event.action === 'up').cancelled, true);
    if (first === 'panel') {completeHeldResponse(fixture.getResponse); completeHeldResponse(fixture.releaseResponse);}
    else {completeHeldResponse(fixture.releaseResponse); completeHeldResponse(fixture.getResponse);}
    const after = await page.evaluate(async () => {
      await Promise.all([...window.releaseQueues, window.staleRefresh]);
      // Exercise public no-op paths after teardown and let cancelled timers
      // and the browser's eventual pointerup run past their old deadline.
      window.panel.handleInput({kind: 'button', id: 'grove/press', action: 'down', source: 'late-fixture'});
      await window.panel.send('scroll1', {'source-count': 99});
      window.panel.dispose(); window.shell.dispose();
      await new Promise(resolve => setTimeout(resolve, 200));
      return {visualWrites: window.visualWrites.length, eventCount: window.events.length, led: window.led.getState(), timer: window.panel.timer, rootConnected: window.shell.root.isConnected};
    });
    await page.mouse.up();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(after.visualWrites, atDispose.visualWrites, 'late GET/POST responses must not call the disposed visual shell');
    assert.equal(after.eventCount, atDispose.eventCount, 'dispose must cancel delayed press events');
    assert.equal(after.led.color, '#000000', 'the stale magenta fixture response must not repaint the disposed LED');
    assert.equal(after.rootConnected, false);
    assert.deepEqual(fixture.posts.map(row => row.values), [{pressed: true}, {pressed: false}], 'late responses, pointerup and repeated dispose must not submit again');
    const finalEventCount = await page.evaluate(() => window.events.length);
    assert.equal(finalEventCount, atDispose.eventCount);
    report.disposal.push({first, ...atDispose, after, post_paths: fixture.postPaths, posts: fixture.posts, delayed_responses: first === 'panel' ? ['stale-get', 'release-ack'] : ['release-ack', 'stale-get'], late_posts: fixture.posts.length - 2});
    report.checks.push(`trusted-held-${first}-dispose-releases-original-session-once-with-no-late-echo`);
  }
  assert.deepEqual(report.errors, []); report.status = 'PASS'; report.posts = posts; report.gets = gets.length;
  console.log(`SCROLL_VISUAL_FIXTURE_OK ${report.checks.length} checks; guest/hardware NOT RUN`);
} catch (error) {report.failure = error.stack; throw error;}
finally {
  report.source_sha256 = Object.fromEntries(await Promise.all(['platform/web/unit-visual-mappings.js', 'platform/web/unit-panel.js', 'platform/web/model-shell.js', 'platform/units/catalog.json', 'platform/units/runtime-profiles.json', 'platform/tests/test_scroll_visual_mapping.mjs', 'platform/web/vendor/m5stack-models/src/units/scroll/index.js'].map(async name => [name, createHash('sha256').update(await readFile(resolve(root, name))).digest('hex')])));
  await mkdir(output, {recursive: true}); await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  await browser?.close(); await new Promise(resolve => server.close(resolve));
}
