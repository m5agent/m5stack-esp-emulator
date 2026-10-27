// Actual UnitPanel/Picker DOM contracts using synthetic HTTP/controller fixtures.
// No Device Service, guest, QEMU, firmware, or physical hardware is started.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const mode = {type: 'boolean', default: true, creation_only: true,
  label: 'Flash 模式（取消为 Torch）', description: '创建时固定，运行中不可切换。'};
const unit = (id, bus = 'gpio', creation = false) => ({id, name: id, interface: {bus},
  inputs: creation ? {'flash-mode': mode} : {}, outputs: {},
  runtime: {status: 'implemented', hosts: ['cores3', 'sticks3'],
    inputs: creation ? {'flash-mode': {property: 'flash-mode', creation_only: true}} : {}}});
const inventory = {units: [unit('flashlight', 'gpio', true), unit('button'), unit('hub', 'i2c'), unit('synthetic-i2c', 'i2c', true)],
  hosts: ['cores3', 'sticks3'].map(device_id => ({device_id, ports: [{id: 'port-a', label: 'PORT.A', visual_port: 'grove',
    wiring_status: 'confirmed', physical_presence: 'main-device'}]}))};
const server = createServer(async (request, response) => {
  const pathname = new URL(request.url, 'http://localhost').pathname;
  if (pathname === '/harness') {
    response.setHeader('Content-Type', 'text/html; charset=utf-8');
    response.end('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"></head><body><main id="panel"></main><div id="picker"></div></body></html>');
    return;
  }
  const path = resolve(root, `.${decodeURIComponent(pathname)}`);
  if (!path.startsWith(root + '/')) { response.writeHead(403).end(); return; }
  try { response.setHeader('Content-Type', 'text/javascript'); response.end(await readFile(path)); }
  catch { response.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
const page = await browser.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(`http://127.0.0.1:${server.address().port}/harness`);
  await page.evaluate(async inventory => {
    const {createUnitPanel, createUnitPicker} = await import('/platform/web/unit-panel.js');
    const attachment = {id: 'lamp', unit_id: 'flashlight', port_id: 'port-a', initial: {'flash-mode': false}};
    window.session = {session_id: 'synthetic-u152-web', device_id: 'cores3', state: 'running', units: [attachment]};
    window.state = {...attachment, available: true, errors: {}, properties: {'output-known': true,
      'pad-synchronized': true, 'gpio-route-supported': true, 'flash-mode': true,
      'en-level': true, active: true, 'flash-level-pct': 70, 'timeout-ms': 1300}};
    window.payload = () => ({source: 'live', session_id: window.session.session_id,
      definitions: inventory.units, units: [structuredClone(window.state)]});
    window.commands = [];
    window.posts = [];
    const api = async (path, options = {}) => {
      if (options.method === 'POST') window.posts.push(JSON.parse(options.body));
      return path.startsWith('/api/v1/units') ? structuredClone(inventory) : window.payload();
    };
    const shell = {attachUnit: async () => ({}), detachUnit() {},
      applyVisualState(commands) {window.commands.push(...structuredClone(commands));}};
    window.panel = await createUnitPanel(document.querySelector('#panel'), {session: window.session, api, shell});
    clearTimeout(window.panel.timer);
    window.panel.schedule = () => {};
    window.picker = await createUnitPicker(document.querySelector('#picker'), {api, deviceId: 'cores3'});
  }, inventory);
  const lastCommand = () => page.evaluate(() => window.commands.at(-1));
  const unknown = {type: 'led', target: 'grove/light', known: false};
  const lamp = (on, brightness) => ({type: 'led', target: 'grove/light', color: 0xFFFAF0, on, brightness});
  assert.deepEqual(await lastCommand(), lamp(true, 0.7), 'actual readback wins over initial Torch request');
  assert.equal(await page.locator('#panel [data-input-field="flash-mode"]').count(), 0);
  assert.equal(await page.locator('#panel input, #panel select, #panel button').count(), 0, 'creation-only mode has no writable live control');
  assert.match(await page.locator('#panel [data-unit-creation-only="flash-mode"]').textContent(), /创建时固定，运行中只读/);
  await page.evaluate(() => {
    window.panel.enableControls();
    window.panel.updateSession({...window.session, state: 'stopped'});
    window.panel.updateSession(window.session);
    window.panel.handleInput({id: 'grove/mode', kind: 'button', action: 'down', position: 0, source: 'pointer'});
  });
  assert.equal(await page.locator('#panel input, #panel select, #panel button').count(), 0);
  assert.deepEqual(await page.evaluate(() => window.posts), []);
  for (const change of [
    {active: false}, // Expiry retains the 70%/1300ms decoded code.
    {'output-known': false},
    {'output-known': true, 'pad-synchronized': false},
    {'pad-synchronized': true, 'gpio-route-supported': false},
  ]) {
    await page.evaluate(change => {Object.assign(window.state.properties, change); window.panel.apply(window.payload());}, change);
    assert.deepEqual(await lastCommand(), Object.hasOwn(change, 'active') ? lamp(false, 0) : unknown);
  }
  await page.evaluate(() => {
    Object.assign(window.state.properties, {'output-known': true, 'pad-synchronized': true, 'gpio-route-supported': true,
      'flash-mode': false, 'en-level': true, active: true, 'flash-level-pct': 0, 'timeout-ms': 0});
    window.panel.apply(window.payload());
  });
  assert.deepEqual(await lastCommand(), lamp(true, 1), 'Torch continuous activity uses zero Flash code and no Flash timeout');
  await page.evaluate(() => window.panel.apply({...window.payload(), units: []}));
  assert.deepEqual(await lastCommand(), unknown, 'missing Unit in the next payload withdraws prior light');
  await page.evaluate(() => window.panel.apply(window.payload()));
  assert.deepEqual(await lastCommand(), lamp(true, 1));
  await page.evaluate(() => window.panel.withdrawPreview());
  assert.deepEqual(await lastCommand(), unknown, 'loss of current Run context withdraws prior light');

  const select = page.locator('#unitModelSelect');
  await select.selectOption('flashlight');
  const fixture = page.locator('#picker [data-creation-field="flash-mode"]');
  assert.equal(await fixture.isChecked(), true, 'schema default is an explicit creation choice');
  assert.deepEqual(await page.evaluate(() => window.picker.attachments('cores3')), [{id: 'external1', unit_id: 'flashlight', port_id: 'port-a', initial: {'flash-mode': true}}]);
  await fixture.uncheck();
  assert.deepEqual(await page.evaluate(() => window.picker.attachments('cores3')), [{id: 'external1', unit_id: 'flashlight', port_id: 'port-a', initial: {'flash-mode': false}}]);
  await select.selectOption('button');
  assert.equal(await fixture.count(), 0);
  assert.deepEqual(await page.evaluate(() => window.picker.attachments('cores3')), [{id: 'external1', unit_id: 'button', port_id: 'port-a'}]);
  await select.selectOption('flashlight');
  assert.equal(await fixture.isChecked(), true, 'switching Unit discards the old creation fixture');
  await select.selectOption('hub');
  await page.locator('select[aria-label="HUB · Grove 1"]').selectOption('synthetic-i2c');
  await fixture.uncheck();
  assert.deepEqual(await page.evaluate(() => window.picker.attachments('cores3')), [
    {id: 'external1', unit_id: 'hub', port_id: 'port-a'},
    {id: 'external1-1', parent_id: 'external1', unit_id: 'synthetic-i2c', port_id: 'grove-1', initial: {'flash-mode': false}},
  ]);
  await select.selectOption('button');
  assert.deepEqual(await page.evaluate(() => window.picker.attachments('cores3')), [{id: 'external1', unit_id: 'button', port_id: 'port-a'}], 'hidden HUB child fixture is not submitted for a different Unit');
  await page.evaluate(() => window.picker.loadDevice('sticks3'));
  assert.deepEqual(await page.evaluate(() => window.picker.attachments('sticks3')), [], 'switching device clears old fixtures and attachments');
  assert.equal(await fixture.count(), 0);
  await select.selectOption('flashlight');
  assert.equal(await fixture.isChecked(), true);
  assert.deepEqual(await page.evaluate(() => window.posts), [], 'picker configuration never posts live input');
  await page.evaluate(() => {window.panel.dispose(); window.picker.dispose();});
  assert.deepEqual(await lastCommand(), unknown, 'detach withdraws the observed appearance');
  assert.deepEqual(errors, []);
  console.log('FLASHLIGHT_UNIT_WEB_OK creation-fixture-picker-and-readonly-runtime; synthetic HTTP/controller fixtures; guest/hardware NOT RUN');
} finally {
  await page.close();
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
