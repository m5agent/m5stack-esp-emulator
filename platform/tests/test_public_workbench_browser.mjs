// Default: browser contracts only. --real-browser-runtime explicitly runs the
// official PaperS3 guest in the exported WASM. No Device Service or hardware.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {chromium} from 'playwright';

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
    executedSourcePaths.slice(0, 3).map(async (path) => [
      path,
      createHash('sha256')
        .update(await readFile(resolve(site, path)))
        .digest('hex'),
    ]),
  ),
);
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
  requests = [];
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
  const file = resolve(site, decodeURIComponent(url.pathname.slice('/showcase/'.length)) || 'index.html');
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
const test = async (name, run) => {
  await run();
  checks.push(name);
};
try {
  await test('first-visit-selects-an-available-browser-profile-without-auto-running-reference', async () => {
    const config = JSON.parse(await readFile(resolve(site, 'platform/web/site-config.json'), 'utf8'));
    await page.goto(`${base}/showcase/`);
    const expected = config.browser_board_execution ? 'stopwatch' : 'cores3';
    await page.waitForFunction((id) => document.querySelector('#deviceMount').dataset.deviceId === id, expected);
    assert.equal(await page.locator('#runtimeStatus').getAttribute('data-status'), 'model');
    if (config.browser_board_execution) {
      assert.equal(await page.locator('#startBtn').isEnabled(), true);
      assert.match(await page.locator('#referenceTitle').textContent(), /User Demo/);
    }
  });
  await test('project-path-entry-and-actual-model-without-device-service', async () => {
    await page.goto(`${base}/showcase/?device=cores3&autostart=0`);
    await page.waitForFunction(() => document.querySelector('#deviceMount').dataset.deviceId === 'cores3');
    assert.equal(await page.locator('#stageTitle').textContent(), 'CoreS3');
    assert.ok((await page.locator('#deviceNav [data-device-id]').count()) >= 18);
    assert.equal(await page.locator('#deviceMount [data-model-source="m5stack-models"]').count(), 1);
    assert.equal(
      await page.locator('#startBtn').isDisabled(),
      true,
      'native-only device does not pretend browser firmware is ready',
    );
    assert.match(await page.locator('#capabilityText').textContent(), /连接兼容服务/);
    assert.equal(
      await page.locator('[data-service-console="platform/web/sessions.html"]').getAttribute('href'),
      '#serviceConnection',
    );
    assert.equal(
      requests.some((url) => /\/api\/v1\//.test(url)),
      false,
      'browsing does not call an implicit local service',
    );
    assert.equal(
      requests.some((url) => new URL(url).pathname.startsWith('/platform/')),
      false,
      'project assets retain their prefix',
    );
  });
  await test('public-console-navigation-opens-connection-panel-without-calling-pages-api', async () => {
    for (const path of ['platform/web/sessions.html', 'platform/web/firmware.html']) {
      const link = page.locator(`[data-service-console="${path}"]`);
      assert.equal(await link.getAttribute('target'), null);
      await page.locator('#serviceConnection').evaluate((node) => {node.open = false;});
      await link.click();
      assert.equal(page.url(), `${base}/showcase/?device=cores3&autostart=0`);
      assert.equal(await page.locator('#serviceConnection').getAttribute('open'), '');
      assert.match(await page.locator('#serviceStatus').textContent(), /控制台，请先连接/);
      assert.equal(await page.locator('#serviceUrl').evaluate((node) => document.activeElement === node), true);
    }
    assert.equal(requests.some((url) => /\/api\/v1\//.test(url)), false);
  });
  await test('search-and-browser-admission-are-explicit', async () => {
    await page.locator('#search').fill('AtomS3 Lite');
    assert.equal(await page.locator('#deviceNav [data-device-id]').count(), 1);
    await page.locator('[data-device-id="atoms3-lite"]').click();
    await page.waitForFunction(() => document.querySelector('#deviceMount').dataset.deviceId === 'atoms3-lite');
    assert.equal(await page.locator('#startBtn').isDisabled(), true);
    assert.match(await page.locator('#frameStatus').textContent(), /仅有视觉模型/);
    assert.equal(await page.locator('#capabilityTitle').textContent(), '仅浏览模型');
    assert.match(await page.locator('#capabilityText').textContent(), /本型号尚未接入固件运行/);
    assert.equal(await page.locator('#openServiceBtn').isVisible(), false);
    await page.locator('#search').fill('');
    await page.locator('[data-device-filter="browser"]').click();
    assert.deepEqual(
      (
        await page.locator('#deviceNav [data-device-id]').evaluateAll((nodes) => nodes.map((n) => n.dataset.deviceId))
      ).sort(),
      ['papers3', 'stopwatch'],
    );
    await page.locator('[data-device-filter="all"]').click();
  });
  await test('unit-model-preview-and-long-notes-are-separate-from-runtime', async () => {
    await page.locator('#unitExplorer > summary').focus();
    await page.keyboard.press('Enter');
    await page.waitForSelector('#unitModelMount [data-visual-only="true"]');
    assert.equal(await page.locator('#unitDetails').getAttribute('open'), null);
    assert.match(await page.locator('#unitPreviewNote').textContent(), /不向固件注入数据/);
    await page.locator('#unitSearch').fill('U001-C');
    assert.equal(await page.locator('[data-unit-model]').count(), 1);
    await page.locator('#unitDetails > summary').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#unitDetailBody').isVisible(), true);
    await page.keyboard.press('Enter');
    await page.locator('#unitSearch').fill('');
    await page.locator('[data-unit-filter="runtime"]').click();
    assert.equal(await page.locator('[data-unit-model]').count(), 0);
    assert.match(await page.locator('#unitResults').textContent(), /先连接服务/);
    await page.locator('[data-unit-filter="all"]').click();
  });
  await test('responsive-real-model-at-four-widths', async () => {
    await page.locator('[data-device-id="cores3"]').click();
    await page.waitForFunction(() => document.querySelector('#deviceMount').dataset.deviceId === 'cores3');
    await page.locator('#unitExplorer').evaluate((node) => {
      node.open = false;
    });
    for (const width of [1440, 1024, 768, 390]) {
      await page.setViewportSize({width, height: 1000});
      await page.waitForTimeout(150);
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        true,
        `no horizontal overflow at ${width}`,
      );
      assert.equal(await page.locator('#startBtn').count(), 1);
      await page.screenshot({path: `${out}/public-${width}.png`, fullPage: true});
    }
  });
  await test('papers3-alias-is-not-papermono-and-shares-no-credentials', async () => {
    await page.goto(`${base}/showcase/?device=m5papers3&autostart=0&token=ignored-secret`);
    await page.waitForFunction(() => document.querySelector('#deviceMount').dataset.deviceId === 'papers3');
    assert.equal(await page.locator('#stageTitle').textContent(), 'PaperS3');
    assert.equal(await page.locator('#startBtn').isEnabled(), true);
    assert.match(await page.locator('#launchNotice').textContent(), /凭据参数已忽略/);
    await page.locator('#shareBtn').click();
    const url = new URL(await page.evaluate(() => navigator.clipboard.readText()));
    assert.equal(url.pathname, '/showcase/');
    assert.equal(url.searchParams.get('device'), 'papers3');
    assert.equal(url.searchParams.has('token'), false);
    assert.equal(url.href.includes('ignored-secret'), false);
  });
  await test('local-sha-mismatch-fails-before-any-runtime-start', async () => {
    await page.locator('[name="firmwareSource"][value="local"]').check();
    await page.locator('#firmwareFile').setInputFiles({
      name: 'fixture.bin',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('invalid browser fixture'),
    });
    await page.locator('.advanced-options > summary').click();
    await page.locator('#firmwareSha').fill('0'.repeat(64));
    await page.locator('#startBtn').click();
    await page.waitForFunction(() => document.querySelector('#errorBanner').textContent.includes('SHA-256'));
    assert.equal(await page.locator('#startBtn').isEnabled(), true, 'failed local load is recoverable');
    assert.equal(
      requests.some((url) => url.includes('/esp32sim/runtime.json')),
      false,
    );
  });
  await test('url-autostart-validates-real-bytes-without-claiming-guest-pass', async () => {
    await page.goto(`${base}/showcase/?device=papers3&firmware=${encodeURIComponent(base + '/fixture/bad.bin')}`);
    await page.waitForFunction(() => document.querySelector('#errorBanner').textContent.includes('完整合并固件'));
    assert.equal(await page.locator('#firmwareUrl').inputValue(), base + '/fixture/bad.bin');
    assert.equal(await page.locator('#runtimeStatus').getAttribute('data-status'), 'error');
    assert.equal(await page.locator('#startBtn').isEnabled(), true);
  });
  await test('cancel-withdraws-delayed-firmware-and-late-start', async () => {
    await page.goto(`${base}/showcase/?device=stopwatch&firmware=${encodeURIComponent(base + '/fixture/slow.bin')}`);
    await page.locator('#cancelLoadBtn').waitFor({state: 'visible'});
    await page.locator('#cancelLoadBtn').click();
    await page.waitForTimeout(1200);
    assert.equal(await page.locator('#runtimeStatus').getAttribute('data-status'), 'stopped');
    assert.equal(await page.locator('#stopBtn').isHidden(), true);
    assert.equal(await page.locator('#startBtn').isEnabled(), true);
    assert.equal(await page.locator('#rawFramePanel').isHidden(), true);
  });
  await test('unknown-device-never-falls-back-silently', async () => {
    await page.goto(`${base}/showcase/?device=unknown-test-device&autostart=0`);
    await page.waitForFunction(() => document.querySelector('#errorBanner').textContent.includes('尚未收录'));
    assert.equal(await page.locator('#stageTitle').textContent(), '请选择设备');
    assert.equal(await page.locator('#startBtn').isDisabled(), true);
    await page.locator('[data-device-id="papers3"]').click();
    await page.waitForFunction(() => document.querySelector('#deviceMount').dataset.deviceId === 'papers3');
    assert.equal(await page.locator('#errorBanner').isHidden(), true, 'manual selection recovers from a bad link');
  });
  await test('native-stop-failure-retains-owner-and-blocks-device-switch-ui-fixture', async () => {
    await page.evaluate(() => {
      const state = window.__publicWorkbenchProbe;
      window.__stopFault = {allow: false, calls: 0};
      const controller = {
        current: {session_id: 'fixture-retained-session'},
        input: async () => {},
        stop: async () => {
          window.__stopFault.calls++;
          if (!window.__stopFault.allow) throw new Error('fixture HTTP 503');
          controller.current = null;
        },
      };
      state.run = {kind: 'service', generation: state.runGeneration, controller};
      document.querySelector('#stopBtn').hidden = false;
    });
    await page.locator('#stopBtn').click();
    await page.waitForFunction(() => document.querySelector('#runtimeStatus').dataset.status === 'stop_pending');
    assert.equal(
      await page.evaluate(() => window.__publicWorkbenchProbe.run.controller.current.session_id),
      'fixture-retained-session',
    );
    assert.equal(await page.locator('#startBtn').isDisabled(), true);
    await page.locator('#deviceLibrary').evaluate((node) => {
      node.open = true;
    });
    await page.locator('[data-device-id="stopwatch"]').click();
    await page.waitForFunction(() => window.__stopFault.calls === 2);
    assert.equal(
      await page.locator('#stageTitle').textContent(),
      'PaperS3',
      'failed stop cannot be bypassed by switching devices',
    );
    await page.evaluate(() => {
      window.__stopFault.allow = true;
    });
    await page.locator('#stopBtn').click();
    await page.waitForFunction(() => window.__publicWorkbenchProbe.run === null);
    assert.equal(await page.locator('#runtimeStatus').getAttribute('data-status'), 'stopped');
    assert.equal(await page.locator('#startBtn').isEnabled(), true);
  });
  await test('configured-service-units-are-never-silently-dropped-by-browser-selection-ui-fixture', async () => {
    await page.evaluate(() => {
      const state = window.__publicWorkbenchProbe;
      window.__laneFixtureRestore = {picker: state.picker, serviceDevices: state.serviceDevices};
      state.serviceDevices = [{device_id: 'papers3', creatable: true}];
      state.picker = {attachments: () => [{id: 'unit-fixture', unit_id: 'pir', port_id: 'port-a'}]};
      document.querySelector('#unitConnectionPicker').dispatchEvent(new Event('change', {bubbles: true}));
    });
    assert.equal(await page.locator('#capabilityTitle').textContent(), '通过仿真服务运行');
    await page.locator('.advanced-options').evaluate((node) => {
      node.open = true;
    });
    await page.locator('#runtimeMode').selectOption('browser');
    assert.equal(await page.locator('#startBtn').isDisabled(), true);
    assert.match(await page.locator('#capabilityText').textContent(), /尚未接入这些 Unit/);
    await page.evaluate(() => Object.assign(window.__publicWorkbenchProbe, window.__laneFixtureRestore));
    await page.locator('#runtimeMode').selectOption('auto');
    assert.equal(await page.locator('#startBtn').isEnabled(), true);
  });
  const serviceFixture = {
    hosts: [{device_id: 'papers3', ports: [{id: 'port-a', label: 'Port A', wiring_status: 'confirmed', physical_presence: 'main-device'}]}],
    units: [{id: 'pir', name: 'PIR fixture', interface: {bus: 'gpio'}, inputs: {}, runtime: {status: 'implemented', hosts: ['papers3']}}],
  };
  const originalService = 'https://original-service.public.invalid/device-center',
    candidateService = 'https://candidate-service.public.invalid/replacement';
  const assertServiceConsoleLinks = async (service) => {
    for (const path of ['platform/web/sessions.html', 'platform/web/firmware.html']) {
      const link = page.locator(`[data-service-console="${path}"]`);
      assert.equal(await link.getAttribute('href'), `${service}/${path}`);
      assert.equal(await link.getAttribute('target'), '_blank');
      assert.deepEqual((await link.getAttribute('rel')).split(/\s+/).sort(), ['noopener', 'noreferrer']);
    }
  };
  let candidateMode = 'invalid', candidateUnitReads = 0;
  await page.route(`${originalService}/**`, (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify(new URL(route.request().url()).pathname.endsWith('/devices')
      ? {devices: [{device_id: 'papers3', creatable: true}]} : serviceFixture),
  }));
  await page.route(`${candidateService}/**`, (route) => {
    const devices = new URL(route.request().url()).pathname.endsWith('/devices');
    if (!devices) candidateUnitReads++;
    return route.fulfill({
      status: candidateMode === 'offline' ? 503 : 200, contentType: 'application/json',
      body: JSON.stringify(candidateMode === 'offline' ? {error: {message: 'fixture offline'}}
        : devices ? {devices: candidateMode === 'invalid' ? {} : [{device_id: 'papers3', creatable: true}]}
          : serviceFixture),
    });
  });
  await test('first-service-failure-rejects-malformed-directory-and-keeps-browser-usable-ui-fixture', async () => {
    await page.goto(`${base}/showcase/?device=papers3&autostart=0`);
    await page.waitForFunction(() => document.querySelector('#deviceMount').dataset.deviceId === 'papers3');
    await page.locator('#serviceConnection').evaluate((node) => {node.open = true;});
    await page.locator('#serviceUrl').fill(candidateService);
    await page.locator('#connectServiceBtn').click();
    await page.waitForFunction(() => document.querySelector('#serviceStatus').textContent.includes('设备目录无效'));
    assert.deepEqual(await page.evaluate(() => {
      const state = window.__publicWorkbenchProbe;
      return {service: state.service, inventory: state.inventory, picker: state.picker, devices: state.serviceDevices};
    }), {service: null, inventory: null, picker: null, devices: []});
    assert.equal(await page.locator('#unitConnectionPicker').textContent(), '');
    assert.equal(await page.locator('#startBtn').isEnabled(), true);
    assert.equal(candidateUnitReads, 0);
    assert.equal(await page.locator('[data-service-console="platform/web/sessions.html"]').getAttribute('href'), '#serviceConnection');
  });
  await test('failed-reconnect-preserves-the-original-service-and-selected-units-ui-fixture', async () => {
    await page.locator('#serviceUrl').fill(originalService);
    await page.locator('#serviceToken').fill('original-fixture-token');
    await page.locator('#connectServiceBtn').click();
    await page.waitForSelector('#unitModelSelect');
    await page.locator('#unitModelSelect').selectOption('pir');
    await assertServiceConsoleLinks(originalService);
    await page.evaluate(() => {
      const state = window.__publicWorkbenchProbe;
      window.__originalServiceFixture = {service: state.service, picker: state.picker, inventory: state.inventory};
    });
    candidateMode = 'offline';
    await page.locator('#serviceUrl').fill(candidateService);
    await page.locator('#serviceToken').fill('candidate-fixture-token');
    await page.locator('#connectServiceBtn').click();
    await page.waitForFunction(() => document.querySelector('#serviceStatus').textContent.includes('已保留原服务连接'));
    assert.equal(await page.evaluate(() => {
      const state = window.__publicWorkbenchProbe, original = window.__originalServiceFixture;
      return state.service === original.service && state.picker === original.picker && state.inventory === original.inventory;
    }), true);
    assert.equal(await page.locator('#serviceUrl').inputValue(), originalService);
    assert.equal(await page.locator('#serviceToken').inputValue(), 'original-fixture-token');
    assert.equal(await page.locator('#unitModelSelect').inputValue(), 'pir');
    assert.deepEqual(await page.evaluate(() => window.__publicWorkbenchProbe.picker.attachments('papers3')),
      [{id: 'external1', unit_id: 'pir', port_id: 'port-a'}]);
    assert.equal(await page.locator('#capabilityTitle').textContent(), '通过仿真服务运行');
    assert.equal(await page.locator('#startBtn').isEnabled(), true);
    await assertServiceConsoleLinks(originalService);
  });
  await test('unresolved-native-owner-blocks-service-replacement-until-stop-recovers-ui-fixture', async () => {
    await page.evaluate(() => {
      const state = window.__publicWorkbenchProbe;
      window.__serviceStopFixture = {allow: false, calls: 0, stopServices: []};
      const controller = {
        current: null, createIntent: {requestId: 'unresolved-create-fixture'},
        input: async () => {},
        stop: async () => {
          window.__serviceStopFixture.calls++;
          window.__serviceStopFixture.stopServices.push(state.service.url);
          if (!window.__serviceStopFixture.allow) throw new Error('fixture create recovery unavailable');
          controller.createIntent = null;
        },
      };
      state.run = {kind: 'service', generation: state.runGeneration, controller};
      state.stopUnconfirmed = true;
    });
    candidateMode = 'valid';
    await page.locator('#serviceUrl').fill(candidateService);
    await page.locator('#connectServiceBtn').click();
    await page.waitForFunction(() => document.querySelector('#serviceStatus').textContent.includes('fixture create recovery unavailable'));
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.service === window.__originalServiceFixture.service), true);
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.run.controller.createIntent.requestId), 'unresolved-create-fixture');
    assert.equal(await page.locator('#unitModelSelect').inputValue(), 'pir');
    assert.equal(await page.locator('#startBtn').isDisabled(), true);
    assert.equal(candidateUnitReads, 0, 'candidate Units are not committed before the old owner is resolved');
    await assertServiceConsoleLinks(originalService);
    await page.evaluate(() => {window.__serviceStopFixture.allow = true;});
    await page.locator('#serviceUrl').fill(candidateService);
    await page.locator('#connectServiceBtn').click();
    await page.waitForFunction((url) => window.__publicWorkbenchProbe.service?.url === url, candidateService);
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.run), null);
    assert.equal(await page.evaluate(() => window.__publicWorkbenchProbe.stopUnconfirmed), false);
    assert.deepEqual(await page.evaluate(() => window.__serviceStopFixture.stopServices), [originalService, originalService]);
    assert.equal(await page.locator('#startBtn').isEnabled(), true);
    assert.equal(candidateUnitReads, 1);
    await assertServiceConsoleLinks(candidateService);
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
      assert.equal(await page.locator('[data-view="shell"]').textContent(), '屏幕');
      const firstApplicationMs = Date.now() - started;
      const canvas = page.locator('#deviceMount .device-screen');
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
        const result = await canvas.evaluate(async (canvas) => {
          const context = canvas.getContext('2d'),
            all = context.getImageData(0, 0, canvas.width, canvas.height).data;
          const region = context.getImageData(30, 270, 160, 160).data;
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
            width: canvas.width,
            height: canvas.height,
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
        const box = await canvas.boundingBox();
        await page.mouse.move(box.x + (116 * box.width) / 540, box.y + (330 * box.height) / 960);
        await page.mouse.down();
        await advance(0.15);
        await page.mouse.up();
        await advance(4.5);
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
          const body = document.querySelector('[data-device="papers3"].device-body').getBoundingClientRect();
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
