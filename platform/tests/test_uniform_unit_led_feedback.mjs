// Real mounted RGB/Encoder/8Encoder HTTP fixture. No guest/controller/hardware execution.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, extname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = resolve(process.env.M5_UNIFORM_LED_OUT || '/tmp/m5-uniform-unit-led-fixture');
await mkdir(output, {recursive: false});
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const sources = ['platform/web/unit-visual-mappings.js', 'platform/web/model-shell.js', 'platform/web/unit-panel.js',
  'platform/tests/test_uniform_unit_led_feedback.mjs', 'platform/units/catalog.json', 'platform/units/runtime-profiles.json',
  'platform/web/vendor/m5stack-models/src/core/components/Led.js',
  'platform/web/vendor/m5stack-models/src/units/rgb/index.js',
  'platform/web/vendor/m5stack-models/src/units/encoder/assembly.js',
  'platform/web/vendor/m5stack-models/src/units/8encoder/index.js'];
const fingerprints = async () => Object.fromEntries(await Promise.all(sources.map(async path => [path, sha(await readFile(resolve(root, path)))])));
const frozen = await fingerprints();
const device = JSON.parse(await readFile(resolve(root, 'devices/catalog.source.json'), 'utf8')).devices.find(row => row.id === 'sticks3');
const catalog = JSON.parse(await readFile(resolve(root, 'platform/units/catalog.json'), 'utf8'));
const profiles = JSON.parse(await readFile(resolve(root, 'platform/units/runtime-profiles.json'), 'utf8')).units;
const targets = {rgb: ['led0', 'led1', 'led2'], encoder: ['led0', 'led1'], '8encoder': Array.from({length: 9}, (_, i) => `rgb-${i + 1}`)};
const definitions = Object.keys(targets).map(id => ({...catalog.units.find(row => row.id === id), runtime: profiles[id]}));
const fixtures = new Map();
const makeFixture = (unitId, suffix) => {
  const attachment = {id: 'unit1', unit_id: unitId, port_id: 'port-a', visual_port: 'grove'};
  const fixture = {session: {session_id: `synthetic-uniform-${unitId}-${suffix}`, device_id: 'sticks3', state: 'running', units: [attachment]},
    attachment, available: true, errors: {}, properties: {'led-rgb': Array(targets[unitId].length).fill(0xff0000),
      ...(unitId === 'encoder' ? {counter: 0, pressed: false} : unitId === '8encoder' ? {counters: Array(8).fill(0), pressed: Array(8).fill(false), 'switch-on': false} : {})}, posts: [], gets: 0};
  fixtures.set(fixture.session.session_id, fixture);
  return fixture;
};
const payload = fixture => ({source: 'browser-test-fixture', session_id: fixture.session.session_id, definitions,
  units: fixture.omitUnit ? [] : [{...fixture.attachment, available: fixture.available, errors: fixture.errors, properties: fixture.properties}]});
const report = {category: 'mounted-uniform-array-led-http-browser-fixture', status: 'FAIL', captured_at: new Date().toISOString(),
  guest_execution: 'NOT RUN', controller_execution: 'NOT RUN', hardware_execution: 'NOT RUN',
  limits: ['Uniform colors only without binding; no physical LED index permutation or mechanical-angle closure.', 'Explicit permutations below are synthetic converter fixtures, not hardware evidence.'],
  source_sha256: frozen, checks: [], units: [], disposal: [], errors: [], resource_errors: []};
