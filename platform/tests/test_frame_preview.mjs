// Browser transport/lifecycle fixtures. No Device Service, firmware or QEMU.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, extname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = resolve(process.env.M5_FRAME_PREVIEW_OUT || '/tmp/m5-frame-preview-test');
await mkdir(output, {recursive: true});
const paths = ['platform/web/sessions.js', 'platform/web/model-shell.js',
  'platform/web/device-shell-factory.js', 'platform/web/three-device-viewer.js'];
const sources = Object.fromEntries(await Promise.all(paths.map(async path => [path, await readFile(resolve(root, path), 'utf8')])));
const source = sources[paths[0]];
const fragments = source.slice(source.indexOf('class SessionVisual {'), source.indexOf('\nfunction createSessionCard')) + '\n' +
  source.slice(source.indexOf('async function refreshFrame('), source.indexOf('\nasync function refreshDeviceState('));
const profile = JSON.parse(await readFile(resolve(root, 'devices/catalog.source.json'), 'utf8')).devices.find(item => item.id === 'cores3');
const html = `<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/platform/web/app.css"><link rel="stylesheet" href="/platform/web/sessions.css"><link rel="stylesheet" href="/platform/web/three-device-viewer.css"><style>body{background:#fff}#fixtures{display:grid;grid-template-columns:440px 440px;gap:12px}.session-visual{width:440px;height:420px}</style><script type="importmap">{"imports":{"three":"/platform/web/vendor/three/three.module.js","three/addons/":"/platform/web/vendor/three/addons/"}}</script></head><body><main id="fixtures"></main></body></html>`;
const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/fixture') { response.setHeader('Content-Type', 'text/html'); response.end(html); return; }
    const path = resolve(root, `.${decodeURIComponent(pathname)}`);
    if (!path.startsWith(root + '/')) { response.writeHead(403).end(); return; }
    response.setHeader('Content-Type', {'.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.json': 'application/json'}[extname(path)] || 'application/octet-stream');
    response.end(await readFile(path));
  } catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
