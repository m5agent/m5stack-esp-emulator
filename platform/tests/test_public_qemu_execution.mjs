// Host-only admission/engine contracts. A JS factory replaces QEMU; no guest
// firmware, C runtime, controller or emulated time is executed.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {validateQemuProfile,validateQemuRuntimeRequirements,resolveQemuFirmwareProfile,clearQemuFirmwareExecutionBinding,
  buildQemuArguments,buildQemuEfuse,qemuInputCommand,getQemuBrowserProfile,QEMU_ONE_INSN_RUNTIME_PATCH,QEMU_CARDPUTER_BOOT_RUNTIME_PATCH} from '../web/public-qemu-profiles.js';

const registry=JSON.parse(await readFile(new URL('../web/qemu-browser-profiles.json',import.meta.url)));
const base=getQemuBrowserProfile('stackchan',registry), firmwareSHA256='a'.repeat(64);
const variant={firmwareSHA256,profile:'stackchan-wasm-contract-wallclock',clockDivisor:1,
  readyMarker:'CONTRACT_READY',fixture:'host-contract-only',sourceSHA256:'b'.repeat(64),
  schedulerCandidate:'qemu-tci-mmio-blocks-v1',oneInsnPerTb:true,requiredRuntimePatch:{...QEMU_ONE_INSN_RUNTIME_PATCH}};
const prepared=structuredClone(base);prepared.firmwareProfiles=[variant];
const resolved=resolveQemuFirmwareProfile(prepared,firmwareSHA256);
const compatible={source:{patches:[{...QEMU_ONE_INSN_RUNTIME_PATCH}]}};
assert.equal(resolved.oneInsnPerTb,true);
assert.equal(resolved.readyFirmwareSHA256,firmwareSHA256);
assert.deepEqual(resolved.firmwareVariant,variant);
assert.deepEqual(buildQemuArguments(resolved).slice(-2),['-accel','tcg,thread=multi,one-insn-per-tb=on']);
assert.equal(buildQemuArguments(resolved).filter(x=>x==='-accel').length,1);
assert.equal(buildQemuArguments(resolved).includes('-icount'),false);
assert.equal(buildQemuArguments(resolved).includes('-smp'),false);
const unknown=resolveQemuFirmwareProfile(prepared,'c'.repeat(64));
assert.equal(unknown.oneInsnPerTb,undefined);assert.equal(unknown.requiredRuntimePatch,undefined);
assert.deepEqual(buildQemuArguments(unknown),buildQemuArguments(base),'unknown hashes retain the original default arguments');
assert.equal(prepared.oneInsnPerTb,undefined,'resolving must not mutate registry metadata');
for(const mutate of [
  p=>p.firmwareProfiles[0].oneInsnPerTb=false,p=>p.firmwareProfiles[0].oneInsnPerTb=1,
  p=>delete p.firmwareProfiles[0].requiredRuntimePatch,p=>delete p.firmwareProfiles[0].oneInsnPerTb,
  p=>p.firmwareProfiles[0].clockDivisor=8,p=>p.firmwareProfiles[0].icountShift=5,
  p=>p.firmwareProfiles[0].arguments=['-accel','tcg'],p=>p.firmwareProfiles[0].firmwareSHA256='short',
  p=>p.firmwareProfiles[0].requiredRuntimePatch.sha256='d'.repeat(64),
  p=>p.firmwareProfiles[0].requiredRuntimePatch.path='../other.patch',
  p=>p.firmwareProfiles[0].requiredRuntimePatch.extra=true,
  p=>p.accelerator={kind:'tcg-icount',thread:'single',tbSizeMb:128,icountShift:5},
]){
  const bad=structuredClone(prepared);mutate(bad);assert.throws(()=>resolveQemuFirmwareProfile(bad,firmwareSHA256));
}
for(const mutate of [p=>p.oneInsnPerTb=false,p=>p.oneInsnPerTb='true',p=>p.clockDivisor=8,
  p=>delete p.firmwareVariant,p=>p.readyFirmwareSHA256='c'.repeat(64),p=>p.readyMarker='unbound',
  p=>delete p.requiredRuntimePatch,p=>p.requiredRuntimePatch.sha256='d'.repeat(64),
  p=>p.accelerator={kind:'tcg-icount',thread:'single',tbSizeMb:128,icountShift:5},
  p=>p.accelerator={kind:'tcg',thread:'multi'},
]){
  const bad=structuredClone(resolved);mutate(bad);assert.throws(()=>buildQemuArguments(bad));
}
for(const manifest of [{},{source:{}},{source:{patches:{}}},{source:{patches:[]}},
  {source:{patches:[{...QEMU_ONE_INSN_RUNTIME_PATCH,sha256:'0'.repeat(64)}]}},
  {source:{patches:[{...QEMU_ONE_INSN_RUNTIME_PATCH},{...QEMU_ONE_INSN_RUNTIME_PATCH}]}},
])assert.throws(()=>validateQemuRuntimeRequirements(resolved,manifest),/required source patch/);
assert.equal(validateQemuRuntimeRequirements(resolved,compatible),resolved);
assert.equal(validateQemuRuntimeRequirements(base,{}),base,'ordinary profiles remain compatible with older manifests');

