// Offline by default. Explicit E2E mode owns two visible Device Service guests.
// Uniform colors need no LED permutation; asymmetric colors remain unknown.
import assert from 'node:assert/strict';
import {createHash, randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {isDeepStrictEqual} from 'node:util';
import {chromium} from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const python = process.env.M5_PYTHON || '/opt/miniconda3/bin/python3.12';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const hex = color => '#' + color.toString(16).padStart(6, '0');
const targets = {encoder: ['led0', 'led1'], '8encoder': Array.from({length: 9}, (_, i) => `rgb-${i + 1}`), rgb: ['led0', 'led1', 'led2']};
const groups = [{id: 'i2c-hub', units: ['hub', 'encoder', '8encoder'], leaves: ['encoder', '8encoder']},
  {id: 'rmt-rgb', units: ['rgb'], leaves: ['rgb']}];
const phases = ['A', 'B', 'C', 'D'];
const frameColors = {A: 0x14385c, B: 0x563412, C: 0x124e36, D: 0x362458};
const colors = {
  A: {encoder: Array(2).fill(0x204060), '8encoder': Array(9).fill(0x40a020), rgb: Array(3).fill(0xa02040)},
  B: {encoder: [0x331122, 0x114466], '8encoder': Array.from({length: 9}, (_, i) => 0x102030 + i * 0x010203), rgb: [0x102030, 0x405060, 0x708090]},
  C: {encoder: Array(2).fill(0x1040e0), '8encoder': Array(9).fill(0xe08010), rgb: Array(3).fill(0x10d0a0)},
  D: {encoder: Array(2).fill(0), '8encoder': Array(9).fill(0), rgb: Array(3).fill(0)},
};

const groupAccepted = group => group.status === 'PASS' && group.evidence?.status === 'PASS'
  && group.cleanup?.state === 'stopped' && group.cleanup?.pid_gone === true && group.cleanup?.flash_retained === false
  && !['evidence_error', 'browser_teardown_error', 'cleanup_error'].some(key => group[key] !== undefined);
async function browserTeardown(group, operation) {
  try {await operation();}
  catch (error) {group.browser_teardown_error = String(error); group.status = 'FAIL';}
}

function guestSource(group, phase, pins, nonce, marker) {
  const init = group.id === 'i2c-hub' ? `from machine import I2C, Pin
from unit import EncoderUnit, Encoder8Unit
bus=I2C(0,scl=Pin(${pins.white}),sda=Pin(${pins.yellow}),freq=100000)
scan=sorted(bus.scan())
assert scan==[0x40,0x41], 'passive HUB must expose exactly the two independent I2C addresses'
encoder=EncoderUnit(bus)
eight=Encoder8Unit(bus)
for _channel,_color in enumerate(${JSON.stringify(colors[phase].encoder)},1):
 encoder.set_color(_channel,_color)
for _channel,_color in enumerate(${JSON.stringify(colors[phase]['8encoder'].slice(0, 8))},1):
 eight.set_led_rgb(_channel,_color)
# Original helper writes the ninth RGB triplet; no electrical-to-location claim.
eight.write_reg_data(0x88,${JSON.stringify([colors[phase]['8encoder'][8] >> 16 & 255, colors[phase]['8encoder'][8] >> 8 & 255, colors[phase]['8encoder'][8] & 255])})
` : `from unit import RGBUnit
unit=RGBUnit((${pins.white},${pins.yellow}),3)
unit.set_brightness(100)
unit.set_screen(${JSON.stringify(colors[phase].rgb)})
scan=None
`;
  const sample = group.id === 'i2c-hub' ? `{'encoder':{'counter':encoder.get_rotary_value(),'pressed':bool(encoder.get_button_status())},'8encoder':{'counters':[eight.get_counter_value(i) for i in range(1,9)],'pressed':[bool(eight.get_button_status(i)) for i in range(1,9)],'switch-on':bool(eight.get_switch_status())}}` : '{}';
  return `import sys,time,json,M5
${phase === 'A' ? `sys.path.append(${JSON.stringify(nonce)})` : `assert ${JSON.stringify(nonce)} in sys.path, 'MicroPython VM reset'`}
M5.begin()
screen=M5.Display
screen.setBrightness(255)
screen.fillScreen(${frameColors[phase]})
screen.setTextSize(2)
screen.setTextColor(0xffffff,${frameColors[phase]})
screen.setCursor(12,12)
screen.print('LED ${group.id} ${phase}')
${init}sequence=0
while True:
 assert ${JSON.stringify(nonce)} in sys.path, 'MicroPython VM reset'
 M5.update()
 print(${JSON.stringify(marker + ' ')}+json.dumps({'kind':'sample','phase':${JSON.stringify(phase)},'nonce':${JSON.stringify(nonce)},'sequence':sequence,'scan':scan,'written_colors':${JSON.stringify(Object.fromEntries(group.leaves.map(id => [id, colors[phase][id]])))},'values':${sample}}))
 sequence+=1
 time.sleep_ms(250)
`;
}

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
 assert {'serial.log','frames/current.png','qom/snapshot.json','units/contract.json','units/runtime.json','units/state.json'}<=set(names)
 assert json.loads(z.read('units/runtime.json'))['attachments']==r['attachments']==s['units']
 state=json.loads(z.read('units/state.json'));assert state==m['units'] and state['session_id']==r['session_id'] and state['source']=='live'
 contract=json.loads(z.read('units/contract.json'));assert contract['source_hashes']==state['contract_hashes']==r['contract_hashes']
 for unit_id in r['group']['units']:assert contract['units'][unit_id]['id']==unit_id
 final_colors=r['phases'][-1]['observation']['sample']['written_colors']
 assert {unit['id']:unit['unit_id'] for unit in state['units']}=={unit['id']:unit['unit_id'] for unit in r['attachments']}
 for unit_id in r['group']['leaves']:
  attachment=next(unit for unit in r['attachments'] if unit['unit_id']==unit_id)
  leaves=[unit for unit in state['units'] if unit['id']==attachment['id']];assert len(leaves)==1
  leaf=leaves[0];assert leaf['unit_id']==unit_id and leaf['available'] is True and leaf['errors']=={} and leaf['source']=='guest-qom'
  expected=final_colors[unit_id];assert type(expected) is list and expected and all(type(color) is int and color==0 for color in expected)
  assert leaf['properties']['led-rgb']==expected
  direct=r['phases'][-1]['capture']['qom']['raw'][unit_id]
  assert direct['session_id']==r['session_id'] and direct['path']=='/machine/units/'+attachment['id'] and direct['property']=='led-rgb' and direct['value']==expected
 generic_qom=json.loads(z.read('qom/snapshot.json'))
 def truncated(value):
  if type(value) is dict:return value.get('__truncated__') is True or any(truncated(child) for child in value.values())
  if type(value) is list:return any(truncated(child) for child in value)
  return False
 raw=z.read('serial.log');text=raw.decode('utf8',errors='replace')
 assert text.count('ESP-ROM:')==r['rom_banners'] and text.count('M5EMU_UART_REPL_READY')==1
 expected_ids={phase['program']['execution_id'] for phase in r['phases']}
 stored_ids={pathlib.PurePosixPath(n).stem for n in names if n.startswith('programs/') and n.count('/')==1 and n.endswith('.json')}
 assert stored_ids==expected_ids and len(expected_ids)==4, 'negative MPY request created a fifth execution'
 for index,phase in enumerate(r['phases']):
  p=phase['program'];saved=json.loads(z.read('programs/'+p['execution_id']+'.json'))
  for k in ['execution_id','revision_id','source_sha256','pid','firmware_sha256']:assert saved[k]==p[k]
  assert saved['pid']==r['pid'] and saved['firmware_sha256']==r['firmware_sha256']
  assert saved['state']==('running' if index==3 else 'interrupted')
  if index<3:assert saved['interruption_confirmed'] is True
  original=json.loads(z.read('programs/'+p['revision_id']+'/source.json'));files={'main.py':phase['source']}
  assert original=={'entrypoint':'main.py','files':files}
  assert sha(canonical({'source_kind':'uiflow2-python',**original}))==p['revision_id'] and sha(canonical(files))==p['source_sha256']
  metadata=json.loads(z.read('programs/'+p['revision_id']+'/revision.json'))
  assert metadata['files']==[{'path':'main.py','size':len(phase['source'].encode()),'sha256':sha(phase['source'].encode())}]
  assert text.count('__M5_EXEC_'+p['execution_id']+'__:START')==1
 for observation in r['serial_observations']:
  a=observation['offset'];w=observation['window'];b=w['next_offset'];assert type(a) is int and type(b) is int and a==w['offset'] and 0<=a<=b<=len(raw)
  assert sha(raw[:a].decode('utf8',errors='replace').encode())==observation['prefix_sha256']
  assert raw[a:b].decode('utf8',errors='replace')==w['data'] and w['session_id']==r['session_id']
  matches=[]
  for line in w['data'].splitlines(keepends=True):
   if not line.endswith('\n') or not line.startswith(r['marker']+' '):continue
   try:v=json.loads(line[len(r['marker'])+1:])
   except ValueError:continue
   if type(v) is dict and v==observation['sample']:matches.append(v)
  assert matches
 for phase in r['phases']:
  frame=phase['capture']['frame'];p=pathlib.Path(sys.argv[1]).parent/frame['path'];b=p.read_bytes();assert sha(b)==frame['sha256']
  with Image.open(p) as im:im.load();assert im.format=='PNG' and list(im.size)==frame['metrics']['size']
  assert frame['headers']['x-frame-execution-id']==phase['program']['execution_id']
  assert frame['headers']['x-frame-revision-id']==phase['program']['revision_id']
 assert sha(z.read('frames/current.png'))==r['phases'][-1]['capture']['frame']['sha256']
 assert s['program']['execution_id']==r['phases'][-1]['program']['execution_id'] and s['program']['state']=='running'
 assert r['mpy_negative']['status']==409 and r['mpy_negative']['body']['error']['code']=='unsupported_program_entrypoint'
 assert r['mpy_negative']['before_execution_id']==r['mpy_negative']['after_execution_id']==r['phases'][0]['program']['execution_id']
 print(json.dumps({'status':'PASS','members':len(names),'executions':len(expected_ids),'serial_windows':len(r['serial_observations']),'identity_source_byte_windows_and_member_sha':True,'final_leaf_unit_state_phase_D_verified':True,'generic_qom_snapshot_truncated':truncated(generic_qom),'generic_qom_used_as_complete_unit_raw_evidence':False,'independent_unit_raw_qom_location':'report phases[].capture.qom.raw','zip_sha256':sha(pathlib.Path(sys.argv[1]).read_bytes())}))
`;

const plan = {mode: 'offline-plan', guest_execution: 'NOT RUN', browser_execution: 'NOT RUN', sessions: groups,
  phases: phases.map(phase => ({phase, electrical_colors: colors[phase], visual: phase === 'B' ? 'unknown-unmapped' : 'known-uniform'})),
  led_components: '2 Encoder + 9 8Encoder + 3 RGB; no index permutation or angle claim',
  transport_negative: 'Browser-only HTTP 503, independent real HTTP/QOM stays live; then recover without program replacement',
  prerequisites: ['M5_UNIT_SERVICE_E2E=1', 'M5_EXPECTED_RUNTIME_SHA256=<frozen sha256>', 'M5_EXPECTED_SERVICE_PID=<reloaded service pid>',
    'M5_EXPECTED_WORKER_GENERATION=<reloaded generation>', 'M5_UNIFORM_LED_LIVE_BROWSER_OUT=<new directory>'],
  assertions: ['actual /devices program_features and main.mpy 409 without new execution', 'fresh UART + independent QOM + all mounted LED materials',
    'known=false distinguishes unknown from electrical off', 'raw electrical array readback survives unknown', 'zero unit-input echo',
    'same VM/PID/firmware + source/revision/frame identity', 'evidence ZIP before purge=0 stop; Flash released']};
assert.ok(process.argv.slice(2).every(arg => ['--plan', '--check-sources', '--check-cleanup'].includes(arg)), 'Unknown argument');
if (process.argv.includes('--check-cleanup')) {
  const sample = {status: 'PASS', evidence: {status: 'PASS'}, cleanup: {state: 'stopped', pid_gone: true, flash_retained: false}};
  assert.equal(groupAccepted(sample), true);
  const failed = structuredClone(sample);
  await browserTeardown(failed, async () => {throw new Error('offline forced teardown failure');});
  assert.equal(failed.status, 'FAIL'); assert.equal(groupAccepted(failed), false);
  failed.status = 'PASS'; assert.equal(groupAccepted(failed), false, 'A later PASS assignment must not hide teardown failure');
  for (const key of ['evidence_error', 'cleanup_error']) assert.equal(groupAccepted({...sample, [key]: 'offline injected failure'}), false);
  console.log(JSON.stringify({status: 'PASS', checks: ['successful-cleanup-accepted', 'teardown-throw-fails', 'later-pass-cannot-hide-teardown-error', 'evidence-and-cleanup-errors-fail'], guest_execution: 'NOT RUN', browser_execution: 'NOT RUN'}));
  process.exit(0);
}
if (process.argv.includes('--check-sources')) {
  const examples = groups.flatMap(group => phases.map(phase => guestSource(group, phase, {white: 1, yellow: 2}, '/offline-nonce', 'OFFLINE_LED')));
  const checked = execFileSync(python, ['-c', 'import ast,json,sys;s=json.load(sys.stdin);[ast.parse(x) for x in s];print(json.dumps({"status":"PASS","python_sources":len(s),"guest_execution":"NOT RUN"}))'],
    {input: JSON.stringify([...examples, zipValidator]), encoding: 'utf8'});
  console.log(checked.trim()); process.exit(0);
}
if (process.argv.includes('--plan') || process.env.M5_UNIT_SERVICE_E2E !== '1') {console.log(JSON.stringify(plan, null, 2)); process.exit(0);}

const expectedRuntime = process.env.M5_EXPECTED_RUNTIME_SHA256;
assert.match(expectedRuntime || '', /^[0-9a-f]{64}$/);
const expectedServicePid = Number(process.env.M5_EXPECTED_SERVICE_PID), expectedGeneration = Number(process.env.M5_EXPECTED_WORKER_GENERATION);
assert.ok(Number.isSafeInteger(expectedServicePid) && expectedServicePid > 0);
assert.ok(Number.isSafeInteger(expectedGeneration) && expectedGeneration > 0);
assert.ok(process.env.M5_UNIFORM_LED_LIVE_BROWSER_OUT, 'A new explicit output directory is required');
const output = resolve(process.env.M5_UNIFORM_LED_LIVE_BROWSER_OUT);
await mkdir(output, {recursive: false});
const base = process.env.M5_DEVICE_SERVICE_URL || 'http://127.0.0.1:8787';
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname));
const sourceNames = ['platform/tests/test_live_uniform_led_service_browser.mjs', 'platform/web/sessions.js', 'platform/web/sessions.html',
  'platform/web/program-panel.js', 'platform/web/device-shell-factory.js', 'platform/web/unit-panel.js', 'platform/web/model-shell.js', 'platform/web/unit-visual-mappings.js',
  'platform/units/catalog.json', 'platform/units/runtime-profiles.json', 'platform/web/vendor/m5stack-models/vendor-manifest.json',
  'platform/web/vendor/m5stack-models/src/core/components/Led.js', 'platform/web/vendor/m5stack-models/src/units/encoder/assembly.js',
  'platform/web/vendor/m5stack-models/src/units/8encoder/index.js', 'platform/web/vendor/m5stack-models/src/units/rgb/index.js',
  'tests/units/run_live_unit_batch.py', 'tests/units/controls_probe/control_drivers/source-manifest.json', 'tests/units/io_probe/io_drivers/source-manifest.json',
  'platform/tools/device_service.py', 'platform/tools/program_packages.py', 'platform/tools/uiflow_runtime.py'];
const fingerprints = async () => Object.fromEntries(await Promise.all(sourceNames.map(async path => [path, sha(await readFile(resolve(root, path)))])));
const report = {schema_version: 1, category: 'actual-uniform-led-controller-to-default-browser-feedback', status: 'FAIL', captured_at: new Date().toISOString(),
  hardware_validation: 'NOT RUN', source_sha256: await fingerprints(), groups: [], unit_posts: [], physical_events: [], shared_frames: [],
  page_errors: [], resource_errors: [], transport_faults: [],
  instrumentation: 'Append only window.__uniformLedProbe={state,SessionVisual}; inspect existing objects. Browser /units 503 is an explicit transport negative, never substitute property values.',
  limits: ['No electrical LED index-to-physical-location binding', 'No angle, rotation or mechanical calibration', 'Stable program stages only; no slot/burst timing claim',
    'General qom/snapshot.json can be node-limited/truncated; complete per-leaf raw QOM replies are in each group report phases[].capture.qom.raw. ZIP final units/state.json is checked separately.']};
const eventually = async (read, predicate, timeout = 60000) => {
  const end = Date.now() + timeout; let last;
  while (Date.now() < end) {last = await read(); if (predicate(last)) return last; await delay(125);}
  throw new Error('Uniform LED observation timeout: ' + JSON.stringify(last).slice(-2500));
};
const rawApi = async (path, options = {}, timeout = 30000) => {
  const response = await fetch(`${base}/api/v1/${path}`, {...options, signal: AbortSignal.timeout(timeout)});
  const bytes = Buffer.from(await response.arrayBuffer());
  return {status: response.status, url: response.url, headers: Object.fromEntries(response.headers.entries()), bytes};
};
const api = async (path, options = {}, timeout) => {
  const response = await rawApi(path, options, timeout);
  assert.ok(response.status >= 200 && response.status < 300, `${path}: HTTP ${response.status} ${response.bytes}`);
  return path.includes('frame.png') || path.endsWith('/evidence') ? response.bytes : JSON.parse(response.bytes);
};
const runtimeIdentity = pid => JSON.parse(execFileSync(python, ['-c',
  'import ctypes,hashlib,json,pathlib,sys;p=int(sys.argv[1]);b=ctypes.create_string_buffer(4096);\nif sys.platform=="darwin":\n assert ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath(p,b,len(b))>0\n f=pathlib.Path(b.value.decode())\nelse:f=pathlib.Path("/proc/%d/exe"%p).resolve(strict=True)\nprint(json.dumps({"pid":p,"executable_name":f.name,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()}))', String(pid)], {encoding: 'utf8'}));
const matchingSample = (data, group, phase, nonce, marker, minimumSequence = -1) => {
  for (const line of data.split(/(?<=\n)/)) {
    if (!line.startsWith(marker + ' ') || !line.endsWith('\n')) continue;
    let value; try {value = JSON.parse(line.slice(marker.length + 1));} catch {continue;}
    if (value?.kind === 'sample' && value.phase === phase && value.nonce === nonce && Number.isInteger(value.sequence) && value.sequence > minimumSequence
      && isDeepStrictEqual(value.written_colors, Object.fromEntries(group.leaves.map(id => [id, colors[phase][id]])))) return value;
  }
  return null;
};
const emission = color => [color >> 16 & 255, color >> 8 & 255, color & 255].map(channel => {
  const s = channel / 255; return (s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4) * 2.2;
});
const near = (actual, wanted) => {assert.equal(actual.length, wanted.length); actual.forEach((value, i) => assert.ok(Math.abs(value - wanted[i]) < 1e-6, `${actual} differs from ${wanted}`));};
function assertVisual(snapshot, group, phase, unknownReason = null) {
  assert.deepEqual(snapshot.bindings, {}, 'The actual UnitPanel must use default bindings');
  assert.equal(snapshot.physicalEvents, 0);
  for (const unitId of group.leaves) {
    const unit = snapshot.units[unitId], electrical = colors[phase][unitId];
    assert.ok(unit); assert.equal(unit.leds.length, targets[unitId].length);
    assert.deepEqual(unit.readback, electrical.map((color, index) => `LED[${index}] ${hex(color)}`));
    const reason = unknownReason || (phase === 'B' ? 'unmapped' : null);
    assert.equal(unit.available, reason === 'unavailable' ? false : true);
    assert.equal(unit.hint.mode, reason || 'uniform'); assert.equal(unit.hint.hidden, !reason);
    assert.equal(unit.hint.text, reason === 'unmapped' ? '灯位未确认，颜色分布请看读回' : reason === 'unavailable' ? '灯光状态未知，模型颜色已撤下' : '');
    if (reason === 'unavailable') assert.match(unit.note, /状态请求失败/);
    for (const led of unit.leds) {
      assert.equal(led.attached, true); assert.equal(led.known, !reason); assert.equal(led.userDataKnown, !reason);
      const color = reason ? 0 : electrical[0], brightness = color === 0 ? 0 : 1;
      assert.deepEqual(led.state, {color: hex(color), brightness}); assert.equal(led.glowColor, hex(color));
      assert.equal(led.glow, brightness > 0); assert.equal(led.opacity, brightness * .85); near(led.emissive, emission(color));
    }
    assert.ok(unit.joints.every(joint => joint.angleDeg === 0 && joint.targetAngleDeg === 0 && joint.rpm === 0));
    if (unitId === 'encoder') {
      assert.equal(unit.diffusion?.length, 2, 'Actual Encoder front-shell diffusion must exist');
      unit.diffusion.forEach(uniform => {
        const color = reason ? 0 : electrical[0]; assert.equal(uniform.brightness, color === 0 ? 0 : 1); near(uniform.color.map(c => c * 2.2), emission(color));
      });
    }
  }
}

let browser, page, current, transportFaultSession = null;
try {
  report.service_start = await api('health');
  assert.equal(report.service_start.capacity.worker.pid, expectedServicePid); assert.equal(report.service_start.capacity.worker.generation, expectedGeneration);
  const catalog = await api('devices'), device = await api('devices/cores3');
  report.device_features = device.program_features;
  assert.deepEqual(device.program_features, {runtimes: ['qemu'], entrypoints: ['main.py'], mpy_dependencies: 'bytecode-only', mpy_entrypoint: false,
    native_mpy: false, main_namespace: 'fresh-exec-globals', cleanup_mode: 'interrupt-only'});
  const listed = (Array.isArray(catalog) ? catalog : catalog.devices).find(row => row.device_id === 'cores3' || row.id === 'cores3');
  assert.deepEqual(listed.program_features, device.program_features);
  const validMpyPath = resolve(root, '.work/uiflow-package-live-20261026/mpy-cross-78ff170d/helper.mpy'), validMpy = await readFile(validMpyPath);
  assert.equal(sha(validMpy), '583a0028999b53b0ba576f0a2c79c6a7cb2b7243b91725215e3de284a18a41fd');
  assert.deepEqual([...validMpy.subarray(0, 4)], [77, 6, 0, 31]);
  execFileSync(python, ['-c', 'import pathlib,sys;sys.path.insert(0,sys.argv[1]);from mpy_bytecode import validate_bytecode;validate_bytecode(pathlib.Path(sys.argv[2]).read_bytes())', resolve(root, 'platform/tools'), validMpyPath]);
  report.negative_mpy = {path: validMpyPath, sha256: sha(validMpy), header: [...validMpy.subarray(0, 4)], compiled_or_built_during_probe: false};
  report.tooling = {node_version: process.version, node_sha256: sha(await readFile(process.execPath)), python_version: execFileSync(python, ['--version'], {encoding: 'utf8'}).trim(), zip_validator_sha256: sha(zipValidator)};
  browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
  report.browser_version = browser.version(); page = await browser.newPage({viewport: {width: 1440, height: 1080}, deviceScaleFactor: 2});
  page.on('pageerror', error => report.page_errors.push(error.message));
  page.on('response', response => {
    const path = new URL(response.url()).pathname;
    if (response.status() >= 400 && path.includes('/vendor/')) report.resource_errors.push({path, status: response.status()});
    if (path.endsWith('/unit-input') && response.request().method() === 'POST') report.unit_posts.push({path, request: response.request().postDataJSON(), status: response.status()});
    if (current && path === `/api/v1/sessions/${current.session_id}/frame.png`) report.shared_frames.push({session_id: current.session_id, status: response.status(), headers: response.headers()});
  });
  await page.route('**/platform/web/sessions.js*', async route => {
    const response = await route.fetch(), content = await response.text();
    assert.equal(sha(content), report.source_sha256['platform/web/sessions.js']);
    await route.fulfill({response, body: content + '\nwindow.__uniformLedProbe={state,SessionVisual};\n'});
  });
  await page.route('**/api/v1/sessions/*/units*', async route => {
    const path = new URL(route.request().url()).pathname;
    if (transportFaultSession && path === `/api/v1/sessions/${transportFaultSession}/units` && route.request().method() === 'GET') {
      report.transport_faults.push({session_id: transportFaultSession, status: 503, observed_at: new Date().toISOString(), scope: 'browser-transport-negative'});
      await route.fulfill({status: 503, contentType: 'application/json', body: JSON.stringify({error: {code: 'probe_browser_transport_unavailable', message: 'Explicit browser-only transport negative'}})});
    } else await route.continue();
  });

  async function inspect() {
    return page.evaluate(({id, leaves, targets}) => {
      const visual = window.__uniformLedProbe.state.visuals.get(id), panel = visual.unitPanel;
      return {bindings: structuredClone(panel.bindingsByUnit), physicalEvents: window.__uniformPhysicalEvents?.[id]?.length || 0,
        frameMetadata: visual.frameMetadata, units: Object.fromEntries(leaves.map(unitId => {
          const attachment = panel.session.units.find(unit => unit.unit_id === unitId), mounted = panel.mounted.get(attachment.id), card = panel.cards.get(attachment.id);
          const note = card.querySelector('[data-unit-led-mapping]'), module = visual.shell.model.port(mounted.port).module;
          return [unitId, {id: attachment.id, port: mounted.port, available: panel.states.get(attachment.id)?.available,
            hint: {hidden: note.hidden, text: note.textContent, mode: note.dataset.unitLedMapping}, note: card.querySelector('[data-unit-note]').textContent,
            readback: [...card.querySelectorAll('[data-unit-values] [data-unit-rgb]')].map(node => node.textContent.trim()),
            leds: targets[unitId].map(component => {
              const led = visual.shell.model.find(`${mounted.port}/${component}`, 'led');
              return {id: led.id, path: led.path, attached: module.components.get(led.id) === led, known: led.runtimeKnown,
                userDataKnown: led.object3d.userData.runtimeKnown, state: led.getState(), emissive: led.lensMaterial.emissive.toArray(),
                glow: led.glow.visible, opacity: led.glow.material.opacity, glowColor: '#' + led.glow.material.color.getHexString()};
            }),
            diffusion: module.encoderShellDiffusion ? [0, 1].map(i => ({brightness: module.encoderShellDiffusion.uniforms['encoderBrightness' + i].value, color: module.encoderShellDiffusion.uniforms['encoderColor' + i].value.toArray()})) : null,
            joints: module.list('joint').map(joint => joint.getState())}];
        }))};
    }, {id: current.session_id, leaves: current.group.leaves, targets});
  }
  async function identity() {
    const value = await api(`sessions/${current.session_id}`);
    for (const key of ['pid', 'firmware_sha256', 'worker']) assert.deepEqual(value[key], current[key]);
    assert.equal(value.state, 'running'); const observed = runtimeIdentity(current.pid); assert.equal(observed.sha256, expectedRuntime); return observed;
  }
  async function serialSample(before, phase, minimumSequence = -1) {
    const window = await eventually(async () => {
      const programPayload = await api(`sessions/${current.session_id}/program`); assert.equal(programPayload.session_id, current.session_id);
      const program = programPayload.program;
      assert.equal(program.execution_id, current.execution_id); assert.equal(program.pid, current.pid); assert.equal(program.firmware_sha256, current.firmware_sha256);
      assert.equal(program.state, 'running');
      return api(`sessions/${current.session_id}/serial?offset=${before.next_offset}&limit=1048576`);
    }, value => Boolean(matchingSample(value.data, current.group, phase, current.nonce, current.marker, minimumSequence)));
    const observation = {offset: before.next_offset, prefix_sha256: sha(Buffer.from(before.data)), window,
      sample: matchingSample(window.data, current.group, phase, current.nonce, current.marker, minimumSequence)};
    assert.deepEqual(observation.sample.scan, current.group.id === 'i2c-hub' ? [0x40, 0x41] : null);
    current.serial_observations.push(observation); return observation;
  }
  async function independentQom(phase) {
    const payload = await eventually(() => api(`sessions/${current.session_id}/units`), value => current.group.leaves.every(unitId => {
      const unit = value.units.find(row => row.unit_id === unitId);
      return unit?.available === true && JSON.stringify(unit.properties['led-rgb']) === JSON.stringify(colors[phase][unitId]);
    }));
    assert.equal(payload.session_id, current.session_id); assert.equal(payload.source, 'live'); assert.deepEqual(payload.contract_hashes, current.contract_hashes);
    const raw = {};
    for (const unitId of current.group.leaves) {
      const unit = payload.units.find(row => row.unit_id === unitId); assert.equal(unit.source, 'guest-qom'); assert.deepEqual(unit.errors, {});
      const path = `/machine/units/${unit.id}`, value = await api(`sessions/${current.session_id}/qom?path=${encodeURIComponent(path)}&property=led-rgb`);
      assert.equal(value.session_id, current.session_id); assert.equal(value.path, path); assert.equal(value.property, 'led-rgb'); assert.deepEqual(value.value, colors[phase][unitId]);
      raw[unitId] = value;
      if (unitId !== 'rgb') {
        const address = await api(`sessions/${current.session_id}/qom?path=${encodeURIComponent(path)}&property=i2c-address`);
        assert.equal(address.value, unitId === 'encoder' ? 0x40 : 0x41); raw[unitId].address = address;
        const transactions = await api(`sessions/${current.session_id}/qom?path=${encodeURIComponent(path)}&property=transactions`);
        assert.ok(Number.isInteger(transactions.value) && transactions.value > 0); raw[unitId].transactions = transactions;
      } else {
        const frames = await api(`sessions/${current.session_id}/qom?path=${encodeURIComponent(path)}&property=led-frames`);
        const incomplete = await api(`sessions/${current.session_id}/qom?path=${encodeURIComponent(path)}&property=incomplete-frames`);
        assert.ok(Number.isInteger(frames.value) && frames.value > 0); assert.equal(incomplete.value, 0);
        Object.assign(raw[unitId], {led_frames: frames, incomplete_frames: incomplete});
      }
    }
    return {payload, raw};
  }
  async function visibleScreenshots(label) {
    const card = page.locator(`[data-session-id="${current.session_id}"]`), stage = card.locator('.three-device-stage').first();
    const panels = [];
    for (const unitId of current.group.leaves) {
      const attachment = current.attachments.find(unit => unit.unit_id === unitId), path = `${label}-${unitId}-panel.png`;
      const bytes = await card.locator(`[data-unit-id="${attachment.id}"]`).screenshot({path: resolve(current.output, path)});
      panels.push({unit_id: unitId, path, sha256: sha(bytes)});
    }
    const views = [];
    for (const view of ['front', 'iso']) {
      await stage.scrollIntoViewIfNeeded();
      await stage.evaluate(element => element.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'}));
      const rendered = await page.evaluate(async ({id, view}) => {
        const {Box3, Vector3} = await import('/platform/web/vendor/three/three.module.js');
        const visual = window.__uniformLedProbe.state.visuals.get(id), viewer = visual.shell.viewer;
        viewer.setView(view, {duration: 0}); viewer.resize(); viewer.fit({padding: 1.6, duration: 0});
        await new Promise((resolve, reject) => {
          let off; const timer = setTimeout(() => {off?.(); reject(new Error('Visible viewer did not render'));}, 5000);
          off = viewer.once('render', () => {clearTimeout(timer); resolve();}); viewer.requestRender();
        });
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        viewer.scene.updateMatrixWorld(true); viewer.camera.updateMatrixWorld(true);
        const rect = viewer.renderer.domElement.getBoundingClientRect();
        const entries = [{name: 'whole-host-and-attached-assembly', root: visual.shell.model.root},
          ...visual.unitPanel.session.units.map(unit => ({name: unit.id, root: visual.shell.model.port(visual.unitPanel.mounted.get(unit.id).port).module.root}))];
        const bounds = entries.map(entry => {
          const box = new Box3().setFromObject(entry.root), points = []; let visible = true;
          for (let node = entry.root; node; node = node.parent) if (!node.visible) visible = false;
          for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
            const p = new Vector3(x, y, z).project(viewer.camera); points.push({x: (p.x + 1) * rect.width / 2, y: (1 - p.y) * rect.height / 2, z: p.z});
          }
          return {name: entry.name, visible, points};
        });
        return {view, width: rect.width, height: rect.height, viewport: {x: rect.x, y: rect.y, width: innerWidth, height: innerHeight},
          bounds, actual_render_png: viewer.screenshot()};
      }, {id: current.session_id, view});
      assert.ok(rendered.viewport.x >= 0 && rendered.viewport.y >= 0 && rendered.viewport.x + rendered.width <= rendered.viewport.width
        && rendered.viewport.y + rendered.height <= rendered.viewport.height, 'Whole 3D canvas must be in the viewport');
      assert.equal(rendered.bounds.length, current.group.units.length + 1);
      assert.ok(rendered.bounds.every(bound => bound.visible && bound.points.every(p => p.x >= 2 && p.x <= rendered.width - 2 && p.y >= 2 && p.y <= rendered.height - 2 && p.z > -1 && p.z < 1)), 'Whole host and every attached model must fit inside canvas');
      const renderPath = `${label}-${view}-render.png`, rendererBytes = Buffer.from(rendered.actual_render_png.split(',')[1], 'base64');
      delete rendered.actual_render_png; await writeFile(resolve(current.output, renderPath), rendererBytes);
      const renderMetrics = JSON.parse(execFileSync(python, ['-c', 'import json,sys;from PIL import Image\nim=Image.open(sys.argv[1]).convert("RGBA");p=list(im.getdata());visible=[v[:3] for v in p if v[3]>0];print(json.dumps({"size":list(im.size),"visible_pixels":len(visible),"unique_rgb":len(set(visible))}))', resolve(current.output, renderPath)], {encoding: 'utf8'}));
      assert.ok(renderMetrics.visible_pixels > 1000 && renderMetrics.unique_rgb > 50, 'Actual WebGL render is blank');
      const path = view === 'front' ? `${label}-browser.png` : `${label}-iso-browser.png`;
      const bytes = await stage.screenshot({path: resolve(current.output, path)});
      views.push({...rendered, path, sha256: sha(bytes), renderer: {path: renderPath, sha256: sha(rendererBytes), metrics: renderMetrics}});
    }
    const overviewPath = `${label}-full-page.png`, overview = await page.screenshot({path: resolve(current.output, overviewPath), fullPage: true});
    return {path: views[0].path, sha256: views[0].sha256, views, panels, overview: {path: overviewPath, sha256: sha(overview)}};
  }
  async function capture(phase) {
    const qom = await independentQom(phase);
    const visual = await eventually(inspect, value => {try {assertVisual(value, current.group, phase); return true;} catch {return false;}});
    assertVisual(visual, current.group, phase);
    let frameResponse;
    const metrics = await eventually(async () => {
      frameResponse = await rawApi(`sessions/${current.session_id}/frame.png?max_age_ms=125`); assert.equal(frameResponse.status, 200);
      assert.equal(new URL(frameResponse.url).pathname, `/api/v1/sessions/${current.session_id}/frame.png`);
      assert.equal(frameResponse.headers['x-frame-source'], 'live');
      assert.match(frameResponse.headers['x-frame-execution-id'] || '', /^[0-9a-f]{32}$/);
      assert.match(frameResponse.headers['x-frame-revision-id'] || '', /^[0-9a-f]{64}$/);
      if (frameResponse.headers['x-frame-execution-id'] !== current.execution_id) {
        const previous = current.phases.slice(0, -1).find(phase => phase.program.execution_id === frameResponse.headers['x-frame-execution-id']);
        assert.ok(previous, 'Frame belongs to an unknown execution/session');
        assert.equal(frameResponse.headers['x-frame-revision-id'], previous.program.revision_id);
        return {ratio: 0, waiting_for_current_execution: true, headers: frameResponse.headers};
      }
      assert.equal(frameResponse.headers['x-frame-revision-id'], current.phases.at(-1).program.revision_id);
      return page.evaluate(async ({encoded, color}) => {
        const image = await createImageBitmap(new Blob([Uint8Array.from(atob(encoded), value => value.charCodeAt(0))], {type: 'image/png'}));
        const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
        const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0); const rgba = ctx.getImageData(0, 0, image.width, image.height).data;
        const wanted = [color >> 16 & 255, color >> 8 & 255, color & 255]; let matching = 0;
        for (let i = 0; i < rgba.length; i += 4) if (wanted.every((value, c) => Math.abs(value - rgba[i + c]) <= 8)) matching++;
        const pixels = [[2, 2], [image.width - 2, image.height - 2]].map(([x, y]) => ({x, y, rgb: [...ctx.getImageData(x, y, 1, 1).data].slice(0, 3)}));
        image.close(); return {size: [canvas.width, canvas.height], matching_pixels: matching, ratio: matching / (canvas.width * canvas.height), pixels};
      }, {encoded: frameResponse.bytes.toString('base64'), color: frameColors[phase]});
    }, value => value.ratio > .6);
    await page.waitForFunction(({id, execution, revision, metrics}) => {
      const v = window.__uniformLedProbe.state.visuals.get(id), d = v?.shell?.display;
      return d && d.width === metrics.size[0] && d.height === metrics.size[1] && metrics.pixels.every(p => p.rgb.every((c, i) => d.getPixel(p.x, p.y)[i] === c))
        && v.frameMetadata?.['x-frame-execution-id'] === execution && v.frameMetadata?.['x-frame-revision-id'] === revision && v.frameMetadata?.['x-frame-source'] === 'live';
    }, {id: current.session_id, execution: current.execution_id, revision: current.phases.at(-1).program.revision_id, metrics}, {timeout: 60000});
    const path = `${phase}-frame.png`; await writeFile(resolve(current.output, path), frameResponse.bytes);
    return {qom, visual, frame: {path, sha256: sha(frameResponse.bytes), headers: frameResponse.headers, metrics}, screenshot: await visibleScreenshots(phase)};
  }
  async function zeroEcho(label) {
    const posts = report.unit_posts.length, events = (await inspect()).physicalEvents, frames = report.shared_frames.filter(row => row.session_id === current.session_id).length;
    assert.equal(posts, 0); assert.equal(events, 0); await delay(1300);
    assert.equal(report.unit_posts.length, 0); assert.equal((await inspect()).physicalEvents, 0);
    const newFrames = report.shared_frames.filter(row => row.session_id === current.session_id).length - frames; assert.ok(newFrames > 0, 'Zero-echo window must include real frame polling');
    current.zero_echo.push({label, observed_ms: 1300, unit_posts: 0, physical_events: 0, new_shared_frames: newFrames});
  }
  async function cleanup() {
    if (!current?.session_id) return;
    const prefix = `sessions/${current.session_id}`;
    try {if (!current.evidence) await writeFile(resolve(current.output, 'failure-evidence.zip'), await api(prefix + '/evidence', {}, 20000));}
    catch (error) {current.evidence_error = String(error); current.status = 'FAIL'; report.status = 'FAIL';}
    transportFaultSession = null;
    await browserTeardown(current, () => page?.evaluate(id => window.__uniformLedProbe?.state.visuals.get(id)?.destroy(), current.session_id));
    try {
      let stopped = await api(prefix + '?purge=0', {method: 'DELETE'}, 20000);
      if (!['stopped', 'failed'].includes(stopped.state)) stopped = await eventually(() => api(prefix), row => ['stopped', 'failed'].includes(row.state));
      assert.equal(stopped.state, 'stopped'); assert.equal(stopped.flash_retained, false); assert.equal(stopped.last_frame_available, true);
      const retained = await api(prefix + '/frame.png'); await writeFile(resolve(current.output, 'retained-frame.png'), retained);
      if (current.phases.at(-1)?.capture) assert.equal(sha(retained), current.phases.at(-1).capture.frame.sha256);
      let gone = false; try {process.kill(current.pid, 0);} catch (error) {if (error.code !== 'ESRCH') throw error; gone = true;}
      assert.equal(gone, true); current.cleanup = {state: stopped.state, flash_retained: false, history_retained: true, last_frame_available: true, pid_gone: true};
      await writeFile(resolve(current.output, 'stopped.json'), JSON.stringify(stopped, null, 2));
    } catch (error) {current.cleanup_error = String(error); current.status = 'FAIL'; report.status = 'FAIL';}
    await writeFile(resolve(current.output, 'report.json'), JSON.stringify(current, null, 2) + '\n'); current = null;
  }

  for (const group of groups) {
    console.log(`UNIFORM_LED_GROUP_START ${group.id}`);
    current = {group, device_id: 'cores3', runtime: 'qemu', output: resolve(output, group.id), phases: [], serial_observations: [], zero_echo: [],
      source_sha256: report.source_sha256, qom_evidence_boundary: report.limits.at(-1)};
    await mkdir(current.output); report.groups.push(current);
    try {
      await page.goto(`${base}/platform/web/sessions.html`, {waitUntil: 'domcontentloaded'});
      await page.locator('#deviceSelect option[value="cores3"]').waitFor({state: 'attached'}); await page.selectOption('#deviceSelect', 'cores3');
      await page.locator(`#unitModelSelect option[value="${group.units[0]}"]`).waitFor({state: 'attached'}); await page.selectOption('#unitModelSelect', group.units[0]);
      if (group.id === 'i2c-hub') {await page.getByLabel('HUB · Grove 1', {exact: true}).selectOption('encoder'); await page.getByLabel('HUB · Grove 2', {exact: true}).selectOption('8encoder');}
      await page.check('#programModeInput');
      const reply = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/sessions' && response.request().method() === 'POST');
      await page.click('#createBtn'); const createdResponse = await reply; current.creation_request = createdResponse.request().postDataJSON(); current.created = await createdResponse.json();
      if (createdResponse.status() === 202 && typeof current.created.session_id === 'string') current.session_id = current.created.session_id;
      assert.equal(createdResponse.status(), 202, JSON.stringify(current.created)); assert.equal(current.creation_request.program_mode, 'uiflow-live');
      assert.deepEqual(current.creation_request.units.map(unit => unit.unit_id), group.units);
      if (group.id === 'i2c-hub') {
        assert.ok(current.creation_request.units.slice(1).every(unit => unit.parent_id === current.creation_request.units[0].id));
        assert.deepEqual(current.creation_request.units.slice(1).map(unit => unit.port_id), ['grove-1', 'grove-2']);
      } else assert.equal(current.creation_request.units[0].parent_id, undefined);
      const prefix = `sessions/${current.session_id}`;
      const ready = await eventually(() => api(prefix), value => ['running', 'failed', 'stopped'].includes(value.state), 120000); assert.equal(ready.state, 'running', ready.error);
      Object.assign(current, {pid: ready.pid, firmware_sha256: ready.firmware_sha256, worker: ready.worker, attachments: ready.units});
      console.log(`UNIFORM_LED_SESSION_READY ${group.id} ${current.session_id} pid=${current.pid}`);
      current.runtime_identity = runtimeIdentity(ready.pid); assert.equal(current.runtime_identity.sha256, expectedRuntime);
      assert.equal(ready.worker.generation, expectedGeneration);
      const initialUnits = await api(prefix + '/units'); current.contract_hashes = initialUnits.contract_hashes;
      const serial = await api(prefix + '/serial?offset=0&limit=1048576'); current.rom_banners = serial.data.split('ESP-ROM:').length - 1;
      assert.equal(serial.data.split('M5EMU_UART_REPL_READY').length - 1, 1);
      const card = page.locator(`[data-session-id="${current.session_id}"]`), editor = card.locator('[data-program-source]'), run = card.locator('[data-program-run]');
      await page.waitForFunction(({id, count}) => window.__uniformLedProbe?.state.visuals.get(id)?.unitPanel?.mounted.size === count,
        {id: current.session_id, count: group.units.length}, {timeout: 90000});
      await card.locator('canvas').first().scrollIntoViewIfNeeded();
      current.framing = await page.evaluate(async id => {
        const {Box3, Vector3} = await import('/platform/web/vendor/three/three.module.js');
        const visual = window.__uniformLedProbe.state.visuals.get(id), viewer = visual.shell.viewer;
        window.__uniformPhysicalEvents ||= {}; window.__uniformPhysicalEvents[id] = [];
        visual.shell.on('unit-input', event => window.__uniformPhysicalEvents[id].push(structuredClone(event)));
        viewer.setView('front', {duration: 0}); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        viewer.resize(); viewer.fit({padding: 1.8, duration: 0}); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        viewer.scene.updateMatrixWorld(true); viewer.camera.updateMatrixWorld(true);
        const box = new Box3().setFromObject(visual.shell.model.port('grove').module.root), rect = viewer.renderer.domElement.getBoundingClientRect(), points = [];
        for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
          const p = new Vector3(x, y, z).project(viewer.camera); points.push({x: (p.x + 1) * rect.width / 2, y: (1 - p.y) * rect.height / 2, z: p.z});
        }
        return {width: rect.width, height: rect.height, points};
      }, current.session_id);
      assert.ok(current.framing.points.every(p => p.x >= 4 && p.x <= current.framing.width - 4 && p.y >= 4 && p.y <= current.framing.height - 4 && p.z > -1 && p.z < 1));
      current.nonce = '/m5-uniform-led-' + randomUUID().replaceAll('-', ''); current.marker = 'UNIFORM_LED_' + randomUUID().replaceAll('-', '').slice(0, 12);
      const pins = ready.units.find(unit => !unit.parent_id).pins;
      for (const phase of phases) {
        console.log(`UNIFORM_LED_PHASE_START ${group.id} ${phase}`);
        const before = await api(prefix + '/serial?offset=0&limit=1048576'), previousExecution = current.execution_id || null;
        const source = guestSource(group, phase, pins, current.nonce, current.marker);
        await writeFile(resolve(current.output, `${phase}.py`), source);
        await eventually(() => run.isEnabled(), Boolean);
        const programReply = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/sessions/${current.session_id}/program` && response.request().method() === 'POST');
        await editor.fill(source); await run.click(); const submitted = await programReply, body = await submitted.json();
        assert.equal(submitted.status(), 200, JSON.stringify(body));
        const request = submitted.request().postDataJSON(); assert.equal(request.source, source); assert.equal(request.expected_execution_id, previousExecution);
        current.execution_id = body.program.execution_id; const record = {phase, source, source_sha256: sha(source), program: body.program, request}; current.phases.push(record);
        assert.equal(body.program.pid, current.pid); assert.equal(body.program.firmware_sha256, current.firmware_sha256);
        record.observation = await serialSample(before, phase); record.capture = await capture(phase); record.runtime_identity = await identity();
        console.log(`UNIFORM_LED_PHASE_OBSERVED ${group.id} ${phase} execution=${current.execution_id}`);
        await zeroEcho(phase);
        if (phase === 'A') {
          const beforeNegative = await api(prefix + '/program'), beforeSerial = await api(prefix + '/serial?offset=0&limit=1048576');
          const rejected = await rawApi(prefix + '/program', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({entrypoint: 'main.mpy', files: {'main.mpy': {encoding: 'base64', data: validMpy.toString('base64')}}, expected_execution_id: current.execution_id})});
          const negativeBody = JSON.parse(rejected.bytes); assert.equal(rejected.status, 409); assert.equal(negativeBody.error.code, 'unsupported_program_entrypoint');
          const afterNegative = await api(prefix + '/program'); assert.equal(afterNegative.program.execution_id, current.execution_id); assert.equal(afterNegative.program.state, 'running');
          current.mpy_negative = {status: rejected.status, body: negativeBody, before_execution_id: beforeNegative.program.execution_id, after_execution_id: afterNegative.program.execution_id,
            continuation: await serialSample(beforeSerial, phase, record.observation.sample.sequence), valid_mpy_sha256: sha(validMpy)};
          await independentQom(phase); await identity();
        }
        if (phase === 'C') {
          const beforeFault = await api(prefix + '/serial?offset=0&limit=1048576'), faultCount = report.transport_faults.length;
          transportFaultSession = current.session_id;
          const unknown = await eventually(inspect, value => {try {assertVisual(value, group, phase, 'unavailable'); return true;} catch {return false;}});
          await delay(700); assertVisual(await inspect(), group, phase, 'unavailable');
          assert.ok(report.transport_faults.length > faultCount);
          const independent = await independentQom(phase), continuation = await serialSample(beforeFault, phase, record.observation.sample.sequence);
          const screenshots = await visibleScreenshots('C-transport-unknown');
          current.transport_negative = {scope: 'browser-only HTTP 503; real guest state remains available', unknown, independent, continuation,
            injected_gets: report.transport_faults.length - faultCount, screenshots};
          await zeroEcho('transport-unavailable'); transportFaultSession = null;
          const recovered = await eventually(inspect, value => {try {assertVisual(value, group, phase); return true;} catch {return false;}});
          assertVisual(recovered, group, phase); current.transport_negative.recovered = recovered; await identity();
        }
      }
      const data = await api(prefix + '/evidence'); await writeFile(resolve(current.output, 'evidence.zip'), data);
      await writeFile(resolve(current.output, 'validation-input.json'), JSON.stringify(current));
      current.evidence = JSON.parse(execFileSync(python, ['-c', zipValidator, resolve(current.output, 'evidence.zip'), resolve(current.output, 'validation-input.json')], {encoding: 'utf8', timeout: 30000}));
      assert.equal(current.evidence.zip_sha256, sha(data)); current.status = 'PASS';
    } finally {await cleanup();}
  }
  assert.equal(report.groups.length, 2); assert.ok(report.groups.every(groupAccepted), 'Every group must pass evidence and cleanup, including browser teardown');
  assert.deepEqual(report.unit_posts, []); assert.deepEqual(report.page_errors, []); assert.deepEqual(report.resource_errors, []);
  assert.deepEqual(await fingerprints(), report.source_sha256, 'Production or probe source changed during run'); report.status = 'PASS';
} catch (error) {report.error = error.stack || String(error);}
finally {
  // The inner finally normally handles this; this branch covers an early failure.
  if (current?.session_id) {
    transportFaultSession = null;
    try {await writeFile(resolve(current.output, 'failure-evidence.zip'), await api(`sessions/${current.session_id}/evidence`, {}, 20000));} catch (error) {report.evidence_error = String(error);}
    try {await api(`sessions/${current.session_id}?purge=0`, {method: 'DELETE'}, 20000);} catch (error) {report.cleanup_error = String(error);}
  }
  try {await browser?.close();} catch (error) {report.status = 'FAIL'; report.browser_close_error = String(error);}
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
}
console.log(`UNIFORM_LED_LIVE_BROWSER_${report.status} ${output}/report.json`);
if (report.status !== 'PASS') {console.error(report.error || report.cleanup_error || report.evidence_error); process.exitCode = 1;}
