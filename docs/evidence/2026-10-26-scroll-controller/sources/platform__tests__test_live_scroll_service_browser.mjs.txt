// Opt-in actual browser -> Device Service -> original guest ScrollUnit -> 3D/frame.
// One owned visible session only; no physical hardware or wheel-angle claim.
import assert from 'node:assert/strict';
import {createHash, randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium} from 'playwright';

assert.equal(process.env.M5_UNIT_SERVICE_E2E, '1', 'Explicit opt-in required: creates one visible virtual session.');
const expectedRuntime = process.env.M5_EXPECTED_RUNTIME_SHA256;
assert.match(expectedRuntime || '', /^[0-9a-f]{64}$/);
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const base = process.env.M5_DEVICE_SERVICE_URL || 'http://127.0.0.1:8787';
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname));
const output = resolve(process.env.M5_SCROLL_LIVE_BROWSER_OUT || '/tmp/m5-scroll-live-browser');
await mkdir(output, {recursive: false});
const python = process.env.M5_PYTHON || '/opt/miniconda3/bin/python3.12';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const sources = ['platform/tests/test_live_scroll_service_browser.mjs', 'platform/web/sessions.js', 'platform/web/sessions.html',
  'platform/web/program-panel.js', 'platform/web/unit-panel.js', 'platform/web/model-shell.js', 'platform/web/unit-visual-mappings.js',
  'platform/units/catalog.json', 'platform/units/runtime-profiles.json', 'platform/web/vendor/m5stack-models/vendor-manifest.json',
  'platform/web/vendor/m5stack-models/src/units/scroll/index.js', 'tests/units/scroll_protocol_probe.py'];
const fingerprints = async () => Object.fromEntries(await Promise.all(sources.map(async path => [path, sha(await readFile(resolve(root, path)))])));
const report = {schema_version: 1, category: 'actual-scroll-web-guest-controller-frame-loop', status: 'FAIL',
  captured_at: new Date().toISOString(), device_id: 'cores3', unit_id: 'scroll', runtime: 'qemu', hardware_validation: 'NOT RUN',
  official_driver: 'https://github.com/m5stack/uiflow-micropython/blob/3a86d8f611b3639cca755a933e01a5a829771ef1/m5stack/libs/unit/scroll.py',
  official_api: 'https://uiflow-micropython.readthedocs.io/en/latest/units/scroll.html',
  instrumentation: 'Only append window.__scrollWebProbe={state,SessionVisual}; observe existing public components and real HTTP responses.',
  limits: ['Stable latest RGB values only; firmware RGB queue/burst/slot behavior is not validated.', 'No calibrated count-to-angle binding, TIM rollover, bootloader, persistence or physical hardware claim.'],
  source_sha256: await fingerprints(), unit_posts: [], samples: [], checks: {}, page_errors: [], resource_errors: [], shared_frames: []};
const api = async (path, options = {}, timeout = 30000) => {
  const response = await fetch(`${base}/api/v1/${path}`, {...options, signal: AbortSignal.timeout(timeout)});
  const bytes = Buffer.from(await response.arrayBuffer());
  if (!response.ok) throw new Error(`${response.status}: ${bytes.toString()}`);
  return path.includes('frame.png') || path.endsWith('/evidence') ? bytes : JSON.parse(bytes);
};
const eventually = async (read, predicate, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    const value = await read();
    if (predicate(value)) return value;
    await delay(125);
  }
  throw new Error('Actual Scroll observation deadline exceeded');
};
const runtimeIdentity = pid => JSON.parse(execFileSync(python, ['-c',
  'import ctypes,hashlib,json,pathlib,sys;b=ctypes.create_string_buffer(4096);p=int(sys.argv[1]);assert ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath(p,b,len(b))>0;f=pathlib.Path(b.value.decode());print(json.dumps({"pid":p,"executable_name":f.name,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()}))', String(pid)], {encoding: 'utf8'}));