// A G0 carrier is admitted only with the exact compiled GPIO0/FIFO-separation patch.
const cardputerBoot=getQemuBrowserProfile('cardputer-adv',registry);
assert.equal(qemuInputCommand(cardputerBoot,{type:'button',id:'boot',down:true}).arguments.events[0].data.key.data,'f12');
assert.equal(cardputerBoot.inputs.keyboard.includes('f12'),false,'G0 is separate from the 56-key matrix');
for(const manifest of [{},{source:{patches:[]}},
  {source:{patches:[{...QEMU_CARDPUTER_BOOT_RUNTIME_PATCH,sha256:'0'.repeat(64)}]}},
  {source:{patches:[{...QEMU_CARDPUTER_BOOT_RUNTIME_PATCH},{...QEMU_CARDPUTER_BOOT_RUNTIME_PATCH}]}},
])assert.throws(()=>validateQemuRuntimeRequirements(cardputerBoot,manifest),/physical input required source patch/);
assert.equal(validateQemuRuntimeRequirements(cardputerBoot,{source:{patches:[{...QEMU_CARDPUTER_BOOT_RUNTIME_PATCH}]}}),cardputerBoot);
for(const mutate of [p=>delete p.requiredInputPatch,p=>p.requiredInputPatch.sha256='0'.repeat(64),
  p=>p.requiredInputPatch.path='../unknown.patch',p=>p.requiredInputPatch.extra=true,
  p=>p.inputs.buttons.boot='a',p=>delete p.inputs.buttons.boot,p=>p.inputs.keyboard.push('f12')]){
  const bad=structuredClone(cardputerBoot);mutate(bad);assert.throws(()=>validateQemuProfile(bad),/physical input patch binding/);
}
const foreignInputPatch=structuredClone(base);foreignInputPatch.requiredInputPatch={...QEMU_CARDPUTER_BOOT_RUNTIME_PATCH};
assert.throws(()=>validateQemuProfile(foreignInputPatch),/physical input patch binding/);

