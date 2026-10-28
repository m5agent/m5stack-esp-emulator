// Opt-in real Device Service acceptance: lose a successful create response,
// recover the same guest by idempotent replay, then retain evidence and stop it.
// This proves lifecycle recovery only, not application display/input behavior.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium} from 'playwright';

if (!process.argv.includes('--execute')) {
  console.log('NOT RUN: --execute --service http://127.0.0.1:8829 --token-file <private-file> --firmware <CoreS3.bin> --out <ignored-dir>');
  process.exit(0);
}
const args = process.argv.slice(2), option = (key, fallback) => args.includes(key) ? args[args.indexOf(key) + 1] : fallback;
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const service = option('--service', 'http://127.0.0.1:8829'), target = new URL(service);
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(target.hostname));
assert.notEqual(target.port, '8787', 'The user testing service is forbidden.');
assert.ok(option('--token-file') && option('--firmware'));
const token = (await readFile(resolve(option('--token-file')), 'utf8')).trim();
assert.ok(token.length >= 32);
const firmwarePath = resolve(option('--firmware')), firmware = await readFile(firmwarePath);
const python = option('--python', process.env.M5_PYTHON || 'python3');
const output = resolve(option('--out', '.work/public-native-recovery/run'));
await mkdir(output, {recursive: true});
const hash = value => createHash('sha256').update(value).digest('hex');
const receipt = {schema_version: 1, category: 'virtual-device-session-create-response-loss', status: 'FAIL',
  application_display: 'NOT RUN', application_input: 'NOT RUN', hardware_validation: 'NOT RUN',
  firmware_input_sha256: hash(firmware), checks: {}, http: [], page_errors: []};
receipt.sources = Object.fromEntries(await Promise.all([
  'platform/tests/test_public_session_recovery_service.mjs', 'platform/web/public.js',
  'platform/web/public-service.js', 'platform/web/public-session-controller.js',
  'platform/tools/device_service.py', 'platform/tools/serve.py',
].map(async path => [path, hash(await readFile(resolve(root, path)))])));
async function api(path, method = 'GET') {
  const response = await fetch(service + '/api/v1/' + path, {method,
    headers: {Authorization: 'Bearer ' + token}, signal: AbortSignal.timeout(30000)});
  const data = Buffer.from(await response.arrayBuffer());
  assert.ok(response.ok, `Service ${method} ${path} returned ${response.status}: ${data.toString().slice(0, 200)}`);
  return path.includes('/evidence') ? data : JSON.parse(data);
}
async function waitFor(check, timeout = 90000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {if (await check()) return; await delay(200);}
  throw new Error(`Recovery condition did not pass within ${timeout} ms.`);
}
assert.equal((await api('health')).capacity.active_sessions, 0, 'Use an empty dedicated service.');
const before = await api('sessions'), previousIds = new Set(before.sessions.map(row => row.session_id));
const types = {'.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json',
  '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.wasm': 'application/wasm'};
