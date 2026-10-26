// Browser/audio lifecycle fixtures only. These tests do not execute firmware,
// contact Device Service, or establish a physical acoustic measurement.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {resolve, dirname, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '../../platform/tests/node_modules/playwright/index.mjs';
import {UnitAudio, buzzerReadback, pwmCoefficients} from '../../platform/web/unit-audio.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = process.env.M5_UNIT_AUDIO_OUT || '/tmp/m5-unit-audio-test';
await mkdir(output, {recursive: true});
const catalog = JSON.parse(await readFile(resolve(root, 'platform/units/catalog.json'), 'utf8'));
const definition = catalog.units.find(unit => unit.id === 'buzzer');
const observed = (frequency = 4000, duty = 50) => ({id: 'buzz', unit_id: 'buzzer', source: 'guest-qom',
  available: true, errors: {}, properties: {'frequency-hz': frequency, 'duty-pct': duty}});
const options = {sessionId: 'audio-fixture', running: true, source: 'live', frozenDefinitions: true, attached: true};
const clone = value => structuredClone(value);
const pending = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return {promise, resolve, reject}; };
let unitAssertions = 0;
const check = (condition, message) => { assert.ok(condition, message); unitAssertions++; };

class FakeContext {
  constructor({deferred = null, failWave = false} = {}) {
    this.state = 'suspended'; this.sampleRate = 48000; this.currentTime = 1;
    this.destination = {}; this.nodes = []; this.waves = []; this.listeners = new Set();
    this.closes = 0; this.resumes = 0; this.deferred = deferred; this.failWave = failWave;
  }
  addEventListener(name, callback) { this.listeners.add(callback); }
  removeEventListener(name, callback) { this.listeners.delete(callback); }
  async resume() { this.resumes++; if (this.deferred) await this.deferred.promise; if (this.state !== 'closed') this.state = 'running'; }
  close() { this.closes++; this.state = 'closed'; return Promise.resolve(); }
  emit(state) { this.state = state; for (const listener of this.listeners) listener(); }
  createPeriodicWave(real, imag, configuration) {
    if (this.failWave) throw new Error('fixture waveform failure');
    const wave = {real: Array.from(real), imag: Array.from(imag), configuration}; this.waves.push(wave); return wave;
  }
  node(kind) {
    const node = {kind, starts: 0, stops: 0, disconnected: false, connections: [],
      connect(target) { this.connections.push(target); }, disconnect() { this.disconnected = true; },
      start() { this.starts++; }, stop() { this.stops++; }, setPeriodicWave(wave) { this.wave = wave; }};
    const param = () => ({value: null, cancelScheduledValues() {}, setValueAtTime(value) { this.value = value; }});
    if (kind === 'oscillator') node.frequency = param();
    else node.gain = param();
    this.nodes.push(node); return node;
  }
  createOscillator() { return this.node('oscillator'); }
  createGain() { return this.node('gain'); }
}

const validSignal = buzzerReadback(observed(), definition, options);
assert.deepEqual(validSignal, {frequency: 4000, duty: 50}); unitAssertions++;
const invalid = [
  ['not running', observed(), definition, {...options, running: false}],
  ['persisted', observed(), definition, {...options, source: 'persisted'}],
  ['mutable inventory', observed(), definition, {...options, frozenDefinitions: false}],
  ['detached', observed(), definition, {...options, attached: false}],
  ['other Unit', {...observed(), unit_id: 'fan'}, definition, options],
  ['other definition', observed(), {...definition, id: 'fan'}, options],
  ['host source', {...observed(), source: 'host-fixture'}, definition, options],
  ['unavailable', {...observed(), available: false}, definition, options],
  ['read error', {...observed(), errors: {pwm: 'unavailable'}}, definition, options],
  ['malformed errors', {...observed(), errors: false}, definition, options],
  ['missing frequency', {...observed(), properties: {'duty-pct': 50}}, definition, options],
  ['missing duty', {...observed(), properties: {'frequency-hz': 4000}}, definition, options],
  ['negative frequency', observed(-1), definition, options],
  ['infinite frequency', observed(Infinity), definition, options],
  ['NaN frequency', observed(NaN), definition, options],
  ['string frequency', observed('4000'), definition, options],
  ['negative duty', observed(4000, -1), definition, options],
  ['excess duty', observed(4000, 101), definition, options],
  ['NaN duty', observed(4000, NaN), definition, options],
];
for (const [field, patch] of [['frequency-hz', {readOnly: false}], ['frequency-hz', {type: 'string'}],
  ['frequency-hz', {minimum: '0'}], ['frequency-hz', {maximum: -1}], ['duty-pct', {maximum: undefined}],
  ['duty-pct', {maximum: 101}], ['duty-pct', {enum: []}], ['frequency-hz', {type: 'integer'}]]) {
  const modified = clone(definition); Object.assign(modified.outputs[field], patch);
  invalid.push([`invalid frozen ${field} ${JSON.stringify(patch)}`, observed(4000.5), modified, options]);
}
const echoDefinition = clone(definition); echoDefinition.inputs['frequency-hz'] = {type: 'number'};
invalid.push(['input echo', observed(), echoDefinition, options]);
for (const [label, unit, schema, configuration] of invalid) {
  assert.equal(buzzerReadback(unit, schema, configuration), null, label); unitAssertions++;
  const audio = new UnitAudio({createContext: () => { throw new Error('must not create a context'); }});
  audio.observe(unit, schema, configuration);
  assert.equal(await audio.enable(), false, label); unitAssertions++;
  audio.dispose();
}

