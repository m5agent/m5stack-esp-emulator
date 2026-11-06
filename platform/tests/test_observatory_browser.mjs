// Opt-in acceptance of the local read-only observatory. Real guest runs and
// logical display-pressure fixtures are reported separately.
import assert from 'node:assert/strict';
import {createHash, randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {mkdir, readFile, readdir, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const sha = value => createHash('sha256').update(value).digest('hex');
const args = process.argv.slice(2);
const option = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;

export function observatoryAcceptancePlan() {
  return {
    kind: 'local-observatory-acceptance-plan', status: 'NOT RUN',
    execute: 'node platform/tests/test_observatory_browser.mjs --execute --service <owned-loopback-service> --token-file <private-file> --out <new-.work-directory>',
    real_guest_scope: ['Mixed and repeated models, same-session screen/Unit/serial observations',
      'Black-screen short task, stop and purge between observer refreshes',
      'Automatic overview/group/device tour and serial presentation without user input',
      'Owned guest abnormal exit, observer close without guest stop', 'Default 12-session / 8-per-model capacity'],
    display_fixture_scope: ['64 logical sessions; group layout and churn only', '1920 / 1440 / 390 viewport checks'],
    excluded: ['Browser-WASM firmware execution', 'Physical hardware', 'Performance claims'],
  };
}

export function validateOptions(options) {
  assert.ok(options.service && options.token_file && options.out, 'Explicit service, token file and output directory required');
  const service = new URL(options.service);
  assert.ok(service.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(service.hostname)
    && service.port && !['8787', '8830'].includes(service.port) && service.pathname === '/'
    && !service.username && !service.password && !service.search && !service.hash,
  'Use an explicitly owned loopback HTTP service, never user test ports');
  const output = resolve(options.out);
  assert.ok(output.startsWith(resolve(root, '.work') + '/'), 'Evidence must be in a new ignored .work directory');
  return {service, output};
}

function processIdentity(pid, python) {
  assert.ok(Number.isSafeInteger(pid) && pid > 0);
  return JSON.parse(execFileSync(python, ['-c', `import ctypes,hashlib,json,pathlib,sys
p=int(sys.argv[1])
if sys.platform=='darwin':
 b=ctypes.create_string_buffer(4096)
 assert ctypes.CDLL('/usr/lib/libproc.dylib').proc_pidpath(p,b,len(b))>0
 f=pathlib.Path(b.value.decode())
else: f=(pathlib.Path('/proc')/str(p)/'exe').resolve()
print(json.dumps({'executable_name':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}))`, String(pid)], {encoding: 'utf8'}));
}

function fixtureSource(nonce, {black = false, relay = false, pins} = {}) {
  // API spelling/rotation and RelayUnit methods follow the bundled official
  // uiflow2-coder display.md / relay.md documents; pins come from service data.
  return `import M5,time\n${relay ? 'from unit import RelayUnit\n' : ''}M5.begin()\nM5.Lcd.setRotation(0)\nM5.Lcd.setBrightness(255)\n`
    + (relay ? `relay=RelayUnit((${pins.white},${pins.yellow}))\n` : '')
    + `phase=0\nwhile True:\n M5.update()\n`
    + (relay ? ' relay.set_status(bool(phase))\n' : '')
    + ` M5.Lcd.fillScreen(${black ? '0' : '0x00FF00 if phase else 0xFF0000'})\n`
    + ` print('OBS_${nonce}',phase${relay ? ',int(relay.get_status())' : ''})\n phase=1-phase\n time.sleep_ms(1000)\n`;
}

export async function execute(options) {
  const {service, output} = validateOptions(options), origin = service.origin;
  const token = (await readFile(resolve(options.token_file), 'utf8')).trim();
  assert.ok(token.length >= 32, 'Use a dedicated private control token');
  await mkdir(output, {recursive: false});
  const python = options.python || process.env.M5_PYTHON || 'python3';
  const report = {kind: 'local-observatory-acceptance', status: 'FAIL', started_at: new Date().toISOString(),
    evidence_level: 'virtual-device validation', hardware_validation: 'NOT RUN',
    scope: observatoryAcceptancePlan(), checks: [], sessions: [], http: [], browser_http: [], page_errors: [],
    frames: [], screenshots: [], automatic_tour: [], display_pressure: {status: 'NOT RUN', label: 'logical display-pressure fixture; no guest execution'}};
  const save = (name, value) => writeFile(resolve(output, name), JSON.stringify(value, null, 2) + '\n');
  const check = (name, ok, details) => { report.checks.push({name, ok, details}); assert.ok(ok, name); console.log(name); };
  const owned = new Map();
  let browser, page, pressurePage;
  let observerHeld = false, releaseObserver;
  let observerGate = Promise.resolve();

  async function sampleTour() {
    if (!page || page.isClosed()) return;
    try {
      const sample = await page.evaluate(() => {
        const probe = globalThis.__observatoryProbe;
        if (!probe?.scene) return null;
        const presentation = probe.tour?.snapshot();
        return {session_id: probe.selectedSessionId ?? probe.scene.selectedSessionId ?? null,
          group_id: presentation?.groupId || probe.scene.selectedGroupId || null,
          phase: presentation?.phase, camera_session_id: probe.scene.selectedSessionId,
          detail_title: document.querySelector('#detailTitle')?.textContent || ''};
      });
      if (!sample) return;
      sample.phase ||= sample.camera_session_id ? 'device' : sample.group_id ? 'group' : 'overview';
      const prior = report.automatic_tour.at(-1);
      if (!prior || prior.phase !== sample.phase || prior.session_id !== sample.session_id || prior.group_id !== sample.group_id) {
        report.automatic_tour.push({...sample, observed_at: new Date().toISOString()});
      }
    } catch {}
  }

  async function api(path, {method = 'GET', body, binary = false, allowError = false, timeout = 30000} = {}) {
    const response = await fetch(origin + '/api/v1/' + path, {method,
      headers: {Authorization: `Bearer ${token}`, ...(body === undefined ? {} : {'Content-Type': 'application/json'})},
      ...(body === undefined ? {} : {body: JSON.stringify(body)}), signal: AbortSignal.timeout(timeout)});
    const bytes = Buffer.from(await response.arrayBuffer());
    report.http.push({path, method, status: response.status, bytes: bytes.length, sha256: sha(bytes)});
    if (!allowError) assert.ok(response.ok, `${method} ${path}: HTTP ${response.status}: ${bytes.toString().slice(0, 500)}`);
    return binary ? {bytes, headers: Object.fromEntries(response.headers), status: response.status}
      : {...JSON.parse(bytes), ...(allowError ? {http_status: response.status} : {})};
  }
  async function until(read, predicate, timeout = 60000) {
    const end = Date.now() + timeout;
    for (;;) {
      await sampleTour();
      const result = await read();
      if (predicate(result)) return result;
      if (Date.now() >= end) throw Error('Observatory acceptance observation deadline exceeded');
      await delay(150);
    }
  }
  async function create(payload, name) {
    const admitted = await api('sessions', {method: 'POST', body: {ttl_seconds: 900, ...payload}});
    assert.ok(admitted.session_id, JSON.stringify(admitted));
    owned.set(admitted.session_id, admitted);
    const session = await until(() => api('sessions/' + admitted.session_id),
      value => ['running', 'failed', 'stopped'].includes(value.state), 180000);
    const record = {name, session_id: session.session_id, device_id: session.device_id,
      firmware_sha256: session.firmware_sha256, runtime: session.runtime, state: session.state,
      pid: session.pid, units: session.units, worker: session.worker};
    report.sessions.push(record);
    assert.equal(session.state, 'running', session.error);
    record.runtime_identity = processIdentity(session.pid, python);
    owned.set(session.session_id, session);
    return session;
  }
  async function evidence(id, name) {
    const zip = await api(`sessions/${id}/evidence`, {binary: true});
    assert.equal(zip.bytes.subarray(0, 2).toString(), 'PK');
    await writeFile(resolve(output, name + '.zip'), zip.bytes);
    return {bytes: zip.bytes.length, sha256: sha(zip.bytes)};
  }
  async function stop(id, {purge = false} = {}) {
    const result = await api(`sessions/${id}?purge=${purge ? 1 : 0}`, {method: 'DELETE'});
    if (!purge) assert.ok(['stopped', 'failed'].includes(result.state), JSON.stringify(result));
    owned.delete(id);
    return result;
  }
  async function cleanupOwned() {
    for (const [id, identity] of [...owned]) {
      try { await evidence(id, 'cleanup-' + id.slice(0, 8)); }
      catch (error) {
        report.cleanup_errors ||= []; report.cleanup_errors.push({session_id: id, phase: 'evidence', error: String(error)});
        report.status = 'FAIL'; process.exitCode = 1;
      }
      try {
        const result = await stop(id);
        if (identity.pid) await until(async () => {
          try { process.kill(identity.pid, 0); return false; }
          catch (error) { if (error.code === 'ESRCH') return true; throw error; }
        }, Boolean, 15000);
        report.cleanup ||= []; report.cleanup.push({session_id: id, state: result.state,
          flash_retained: result.flash_retained, owned_pid_gone: true});
      } catch (error) {
        report.cleanup_errors ||= []; report.cleanup_errors.push({session_id: id, phase: 'stop', error: String(error)});
        report.status = 'FAIL'; process.exitCode = 1;
      }
    }
  }
  async function screenshot(width, height, name) {
    await page.setViewportSize({width, height});
    await delay(700);
    const layout = await page.evaluate(() => ({width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
      height: innerHeight, scrollHeight: document.documentElement.scrollHeight, canvasCount: document.querySelectorAll('canvas').length}));
    check(name + '-no-horizontal-overflow', layout.scrollWidth <= layout.width + 1, layout);
    if (width >= 1440) check(name + '-fits-one-screen-height', layout.scrollHeight <= layout.height + 1, layout);
    await page.screenshot({path: resolve(output, name + '.png'), fullPage: true});
    report.screenshots.push({name, width, height});
  }
  async function noInteractiveControls(target, name) {
    const visible = await target.evaluate(() => [...document.querySelectorAll('button,input,select,textarea,a,[tabindex],[role="button"],[contenteditable="true"]')]
      .filter(element => {
        if (element.hasAttribute('tabindex') && element.tabIndex < 0 && !element.matches('button,input,select,textarea,a,[role="button"],[contenteditable="true"]')) return false;
        const style = getComputedStyle(element), box = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
      }).map(element => ({tag: element.tagName, id: element.id, role: element.getAttribute('role'), tabindex: element.getAttribute('tabindex')})));
    check(name + '-has-no-visible-interactive-controls', visible.length === 0, visible);
  }
  async function pixels(bytes) {
    return page.evaluate(async base64 => {
      const bytes = Uint8Array.from(atob(base64), value => value.charCodeAt(0));
      const image = await createImageBitmap(new Blob([bytes], {type: 'image/png'}));
      try {
        const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
        const context = canvas.getContext('2d'); context.drawImage(image, 0, 0);
        const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
        let nonblack = 0;
        for (let index = 0; index < data.length; index += 4) if (data[index] || data[index + 1] || data[index + 2]) nonblack++;
        return {width: image.width, height: image.height, corner: Array.from(data.slice(0, 4)), nonblack_pixels: nonblack};
      } finally { image.close(); }
    }, bytes.toString('base64'));
  }

  try {
    const sources = [...(await readdir(resolve(root, 'platform/web'))).filter(name => /^observatory(?:-.*)?\.(?:js|html|css)$/.test(name))
      .map(name => 'platform/web/' + name), 'platform/web/model-output.js', 'platform/web/unit-visual-mappings.js',
      'platform/web/unit-assembly-layout.js', 'platform/web/vendor/m5stack-models/vendor-manifest.json',
      'platform/tools/device_service.py', 'platform/tools/serve.py',
      'platform/tools/observation_store.py', 'platform/tests/test_observatory_browser.mjs'];
    report.source_sha256 = Object.fromEntries(await Promise.all(sources.map(async path => [path, sha(await readFile(resolve(root, path)))])));
    const health = await api('health');
    check('dedicated-service-starts-empty', health.capacity.active_sessions === 0);
    const devices = await api('devices');
    const core = devices.devices.find(x => x.device_id === 'cores3');
    const atom = devices.devices.find(x => x.device_id === 'atoms3r');
    check('native-reference-backends-ready', core?.creatable && atom?.creatable);
    const units = await api('units?device_id=cores3');
    await save('unit-inventory.json', units);
    // The admitted session supplies the final frozen pin tuple. This first
    // reference guest is also retained as part of the mixed-model display.
    const initial = await create({device_id: 'cores3', units: [{id: 'relay1', unit_id: 'relay', port_id: 'port-a'}],
      program_mode: 'uiflow-live'}, 'live-relay');
    const nonce = randomUUID().replaceAll('-', '');
    const program = fixtureSource(nonce, {relay: true, pins: initial.units[0].pins});
    const executed = await api(`sessions/${initial.session_id}/program`, {method: 'POST',
      body: {source: program, expected_execution_id: null, timeout_seconds: 15}, timeout: 30000});
    report.program = {source_sha256: sha(program), execution: executed, nonce};
    await until(() => api(`sessions/${initial.session_id}/serial?offset=0&limit=65536`), value => value.data.includes(`OBS_${nonce}`), 120000);
    const repeated = [initial];
    for (let i = 0; i < 2; i++) repeated.push(await create({device_id: 'cores3'}, 'same-model-' + i));
    const different = await create({device_id: 'atoms3r'}, 'different-model');

    const {chromium} = await import('playwright');
    browser = await chromium.launch({headless: true,
      executablePath: options.chrome || process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      args: ['--use-gl=angle', '--use-angle=metal', '--enable-webgl', '--ignore-gpu-blocklist']});
    report.browser_version = browser.version();
    const context = await browser.newContext({viewport: {width: 1920, height: 1080}});
    await context.addInitScript(value => sessionStorage.setItem('m5-service-token', value), token);
    page = await context.newPage();
    page.on('pageerror', error => report.page_errors.push(error.message));
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.origin === origin && url.pathname.startsWith('/api/v1/')) {
        report.browser_http.push({method: request.method(), path: url.pathname});
      }
    });
    await page.route('**/api/v1/observatory/**', async route => {
      if (observerHeld) await observerGate;
      await route.continue();
    });
    const document = await page.goto(origin + '/observatory', {waitUntil: 'domcontentloaded'});
    assert.ok(document.ok());
    await page.waitForFunction(() => !!globalThis.__observatoryProbe?.scene, undefined, {timeout: 60000});
    await until(() => page.locator(`[data-session-id="${initial.session_id}"]`).count(), n => n > 0);
    check('external-mixed-and-repeated-sessions-discovered', await page.locator('[data-session-id]').count() >= 4);
    await noInteractiveControls(page, 'automatic-display');
    await until(() => page.evaluate(id => globalThis.__observatoryProbe?.selectedSessionId === id, initial.session_id), Boolean, 180000);
    await until(async () => ({selected: await page.evaluate(() => globalThis.__observatoryProbe?.selectedSessionId),
      serial: await page.locator('#detailSerial').innerText()}), value => value.selected === initial.session_id && value.serial.includes(`OBS_${nonce}`), 180000);
    check('automatically-focused-serial-is-actual-same-session-output', true);
    const automaticSerial = await until(() => page.evaluate(id => {
      if (globalThis.__observatoryProbe?.selectedSessionId !== id) return null;
      const serial = document.querySelector('#detailSerial');
      return {scroll_top: serial.scrollTop, scroll_height: serial.scrollHeight, client_height: serial.clientHeight};
    }, initial.session_id), sample => sample && sample.client_height >= 60 && sample.scroll_height > sample.client_height && sample.scroll_top > 0, 180000);
    check('serial-output-follows-tail-without-user-scroll', true, automaticSerial);

    const visualColors = new Set(), unitLevels = new Set();
    await until(async () => {
      const visual = await page.evaluate(id => {
        const scene = globalThis.__observatoryProbe?.scene, record = scene?.records.get(id);
        const display = record?.model?.find('lcd', 'display');
        const snapshot = scene?.snapshot().sessions.find(row => row.session_id === id);
        return {pixel: display ? Array.from(display.getPixel(0, 0)) : null, snapshot};
      }, initial.session_id);
      if (visual.pixel && (visual.pixel[0] > 240 || visual.pixel[1] > 240)) visualColors.add(visual.pixel.slice(0, 3).join(','));
      const level = visual.snapshot?.units?.[0]?.properties?.['output-level'];
      if (typeof level === 'boolean') unitLevels.add(level);
      return visual;
    }, visual => visualColors.size >= 2 && unitLevels.size >= 2 && visual.snapshot?.attached_units.includes('relay1'), 45000);
    report.model_observations = {screen_colors: [...visualColors], unit_output_levels: [...unitLevels]};
    check('actual-screen-changes-reach-corresponding-3d-display', visualColors.has('255,0,0') && visualColors.has('0,255,0'), report.model_observations);
    check('actual-unit-output-changes-reach-corresponding-scene', unitLevels.size === 2);

    for (let i = 0; i < 2; i++) {
      const sample = await until(() => api(`sessions/${initial.session_id}/units`), x => x.units?.[0]?.available);
      report.unit_observations ||= []; report.unit_observations.push(sample);
      await delay(1100);
    }
    check('relay-actual-controller-output-observed', report.unit_observations.every(x => typeof x.units[0].properties?.['output-level'] === 'boolean'));
    for (let i = 0; i < 2; i++) {
      const frame = await api(`sessions/${initial.session_id}/frame.png?max_age_ms=1`, {binary: true});
      await writeFile(resolve(output, `live-frame-${i}.png`), frame.bytes);
      report.frames.push({name: `live-frame-${i}`, session_id: initial.session_id, bytes: frame.bytes.length,
        sha256: sha(frame.bytes), headers: frame.headers, pixels: await pixels(frame.bytes)});
      await delay(1100);
    }
    check('same-guest-screen-observed', report.frames.every(x => x.bytes > 0 && x.pixels.width === 320 && x.pixels.height === 240
      && (x.pixels.corner[0] > 240 || x.pixels.corner[1] > 240)));
    await until(async () => report.automatic_tour, samples => {
      const phases = new Set(samples.map(sample => sample.phase));
      const devices = new Set(samples.map(sample => sample.session_id).filter(Boolean));
      return ['overview', 'group', 'device'].every(phase => phases.has(phase)) && devices.size >= 2;
    }, 180000);
    check('overview-group-and-multiple-device-tour-advances-without-input', true, report.automatic_tour);
    await screenshot(1920, 1080, 'observatory-1920');
    await screenshot(1440, 900, 'observatory-1440');
    await screenshot(390, 844, 'observatory-390');
    await page.setViewportSize({width: 1920, height: 1080});

    observerHeld = true;
    observerGate = new Promise(resolveGate => { releaseObserver = resolveGate; });
    const shortNonce = randomUUID().replaceAll('-', '');
    const shortSource = fixtureSource(shortNonce, {black: true});
    const short = await create({device_id: 'cores3', program_mode: 'uiflow-live'}, 'black-screen-short');
    const shortExecution = await api(`sessions/${short.session_id}/program`, {method: 'POST',
      body: {source: shortSource, expected_execution_id: null, timeout_seconds: 15}});
    const serial = await until(() => api(`sessions/${short.session_id}/serial?offset=0&limit=65536`), x => x.data.includes(`OBS_${shortNonce}`));
    const black = await api(`sessions/${short.session_id}/frame.png?max_age_ms=1`, {binary: true});
    await writeFile(resolve(output, 'short-black-frame.png'), black.bytes);
    report.short_task = {session_id: short.session_id, firmware_sha256: short.firmware_sha256,
      source_sha256: sha(shortSource), execution: shortExecution, serial_sha256: sha(serial.data), serial_bytes: serial.next_offset,
      frame_sha256: sha(black.bytes), frame_headers: black.headers, pixels: await pixels(black.bytes), evidence: await evidence(short.session_id, 'short-before-stop')};
    check('short-task-frame-is-actually-black', report.short_task.pixels.nonblack_pixels === 0);
    await stop(short.session_id);
    await api(`sessions/${short.session_id}?purge=1`, {method: 'DELETE'});
    const observed = await api('observatory/snapshot');
    check('purged-short-task-survives-in-observation-index', [...observed.active, ...observed.recent].some(x => x.session_id === short.session_id && x.purged));
    observerHeld = false; releaseObserver();
    await until(() => page.locator(`.observatory-device-label[data-session-id="${short.session_id}"]`).count(), count => count > 0);
    const shortBadge = page.locator(`.observatory-device-label[data-session-id="${short.session_id}"]`);
    await until(() => shortBadge.getAttribute('data-state'), state => state === 'stopped');
    await until(() => page.evaluate(() => globalThis.__observatoryProbe?.tour.snapshot().phase), phase => phase === 'overview', 5000);
    const shortActivity = await page.locator(`[data-activity-session="${short.session_id}"]`).innerText();
    assert.ok(shortActivity.includes('已结束') && shortActivity.includes('详情已清理') && !/PASS|通过/.test(shortActivity));
    await page.screenshot({path: resolve(output, 'short-ended-after-purge.png'), fullPage: true});
    check('short-task-ended-before-observer-is-presented', true);
    check('new-short-task-lifecycle-is-shown-in-overview', true);

    report.abnormal = {session_id: different.session_id, pid: different.pid,
      evidence_before_exit: await evidence(different.session_id, 'abnormal-before-exit')};
    process.kill(different.pid, 'SIGKILL');
    const failed = await until(() => api(`sessions/${different.session_id}`), x => x.state === 'failed');
    report.abnormal.result = failed;
    check('abnormal-exit-is-failed-not-pass', failed.state === 'failed');
    await until(() => page.locator(`.observatory-device-label[data-session-id="${different.session_id}"]`).getAttribute('data-state'), state => state === 'failed');
    await page.screenshot({path: resolve(output, 'abnormal-exit-observed.png'), fullPage: true});
    check('abnormal-exit-reaches-observatory', true);
    await evidence(different.session_id, 'abnormal-after-exit');
    await stop(different.session_id);

    // Fill the service's unchanged defaults without treating process state as
    // application readiness. Existing live guests are part of these 12 slots.
    let capacity = await api('capacity');
    let cores = [...owned.values()].filter(x => x.device_id === 'cores3').length;
    while (cores < 8) { await create({device_id: 'cores3'}, 'capacity-core-' + cores); cores++; }
    const ninthCore = await api('sessions', {method: 'POST', body: {device_id: 'cores3', ttl_seconds: 900}, allowError: true});
    if (ninthCore.session_id) owned.set(ninthCore.session_id, ninthCore);
    check('ninth-same-model-session-remains-rejected', ninthCore.http_status === 429 && ninthCore.error?.code === 'device_capacity_exhausted');
    capacity = await api('capacity');
    while (capacity.active_sessions < 12) {
      await create({device_id: 'atoms3r'}, 'capacity-atom-' + capacity.active_sessions);
      capacity = await api('capacity');
    }
    report.default_capacity = capacity;
    check('unchanged-default-12-total-8-same-model-capacity', capacity.active_sessions === 12 && capacity.max_sessions === 12
      && capacity.max_per_device === 8 && capacity.by_device.cores3 === 8 && capacity.by_device.atoms3r === 4);
    const thirteenth = await api('sessions', {method: 'POST', body: {device_id: 'atoms3r', ttl_seconds: 900}, allowError: true});
    if (thirteenth.session_id) owned.set(thirteenth.session_id, thirteenth);
    check('thirteenth-total-session-remains-rejected', thirteenth.http_status === 429 && thirteenth.error?.code === 'capacity_exhausted');
    await page.close(); page = null;
    const afterClose = await api('capacity');
    check('closing-observer-does-not-stop-external-guests', afterClose.active_sessions === 12);
    check('observatory-browser-requests-are-get-only', report.browser_http.every(x => x.method === 'GET'), report.browser_http.length);
    await cleanupOwned();
    check('real-guests-cleaned-before-display-pressure-fixture', owned.size === 0 && !report.cleanup_errors?.length);

    // Separate synthetic data is used only to stress display/layout behavior.
    const fixtureContext = await browser.newContext({viewport: {width: 1920, height: 1080}});
    await fixtureContext.addInitScript(value => sessionStorage.setItem('m5-service-token', value), token);
    pressurePage = await fixtureContext.newPage();
    const logical = Array.from({length: 64}, (_, i) => ({...initial,
      session_id: (i + 1).toString(16).padStart(32, '0'), device_id: i < 40 ? 'cores3' : 'atoms3r',
      units: [], state: 'running', serial_bytes: i * 101, display_available: false, last_frame_available: false,
      created_at: new Date(Date.now() - 10000).toISOString(), completed_at: null}));
    const fixtureWrites = [];
    const fixtureEvents = [];
    await pressurePage.route('**/api/v1/**', async route => {
      const request = route.request(), url = new URL(request.url());
      if (request.method() !== 'GET') { fixtureWrites.push({path: url.pathname, method: request.method()}); return route.abort(); }
      const common = {journal_id: 'display-fixture', cursor: fixtureEvents.length, status: {state: 'ok', gap_possible: false}};
      let payload;
      if (url.pathname.endsWith('/observatory/snapshot')) payload = {...common, active: logical.filter(x => x.state === 'running'), recent: logical.filter(x => x.state !== 'running'),
        capacity: {active_sessions: 64, max_sessions: 64, available_sessions: 0}, jobs: {available: false, counts: {}}};
      else if (url.pathname.endsWith('/observatory/events')) payload = {...common,
        events: fixtureEvents.filter(x => x.seq > Number(url.searchParams.get('after') || 0)), next_cursor: fixtureEvents.length, has_more: false, resync: false};
      else if (url.pathname === '/api/v1/sessions') payload = {sessions: logical};
      else if (url.pathname === '/api/v1/capacity') payload = {active_sessions: 64, max_sessions: 64, available_sessions: 0};
      else if (/\/sessions\//.test(url.pathname)) {
        if (url.pathname.endsWith('/frame.png')) return route.fulfill({status: 503, contentType: 'application/json',
          body: JSON.stringify({error: {code: 'display_fixture_no_frame', message: 'Logical display fixture has no guest framebuffer'}})});
        payload = url.pathname.endsWith('/serial') ? {data: '', next_offset: 0}
          : url.pathname.endsWith('/units') ? {units: [], definitions: []} : {available: false, visual_commands: []};
      }
      else return route.continue();
      await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(payload)});
    });
    await pressurePage.goto(origin + '/observatory', {waitUntil: 'domcontentloaded'});
    await until(() => pressurePage.locator('[data-session-id]').count(), n => n >= 64, 120000);
    await until(() => pressurePage.evaluate(() => globalThis.__observatoryProbe?.scene.rendererInfo.detailedModels || 0), count => count >= 32, 120000);
    await pressurePage.evaluate(() => {
      const note = document.createElement('div'); note.textContent = '展示压力夹具 · 64 个逻辑会话 · 无 guest 执行';
      Object.assign(note.style, {position: 'fixed', left: '24px', bottom: '18px', zIndex: '10000',
        background: '#fff', border: '1px solid #0282cb', borderRadius: '6px', padding: '10px 16px', fontSize: '13px', color: '#234'});
      document.body.append(note);
    });
    await delay(1500);
    const positionsBefore = await pressurePage.evaluate(() => Object.fromEntries(globalThis.__observatoryProbe.scene.snapshot().sessions.map(row => [row.session_id, row.position])));
    await pressurePage.screenshot({path: resolve(output, 'display-pressure-64-logical.png'), fullPage: true});
    for (let index = 0; index < 8; index++) {
      logical[index] = {...logical[index], state: 'stopped', completed_at: new Date().toISOString()};
      fixtureEvents.push({seq: fixtureEvents.length + 1, kind: 'session', session: logical[index]});
      const replacement = {...logical[index], session_id: (index + 101).toString(16).padStart(32, '0'), state: 'running',
        created_at: new Date().toISOString(), completed_at: null};
      logical.push(replacement);
      fixtureEvents.push({seq: fixtureEvents.length + 1, kind: 'session', session: replacement});
    }
    await until(() => pressurePage.locator(`[data-session-id="${logical[71].session_id}"]`).count(), n => n > 0, 15000);
    assert.ok(await pressurePage.locator(`[data-session-id="${logical[0].session_id}"]`).count(), 'Ended logical device keeps an explicit visual dwell');
    await until(async () => ({count: await pressurePage.locator('.observatory-device-label[data-session-id]').count(),
      firstEnded: await pressurePage.locator(`[data-session-id="${logical[0].session_id}"]`).count()}),
    value => value.count === 64 && value.firstEnded === 0, 20000);
    const afterChurn = await pressurePage.locator('.observatory-device-label[data-session-id]').count();
    assert.equal(afterChurn, 64, 'Ended logical models leave after the visual dwell');
    const positionsAfter = await pressurePage.evaluate(() => Object.fromEntries(globalThis.__observatoryProbe.scene.snapshot().sessions.map(row => [row.session_id, row.position])));
    await save('display-pressure-layout.json', {before: positionsBefore, after: positionsAfter});
    for (const row of logical.slice(8, 64)) assert.ok(positionsAfter[row.session_id]?.every((value, axis) =>
      Math.abs(value - positionsBefore[row.session_id][axis]) < 1e-6),
    `Existing model positions remain stable during churn: ${row.session_id}`);
    await pressurePage.screenshot({path: resolve(output, 'display-pressure-64-after-churn.png'), fullPage: true});
    const pressureLayout = await pressurePage.evaluate(() => ({canvas_count: document.querySelectorAll('canvas').length,
      scroll_width: document.documentElement.scrollWidth, viewport: innerWidth}));
    assert.equal(pressureLayout.canvas_count, 1, 'All devices share one WebGL canvas');
    assert.ok(pressureLayout.scroll_width <= pressureLayout.viewport + 1);
    assert.equal(fixtureWrites.length, 0);
    await noInteractiveControls(pressurePage, 'logical-display');
    report.display_pressure = {...report.display_pressure, status: 'PASS', logical_session_count: 64,
      churn_ended: 8, churn_created: 8, labels_after_dwell: afterChurn, ...pressureLayout};
    check('64-logical-session-display-only-layout', true, report.display_pressure);
    check('no-browser-page-errors', report.page_errors.length === 0, report.page_errors);
    if (!report.cleanup_errors?.length) report.status = 'PASS';
  } catch (error) {
    report.error = String(error?.stack || error);
    if (page && !page.isClosed()) {
      try {
        report.failure_observation = await page.evaluate(() => ({notice: document.querySelector('#notice')?.textContent,
          body: document.body.innerText.slice(0, 12000), scene: globalThis.__observatoryProbe?.scene?.snapshot(),
          connected: globalThis.__observatoryProbe?.store.connected}));
        await page.screenshot({path: resolve(output, 'failure.png'), fullPage: true});
      } catch (observationError) { report.failure_observation_error = String(observationError); }
    }
    process.exitCode = 1;
  } finally {
    observerHeld = false; releaseObserver?.();
    await pressurePage?.close().catch(() => {});
    await page?.close().catch(() => {});
    await cleanupOwned();
    await browser?.close().catch(() => {});
    report.completed_at = new Date().toISOString();
    await save('report.json', report);
    console.log(JSON.stringify({status: report.status, output, checks: report.checks.length, error: report.error}));
  }
  return report;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (!args.includes('--execute')) console.log(JSON.stringify(observatoryAcceptancePlan(), null, 2));
  else await execute({service: option('--service'), token_file: option('--token-file'), out: option('--out'),
    python: option('--python'), chrome: option('--chrome')});
}