const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (pathname === '/favicon.ico') {response.writeHead(204); response.end(); return;}
    const file = resolve(root, '.' + (pathname === '/' ? '/platform/web/index.html' : decodeURIComponent(pathname)));
    if (!['platform/web/', 'devices/'].some(prefix => file.startsWith(resolve(root, prefix) + '/'))) {
      response.writeHead(403); response.end(); return;
    }
    let data = await readFile(file);
    if (file === resolve(root, 'platform/web/public.js')) data = Buffer.concat([data,
      Buffer.from('\nwindow.__publicRecoveryProbe={state};\n')]);
    response.setHeader('Content-Type', types[extname(file)] || 'application/octet-stream');
    response.end(data);
  } catch {response.writeHead(404); response.end();}
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const pageOrigin = `http://127.0.0.1:${server.address().port}`;
assert.notEqual(pageOrigin, target.origin, 'Exercise cross-origin service access.');
let browser, page, ownedId, guestPid, stopped = false, event = 0;
const createRequests = [], routeWork = [];
try {
  browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  page = await browser.newPage({viewport: {width: 1440, height: 1080}});
  page.on('pageerror', error => receipt.page_errors.push(error.message));
  page.on('request', request => {
    if (!request.url().startsWith(service + '/api/v1/')) return;
    const url = new URL(request.url());
    receipt.http.push({event: ++event, phase: 'request', method: request.method(), path: url.pathname, purge: url.searchParams.get('purge')});
  });
  page.on('response', response => {
    if (!response.url().startsWith(service + '/api/v1/')) return;
    const url = new URL(response.url());
    receipt.http.push({event: ++event, phase: 'response', method: response.request().method(), path: url.pathname, status: response.status()});
  });
  await page.route(service + '/api/v1/sessions', route => {
    const operation = (async () => {
      const request = route.request();
      if (request.method() !== 'POST') {await route.continue(); return;}
      const body = request.postData(), payload = JSON.parse(body);
      assert.ok(payload.idempotency_key, 'Production controller must generate the key.');
      const response = await route.fetch();
      assert.equal(response.status(), 202);
      const session = await response.json();
      createRequests.push({body, response: session});
      if (createRequests.length === 1) {
        ownedId = session.session_id;
        assert.equal(session.idempotent_replay, false);
        // Let the actual guest launch before dropping its first receipt. This
        // waits only for a process, without claiming an application frame.
        let current;
        await waitFor(async () => {current = await api(`sessions/${ownedId}`); return Number.isSafeInteger(current.pid) && current.pid > 0;}, 24000);
        guestPid = current.pid;
        receipt.session = {session_id: ownedId, device_id: current.device_id, pid: guestPid,
          runtime: current.runtime, firmware_sha256: current.firmware_sha256};
        receipt.runtime = JSON.parse(execFileSync(python, ['-c',
          'import ctypes,hashlib,json,pathlib,sys;p=int(sys.argv[1]);b=ctypes.create_string_buffer(4096);assert ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath(p,b,len(b))>0;f=pathlib.Path(b.value.decode());print(json.dumps({"name":f.name,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()}))', String(guestPid)], {encoding: 'utf8'}));
        assert.equal(receipt.runtime.sha256, option('--expected-runtime', 'cc21773f0ad91fa589447d3badb1eb681b74170cd8b749153f37ad23cebc70c2'));
        await page.evaluate(() => {window.__recoveryController = window.__publicRecoveryProbe.state.run.controller;});
        receipt.checks.actual_guest_allocated_before_loss = true;
        receipt.http.push({event: ++event, phase: 'injected-response-loss', method: 'POST', path: '/api/v1/sessions', status: 202});
        await route.abort('failed');
      } else {
        assert.equal(createRequests.length, 2, 'Recovery must not create a third request.');
        assert.equal(session.session_id, ownedId);
        assert.equal(session.idempotent_replay, true);
        await route.fulfill({response});
      }
    })();
    routeWork.push(operation);
    return operation;
  });
  await page.goto(pageOrigin + '/?device=cores3&mode=service&autostart=0', {waitUntil: 'domcontentloaded'});
  await page.waitForFunction(() => window.__publicRecoveryProbe?.state.selected?.id === 'cores3' && window.__publicRecoveryProbe.state.shell);
  await page.locator('#serviceConnection').evaluate(node => {node.open = true;});
  await page.fill('#serviceUrl', service);
  await page.fill('#serviceToken', token);
  await page.click('#connectServiceBtn');
  await page.waitForFunction(() => window.__publicRecoveryProbe.state.serviceDevices.some(row => row.device_id === 'cores3' && row.creatable));
  receipt.checks.cross_origin_real_homepage_connected = true;
  await page.check('input[name="firmwareSource"][value="local"]');
  await page.locator('#firmwareFile').setInputFiles(firmwarePath);
  await page.click('#startBtn');
  await page.waitForFunction(() => window.__recoveryController && !window.__recoveryController.current
    && !window.__recoveryController.createIntent && !window.__recoveryController.pendingCreate
    && window.__recoveryController.lastEvidence instanceof Blob && !window.__publicRecoveryProbe.state.run,
  {}, {timeout: 120000});
  await Promise.all(routeWork);
  assert.equal(createRequests.length, 2);
  assert.equal(createRequests[0].body, createRequests[1].body, 'Replay must preserve exact JSON bytes.');
  receipt.creates = createRequests.map(({body, response}) => ({body_sha256: hash(body),
    idempotency_key_sha256: hash(JSON.parse(body).idempotency_key), session_id: response.session_id,
    idempotent_replay: response.idempotent_replay}));
  const evidenceBytes = Buffer.from(await page.evaluate(async () => [...new Uint8Array(await window.__recoveryController.lastEvidence.arrayBuffer())]));
  await writeFile(resolve(output, 'evidence.zip'), evidenceBytes);
  assert.equal(evidenceBytes.subarray(0, 2).toString(), 'PK');
  receipt.evidence = JSON.parse(execFileSync(python, ['-c',
    'import hashlib,json,sys,zipfile;z=zipfile.ZipFile(sys.argv[1]);m=json.loads(z.read("manifest.json"));rows=m["files"];assert all(len(z.read(p))==r["size"] and hashlib.sha256(z.read(p)).hexdigest()==r["sha256"] for p,r in rows.items());print(json.dumps({"zip_sha256":hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest(),"verified_files":len(rows),"session_id":m["session"]["session_id"]}))', resolve(output, 'evidence.zip')], {encoding: 'utf8'}));
  assert.equal(receipt.evidence.session_id, ownedId);
  const evidenceResponse = receipt.http.find(row => row.phase === 'response' && row.path.endsWith('/evidence') && row.status === 200);
  const deleteRequest = receipt.http.find(row => row.phase === 'request' && row.method === 'DELETE' && row.path === `/api/v1/sessions/${ownedId}`);
  assert.ok(evidenceResponse && deleteRequest && evidenceResponse.event < deleteRequest.event);
  assert.equal(deleteRequest.purge, '0');
  const history = await api(`sessions/${ownedId}`);
  await writeFile(resolve(output, 'history.json'), JSON.stringify(history, null, 2) + '\n');
  assert.ok(['stopped', 'failed'].includes(history.state));
  assert.notEqual(history.stop_pending, true);
  assert.equal(history.worker.lease_active, false);
  assert.equal(history.flash_retained, false);
  const all = await api('sessions'), newSessions = all.sessions.filter(row => !previousIds.has(row.session_id));
  assert.equal(newSessions.length, 1);
  assert.equal(newSessions[0].session_id, ownedId);
  assert.equal((await api('health')).capacity.active_sessions, 0);
  await waitFor(() => {try {process.kill(guestPid, 0); return false;} catch (error) {if (error.code === 'ESRCH') return true; throw error;}}, 10000);
  stopped = true;
  Object.assign(receipt.checks, {real_upload_and_import: true, same_key_body_id_replay: true,
    exactly_one_new_history_session: true, evidence_zip_before_delete: true, purge_zero_retained_history: true,
    terminal_lease_released: true, no_active_sessions: true, actual_guest_pid_exited: true,
    automatic_homepage_failure_cleanup: true});
  assert.deepEqual(receipt.page_errors, []);
  await page.screenshot({path: resolve(output, 'homepage-recovered.png'), fullPage: true});
  receipt.status = 'PASS';
  console.log(JSON.stringify({status: receipt.status, checks: receipt.checks, creates: receipt.creates,
    evidence: receipt.evidence, runtime: receipt.runtime}));
} catch (error) {
  receipt.failure = error.message;
  throw error;
} finally {
  if (ownedId && !stopped) {
    try {
      await writeFile(resolve(output, 'cleanup-evidence.zip'), await api(`sessions/${ownedId}/evidence`));
      await api(`sessions/${ownedId}?purge=0`, 'DELETE');
      await waitFor(async () => {const row = await api(`sessions/${ownedId}`); return ['stopped', 'failed'].includes(row.state) && !row.stop_pending && row.worker?.lease_active === false;}, 30000);
    } catch (error) {receipt.cleanup_error = error.message;}
  }
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
  await writeFile(resolve(output, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
}