const half = pwmCoefficients(1000, 50, 48000), quarter = pwmCoefficients(1000, 25, 48000);
check(Math.abs(half.real[1] - 2 / Math.PI) < 1e-7, 'half duty has the expected fundamental');
check(Math.abs(half.real[2]) < 1e-7 && quarter.real[2] > 0.3, 'duty controls harmonic content');
check(half.real[0] === 0 && half.imag.every(value => value === 0), 'no synthesized DC');
check(half.real.length === 24, 'harmonics at and above Nyquist are omitted');
check(pwmCoefficients(0.001, 50, 48000).real.length === 257, 'low frequency work is bounded');
for (const args of [[0, 50, 48000], [4000, 0, 48000], [4000, 100, 48000], [24000, 50, 48000], [NaN, 50, 48000]]) {
  assert.equal(pwmCoefficients(...args), null); unitAssertions++;
}

{
  const context = new FakeContext(), audio = new UnitAudio({createContext: () => context});
  const unit = observed(), schema = clone(definition), frozen = JSON.stringify({unit, schema});
  audio.observe(unit, schema, options);
  check(!audio.enabled && !audio.context && context.resumes === 0, 'valid output remains muted until user enable');
  check(await audio.enable(), 'enable starts native graph after resume');
  const oscillator = audio.oscillator, gain = audio.gain;
  check(oscillator.frequency.value === 4000 && oscillator.starts === 1, 'observed frequency drives oscillator');
  check(context.waves[0].configuration.disableNormalization === true && gain.gain.value === 0.12, 'duty amplitude is retained with a low fixed gain');
  audio.observe(observed(800, 25), schema, options);
  check(audio.oscillator === oscillator && oscillator.frequency.value === 800 && oscillator.starts === 1, 'continuous updates reuse oscillator');
  check(JSON.stringify({unit, schema}) === frozen, 'observer cannot mutate source values/schema');
  for (const [frequency, duty] of [[0, 50], [800, 0], [800, 100], [48000, 50]]) {
    audio.observe(observed(frequency, duty), schema, options);
    check(audio.enabled && !audio.oscillator && !audio.gain, 'DC/off/out-of-band state stays silent');
    audio.observe(observed(1000, 50), schema, options);
    check(Boolean(audio.oscillator), 'next observed AC output resumes after a valid rest');
  }
  audio.mute();
  check(!audio.enabled && !audio.context && context.closes === 1 && context.listeners.size === 0, 'mute destroys graph and context');
  audio.dispose(); audio.dispose();
  check(context.closes === 1, 'cleanup is idempotent');
}

