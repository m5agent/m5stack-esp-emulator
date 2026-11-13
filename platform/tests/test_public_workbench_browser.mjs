// Default: browser contracts only. --real-browser-runtime explicitly runs the
// official PaperS3 guest in the exported WASM. No Device Service or hardware.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname, extname} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const {chromium} = await import(process.env.M5_WASM_NODE_MODULES
  ? pathToFileURL(resolve(process.env.M5_WASM_NODE_MODULES, 'playwright/index.mjs')).href : 'playwright');

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const site = resolve(process.env.M5_PUBLIC_SITE || resolve(repo, '.work/public-ux-contract-site'));
const out = process.env.M5_PUBLIC_UI_OUT || '/tmp/m5-public-workbench-browser';
const realBrowser = process.argv.includes('--real-browser-runtime');
const runtimeArgument = process.argv.indexOf('--runtime');
const runtimePath = resolve(
  runtimeArgument >= 0 ? process.argv[runtimeArgument + 1] : resolve(repo, '.work/browser-runtime'),
);
const firmwarePath = resolve(
  process.env.M5_PUBLIC_FIRMWARE || resolve(repo, '.work/public-firmware-fixtures/papers3-factory-v0.5.bin'),
);
const realFirmwareSha = 'd6733a0ca378f95335fa5fba4d4d992fb1dd97c17557b20e9aebfca08ba6d624';
const checkpoints = [];
const executedSourcePaths = [
  'platform/web/index.html',
  'platform/web/public.js',
  'platform/web/public.css',
  'platform/web/public-unit-assembly.js',
  'platform/web/unit-panel.js',
  'platform/web/public-session-controller.js',
  'platform/web/public-service-program.js',
  'platform/web/public-service.js',
  'platform/web/uiflow-cloud-status.js',
  'platform/web/model-shell.js',
  'platform/tests/test_public_workbench_browser.mjs',
];
const executedSourceHashes = Object.fromEntries(
  await Promise.all(
    executedSourcePaths.map(async (path) => [
      path,
      createHash('sha256')
        .update(await readFile(resolve(repo, path)))
        .digest('hex'),
    ]),
  ),
);
const exportedSourceHashes = Object.fromEntries(
  await Promise.all(
    executedSourcePaths.slice(0, -1).map(async (path) => [
      path,
      createHash('sha256')
        .update(await readFile(resolve(site, path)))
        .digest('hex'),
    ]),
  ),
);
const siteManifest = JSON.parse(await readFile(resolve(site, 'public-site-manifest.json'), 'utf8'));
const exportedAssets = new Set(siteManifest.assets.map(asset => asset.path));
for (const path of ['platform/units/catalog.json', 'platform/units/host-ports.json', 'platform/units/runtime-profiles.json'])
  assert.ok(exportedAssets.has(path), 'offline wiring contract must be part of the export closed set: ' + path);
let runtimeManifest;
if (realBrowser) {
  runtimeManifest = JSON.parse(await readFile(resolve(runtimePath, 'runtime.json'), 'utf8'));
  assert.equal(runtimeManifest.build.kind, 'source-build');
  assert.equal(
    createHash('sha256')
      .update(await readFile(firmwarePath))
      .digest('hex'),
    realFirmwareSha,
  );
}
await mkdir(out, {recursive: true});
const checks = [],
  pageErrors = [],
  requests = [], workers = [];
