// Observe only a root-owned Device Service session. Never create/stop a session
// or submit firmware/controller/input mutations. Product sources stay frozen.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createReadStream} from 'node:fs';
import {mkdir, readFile, writeFile, access} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createRequire} from 'node:module';
import {resolve, dirname, basename, relative} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';

const HERE = dirname(fileURLToPath(import.meta.url)), ROOT = resolve(HERE, '../..');
const require = createRequire(resolve(ROOT, 'platform/tests/package.json'));
const {chromium} = require('playwright');
const run = promisify(execFile), sha = bytes => createHash('sha256').update(bytes).digest('hex');
const args = process.argv.slice(2), flags = {};
for (let i = 0; i < args.length; i++) {
  assert.ok(args[i].startsWith('--'), 'expected named arguments');
  const key = args[i].slice(2);
  assert.ok(['session-id', 'expected-firmware-sha256', 'expected-runtime-sha256', 'expected-frequency',
    'expected-duty-sequence', 'duty-tolerance', 'frequency-tolerance', 'out', 'timeout-seconds', 'api-base', 'self-check'].includes(key), `unknown --${key}`);
  assert.ok(!(key in flags), `duplicate --${key}`);
  flags[key] = key === 'self-check' ? true : args[++i];
}
const OUT = resolve(flags.out || resolve(HERE, 'self-check'));
assert.ok(relative(HERE, OUT) && !relative(HERE, OUT).startsWith('..') && OUT !== HERE, '--out must be a new child of this harness directory');
await assert.rejects(access(OUT), {code: 'ENOENT'});
await mkdir(OUT, {recursive: true});
const freeze = JSON.parse(await readFile(resolve(ROOT, '.work/unit-audio-20261026/freeze-receipt.json')));
const sources = [...Object.keys(freeze.source_sha256), 'platform/web/sessions.js', 'platform/web/sessions.html',
  'platform/web/unit-annotations.js', 'platform/web/unit-visual-mappings.js', 'platform/web/unit-assembly-layout.js',
  'platform/web/model-shell.js', 'platform/web/device-shell-factory.js', relative(ROOT, fileURLToPath(import.meta.url))];
const sourceHashes = Object.fromEntries(await Promise.all(sources.map(async path => [path, sha(await readFile(resolve(ROOT, path)))])));
for (const [path, expected] of Object.entries(freeze.source_sha256)) assert.equal(sourceHashes[path], expected, `${path} changed after product freeze`);
const {buzzerReadback} = await import(pathToFileURL(resolve(ROOT, 'platform/web/unit-audio.js')));
const jsonFile = async (name, value) => writeFile(resolve(OUT, name), JSON.stringify(value, null, 2) + '\n');
if (flags['self-check']) {
  const result = {schema_version: 1, status: 'OFFLINE_SELF_CHECK_PASS', network_contacted: false,
    browser_started: false, source_sha256: sourceHashes, frozen_product_files: Object.keys(freeze.source_sha256),
    cli_contract: 'Explicit session ID + firmware/runtime SHA; GET-only transport, expected ordered duty readbacks, root-owned stop.'};
  await jsonFile('receipt.json', result); console.log(JSON.stringify({event: result.status, output: OUT})); process.exit(0);
}
const sid = flags['session-id']; assert.match(sid || '', /^[a-zA-Z0-9_-]+$/);
for (const name of ['expected-firmware-sha256', 'expected-runtime-sha256']) assert.match(flags[name] || '', /^[a-f0-9]{64}$/);
const base = new URL(flags['api-base'] || 'http://127.0.0.1:8787');
assert.equal(base.protocol, 'http:'); assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname));
assert.ok(!base.username && !base.password && base.pathname === '/' && !base.search && !base.hash);
const expectedDuty = (flags['expected-duty-sequence'] || '0,25,50,75,100,0').split(',').map(Number);
assert.ok(expectedDuty.length >= 2 && expectedDuty.every(value => Number.isFinite(value) && value >= 0 && value <= 100));
const dutyTolerance = Number(flags['duty-tolerance'] || 0.1), frequencyTolerance = Number(flags['frequency-tolerance'] || 1);
const expectedFrequency = flags['expected-frequency'] === undefined ? null : Number(flags['expected-frequency']);
assert.ok(Number.isFinite(dutyTolerance) && dutyTolerance >= 0 && dutyTolerance <= 1);
assert.ok(Number.isFinite(frequencyTolerance) && frequencyTolerance >= 0 && frequencyTolerance <= 10);
assert.ok(expectedFrequency === null || Number.isFinite(expectedFrequency) && expectedFrequency > 0);
const seconds = Number(flags['timeout-seconds'] || 180); assert.ok(Number.isFinite(seconds) && seconds >= 30 && seconds <= 900);
const deadline = Date.now() + seconds * 1000, sessionPath = `/api/v1/sessions/${sid}`;
const token = process.env.M5_DEVICE_SERVICE_TOKEN || '';
const record = {schema_version: 1, category: 'real-product-buzzer-audio-observer', status: 'RUNNING', session_id: sid,
  expected_firmware_sha256: flags['expected-firmware-sha256'], expected_runtime_sha256: flags['expected-runtime-sha256'],
  expected_frequency: expectedFrequency, expected_duty_sequence: expectedDuty, duty_tolerance: dutyTolerance,
  scope: 'Constant-frequency duty updates when expected-frequency is fixed; no dynamic frequency-update claim. Electrical PWM audition, not physical acoustics.',
  hardware_execution: 'NOT RUN', physical_acoustics_measured: false, browser_output_sink_muted: true,
  source_sha256: sourceHashes, opened_at: new Date().toISOString(), node_gets: [], units_gets: [], session_metadata_gets: [],
  forbidden_requests: [], blocked_non_target_reads: 0, snapshots: [], phases: [], actions: [], errors: [],
  instrumentation: 'Actual sessions page; append read-only state references. No replacement of product APIs, functions, schemas or payloads. Native analyser is a passive disconnected observation branch; no firmware/controller writes.'};
