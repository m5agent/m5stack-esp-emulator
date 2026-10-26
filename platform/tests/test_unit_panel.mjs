// Browser bridge/lifecycle contract only: these fixtures do not execute firmware.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {resolve, dirname, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = process.env.M5_UNIT_PANEL_OUT || '/tmp/m5-unit-panel-test';
await mkdir(output, {recursive: true});
const units = JSON.parse(await readFile(resolve(root, 'platform/units/catalog.json'), 'utf8')).units;
const hosts = JSON.parse(await readFile(resolve(root, 'platform/units/host-ports.json'), 'utf8')).hosts;
const profiles = JSON.parse(await readFile(resolve(root, 'platform/units/runtime-profiles.json'), 'utf8')).units;
const inventory = {units: units.map(unit => ({...unit, runtime: {...(profiles[unit.id] || {}), ...(unit.id === 'pir' ? {status: 'planned'} : {})}})), hosts};
const server = createServer(async (request, response) => {
  const pathname = new URL(request.url, 'http://localhost').pathname;
  if (pathname === '/harness') {
    response.setHeader('Content-Type', 'text/html');
    response.end('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><link rel="stylesheet" href="/platform/web/m5-tokens.css"><link rel="stylesheet" href="/platform/web/unit-panel.css"></head><body><main id="panel"></main><div id="picker"></div></body></html>');
    return;
  }
  const path = resolve(root, `.${decodeURIComponent(pathname)}`);
  if (!path.startsWith(root + '/')) { response.writeHead(403).end(); return; }
  try {
    response.setHeader('Content-Type', {'.js': 'text/javascript', '.css': 'text/css'}[extname(path)] || 'application/octet-stream');
    response.end(await readFile(path));
  } catch { response.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
const page = await browser.newPage({viewport: {width: 700, height: 700}});
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(`http://127.0.0.1:${server.address().port}/harness`);
  await page.evaluate(async inventory => {
    const {createUnitPanel, createUnitPicker} = await import('/platform/web/unit-panel.js');
    window.calls = [];
    window.pressed = false;
    window.commands = [];
    const attachment = {id: 'button1', unit_id: 'button', port_id: 'port-a', initial: {pressed: true}};
    window.session = {session_id: 'test-fixture', device_id: 'cores3', state: 'running', units: [attachment]};
    window.api = async (path, options = {}) => {
      window.calls.push({path, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : null});
      if (path.startsWith('/api/v1/units')) return inventory;
      if (options.method === 'POST') window.pressed = JSON.parse(options.body).values.pressed;
      return {source: window.session.state === 'running' ? 'live' : 'persisted', units: [{...attachment, available: true, errors: {}, properties: {pressed: window.pressed, 'input-level': Number(!window.pressed)}}]};
    };
    const shell = {attachUnit: async () => ({}), detachUnit: () => {}, applyVisualState: values => window.commands.push(...values)};
    window.panel = await createUnitPanel(document.querySelector('#panel'), {session: window.session, shell, api: window.api});
    window.picker = await createUnitPicker(document.querySelector('#picker'), {api: window.api, deviceId: 'cores3'});
  }, inventory);
  assert.equal(await page.locator('.unit-values dd').first().textContent(), 'false', 'readback must override initial=true');
  const button = page.locator('.unit-control button');
  await button.hover();
  await page.mouse.down();
  await page.waitForFunction(() => window.pressed === true);
  // A second independent source must not be released by the first source.
  await page.evaluate(() => window.panel.handleInput({id: 'grove/press', kind: 'button', action: 'down', source: 'pointer-2'}));
  await page.mouse.up();
  assert.equal(await page.evaluate(() => window.pressed), true);
  await page.evaluate(() => window.panel.handleInput({id: 'grove/press', kind: 'button', action: 'up', source: 'pointer-2'}));
  await page.waitForFunction(() => window.pressed === false);
  const posts = await page.evaluate(() => window.calls.filter(call => call.method === 'POST').map(call => call.body));
  assert.deepEqual(posts, [{id: 'button1', values: {pressed: true}}, {id: 'button1', values: {pressed: false}}]);
  assert.equal(await page.evaluate(() => window.commands.at(-1).pressed), false);
  assert.equal(await page.locator('#unitModelSelect option[value="pir"]').isDisabled(), true, 'unimplemented Unit cannot be selected');
  await button.hover();
  await page.mouse.down();
  await page.waitForFunction(() => window.pressed === true);
  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  await page.waitForFunction(() => window.pressed === false);
  await page.mouse.up();
  await page.screenshot({path: `${output}/unit-panel.png`});
  await page.evaluate(() => { window.session.state = 'stopped'; window.panel.updateSession(window.session); });
  assert.equal(await button.isDisabled(), true);
  const before = await page.evaluate(() => { window.panel.dispose(); window.picker.dispose(); return window.calls.length; });
  await page.waitForTimeout(1100);
  assert.equal(await page.evaluate(() => window.calls.length), before, 'disposed panel must stop polling');

  await page.evaluate(async inventory => {
    const {createUnitPanel} = await import('/platform/web/unit-panel.js');
    window.makeFlashing = async () => {
      window.panel?.dispose();
      window.flashPolls = 0;
      window.flashReady = false;
      window.flashSession = {session_id: 'flashing-fixture', device_id: 'cores3', state: 'flashing', units: [{id: 'flash-button', unit_id: 'button', port_id: 'port-a'}]};
      const api = async path => {
        if (path.startsWith('/api/v1/units')) return inventory;
        window.flashPolls += 1;
        return {source: 'live', definitions: inventory.units, units: [{...window.flashSession.units[0], available: window.flashReady, errors: {}, properties: {pressed: window.flashReady}}]};
      };
      window.panel = await createUnitPanel(document.querySelector('#panel'), {session: window.flashSession, shell: null, api});
    };
    await window.makeFlashing();
  }, inventory);
  assert.equal(await page.locator('[data-unit-id="flash-button"] button').isDisabled(), true);
  await page.waitForTimeout(650);
  assert.equal(await page.evaluate(() => window.flashPolls), 1, 'flashing must not start active polling');
  await page.evaluate(() => window.panel.updateSession({...window.flashSession, state: 'booting'}));
  await page.waitForFunction(() => window.flashPolls >= 2);
  assert.equal(await page.locator('[data-unit-id="flash-button"] button').isDisabled(), true);
  assert.equal(await page.evaluate(() => {
    const timer = window.panel.timer;
    window.panel.updateSession({...window.flashSession, state: 'booting'});
    return window.panel.timer === timer;
  }), true, 'active updates must preserve the existing poll deadline');
  await page.evaluate(() => { window.flashReady = true; window.panel.updateSession({...window.flashSession, state: 'running'}); });
  await page.waitForFunction(() => !document.querySelector('[data-unit-id="flash-button"] button').disabled && document.querySelector('[data-unit-values] dd').textContent === 'true');
  await page.evaluate(() => window.panel.updateSession({...window.flashSession, state: 'stopped'}));
  const stoppedPolls = await page.evaluate(() => window.flashPolls);
  await page.waitForTimeout(650);
  assert.equal(await page.evaluate(() => window.flashPolls), stoppedPolls);
  await page.evaluate(async () => { await window.makeFlashing(); window.flashReady = true; window.panel.updateSession({...window.flashSession, state: 'running'}); });
  await page.waitForFunction(() => window.flashPolls >= 2 && !document.querySelector('[data-unit-id="flash-button"] button').disabled);
  await page.evaluate(() => window.panel.dispose());

  await page.evaluate(async inventory => {
    const {createUnitPanel, createUnitPicker} = await import('/platform/web/unit-panel.js');
    window.rejections = [];
    window.addEventListener('unhandledrejection', event => window.rejections.push(String(event.reason)));
    window.makeScenario = async ({attachments, delayPosts = false, detachFailure = null} = {}) => {
      window.panel?.dispose();
      const definitions = structuredClone(inventory.units);
      const button = definitions.find(unit => unit.id === 'button');
      button.name = '冻结按键合同';
      button.inputs['frozen-only'] = {type: 'integer', label: '冻结字段', minimum: 0, maximum: 10};
      button.runtime.inputs['frozen-only'] = {property: 'frozen-only'};
      const live = structuredClone(inventory);
      const liveButton = live.units.find(unit => unit.id === 'button');
      liveButton.name = 'LIVE WRONG';
      liveButton.inputs = {'live-only': {type: 'number'}};
      liveButton.runtime.inputs = {'live-only': {property: 'live-only'}};
      const value = schema => schema.default !== undefined ? structuredClone(schema.default) : schema.type === 'boolean' ? false : schema.type === 'array' ? Array.from({length: schema.maxItems || schema.minItems || 0}, () => schema.items?.type === 'boolean' ? false : 0) : schema.type === 'string' ? '' : 0;
      const all = attachments || definitions.map(unit => ({id: `u-${unit.id}`, unit_id: unit.id, port_id: 'port-a', visual_port: `fixture-${unit.id}`}));
      window.fixtureState = new Map(all.map(attachment => {
        const definition = definitions.find(unit => unit.id === attachment.unit_id);
        return [attachment.id, {...attachment, available: true, errors: {}, properties: Object.fromEntries([...Object.entries(definition.inputs), ...Object.entries(definition.outputs)].map(([field, schema]) => [field, value(schema)]))}];
      }));
      window.fixtureCalls = [];
      window.postWaiters = [];
      window.delayPosts = delayPosts;
      window.attachOrder = [];
      window.detachCalls = [];
      window.fixtureCommands = [];
      const payload = () => ({source: 'live', units: [...window.fixtureState.values()].map(unit => structuredClone(unit)), definitions});
      window.fixtureApi = async (path, options = {}) => {
        if (path.startsWith('/api/v1/units')) return live;
        if (options.method === 'POST') {
          const body = JSON.parse(options.body);
          window.fixtureCalls.push(body);
          if (window.delayPosts) await new Promise(resolve => window.postWaiters.push(resolve));
          Object.assign(window.fixtureState.get(body.id).properties, body.values);
        }
        return payload();
      };
      window.fixtureShell = {
        async attachUnit(unit, {port}) { window.attachOrder.push({unit, port}); return {}; },
        detachUnit(port) {
          window.detachCalls.push(port);
          if (detachFailure === 'sync') throw new Error('disposed renderer');
          if (detachFailure === 'async') return Promise.reject(new Error('disposed renderer'));
        },
        applyVisualState(commands) { window.fixtureCommands.push(...commands); },
      };
      window.fixtureSession = {session_id: 'frozen-fixture', device_id: 'cores3', state: 'running', units: all};
      window.panel = await createUnitPanel(document.querySelector('#panel'), {session: window.fixtureSession, shell: window.fixtureShell, api: window.fixtureApi});
      clearTimeout(window.panel.timer);
      return all;
    };
    await window.makeScenario();
  }, inventory);
  assert.equal(await page.locator('.unit-card').count(), 27, 'all 27 schema families render');
  assert.ok((await page.locator('[data-unit-id="u-button"] h4').textContent()).includes('冻结按键合同'));
  assert.equal(await page.locator('[data-unit-id="u-button"] [data-input-field="frozen-only"]').count(), 1);
  assert.equal(await page.locator('[data-input-field="live-only"]').count(), 0, 'live catalog must not replace frozen contract');
  assert.equal(await page.locator('[data-unit-id="u-cardkb"] [data-press-field="keys"]').count(), 50);
  assert.equal(await page.locator('[data-unit-id="u-8encoder"] [data-press-field="pressed"]').count(), 8);
  assert.equal(await page.locator('[data-unit-id="u-8encoder"] textarea[data-input-field="counters"]').count(), 1);
  assert.equal(await page.locator('[data-unit-id="u-thermal"] textarea[data-input-field="eeprom-hex"]').count(), 1);
  assert.equal(await page.locator('[data-unit-id="u-pir"] input[type="checkbox"]').count(), 1);
  assert.equal(await page.locator('[data-unit-id="u-8encoder"] [data-unit-rgb]').count(), 9, 'electrical LED order remains visible without a guessed physical mapping');
  await page.evaluate(() => window.panel.apply({source: 'live', units: [{id: 'u-key', unit_id: 'key', available: true, errors: {}, properties: {pressed: false, 'led-rgb': 0x123456}}]}));
  assert.equal(await page.locator('[data-unit-id="u-key"] [data-unit-rgb="0"]').getAttribute('aria-label'), 'LED[0] #123456');
  assert.deepEqual(await page.locator('[data-unit-id="u-key"] .unit-value-source').allTextContents(), ['输入 fixture', '固件输出观测']);
  assert.equal(await page.evaluate(() => window.fixtureCalls.length), 0, 'output color rendering cannot emit a runtime input');
  await page.evaluate(async () => {
    window.panel.apply({source: 'live', units: [{id: 'u-fan', unit_id: 'fan', available: true, errors: {}, properties: {'duty-pct': 50, 'frequency-hz': 1000}}]});
    window.panel.updateSession({...window.fixtureSession, state: 'stopped'});
  });
  assert.equal(await page.evaluate(() => window.fixtureCommands.filter(command => command.type === 'drive-activity').at(-1).active), false, 'terminal state stops a positive last PWM snapshot');
  await page.evaluate(async () => {
    window.panel.updateSession(window.fixtureSession);
    const api = window.panel.api;
    window.panel.api = async () => { throw new Error('offline fixture'); };
    await window.panel.refresh();
    window.panel.api = api;
  });
  assert.equal(await page.evaluate(() => window.fixtureCommands.filter(command => command.type === 'drive-activity').at(-1).active), false, 'transport failure stops activity instead of displaying stale motion');
  await page.evaluate(async () => { await window.panel.refresh(); clearTimeout(window.panel.timer); });
  const expectedFields = units.flatMap(unit => Object.keys(profiles[unit.id]?.inputs || {}).map(field => ({unit: unit.id, field})));
  for (const {unit, field} of expectedFields) {
    assert.ok(await page.locator(`[data-unit-id="u-${unit}"] [data-input-field="${field}"], [data-unit-id="u-${unit}"] [data-press-field="${field}"]`).count(), `${unit}.${field} must have a schema control`);
  }

  await page.evaluate(() => { window.delayPosts = true; });
  const q = page.locator('#unit-u-cardkb-keys-13');
  const a = page.locator('#unit-u-cardkb-keys-25');
  await q.dispatchEvent('pointerdown', {pointerId: 10});
  await a.dispatchEvent('pointerdown', {pointerId: 11});
  await page.evaluate(() => window.panel.handleInput({id: 'fixture-cardkb/key-q', kind: 'button', action: 'down', source: 'other-pointer'}));
  await q.dispatchEvent('pointerup', {pointerId: 10});
  assert.equal(await q.getAttribute('aria-pressed'), 'true', 'independent shell source keeps the same key held');
  await page.evaluate(() => window.panel.handleInput({id: 'fixture-cardkb/key-q', kind: 'button', action: 'up', source: 'other-pointer'}));
  await a.dispatchEvent('pointercancel', {pointerId: 11});
  assert.equal(await page.evaluate(() => window.fixtureCalls.length), 1, 'array updates remain serialized behind the first request');
  await page.evaluate(async () => {
    window.delayPosts = false;
    window.postWaiters.splice(0).forEach(resolve => resolve());
    await Promise.all(window.panel.queues.values());
  });
  const cardPosts = await page.evaluate(() => window.fixtureCalls.filter(call => call.id === 'u-cardkb'));
  assert.equal(cardPosts.length, 4);
  assert.equal(cardPosts[0].values.keys[13], true);
  assert.equal(cardPosts[1].values.keys[13], true, 'second pending key update preserves the first held key');
  assert.equal(cardPosts[1].values.keys[25], true);
  assert.equal(cardPosts[2].values.keys[13], false);
  assert.equal(cardPosts[2].values.keys[25], true);
  assert.ok(cardPosts[3].values.keys.every(value => value === false));
  assert.equal(await page.evaluate(() => window.fixtureState.get('u-cardkb').properties.keys.some(Boolean)), false);

  const ch1 = page.locator('#unit-u-8encoder-pressed-0');
  const ch8 = page.locator('#unit-u-8encoder-pressed-7');
  await ch1.dispatchEvent('pointerdown', {pointerId: 20});
  await ch8.dispatchEvent('pointerdown', {pointerId: 21});
  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  await page.evaluate(() => Promise.all(window.panel.queues.values()));
  const channelPosts = await page.evaluate(() => window.fixtureCalls.filter(call => call.id === 'u-8encoder'));
  assert.ok(channelPosts[1].values.pressed[0] && channelPosts[1].values.pressed[7]);
  assert.ok(channelPosts.at(-1).values.pressed.every(value => value === false), 'blur releases every owned channel');
  await ch1.dispatchEvent('pointerdown', {pointerId: 30});
  await page.evaluate(() => Promise.all(window.panel.queues.values()));
  await page.evaluate(() => window.panel.apply({source: 'live', units: [{id: 'u-8encoder', unit_id: '8encoder', available: true, errors: {}, properties: {pressed: Array(8).fill(false)}}]}));
  await ch8.dispatchEvent('pointerdown', {pointerId: 31});
  await page.evaluate(() => Promise.all(window.panel.queues.values()));
  assert.equal(await page.evaluate(() => window.fixtureCalls.at(-1).values.pressed[0]), true, 'a stale GET after an ACK must not clear another locally held key');
  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  await page.evaluate(() => Promise.all(window.panel.queues.values()));
  const arrayInput = page.locator('[data-unit-id="u-8encoder"] textarea[data-input-field="counters"]');
  const postsBeforeInvalid = await page.evaluate(() => window.fixtureCalls.length);
  await arrayInput.fill('[1]');
  await arrayInput.dispatchEvent('change');
  assert.equal(await page.evaluate(() => window.fixtureCalls.length), postsBeforeInvalid, 'invalid array shape must not reach API');
  await arrayInput.fill('[1,-2,3,4,5,6,7,8]');
  await arrayInput.dispatchEvent('change');
  await page.evaluate(() => Promise.all(window.panel.queues.values()));
  assert.deepEqual(await page.evaluate(() => window.fixtureState.get('u-8encoder').properties.counters), [1, -2, 3, 4, 5, 6, 7, 8]);

  // A shared-bus HUB must mount before its children even if the API order is
  // different. Its normalized nested paths route inputs to the leaf Unit.
  await page.evaluate(async () => {
    await window.makeScenario({detachFailure: 'async', attachments: [
      {id: 'leaf2', unit_id: 'encoder', parent_id: 'hub1', port_id: 'grove-2', visual_port: 'grove/grove-2'},
      {id: 'hub1', unit_id: 'hub', port_id: 'port-a', visual_port: 'grove'},
      {id: 'leaf1', unit_id: 'cardkb', parent_id: 'hub1', port_id: 'grove-1', visual_port: 'grove/grove-1'},
    ]});
  });
  assert.deepEqual(await page.evaluate(() => window.attachOrder), [
    {unit: 'hub', port: 'grove'}, {unit: 'encoder', port: 'grove/grove-2'}, {unit: 'cardkb', port: 'grove/grove-1'},
  ]);
  await page.evaluate(async () => {
    window.panel.handleInput({id: 'grove/grove-1/key-q', kind: 'button', action: 'down', source: 'nested-pointer'});
    await Promise.all(window.panel.queues.values());
    await window.panel.setShell(null);
    await Promise.all(window.panel.queues.values());
  });
  assert.equal(await page.evaluate(() => window.fixtureCalls.at(-1).id), 'leaf1');
  assert.ok(await page.evaluate(() => window.fixtureCalls.at(-1).values.keys.every(value => value === false)));
  assert.equal(await page.evaluate(() => window.panel.mounted.size), 0);
  assert.equal(await page.evaluate(() => window.detachCalls.at(-1)), 'grove', 'children must release before the parent HUB');
  await page.evaluate(async () => {
    const shell = {attachUnit: () => new Promise(resolve => { window.finishAttach = resolve; }), detachUnit: () => { throw new Error('already disposed'); }, applyVisualState() {}};
    const pending = window.panel.setShell(shell);
    await Promise.resolve();
    await window.panel.setShell(null);
    window.finishAttach({});
    await pending;
  });
  assert.equal(await page.evaluate(() => window.panel.mounted.size), 0, 'stale async attachment cannot reclaim a released shell');
  assert.equal(await page.evaluate(() => window.panel.attaching.size), 0);
  await page.evaluate(() => window.panel.dispose());
  await page.waitForTimeout(30);
  assert.deepEqual(await page.evaluate(() => window.rejections), [], 'sync and async disposed-renderer errors are contained');

  // Each deferred API response is explicitly released; no timing sleeps choose
  // the race ordering. Snapshots are captured before the GET's response gate.
  await page.evaluate(async inventory => {
    const {createUnitPanel} = await import('/platform/web/unit-panel.js');
    window.fixtureInventory = inventory;
    window.makeRaceScenario = async () => {
      window.panel?.dispose();
      const attachment = {id: 'race-button', unit_id: 'button', port_id: 'port-a', visual_port: 'grove'};
      const r = {calls: [], observations: [], gates: {GET: [], POST: []}, values: new Map([['race-a', false], ['race-b', false]])};
      r.session = session_id => ({session_id, device_id: 'cores3', state: 'running', units: [attachment]});
      r.payload = session_id => ({session_id, source: 'live', definitions: inventory.units, units: [{...attachment, available: true, errors: {}, properties: {pressed: r.values.get(session_id)}}]});
      r.gate = method => {
        let resolve, reject, start;
        const gate = {promise: new Promise((yes, no) => { resolve = yes; reject = no; }), started: new Promise(yes => { start = yes; }), resolve: () => resolve(), reject: () => reject(new Error('deferred old request')), start: () => start()};
        r.gates[method].push(gate);
        return gate;
      };
      const api = async (path, options = {}) => {
        if (path.startsWith('/api/v1/units')) return inventory;
        const sid = decodeURIComponent(path.split('/')[4]);
        const method = options.method || 'GET';
        const body = options.body ? JSON.parse(options.body) : null;
        r.calls.push({sid, method, body});
        const snapshot = r.payload(sid);
        const gate = r.gates[method].shift();
        if (gate) { gate.start(); await gate.promise; }
        if (method === 'POST') {
          r.values.set(sid, body.values.pressed);
          return r.payload(sid);
        }
        return snapshot;
      };
      const shell = {async attachUnit() { return {}; }, detachUnit() {}, applyVisualState() {}, updateUnitAnnotation(unit) { r.observations.push(structuredClone(unit)); }};
      r.panel = window.panel = await createUnitPanel(document.querySelector('#panel'), {session: r.session('race-a'), shell, api});
      clearTimeout(r.panel.timer);
      r.drain = async () => { await Promise.all(r.panel.queues.values()); clearTimeout(r.panel.timer); };
      r.read = () => ({state: structuredClone(r.panel.states.get('race-button')), text: document.querySelector('[data-unit-values]')?.textContent, note: document.querySelector('[data-unit-note]')?.textContent, observed: r.observations.at(-1)?.properties.pressed});
      window.race = r;
    };
  }, inventory);
  for (const startedDuringPost of [false, true]) {
    await page.evaluate(async startedDuringPost => {
      await window.makeRaceScenario();
      const r = window.race;
      let post, postGate;
      if (startedDuringPost) {
        postGate = r.gate('POST');
        post = r.panel.send('race-button', {pressed: true});
        await postGate.started;
      }
      const getGate = r.gate('GET');
      const get = r.panel.refresh();
      await getGate.started;
      if (postGate) postGate.resolve();
      else post = r.panel.send('race-button', {pressed: true});
      await post;
      r.beforeLateGet = r.read();
      getGate.resolve();
      await get;
      clearTimeout(r.panel.timer);
    }, startedDuringPost);
    assert.equal(await page.evaluate(() => window.race.beforeLateGet.state.properties.pressed), true, 'POST response must provide the actual controller observation');
    const result = await page.evaluate(() => window.race.read());
    assert.equal(result.state.properties.pressed, true, `late GET started ${startedDuringPost ? 'during' : 'before'} POST must not roll controller readback back`);
    assert.equal(result.observed, true, 'shell annotations retain the confirmed observation');
    assert.ok(result.text.includes('true'), 'DOM retains the confirmed observation');
  }
  for (const ending of ['success', 'error', 'same-id-reused', 'init', 'init-during-input']) {
    await page.evaluate(async ending => {
      await window.makeRaceScenario();
      const r = window.race, gate = r.gate('GET');
      const old = ending.startsWith('init') ? r.panel.init() : r.panel.refresh();
      await gate.started;
      if (ending !== 'init-during-input') r.panel.updateSession(r.session('race-b'));
      if (ending === 'same-id-reused') r.panel.updateSession(r.session('race-a'));
      r.values.set(r.panel.session.session_id, true);
      if (ending === 'init-during-input') await r.panel.send('race-button', {pressed: true});
      else await r.panel.refresh();
      r.newSessionSnapshot = r.read();
      if (ending === 'error') gate.reject(); else gate.resolve();
      await old;
      clearTimeout(r.panel.timer);
    }, ending);
    const result = await page.evaluate(() => window.race.read());
    assert.equal(result.state.properties.pressed, true, `${ending}: old session response must not change the current observation`);
    assert.equal(result.state.available, true, `${ending}: old failure must not disable current controls`);
    assert.deepEqual(result, await page.evaluate(() => window.race.newSessionSnapshot), `${ending}: old request must not alter states, DOM, notes or annotations`);
  }
  await page.evaluate(async () => {
    await window.makeRaceScenario();
    const r = window.race, gate = r.gate('POST');
    const inFlight = r.panel.send('race-button', {pressed: true});
    await gate.started;
    const queued = r.panel.send('race-button', {pressed: false});
    r.panel.updateSession(r.session('race-b'));
    await r.panel.refresh();
    await r.panel.send('race-button', {pressed: true});
    r.newSessionSnapshot = r.read();
    gate.resolve();
    await Promise.all([inFlight, queued]);
    clearTimeout(r.panel.timer);
  });
  assert.deepEqual(await page.evaluate(() => window.race.calls.filter(call => call.method === 'POST').map(call => ({sid: call.sid, pressed: call.body.values.pressed}))), [{sid: 'race-a', pressed: true}, {sid: 'race-b', pressed: true}], 'ordinary queued input is discarded when its session is replaced');
  assert.deepEqual(await page.evaluate(() => window.race.read()), await page.evaluate(() => window.race.newSessionSnapshot), 'old in-flight POST cannot replace new session readback');
  await page.evaluate(async () => {
    await window.makeRaceScenario();
    const r = window.race;
    r.panel.setPressed('race-button', 'fixture', true);
    await r.drain();
    const gate = r.gate('POST');
    const inFlight = r.panel.send('race-button', {pressed: true});
    await gate.started;
    const send = r.panel.send.bind(r.panel);
    r.panel.send = (...args) => {
      const promise = send(...args);
      if (args[2]) r.originalRelease = promise;
      return promise;
    };
    r.panel.updateSession(r.session('race-b'));
    await r.panel.refresh();
    await r.panel.send('race-button', {pressed: true});
    r.newSessionSnapshot = r.read();
    gate.resolve();
    await Promise.all([inFlight, r.originalRelease]);
    clearTimeout(r.panel.timer);
  });
  assert.deepEqual(await page.evaluate(() => window.race.calls.filter(call => call.method === 'POST').map(call => ({sid: call.sid, pressed: call.body.values.pressed}))), [{sid: 'race-a', pressed: true}, {sid: 'race-a', pressed: true}, {sid: 'race-b', pressed: true}, {sid: 'race-a', pressed: false}], 'session replacement preserves the necessary release at the original sid');
  assert.equal(await page.evaluate(() => window.race.values.get('race-a')), false);
  assert.equal(await page.evaluate(() => window.race.values.get('race-b')), true);
  assert.deepEqual(await page.evaluate(() => window.race.read()), await page.evaluate(() => window.race.newSessionSnapshot), 'original-session release cannot overwrite replacement-session readback');
  await page.evaluate(async () => {
    await window.makeRaceScenario();
    const r = window.race;
    r.panel.setPressed('race-button', 'fixture', true);
    await r.drain();
    const failure = r.gate('POST');
    r.panel.setPressed('race-button', 'fixture', false);
    await failure.started;
    failure.reject();
    await r.drain();
    let unblock;
    const blocker = new Promise(resolve => { unblock = resolve; });
    r.panel.queues.set('race-button', blocker);
    await r.panel.refresh();
    const recovery = r.panel.queues.get('race-button');
    r.panel.updateSession(r.session('race-b'));
    await r.panel.refresh();
    unblock();
    await recovery;
    clearTimeout(r.panel.timer);
  });
  assert.equal(await page.evaluate(() => window.race.calls.filter(call => call.method === 'POST').length), 2, 'queued release recovery cannot dispatch into a replacement session');
  assert.equal(await page.evaluate(() => window.race.read().state.properties.pressed), false);
  await page.evaluate(async () => {
    await window.makeRaceScenario();
    const r = window.race;
    r.panel.setPressed('race-button', 'fixture', true);
    await r.drain();
    const gate = r.gate('POST');
    const inFlight = r.panel.send('race-button', {pressed: true});
    await gate.started;
    const queued = r.panel.send('race-button', {pressed: true});
    r.panel.dispose();
    const release = r.panel.queues.get('race-button');
    r.disposedState = structuredClone(r.panel.states.get('race-button'));
    gate.resolve();
    await Promise.all([inFlight, queued, release]);
  });
  assert.deepEqual(await page.evaluate(() => window.race.calls.filter(call => call.method === 'POST').map(call => ({sid: call.sid, pressed: call.body.values.pressed}))), [{sid: 'race-a', pressed: true}, {sid: 'race-a', pressed: true}, {sid: 'race-a', pressed: false}], 'dispose cancels ordinary queued inputs and preserves the necessary original-session release');
  assert.equal(await page.evaluate(() => window.race.values.get('race-a')), false, 'dispose release reaches its original controller fixture');
  assert.equal(await page.locator('#panel').textContent(), '', 'late responses cannot repopulate a disposed panel');
  assert.deepEqual(await page.evaluate(() => window.race.panel.states.get('race-button')), await page.evaluate(() => window.race.disposedState), 'late dispose release response cannot mutate disposed state');

  await page.evaluate(async () => {
    await window.makeRaceScenario();
    const r = window.race;
    r.originalSnapshot = r.read();
    r.mismatchedApplied = r.panel.apply({...r.payload('race-b'), source: 'persisted'});
  });
  assert.equal(await page.evaluate(() => window.race.mismatchedApplied), false, 'payload session id must match even when the caller omits an observed id');
  assert.deepEqual(await page.evaluate(() => window.race.read()), await page.evaluate(() => window.race.originalSnapshot), 'mismatched payload cannot change state, source, DOM or annotation');
  for (const delayedOld of [false, true]) {
    await page.evaluate(async delayedOld => {
      await window.makeRaceScenario();
      const r = window.race;
      r.mounts = []; r.detaches = [];
      let finishOld;
      const shell = {
        attachUnit(unit, {port}) {
          r.mounts.push({unit, port});
          if (delayedOld && r.mounts.length === 1) return new Promise(resolve => { finishOld = resolve; });
          return Promise.resolve({});
        },
        detachUnit(port) { r.detaches.push(port); }, applyVisualState() {},
      };
      const pending = r.panel.setShell(shell);
      if (delayedOld) await Promise.resolve(); else await pending;
      const attachment = {...r.session('race-b').units[0], unit_id: 'key'};
      r.panel.updateSession({...r.session('race-b'), units: [attachment]});
      r.panel.apply({session_id: 'race-b', source: 'live', definitions: window.fixtureInventory.units, units: [{...attachment, available: true, errors: {}, properties: {pressed: false, 'led-rgb': 0}}]});
      await Promise.resolve();
      if (finishOld) finishOld({});
      await pending;
      clearTimeout(r.panel.timer);
    }, delayedOld);
    assert.deepEqual(await page.evaluate(() => window.race.mounts), [{unit: 'button', port: 'grove'}, {unit: 'key', port: 'grove'}], 'same id and port remount the new session Unit model');
    assert.deepEqual(await page.evaluate(() => window.race.detaches), ['grove'], 'old pending attachment is detached before its replacement starts');
    assert.equal(await page.evaluate(() => window.race.panel.mounted.get('race-button')?.generation), await page.evaluate(() => window.race.panel.generation), 'late old same-shell attachment cannot reclaim the new port');
    assert.equal(await page.evaluate(() => window.race.panel.attaching.size), 0);
    await page.evaluate(() => window.race.panel.dispose());
  }

  await page.evaluate(async () => {
    window.picker.dispose();
    const {createUnitPicker} = await import('/platform/web/unit-panel.js');
    window.picker = await createUnitPicker(document.querySelector('#picker'), {api: window.api, deviceId: 'cores3'});
  });
  await page.locator('#unitModelSelect').selectOption('hub');
  await page.getByRole('combobox', {name: 'HUB · Grove 1', exact: true}).selectOption('env-iii');
  await page.getByRole('combobox', {name: 'HUB · Grove 2', exact: true}).selectOption('encoder');
  await page.getByRole('combobox', {name: 'HUB · Grove 3', exact: true}).selectOption('cardkb');
  assert.deepEqual(await page.evaluate(() => window.picker.attachments()), [
    {id: 'external1', unit_id: 'hub', port_id: 'port-a'},
    {id: 'external1-1', parent_id: 'external1', unit_id: 'env-iii', port_id: 'grove-1'},
    {id: 'external1-2', parent_id: 'external1', unit_id: 'encoder', port_id: 'grove-2'},
    {id: 'external1-3', parent_id: 'external1', unit_id: 'cardkb', port_id: 'grove-3'},
  ]);
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({width, height: 900});
    await page.evaluate(() => window.makeScenario());
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false, `no horizontal overflow at ${width}`);
    assert.equal(await page.getByRole('button', {name: 'backspace', exact: true}).count(), 1, 'full CardKB accessible key name is retained');
    const keyLayout = await page.locator('[data-unit-id="u-cardkb"] [data-press-field="keys"]').evaluateAll(keys => keys.map(key => ({index: Number(key.dataset.pressIndex), id: key.id, label: key.textContent, nowrap: getComputedStyle(key).whiteSpace === 'nowrap', fits: key.scrollWidth <= key.clientWidth})));
    assert.equal(keyLayout.length, 50);
    assert.ok(keyLayout.every((key, index) => key.index === index && key.id === `unit-u-cardkb-keys-${index}` && key.nowrap && key.fits), `CardKB key labels remain readable at ${width}`);
    await page.locator('[data-unit-id="u-cardkb"]').screenshot({path: `${output}/cardkb-${width}.png`});
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path: `${output}/all-units-${width}.png`, fullPage: true});
    await page.screenshot({path: `${output}/viewport-${width}.png`});
  }
  await page.evaluate(() => { window.panel.dispose(); window.picker.dispose(); });
  assert.deepEqual(errors, []);
  const source_sha256 = Object.fromEntries(await Promise.all(['platform/web/unit-panel.js', 'platform/web/unit-panel.css', 'platform/web/unit-visual-mappings.js', 'platform/tests/test_unit_panel.mjs', 'platform/units/catalog.json', 'platform/units/runtime-profiles.json'].map(async path => [path, createHash('sha256').update(await readFile(resolve(root, path))).digest('hex')])));
  await writeFile(`${output}/report.json`, JSON.stringify({category: 'browser-bridge-contract', status: 'PASS', captured_at: new Date().toISOString(), browser_version: browser.version(), source_sha256, checks: ['controller-readback-over-initial', 'multi-source-press-release', 'readback-animation-command', 'explicit-planned-picker', 'blur-release', 'terminal-controls-disabled', 'dispose-polling', 'frozen-session-schema-over-live-catalog', 'all-27-schema-forms', 'cardkb-50-and-encoder8-8-controls', 'pending-multikey-array-preservation', 'stale-readback-preserves-held-channels', 'get-before-post-late-snapshot-rejected', 'get-during-post-late-snapshot-rejected', 'old-session-get-success-and-error-fenced', 'payload-session-id-before-state-writes', 'reused-session-id-epoch-fenced', 'old-session-init-fenced', 'same-session-init-input-epoch-fenced', 'replacement-session-original-release-preserved', 'replacement-session-model-remount-and-old-async-attach-fenced', 'old-session-post-and-queued-input-fenced', 'queued-release-recovery-session-fenced', 'dispose-original-session-release-without-late-state-writes', 'observed-rgb-swatches-electrical-order', 'fan-terminal-and-transport-fail-closed', 'array-schema-validation', 'nested-hub-parent-first-input-routing', 'null-shell-release', 'async-attach-cancel', 'disposed-shell-sync-and-async-errors', 'hub-three-i2c-picker', 'responsive-1440-1024-768-390', 'cardkb-full-key-names-nowrap-no-text-overflow-all-viewports'], firmware_execution: 'NOT RUN', errors}, null, 2) + '\n');
  console.log('UNIT_PANEL_BROWSER_OK');
} catch (error) {
  const source_sha256 = Object.fromEntries(await Promise.all(['platform/web/unit-panel.js', 'platform/tests/test_unit_panel.mjs'].map(async path => [path, createHash('sha256').update(await readFile(resolve(root, path))).digest('hex')])));
  await writeFile(`${output}/report.json`, JSON.stringify({category: 'browser-bridge-contract', status: 'FAIL', captured_at: new Date().toISOString(), browser_version: browser.version(), source_sha256, firmware_execution: 'NOT RUN', error: error.stack, errors}, null, 2) + '\n');
  throw error;
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