for (const ending of ['mute', 'dispose', 'session', 'stopped', 'unavailable', 'detach', 'invalid']) {
  const deferred = pending(), context = new FakeContext({deferred});
  const audio = new UnitAudio({createContext: () => context});
  audio.observe(observed(), definition, options);
  const enabled = audio.enable(), second = audio.enable();
  check(context.resumes === 1 && !audio.oscillator, `${ending}: coalesced pending resume has no oscillator`);
  if (ending === 'mute') audio.mute();
  else if (ending === 'dispose') audio.dispose();
  else if (ending === 'session') audio.observe(observed(), definition, {...options, sessionId: 'next'});
  else if (ending === 'stopped') audio.observe(observed(), definition, {...options, running: false});
  else if (ending === 'detach') audio.observe(observed(), definition, {...options, attached: false});
  else if (ending === 'invalid') audio.observe(observed(4000, 101), definition, options);
  else audio.observe({...observed(), available: false}, definition, options);
  deferred.resolve();
  assert.deepEqual(await Promise.all([enabled, second]), [false, false], ending); unitAssertions++;
  check(context.closes === 1 && context.nodes.length === 0 && !audio.context && !audio.enabled, `${ending}: late resume cannot resurrect sound`);
  audio.dispose();
}
{
  const deferred = pending(), context = new FakeContext({deferred});
  const audio = new UnitAudio({createContext: () => context});
  audio.observe(observed(), definition, options);
  const enabled = audio.enable();
  audio.observe(observed(777, 37), definition, options);
  deferred.resolve(); await enabled;
  check(audio.oscillator.frequency.value === 777 && audio.signal.duty === 37, 'pending resume uses latest verified observation');
  context.emit('suspended');
  check(context.closes === 1 && !audio.oscillator && !audio.enabled, 'browser interruption fails closed');
  audio.dispose();
}
{
  const deferred = pending(), context = new FakeContext({deferred});
  const audio = new UnitAudio({createContext: () => context}); audio.observe(observed(), definition, options);
  const first = audio.enable(), second = audio.enable(); deferred.reject(new Error('autoplay denied'));
  assert.deepEqual(await Promise.all([first, second]), [false, false]); unitAssertions++;
  check(context.closes === 1 && !audio.enabled, 'resume rejection cleans up without unhandled rejection');
}
{
  const contexts = [new FakeContext({failWave: true}), new FakeContext()];
  const audio = new UnitAudio({createContext: () => contexts.shift()}); audio.observe(observed(), definition, options);
  check(await audio.enable() === false && !audio.context, 'wave construction failure closes graph');
  check(await audio.enable(), 'user can retry after browser failure'); audio.dispose();
}
{
  const oldResume = pending(), newResume = pending();
  const contexts = [new FakeContext({deferred: oldResume}), new FakeContext({deferred: newResume})];
  const audio = new UnitAudio({createContext: () => contexts.shift()});
  audio.observe(observed(), definition, options); const oldEnable = audio.enable();
  audio.mute(); audio.observe(observed(888, 35), definition, options); const newEnable = audio.enable();
  newResume.resolve(); check(await newEnable, 'new user enable can complete before the old resume');
  const currentContext = audio.context;
  oldResume.reject(new Error('old resume rejected late'));
  check(await oldEnable === false && audio.context === currentContext && audio.oscillator.frequency.value === 888,
    'old resume failure cannot mute or replace a newer graph');
  audio.dispose();
}
{
  const audio = new UnitAudio({createContext: () => { throw new Error('AudioContext unsupported'); }});
  audio.observe(observed(), definition, options);
  check(await audio.enable() === false && !audio.enabled && !audio.context, 'unsupported browser stays muted');
  audio.dispose();
}