const unitState = payload => {
  assert.equal(payload.session_id, report.session_id); assert.equal(payload.source, 'live');
  const units = payload.units.filter(unit => unit.id === 'external1');
  assert.equal(units.length, 1); assert.equal(units[0].unit_id, 'scroll'); assert.equal(units[0].available, true);
  assert.equal(units[0].source, 'guest-qom'); assert.deepEqual(units[0].errors, {});
  return units[0].properties;
};
function guestSource(pins, nonce, marker) {
  return `import sys, time, json
import M5
from hardware import I2C, Pin
from unit import ScrollUnit
sys.path.append(${JSON.stringify(nonce)})
M5.begin()
i2c=I2C(0,scl=Pin(${pins.white}),sda=Pin(${pins.yellow}),freq=100000)
scroll=ScrollUnit(i2c,0x40)
screen=M5.Display
screen.setBrightness(255)
screen.setTextSize(2)
print(${JSON.stringify(marker + ' ')}+json.dumps({'kind':'ready','firmware':scroll.get_firmware_version(),'nonce':${JSON.stringify(nonce)}}))
previous=None
last_sample=time.ticks_ms()
while True:
 assert ${JSON.stringify(nonce)} in sys.path, 'MicroPython VM reset'
 M5.update()
 pressed=scroll.get_button_status()
 value=scroll.get_rotary_value()
 increment=scroll.get_rotary_increments()
 color=0xff0000 if pressed else 0x00ff00
 current=(pressed,value)
 changed=current!=previous
 if changed:
  scroll.fill_color(color)
  screen.fillScreen(color)
  screen.setTextColor(0xffffff,color)
  screen.setCursor(16,60)
  screen.print('SCROLL '+str(value))
  screen.setCursor(16,100)
  screen.print('PRESSED' if pressed else 'RELEASED')
 now=time.ticks_ms()
 if changed or time.ticks_diff(now,last_sample)>=250:
  print(${JSON.stringify(marker + ' ')}+json.dumps({'kind':'sample','pressed':pressed,'value':value,'increment':increment,'color':color,'nonce':${JSON.stringify(nonce)}}))
  last_sample=now
 previous=current
 time.sleep_ms(25)
`;
}
const matchingSample = (data, marker, expected) => {
  for (const line of data.split(/(?<=\n)/)) {
    if (!line.startsWith(marker + ' ') || !line.endsWith('\n')) continue;
    let value; try {value = JSON.parse(line.slice(marker.length + 1));} catch {continue;}
    if (value?.kind === 'sample' && Object.entries(expected).every(([key, wanted]) => typeof value[key] === typeof wanted && value[key] === wanted)) return value;
  }
  return null;
};