const harness = `<!doctype html><html><head><meta charset="utf-8"><link rel="icon" href="data:,"><link rel="stylesheet" href="/platform/web/three-device-viewer.css"><style>body{margin:0;padding:12px;display:grid;grid-template-columns:900px 420px;gap:16px}#host{width:900px;height:800px}.three-device-root,.three-device-stage{min-height:800px!important}#panel{max-height:800px;overflow:auto;font:13px system-ui}.unit-values{display:grid;grid-template-columns:1fr 1fr;gap:6px}.unit-value-source{display:block;font-size:10px}</style><script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script></head><body><div id="host"></div><div id="panel"></div></body></html>`;
const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, 'http://localhost');
    if (url.pathname === '/harness') {response.setHeader('Content-Type', 'text/html'); response.end(harness); return;}
    if (url.pathname === '/api/v1/units') {response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({units: definitions, hosts: []})); return;}
    if (url.pathname.startsWith('/api/')) {
      const route = /^\/api\/v1\/sessions\/([^/]+)\/(units|unit-input)$/.exec(url.pathname);
      const fixture = fixtures.get(route?.[1]);
      if (!fixture) throw new Error(`Unexpected fixture API ${request.method} ${url.pathname}`);
      response.setHeader('Content-Type', 'application/json');
      if (route[2] === 'unit-input') {
        let body = ''; for await (const chunk of request) body += chunk;
        fixture.posts.push({path: url.pathname, body: JSON.parse(body)});
        response.writeHead(400).end(JSON.stringify({error: 'output fixture must never send inputs'})); return;
      }
      assert.equal(request.method, 'GET'); fixture.gets++;
      if (fixture.failNext) {fixture.failNext = false; response.writeHead(503).end(JSON.stringify({error: 'intentional unavailable fixture'})); return;}
      const body = JSON.stringify(payload(fixture));
      if (fixture.holdNext) {fixture.holdNext = false; fixture.held = {response, body}; return;}
      response.end(body); return;
    }
    const path = resolve(root, '.' + decodeURIComponent(url.pathname));
    if (!path.startsWith(root + '/')) {response.writeHead(403).end(); return;}
    response.setHeader('Content-Type', {'.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.json': 'application/json'}[extname(path)] || 'application/octet-stream');
    response.end(await readFile(path));
  } catch (error) {report.errors.push(error.message); response.writeHead(500).end();}
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
const waitFor = async predicate => {
  const deadline = Date.now() + 5000;
  while (!predicate()) {assert.ok(Date.now() < deadline, 'Expected held GET'); await new Promise(resolve => setTimeout(resolve, 10));}
};
const hex = color => '#' + color.toString(16).padStart(6, '0');
const emission = color => [16, 8, 0].map(shift => {
  const s = ((color >>> shift) & 255) / 255;
  return (s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4) * 2.2;
});
const near = (actual, expected) => actual.forEach((channel, i) => assert.ok(Math.abs(channel - expected[i]) < 1e-6, `emission ${actual} != ${expected}`));
try {
  browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  report.browser_version = browser.version();
  const page = await browser.newPage({viewport: {width: 1360, height: 860}});
  page.on('pageerror', error => report.errors.push(error.message));
  page.on('response', response => {if (response.status() >= 400 && !response.url().includes('/api/')) report.resource_errors.push({url: response.url(), status: response.status()});});
  const mount = async fixture => {
    await page.goto(`http://127.0.0.1:${server.address().port}/harness`);
    await page.evaluate(async ({device, session, ids}) => {
      const {createModelShell} = await import('/platform/web/model-shell.js');
      const {createUnitPanel} = await import('/platform/web/unit-panel.js');
      window.api = async (url, options) => {const response = await fetch(url, options); if (!response.ok) throw new Error('fixture HTTP ' + response.status); return response.json();};
      window.shell = await createModelShell(document.querySelector('#host'), device, {live: true});
      window.panel = await createUnitPanel(document.querySelector('#panel'), {session, shell: window.shell, api: window.api});
      clearTimeout(window.panel.timer);
      window.events = []; window.visualWrites = [];
      window.shell.on('unit-input', event => {window.events.push(structuredClone(event)); window.panel.handleInput(event);});
      const apply = window.shell.applyVisualState.bind(window.shell);
      window.shell.applyVisualState = (...args) => {window.visualWrites.push(structuredClone(args)); return apply(...args);};
      window.module = window.shell.model.port('grove').module;
      window.leds = ids.map(id => window.shell.model.find('grove/' + id, 'led'));
      if (!window.module || window.leds.some(led => !led)) throw new Error('Actual mounted LEDs are missing');
      window.inspect = () => {
        const note = window.panel.container.querySelector('[data-unit-led-mapping]');
        return {
          leds: window.leds.map(led => ({id: led.id, path: led.path, known: led.runtimeKnown, userDataKnown: led.object3d.userData.runtimeKnown,
            state: led.getState(), emissive: led.lensMaterial.emissive.toArray(), glow: led.glow.visible, opacity: led.glow.material.opacity,
            glowColor: '#' + led.glow.material.color.getHexString(), attached: window.module.components.get(led.id) === led})),
          diffusion: window.module.encoderShellDiffusion ? [0, 1].map(i => ({brightness: window.module.encoderShellDiffusion.uniforms['encoderBrightness' + i].value,
            color: window.module.encoderShellDiffusion.uniforms['encoderColor' + i].value.toArray()})) : null,
          hint: note ? {hidden: note.hidden, text: note.textContent, mode: note.dataset.unitLedMapping} : null,
          readback: [...window.panel.container.querySelectorAll('[data-unit-rgb]')].map(node => node.textContent.trim()),
          joints: window.module.list('joint').map(joint => joint.getState()), events: window.events.length, visualWrites: window.visualWrites.length,
        };
      };
      const settle = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      window.shell.viewer.setView('front', {duration: 0}); await settle();
      window.shell.viewer.resize(); window.shell.viewer.fit({padding: 1.6, duration: 0}); await settle();
      clearTimeout(window.panel.timer);
    }, {device, session: fixture.session, ids: targets[fixture.attachment.unit_id]});
  };
  const observe = async (fixture, label, screenshot = false) => {
    const observation = await page.evaluate(async () => {await window.panel.refresh(); clearTimeout(window.panel.timer); return window.inspect();});
    observation.label = label;
    if (screenshot) {
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const name = `${fixture.attachment.unit_id}-${label}.png`, bytes = await page.screenshot({path: resolve(output, name)});
      observation.screenshot = {path: name, sha256: sha(bytes)};
    }
    assert.equal(observation.events, 0, 'Feedback must never generate physical input events');
    assert.equal(fixture.posts.length, 0, 'Feedback must never POST fixture inputs');
    assert.ok(observation.joints.every(joint => joint.angleDeg === 0 && joint.targetAngleDeg === 0 && joint.rpm === 0), 'Raw counters/reset must not move any shaft');
    return observation;
  };
  const assertKnown = (observation, colors, mapping = 'uniform') => {
    assert.equal(observation.leds.length, colors.length);
    assert.deepEqual(observation.hint, {hidden: true, text: '', mode: mapping});
    observation.leds.forEach((led, i) => {
      assert.equal(led.attached, true); assert.equal(led.known, true); assert.equal(led.userDataKnown, true);
      assert.equal(led.state.color, hex(colors[i])); assert.equal(led.state.brightness, colors[i] === 0 ? 0 : 1);
      assert.equal(led.glowColor, hex(colors[i])); assert.equal(led.glow, colors[i] !== 0); assert.equal(led.opacity, colors[i] === 0 ? 0 : .85);
      near(led.emissive, emission(colors[i]));
    });
    if (observation.diffusion) observation.diffusion.forEach((uniform, i) => {
      assert.equal(uniform.brightness, colors[i] === 0 ? 0 : 1); near(uniform.color.map(c => c * 2.2), emission(colors[i]));
    });
  };
  const assertUnknown = (observation, count, reason) => {
    assert.equal(observation.leds.length, count); assert.equal(observation.hint.hidden, false); assert.equal(observation.hint.mode, reason);
    assert.ok(observation.hint.text.includes(reason === 'unmapped' ? '灯位未确认' : reason === 'invalid' ? '读回无效' : '状态未知'));
    observation.leds.forEach(led => {
      assert.equal(led.attached, true); assert.equal(led.known, false); assert.equal(led.userDataKnown, false);
      assert.deepEqual(led.state, {color: '#000000', brightness: 0}); assert.deepEqual(led.emissive, [0, 0, 0]);
      assert.equal(led.glow, false); assert.equal(led.opacity, 0);
    });
    if (observation.diffusion) observation.diffusion.forEach(uniform => {assert.equal(uniform.brightness, 0); assert.deepEqual(uniform.color, [0, 0, 0]);});
  };
  for (const unitId of Object.keys(targets)) {
    const fixture = makeFixture(unitId, 'states'), count = targets[unitId].length, observations = [];
    await mount(fixture);
    const setColors = colors => {fixture.properties['led-rgb'] = colors;};
    const uniform = (color, label, screenshot = false) => {setColors(Array(count).fill(color)); return observe(fixture, label, screenshot);};
    for (const [color, label] of [[0xff0000, 'red'], [0x00ff00, 'green'], [0x0000ff, 'blue']]) {
      const observation = await uniform(color, label, label === 'red'); assertKnown(observation, Array(count).fill(color)); observations.push(observation);
    }
    if (unitId === 'encoder') fixture.properties.counter = 301;
    if (unitId === '8encoder') fixture.properties.counters = [100, -100, 200, -200, 300, -300, 400, -400];
    const asymmetric = Array.from({length: count}, (_, i) => [0xff0000, 0x00ff00, 0x0000ff, 0xffff00, 0xff00ff, 0x00ffff, 0x123456, 0xabcdef, 0x101010][i]);
    setColors(asymmetric);
    const unmapped = await observe(fixture, 'nonuniform', true); assertUnknown(unmapped, count, 'unmapped');
    assert.deepEqual(unmapped.readback, asymmetric.map((color, i) => `LED[${i}] ${hex(color)}`), 'Real numeric readback must survive unknown visual mapping'); observations.push(unmapped);
    const invalidCommands = await page.evaluate(() => {
      const failures = [], led = window.leds[0], target = led.path;
      for (const fields of [{color: {}}, {color: 'not-a-color'}, {color: NaN}, {color: Infinity}, {color: -1}, {color: 0x1000000}, {brightness: NaN}, {on: 'true'}]) {
        try {window.shell.applyVisualState({type: 'led', target, ...fields});}
        catch (error) {failures.push(error.message);}
      }
      const handle = led.handle;
      led.handle = () => {throw new Error('intentional LED handle failure');};
      try {window.shell.applyVisualState({type: 'led', target, color: 0xff0000, on: true});}
      catch (error) {failures.push(error.message);}
      finally {led.handle = handle;}
      return {failures, observation: window.inspect()};
    });
    assert.equal(invalidCommands.failures.length, 9);
    assertUnknown(invalidCommands.observation, count, 'unmapped');
    report.checks.push(`${unitId}-invalid-color-brightness-on-or-failed-handle-cannot-promote-unknown`);
    if (unitId === 'encoder') fixture.properties.counter = 0;
    if (unitId === '8encoder') fixture.properties.counters = Array(8).fill(0);
    const restored = await uniform(0x00ff00, 'restored', true); assertKnown(restored, Array(count).fill(0x00ff00)); observations.push(restored);
    const off = await uniform(0, 'off', true); assertKnown(off, Array(count).fill(0)); observations.push(off);
    for (const [name, colors] of [['null', null], ['short', Array(count - 1).fill(0)], ['boolean', Array(count).fill(true)], ['negative', Array(count).fill(-1)], ['too-large', Array(count).fill(0x1000000)]]) {
      assertKnown(await uniform(0xff0000, `before-${name}`), Array(count).fill(0xff0000));
      setColors(colors); const observation = await observe(fixture, name); assertUnknown(observation, count, 'invalid'); observations.push(observation);
    }
    await uniform(0xff0000, 'before-unavailable'); fixture.available = false;
    const unavailable = await observe(fixture, 'unavailable'); assertUnknown(unavailable, count, 'unavailable'); observations.push(unavailable); fixture.available = true;
    await uniform(0xff0000, 'before-errors'); fixture.errors = {'led-rgb': 'intentional controller error'};
    const errors = await observe(fixture, 'errors'); assertUnknown(errors, count, 'unavailable'); observations.push(errors); fixture.errors = {};
    await uniform(0xff0000, 'before-missing-unit'); fixture.omitUnit = true;
    const missing = await observe(fixture, 'missing-unit'); assertUnknown(missing, count, 'unavailable'); observations.push(missing); fixture.omitUnit = false;
    await uniform(0xff0000, 'before-transport-error'); fixture.failNext = true;
    const transport = await observe(fixture, 'transport-error'); assertUnknown(transport, count, 'unavailable'); observations.push(transport);
    const recovered = await uniform(0x0000ff, 'recovered'); assertKnown(recovered, Array(count).fill(0x0000ff)); observations.push(recovered);
    await page.evaluate(({unitId, ids}) => {window.panel.bindingsByUnit[unitId] = {evidence: 'synthetic permutation fixture; not measured hardware', ledTargets: [...ids].reverse()};}, {unitId, ids: targets[unitId]});
    setColors(asymmetric); const explicit = await observe(fixture, 'explicit-permutation'); assertKnown(explicit, [...asymmetric].reverse(), 'explicit'); observations.push(explicit);
    await page.evaluate(unitId => {window.panel.bindingsByUnit[unitId].evidence = '';}, unitId);
    const noEvidence = await observe(fixture, 'no-evidence'); assertUnknown(noEvidence, count, 'unmapped'); observations.push(noEvidence);
    await page.evaluate(unitId => {window.panel.bindingsByUnit[unitId] = {evidence: 'invalid synthetic target set', ledTargets: Array(9).fill('invalid')};}, unitId);
    const fallback = await uniform(0xff0000, 'invalid-binding-uniform-fallback'); assertKnown(fallback, Array(count).fill(0xff0000)); observations.push(fallback);
    assert.equal(fixture.posts.length, 0);
    report.units.push({unit_id: unitId, led_count: count, observations, posts: fixture.posts, gets: fixture.gets});
    report.checks.push(`${unitId}-all-${count}-mounted-led-materials-uniform-unknown-explicit-recovery-no-echo-no-angle`);
    await page.evaluate(() => {window.panel.dispose(); window.shell.dispose();});
    const initialFailure = makeFixture(unitId, 'initial-unavailable'); initialFailure.failNext = true;
    await mount(initialFailure);
    const initialUnknown = await page.evaluate(() => window.inspect());
    assertUnknown(initialUnknown, count, 'unavailable');
    assertKnown(await observe(initialFailure, 'initial-recovery'), Array(count).fill(0xff0000));
    report.units.at(-1).initial_http_503 = initialUnknown;
    await page.evaluate(() => {window.panel.dispose(); window.shell.dispose();});
    for (const first of ['panel', 'shell']) {
      const disposed = makeFixture(unitId, `dispose-${first}`); await mount(disposed);
      assertKnown(await observe(disposed, 'before-dispose'), Array(count).fill(0xff0000));
      disposed.properties['led-rgb'] = Array(count).fill(0xff00ff); disposed.holdNext = true;
      await page.evaluate(() => {window.heldRefresh = window.panel.refresh();}); await waitFor(() => disposed.held);
      const beforeLate = await page.evaluate(first => {
        if (first === 'panel') {window.panel.dispose(); window.shell.dispose();} else {window.shell.dispose(); window.panel.dispose();}
        return {writes: window.visualWrites.length, events: window.events.length, leds: window.leds.map(led => ({known: led.runtimeKnown, state: led.getState(), glow: led.glow.visible, emissive: led.lensMaterial.emissive.toArray()})), rootConnected: window.shell.root.isConnected};
      }, first);
      assert.equal(beforeLate.rootConnected, false); assert.equal(beforeLate.events, 0);
      beforeLate.leds.forEach(led => {assert.equal(led.known, false); assert.deepEqual(led.state, {color: '#000000', brightness: 0}); assert.equal(led.glow, false); assert.deepEqual(led.emissive, [0, 0, 0]);});
      disposed.held.response.end(disposed.held.body);
      const afterLate = await page.evaluate(async () => {
        await window.heldRefresh; clearTimeout(window.panel.timer);
        await window.panel.send('unit1', {'led-rgb': [1]}); window.panel.dispose(); window.shell.dispose();
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        return {writes: window.visualWrites.length, events: window.events.length, leds: window.leds.map(led => ({known: led.runtimeKnown, state: led.getState(), glow: led.glow.visible, emissive: led.lensMaterial.emissive.toArray()})), rootConnected: window.shell.root.isConnected};
      });
      assert.deepEqual(afterLate, beforeLate, 'Late GET / repeated teardown must not repaint or emit events'); assert.equal(disposed.posts.length, 0);
      report.disposal.push({unit_id: unitId, first, beforeLate, afterLate, posts: disposed.posts, delayed_get: true});
    }
  }
  assert.deepEqual(await fingerprints(), frozen, 'Freeze all source bytes through the entire fixture');
  assert.deepEqual(report.errors, []); assert.deepEqual(report.resource_errors, []);
  report.checks.push('all-three-products-panel-first-shell-first-dispose-late-get-no-repaint-no-post');
  report.checks.push('source-bytes-frozen-no-guest-controller-or-hardware-execution');
  report.status = 'PASS'; console.log(`UNIFORM_UNIT_LED_FIXTURE_PASS ${output}/report.json`);
} catch (error) {report.failure = error.stack; throw error;}
finally {
  report.source_sha256_after = await fingerprints();
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  await browser?.close(); await new Promise(resolve => server.close(resolve));
}