const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost');
  if (url.pathname === '/fixture/real.bin' && realBrowser) {
    response.writeHead(200, {'Content-Type': 'application/octet-stream'});
    response.end(await readFile(firmwarePath));
    return;
  }
  if (url.pathname === '/fixture/bad.bin') {
    response.writeHead(200, {'Content-Type': 'application/octet-stream'});
    response.end('THIS IS A BROWSER CONTRACT FIXTURE, NOT FIRMWARE');
    return;
  }
  if (url.pathname === '/fixture/slow.bin') {
    setTimeout(() => {
      response.writeHead(200, {'Content-Type': 'application/octet-stream'});
      response.end('late fixture');
    }, 1000);
    return;
  }
  if (!url.pathname.startsWith('/showcase/')) {
    response.writeHead(404).end();
    return;
  }
  const relative = decodeURIComponent(url.pathname.slice('/showcase/'.length)) || 'index.html';
  if (!exportedAssets.has(relative)) { response.writeHead(404).end(); return; }
  const file = resolve(site, relative);
  if (!file.startsWith(site + '/')) {
    response.writeHead(403).end();
    return;
  }
  try {
    response.setHeader(
      'Content-Type',
      {
        '.html': 'text/html; charset=utf-8',
        '.js': 'text/javascript',
        '.mjs': 'text/javascript',
        '.css': 'text/css',
        '.json': 'application/json',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.wasm': 'application/wasm',
      }[extname(file)] || 'application/octet-stream',
    );
    let content = await readFile(file);
    // Read-only observability of the actual page's controller; no state or
    // frame injection. Runtime execution and all input still use product UI.
    if (file.endsWith('/platform/web/public.js'))
      content = Buffer.concat([content, Buffer.from('\nwindow.__publicWorkbenchProbe = state;\n')]);
    response.end(content);
  } catch {
    response.writeHead(404).end();
  }
});
await new Promise((done) => server.listen(0, '127.0.0.1', done));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({
  executablePath:
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
});
const context = await browser.newContext({
  viewport: {width: 1440, height: 1000},
  permissions: ['clipboard-read', 'clipboard-write'],
});
const page = await context.newPage();
page.on('pageerror', (e) => pageErrors.push(e.message));
page.on('request', (r) => requests.push(r.url()));
page.on('worker', worker => workers.push(worker.url()));
const test = async (name, run) => {
  await run();
  checks.push(name);
};
try {
  const config = JSON.parse(await readFile(resolve(site, 'platform/web/site-config.json'), 'utf8'));
  if (!realBrowser) assert.equal(config.browser_board_execution, false, 'host contract uses an export without an executable runtime');
  const modelReady = async id => page.waitForFunction(id => document.querySelector('#deviceMount')?.dataset.deviceId === id
    && window.__publicWorkbenchProbe?.picker?.deviceId === id, id);
  const selectDevice = async id => {
    await page.locator('#deviceLibrary').evaluate(node => node.open = true);
    await page.locator(`#deviceNav button[data-device-id="${id}"]`).click(); await modelReady(id);
  };
  const unitReady = async id => page.waitForFunction(id => document.querySelector('#unitModelMount')?.dataset.unitId === id
    && window.__publicWorkbenchProbe?.unitShell?.device.id === id
    && !window.__publicWorkbenchProbe.unitShell.disposed, id);
  await test('first-visit-and-project-prefix-are-model-only-without-an-implicit-service', async () => {
    await page.goto(`${base}/showcase/?device=cores3&autostart=0`); await modelReady('cores3');
    assert.equal(await page.locator('#runtimeStatus').getAttribute('data-status'), 'model');
    assert.equal(await page.locator('#stageTitle').textContent(), 'CoreS3');
    assert.ok(await page.locator('#deviceNav [data-device-id]').count() >= 18);
    assert.equal(await page.locator('#deviceMount [data-model-source="m5stack-models"]').count(), 1);
    if (!realBrowser) assert.equal(await page.locator('#startBtn').isDisabled(), true);
    assert.equal(requests.some(url => /\/api\/v1(?:\/|\?|$)/.test(url)), false);
    assert.equal(requests.some(url => new URL(url).pathname.startsWith('/platform/')), false);
    for (const name of ['catalog', 'host-ports', 'runtime-profiles'])
      assert.ok(requests.some(url => new URL(url).pathname === `/showcase/platform/units/${name}.json`));
    assert.equal(await page.locator('#pythonRunBtn').isDisabled(), true);
    assert.equal(await page.locator('#pythonInterruptBtn').isDisabled(), true);
    assert.equal(await page.locator('#pythonSource').isDisabled(), false, 'source remains an editable local draft');
    assert.match(await page.locator('#serviceTokenHelp').textContent(), /本机同源连接无需 Token.*服务已配置 Token.*远程连接/);
    assert.equal(await page.locator('#serviceToken').getAttribute('aria-describedby'), 'serviceTokenHelp');
  });
  await test('one-page-navigation-never-opens-a-separate-console', async () => {
    const targets = ['#pythonHeading', '#unitAssemblyPanel', '#serviceSessions', '#firmwareHeading'];
    for (const href of targets) {
      const link = page.locator(`nav a[href="${href}"]`); assert.equal(await link.count(), 1);
      assert.equal(await link.getAttribute('target'), null); await link.click();
      assert.equal(new URL(page.url()).pathname, '/showcase/'); assert.equal(new URL(page.url()).hash, href);
    }
    assert.equal(await page.locator('nav [data-service-console]').count(), 0);
    assert.equal(requests.some(url => /\/api\/v1(?:\/|\?|$)/.test(url)), false);
  });
  await test('offline-unit-adds-to-main-host-and-retains-an-honest-capability-boundary', async () => {
    await page.locator('#unitExplorer').evaluate(node => node.open = true);
    await page.locator('#unitSearch').fill('U027');
    await page.locator('[data-unit-model="button"]').click();
    await unitReady('button');
    assert.equal(await page.locator('#unitDetails').getAttribute('open'), null);
    assert.equal(await page.locator('#unitModelMount canvas').count(), 1, 'Unit selection previews the real catalog model');
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.unitShell !== window.__publicWorkbenchProbe.shell), true);
    assert.equal(await page.locator('#unitModelMount [data-visual-only="true"]').count(), 1);
    assert.match(await page.locator('#unitPreviewNote').textContent(), /主机模型.*后端/);
    await page.locator('#addSelectedUnitBtn').click();
    await page.waitForFunction(() => window.__publicWorkbenchProbe.picker.attachments('cores3').some(row => row.unit_id === 'button')
      && window.__publicWorkbenchProbe.shell.model.port('grove').module?.meta.id === 'm5stack.unit.button.grove');
    assert.equal(await page.locator('#deviceMount canvas').count(), 1);
    assert.equal(await page.locator('#unitModelSelect').inputValue(), 'button');
    assert.match(await page.locator('.public-unit-assembly > p[role="status"]').textContent(), /草稿.*另行确认/);
    assert.equal(await page.locator('#startBtn').isDisabled(), true, 'offline wiring does not grant browser Unit execution');
    assert.equal(await page.locator('#capabilityTitle').textContent(),'所选 Unit 需要服务运行','auto/offline explains the actual Unit execution boundary');
    assert.equal(await page.locator('#pythonRunBtn').isDisabled(), true);
    await page.locator('#addSelectedUnitBtn').click();
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.picker.attachments().length), 1, 'Add locates an existing Unit without duplicating it');
    await page.locator('#unitDetails > summary').click(); assert.equal(await page.locator('#unitDetailBody').isVisible(), true);
    await page.locator('#unitDetails > summary').click();
    await page.locator('#unitSearch').fill('');
    await page.locator('[data-unit-filter="runtime"]').click();
    assert.equal(await page.locator('[data-unit-model]').count(), 0); assert.match(await page.locator('#unitResults').textContent(), /先连接服务/);
    await page.locator('[data-unit-filter="all"]').click();
  });
  await test('catalog-preview-disposal-and-reopen-never-change-the-host-draft', async () => {
    await page.evaluate(() => window.__previousUnitPreview = window.__publicWorkbenchProbe.unitShell);
    await page.locator('[data-unit-model="angle"]').click(); await unitReady('angle');
    assert.equal(await page.evaluate(() => window.__previousUnitPreview.disposed), true);
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.picker.attachments()[0].unit_id), 'button');
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.shell.model.port('grove').module.meta.id), 'm5stack.unit.button.grove');
    await page.evaluate(() => window.__previousUnitPreview = window.__publicWorkbenchProbe.unitShell);
    await page.locator('#unitExplorer').evaluate(node => node.open = false);
    await page.waitForFunction(() => window.__publicWorkbenchProbe.unitShell === null);
    assert.equal(await page.evaluate(() => window.__previousUnitPreview.disposed), true);
    assert.equal(await page.locator('#unitModelMount canvas').count(), 0);
    await page.locator('#unitExplorer').evaluate(node => node.open = true); await unitReady('angle');
    assert.equal(await page.evaluate(() => window.__previousUnitPreview !== window.__publicWorkbenchProbe.unitShell), true);
    assert.equal(await page.locator('#deviceMount canvas').count(), 1);
  });
  await test('late-catalog-model-load-cannot-replace-a-newer-unit-preview', async () => {
    let release, seen;
    const gate = new Promise(resolve => release = resolve), observed = new Promise(resolve => seen = resolve);
    const pattern = '**/vendor/m5stack-models/src/units/relay/index.js';
    await page.route(pattern, async route => { seen(); await gate; await route.continue(); });
    await page.evaluate(() => {
      const prototype = Object.getPrototypeOf(window.__publicWorkbenchProbe.unitShell), original = prototype.dispose;
      window.__staleRelayDisposed = 0;
      prototype.dispose = function(...args) {
        if (this.device.id === 'relay' && !this.disposed) window.__staleRelayDisposed++;
        return original.apply(this, args);
      };
    });
    await page.locator('[data-unit-model="relay"]').click();
    let timer;
    try {
      await Promise.race([observed, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Relay model request was not observed')), 10000); })]);
    } finally { clearTimeout(timer); }
    await page.locator('[data-unit-model="button"]').click(); await unitReady('button');
    release(); await page.waitForFunction(() => window.__staleRelayDisposed === 1);
    await page.unroute(pattern);
    assert.equal(await page.locator('#unitModelMount').getAttribute('data-unit-id'), 'button');
    assert.equal(await page.locator('#unitModelMount canvas').count(), 1);
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.unitShell.device.id), 'button');
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.picker.attachments()[0].unit_id), 'button');
    assert.equal(requests.some(url => /\/api\/v1(?:\/|\?|$)/.test(url)), false);
  });
  await test('device-selection-preserves-only-its-own-unit-draft', async () => {
    await page.evaluate(() => window.__sameCatalogPreview = window.__publicWorkbenchProbe.unitShell);
    await selectDevice('atoms3-lite'); assert.deepEqual(await page.evaluate(() => window.__publicWorkbenchProbe.picker.attachments()), []);
    assert.equal(await page.evaluate(() => window.__sameCatalogPreview === window.__publicWorkbenchProbe.unitShell), true);
    assert.match(await page.locator('#unitPreviewNote').textContent(), /AtomS3 Lite/);
    assert.equal(await page.locator('#unitCapability').textContent(), '运行能力待确认');
    if (!realBrowser) assert.equal(await page.locator('#startBtn').isDisabled(), true);
    await selectDevice('cores3');
    await page.waitForFunction(() => window.__publicWorkbenchProbe.shell.model.port('grove').module?.meta.id === 'm5stack.unit.button.grove');
    assert.equal(await page.locator('#unitModelSelect').inputValue(), 'button');
    assert.match(await page.locator('#unitPreviewNote').textContent(), /CoreS3/);
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.run), null);
  });
  await test('responsive-main-host-assembly-has-no-overflow-at-four-widths', async () => {
    await page.locator('#unitExplorer').evaluate(node => node.open = true); await unitReady('button');
    for (const width of [1440, 1024, 768, 390]) {
      await page.setViewportSize({width, height:1000}); await page.waitForTimeout(150);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `no horizontal overflow at ${width}`);
      assert.equal(await page.locator('#startBtn').count(), 1);
      assert.equal(await page.locator('#deviceMount canvas').count(), 1);
      assert.equal(await page.locator('#unitModelMount canvas').count(), 1);
      const bounds = await page.locator('#unitModelMount canvas').boundingBox();
      assert.ok(bounds.width > 100 && bounds.height > 100, `independent Unit preview remains visible at ${width}`);
      await page.screenshot({path:`${out}/public-${width}.png`, fullPage:true});
      await page.locator('#unitModelMount').screenshot({path:`${out}/unit-preview-${width}.png`});
    }
    await page.setViewportSize({width:1440, height:1000});
  });
  await test('device-alias-and-share-never-forward-credentials', async () => {
    await page.evaluate(() => {
      const preview = window.__publicWorkbenchProbe.unitShell, original = preview.dispose.bind(preview);
      localStorage.removeItem('unit-preview-pagehide-disposed');
      preview.dispose = (...args) => { const result = original(...args); localStorage.setItem('unit-preview-pagehide-disposed', String(preview.disposed)); return result; };
    });
    await page.goto(`${base}/showcase/?device=m5papers3&autostart=0&token=ignored-secret`); await modelReady('papers3');
    assert.equal(await page.evaluate(() => localStorage.getItem('unit-preview-pagehide-disposed')), 'true');
    assert.equal(await page.locator('#stageTitle').textContent(), 'PaperS3');
    assert.match(await page.locator('#launchNotice').textContent(), /凭据参数已忽略/);
    if (!realBrowser) assert.equal(await page.locator('#startBtn').isDisabled(), true);
    await page.locator('#shareBtn').click(); const url = new URL(await page.evaluate(() => navigator.clipboard.readText()));
    assert.equal(url.pathname, '/showcase/'); assert.equal(url.searchParams.get('device'), 'papers3');
    assert.equal(url.searchParams.has('token'), false); assert.equal(url.href.includes('ignored-secret'), false);
  });
  await test('four-controller-model-links-use-the-pinned-3d-shells', async () => {
    for (const id of ['paperdiy','papers3','cardputer','corematrix']) {
      await page.goto(`${base}/showcase/?device=${id}&mode=model&autostart=0`);
      await modelReady(id);
      assert.equal(await page.locator(`#deviceMount [data-renderer="${id}-three"]`).count(), 1);
      assert.match(await page.locator('#startBtn').textContent(), /浏览设备模型/);
      assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.run), null);
    }
  });
  const [unitCatalog, hostPorts, runtimeProfiles] = await Promise.all(['catalog','host-ports','runtime-profiles'].map(name =>
    readFile(resolve(site, `platform/units/${name}.json`), 'utf8').then(JSON.parse)));
  const serviceFixture = {units:unitCatalog.units.map(unit => ({...unit, runtime:runtimeProfiles.units[unit.id] || {}})), hosts:hostPorts.hosts};
  const originalService = 'https://original-service.public.invalid/device-center',
    candidateService = 'https://candidate-service.public.invalid/replacement';
  let candidateMode = 'invalid', candidateUnitReads = 0, fixtureSessions = [], serviceCalls = [], delayedSession = null, fixtureSerial = null, delayedSessionList = null, sessionListFailure = false;
  let fixtureCloudStartup = false, fixtureCreates = [];
  const cloudStatusFixture = {source:'guest-pcap',state:'observed',pairing:{state:'code_received'},
    webrepl:{state:'identity_rejected',reason:'mac_not_bound',handshakes:1,disconnects:1},observation:{status:'complete'}};
  const fixtureResponse = async (route, candidate = false) => {
    const url = new URL(route.request().url()), method = route.request().method();
    serviceCalls.push({candidate, method, path:url.pathname});
    if (candidate && !url.pathname.endsWith('/devices')) candidateUnitReads++;
    if(delayedSession && url.pathname.endsWith('/sessions/'+delayedSession.id)) {
      const gate=delayedSession; delayedSession=null; gate.seen(); await gate.promise;
    }
    let sessionList;
    if(delayedSessionList && url.pathname.endsWith('/sessions')) {
      const gate=delayedSessionList; delayedSessionList=null; sessionList=gate.sessions; gate.seen(); await gate.promise;
    }
    let body;
    if (candidate && candidateMode === 'offline') body = {error:{message:'fixture offline'}};
    else if (url.pathname.endsWith('/devices')) body = {devices:candidate && candidateMode === 'invalid' ? {} : [{device_id:'cores3', creatable:true, program_modes:[],
      ...(fixtureCloudStartup?{uiflow_startup:{modes:['cloud'],runtime:'qemu-wifi',reference_sha256:'f'.repeat(64)}}:{})}]};
    else if (url.pathname.endsWith('/units')) body = serviceFixture;
    else if (fixtureCloudStartup && url.pathname.endsWith('/sessions') && method === 'POST') {
      const request=route.request().postDataJSON();fixtureCreates.push(request);
      body={session_id:`cloud-fixture-${fixtureCreates.length}`,device_id:'cores3',state:'running',display:null,units:[],device_state_supported:false,
        uiflow_startup:request.uiflow_startup,uiflow_cloud_status:structuredClone(cloudStatusFixture)};
      fixtureSessions=[body];
    }
    else if (url.pathname.endsWith('/sessions')) body = sessionListFailure ? {error:{message:'session list unavailable'}} : {sessions:sessionList || fixtureSessions};
    else if (url.pathname.endsWith('/serial')) {
      const channel=url.searchParams.get('channel')||'console', offset=Number(url.searchParams.get('offset')||0), text=fixtureSerial?.[channel]||'';
      body={session_id:url.pathname.split('/').at(-2),channel,data:text.slice(offset),next_offset:text.length};
    }
    else if (/\/sessions\/[^/]+$/.test(url.pathname)) {
      body = fixtureSessions.find(row=>row.session_id===url.pathname.split('/').at(-1)) || {};
      if (fixtureCloudStartup && method === 'DELETE') {body.state='stopped';body.worker={lease_active:false};}
    }
    else if (fixtureCloudStartup && url.pathname.endsWith('/evidence')) body={fixture:'HTTP UI contract only; no guest evidence'};
    else body = {error:{message:'unexpected host-fixture route'}};
    return route.fulfill({status:(candidate && candidateMode === 'offline') || (sessionListFailure && url.pathname.endsWith('/sessions')) ? 503 : 200, contentType:'application/json', body:JSON.stringify(body)});
  };
  await page.route(`${originalService}/**`, route => fixtureResponse(route));
  await page.route(`${candidateService}/**`, route => fixtureResponse(route, true));
  await test('first-service-failure-preserves-offline-unit-catalog-and-draft-ui-fixture', async () => {
    await page.goto(`${base}/showcase/?device=cores3&autostart=0`); await modelReady('cores3');
    await page.locator('#unitModelSelect').selectOption('button');
    await page.locator('#serviceConnection').evaluate(node => node.open = true);
    await page.locator('#serviceUrl').fill(candidateService); await page.locator('#connectServiceBtn').click();
    await page.waitForFunction(() => document.querySelector('#serviceStatus').textContent.includes('设备目录无效'));
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.service), null);
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.inventory === window.__publicWorkbenchProbe.localUnitInventory), true);
    assert.equal(await page.locator('#unitModelSelect').inputValue(), 'button'); assert.equal(candidateUnitReads, 0);
  });
  await test('service-connect-keeps-navigation-local-and-does-not-create-a-guest-ui-fixture', async () => {
    await page.locator('#serviceUrl').fill(originalService); await page.locator('#serviceToken').fill('original-fixture-token');
    await page.locator('#connectServiceBtn').click();
    await page.waitForFunction(url => window.__publicWorkbenchProbe.service?.url === url, originalService);
    await page.waitForFunction(() => document.querySelector('#sessionsStatus').textContent.includes('0 个会话'));
    assert.equal(await page.locator('#unitModelSelect').inputValue(), 'button');
    assert.equal(await page.locator('#startBtn').isEnabled(), true);
    assert.equal(await page.locator('nav a[href="#serviceSessions"]').getAttribute('target'), null);
    assert.equal(serviceCalls.some(row => row.method === 'POST' || row.method === 'DELETE'), false);
  });
  await test('configured-units-are-not-silently-dropped-by-browser-mode-ui-fixture', async () => {
    await page.locator('.advanced-options').evaluate(node => node.open = true); await page.locator('#runtimeMode').selectOption('browser');
    assert.equal(await page.locator('#startBtn').isDisabled(), true); assert.match(await page.locator('#capabilityText').textContent(), /尚未接入这些 Unit/);
    await page.locator('#runtimeMode').selectOption('auto'); assert.equal(await page.locator('#startBtn').isEnabled(), true);
  });
  await test('failed-reconnect-preserves-original-service-and-unit-owner-ui-fixture', async () => {
    await page.evaluate(() => {const s=window.__publicWorkbenchProbe;window.__originalServiceFixture={service:s.service,picker:s.picker};});
    candidateMode='offline'; await page.locator('#serviceUrl').fill(candidateService); await page.locator('#serviceToken').fill('candidate-fixture-token');
    await page.locator('#connectServiceBtn').click(); await page.waitForFunction(() => document.querySelector('#serviceStatus').textContent.includes('fixture offline'));
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.service === window.__originalServiceFixture.service), true);
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.picker === window.__originalServiceFixture.picker), true);
    assert.equal(await page.locator('#unitModelSelect').inputValue(), 'button'); assert.equal(await page.locator('#serviceToken').inputValue(), 'original-fixture-token');
    assert.equal(candidateUnitReads, 0);
  });
  await test('catalog-change-keeps-invalid-draft-and-blocks-auto-browser-and-programmatic-start-ui-fixture', async () => {
    const before=serviceCalls.length, requestOffset=requests.length;
    await page.evaluate(async()=>{
      const state=window.__publicWorkbenchProbe,changed=structuredClone(state.inventory);
      changed.units.find(unit=>unit.id==='button').runtime.status='planned';
      await state.picker.updateInventory(changed);
    });
    assert.equal(await page.evaluate(()=>window.__publicWorkbenchProbe.picker.snapshot().valid),false);
    assert.equal(await page.evaluate(()=>window.__publicWorkbenchProbe.picker.snapshot().attachments[0].unit_id),'button','invalid wiring remains visible as a draft instead of disappearing');
    assert.equal(await page.locator('#startBtn').isDisabled(),true,'auto/service cannot treat invalid wiring as an empty configuration');
    assert.equal(await page.locator('#capabilityTitle').textContent(),'请调整 Unit 连线');
    await page.locator('#runtimeMode').selectOption('browser');assert.equal(await page.locator('#startBtn').isDisabled(),true);
    // Deliberately invoke the real handler past the disabled button: the start
    // admission guard must independently reject, before firmware or allocation.
    await page.locator('#startBtn').dispatchEvent('click');
    await page.waitForFunction(()=>document.querySelector('#errorBanner').textContent.includes('合同不兼容'));
    assert.equal(await page.evaluate(()=>window.__publicWorkbenchProbe.run),null);
    assert.equal(serviceCalls.slice(before).some(row=>row.method==='POST'||row.method==='DELETE'),false);
    assert.equal(requests.slice(requestOffset).some(url=>/\.wasm(?:\?|$)|m5burner-cdn/.test(url)),false);
    assert.equal(workers.length,0);
    await page.evaluate(async()=>{const s=window.__publicWorkbenchProbe;await s.picker.updateInventory(s.inventory);});
    await page.locator('#runtimeMode').selectOption('auto');assert.equal(await page.locator('#startBtn').isEnabled(),true);
  });
  await test('sha-mismatch-fails-before-any-native-session-allocation-ui-fixture', async () => {
    await page.locator('[name="firmwareSource"][value="local"]').check();
    await page.locator('#firmwareFile').setInputFiles({name:'fixture.bin',mimeType:'application/octet-stream',buffer:Buffer.from('invalid browser fixture')});
    await page.locator('#firmwareSha').fill('0'.repeat(64)); await page.locator('#startBtn').click();
    await page.waitForFunction(() => document.querySelector('#errorBanner').textContent.includes('SHA-256'));
    assert.equal(await page.locator('#unitAssemblyPanel fieldset').evaluate(node=>node.disabled), false);
    assert.equal(serviceCalls.some(row => row.method === 'POST'), false); assert.equal(await page.locator('#startBtn').isEnabled(), true);
  });
  await test('firmware-load-locks-unit-draft-and-cancel-releases-it-without-a-guest-ui-fixture', async () => {
    await page.locator('[name="firmwareSource"][value="url"]').check(); await page.locator('#firmwareUrl').fill(base + '/fixture/slow.bin');
    await page.locator('#firmwareSha').fill(''); await page.locator('#startBtn').click();
    await page.locator('#cancelLoadBtn').waitFor({state:'visible'}); assert.equal(await page.locator('#unitAssemblyPanel fieldset').evaluate(node=>node.disabled), true);
    assert.equal(await page.locator('#unitModelSelect').isDisabled(),true,'the locked fieldset disables its actual picker control');
    await page.locator('#cancelLoadBtn').click(); await page.waitForTimeout(1200);
    assert.equal(await page.locator('#runtimeStatus').getAttribute('data-status'), 'stopped');
    assert.equal(await page.locator('#unitAssemblyPanel fieldset').evaluate(node=>node.disabled), false);
    assert.equal(await page.locator('#unitModelSelect').inputValue(), 'button'); assert.equal(await page.locator('#stopBtn').isHidden(), true);
  });
  await test('unconfirmed-stop-blocks-device-and-service-replacement-ui-fixture', async () => {
    await page.evaluate(async () => {
      const s=window.__publicWorkbenchProbe;window.__stopFault={allow:false,calls:0};
      const controller={current:{session_id:'host-only-fixture'},input:async()=>{},stop:async()=>{window.__stopFault.calls++;if(!window.__stopFault.allow)throw Error('fixture stop unavailable');controller.current=null;}};
      s.run={kind:'service',generation:s.runGeneration,controller}; await s.picker.setLocked(true); document.querySelector('#stopBtn').hidden=false;
    });
    await page.locator('#stopBtn').click(); await page.waitForFunction(() => document.querySelector('#runtimeStatus').dataset.status === 'stop_pending');
    assert.equal(await page.locator('#unitAssemblyPanel fieldset').evaluate(node=>node.disabled), true); assert.equal(await page.locator('#startBtn').isDisabled(), true);
    await page.locator('#deviceLibrary').evaluate(node => node.open=true); await page.locator('#deviceNav button[data-device-id="stopwatch"]').click();
    await page.waitForFunction(() => window.__stopFault.calls === 2); assert.equal(await page.locator('#stageTitle').textContent(), 'CoreS3');
    candidateMode='valid'; await page.locator('#serviceUrl').fill(candidateService); await page.locator('#connectServiceBtn').click();
    await page.waitForFunction(() => window.__stopFault.calls === 3);
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.service === window.__originalServiceFixture.service), true);
    assert.equal(candidateUnitReads, 0);
    await page.evaluate(() => window.__stopFault.allow=true); await page.locator('#stopBtn').click();
    await page.waitForFunction(() => window.__publicWorkbenchProbe.run === null);
    assert.equal(await page.locator('#unitAssemblyPanel fieldset').evaluate(node=>node.disabled), false);
  });
  await test('concurrent-session-list-refresh-replaces-only-newest-deduplicated-batch', async () => {
    const old={session_id:'c'.repeat(32),device_id:'cores3',state:'running'},latest={...old,session_id:'d'.repeat(32)};
    let release,seen;const promise=new Promise(resolve=>release=resolve),observed=new Promise(resolve=>seen=resolve);
    delayedSessionList={sessions:[old],promise,seen};fixtureSessions=[latest,latest];
    await page.locator('#serviceSessions').evaluate(node=>node.open=true);
    await page.locator('#refreshSessionsBtn').click();await observed;
    await page.locator('#refreshSessionsBtn').click();
    await page.waitForFunction(()=>document.querySelector('#serviceSessionList').textContent.includes('dddddddd'));
    assert.equal(await page.locator('#serviceSessionList .workbench-session').count(),1);
    const stale=page.waitForResponse(r=>r.url()===originalService+'/api/v1/sessions');release();await (await stale).finished();
    await page.waitForTimeout(100);
    assert.equal(await page.locator('#serviceSessionList .workbench-session').count(),1);
    assert.ok((await page.locator('#serviceSessionList').textContent()).includes('dddddddd'));
    assert.ok(!(await page.locator('#serviceSessionList').textContent()).includes('cccccccc'));
    fixtureSessions=[];await page.locator('#refreshSessionsBtn').click();
    await page.waitForFunction(()=>!document.querySelector('#serviceSessionList').children.length);
  });
  await test('borrowed-live-session-opens-in-place-without-create-or-delete-ui-fixture', async () => {
    fixtureSessions=[{session_id:'a'.repeat(32),device_id:'cores3',created_at:'2026-11-05T00:00:00Z',state:'running',
      firmware_sha256:'1'.repeat(64),units:[],display:null,serial_bytes:0,device_state_supported:false}];
    const before=serviceCalls.length; await page.locator('#serviceSessions').evaluate(node=>node.open=true);
    await page.locator('#refreshSessionsBtn').click(); await page.getByRole('button',{name:'在工作台打开',exact:true}).click();
    await page.waitForFunction(() => window.__publicWorkbenchProbe.run?.controller.current?.session_id === 'a'.repeat(32));
    assert.equal(await page.locator('#stopBtn').textContent(), '停止查看'); assert.equal(await page.locator('#unitAssemblyPanel fieldset').evaluate(node=>node.disabled), true);
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.shell.model.port('grove').module), null, 'a borrowed empty topology must not display the unrelated draft Unit');
    await page.locator('#unitExplorer').evaluate(node=>node.open=true);
    await page.locator('[data-unit-model="button"]').click(); await unitReady('button');
    assert.equal(await page.locator('#addSelectedUnitBtn').isDisabled(), true);
    await page.locator('#unitModelMount canvas').click();
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.run.controller.current.session_id), 'a'.repeat(32));
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.shell.model.port('grove').module), null, 'catalog preview cannot attach to the borrowed guest');
    assert.equal(serviceCalls.slice(before).some(row=>row.method==='POST'||row.method==='DELETE'), false, 'opening never creates or destroys another owner session');
  });
  await test('failed-list-refresh-keeps-same-service-retained-row-attachable', async () => {
    await page.locator('#stopBtn').click();await page.waitForFunction(()=>window.__publicWorkbenchProbe.run===null);
    sessionListFailure=true;const before=serviceCalls.length;
    await page.locator('#refreshSessionsBtn').click();
    await page.waitForFunction(()=>document.querySelector('#sessionsStatus').textContent.includes('会话读取失败'));
    assert.equal(await page.locator('#serviceSessionList .workbench-session').count(),1);
    await page.getByRole('button',{name:'在工作台打开',exact:true}).click();
    await page.waitForFunction(()=>window.__publicWorkbenchProbe.run?.controller.current?.session_id==='a'.repeat(32));
    assert.equal(serviceCalls.slice(before).some(row=>row.method==='POST'||row.method==='DELETE'),false);
    sessionListFailure=false;
  });
  await test('native-serial-channel-selection-keeps-independent-text-and-cursors-ui-fixture', async () => {
    fixtureSessions[0].serial_channels=[{channel:'console',transport:'console',bytes:4},{channel:'usb-serial-jtag',transport:'usb-serial-jtag',bytes:3}];
    fixtureSerial={console:'UART','usb-serial-jtag':'USB'};
    await page.locator('#serialDrawer').evaluate(node=>node.open=true);
    await page.waitForFunction(()=>!document.querySelector('#serialChannel').disabled);
    await page.waitForFunction(()=>document.querySelector('#serialOutput').textContent==='UART');
    await page.locator('#serialChannel').selectOption('usb-serial-jtag');
    await page.waitForFunction(()=>document.querySelector('#serialOutput').textContent==='USB');
    await page.locator('#serialDrawer').screenshot({path:resolve(out,'serial-channel-usb.png')});
    await page.locator('#serialChannel').selectOption('console');
    await page.waitForFunction(()=>document.querySelector('#serialOutput').textContent==='UART');
    assert.equal(await page.locator('#serialCount').textContent(),'4 B');
    fixtureSerial=null;delete fixtureSessions[0].serial_channels;
  });
  await test('cloud-observations-stay-independent-of-pairing-and-running-ui-fixture', async () => {
    fixtureSessions[0].uiflow_startup={mode:'cloud'};
    fixtureSessions[0].uiflow_cloud_status=structuredClone(cloudStatusFixture);
    await page.waitForFunction(()=>document.querySelector('#uiflowCloudStatus').textContent.includes('设备尚未绑定'));
    assert.match(await page.locator('#uiflowCloudStatus').textContent(),/已收到配对码（不代表已完成绑定）/);
    assert.equal(await page.locator('#runtimeStatus').getAttribute('data-status'),'running');
    fixtureSessions[0].uiflow_cloud_status.webrepl={state:'heartbeat_observed',reason:null,handshakes:1,disconnects:0,heartbeat_roundtrips:2,device_registered:true};
    await page.waitForFunction(()=>document.querySelector('#uiflowCloudStatus').textContent.includes('心跳往返 2 次'));
    assert.match(await page.locator('#uiflowCloudStatus').textContent(),/尚未验证远程代码执行/);
    fixtureSessions[0].uiflow_cloud_status={...structuredClone(cloudStatusFixture),state:'unavailable'};
    await page.waitForFunction(()=>document.querySelector('#uiflowCloudStatus').textContent.includes('暂无法判断'));
    assert.doesNotMatch(await page.locator('#uiflowCloudStatus').textContent(),/已收到配对码|尚未绑定/);
    delete fixtureSessions[0].uiflow_startup;delete fixtureSessions[0].uiflow_cloud_status;
    await page.waitForFunction(()=>document.querySelector('#uiflowCloudStatus').hidden);
  });
  await test('pending-borrowed-B-cannot-replace-current-A-after-A-is-reselected-ui-fixture', async () => {
    fixtureSessions.push({...fixtureSessions[0],session_id:'b'.repeat(32),firmware_sha256:'2'.repeat(64)});
    await page.locator('#refreshSessionsBtn').click(); await page.getByRole('button',{name:'在工作台打开',exact:true}).nth(1).waitFor();
    await page.evaluate(()=>window.__borrowedControllerA=window.__publicWorkbenchProbe.run.controller);
    let release,seen; const promise=new Promise(resolve=>release=resolve), observed=new Promise(resolve=>seen=resolve);
    delayedSession={id:'b'.repeat(32),promise,seen}; const before=serviceCalls.length;
    await page.getByRole('button',{name:'在工作台打开',exact:true}).nth(1).click(); await observed;
    await page.getByRole('button',{name:'在工作台打开',exact:true}).nth(0).click();
    const response=page.waitForResponse(r=>r.url()===originalService+'/api/v1/sessions/'+'b'.repeat(32));release();
    await (await response).finished(); await page.waitForTimeout(200);
    assert.equal(await page.evaluate(()=>window.__publicWorkbenchProbe.run.controller===window.__borrowedControllerA),true);
    assert.equal(await page.evaluate(()=>window.__publicWorkbenchProbe.run.controller.current.session_id),'a'.repeat(32));
    assert.equal(await page.locator('#stageTitle').textContent(),'CoreS3');
    await page.locator('#stopBtn').click(); await page.waitForFunction(() => window.__publicWorkbenchProbe.run === null);
    await page.waitForFunction(() => window.__publicWorkbenchProbe.shell.model.port('grove').module?.meta.id === 'm5stack.unit.button.grove');
    assert.equal(serviceCalls.slice(before).some(row=>row.method==='POST'||row.method==='DELETE'),false,'neither pending B nor leaving A writes a session');
  });
  await test('late-picker-device-A-return-cannot-overwrite-current-device-B', async () => {
    await page.evaluate(()=>{
      const picker=window.__publicWorkbenchProbe.picker,original=picker.setDevice.bind(picker);
      window.__pickerRace={entered:false,released:false};
      picker.setDevice=async id=>{const result=await original(id);if(id==='stopwatch'&&!window.__pickerRace.entered){
        window.__pickerRace.entered=true;await new Promise(resolve=>window.__pickerRace.release=resolve);
      }return result;};
    });
    await page.locator('#deviceLibrary').evaluate(node=>node.open=true);
    await page.locator('#deviceNav button[data-device-id="stopwatch"]').click();await page.waitForFunction(()=>window.__pickerRace.entered);
    await page.locator('#deviceNav button[data-device-id="cores3"]').click();await modelReady('cores3');
    await page.evaluate(()=>{window.__pickerRace.release();window.__pickerRace.released=true;});await page.waitForTimeout(200);
    assert.equal(await page.locator('#stageTitle').textContent(),'CoreS3');
    assert.equal(await page.locator('#deviceMount').getAttribute('data-device-id'),'cores3');
    assert.equal(await page.evaluate(()=>window.__publicWorkbenchProbe.picker.deviceId),'cores3');
    assert.equal(await page.evaluate(()=>window.__publicWorkbenchProbe.shell.device.id),'cores3');
  });
  await test('unknown-device-fails-closed-and-no-runtime-is-started-by-host-contracts', async () => {
    await page.goto(`${base}/showcase/?device=unknown-test-device&autostart=0`);
    await page.waitForFunction(() => document.querySelector('#errorBanner').textContent.includes('尚未收录'));
    assert.equal(await page.locator('#startBtn').isDisabled(), true); assert.equal(await page.locator('#stageTitle').textContent(), '请选择设备');
    await selectDevice('cores3'); assert.equal(await page.locator('#errorBanner').isHidden(), true);
    if(!realBrowser){assert.equal(workers.length,0);assert.equal(requests.some(url=>/\.wasm(?:\?|$)/.test(url)),false);}
  });
  await test('cloud-identity-is-optional-ephemeral-and-sent-only-on-explicit-cloud-start-ui-fixture', async () => {
    fixtureCloudStartup=true;fixtureSessions=[];
    await page.locator('#serviceConnection').evaluate(node=>node.open=true);
    await page.locator('#serviceUrl').fill(originalService);await page.locator('#connectServiceBtn').click();
    await page.waitForFunction(()=>!document.querySelector('#cloudIdentityFields').hidden);
    await page.locator('input[name="firmwareSource"][value="local"]').check();
    await page.locator('.advanced-options').evaluate(node=>node.open=true);
    await page.locator('#runtimeMode').selectOption('service');await page.locator('#runtimeMode').selectOption('auto');
    assert.equal(await page.locator('#cloudIdentityFields').isHidden(),true);
    await page.locator('input[name="firmwareSource"][value="reference"]').check();
    assert.equal(await page.locator('#cloudIdentityFields').isVisible(),true,'source changes must restore the selected cloud identity field after details were rerendered');
    assert.equal(await page.locator('#cloudIdentityMac').inputValue(),'');
    assert.equal(await page.locator('#cloudIdentityMac').getAttribute('autocomplete'),'off');
    await page.locator('#cloudIdentityMac').fill('020000000001');
    await page.locator('#startBtn').click();
    await page.waitForFunction(()=>window.__publicWorkbenchProbe.run?.controller.current?.session_id==='cloud-fixture-1');
    assert.deepEqual(fixtureCreates[0].device_identity,{mac:'020000000001'});
    assert.equal(fixtureCreates[0].uiflow_startup.mode,'cloud');
    assert.equal(await page.locator('#cloudIdentityMac').isDisabled(),true);
    assert.equal(await page.evaluate(()=>[localStorage,sessionStorage].some(storage=>Object.values(storage).some(value=>value.includes('020000000001')))),false);
    await page.locator('#uiflowCloudStatus').screenshot({path:resolve(out,'cloud-identity-rejection-host-fixture.png')});
    await page.locator('#stopBtn').click();await page.waitForFunction(()=>window.__publicWorkbenchProbe.run===null);
    assert.match(await page.locator('#uiflowCloudStatus').textContent(),/末次观测/);
    await page.locator('#cloudIdentityMac').fill('');await page.locator('#startBtn').click();
    await page.waitForFunction(()=>window.__publicWorkbenchProbe.run?.controller.current?.session_id==='cloud-fixture-2');
    assert.equal(Object.hasOwn(fixtureCreates[1],'device_identity'),false);
    await page.locator('#stopBtn').click();await page.waitForFunction(()=>window.__publicWorkbenchProbe.run===null);
    await page.locator('#referenceExample').selectOption('uiflow');
    assert.equal(await page.locator('#cloudIdentityFields').isHidden(),true);
    fixtureCloudStartup=false;
  });
  if (realBrowser)
    await test('real-papers3-url-autostart-serial-screen-touch-pause-and-stop', async () => {
      const firstRealRequest = requests.length;
      await page.setViewportSize({width: 1440, height: 1000});
      const started = Date.now();
      await page.goto(
        `${base}/showcase/?device=m5papers3&firmware=${encodeURIComponent(base + '/fixture/real.bin')}&sha256=${realFirmwareSha}`,
      );
      await page.waitForFunction(
        () => {
          const error = document.querySelector('#errorBanner');
          if (!error.hidden && error.textContent) throw new Error(error.textContent);
          return (
            document.querySelector('#serialOutput').textContent.includes('AppWifi') &&
            window.__publicWorkbenchProbe?.run?.controller.observe().stats.time > 14 &&
            Number(document.querySelector('#deviceMount').dataset.frameSequence) > 0
          );
        },
        null,
        {timeout: 120000},
      );
      assert.equal(await page.locator('[data-view="shell"]').textContent(), '3D');
      assert.equal(await page.locator('#deviceMount [data-renderer="papers3-three"]').count(), 1);
      const firstApplicationMs = Date.now() - started;
      const canvas = page.locator('#deviceMount .three-device-stage canvas');
      const cdp = await context.newCDPSession(page);
      const guestTargets = async () => (await cdp.send('Target.getTargets')).targetInfos
        .filter(target => target.type === 'worker' && target.url.includes('/vendor/esp32sim/worker.js'))
        .map(target => target.targetId);
      const startedWorkers = await guestTargets();
      assert.ok(startedWorkers.length > 0, 'CDP sees the actual guest Worker');
      await page.evaluate(() => {
        window.__paperTouches = [];
        window.__publicWorkbenchProbe.shell.on('touch', ({action, x, y}) => window.__paperTouches.push({action, x, y}));
      });
      async function advance(seconds) {
        const target =
          (await page.evaluate(() => window.__publicWorkbenchProbe.run.controller.observe().stats.time)) + seconds;
        await page.waitForFunction(
          (target) => window.__publicWorkbenchProbe.run.controller.observe().stats.time >= target,
          target,
          {timeout: 120000},
        );
      }
      async function checkpoint(name) {
        if ((await page.locator('#runtimeStatus').getAttribute('data-status')) !== 'paused')
          await page.locator('#pauseBtn').click();
        await page.waitForFunction(() => document.querySelector('#runtimeStatus').dataset.status === 'paused');
        const result = await page.evaluate(async () => {
          const {display} = window.__publicWorkbenchProbe.shell;
          const {width, height, buffer:all} = display;
          const region = new Uint8Array(160 * 160 * 4);
          for (let row = 0; row < 160; row++) {
            const offset = ((270 + row) * width + 30) * 4;
            region.set(all.subarray(offset, offset + 160 * 4), row * 160 * 4);
          }
          const hash = (data) =>
            crypto.subtle
              .digest('SHA-256', data)
              .then((bytes) => Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, '0')).join(''));
          let dark = 0,
            light = 0;
          for (let i = 0; i < all.length; i += 4) {
            if (all[i] < 32 && all[i + 1] < 32 && all[i + 2] < 32) dark++;
            if (all[i] > 224 && all[i + 1] > 224 && all[i + 2] > 224) light++;
          }
          return {
            width,
            height,
            rgba_sha256: await hash(all),
            region_sha256: await hash(region),
            dark_pixels: dark,
            light_pixels: light,
            observe: window.__publicWorkbenchProbe.run.controller.observe(),
          };
        });
        assert.equal(result.width, 540);
        assert.equal(result.height, 960);
        assert.ok(result.dark_pixels > 100 && result.light_pixels > 100);
        assert.equal(result.observe.runtime.firmwareSha256, realFirmwareSha);
        assert.equal(result.observe.runtime.wasmSha256, runtimeManifest.wasm.sha256);
        checkpoints.push({name, ...result});
        await page.screenshot({path: `${out}/${name}.png`, fullPage: true});
        await canvas.screenshot({path: `${out}/${name}-screen.png`});
        return result;
      }
      async function tap() {
        await page.locator('#pauseBtn').click();
        await page.waitForFunction(() => document.querySelector('#runtimeStatus').dataset.status === 'running');
        await canvas.scrollIntoViewIfNeeded();
        const point = await page.evaluate(async () => {
          const {Vector3} = await import('three');
          const {display, viewer} = window.__publicWorkbenchProbe.shell;
          const screenPoint = display.panel.localToWorld(new Vector3(
            (116.5 / display.width - 0.5) * display.size[0],
            (0.5 - 330.5 / display.height) * display.size[1], 0,
          )).project(viewer.camera);
          const rect = viewer.renderer.domElement.getBoundingClientRect();
          return [rect.left + (screenPoint.x + 1) * rect.width / 2,
            rect.top + (1 - screenPoint.y) * rect.height / 2];
        });
        await page.mouse.move(...point);
        await page.mouse.down();
        await advance(0.15);
        await page.mouse.up();
        await advance(4.5);
        const events = await page.evaluate(() => window.__paperTouches.slice(-2));
        assert.deepEqual(events.map(event => event.action), ['start','end']);
        for (const event of events) assert.ok(Math.abs(event.x - 116) <= 2 && Math.abs(event.y - 330) <= 2);
        checkpoints.push({name:'papers3-3d-pointer', events});
      }
      const boot = await checkpoint('homepage-official-boot');
      await tap();
      const changed = await checkpoint('homepage-touch-toggle');
      assert.notEqual(
        changed.region_sha256,
        boot.region_sha256,
        'actual page GT911 touch changes the official application icon',
      );
      await tap();
      await checkpoint('homepage-touch-return');
      for (const width of [1440, 1024, 768, 390]) {
        await page.setViewportSize({width, height: 1000});
        // Let Chromium paint the resized viewport before full-page capture;
        // layout bounds alone can precede compositor tile updates.
        await page.waitForTimeout(150);
        const bounds = await page.evaluate(() => {
          const stage = document.querySelector('#deviceMount').getBoundingClientRect();
          const body = document.querySelector('[data-renderer="papers3-three"]').getBoundingClientRect();
          return {
            stage: {x: stage.x, y: stage.y, width: stage.width, height: stage.height},
            body: {x: body.x, y: body.y, width: body.width, height: body.height},
            within:
              body.left >= stage.left - 1 &&
              body.right <= stage.right + 1 &&
              body.top >= stage.top - 1 &&
              body.bottom <= stage.bottom + 1,
            noOverflow: document.documentElement.scrollWidth <= innerWidth,
          };
        });
        checkpoints.push({name: `papers3-layout-${width}`, ...bounds});
        assert.ok(bounds.within, `PaperS3 screen shell stays inside its stage at ${width}: ${JSON.stringify(bounds)}`);
        assert.ok(bounds.noOverflow, `PaperS3 page has no horizontal overflow at ${width}`);
        await page.screenshot({path: `${out}/papers3-page-${width}.png`, fullPage: true});
      }
      const controller = await page.evaluateHandle(() => window.__publicWorkbenchProbe.run.controller);
      await page.locator('#stopBtn').click();
      await page.waitForFunction(() => document.querySelector('#runtimeStatus').dataset.status === 'stopped');
      assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.run), null);
      assert.equal(await controller.evaluate((controller) => controller.worker === null), true);
      const deadline = Date.now() + 5000;
      while ((await guestTargets()).some(target => startedWorkers.includes(target))) {
        assert.ok(Date.now() < deadline, 'guest Worker must disappear before browser closure');
        await page.waitForTimeout(50);
      }
      await cdp.detach();
      await controller.dispose();
      assert.equal(
        requests.slice(firstRealRequest).some((url) => /\/api\/v1\//.test(url)),
        false,
        'real guest remains entirely in browser',
      );
      checkpoints.push({
        name: 'stopped',
        first_application_wall_ms: firstApplicationMs,
        api_requests: 0,
        worker_terminated: true,
      });
    });
  assert.deepEqual(pageErrors, []);
  await writeFile(
    `${out}/report.json`,
    JSON.stringify(
      {
        status: 'PASS',
        category: 'public-page-browser-contract',
        checks,
        source_sha256: executedSourceHashes,
        exported_source_sha256: exportedSourceHashes,
        browser: browser.version(),
        guest_execution: realBrowser ? 'PaperS3 official factory v0.5, browser virtual-device' : 'NOT RUN',
        firmware_sha256: realBrowser ? realFirmwareSha : null,
        runtime: runtimeManifest || null,
        checkpoints,
        hardware_execution: 'NOT RUN',
        service_fixture_scope: 'HTTP/model/lifecycle host contracts only; no native guest, program output or framebuffer is fabricated.',
        runtime_workers_observed: workers,
        manifest_sha256: createHash('sha256').update(await readFile(resolve(site, 'public-site-manifest.json'))).digest('hex'),
        errors: pageErrors,
      },
      null,
      2,
    ) + '\n',
  );
  console.log(`PUBLIC_WORKBENCH_BROWSER_OK ${checks.length} checks`);
} catch (error) {
  const pageState = await page
    .evaluate(() => ({
      status: document.querySelector('#runtimeStatus')?.textContent,
      error: document.querySelector('#errorBanner')?.textContent,
      progress: document.querySelector('#runProgress')?.textContent,
      frame: document.querySelector('#deviceMount')?.dataset.frameSequence,
      serial: document.querySelector('#serialOutput')?.textContent.slice(-8000),
      observe: window.__publicWorkbenchProbe?.run?.controller.observe?.(),
    }))
    .catch(() => null);
  await page.screenshot({path: `${out}/failure.png`, fullPage: true}).catch(() => {});
  await writeFile(
    `${out}/report.json`,
    JSON.stringify(
      {
        status: 'FAIL',
        checks,
        error: error.stack,
        pageErrors,
        pageState,
        checkpoints,
        guest_execution: realBrowser ? 'ATTEMPTED' : 'NOT RUN',
      },
      null,
      2,
    ) + '\n',
  );
  throw error;
} finally {
  await browser.close();
  await new Promise((done) => server.close(done));
}
