// Opt-in same-guest test for an explicit StackChan merged firmware. No binary
// or ROM is bundled; production site files are served without modification.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {dirname,extname,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {capturePublicQemuProvenance} from './public_qemu_artifacts.mjs';
import {observeWorkerTargets} from './public_qemu_worker_targets.mjs';

if (!process.env.M5_PUBLIC_SITE || !process.env.M5_STACKCHAN_IMAGE) {
  console.log('SKIP: explicit M5_PUBLIC_SITE/M5_STACKCHAN_IMAGE required');
  process.exit(0);
}

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const site = resolve(process.env.M5_PUBLIC_SITE);
const image = resolve(process.env.M5_STACKCHAN_IMAGE);
const out = resolve(process.env.M5_STACKCHAN_OUT || resolve(repo, '.work/stackchan-dance-user-firmware'));
assert.ok(out.startsWith(resolve(repo) + '/.work/'), 'Raw execution evidence must stay in ignored .work');
await mkdir(out, {recursive:false});
const sha = value => createHash('sha256').update(value).digest('hex');
const imageSHA = sha(await readFile(image));
assert.equal(imageSHA, process.env.M5_STACKCHAN_IMAGE_SHA256, 'Explicit firmware identity required');
assert.match(process.env.M5_STACKCHAN_WASM_SHA256 || '', /^[a-f0-9]{64}$/, 'Explicit WASM identity required');
assert.match(process.env.M5_STACKCHAN_MANIFEST_SHA256 || '', /^[a-f0-9]{64}$/, 'Explicit site manifest identity required');

const provenance = await capturePublicQemuProvenance({
  repo, site, testScript:'platform/tests/test_stackchan_dance_user_firmware.mjs',
});
const manifestBytes = await readFile(resolve(site, 'public-site-manifest.json'));
const manifest = JSON.parse(manifestBytes);
assert.equal(sha(manifestBytes), process.env.M5_STACKCHAN_MANIFEST_SHA256);
assert.equal(
  manifest.assets.find(row => row.path === 'platform/runtime/qemu/qemu-system-xtensa.wasm')?.sha256,
  process.env.M5_STACKCHAN_WASM_SHA256,
);

const report = {
  kind:'stackchan-user-firmware-dance-motion',
  status:'FAIL',
  started_at:new Date().toISOString(),
  firmware_sha256:imageSHA,
  wasm_sha256:process.env.M5_STACKCHAN_WASM_SHA256,
  site_manifest_sha256:process.env.M5_STACKCHAN_MANIFEST_SHA256,
  provenance,
  hardware_validation:'NOT RUN',
  checks:[],
  frames:[],
  samples:[],
};
const checks = [];
const check = (name, ok, detail) => {
  checks.push({name, ok:Boolean(ok), detail});
  console.log(name, ok ? 'PASS' : 'FAIL');
};

