// Host admission/layout/input contracts. No QEMU guest or service is started.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {validateQemuBrowserProfiles, getQemuBrowserProfile, validateQemuFirmware,
  buildQemuArguments, buildQemuEfuse, advanceQemuEncoderTarget, qemuInputCommand, loadQemuBrowserProfiles, resolveQemuFirmwareProfile,
  qemuOnboardOutputQueries, validateQemuOnboardState} from '../web/public-qemu-profiles.js';
import {qemuProbeVfs} from '../web/public-qemu-probe-firmware.js';

const registry = JSON.parse(await readFile(new URL('../web/qemu-browser-profiles.json', import.meta.url), 'utf8'));
validateQemuBrowserProfiles(registry);
const pick = id => getQemuBrowserProfile(id, registry, {allowCandidateProfiles:true});
assert.deepEqual(registry.profiles.filter(p => p.admission === 'public').map(p => p.deviceId), ['stopwatch', 'sticks3', 'atoms3', 'atoms3-lite', 'atoms3r', 'cores3', 'cardputer-adv', 'stamplc', 'stackchan', 'papercolor', 'papermono', 'core2', 'stickc-plus2', 'stickc', 'stickc-plus-se']);
const withheld = structuredClone(registry); withheld.profiles.find(row => row.deviceId === 'stopwatch').admission = 'candidate';
assert.equal(getQemuBrowserProfile('stopwatch', withheld), null, 'a compiled board without independent browser acceptance remains unavailable publicly');
assert.equal(getQemuBrowserProfile('nanoc6', registry, {allowCandidateProfiles:true}), null);
assert.equal(getQemuBrowserProfile('tab5', registry, {allowCandidateProfiles:true}), null);
const detached = pick('cores3'); detached.display.width = 1;
assert.equal(pick('cores3').display.width, 320);
const duplicate = structuredClone(registry); duplicate.profiles.push(duplicate.profiles[0]);
assert.throws(() => validateQemuBrowserProfiles(duplicate), /Duplicate/);
for (const mutate of [p => p.target = 'riscv32-softmmu', p => p.roms[0].url = 'https://example.test/rom',
  p => p.inputs.pir = {path:'/machine/other',property:'motion'}, p => p.display.hostRotation = 90,
  p => p.efuse.packageVersion = 2, p => p.reference.sha256 = 'unknown']) {
  const broken = structuredClone(registry); mutate(broken.profiles.find(p => p.deviceId === 'cores3'));
  assert.throws(() => validateQemuBrowserProfiles(broken));
}
for (const [id, mutate] of [
  ['papercolor', p => p.fixture.frameOracle.rect.x = p.display.width],
  ['papercolor', p => p.fixture.frameOracle.after = p.fixture.frameOracle.before],
  ['papercolor', p => p.fixture.frameOracle.before = 65536],
  ['papercolor', p => p.fixture.frameOracle.encoding = 'unreviewed'],
  ['stopwatch', p => p.fixture.logicalDisplay.width = 0],
  ['papermono', p => p.fixture.touchPoint.y = p.display.height],
  ['papermono', p => p.inputs.touch = false],
  ['papermono', p => p.fixture.coordinateSource = 'host-fabricated'],
  ['papermono', p => p.fixture.logicalTouchStatus = 'fixed'],
  ['papermono', p => p.fixture.releaseCoordinates = 'current-logical'],
]) {
  const broken = structuredClone(registry); mutate(broken.profiles.find(p => p.deviceId === id));
  assert.throws(() => validateQemuBrowserProfiles(broken), /Invalid QEMU/);
}
let loadedURL;
const loaded = await loadQemuBrowserProfiles({root:'https://example.test/sim/', fetchImpl:async (url, options) => {
  loadedURL = url; assert.equal(options.credentials, 'omit'); return new Response(JSON.stringify(registry));
}});
assert.equal(loadedURL, 'https://example.test/sim/platform/web/qemu-browser-profiles.json');
assert.equal(loaded.profiles.length, registry.profiles.length);
const originalAtom = pick('atoms3');
assert.equal(originalAtom.admission, 'public');
assert.equal(getQemuBrowserProfile('atoms3', registry).fixture.firmwareSHA256, originalAtom.fixture.firmwareSHA256);
assert.equal(originalAtom.board, 'm5atoms3');
assert.equal(originalAtom.psramMb, 0);
assert.equal(originalAtom.efuse.packageVersion, 0);
assert.equal(originalAtom.reference.sha256, 'fb294c9780cfc3766fd489e164a1a04dddf54cb989adb113d098fe10cbc52075');
assert.equal(originalAtom.fixture.firmwareSHA256, '1cd37f1eb26c466e4c1bae052a55a5e0be307e3b60f9762a0c8a4d36d4a81319');
assert.equal(originalAtom.fixture.sources['boot.py'].path, 'platform/runtime/qemu-probe/fixture/core2_boot.py');
assert.equal(qemuInputCommand(originalAtom, {type:'button',id:'button',down:true}).arguments.events[0].data.key.data, 'a');
const lite = pick('atoms3-lite');
assert.equal(lite.display, null); assert.equal(lite.board, 'm5atoms3lite'); assert.equal(lite.psramMb, 0);
assert.equal(lite.admission, 'public'); assert.equal(getQemuBrowserProfile('atoms3-lite', registry).display, null);
assert.equal(lite.reference.sha256, '338baf7f16703b26fff78619d32e593d8ca4f1934bdad63e3c95eef862f3133c');
assert.equal(lite.fixture.id, 'xtensa-board-led-v1');
assert.equal(lite.fixture.firmwareSHA256, 'ad515fce316589d186fbcfb53b409787936f052748323db4b793ef3bc640fa36');
assert.equal(lite.fixture.sources['boot.py'].path, 'platform/runtime/qemu-probe/fixture/boot.py');
assert.deepEqual(qemuOnboardOutputQueries(lite), ['led-rgb','led-frames','pressed'].map(property=>({execute:'qom-get',arguments:{path:'/machine/onboard_io',property}})));
assert.equal(qemuInputCommand(lite, {type:'button',id:'button',down:true}).arguments.events[0].data.key.data, 'a');
assert.throws(()=>qemuInputCommand(lite, {type:'touch',x:0,y:0,down:true}), /unsupported/);
assert.throws(()=>qemuOnboardOutputQueries(pick('atoms3')), /no admitted/);
for (const mutate of [p=>p.outputs.path='/machine/other',p=>p.outputs.properties[0]='led-write',p=>p.outputs.properties=['led-rgb,led-frames,pressed'],
  p=>p.outputs.properties.push('input-level'),p=>p.outputs.value=0,p=>p.outputs.ledTarget='other',p=>p.outputs.buttonTarget='reset',
  p=>p.inputs.touch=true,p=>p.psramMb=8,p=>p.efuse.packageVersion=1,p=>p.board='m5atoms3r',p=>p.deviceId='atoms3',p=>p.display={width:1,height:1,coordinateSpace:'qemu-physical-frame',hostRotation:0}]) {
  const changed=structuredClone(lite);mutate(changed);assert.throws(()=>validateQemuBrowserProfiles({...registry,profiles:[changed]}));
}
const onboardState={schema_version:1,device_id:'atoms3-lite',source:'qemu-rmt-qom-readback',path:'/machine/onboard_io',led_rgb:0x204060,led_frames:1,pressed:false};
assert.equal(validateQemuOnboardState(lite,onboardState),onboardState);
for(const mutate of [s=>s.path='/machine/other',s=>s.source='host-input-echo',s=>s.device_id='atoms3',s=>s.led_rgb=0x1000000,
  s=>s.led_rgb=-1,s=>s.led_frames=1.5,s=>s.led_frames=Number.MAX_SAFE_INTEGER+1,s=>s.pressed=1,s=>s.value=123]) {
  const changed=structuredClone(onboardState);mutate(changed);assert.throws(()=>validateQemuOnboardState(lite,changed));
}
for(const expected of [
  {id:'stickc',board:'m5stickc',width:80,height:160,base:'2463fc362f6acfacccb678a2c40aeb733e470ca793ec4a100d2e077baa641f03',composed:'ece54cdc3ba937dbe3e8b30185432d604312b4c4d9961167cf24f08d65902b15'},
  {id:'stickc-plus-se',board:'m5stickcplusse',width:135,height:240,base:'0c7055bb8e64afe1d8fa4fd4bdc0961ca0d6366351aca5d6c83eaaf72155ee88',composed:'21ed0df8f19b9ed2c670f411a6b448a8469a68dbaaca5653e529dbf95e99f2dc'},
]){
  const profile=pick(expected.id);
  assert.equal(profile.admission,'public');assert.equal(getQemuBrowserProfile(expected.id,registry).board,expected.board);
  assert.equal(profile.board,expected.board);assert.equal(profile.flashMb,4);assert.equal(profile.psramMb,0);
  assert.equal(profile.efuse.packageVersion,5);assert.equal(profile.display.width,expected.width);assert.equal(profile.display.height,expected.height);
  assert.equal(profile.reference.sha256,expected.base);assert.equal(profile.fixture.firmwareSHA256,expected.composed);
  assert.equal(profile.fixture.sources['boot.py'].path,'platform/runtime/qemu-probe/fixture/core2_boot.py');
  assert.equal(qemuInputCommand(profile,{type:'button',id:'a',down:true}).arguments.events[0].data.key.data,'a');
  for(const mutate of [p=>p.efuse.packageVersion=6,p=>p.efuse=null,p=>p.flashMb=8,p=>p.psramMb=2,
    p=>p.board='m5stickcplus2',p=>p.deviceId='stickc-plus',p=>p.display.width=240]){
    const changed=structuredClone(profile);mutate(changed);assert.throws(()=>validateQemuBrowserProfiles({...registry,profiles:[changed]}));
  }
}

