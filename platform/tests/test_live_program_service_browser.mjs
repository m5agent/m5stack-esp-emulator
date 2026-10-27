// Opt-in real product UI -> Device Service UART -> guest -> Unit/frame evidence.
// The only instrumentation exposes existing SessionVisual objects for observation.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium} from 'playwright';

assert.equal(process.env.M5_UNIT_SERVICE_E2E, '1', 'Explicit opt-in required: creates visible virtual sessions.');
const expectedRuntime = process.env.M5_EXPECTED_RUNTIME_SHA256;
assert.match(expectedRuntime || '', /^[0-9a-f]{64}$/);
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const base = process.env.M5_DEVICE_SERVICE_URL || 'http://127.0.0.1:8787';
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname), 'direct PID validation requires a local service');
const output = resolve(process.env.M5_LIVE_PROGRAM_BROWSER_OUT || '/tmp/m5-live-program-browser');
await mkdir(output, {recursive: true});
const sources = ['platform/web/sessions.js', 'platform/web/sessions.html', 'platform/web/program-panel.js',
  'platform/web/program-panel.css', 'platform/web/unit-panel.js', 'platform/web/model-shell.js',
  'platform/web/vendor/m5stack-models/vendor-manifest.json', 'platform/tests/test_live_program_service_browser.mjs'];
const fingerprints = async () => Object.fromEntries(await Promise.all(sources.map(async path => [path, createHash('sha256').update(await readFile(resolve(root, path))).digest('hex')])));
const report = {category: 'virtual-device-live-program-browser', status: 'FAIL', device_id: 'cores3', runtime: 'qemu',
  hardware_validation: 'NOT RUN', captured_at: new Date().toISOString(), source_sha256: await fingerprints(),
  instrumentation: 'Only window.__liveProgramProbe={state,SessionVisual}; product methods and API data remain unchanged.',
  cases: [], page_errors: [], resource_errors: [], shared_frame_responses: []};
const api = async (path, options = {}, timeout = 30000) => {
  const deadline = AbortSignal.timeout(Math.max(1, Math.ceil(timeout)));
  const signal = options.signal ? AbortSignal.any([options.signal, deadline]) : deadline;
  try {
    const response = await fetch(`${base}/api/v1/${path}`, {...options, signal});
    const bytes = Buffer.from(await response.arrayBuffer());
    if (!response.ok) throw new Error(`${response.status}: ${bytes.toString()}`);
    return path.endsWith('evidence') || path.includes('frame.png') ? bytes : JSON.parse(bytes);
  } catch (error) {
    if (deadline.aborted) throw new Error(`${options.method || 'GET'} ${path}: request exceeded ${timeout} ms`, {cause: error});
    throw error;
  }
};
const eventually = async (read, predicate, timeout = 45000) => {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await read(deadline - Date.now());
    if (predicate(value)) return value;
    await delay(Math.min(100, Math.max(0, deadline - Date.now())));
  }
  throw new Error('Actual guest/browser observation deadline exceeded');
};
const stopOwnedSession = async id => {
  const path = `sessions/${encodeURIComponent(id)}`;
  let stopped = await api(path + '?purge=0', {method: 'DELETE'}, 15000);
  if (!['stopped', 'failed'].includes(stopped.state)) {
    stopped = await eventually(remaining => api(path, {}, Math.min(10000, remaining)),
      value => ['stopped', 'failed'].includes(value.state), 45000);
  }
  assert.equal(stopped.flash_retained, false, 'owned session cleanup did not release mutable Flash');
  return stopped;
};
const runtimeIdentity = pid => JSON.parse(execFileSync(process.env.M5_PYTHON || '/opt/miniconda3/bin/python3.12', ['-c',
  'import ctypes,hashlib,json,pathlib,sys; p=int(sys.argv[1]); b=ctypes.create_string_buffer(4096); assert ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath(p,b,len(b))>0; f=pathlib.Path(b.value.decode()); print(json.dumps({"pid":p,"executable_name":f.name,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()}))', String(pid)], {encoding: 'utf8'}));