const mime = {
  '.html':'text/html', '.js':'text/javascript', '.mjs':'text/javascript',
  '.json':'application/json', '.wasm':'application/wasm', '.css':'text/css',
  '.png':'image/png', '.webp':'image/webp', '.svg':'image/svg+xml', '.woff2':'font/woff2',
};
const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (!pathname.startsWith(manifest.base_path)) {
      response.writeHead(404).end();
      return;
    }
    const file = resolve(site, decodeURIComponent(pathname.slice(manifest.base_path.length)) || 'index.html');
    if (!file.startsWith(site + '/')) {
      response.writeHead(403).end();
      return;
    }
    const bytes = await readFile(file);
    response.writeHead(200, {
      'content-type':mime[extname(file)] || 'application/octet-stream',
      'cache-control':'no-cache',
    });
    response.end(bytes);
  } catch {
    response.writeHead(404).end();
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
report.url = `http://127.0.0.1:${server.address().port}${manifest.base_path}`;

const modules = process.env.M5_WASM_NODE_MODULES || resolve(repo, 'platform/tests/node_modules');
const {chromium} = await import(pathToFileURL(resolve(modules, 'playwright/index.mjs')));
let browser, context, page, targets;
try {
  browser = await chromium.launch({
    headless:true,
    executablePath:process.env.M5_WASM_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args:process.env.M5_WASM_GPU === 'hardware'
      ? ['--enable-webgl','--use-gl=angle','--use-angle=metal','--ignore-gpu-blocklist']
      : ['--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'],
  });
  report.browser = browser.version();
  targets = await observeWorkerTargets(browser);
  context = await browser.newContext({viewport:{width:1400,height:1100}});
  page = await context.newPage();
  const requests = [];
  const blocked = [];
  const pageErrors = [];
  report.requests = requests;
  report.blocked = blocked;
  report.page_errors = pageErrors;
  page.on('request', request => requests.push(request.url()));
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.route(
    url => [8787,8830].includes(Number(url.port)) || /\/api\/v1(?:\/|$)/.test(url.pathname),
    route => {
      blocked.push(route.request().url());
      return route.abort('blockedbyclient');
    },
  );
  await page.goto(report.url, {waitUntil:'domcontentloaded'});
  await page.waitForFunction(
    () => crossOriginIsolated && document.querySelector('#deviceMount')?.dataset.deviceId === 'cores3',
    {},
    {timeout:45000},
  );
  await page.evaluate(async origin => {
    const {ModelDeviceShell} = await import(new URL('platform/web/model-shell.js?v=20261026h', origin));
    const create = ModelDeviceShell.create;
    ModelDeviceShell.create = async function (...args) {
      const shell = await create.apply(this, args);
      if (args[1].id === 'stackchan') globalThis.stackchanShell = shell;
      return shell;
    };
    const {PublicQemuRuntime} = await import(new URL('platform/web/public-qemu-runtime.js', origin));
    const {sha256Bytes} = await import(new URL('platform/web/sha256.js', origin));
    const start = PublicQemuRuntime.prototype.start;
    PublicQemuRuntime.prototype.start = function (...args) {
      if (args[0].device === 'stackchan') {
        const runtime = this;
        const onSerial = this.onSerial;
        const onFrame = this.onFrame;
        const onDeviceState = this.onDeviceState;
        const onError = this.onError;
        globalThis.stackchanRun = {
          runtime, serial:'', samples:[], frames:[], errors:[],
        };
        this.onSerial = text => {
          onSerial(text);
          globalThis.stackchanRun.serial += text;
        };
        this.onError = error => {
          globalThis.stackchanRun.errors.push(error.message);
          onError(error);
        };
        this.onDeviceState = value => {
          try {
            onDeviceState(value);
            const mount = document.querySelector('#deviceMount');
            const shell = globalThis.stackchanShell;
            globalThis.stackchanRun.samples.push({
              wall_ms:performance.now(),
              state:structuredClone(value),
              yaw:shell.model.find('yaw', 'joint').getState(),
              pitch:shell.model.find('pitch', 'joint').getState(),
              dom:{
                yawTicks:Number(mount.dataset.servoYawTicks),
                pitchTicks:Number(mount.dataset.servoPitchTicks),
                packets:Number(mount.dataset.servoPackets),
                label:mount.dataset.outputLabel || '',
                frameStatus:document.querySelector('#frameStatus')?.textContent || '',
              },
            });
          } catch (error) {
            globalThis.stackchanRun.errors.push(`onDeviceState: ${error.stack || error}`);
            throw error;
          }
        };
        this.onFrame = frame => {
          onFrame(frame);
          globalThis.stackchanRun.frames.push({
            wall_ms:performance.now(),
            sequence:frame.sequence,
            sha256:sha256Bytes(frame.pixels),
          });
        };
      }
      return start.apply(this, args);
    };
  }, report.url);

  await page.locator('button[data-device-id="stackchan"]').click();
  await page.waitForFunction(
    () => globalThis.stackchanShell?.device.id === 'stackchan',
    {},
    {timeout:45000},
  );
  await page.locator('.advanced-options > summary').click();
  await page.locator('#runtimeMode').selectOption('browser');
  await page.locator('input[name="firmwareSource"][value="local"]').check();
  await page.locator('#firmwareFile').setInputFiles(image);
  await page.locator('#firmwareSha').fill(imageSHA);
  await page.waitForFunction(() => !document.querySelector('#startBtn').disabled);
  await page.locator('#startBtn').click();
  await page.waitForFunction(
    () => globalThis.stackchanRun?.runtime.receipt && globalThis.stackchanRun.samples.length >= 3,
    {},
    {timeout:90000},
  );
  const receipt = await page.evaluate(() => globalThis.stackchanRun.runtime.receipt);
  assert.equal(receipt.firmwareSha256, imageSHA);
  assert.equal(receipt.wasmSha256, process.env.M5_STACKCHAN_WASM_SHA256);
  assert.equal(receipt.outputTransport, 'stackchan-scs-qom-v1');
  assert.equal(receipt.clockDivisor, 6);
  check('exact-image-runtime-and-output-transport', true, receipt);

  await page.waitForFunction(() => {
    const states = globalThis.stackchanRun.samples.map(sample => sample.state);
    if (states.length < 8) return false;
    const present = axis => states.map(state => state.servos[axis].present_position);
    const yaw = present(0);
    const pitch = present(1);
    return Math.max(...yaw) - Math.min(...yaw) >= 200
      && Math.max(...pitch) - Math.min(...pitch) >= 60
      && states.some(state => state.packets >= 30);
  }, {}, {timeout:60000});

  const run = await page.evaluate(() => ({
    serial:globalThis.stackchanRun.serial,
    samples:globalThis.stackchanRun.samples,
    frames:globalThis.stackchanRun.frames,
    errors:globalThis.stackchanRun.errors,
    receipt:globalThis.stackchanRun.runtime.receipt,
    status:globalThis.stackchanRun.runtime.status,
    evidence:globalThis.stackchanRun.runtime.evidence(),
  }));
  report.samples = run.samples;
  report.frames = run.frames;
  const visualTrace = await page.evaluate(async () => {
    const trace=[],start=performance.now();
    while(performance.now()-start<2000){
      const joint=globalThis.stackchanShell.model.find('yaw','joint').getState();
      trace.push({wall_ms:performance.now(),angleDeg:joint.angleDeg,targetAngleDeg:joint.targetAngleDeg,
        transitioning:joint.transitioning});
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    return trace;
  });
  report.visual_trace = visualTrace;
  const visualFrames = visualTrace.filter((sample,index) =>
    index > 0 && sample.angleDeg !== visualTrace[index-1].angleDeg).length;
  const states = run.samples.map(sample => sample.state);
  const present = axis => states.map(state => state.servos[axis].present_position);
  const goals = axis => states.map(state => state.servos[axis].goal_position);
  const span = values => Math.max(...values) - Math.min(...values);
  report.ranges = {
    yaw_present:[Math.min(...present(0)), Math.max(...present(0))],
    pitch_present:[Math.min(...present(1)), Math.max(...present(1))],
    yaw_goal:[Math.min(...goals(0)), Math.max(...goals(0))],
    pitch_goal:[Math.min(...goals(1)), Math.max(...goals(1))],
  };
  check('actual-SCS-present-position-moves', span(present(0)) >= 200 && span(present(1)) >= 60, report.ranges);
  check(
    'firmware-commands-reach-three-yaw-and-pitch-targets',
    Math.min(...goals(0)) <= 340 && Math.max(...goals(0)) >= 590
      && Math.min(...goals(1)) <= 690 && Math.max(...goals(1)) >= 830,
    report.ranges,
  );
  check(
    'packets-accepted-with-live-uart-and-torque',
    states.every(state => state.packets >= 0 && state.rejected_packets === 0)
      && states.some(state => state.packets >= 30 && state.uart_tx_connected && state.uart_rx_connected)
      && states.some(state => state.powered && state.servos.every(servo => servo.torque === 1)),
    states.at(-1),
  );
  const expectedYaw = sample => (sample.state.servos[0].present_position - 460) * 5 / 16;
  const expectedPitch = sample => Math.max(0, Math.min(90,
    (sample.state.servos[1].present_position - 620) * 5 / 16));
  const observedChanges = run.samples.slice(1).filter((sample, index) => {
    const previous = run.samples[index];
    return sample.state.packets !== previous.state.packets
      && (sample.state.servos[0].present_position !== previous.state.servos[0].present_position
        || sample.state.servos[1].present_position !== previous.state.servos[1].present_position);
  });
  check(
    'model-joint-target-follows-present-with-presentation-interpolation',
    observedChanges.length > 0 && observedChanges.every(sample =>
      sample.yaw.targetAngleDeg === expectedYaw(sample)
      && sample.pitch.targetAngleDeg === expectedPitch(sample)
      && (sample.state.servos[0].present_position === run.samples[run.samples.indexOf(sample) - 1].state.servos[0].present_position
        || sample.yaw.transitioning)
      && (sample.state.servos[1].present_position === run.samples[run.samples.indexOf(sample) - 1].state.servos[1].present_position
        || sample.pitch.transitioning)),
    {samples:run.samples.length, observed_changes:observedChanges.length},
  );
  check(
    'three-d-presentation-emits-intermediate-poses',
    visualFrames >= 5,
    {samples:visualTrace.length, changed_frames:visualFrames},
  );
  check(
    'dom-ticks-and-angle-label-consume-the-same-snapshot',
    run.samples.every(sample =>
      sample.dom.yawTicks === sample.state.servos[0].present_position
      && sample.dom.pitchTicks === sample.state.servos[1].present_position
      && sample.dom.packets === sample.state.packets
      && sample.dom.label.includes(expectedYaw(sample).toFixed(1))
      && sample.dom.label.includes(expectedPitch(sample).toFixed(1))),
    run.samples.at(-1),
  );
  check('guest-started-and-initialized-servo-bus', /StackChan auto-dance started/.test(run.serial)
    && /SERVO ready zeroX=460 zeroY=620 torque=1/.test(run.serial), run.serial.slice(-1000));
  check('display-frames-observed', run.frames.length > 1, {frames:run.frames.length});
  check('same-guest-alive-and-error-free', run.status === 'running' && !run.errors.length && !pageErrors.length,
    {status:run.status, errors:run.errors, pageErrors});
  check('no-protected-services-used', blocked.length === 0, blocked);

  await page.screenshot({path:resolve(out, 'stackchan-dance.png'), fullPage:true});
  report.screenshot = {
    path:'stackchan-dance.png',
    sha256:sha(await readFile(resolve(out, 'stackchan-dance.png'))),
  };
  await page.locator('#stopBtn').click();
  await page.waitForFunction(
    () => globalThis.stackchanRun.runtime.status === 'stopped' && !globalThis.stackchanRun.runtime.iframe,
    {},
    {timeout:45000},
  );
  report.cleanup = await page.evaluate(() => globalThis.stackchanRun.runtime.evidence().cleanup);
  report.worker_targets = await targets.waitUntilClosed({minimumObserved:6, timeoutMs:120000});
  check('normal-stop-cleanly-closes-qemu-worker',
    report.worker_targets.ok && await page.locator('iframe').count() === 0,
    report.worker_targets,
  );
  assert.ok(checks.every(row => row.ok), 'StackChan dance checks failed');
  report.status = 'PASS';
} catch (error) {
  report.error = String(error.stack || error);
  if (page) {
    try {
      report.failure_state = await page.evaluate(() => globalThis.stackchanRun ? {
        serial:globalThis.stackchanRun.serial,
        samples:globalThis.stackchanRun.samples,
        frames:globalThis.stackchanRun.frames,
        errors:globalThis.stackchanRun.errors,
        receipt:globalThis.stackchanRun.runtime.receipt,
        status:globalThis.stackchanRun.runtime.status,
        evidence:globalThis.stackchanRun.runtime.evidence(),
      } : null);
    } catch (snapshotError) {
      report.failure_snapshot_error = String(snapshotError);
    }
  }
  console.error(report.error);
  process.exitCode = 1;
} finally {
  report.finished_at = new Date().toISOString();
  report.checks = checks;
  await writeFile(resolve(out, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  await targets?.detach();
  await context?.close();
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
  console.log('BROWSER_WINDOW_RELEASED');
}