// Published BINs identify their original artifact, never claim matching source
// code or an application-ready log. Only these complete Flash/device pairs opt in.
for(const deviceId of ['stopwatch']){
  const original=getQemuBrowserProfile(deviceId,registry),vendor=original.firmwareProfiles.find(row=>row.sourceKind==='published-firmware-binary');
  assert.ok(vendor,'each exact vendor artifact has an explicit provenance row');
  const admitted=resolveQemuFirmwareProfile(original,vendor.firmwareSHA256);
  assert.equal(admitted.readyMarker,null);assert.equal(admitted.readyFirmwareSHA256,vendor.firmwareSHA256);
  assert.equal(admitted.firmwareVariant.sourceKind,'published-firmware-binary');
  assert.equal(admitted.firmwareVariant.sourceSHA256,vendor.sourceSHA256);
  assert.equal(admitted.oneInsnPerTb,true);assert.equal(admitted.clockDivisor,1);
  assert.equal(buildQemuArguments(admitted).at(-1),'tcg,thread=multi,one-insn-per-tb=on');
  assert.equal(validateQemuRuntimeRequirements(admitted,compatible),admitted);
  assert.throws(()=>validateQemuRuntimeRequirements(admitted,{source:{patches:[]}}),/required source patch/);
  const unmatched=resolveQemuFirmwareProfile(original,'e'.repeat(64));
  assert.equal(unmatched.oneInsnPerTb,undefined);assert.equal(unmatched.profile,original.profile);
  assert.deepEqual(buildQemuArguments(unmatched),buildQemuArguments(original));
  const overridden=clearQemuFirmwareExecutionBinding(structuredClone(admitted));
  assert.equal(overridden.firmwareVariant,undefined);assert.equal(overridden.oneInsnPerTb,undefined);
  assert.equal(overridden.requiredRuntimePatch,undefined);assert.equal(overridden.readyMarker,null);
  assert.equal(overridden.readyFirmwareSHA256,null,'no absent app marker retains a ready identity after the variant is cleared');
  assert.doesNotThrow(()=>validateQemuProfile(overridden));
  assert.equal(buildQemuArguments(overridden).includes('-accel'),false);
  for(const change of [v=>delete v.sourceKind,v=>v.sourceKind=null,v=>v.sourceKind=undefined,v=>v.sourceKind='source-code',
    v=>v.sourceKind='unknown',v=>v.sourceSHA256='f'.repeat(64),v=>v.firmwareSHA256='f'.repeat(64),
    v=>v.readyMarker='boot complete',v=>v.readyMarker='',v=>delete v.readyMarker,
    v=>v.fixture='unreviewed-vendor-pad',v=>v.clockDivisor=8,v=>delete v.oneInsnPerTb,v=>delete v.requiredRuntimePatch]){
    const bad=structuredClone(original),row=bad.firmwareProfiles.find(v=>v.sourceKind==='published-firmware-binary');change(row);
    assert.throws(()=>validateQemuProfile(bad),'vendor metadata cannot alias a source-code row or unknown provenance');
  }
  const foreign=getQemuBrowserProfile(deviceId==='stackchan'?'stopwatch':'stackchan',registry);
  foreign.firmwareProfiles=[structuredClone(vendor)];
  assert.throws(()=>validateQemuProfile(foreign),/published firmware binary provenance/,'a full image is bound to its actual board');
  const detached=structuredClone(admitted);delete detached.firmwareVariant;delete detached.oneInsnPerTb;delete detached.requiredRuntimePatch;
  assert.throws(()=>validateQemuProfile(detached),/ready marker/,'generic null-marker/hash combinations stay forbidden');
}
const unadmittedFactory=resolveQemuFirmwareProfile(base,'39910815a732530b95a0fc3a7cd251b26cc818b2a94e6a6a9b2abd94c75e97da');
assert.equal(unadmittedFactory.firmwareVariant,undefined,'the unstable Factory diagnostic does not admit a product execution variant');
assert.deepEqual(buildQemuArguments(unadmittedFactory),buildQemuArguments(base));
const dance=base.firmwareProfiles.find(row=>row.firmwareSHA256==='c854d3ac6b958439ad30c5277266575d8765f228febf75de243da5d011904542');
assert.equal(dance.sourceKind,undefined);assert.equal(typeof dance.readyMarker,'string');
for(const change of [v=>v.sourceKind='published-firmware-binary',v=>v.readyMarker=null]){
  const bad=structuredClone(base);change(bad.firmwareProfiles.find(row=>row.firmwareSHA256===dance.firmwareSHA256));
  assert.throws(()=>validateQemuProfile(bad),'the dance source-code/real marker contract cannot migrate to publisher BIN provenance');
}
const danceOverride=clearQemuFirmwareExecutionBinding(resolveQemuFirmwareProfile(base,dance.firmwareSHA256));
assert.equal(danceOverride.readyMarker,dance.readyMarker);assert.equal(danceOverride.readyFirmwareSHA256,dance.firmwareSHA256);

