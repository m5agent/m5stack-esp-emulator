// Host admission/layout/input contracts. No QEMU guest or service is started.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {validateQemuBrowserProfiles, getQemuBrowserProfile, validateQemuFirmware,
  buildQemuArguments, buildQemuEfuse, qemuInputCommand, loadQemuBrowserProfiles, resolveQemuFirmwareProfile} from '../web/public-qemu-profiles.js';
import {qemuProbeVfs} from '../web/public-qemu-probe-firmware.js';

const registry = JSON.parse(await readFile(new URL('../web/qemu-browser-profiles.json', import.meta.url), 'utf8'));
validateQemuBrowserProfiles(registry);
const pick = id => getQemuBrowserProfile(id, registry, {allowCandidateProfiles:true});
assert.deepEqual(registry.profiles.filter(p => p.admission === 'public').map(p => p.deviceId), ['sticks3', 'atoms3r', 'cores3', 'core2']);
assert.equal(getQemuBrowserProfile('stopwatch', registry), null, 'a compiled board without independent browser acceptance remains unavailable publicly');
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
let loadedURL;
const loaded = await loadQemuBrowserProfiles({root:'https://example.test/sim/', fetchImpl:async (url, options) => {
  loadedURL = url; assert.equal(options.credentials, 'omit'); return new Response(JSON.stringify(registry));
}});
assert.equal(loadedURL, 'https://example.test/sim/platform/web/qemu-browser-profiles.json');
assert.equal(loaded.profiles.length, 10);

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
  const raw = image(profile), before = raw.slice(), flash = validateQemuFirmware(raw, profile);
  assert.equal(flash.length, profile.flashMb * 1048576); assert.deepEqual(raw, before);
  assert.deepEqual(flash.subarray(0, raw.length), raw); assert.equal(flash.at(-1), 255);
  const args = buildQemuArguments(profile);
  assert.deepEqual(args.slice(0, 2), ['-M', profile.board]);
  assert.equal(args.includes('-global'), profile.chip === 'esp32s3');
  if (profile.efuse) assert.equal(new DataView(buildQemuEfuse(profile).buffer).getUint32(36, true), profile.efuse.packageVersion << 21);
  else assert.equal(buildQemuEfuse(profile), null);
  const wrongChip = raw.slice(); new DataView(wrongChip.buffer).setUint16(profile.bootloaderOffset + 12, profile.imageChipId === 9 ? 0 : 9, true);
  assert.throws(() => validateQemuFirmware(wrongChip, profile), /chip/);
  assert.throws(() => validateQemuFirmware(raw.subarray(0, 0x10020), profile), /Truncated/);
  const overflow = raw.slice(); new DataView(overflow.buffer).setUint32(0x8008, 0xffffffff, true);
  assert.throws(() => validateQemuFirmware(overflow, profile), /Partition/);
}
const core2 = pick('core2'), s3 = pick('cores3'), atom = pick('atoms3r');
for (const id of ['atoms3r', 'sticks3', 'core2']) {
  assert.equal(pick(id).clockDivisor, 1, 'fixed non-LVGL board probes use their admitted normal-clock configuration');
  assert.equal(pick(id).profile, `${id}-wasm-wallclock`);
}
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