const requests = [], browserErrors = [];
const server = createServer(async (request, response) => {
  requests.push({path: request.url, method: request.method});
  const pathname = new URL(request.url, 'http://localhost').pathname;
  if (pathname === '/harness') {
    response.setHeader('Content-Type', 'text/html');
    response.end('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><link rel="stylesheet" href="/platform/web/m5-tokens.css"><link rel="stylesheet" href="/platform/web/unit-panel.css"></head><body><main id="panel"></main></body></html>'); return;
  }
  const path = resolve(root, `.${decodeURIComponent(pathname)}`);
  if (!path.startsWith(root + '/')) { response.writeHead(403).end(); return; }
  try { response.setHeader('Content-Type', {'.js': 'text/javascript', '.css': 'text/css'}[extname(path)] || 'application/octet-stream'); response.end(await readFile(path)); }
  catch { response.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
const browserChecks = [];
try {
  browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--mute-audio', '--autoplay-policy=user-gesture-required']});
  const page = await browser.newPage({viewport: {width: 700, height: 700}});
  page.on('pageerror', error => browserErrors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/harness`);
  await page.evaluate(async definition => {
    const {createUnitPanel} = await import('/platform/web/unit-panel.js');
    window.audioCalls = []; window.createdContexts = [];
    const NativeContext = window.AudioContext;
    window.AudioContext = class extends NativeContext { constructor(...args) { super(...args); window.createdContexts.push(this); } };
    window.audioSession = {session_id: 'browser-audio-fixture', device_id: 'cores3', state: 'running', units: [{id: 'buzz', unit_id: 'buzzer', port_id: 'port-b'}]};
    window.audioDefinition = definition;
    window.payload = (frequency = 4000, duty = 50) => ({source: 'live', definitions: [definition], units: [{...window.audioSession.units[0], source: 'guest-qom', available: true, errors: {}, properties: {'frequency-hz': frequency, 'duty-pct': duty}}]});
    const api = async (path, request = {}) => {
      window.audioCalls.push({path, method: request.method || 'GET'});
      if (request.method && request.method !== 'GET') throw new Error('audio fixture forbids mutations');
      return path.startsWith('/api/v1/units?') ? {units: [definition], hosts: []} : window.payload();
    };
    window.makeAudioPanel = async () => {
      window.panel?.dispose?.();
      window.panel = await createUnitPanel(document.querySelector('#panel'), {session: window.audioSession,
        shell: {attachUnit: async () => ({}), detachUnit() {}, applyVisualState() {}}, api});
      clearTimeout(window.panel.timer);
      window.audio = window.panel.audio.get('buzz');
    };
    await window.makeAudioPanel();
  }, definition);
  const toggle = page.locator('[data-unit-audio-toggle]');
  assert.equal(await toggle.getAttribute('aria-pressed'), 'false');
  assert.equal(await page.evaluate(() => window.createdContexts.length), 0, 'default muted creates no AudioContext');
  assert.match(await page.locator('#panel').textContent(), /不代表实物音色或声压/);
  browserChecks.push('default-muted-no-context-and-acoustic-boundary');
  await toggle.click();
  await page.waitForFunction(() => window.audio.oscillator && window.audio.context.state === 'running');
  const realSignal = await page.evaluate(async () => {
    const analyser = window.audio.context.createAnalyser(); analyser.fftSize = 2048;
    window.audio.gain.connect(analyser);
    const started = performance.now(), observations = [];
    const read = () => {
      const samples = new Float32Array(analyser.fftSize); analyser.getFloatTimeDomainData(samples);
      return {elapsedMs: performance.now() - started, currentTime: window.audio.context.currentTime,
        state: window.audio.context.state, peak: Math.max(...samples.map(Math.abs)),
        frequency: window.audio.oscillator.frequency.value, gain: window.audio.gain.gain.value,
        sampleRate: window.audio.context.sampleRate,
        latency: window.audio.context.baseLatency, outputLatency: window.audio.context.outputLatency,
        outputTimestamp: window.audio.context.getOutputTimestamp()};
    };
    for (const deadline of [100, 250, 500, 1000, 2000]) {
      await new Promise(resolve => setTimeout(resolve, Math.max(0, deadline - (performance.now() - started))));
      observations.push(read());
    }
    analyser.disconnect();
    return {...observations[0], observations, userAgent: navigator.userAgent};
  });
  await writeFile(`${output}/native-diagnostic.json`, JSON.stringify({originalFirstReadThreshold: 0.001, originalFirstReadPass: realSignal.peak > 0.001, nativeAudio: realSignal, browserVersion: browser.version(), browserErrors, requests, device_service_contacted: false}, null, 2) + '\n');
  assert.ok(realSignal.peak > 0.001, 'real browser audio graph contains the PWM waveform');
  assert.equal(realSignal.frequency, 4000);
  browserChecks.push('explicit-click-resumes-native-audio-and-produces-waveform');
  await page.evaluate(() => { window.firstOscillator = window.audio.oscillator; window.panel.apply(window.payload(800, 25)); });
  await page.waitForFunction(() => window.audio.oscillator.frequency.value === 800);
  assert.deepEqual(await page.evaluate(() => ({same: window.audio.oscillator === window.firstOscillator, frequency: window.audio.oscillator.frequency.value, duty: window.audio.signal.duty})), {same: true, frequency: 800, duty: 25});
  browserChecks.push('continuous-actual-parameter-update-same-oscillator');
  await page.screenshot({path: `${output}/unit-audio.png`});
  await toggle.click();
  await page.waitForFunction(() => window.createdContexts.every(context => context.state === 'closed'));
  assert.equal(await toggle.getAttribute('aria-pressed'), 'false');
  browserChecks.push('user-mute-closes-native-context');

  for (const ending of ['stopped', 'session-change', 'unavailable', 'persisted', 'missing-unit', 'invalid-field', 'detach', 'dispose', 'transport']) {
    await page.evaluate(async () => { await window.makeAudioPanel(); });
    await toggle.click(); await page.waitForFunction(() => Boolean(window.audio.oscillator));
    await page.evaluate(async ending => {
      const current = window.audio;
      if (ending === 'stopped') window.panel.updateSession({...window.audioSession, state: 'stopped'});
      else if (ending === 'session-change') {
        window.panel.updateSession({...window.audioSession, session_id: 'next-session'});
        window.panel.apply(window.payload(), window.audioSession.session_id);
      } else if (ending === 'unavailable') { const payload = window.payload(); payload.units[0].available = false; window.panel.apply(payload); }
      else if (ending === 'persisted') window.panel.apply({...window.payload(), source: 'persisted'});
      else if (ending === 'missing-unit') window.panel.apply({...window.payload(), units: []});
      else if (ending === 'invalid-field') window.panel.apply(window.payload(4000, 101));
      else if (ending === 'detach') await window.panel.setShell(null);
      else if (ending === 'dispose') window.panel.dispose();
      else { window.panel.api = async () => { throw new Error('offline fixture'); }; await window.panel.refresh(); clearTimeout(window.panel.timer); }
      if (current.enabled || current.context || current.oscillator || current.gain) throw new Error(`${ending} left audio active`);
    }, ending);
    await page.waitForFunction(() => window.createdContexts.every(context => context.state === 'closed'));
    browserChecks.push(`${ending}-destroys-native-graph-and-context`);
  }
  // A real panel with a deliberately delayed *native* resume must not play
  // after stop, even if that browser promise resolves later.
  await page.evaluate(async () => {
    await window.makeAudioPanel();
    window.audio.createContext = () => {
      const context = new window.AudioContext(), resume = context.resume.bind(context);
      context.resume = () => { const result = resume(); return new Promise(resolve => { window.completeResume = () => result.then(resolve); }); };
      return context;
    };
  });
  await toggle.click();
  await page.waitForFunction(() => window.audio.pending && Boolean(window.completeResume));
  await page.evaluate(() => { window.panel.updateSession({...window.audioSession, state: 'stopped'}); window.completeResume(); });
  await page.waitForFunction(() => window.createdContexts.every(context => context.state === 'closed'));
  assert.equal(await page.evaluate(() => Boolean(window.audio.enabled || window.audio.oscillator || window.audio.context)), false);
  browserChecks.push('late-native-resume-after-stop-does-not-revive-audio');
  const calls = await page.evaluate(() => window.audioCalls);
  assert.ok(calls.every(call => call.method === 'GET'), 'audio controls and observation emit no runtime mutation');
  assert.ok(requests.every(request => request.method === 'GET') && !requests.some(request => request.path.startsWith('/api/')), 'fixture never contacts a Device Service');
  assert.deepEqual(browserErrors, []);
  browserChecks.push('no-post-no-runtime-api-no-browser-errors');
  const paths = ['platform/web/unit-audio.js', 'platform/web/unit-panel.js', 'platform/web/unit-panel.css', 'platform/tests/test_unit_audio.mjs'];
  const source_sha256 = Object.fromEntries(await Promise.all(paths.map(async path => [path, createHash('sha256').update(await readFile(resolve(root, path))).digest('hex')])));
  const receipt = {schema_version: 1, status: 'PASS', category: 'browser-audio-fixture', firmware_executed: false, device_service_contacted: false, acoustic_measurement: false,
    unit_assertions: unitAssertions, browser_checks: browserChecks, native_audio: realSignal, api_calls: calls, requests, source_sha256, captured_at: new Date().toISOString()};
  await writeFile(`${output}/receipt.json`, JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify({status: receipt.status, unit_assertions: unitAssertions, browser_checks: browserChecks.length, output}));
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