const source=(await readFile(new URL('../web/public-qemu-engine.js',import.meta.url),'utf8')).replace(/^import .+;\r?\n/gm,'');
class NativeWorker {terminate(){}}
class TestBlob {constructor(parts){this.parts=parts;}}
class TestURL extends URL {
  static createObjectURL(blob){return 'data:text/javascript;base64,'+Buffer.concat(blob.parts.map(x=>Buffer.from(x))).toString('base64');}
  static revokeObjectURL(){}
}
function engine(){
  const context=vm.createContext({Worker:NativeWorker,TextEncoder,TextDecoder,Uint8Array,Map,Set,
    URL:TestURL,Blob:TestBlob,ArrayBuffer,Number,JSON,Error,Promise,WebAssembly,setTimeout,clearTimeout,
    location:{origin:'https://example.test'},crossOriginIsolated:true,SharedArrayBuffer,crypto:globalThis.crypto,performance,
    validateQemuProfile,validateQemuRuntimeRequirements,buildQemuArguments,buildQemuEfuse,qemuInputCommand,
    self:{postMessage(){},close(){}},addEventListener(){}});
  vm.runInContext(source+'\nglobalThis.contract={start,request,snapshot:()=>({arguments:runtimeArguments,env:module?.ENV})};',context,
    {importModuleDynamically:vm.constants.USE_MAIN_CONTEXT_DEFAULT_LOADER});
  return {context,...context.contract};
}
const factory=`export default async function(options){
 const stream={stream_ops:{}};const m={ENV:{},HEAPU8:new Uint8Array(new SharedArrayBuffer(65536)),
 FS:{mkdirTree(){},writeFile(){},makedev:(a,b)=>b,registerDevice(){},mkdev(){},getStream:()=>stream}};
 for(const f of options.preRun)f(m);options.onRuntimeInitialized();return m;
}`;
function config(profile=resolved,patches=compatible.source.patches){return {
  javascript:new TextEncoder().encode(factory),javascriptURL:'https://example.test/qemu.js',worker:new Uint8Array(),
  profile,runtimePatches:patches,frameTransport:'shared-rgb565-v1',
  roms:profile.roms.map(x=>({name:x.name,sha256:x.sha256,bytes:new ArrayBuffer(x.bytes)})),firmware:new ArrayBuffer(0),
};}
const allowed=engine();await allowed.start(config());
assert.deepEqual(Array.from(allowed.snapshot().arguments),buildQemuArguments(resolved),'factory receives the exact single accelerator arguments');
assert.equal(allowed.snapshot().env.M5_WASM_VM_CLOCK_DIVISOR,'1');
assert.equal(Object.hasOwn(allowed.snapshot().env,'M5_QEMU_WASM_JIT'),false,'the shipped engine does not select a second CPU implementation');
await assert.rejects(engine().start(config(resolved,[])),/required source patch/,'engine independently rejects an old runtime manifest');
await assert.rejects(engine().start(config(cardputerBoot,[])),/physical input required source patch/,'engine independently rejects a runtime without the G0 GPIO0 route');
const bootEngine=engine();await bootEngine.start(config(cardputerBoot,[{...QEMU_CARDPUTER_BOOT_RUNTIME_PATCH}]));
const ordinary=engine();await ordinary.start(config(base,undefined));
assert.deepEqual(Array.from(ordinary.snapshot().arguments),buildQemuArguments(base));
assert.equal(ordinary.snapshot().arguments.includes('-accel'),false);
console.log('PUBLIC_QEMU_EXECUTION_OK: SHA/ready-bound single-instruction variant, exact source-patch capability, default/unknown arguments and engine checks; no guest executed');