function image(profile) {
  const bytes = new Uint8Array(0x10100).fill(255), view = new DataView(bytes.buffer);
  for (const offset of [profile.bootloaderOffset, 0x10000]) {
    bytes[offset] = 0xe9; bytes[offset + 1] = 1;
    view.setUint16(offset + 12, profile.imageChipId, true); view.setUint32(offset + 28, 4, true);
  }
  view.setUint16(0x8000, 0x50aa, true); bytes[0x8002] = 0;
  view.setUint32(0x8004, 0x10000, true); view.setUint32(0x8008, 0x1000, true);
  return bytes;
}
for (const profile of registry.profiles) {
  if (profile.fixture?.id === 'xtensa-board-display-v1') {
    assert.ok(Number.isSafeInteger(profile.fixture.preservedFileCount));
    assert.equal(profile.fixture.preservedFileCount, profile.fixture.baseFileCount - 2);
  }
  const raw = image(profile), before = raw.slice(), flash = validateQemuFirmware(raw, profile);
  assert.equal(flash.length, profile.flashMb * 1048576); assert.deepEqual(raw, before);
  assert.deepEqual(flash.subarray(0, raw.length), raw); assert.equal(flash.at(-1), 255);
  const args = buildQemuArguments(profile);
  assert.deepEqual(args.slice(0, 2), ['-M', profile.board]);
  assert.equal(args.includes('-global'), Boolean(profile.efuse));
  if (profile.efuse) {
    const offset=profile.chip==='esp32'?12:36, shift=profile.chip==='esp32'?9:21;
    assert.equal(new DataView(buildQemuEfuse(profile).buffer).getUint32(offset,true),profile.efuse.packageVersion<<shift);
  }
  else assert.equal(buildQemuEfuse(profile), null);
  const wrongChip = raw.slice(); new DataView(wrongChip.buffer).setUint16(profile.bootloaderOffset + 12, profile.imageChipId === 9 ? 0 : 9, true);
  assert.throws(() => validateQemuFirmware(wrongChip, profile), /chip/);
  assert.throws(() => validateQemuFirmware(raw.subarray(0, 0x10020), profile), /Truncated/);
  const overflow = raw.slice(); new DataView(overflow.buffer).setUint32(0x8008, 0xffffffff, true);
  assert.throws(() => validateQemuFirmware(overflow, profile), /Partition/);
}
const core2 = pick('core2'), s3 = pick('cores3'), atom = pick('atoms3r');
for (const id of ['atoms3r', 'sticks3']) {
  assert.equal(pick(id).clockDivisor, 1, 'fixed non-LVGL board probes use their admitted normal-clock configuration');
  assert.equal(pick(id).profile, `${id}-wasm-wallclock`);
}
assert.equal(core2.clockDivisor, 1);
assert.equal(core2.profile, 'core2-wasm-deterministic-icount');
assert.deepEqual(core2.accelerator, {kind:'tcg-icount', thread:'single', tbSizeMb:128, icountShift:5});
assert.deepEqual(buildQemuArguments(core2).slice(-4),
  ['-accel', 'tcg,thread=single,tb-size=128', '-icount', 'shift=5,align=off,sleep=off']);