// The host validator only parses saved bytes. It never imports/executes guest
// source; actual MicroPython execution occurs exclusively inside Device Service.
const zipValidator = String.raw`
import hashlib,json,pathlib,stat,sys,zipfile
from PIL import Image
sha=lambda b:hashlib.sha256(b).hexdigest()
canonical=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
r=json.loads(pathlib.Path(sys.argv[2]).read_text())
with zipfile.ZipFile(sys.argv[1]) as z:
 names=z.namelist();assert z.testzip() is None and len(names)==len(set(names))
 for n in names:
  p=pathlib.PurePosixPath(n);assert not p.is_absolute() and '..' not in p.parts and '\\' not in n and p.as_posix()==n
  assert stat.S_IFMT(z.getinfo(n).external_attr>>16)!=stat.S_IFLNK
 m=json.loads(z.read('manifest.json'));assert set(m['files'])==set(names)-{'manifest.json'}
 for n,v in m['files'].items():
  b=z.read(n);assert type(v['size']) is int and v['size']==len(b) and v['sha256']==sha(b)
 s=m['session'];assert s['state']=='running'
 for k in ['session_id','device_id','runtime','pid','firmware_sha256','worker']:assert s[k]==r[k]
 assert m['device']['device_id']==r['device_id']
 assert {'serial.log','frames/current.png','qom/snapshot.json','units/contract.json','units/runtime.json','units/state.json'}<=set(names)
 assert json.loads(z.read('units/runtime.json'))['attachments']==r['attachments']==s['units']
 state=json.loads(z.read('units/state.json'));assert state==m['units'] and state['session_id']==r['session_id'] and state['source']=='live'
 contract=json.loads(z.read('units/contract.json'));assert contract['source_hashes']==state['contract_hashes']==r['contract_hashes']
 assert contract['units']['scroll']['id']=='scroll'
 raw=z.read('serial.log');text=raw.decode('utf8',errors='replace');assert text.count('ESP-ROM:')==1 and text.count('M5EMU_UART_REPL_READY')==1
 p=r['program']['program'];saved=json.loads(z.read('programs/'+p['execution_id']+'.json'))
 for k in ['execution_id','revision_id','source_sha256','pid','firmware_sha256']:assert saved[k]==p[k]
 assert saved['state']=='running' and saved['pid']==r['pid'] and saved['firmware_sha256']==r['firmware_sha256']
 assert text.count('__M5_EXEC_'+p['execution_id']+'__:START')==1 and '__M5_EXEC_'+p['execution_id']+'__:ERROR' not in text
 original=json.loads(z.read('programs/'+p['revision_id']+'/source.json'));files={'main.py':r['submitted_source']}
 assert original=={'entrypoint':'main.py','files':files}
 assert sha(canonical({'source_kind':'uiflow2-python',**original}))==p['revision_id'] and sha(canonical(files))==p['source_sha256']
 metadata=json.loads(z.read('programs/'+p['revision_id']+'/revision.json'));assert metadata['revision_id']==p['revision_id'] and metadata['source_sha256']==p['source_sha256']
 assert metadata['files']==[{'path':'main.py','size':len(r['submitted_source'].encode()),'sha256':sha(r['submitted_source'].encode())}]
 assert s['program']['execution_id']==p['execution_id'] and s['program']['state']=='running'
 for sample in r['samples']:
  a=sample['offset'];w=sample['window'];b=w['next_offset'];assert type(a) is int and type(b) is int and a==w['offset'] and 0<=a<=b<=len(raw)
  assert sha(raw[:a].decode('utf8',errors='replace').encode())==sample['prefix_sha256']
  assert raw[a:b].decode('utf8',errors='replace')==w['data'] and w['session_id']==r['session_id'] and w['bytes']==b-a
  matches=[]
  for line in w['data'].splitlines(keepends=True):
   if not line.endswith('\n') or not line.startswith(r['marker']+' '):continue
   try:v=json.loads(line[len(r['marker'])+1:])
   except ValueError:continue
   if type(v) is dict and all(k in v and type(v[k]) is type(x) and v[k]==x for k,x in sample['expected'].items()):matches.append(v)
  assert sample['sample'] in matches
 for frame in r['frames']:
  b=pathlib.Path(sys.argv[1]).parent.joinpath(frame['path']).read_bytes();assert sha(b)==frame['sha256']
  with Image.open(pathlib.Path(sys.argv[1]).parent/frame['path']) as im:im.load();assert im.format=='PNG' and list(im.size)==frame['metrics']['size']
 assert sha(z.read('frames/current.png'))==r['frames'][-1]['sha256']
 print(json.dumps({'status':'PASS','members':len(names),'serial_windows':len(r['samples']),'original_source_and_revision_sha':True,'identity_and_member_sha':True,'zip_sha256':sha(pathlib.Path(sys.argv[1]).read_bytes())}))
`;