let browser, page, proofTask, closing = false, counter = 0, sourceServed = {}, pendingResponses = new Set(), latestUnits = [];
const terminal = new Set(['stopped', 'failed', 'expired']);
const save = async () => jsonFile('receipt.json', record);
const notify = value => console.log(JSON.stringify({...value, at: new Date().toISOString()}));
const getSession = async label => {
  const response = await fetch(new URL(sessionPath, base), {method: 'GET', signal: AbortSignal.timeout(10000), headers: token ? {Authorization: `Bearer ${token}`} : {}});
  const body = Buffer.from(await response.arrayBuffer());
  const path = `session-${counter++}-${label}.json`; await writeFile(resolve(OUT, path), body);
  record.node_gets.push({at: new Date().toISOString(), method: 'GET', path: sessionPath, status: response.status, body: path, sha256: sha(body)});
  assert.equal(response.status, 200); const session = JSON.parse(body);
  assert.equal(session.session_id, sid); assert.equal(session.firmware_sha256, flags['expected-firmware-sha256']);
  assert.equal(session.runtime, 'qemu'); assert.ok(session.units?.some(unit => unit.unit_id === 'buzzer'));
  return session;
};
const digestExecutable = async path => {
  const hash = createHash('sha256'); for await (const chunk of createReadStream(path)) hash.update(chunk); return hash.digest('hex');
};
const runtimeProof = async () => {
  let before;
  while (!closing && Date.now() < deadline) {
    before = await getSession('await-runtime');
    if (before.state === 'running') break;
    assert.ok(!terminal.has(before.state), 'root session ended before audio observation'); await delay(250);
  }
  assert.equal(before?.state, 'running'); assert.ok(Number.isInteger(before.pid) && before.pid > 1);
  const {stdout} = await run('ps', ['-p', String(before.pid), '-o', 'comm='], {encoding: 'utf8'});
  const executable = stdout.trim(); assert.ok(executable.startsWith('/')); assert.equal(basename(executable), 'qemu-system-xtensa');
  const runtimeHash = await digestExecutable(executable); assert.equal(runtimeHash, flags['expected-runtime-sha256']);
  const after = await getSession('after-runtime-hash');
  assert.equal(after.state, 'running'); assert.equal(after.pid, before.pid);
  assert.equal(after.firmware_sha256, before.firmware_sha256);
  assert.equal(after.worker?.worker_id, before.worker?.worker_id); assert.equal(after.worker?.generation, before.worker?.generation);
  assert.ok(after.worker?.worker_id && Number.isInteger(after.worker.generation));
  const proof = {session_id: sid, kind: 'direct-pid', status: 'VERIFIED', observed_pid: before.pid,
    worker_id: after.worker.worker_id, worker_generation: after.worker.generation,
    firmware_sha256: after.firmware_sha256, runtime_binary_sha256: runtimeHash, executable_name: basename(executable),
    method: 'Live explicit-session GET PID, macOS ps comm, live executable SHA256, then exact PID/firmware/worker rebind. No runtime started by observer.'};
  await jsonFile('runtime-provenance.json', proof); record.runtime_provenance = proof; await save(); return proof;
};
const snapshot = async () => page.evaluate(({sid}) => {
  const visual = window.__unitAudioLiveProbe?.state.visuals.get(sid), panel = visual?.unitPanel;
  const attachment = visual?.session?.units?.find(unit => unit.unit_id === 'buzzer');
  const audio = panel?.audio.get(attachment?.id) || window.__unitAudioObserver?.audio;
  const observer = window.__unitAudioObserver ||= {contexts: [], oscillators: new WeakMap(), nextOscillator: 1};
  if (audio) observer.audio = audio;
  if (audio?.context && !observer.contexts.includes(audio.context)) observer.contexts.push(audio.context);
  if (audio?.oscillator && !observer.oscillators.has(audio.oscillator)) observer.oscillators.set(audio.oscillator, observer.nextOscillator++);
  const context = audio?.context, card = document.querySelector(`[data-session-id="${sid}"]`);
  return {at: new Date().toISOString(), session: visual?.session, panel_session_id: panel?.session.session_id,
    source: panel?.stateSource, frozen: panel?.audioDefinitionSessionId === sid,
    definition: panel?.audioDefinitions.get('buzzer'), unit: panel?.states.get(attachment?.id),
    mounted: panel?.mounted.has(attachment?.id), attaching: panel?.attaching.size,
    audio: audio ? {enabled: audio.enabled, pending: audio.pending, disposed: audio.disposed, signal: audio.signal,
      message: audio.message, context_state: context?.state || null, sample_rate: context?.sampleRate || null,
      oscillator: audio.oscillator ? observer.oscillators.get(audio.oscillator) : null,
      frequency: audio.oscillator?.frequency.value ?? null, gain: audio.gain?.gain.value ?? null} : null,
    context_states: observer.contexts.map(context => context.state),
    toggle_pressed: card?.querySelector('[data-unit-audio-toggle]')?.getAttribute('aria-pressed')};
}, {sid});
try {
  proofTask = runtimeProof().catch(error => { record.errors.push(`runtime proof: ${error.message}`); return null; });
  browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--mute-audio', '--autoplay-policy=user-gesture-required', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  record.browser_version = browser.version();
  page = await browser.newPage({viewport: {width: 1440, height: 1100}}); page.setDefaultTimeout(30000);
  if (token) await page.addInitScript(value => sessionStorage.setItem('m5-service-token', value), token);
  page.on('pageerror', error => record.errors.push(error.message));
  await page.route('**/*', async route => {
    try {
    const request = route.request(), url = new URL(request.url());
    if (request.method() !== 'GET' || url.origin !== base.origin) {
      record.forbidden_requests.push({at: new Date().toISOString(), method: request.method(), path: url.pathname,
        body_sha256: request.postData() ? sha(request.postData()) : null, reason: request.method() !== 'GET' ? 'non-GET rejected' : 'outside service origin rejected'});
      await route.abort('blockedbyclient'); return;
    }
    if (url.pathname.startsWith('/api/v1/sessions/') && url.pathname.split('/')[4] !== sid) {
      record.blocked_non_target_reads++; await route.abort('blockedbyclient'); return;
    }
    if (url.pathname === '/platform/web/sessions.js') {
      const response = await route.fetch(), source = await response.body();
      assert.equal(sha(source), sourceHashes['platform/web/sessions.js']);
      sourceServed['platform/web/sessions.js'] = sha(source);
      await route.fulfill({response, body: source.toString('utf8') + '\nwindow.__unitAudioLiveProbe = {state, SessionVisual};\n'}); return;
    }
    await route.continue();
    } catch (error) {
      record.errors.push(`request guard: ${error.message}`);
      try { await route.abort('blockedbyclient'); } catch {}
    }
  });
  page.on('response', response => {
    const url = new URL(response.url()), request = response.request();
    const sourceFile = url.pathname.slice(1);
    if (!(url.pathname === `${sessionPath}/units` || url.pathname === '/api/v1/sessions' || sourceFile in sourceHashes)) return;
    const task = (async () => {
      const body = await response.body();
      if (sourceFile in sourceHashes && sourceFile !== 'platform/web/sessions.js') {
        assert.equal(response.status(), 200); assert.equal(sha(body), sourceHashes[sourceFile], `${sourceFile} served bytes differ`); sourceServed[sourceFile] = sha(body);
      } else if (url.pathname === `${sessionPath}/units`) {
        const payload = JSON.parse(body), path = `units-${record.units_gets.length.toString().padStart(4, '0')}.json`;
        assert.equal(payload.session_id, sid, 'Units response must belong to the explicit session');
        await writeFile(resolve(OUT, path), body);
        const event = {at: new Date().toISOString(), method: request.method(), path: url.pathname, status: response.status(), body: path, sha256: sha(body)};
        record.units_gets.push(event); latestUnits.push({event, payload});
      } else if (url.pathname === '/api/v1/sessions') {
        const payload = JSON.parse(body), selected = payload.sessions?.find(session => session.session_id === sid);
        if (selected) record.session_metadata_gets.push({at: new Date().toISOString(), status: response.status(), raw_response_sha256: sha(body), selected_session: selected});
      }
    })().catch(error => record.errors.push(`HTTP observation: ${error.message}`));
    pendingResponses.add(task); void task.finally(() => pendingResponses.delete(task));
  });
  const response = await page.goto(new URL('/platform/web/sessions.html', base).href, {waitUntil: 'domcontentloaded'}); assert.ok(response.ok());
  await page.waitForFunction(sid => {
    const visual = window.__unitAudioLiveProbe?.state.visuals.get(sid), panel = visual?.unitPanel;
    const attachment = visual?.session?.units?.find(unit => unit.unit_id === 'buzzer');
    const toggle = document.querySelector(`[data-session-id="${sid}"] [data-unit-audio-toggle]`);
    return visual?.session?.state === 'running' && panel?.session.state === 'running' && panel.audio.get(attachment?.id)?.signal
      && !panel.attaching.size && visual.shell?.model && panel.mounted.has(attachment.id) && toggle && !toggle.disabled;
  }, sid, {timeout: Math.min(seconds * 1000, 180000)});
  const initial = await snapshot(); record.snapshots.push({phase: 'default-muted', ...initial});
  assert.equal(initial.audio.enabled, false); assert.equal(initial.audio.context_state, null); assert.equal(initial.audio.oscillator, null);
  assert.equal(initial.toggle_pressed, 'false'); assert.deepEqual(initial.context_states, []);
  const card = page.locator(`[data-session-id="${sid}"]`), toggle = card.locator('[data-unit-audio-toggle]');
  await card.screenshot({path: resolve(OUT, 'default-muted.png')});
  await toggle.click(); record.actions.push({at: new Date().toISOString(), kind: 'trusted-product-audio-enable-click', product_mutation: false});
  await page.waitForFunction(sid => {
    const panel = window.__unitAudioLiveProbe?.state.visuals.get(sid)?.unitPanel;
    const audio = [...(panel?.audio.values() || [])][0];
    return audio?.enabled && !audio.pending && audio.context?.state === 'running';
  }, sid, {timeout: 15000});
  notify({event: 'AUDIO_ENABLED', session_id: sid});
  let ready = false, lastResponseIndex = -1, previousActiveOscillator = null;
  while (Date.now() < deadline) {
    await Promise.all([...pendingResponses]);
    const current = await snapshot();
    const unitsTerminal = latestUnits.findLast(({payload}) => payload.session_id === sid && terminal.has(payload.state));
    if (terminal.has(current.session?.state) || unitsTerminal) {
      record.terminal_trigger = unitsTerminal ? {source: 'actual-matching-session-units-response',
        state: unitsTerminal.payload.state, units_get: unitsTerminal.event.body, units_get_sha256: unitsTerminal.event.sha256}
        : {source: 'actual-product-session-list-state', state: current.session.state};
      assert.ok(ready, 'root stopped before required live duty sequence was observed');
      // Units, session-list polling and AudioContext.close() are independent
      // observations. A real terminal Units reply is sufficient to begin
      // cleanup, never to fabricate a new live readback from retained values.
      await page.waitForFunction(sid => {
        const visual = window.__unitAudioLiveProbe?.state.visuals.get(sid), panel = visual?.unitPanel;
        const attachment = visual?.session?.units?.find(unit => unit.unit_id === 'buzzer');
        const audio = panel?.audio.get(attachment?.id) || window.__unitAudioObserver?.audio;
        const contexts = window.__unitAudioObserver?.contexts || [];
        return audio && !audio.enabled && !audio.context && !audio.oscillator && !audio.gain
          && contexts.length > 0 && contexts.every(context => context.state === 'closed');
      }, sid, {timeout: 15000});
      const stopped = await snapshot();
      assert.ok(stopped.audio && !stopped.audio.enabled && !stopped.audio.context_state && !stopped.audio.oscillator && stopped.audio.gain === null);
      assert.ok(stopped.context_states.length >= 1 && stopped.context_states.every(state => state === 'closed'));
      record.snapshots.push({phase: 'root-stopped', ...stopped});
      await card.screenshot({path: resolve(OUT, 'root-stopped.png')});
      const history = await getSession('history'); assert.ok(terminal.has(history.state)); record.history = history;
      await assert.rejects(run('ps', ['-p', String(record.runtime_provenance.observed_pid), '-o', 'pid='], {encoding: 'utf8'}), error => error.code === 1);
      record.cleanup = {root_owned_stop_observed: true, all_observed_contexts_closed: true, pid_exited: true};
      break;
    }
    assert.equal(current.session?.session_id, sid); assert.equal(current.panel_session_id, sid);
    assert.equal(current.session?.firmware_sha256, flags['expected-firmware-sha256']);
    const signal = buzzerReadback(current.unit, current.definition, {running: current.session.state === 'running', source: current.source, frozenDefinitions: current.frozen});
    assert.ok(signal, 'live readback became unavailable'); assert.deepEqual(current.audio.signal, signal);
    assert.equal(current.audio.enabled, true); assert.equal(current.audio.context_state, 'running');
    if (expectedFrequency !== null) assert.ok(Math.abs(signal.frequency - expectedFrequency) <= frequencyTolerance, 'observed frequency differs from fixed-frequency contract');
    const matchIndex = latestUnits.findLastIndex(({payload}) => payload.source === 'live' && payload.units?.some(unit => unit.id === current.unit.id
      && unit.source === 'guest-qom' && unit.available === true && unit.properties['frequency-hz'] === signal.frequency && unit.properties['duty-pct'] === signal.duty)
      && payload.definitions?.some(definition => JSON.stringify(definition) === JSON.stringify(current.definition)));
    assert.ok(matchIndex >= 0, 'audio observation must match an actual frozen-schema GET response');
    const active = signal.frequency > 0 && signal.duty > 0 && signal.duty < 100 && signal.frequency < current.audio.sample_rate / 2;
    if (active && (current.audio.oscillator === null || Math.abs(current.audio.frequency - signal.frequency) > 0.01)) { await delay(50); continue; }
    if (!active) assert.ok(current.audio.oscillator === null && current.audio.gain === null, 'observed DC/off state must have no tone');
    if (record.phases.length < expectedDuty.length && matchIndex > lastResponseIndex && Math.abs(signal.duty - expectedDuty[record.phases.length]) <= dutyTolerance) {
      const index = record.phases.length;
      if (active && previousActiveOscillator !== null) assert.equal(current.audio.oscillator, previousActiveOscillator, 'continuous duty updates must preserve the native oscillator');
      previousActiveOscillator = active ? current.audio.oscillator : null;
      const phase = {index, expected_duty: expectedDuty[index], observed_frequency: signal.frequency, observed_duty: signal.duty,
        units_get: latestUnits[matchIndex].event.body, units_get_sha256: latestUnits[matchIndex].event.sha256, snapshot: current};
      if (active) {
        const samples = await page.evaluate(async sid => {
          const visual = window.__unitAudioLiveProbe.state.visuals.get(sid), audio = [...visual.unitPanel.audio.values()][0];
          const before = JSON.stringify(audio.signal), context = audio.context, gain = audio.gain;
          const analyser = context.createAnalyser(); analyser.fftSize = 2048; gain.connect(analyser);
          try {
            await new Promise(resolve => setTimeout(resolve, 80));
            const samples = new Float32Array(analyser.fftSize); analyser.getFloatTimeDomainData(samples);
            return {before_signal: JSON.parse(before), after_signal: audio.signal, sample_rate: context.sampleRate,
              stable: before === JSON.stringify(audio.signal) && audio.context === context && audio.gain === gain,
              samples: Array.from(samples), peak: Math.max(...samples.map(Math.abs))};
          } finally { try { gain.disconnect(analyser); } catch {} analyser.disconnect(); }
        }, sid);
        if (!samples.stable) { await delay(50); continue; }
        assert.ok(samples.peak > 1e-7, 'native waveform graph is silent for an observed AC PWM');
        const path = `phase-${index}-native-waveform.json`; await jsonFile(path, samples);
        phase.native_waveform = {path, sha256: sha(await readFile(resolve(OUT, path))), peak: samples.peak, sample_rate: samples.sample_rate};
      }
      await card.screenshot({path: resolve(OUT, `phase-${index}.png`)});
      record.phases.push(phase); lastResponseIndex = matchIndex;
      record.snapshots.push({phase: `accepted-${index}`, ...current}); await save();
      notify({event: 'DUTY_PHASE_OBSERVED', session_id: sid, index, actual_frequency: signal.frequency, actual_duty: signal.duty});
    }
    if (!ready && record.phases.length === expectedDuty.length) {
      assert.ok(await proofTask, 'runtime proof did not validate'); assert.equal(record.forbidden_requests.length, 0);
      ready = true; record.ready_for_root_stop_at = new Date().toISOString(); await save();
      notify({event: 'READY_FOR_ROOT_STOP', session_id: sid, observed_phases: record.phases.length});
    }
    await delay(100);
  }
  assert.ok(record.cleanup, 'timeout waiting for required phases and root-owned stop');
  await Promise.all([...pendingResponses]);
  for (const path of sources.filter(path => path.startsWith('platform/web/') && !path.endsWith('.css'))) assert.equal(sourceServed[path], sourceHashes[path], `required product asset was not observed: ${path}`);
  for (const path of Object.keys(sourceHashes)) assert.equal(sha(await readFile(resolve(ROOT, path))), sourceHashes[path], `${path} changed during observation`);
  assert.equal(record.forbidden_requests.length, 0); assert.deepEqual(record.errors, []);
  record.served_source_sha256 = sourceServed; record.status = 'PASS';
} catch (error) {
  record.status = 'FAIL'; record.error = `${error.name}: ${error.message}`;
  if (page) { try { await page.screenshot({path: resolve(OUT, 'failure.png'), fullPage: true}); } catch {} }
} finally {
  closing = true;
  if (proofTask) await proofTask;
  if (page) { try { record.final_snapshot = await snapshot(); } catch {} }
  await Promise.all([...pendingResponses]);
  record.completed_at = new Date().toISOString(); await save();
  if (browser) await browser.close();
  notify({event: 'OBSERVER_FINISHED', status: record.status, output: OUT, error: record.error || null});
}
process.exitCode = record.status === 'PASS' ? 0 : 1;