const variantSHA = 'e9500994f4c0e1708ec35f5a46146225ac330d210a2427e1fc537c33635d9554';
const variantProfile = resolveQemuFirmwareProfile(s3, variantSHA);
assert.equal(variantProfile.clockDivisor, 1); assert.equal(variantProfile.profile, 'cores3-wasm-wallclock-sdk-candidate');
assert.equal(variantProfile.readyFirmwareSHA256, variantSHA); assert.equal(variantProfile.firmwareVariant.schedulerCandidate, 'sdk-python-single-schedule-v1');
for (const key of ['board','chip','imageChipId','flashMb','psramMb','display','roms','inputs','units','efuse']) assert.deepEqual(variantProfile[key], s3[key], 'firmware metadata cannot change hardware');
assert.equal(s3.clockDivisor, 8, 'variant resolution must not mutate the base profile');
assert.equal(resolveQemuFirmwareProfile(s3, '0'.repeat(64)).clockDivisor, 8);
assert.equal(resolveQemuFirmwareProfile(s3, '0'.repeat(64)).firmwareVariant, undefined);
for (const mutate of [p => p.firmwareProfiles.push({...p.firmwareProfiles[0]}), p => p.firmwareProfiles[0].board = 'm5core2',
  p => p.firmwareProfiles[0].firmwareSHA256 = 'short', p => p.firmwareProfiles[0].clockDivisor = 2]) {
  const broken = structuredClone(registry); mutate(broken.profiles.find(p => p.deviceId === 'cores3')); assert.throws(() => validateQemuBrowserProfiles(broken));
}
assert.equal(core2.bootloaderOffset, 4096); assert.equal(core2.roms.length, 2);
assert.throws(() => validateQemuFirmware(image(core2), s3), /ESP image/);
const touch = qemuInputCommand(s3, {type:'touch', x:319, y:239, down:true});
assert.deepEqual(touch.arguments.events.slice(0, 2).map(e => e.data.value), [32767, 32767]);
for (const coordinate of [[320, 0], [0, 240], [-1, 1], [1.5, 1]]) assert.throws(() => qemuInputCommand(s3, {type:'touch',x:coordinate[0],y:coordinate[1],down:true}));
assert.throws(() => qemuInputCommand(atom, {type:'touch',x:1,y:1,down:true}));
assert.equal(qemuInputCommand(atom, {type:'button',id:'button',down:true}).arguments.events[0].data.key.data, 'a');
assert.equal(qemuInputCommand(atom, {type:'button',id:'a',down:true}).arguments.events[0].data.key.data, 'a', 'model/fallback shell emits normalized qcode');
assert.equal(qemuInputCommand(pick('cardputer-adv'), {type:'key',key:'a',down:false}).arguments.events[0].data.down, false);
assert.equal(qemuInputCommand(pick('cardputer-adv'), {type:'button',id:'a',down:false}).arguments.events[0].data.down, false, 'keyboard model also emits control events');
assert.throws(() => qemuInputCommand(atom, {type:'key',key:'a',down:true}));
assert.equal(qemuInputCommand(s3, {type:'pir',motion:true}).readback.execute, 'qom-get');
assert.throws(() => qemuInputCommand(atom, {type:'pir',motion:true}));
assert.throws(() => qemuInputCommand(s3, {type:'uart',text:'hello'}));
const probe = pick('atoms3r'), probeFlash = validateQemuFirmware(image(probe), probe), vfsAt = 0x8020;
const vfsView = new DataView(probeFlash.buffer);
vfsView.setUint16(vfsAt, 0x50aa, true); probeFlash[vfsAt + 2] = 1; probeFlash[vfsAt + 3] = 0x81;
vfsView.setUint32(vfsAt + 4, probe.fixture.vfsOffset, true); vfsView.setUint32(vfsAt + 8, probe.fixture.vfsSize, true);
probeFlash.fill(0, vfsAt + 12, vfsAt + 32); probeFlash.set(new TextEncoder().encode('vfs'), vfsAt + 12);
assert.equal(qemuProbeVfs(probeFlash, probe).size, probe.fixture.vfsSize);
for (const mutate of [view => view.setUint32(vfsAt + 28, 1, true), view => view.setUint32(vfsAt + 4, probe.fixture.vfsOffset + 4096, true),
  view => view.setUint32(vfsAt + 8, 0xffffffff, true)]) {
  const changed = probeFlash.slice(); mutate(new DataView(changed.buffer)); assert.throws(() => qemuProbeVfs(changed, probe), /VFS layout/);
}
const duplicateVfs = probeFlash.slice(); duplicateVfs.set(duplicateVfs.subarray(vfsAt, vfsAt + 32), vfsAt + 32);
assert.throws(() => qemuProbeVfs(duplicateVfs, probe), /exactly one/);
console.log('QEMU browser per-board admission, merged image layout, ROM/eFuse, frame coordinates and controller input contracts passed; no guest executed');