let browser, page, currentId;
try {
  report.tooling = {node_version: process.version, node_sha256: sha(await readFile(process.execPath)),
    python_version: execFileSync(python, ['--version'], {encoding: 'utf8'}).trim(), python_sha256: sha(await readFile(python)),
    zip_validator_sha256: sha(Buffer.from(zipValidator))};
  report.service_start = await api('health');
  assert.ok(report.service_start.ok);
  browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  report.browser_version = browser.version();
  page = await browser.newPage({viewport: {width: 1440, height: 1080}});
  page.on('pageerror', error => report.page_errors.push(error.message));
  page.on('response', response => {
    const url = new URL(response.url());
    if (response.status() >= 400 && url.pathname.includes('/vendor/')) report.resource_errors.push({path: url.pathname, status: response.status()});
    if (currentId && url.pathname === `/api/v1/sessions/${currentId}/frame.png`) report.shared_frames.push({path: url.pathname, query: url.search, status: response.status(), headers: response.headers()});
    if (currentId && url.pathname === `/api/v1/sessions/${currentId}/unit-input` && response.request().method() === 'POST') {
      report.unit_posts.push({path: url.pathname, request: response.request().postDataJSON(), status: response.status()});
    }
  });
  await page.route('**/platform/web/sessions.js*', async route => {
    const response = await route.fetch(); const content = await response.text();
    assert.equal(sha(content), report.source_sha256['platform/web/sessions.js']);
    await route.fulfill({response, body: content + '\nwindow.__scrollWebProbe={state,SessionVisual};\n'});
  });
  await page.goto(`${base}/platform/web/sessions.html`, {waitUntil: 'domcontentloaded'});
  await page.locator('#deviceSelect option[value="cores3"]').waitFor({state: 'attached'});
  await page.selectOption('#deviceSelect', 'cores3');
  await page.locator('#unitModelSelect option[value="scroll"]').waitFor({state: 'attached'});
  await page.selectOption('#unitModelSelect', 'scroll'); await page.check('#programModeInput');
  const createReply = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/sessions' && response.request().method() === 'POST');
  await page.click('#createBtn'); const createdResponse = await createReply;
  report.creation_request = createdResponse.request().postDataJSON(); report.created = await createdResponse.json();
  if (createdResponse.status() === 202 && typeof report.created.session_id === 'string') currentId = report.created.session_id;
  assert.equal(createdResponse.status(), 202, JSON.stringify(report.created)); assert.equal(report.creation_request.program_mode, 'uiflow-live');
  assert.match(currentId || '', /^[0-9a-f]{32}$/); report.session_id = currentId;
  const prefix = `sessions/${currentId}`;
  const ready = await eventually(() => api(prefix), value => ['running', 'failed', 'stopped'].includes(value.state), 120000);
  assert.equal(ready.state, 'running', ready.error);
  Object.assign(report, {pid: ready.pid, firmware_sha256: ready.firmware_sha256, worker: ready.worker, attachments: ready.units});
  report.runtime_identity = runtimeIdentity(ready.pid); assert.equal(report.runtime_identity.sha256, expectedRuntime);
  const firstUnits = await api(prefix + '/units'); report.contract_hashes = firstUnits.contract_hashes;
  assert.equal(unitState(firstUnits)['source-count'], 0); assert.equal(unitState(firstUnits).pressed, false);
  const card = page.locator(`[data-session-id="${currentId}"]`);
  const editor = card.locator('[data-program-source]'), run = card.locator('[data-program-run]');
  await run.waitFor({state: 'visible'}); await eventually(() => run.isEnabled(), Boolean);
  await page.waitForFunction(id => window.__scrollWebProbe?.state.visuals.get(id)?.unitPanel?.mounted.size === 1, currentId, {timeout: 90000});
  report.marker = 'SCROLL_WEB_' + randomUUID().replaceAll('-', '').slice(0, 12).toUpperCase();
  report.vm_nonce = '/m5-scroll-web-' + randomUUID().replaceAll('-', '');
  report.submitted_source = guestSource(ready.units[0].pins, report.vm_nonce, report.marker);
  report.submitted_source_sha256 = sha(Buffer.from(report.submitted_source));
  const beforeProgram = await api(prefix + '/serial?offset=0&limit=1048576');
  const programReply = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/sessions/${currentId}/program` && response.request().method() === 'POST');
  await editor.fill(report.submitted_source); await run.click(); const submitted = await programReply;
  report.program_request = submitted.request().postDataJSON();
  report.program = await submitted.json();
  // A global revision-quota rejection is a service admission failure, not a
  // guest execution failure. Save its exact HTTP envelope before cleanup.
  report.program_http_status = submitted.status();
  assert.equal(submitted.status(), 200, 'program admission: ' + JSON.stringify(report.program));
  assert.equal(report.program_request.source, report.submitted_source); assert.equal(report.program_request.expected_execution_id, null);
  assert.equal(report.program.program.pid, report.pid); assert.equal(report.program.program.firmware_sha256, report.firmware_sha256);
  const execution = report.program.program.execution_id;
  const observe = async (before, expected) => {
    const wanted = {kind: 'sample', nonce: report.vm_nonce, ...expected};
    const window = await eventually(async () => {
      const program = (await api(prefix + '/program')).program;
      assert.equal(program.execution_id, execution); assert.equal(program.pid, report.pid); assert.equal(program.state, 'running');
      return api(prefix + `/serial?offset=${before.next_offset}&limit=1048576`);
    }, value => Boolean(matchingSample(value.data, report.marker, wanted)));
    const result = {offset: before.next_offset, prefix_sha256: sha(Buffer.from(before.data)), window, expected: wanted, sample: matchingSample(window.data, report.marker, wanted)};
    report.samples.push(result); return result;
  };
  await observe(beforeProgram, {pressed: false, value: 0, color: 0x00ff00});
  report.checks.original_scroll_api_running_in_same_guest = true;
  await card.locator('canvas').first().scrollIntoViewIfNeeded();
  report.framing = await page.evaluate(async id => {
    const {Box3, Vector3} = await import('/platform/web/vendor/three/three.module.js');
    const visual = window.__scrollWebProbe.state.visuals.get(id), shell = visual.shell, viewer = shell.viewer;
    window.scrollWebEvents = []; window.scrollWebTrusted = [];
    shell.on('unit-input', event => window.scrollWebEvents.push(structuredClone(event)));
    viewer.renderer.domElement.addEventListener('pointerdown', event => window.scrollWebTrusted.push(event.isTrusted));
    viewer.setView('front', {duration: 0}); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    viewer.resize(); viewer.fit({padding: 1.65, duration: 0}); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    viewer.scene.updateMatrixWorld(true); viewer.camera.updateMatrixWorld(true);
    const box = new Box3().setFromObject(shell.model.port('grove').module.root), rect = viewer.renderer.domElement.getBoundingClientRect(), points = [];
    for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
      const p = new Vector3(x, y, z).project(viewer.camera); points.push({x: (p.x + 1) * rect.width / 2, y: (1 - p.y) * rect.height / 2, z: p.z});
    }
    return {width: rect.width, height: rect.height, points};
  }, currentId);
  assert.ok(report.framing.points.every(p => p.x >= 4 && p.x <= report.framing.width - 4 && p.y >= 4 && p.y <= report.framing.height - 4 && p.z > -1 && p.z < 1));
  const pressPoint = () => page.evaluate(async id => {
    const {Box3, Vector3} = await import('/platform/web/vendor/three/three.module.js');
    const viewer = window.__scrollWebProbe.state.visuals.get(id).shell.viewer, button = viewer.device.button('grove/press');
    viewer.scene.updateMatrixWorld(true); viewer.camera.updateMatrixWorld(true);
    const box = new Box3().setFromObject(button.cap), rect = viewer.renderer.domElement.getBoundingClientRect();
    for (const fx of [.5, .25, .75]) for (const fy of [.5, .25, .75]) {
      const p = new Vector3(box.min.x + (box.max.x - box.min.x) * fx, box.min.y + (box.max.y - box.min.y) * fy, box.max.z).project(viewer.camera);
      const hit = {clientX: rect.left + (p.x + 1) * rect.width / 2, clientY: rect.top + (1 - p.y) * rect.height / 2};
      if (viewer.pick(hit)?.component === button && hit.clientY > 0 && hit.clientY < innerHeight) return {x: hit.clientX, y: hit.clientY};
    }
    throw new Error('actual mounted Scroll press is not a visible raycast target');
  }, currentId);
  report.frames = [];
  const capture = async (name, pressed, value, color) => {
    const state = unitState(await eventually(() => api(prefix + '/units'), payload => {
      const p = unitState(payload); return p.pressed === pressed && p.counter === value && p['led-rgb'] === color;
    }));
    const visual = await eventually(() => page.evaluate(id => {
      const v = window.__scrollWebProbe.state.visuals.get(id), led = v.shell.model.find('grove/rgb', 'led');
      return {led: led.getState(), glow: led.glow.visible, opacity: led.glow.material.opacity, emissive: led.lensMaterial.emissive.toArray(), pressed: v.shell.model.button('grove/press').getState().pressed,
        joint: v.shell.model.find('grove/rotation', 'joint').getState(), frameMetadata: v.frameMetadata};
    }, currentId), item => item.led.color === '#' + color.toString(16).padStart(6, '0') && item.led.brightness === 1 && item.pressed === pressed);
    assert.equal(visual.glow, true); assert.equal(visual.opacity, .85); assert.ok(visual.emissive.some(value => value > 0));
    assert.equal(visual.joint.angleDeg, 0); assert.equal(visual.joint.targetAngleDeg, 0); assert.equal(visual.joint.rpm, 0);
    let png;
    const metrics = await eventually(async () => {
      png = await api(prefix + '/frame.png');
      return page.evaluate(async ({encoded, color}) => {
        const image = await createImageBitmap(new Blob([Uint8Array.from(atob(encoded), value => value.charCodeAt(0))], {type: 'image/png'}));
        const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
        const context = canvas.getContext('2d'); context.drawImage(image, 0, 0); const rgba = context.getImageData(0, 0, image.width, image.height).data;
        const wanted = [color >> 16 & 255, color >> 8 & 255, color & 255]; let matching = 0;
        for (let i = 0; i < rgba.length; i += 4) if (wanted.every((value, channel) => Math.abs(value - rgba[i + channel]) <= 8)) matching++;
        const points = [[image.width - 2, image.height - 2], [2, 2], [image.width - 2, 2]];
        const pixels = points.map(([x, y]) => ({x, y, rgb: [...context.getImageData(x, y, 1, 1).data].slice(0, 3)}));
        image.close(); return {size: [canvas.width, canvas.height], matching_pixels: matching, ratio: matching / (canvas.width * canvas.height), pixels};
      }, {encoded: png.toString('base64'), color});
    }, metrics => metrics.ratio > .6);
    await page.waitForFunction(({id, metrics, execution}) => {
      const v = window.__scrollWebProbe.state.visuals.get(id), display = v?.shell?.display;
      return display && display.width === metrics.size[0] && display.height === metrics.size[1] && metrics.pixels.every(p => p.rgb.every((channel, i) => display.getPixel(p.x, p.y)[i] === channel))
        && v.frameMetadata?.['x-frame-execution-id'] === execution && v.frameMetadata?.['x-frame-source'] === 'live';
    }, {id: currentId, metrics, execution}, {timeout: 60000});
    const path = `${name}-frame.png`; await writeFile(resolve(output, path), png);
    const clip = await card.boundingBox(); assert.ok(clip);
    const screenshot = `${name}-browser.png`; const screenshotBytes = await page.screenshot({path: resolve(output, screenshot), clip, captureBeyondViewport: true});
    report.frames.push({name, path, sha256: sha(png), metrics, state, visual, screenshot: {path: screenshot, sha256: sha(screenshotBytes)}});
    return report.frames.at(-1);
  };
  await capture('released-initial', false, 0, 0x00ff00);
  const point = await pressPoint();
  let before = await api(prefix + '/serial?offset=0&limit=1048576');
  await page.mouse.move(point.x, point.y); await page.mouse.down();
  await eventually(async () => report.unit_posts, posts => posts.some(post => post.request.values.pressed === true));
  await observe(before, {pressed: true, value: 0, color: 0xff0000});
  await capture('pressed', true, 0, 0xff0000);
  before = await api(prefix + '/serial?offset=0&limit=1048576'); await page.mouse.up();
  await observe(before, {pressed: false, value: 0, color: 0x00ff00});
  await capture('released', false, 0, 0x00ff00);
  const sourceField = card.locator('[data-input-field="source-count"]');
  for (const count of [3, -2]) {
    before = await api(prefix + '/serial?offset=0&limit=1048576');
    const reply = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/sessions/${currentId}/unit-input` && response.request().method() === 'POST');
    await sourceField.fill(String(count)); await sourceField.press('Tab'); assert.equal((await reply).status(), 200);
    await observe(before, {pressed: false, value: count, color: 0x00ff00});
    assert.equal(unitState(await api(prefix + '/units'))['source-count'], count);
    await capture(`source-${count}`, false, count, 0x00ff00);
  }
  assert.deepEqual(report.unit_posts.map(post => post.request.values), [{pressed: true}, {pressed: false}, {'source-count': 3}, {'source-count': -2}]);
  assert.ok(report.unit_posts.every(post => post.status === 200 && post.request.id === 'external1'));
  const beforeEcho = await page.evaluate(() => ({events: window.scrollWebEvents.length, trusted: window.scrollWebTrusted, now: performance.now()}));
  assert.ok(beforeEcho.trusted.length > 0 && beforeEcho.trusted.every(Boolean));
  const postCount = report.unit_posts.length, sharedCount = report.shared_frames.length;
  await delay(1600);
  assert.equal(report.unit_posts.length, postCount, 'readback/frame refresh must not echo fixture inputs');
  assert.equal(await page.evaluate(() => window.scrollWebEvents.length), beforeEcho.events, 'readback must not emit physical input');
  assert.ok(report.shared_frames.length > sharedCount, 'zero-echo observation must include actual continued frame polling');
  report.zero_echo = {observed_ms: 1600, unit_posts_before: postCount, unit_posts_after: report.unit_posts.length, new_shared_frames: report.shared_frames.length - sharedCount, physical_events_before: beforeEcho.events, physical_events_after: await page.evaluate(() => window.scrollWebEvents.length)};
  report.checks.trusted_canvas_to_http_original_driver_and_gpio_i2c = true;
  report.checks.guest_rgb_to_controller_http_and_real_led_material = true;
  report.checks.actual_png_to_model_display_and_live_execution_metadata = true;
  report.checks.web_source_count_to_original_low16_api_without_guessed_rotation = true;
  report.checks.runtime_readback_zero_input_echo = true;
  const final = await api(prefix); assert.equal(final.pid, report.pid); assert.equal(final.firmware_sha256, report.firmware_sha256); assert.deepEqual(final.worker, report.worker);
  report.final_runtime_identity = runtimeIdentity(final.pid); assert.equal(report.final_runtime_identity.sha256, expectedRuntime);
  report.final_program = await api(prefix + '/program'); assert.equal(report.final_program.program.execution_id, execution); assert.equal(report.final_program.program.state, 'running');
  const evidence = await api(prefix + '/evidence'); await writeFile(resolve(output, 'evidence.zip'), evidence);
  await writeFile(resolve(output, 'validation-input.json'), JSON.stringify(report));
  report.evidence = JSON.parse(execFileSync(python, ['-c', zipValidator, resolve(output, 'evidence.zip'), resolve(output, 'validation-input.json')], {encoding: 'utf8', timeout: 30000}));
  assert.equal(report.evidence.zip_sha256, sha(evidence));
  report.checks.same_vm_pid_firmware_source_uart_and_zip_evidence = true;
  assert.deepEqual(report.page_errors, []); assert.deepEqual(report.resource_errors, []);
  assert.deepEqual(await fingerprints(), report.source_sha256, 'browser/source inputs changed during run');
  report.status = 'PASS';
} catch (error) {report.error = error.stack || String(error);}
finally {
  if (currentId) {
    const prefix = `sessions/${currentId}`;
    try {
      if (!report.evidence) await writeFile(resolve(output, 'failure-evidence.zip'), await api(prefix + '/evidence', {}, 20000));
    } catch (error) {report.status = 'FAIL'; report.evidence_error = String(error);}
    try {
      await page?.evaluate(id => {
        const visual = window.__scrollWebProbe?.state.visuals.get(id);
        visual?.destroy();
      }, currentId);
      try {await page?.mouse.up();} catch { /* native browser pointer can already be cancelled */ }
    } catch (error) {report.status = 'FAIL'; report.browser_teardown_error = String(error);}
    try {
      let stopped = await api(prefix + '?purge=0', {method: 'DELETE'}, 20000);
      if (!['stopped', 'failed'].includes(stopped.state)) stopped = await eventually(() => api(prefix), value => ['stopped', 'failed'].includes(value.state));
      assert.equal(stopped.state, 'stopped'); assert.equal(stopped.flash_retained, false); assert.equal(stopped.last_frame_available, true);
      report.cleanup = {state: stopped.state, flash_retained: stopped.flash_retained, history_retained: true, last_frame_available: stopped.last_frame_available};
      await writeFile(resolve(output, 'stopped.json'), JSON.stringify(stopped, null, 2));
      const retained = await api(prefix + '/frame.png'); await writeFile(resolve(output, 'retained-frame.png'), retained);
      report.cleanup.retained_frame_sha256 = sha(retained);
      if (report.frames?.length) assert.equal(sha(retained), report.frames.at(-1).sha256);
      try {process.kill(report.pid, 0); report.cleanup.pid_gone = false;}
      catch (error) {if (error.code !== 'ESRCH') throw error; report.cleanup.pid_gone = true;}
      assert.equal(report.cleanup.pid_gone, true, 'the owned guest PID is still present after stop');
      report.checks.evidence_before_stop_history_and_frame_retained_flash_released = true;
    } catch (error) {report.status = 'FAIL'; report.cleanup_error = String(error);}
  }
  try {await browser?.close();} catch (error) {report.status = 'FAIL'; report.browser_close_error = String(error);}
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
}
console.log(`SCROLL_LIVE_BROWSER_${report.status} ${output}/report.json`);
if (report.status !== 'PASS') {console.error(report.error || report.cleanup_error || report.evidence_error); process.exitCode = 1;}