const page = await browser.newPage({viewport: {width: 1100, height: 940}});
const errors = [], checks = [];
page.on('pageerror', error => errors.push(error.message));
async function test(name, run) { await run(); checks.push(name); }
async function setup(extra = {}) {
  await page.evaluate(async ({fragments, extra}) => {
    window.fixture?.cleanup();
    const nativeFetch = window.fixture?.nativeFetch || window.fetch.bind(window);
    const nativeDecode = window.fixture?.nativeDecode || HTMLImageElement.prototype.decode;
    const nativeBitmap = window.fixture?.nativeBitmap || window.createImageBitmap.bind(window);
    const nativeRevoke = window.fixture?.nativeRevoke || URL.revokeObjectURL.bind(URL);
    const state = {visuals: new Map(), sessions: [], deviceProfiles: new Map(), devicePaths: new Map(), deviceStates: new Map(), token: 'fixture-token', frameLoopStarted: false};
    const f = window.fixture = {state, nativeFetch, nativeDecode, nativeBitmap, nativeRevoke,
      calls: [], controlCalls: [], blobsRead: 0, imageDecodes: 0, bitmapDecodes: 0, closedBitmaps: 0,
      revoked: [], plans: new Map(), gates: [], visuals: new Map(), pending: new Map(), done: new Set(), frameJobs: [], imageGates: [], bitmapGates: [], blobs: {}, auto: false,
      gate() { let resolve; const promise = new Promise(done => { resolve = done; }); this.gates.push({promise, resolve, entered: false}); return this.gates.length - 1; },
      async waitGate(index) { const gate = this.gates[index]; gate.entered = true; await gate.promise; },
      release(index) { this.gates[index].resolve(); },
      queue(id, plan = {}) { if (!this.plans.has(id)) this.plans.set(id, []); this.plans.get(id).push(plan); },
      session(id = 'owner-a', values = {}) { return {session_id: id, device_id: 'cores3', runtime: 'qemu', state: 'running', created_at: '2026-10-26T00:00:00Z', firmware_sha256: 'a'.repeat(64), pid: 101, display: {width: 2, height: 2}, ...values}; },
      add(name = 'a', session = this.session()) { const host = document.createElement('div'); host.className = 'session-visual'; host.dataset.fixture = name; document.querySelector('#fixtures').append(host); const visual = new this.Visual(host, session, false); this.visuals.set(name, visual); state.visuals.set(session.session_id, visual); return visual; },
      bind(name, values) { const visual = this.visuals.get(name); if (state.visuals.get(visual.session.session_id) === visual) state.visuals.delete(visual.session.session_id); visual.updateSession({...visual.session, ...values}); state.visuals.set(visual.session.session_id, visual); },
      run(name = 'a', label = 'run') { const visual = this.visuals.get(name); const task = this.refreshFrame(visual.session).finally(() => this.done.add(label)); this.pending.set(label, task); },
      snapshot(name = 'a') { const visual = this.visuals.get(name); const image = visual.container.querySelector('img.session-frame'); let pixel = null; if (image) { const canvas = document.createElement('canvas'); canvas.width = canvas.height = 2; const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0); pixel = [...ctx.getImageData(0, 0, 1, 1).data]; } return {etag: visual.frameEtag, hash: visual.lastFrameHash, url: visual.frameUrl, pixel, blob: Object.entries(this.blobs).find(([, blob]) => blob === visual.frameBlob)?.[0] || null, inFlight: !!visual.frameRequest, metadata: visual.frameMetadata, imageDecodes: this.imageDecodes, bitmapDecodes: this.bitmapDecodes, calls: this.calls.length, revoked: this.revoked.slice()}; },
      cleanup() { this.state.sessions = []; for (const visual of this.visuals.values()) visual.destroy(); for (const gate of this.gates) gate.resolve(); document.querySelector('#fixtures').replaceChildren(); },
    };
    URL.revokeObjectURL = url => { f.revoked.push(url); nativeRevoke(url); };
    HTMLImageElement.prototype.decode = async function () { f.imageDecodes++; const gate = f.imageGates.shift(); if (gate !== undefined) await f.waitGate(gate); return nativeDecode.call(this); };
    window.createImageBitmap = async (...args) => { f.bitmapDecodes++; const gate = f.bitmapGates.shift(); if (gate !== undefined) await f.waitGate(gate); const bitmap = await nativeBitmap(...args); const close = bitmap.close.bind(bitmap); bitmap.close = () => { f.closedBitmaps++; close(); }; return bitmap; };
    window.fetch = async (url, options = {}) => {
      const match = String(url).match(/\/api\/v1\/sessions\/([^/]+)\/frame\.png/);
      if (!match) return nativeFetch(url, options);
      const id = decodeURIComponent(match[1]), headers = new Headers(options.headers);
      const call = {id, url: String(url), etag: headers.get('If-None-Match'), auth: headers.get('Authorization'), cache: options.cache, aborted: options.signal?.aborted || false};
      options.signal?.addEventListener('abort', () => { call.aborted = true; }); f.calls.push(call);
      const plan = f.plans.get(id)?.shift() || (f.auto ? {status: call.etag ? 304 : 200, body: 'green', etag: '"auto"'} : {status: 503});
      if (plan.responseGate !== undefined) await f.waitGate(plan.responseGate); // Deliberately ignores abort to exercise the fence.
      if (plan.error) throw new Error(plan.error);
      const status = plan.status || 200;
      return {status, ok: status >= 200 && status < 300, headers: new Headers({'Content-Type': 'image/png', ...(plan.etag ? {ETag: plan.etag} : {}), 'X-Frame-SHA256': plan.body || 'unchanged', ...(plan.headers || {})}),
        async blob() { f.blobsRead++; if (plan.blobGate !== undefined) await f.waitGate(plan.blobGate); if (plan.blobError) throw new Error(plan.blobError); return f.blobs[plan.body || 'red']; }};
    };
    const {createDeviceShell} = await import('/platform/web/device-shell-factory.js');
    const compiled = new Function('state', 'createDeviceShell', 'ACTIVE_STATES', 'FRAME_INTERVAL_MS', 'FRAME_REQUEST_TIMEOUT_MS', 'HIDDEN_FRAME_INTERVAL_MS', 'CONTROL_RELEASE_TIMEOUT_MS', 'api', 'framePlaceholder', 'escapeHtml', fragments + '\nreturn {SessionVisual, refreshFrame, startFrameLoop};');
    const code = compiled(state, createDeviceShell, new Set(['provisioning', 'flashing', 'booting', 'running']), 125, 3000, 1000, 5000, async (path, options) => { f.controlCalls.push({path, body: JSON.parse(options.body)}); }, () => 'waiting for frame', String);
    const setFrame = code.SessionVisual.prototype.setFrame;
    code.SessionVisual.prototype.setFrame = function (...args) { const work = setFrame.apply(this, args); f.frameJobs.push(work); return work; };
    Object.assign(f, {Visual: code.SessionVisual, refreshFrame: code.refreshFrame, startFrameLoop: code.startFrameLoop, createDeviceShell});
    for (const [name, color] of Object.entries({red: '#ff0000', green: '#00ff00', blue: '#0000ff'})) {
      const canvas = document.createElement('canvas'); canvas.width = canvas.height = 2; const ctx = canvas.getContext('2d'); ctx.fillStyle = color; ctx.fillRect(0, 0, 2, 2); f.blobs[name] = await new Promise(done => canvas.toBlob(done, 'image/png'));
    }
    f.blobs.invalid = new Blob(['invalid png'], {type: 'image/png'});
    f.add('a', f.session('owner-a', extra));
  }, {fragments, extra});
}
async function run(plan, {name = 'a', label = 'run'} = {}) {
  await page.evaluate(({plan, name, label}) => { const f = window.fixture; f.queue(f.visuals.get(name).session.session_id, plan); f.run(name, label); }, {plan, name, label});
  await page.waitForFunction(label => window.fixture.done.has(label), label);
  return page.evaluate(name => window.fixture.snapshot(name), name);
}
async function entered(index) { await page.waitForFunction(index => window.fixture.gates[index].entered, index); }
async function release(index, label) {
  await page.evaluate(index => window.fixture.release(index), index);
  if (label) await page.evaluate(label => window.fixture.pending.get(label), label);
  // Cancellation bounds the public request before an unabortable decoder or
  // hostile fetch fixture settles. Drain the actual rendering work as well,
  // so a late draw cannot occur after the assertion and escape this test.
  await page.evaluate(async () => { await new Promise(done => setTimeout(done, 0)); await Promise.allSettled(window.fixture.frameJobs); });
}
const red = [255, 0, 0, 255], green = [0, 255, 0, 255], blue = [0, 0, 255, 255];
let status = 'FAIL';
try {
  await page.goto(`http://127.0.0.1:${server.address().port}/fixture`);
  await page.clock.install({time: new Date('2026-10-26T12:00:00Z')});
  await test('qemu-200-304-changed-body-and-external-program-context', async () => {
    await setup(); const first = await run({body: 'red', etag: '"A"', headers: {'X-Frame-Program-Execution-Id': 'execution-a'}});
    assert.deepEqual(first.pixel, red); assert.equal(first.etag, '"A"');
    await page.evaluate(() => window.fixture.bind('a', {program: {execution_id: 'external-agent-execution', state: 'running'}}));
    const unchanged = await run({status: 304, etag: '"A"', headers: {'X-Frame-Program-Execution-Id': 'external-agent-execution', 'X-Frame-Sample-Sequence': '2'}}, {label: 'unchanged'});
    assert.equal(unchanged.url, first.url); assert.equal(unchanged.imageDecodes, first.imageDecodes); assert.equal(unchanged.blob, 'red');
    assert.equal(unchanged.metadata['x-frame-program-execution-id'], 'external-agent-execution');
    const changed = await run({body: 'green', etag: '"B"'}, {label: 'changed'});
    assert.deepEqual(changed.pixel, green); assert.equal(changed.etag, '"B"'); assert.notEqual(changed.url, first.url); assert.ok(changed.revoked.includes(first.url));
    const calls = await page.evaluate(() => window.fixture.calls);
    assert.equal(calls[0].etag, null); assert.equal(calls[1].etag, '"A"'); assert.equal(calls[2].etag, '"A"');
    assert.ok(calls.every(call => new URL(call.url, 'http://fixture.local').searchParams.get('max_age_ms') === '125' && call.cache === 'no-store' && call.auth === 'Bearer fixture-token'));
    assert.equal(await page.evaluate(() => window.fixture.blobsRead), 2);
  });
  await test('tab5-network-and-unknown-runtime-retain-fresh-lane', async () => {
    for (const runtime of ['tab5', 'network', null]) {
      await setup({runtime}); await run({body: 'red', etag: '"fresh"'});
      await run({body: 'green', etag: '"fresh-new"'}, {label: 'next'});
      const calls = await page.evaluate(() => window.fixture.calls);
      assert.ok(calls.every(call => !call.url.includes('max_age_ms') && call.url.includes('?t=') && call.etag === null));
      assert.equal((await page.evaluate(() => window.fixture.snapshot())).etag, null);
    }
  });
  await test('late-response-after-session-owner-switch-is-not-read-or-decoded', async () => {
    await setup();
    const gate = await page.evaluate(() => { const f = window.fixture, gate = f.gate(); f.queue('owner-a', {body: 'red', etag: '"old"', responseGate: gate}); f.run('a', 'old'); return gate; });
    await entered(gate);
    await page.evaluate(() => window.fixture.bind('a', {session_id: 'owner-b'}));
    const next = await run({body: 'green', etag: '"new"'}, {label: 'new'}); await release(gate, 'old');
    const after = await page.evaluate(() => window.fixture.snapshot());
    assert.equal(after.etag, '"new"'); assert.deepEqual(after.pixel, green); assert.equal(after.imageDecodes, next.imageDecodes);
    assert.equal(await page.evaluate(() => window.fixture.blobsRead), 1);
  });
  await test('same-id-created-firmware-and-pid-changes-fence-slow-blob', async () => {
    for (const values of [{created_at: '2026-10-26T01:00:00Z'}, {firmware_sha256: 'b'.repeat(64)}, {pid: 202}]) {
      await setup();
      const gate = await page.evaluate(() => { const f = window.fixture, gate = f.gate(); f.queue('owner-a', {body: 'red', etag: '"old"', blobGate: gate}); f.run('a', 'old'); return gate; });
      await entered(gate); await page.evaluate(values => window.fixture.bind('a', values), values);
      const next = await run({body: 'green', etag: '"new"'}, {label: 'new'}); await release(gate, 'old');
      const after = await page.evaluate(() => window.fixture.snapshot());
      assert.equal(after.etag, '"new"'); assert.deepEqual(after.pixel, green); assert.equal(after.imageDecodes, next.imageDecodes);
    }
  });
  await test('slow-generic-decode-cannot-overwrite-new-owner-or-tag', async () => {
    await setup();
    const gate = await page.evaluate(() => { const f = window.fixture, gate = f.gate(); f.imageGates.push(gate); f.queue('owner-a', {body: 'red', etag: '"old"'}); f.run('a', 'old'); return gate; });
    await entered(gate); assert.equal((await page.evaluate(() => window.fixture.snapshot())).etag, null);
    await page.evaluate(() => window.fixture.bind('a', {created_at: '2026-10-26T02:00:00Z'}));
    const next = await run({body: 'green', etag: '"new"'}, {label: 'new'}); await release(gate, 'old');
    await page.waitForFunction(() => window.fixture.revoked.length > 0);
    const after = await page.evaluate(() => window.fixture.snapshot());
    assert.equal(after.url, next.url); assert.deepEqual(after.pixel, green); assert.equal(after.etag, '"new"');
  });
  await test('late-saved-frame-fallback-cannot-overwrite-newer-applied-body', async () => {
    await setup(); await run({body: 'red', etag: '"A"'});
    const gate = await page.evaluate(() => { const f = window.fixture, gate = f.gate(), visual = f.visuals.get('a'); f.imageGates.push(gate); f.fallback = visual.setGenericFrame(visual.frameBlob); return gate; });
    await entered(gate); const next = await run({body: 'green', etag: '"B"'}, {label: 'new'});
    await release(gate); await page.evaluate(() => window.fixture.fallback);
    const after = await page.evaluate(() => window.fixture.snapshot());
    assert.equal(after.url, next.url); assert.equal(after.etag, '"B"'); assert.deepEqual(after.pixel, green);
  });
  await test('dispose-and-reused-container-fence-response-blob-and-decode', async () => {
    for (const stage of ['response', 'blob', 'decode']) {
      await setup();
      const gate = await page.evaluate(stage => { const f = window.fixture, gate = f.gate(); if (stage === 'decode') f.imageGates.push(gate); f.queue('owner-a', {body: 'red', etag: '"old"', ...(stage === 'response' ? {responseGate: gate} : stage === 'blob' ? {blobGate: gate} : {})}); f.run('a', 'old'); return gate; }, stage);
      await entered(gate);
      await page.evaluate(() => { const f = window.fixture, old = f.visuals.get('a'), host = old.container; old.destroy(); const next = new f.Visual(host, f.session('owner-a', {pid: 999}), false); f.visuals.set('a', next); f.state.visuals.set('owner-a', next); });
      const next = await run({body: 'blue', etag: '"new"'}, {label: 'new'}); await release(gate, 'old');
      const after = await page.evaluate(() => window.fixture.snapshot());
      assert.equal(after.url, next.url); assert.deepEqual(after.pixel, blue); assert.equal(after.etag, '"new"');
    }
  });
  await test('owner-change-releases-queued-controls-to-original-session', async () => {
    await setup();
    const calls = await page.evaluate(async () => {
      const f = window.fixture, visual = f.visuals.get('a'), gate = f.gate();
      visual.controlQueues.set('a', f.gates[gate].promise); visual.activeControls.add('a');
      f.bind('a', {session_id: 'owner-b'}); f.release(gate); await visual.controlQueues.get('a');
      return f.controlCalls;
    });
    assert.equal(calls.length, 1); assert.equal(calls[0].path, '/api/v1/sessions/owner-a/input'); assert.equal(calls[0].body.action, 'up');
  });
  await test('response-blob-and-decode-timeouts-release-only-their-request', async () => {
    for (const stage of ['response', 'blob', 'decode']) {
      await setup(); await run({body: 'red', etag: '"A"'}, {label: 'baseline'});
      const gate = await page.evaluate(stage => { const f = window.fixture, gate = f.gate(); if (stage === 'decode') f.imageGates.push(gate); f.queue('owner-a', {body: 'green', etag: '"unapplied"', ...(stage === 'response' ? {responseGate: gate} : stage === 'blob' ? {blobGate: gate} : {})}); f.run('a', 'timeout'); return gate; }, stage);
      await entered(gate); assert.equal((await page.evaluate(() => window.fixture.snapshot())).etag, '"A"');
      await page.clock.fastForward(3001); await page.evaluate(() => window.fixture.pending.get('timeout'));
      const timedOut = await page.evaluate(() => window.fixture.snapshot());
      assert.equal(timedOut.inFlight, false); assert.equal(timedOut.etag, '"A"'); assert.deepEqual(timedOut.pixel, red);
      assert.equal(await page.evaluate(() => window.fixture.calls.at(-1).aborted), true);
      const next = await run({body: 'blue', etag: '"C"'}, {label: 'next'}); await release(gate);
      await page.waitForFunction(() => !window.fixture.visuals.get('a').frameRequest);
      const after = await page.evaluate(() => window.fixture.snapshot());
      assert.equal(after.url, next.url); assert.equal(after.etag, '"C"'); assert.deepEqual(after.pixel, blue);
    }
  });
  await test('invalid-body-does-not-save-etag-or-discard-last-good-frame', async () => {
    await setup(); const baseline = await run({body: 'red', etag: '"good"'});
    const invalid = await run({body: 'invalid', etag: '"invalid"'}, {label: 'invalid'});
    assert.equal(invalid.url, baseline.url); assert.equal(invalid.etag, '"good"'); assert.deepEqual(invalid.pixel, red);
    await setup(); const failed = await run({status: 503}); assert.equal(failed.blob, null); assert.equal(failed.etag, null);
    assert.equal(await page.locator('[data-fixture="a"] .no-frame').textContent(), 'waiting for frame');
  });
  await test('real-model-and-generic-renderers-guard-after-bitmap-decode', async () => {
    await setup();
    const result = await page.evaluate(async profile => {
      const f = window.fixture, results = [];
      for (const kind of ['model', 'generic']) {
        const session = f.session(`renderer-${kind}`), visual = f.add(kind, session);
        const renderingProfile = kind === 'model' ? profile : {...profile, id: 'preview-generic-fixture', shell: {...profile.shell, renderer: null, reference_image: null}};
        const shell = await f.createDeviceShell(visual.container, renderingProfile, {live: true}); visual.shell = shell; visual.container.classList.add('is-three');
        const canvas = document.createElement('canvas'); canvas.width = shell.display?.width || profile.hardware.display.width; canvas.height = shell.display?.height || profile.hardware.display.height;
        const ctx = canvas.getContext('2d');
        const make = async color => { ctx.fillStyle = color; ctx.fillRect(0, 0, canvas.width, canvas.height); return new Promise(done => canvas.toBlob(done, 'image/png')); };
        const red = await make('#ff0000'), green = await make('#00ff00');
        await shell.setImage(red); // Existing caller, with no guard argument.
        const display = () => shell.display?.getContext2D() || shell.canvas.getContext('2d');
        let valid = true; const gate = f.gate(); f.bitmapGates.push(gate);
        const stale = shell.setImage(green, undefined, () => valid);
        await Promise.resolve(); valid = false; f.release(gate); const applied = await stale;
        const rejectedPixel = [...display().getImageData(0, 0, 1, 1).data];
        await shell.setImage(green); const acceptedPixel = [...display().getImageData(0, 0, 1, 1).data];
        results.push({kind, applied, rejectedPixel, acceptedPixel, renderer: shell.root?.dataset.modelSource || visual.container.querySelector('[data-renderer-fallback]')?.dataset.rendererFallback});
      }
      const {ThreeDeviceShell} = await import('/platform/web/three-device-viewer.js');
      const canvas = document.createElement('canvas'); canvas.width = canvas.height = 2; const ctx = canvas.getContext('2d'); ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 0, 2, 2);
      const shell = {display: {width: 2, height: 2, getContext2D: () => ctx, present() {}}, frameSeq: 0, hideOverlay() {}};
      let valid = true; const gate = f.gate(); f.bitmapGates.push(gate); const pending = ThreeDeviceShell.prototype.setImage.call(shell, f.blobs.green, undefined, () => valid);
      await Promise.resolve(); valid = false; f.release(gate); const applied = await pending;
      results.push({kind: 'legacy-three', applied, rejectedPixel: [...ctx.getImageData(0, 0, 1, 1).data]});
      return {results, closedBitmaps: f.closedBitmaps, bitmapDecodes: f.bitmapDecodes};
    }, profile);
    for (const item of result.results) { assert.equal(item.applied, false); assert.deepEqual(item.rejectedPixel, red); if (item.acceptedPixel) assert.deepEqual(item.acceptedPixel, green); }
    assert.equal(result.results[0].renderer, 'm5stack-models'); assert.equal(result.results[1].renderer, 'true');
    assert.equal(result.closedBitmaps, result.bitmapDecodes);
    await page.locator('[data-fixture="a"]').evaluate(node => { node.hidden = true; });
    await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
    await page.locator('#fixtures').screenshot({path: resolve(output, 'renderers.png')});
  });
  await test('slow-three-decode-times-out-without-serializing-new-generation', async () => {
    await setup();
    await page.evaluate(() => { const f = window.fixture, v = f.visuals.get('a'), canvas = document.createElement('canvas'); canvas.width = canvas.height = 2; v.container.replaceChildren(canvas); v.shell = {async setImage(blob, sequence, guard = () => true) { const bitmap = await createImageBitmap(blob); try { if (!guard()) return false; canvas.getContext('2d').drawImage(bitmap, 0, 0); return true; } finally { bitmap.close(); } }, dispose() { canvas.remove(); }}; f.drawnPixel = () => [...canvas.getContext('2d').getImageData(0, 0, 1, 1).data]; });
    const gate = await page.evaluate(() => { const f = window.fixture, gate = f.gate(); f.bitmapGates.push(gate); f.queue('owner-a', {body: 'red', etag: '"old"'}); f.run('a', 'old'); return gate; });
    await entered(gate); await page.clock.fastForward(3001); await page.evaluate(() => window.fixture.pending.get('old'));
    await run({body: 'green', etag: '"new"'}, {label: 'new'}); await release(gate);
    await page.waitForFunction(() => window.fixture.closedBitmaps === 2);
    assert.deepEqual(await page.evaluate(() => window.fixture.drawnPixel()), green); assert.equal((await page.evaluate(() => window.fixture.snapshot())).etag, '"new"');
  });
  await test('slow-session-does-not-delay-other-session-polling-or-overlap-itself', async () => {
    await setup();
    const gate = await page.evaluate(() => { const f = window.fixture, gate = f.gate(); f.auto = true; f.add('b', f.session('owner-b')); f.queue('owner-a', {body: 'red', etag: '"slow"', responseGate: gate}); f.state.sessions = [...f.visuals.values()].map(v => v.session); f.startFrameLoop(); return gate; });
    await entered(gate); await page.clock.runFor(550);
    const calls = await page.evaluate(() => window.fixture.calls);
    assert.equal(calls.filter(call => call.id === 'owner-a').length, 1); assert.ok(calls.filter(call => call.id === 'owner-b').length >= 3);
    await page.evaluate(() => { window.fixture.state.sessions = []; }); await release(gate);
    await page.waitForFunction(() => !window.fixture.visuals.get('a').frameRequest && !window.fixture.visuals.get('b').frameRequest);
  });
  assert.deepEqual(errors, []); status = 'PASS';
} finally {
  const report = {category: 'browser-frame-preview-contract', status, firmware_execution: 'NOT RUN', hardware_execution: 'NOT RUN', browser_version: browser.version(),
    source_sha256: Object.fromEntries(Object.entries(sources).map(([path, body]) => [path, createHash('sha256').update(body).digest('hex')])), checks, errors};
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  await browser.close(); await new Promise(done => server.close(done));
}
console.log(`FRAME_PREVIEW_BROWSER_OK ${checks.length}`);