const plus2 = pick('stickc-plus2');
assert.equal(plus2.admission, 'public');
assert.equal(getQemuBrowserProfile('stickc-plus2', registry).board, 'm5stickcplus2');
assert.equal(plus2.board, 'm5stickcplus2');
assert.equal(plus2.psramMb, 2);
assert.equal(plus2.fixture.firmwareSHA256, 'bcdcac7a7590153c4d4db05a3ff9f3e4b84d8678740d0dc27851c2425e431f68');
assert.equal(plus2.fixture.sources['main.py'].path, 'platform/runtime/qemu-probe/fixture/stickc_plus2_main.py');
assert.deepEqual(plus2.accelerator, core2.accelerator);
const plus2Efuse=new DataView(buildQemuEfuse(plus2).buffer);
assert.equal(plus2Efuse.getUint32(12,true), 6<<9);
assert.equal(plus2Efuse.getUint32(36,true), 0);
assert.equal(buildQemuEfuse(core2), null);
for(const mutate of [p=>p.efuse.driver='nvram.esp32s3.efuse',p=>p.efuse.packageVersion=5,p=>p.psramMb=8,p=>p.board='m5core2',p=>p.efuse.bytes=64,p=>p.efuse=null]) {
 const changed=structuredClone(plus2);mutate(changed);assert.throws(()=>validateQemuBrowserProfiles({...registry,profiles:[changed]}), /eFuse/);
}