function source(unit, stage, pins) {
  const init = unit === 'pir'
    ? `from unit import PIRUnit\nunit = PIRUnit((${pins.white}, ${pins.yellow}))`
    : `from unit import RelayUnit\nunit = RelayUnit((${pins.white}, ${pins.yellow}))\nunit.set_status(${stage === 'B' ? 'True' : 'False'})`;
  return `import M5\nimport time\nM5.begin()\n${init}\nscreen=M5.Display\nscreen.setBrightness(255)\nscreen.fillScreen(${stage === 'A' ? '0xFFFFFF' : '0x88FF88'})\nscreen.setTextSize(2)\nscreen.setTextColor(0)\nprint("WEB_${stage}_READY")\nprevious=None\nwhile True:\n M5.update()\n value=int(unit.get_status())\n if value!=previous:\n  print("WEB_${stage}_${unit.toUpperCase()}",value)\n  screen.fillRect(0,0,128,90,${stage === 'A' ? '0xFFFFFF' : '0x88FF88'})\n  screen.setCursor(4,4)\n  screen.print("WEB ${stage}")\n  screen.setCursor(4,32)\n  screen.print("${unit.toUpperCase()} "+str(value))\n  previous=value\n time.sleep_ms(25)\n`;
}

let browser, page, currentId;
try {
  browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  report.browser_version = browser.version();
  page = await browser.newPage({viewport: {width: 1440, height: 1080}});
  page.on('pageerror', error => report.page_errors.push(error.message));
  page.on('response', response => { if (response.status() >= 400 && response.url().includes('/vendor/')) report.resource_errors.push({url: response.url(), status: response.status()}); });
  page.on('response', response => {
    const url = new URL(response.url());
    if (url.pathname.endsWith('/frame.png') && url.searchParams.get('max_age_ms') === '125') {
      report.shared_frame_responses.push({path: url.pathname, max_age_ms: 125, status: response.status()});
    }
  });
  await page.route('**/platform/web/sessions.js*', async route => {
    const response = await route.fetch(); const actual = await response.text();
    assert.equal(createHash('sha256').update(actual).digest('hex'), report.source_sha256['platform/web/sessions.js']);
    await route.fulfill({response, body: actual + '\nwindow.__liveProgramProbe={state,SessionVisual};\n'});
  });
  await page.goto(`${base}/platform/web/sessions.html`, {waitUntil: 'domcontentloaded'});
  await page.locator('#deviceSelect option[value="cores3"]').waitFor({state: 'attached'});
  for (const unit of ['pir', 'relay']) {
    const result = {unit_id: unit, checks: {}, submissions: [], unit_posts: []}; report.cases.push(result);
    await page.selectOption('#deviceSelect', 'cores3');
    await page.locator('#unitModelSelect option[value="' + unit + '"]').waitFor({state: 'attached'});
    await page.selectOption('#unitModelSelect', unit);
    await page.check('#programModeInput');
    const createdResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/sessions') && response.request().method() === 'POST');
    await page.click('#createBtn');
    const response = await createdResponse;
    result.creation_request = response.request().postDataJSON();
    result.creation_response = await response.json();
    const created = result.creation_response;
    // Register the successful creation before checking its request contract:
    // a regression in the checkbox/payload must still clean up its own lease.
    if (response.status() === 202 && typeof created.session_id === 'string') {
      currentId = created.session_id;
      result.session_id = currentId;
    }
    assert.equal(response.status(), 202, JSON.stringify(result.creation_response));
    assert.equal(response.request().postDataJSON().program_mode, 'uiflow-live');
    assert.match(currentId || '', /^[0-9a-f]{32}$/);
    const prefix = `sessions/${currentId}`;
    const ready = await eventually(() => api(prefix), value => ['running', 'failed', 'stopped'].includes(value.state), 120000);
    assert.equal(ready.state, 'running', ready.error);
    result.firmware_sha256 = ready.firmware_sha256; result.pid = ready.pid;
    result.runtime_identity = runtimeIdentity(ready.pid); assert.equal(result.runtime_identity.sha256, expectedRuntime);
    const pins = ready.units[0].pins;
    const card = page.locator(`[data-session-id="${currentId}"]`);
    const editor = card.locator('[data-program-source]'), run = card.locator('[data-program-run]');
    await run.waitFor({state: 'visible'});
    await eventually(() => run.isEnabled(), Boolean);
    await page.waitForFunction(id => window.__liveProgramProbe?.state.visuals.get(id)?.unitPanel?.mounted.size === 1, currentId, {timeout: 60000});
    const serial = () => api(prefix + '/serial?limit=1048576');
    const observe = marker => eventually(serial, value => value.data.includes(marker));
    if (unit === 'pir') {
      // Establish an explicit controller fixture before guest GPIO setup.
      // Merely displaying a default input value is not guest readback evidence.
      const field = card.locator('.unit-control input').first();
      for (const motion of [true, false]) {
        const post = page.waitForResponse(r => r.url().endsWith(`/sessions/${currentId}/unit-input`) && r.request().method() === 'POST');
        await field.setChecked(motion); const reply = await post; assert.equal(reply.status(), 200);
        result.unit_posts.push(reply.request().postDataJSON());
      }
      await eventually(() => api(prefix + '/units'), value => value.units[0].properties['input-level'] === false);
    }
    let expected = null;
    const execute = async (text, marker) => {
      const wait = page.waitForResponse(r => r.url().endsWith(`/sessions/${currentId}/program`) && r.request().method() === 'POST');
      await editor.fill(text); await run.click(); const reply = await wait;
      const request = reply.request().postDataJSON(); assert.equal(request.source, text); assert.equal(request.expected_execution_id, expected);
      assert.equal(reply.status(), 200); const status = await reply.json(); expected = status.program.execution_id;
      result.submissions.push({request, response: status});
      if (marker) await observe(marker);
      await eventually(() => run.isEnabled(), Boolean);
      assert.equal(await editor.inputValue(), text, 'status polling must preserve the editable draft');
      return status;
    };
    await execute(source(unit, 'A', pins), 'WEB_A_READY');
    if (unit === 'pir') {
      await observe('WEB_A_PIR 0');
      const field = card.locator('.unit-control input').first();
      for (const motion of [true, false]) {
        const before = (await serial()).next_offset;
        const post = page.waitForResponse(r => r.url().endsWith(`/sessions/${currentId}/unit-input`) && r.request().method() === 'POST');
        await field.setChecked(motion); const reply = await post; assert.equal(reply.status(), 200);
        result.unit_posts.push(reply.request().postDataJSON());
        await eventually(() => api(prefix + '/serial?offset=' + before), value => value.data.includes(`WEB_A_PIR ${Number(motion)}`));
        const state = await api(prefix + '/units'); assert.equal(state.units[0].properties.motion, motion);
      }
      result.checks.web_input_to_same_guest_gpio_and_driver = true;
    } else {
      await observe('WEB_A_RELAY 0');
      assert.equal((await api(prefix + '/units')).units[0].properties['output-level'], false);
    }
    const frameA = await api(prefix + '/frame.png'); await writeFile(`${output}/${unit}-a-frame.png`, frameA);
    const displayedFrame = async png => {
      // Compare to the actual PNG, not unquantized 24-bit draw arguments:
      // RGB565 guest framebuffers can round 0x88 to 0x8c.
      const color = await page.evaluate(async encoded => {
        const bytes = Uint8Array.from(atob(encoded), value => value.charCodeAt(0));
        const image = await createImageBitmap(new Blob([bytes], {type: 'image/png'}));
        const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
        const context = canvas.getContext('2d'); context.drawImage(image, 0, 0);
        const pixel = [...context.getImageData(image.width - 2, image.height - 2, 1, 1).data].slice(0, 3);
        image.close(); return pixel;
      }, png.toString('base64'));
      await page.waitForFunction(({id, color}) => {
        const display = window.__liveProgramProbe.state.visuals.get(id)?.shell?.display;
        const pixel = display?.getPixel(display.width - 2, display.height - 2);
        return pixel && color.every((channel, index) => pixel[index] === channel);
      }, {id: currentId, color}, {timeout: 30000});
      return color;
    };
    result.frame_a_corner_rgb = await displayedFrame(frameA);
    await execute(source(unit, 'B', pins), 'WEB_B_READY');
    if (unit === 'relay') {
      await observe('WEB_B_RELAY 1');
      assert.equal((await api(prefix + '/units')).units[0].properties['output-level'], true);
      await page.waitForFunction(id => window.__liveProgramProbe.state.visuals.get(id).unitPanel.states.get('external1')?.properties['output-level'] === true, currentId);
      result.checks.guest_relay_output_to_controller_and_web_readback = true;
    }
    const frameB = await api(prefix + '/frame.png'); await writeFile(`${output}/${unit}-b-frame.png`, frameB);
    assert.notEqual(createHash('sha256').update(frameA).digest('hex'), createHash('sha256').update(frameB).digest('hex'));
    result.frame_b_corner_rgb = await displayedFrame(frameB);
    result.web_preview = await eventually(() => page.evaluate(id => {
      const visual = window.__liveProgramProbe.state.visuals.get(id);
      return {etag: visual?.frameEtag, metadata: visual?.frameMetadata};
    }, currentId), value => value.etag && value.metadata?.['x-frame-execution-id'] === expected);
    assert.equal(result.web_preview.metadata['x-frame-source'], 'live');
    assert.ok(result.web_preview.metadata['x-frame-captured-at']);
    result.checks.actual_web_uses_shared_frame_metadata = true;
    result.checks.actual_guest_frame_updates_web_model_display = true;
    await execute('def broken(:\n', null);
    await eventually(() => api(prefix + '/program'), value => value.program.state === 'failed');
    const failedState = card.locator('[data-program-state]');
    const serialView = card.locator('[data-field="serial"]');
    await eventually(() => failedState.textContent(), text => text === '执行失败');
    await eventually(() => serialView.textContent(), text => text.includes('SyntaxError') && text.includes(`__M5_EXEC_${expected}__:ERROR`));
    assert.equal(await failedState.isVisible(), true);
    assert.equal(await serialView.isVisible(), true);
    result.syntax_error_status_text = await failedState.textContent();
    result.checks.syntax_error_dom_status_and_serial = true;
    await execute('print("WEB_RECOVERED")\n', 'WEB_RECOVERED');
    assert.equal((await api(prefix)).pid, ready.pid); assert.equal((await api(prefix)).firmware_sha256, ready.firmware_sha256);
    result.checks.ui_replaces_program_without_reflash_or_process_change = true;
    result.checks.syntax_error_visible_and_recoverable = true;
    await page.evaluate(() => window.scrollTo(0, 0));
    const clip = await card.boundingBox(); assert.ok(clip);
    await page.screenshot({path: `${output}/${unit}-browser.png`, clip: {x: clip.x, y: clip.y, width: clip.width, height: clip.height}, captureBeyondViewport: true});
    const zip = await api(prefix + '/evidence'); await writeFile(`${output}/${unit}-evidence.zip`, zip);
    result.evidence_sha256 = createHash('sha256').update(zip).digest('hex');
    const stopped = await stopOwnedSession(currentId); assert.equal(stopped.state, 'stopped');
    result.stopped = stopped;
    currentId = null; result.checks.evidence_before_stop_and_retained_history = true;
    result.status = 'PASS';
  }
  assert.deepEqual(report.page_errors, []); assert.deepEqual(report.resource_errors, []);
  assert.ok(report.shared_frame_responses.some(row => row.status === 200));
  assert.deepEqual(await fingerprints(), report.source_sha256);
  report.status = 'PASS';
} catch (error) { report.error = error.stack || String(error); }
finally {
  if (currentId) {
    try { await writeFile(`${output}/failure-evidence.zip`, await api(`sessions/${encodeURIComponent(currentId)}/evidence`, {}, 15000)); }
    catch (error) { report.status = 'FAIL'; report.evidence_error = String(error); }
    try { report.failure_cleanup = await stopOwnedSession(currentId); }
    catch (error) { report.status = 'FAIL'; report.cleanup_error = String(error); }
  }
  try { if (browser) await browser.close(); }
  catch (error) { report.status = 'FAIL'; report.browser_close_error = String(error); }
  finally { await writeFile(`${output}/report.json`, JSON.stringify(report, null, 2) + '\n'); }
}
console.log(`LIVE_PROGRAM_BROWSER_${report.status} ${output}/report.json`);
if (report.status !== 'PASS') { console.error(report.error || report.cleanup_error || report.browser_close_error || report.evidence_error); process.exitCode = 1; }