const dial = pick('dial');
assert.equal(dial.admission, 'candidate');
assert.equal(getQemuBrowserProfile('dial', registry), null);
assert.equal(dial.board, 'm5dial');
assert.equal(dial.flashMb, 8); assert.equal(dial.psramMb, 0);
assert.equal(dial.reference.sha256, '6a0187dad13c491129e9228ca36b9e04adb46ebf9d8d51fca8eca5f9b7332a53');
assert.equal(dial.fixture.firmwareSHA256, 'c2877fc3727664412acb4d40cf3df497d6ecdaa778b88f5a963a0f804ae2b6a7');
const rotary=qemuInputCommand(dial,{type:'encoder',detents:-3});
assert.deepEqual(rotary,{execute:'qom-set',arguments:{path:'/machine/encoder',property:'detents',value:-3},readback:{execute:'qom-get',arguments:{path:'/machine/encoder',property:'detents'}},readbackResult:'detents'});
for(const event of [{type:'encoder',detents:4097},{type:'encoder',detents:-4097},{type:'encoder',detents:1.5},
 {type:'encoder',detents:0,path:'/machine/other'},{type:'encoder',detents:0,property:'gpio-edges'}]) assert.throws(()=>qemuInputCommand(dial,event));
assert.throws(()=>qemuInputCommand(plus2,{type:'encoder',detents:1}));
for(const mutate of [p=>p.inputs.encoder.path='/machine/other',p=>p.inputs.encoder.property='gpio-edges',p=>p.inputs.encoder.minimum=-8192,
 p=>p.inputs.encoder.maximum=8192,p=>p.inputs.encoder.value=1,p=>p.board='m5atoms3',p=>p.deviceId='atoms3']) {
 const changed=structuredClone(dial);mutate(changed);assert.throws(()=>validateQemuBrowserProfiles({...registry,profiles:[changed]}), /encoder/);
}

let gesture = advanceQemuEncoderTarget(dial, {target:0,remainderDegrees:0}, 11.25);
assert.equal(gesture.command,null);
gesture=advanceQemuEncoderTarget(dial,gesture.state,11.25);
assert.deepEqual(gesture,{state:{target:1,remainderDegrees:0},command:{type:'encoder',detents:1}});
gesture=advanceQemuEncoderTarget(dial,gesture.state,-45);
assert.deepEqual(gesture,{state:{target:-1,remainderDegrees:0},command:{type:'encoder',detents:-1}});
gesture=advanceQemuEncoderTarget(dial,{target:0,remainderDegrees:10},-10);
assert.equal(gesture.command,null);assert.deepEqual(gesture.state,{target:0,remainderDegrees:0});
for(const [state,delta] of [[{target:4096,remainderDegrees:0},22.5],[{target:-4096,remainderDegrees:0},-22.5],
 [{target:0,remainderDegrees:22.5},0],[{target:0,remainderDegrees:0},Infinity],[{target:0,remainderDegrees:0},181],
 [{target:1.5,remainderDegrees:0},1],[{target:0,remainderDegrees:0,guestCount:0},1]])
 assert.throws(()=>advanceQemuEncoderTarget(dial,state,delta));
assert.throws(()=>advanceQemuEncoderTarget(plus2,{target:0,remainderDegrees:0},22.5));
