import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {composeUIFlowWorkbenchImage, validateUIFlowWorkbenchRegistry, resolveUIFlowWorkbenchProfile,
  UIFLOW_WORKBENCH_READY} from '../web/public-uiflow-firmware.js';
import {validateQemuBrowserProfiles, resolveQemuFirmwareProfile, validateQemuRuntimeRequirements,
  QEMU_ONE_INSN_RUNTIME_PATCH} from '../web/public-qemu-profiles.js';
import {planPublicQemuGate, publicQemuGateChildEnvironment, validatePublicQemuGateResult, PUBLIC_QEMU_GATE_PHASES,
  publicQemuGateWorkers, schedulePublicQemuGate} from './test_public_qemu_admitted_boards.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const registry = validateUIFlowWorkbenchRegistry(JSON.parse(await fs.readFile(path.join(root, 'platform/web/uiflow-workbench-profiles.json'))));
const qemu = validateQemuBrowserProfiles(JSON.parse(await fs.readFile(path.join(root, 'platform/web/qemu-browser-profiles.json'))));
const originalQemu = structuredClone(qemu);
assert.deepEqual(registry.profiles.map(row => row.deviceId).sort(), qemu.profiles.filter(row => row.admission === 'public').map(row => row.deviceId).sort());
for (const row of registry.profiles) {
  const profile = qemu.profiles.find(profile => profile.deviceId === row.deviceId);
  for (const source of Object.values(row.files)) {
    const bytes = await fs.readFile(path.join(root, source.path));
    assert.equal(bytes.toString('utf8'), source.text); assert.equal(bytes.length, source.bytes); assert.equal(sha(bytes), source.sha256);
  }
  assert.equal(row.files['boot.py'].path.endsWith('/boot_native.py'), profile.fixture.sources?.['boot.py']?.path.endsWith('/core2_boot.py') === true);
  assert.equal(row.files['main.py'].text, 'import M5\n\nM5.begin()\nprint("M5_UIFLOW_WORKBENCH_READY")\n');
  const resolved = resolveUIFlowWorkbenchProfile(resolveQemuFirmwareProfile(profile, row.firmwareSHA256), row.firmwareSHA256, registry);
  assert.equal(resolved.readyMarker, UIFLOW_WORKBENCH_READY); assert.equal(resolved.readyFirmwareSHA256, row.firmwareSHA256);
  if (['cores3','stamplc'].includes(row.deviceId)) {
    assert.equal(resolved.clockDivisor, 1); assert.equal(resolved.oneInsnPerTb, true);
    assert.equal(resolved.profile, row.deviceId==='cores3'?'cores3-wasm-uiflow-workbench-wallclock-candidate'
      :'stamplc-wasm-uiflow-workbench-wallclock-oneinsn-candidate');
    assert.deepEqual(resolved.requiredRuntimePatch, QEMU_ONE_INSN_RUNTIME_PATCH);
    assert.equal(resolved.firmwareVariant.firmwareSHA256, row.firmwareSHA256);
    assert.equal(resolved.firmwareVariant.sourceSHA256, row.files['main.py'].sha256);
    assert.equal(resolved.firmwareVariant.fixture, 'uiflow-workbench-v1');
    assert.equal(resolved.firmwareVariant.schedulerCandidate, 'qemu-tci-mmio-blocks-v1');
    assert.equal(resolved.accelerator, undefined);
  } else {
    assert.equal(resolved.clockDivisor, profile.clockDivisor, `${row.deviceId} cannot inherit another board's exact execution policy`);
    assert.deepEqual(resolved.accelerator, profile.accelerator);
    assert.equal(resolved.oneInsnPerTb, undefined); assert.equal(resolved.firmwareVariant, undefined);
  }
  assert.deepEqual(profile, qemu.profiles.find(profile => profile.deviceId === row.deviceId), 'resolution must not mutate the base registry');
  assert.deepEqual(resolveUIFlowWorkbenchProfile(profile, 'f'.repeat(64), registry), profile, 'unknown Flash cannot acquire programming readiness');
  const mismatch = structuredClone(profile); mismatch.reference.sha256 = '0'.repeat(64);
  assert.throws(() => resolveUIFlowWorkbenchProfile(mismatch, row.firmwareSHA256, registry), /no matching/);
}
const cores3 = qemu.profiles.find(profile => profile.deviceId === 'cores3');
const workbench = registry.profiles.find(row => row.deviceId === 'cores3');
const exactVariant = cores3.firmwareProfiles.find(row => row.firmwareSHA256 === workbench.firmwareSHA256);
const resolveWorkbench = (profile = cores3, workbenchRegistry = registry) => resolveUIFlowWorkbenchProfile(
  resolveQemuFirmwareProfile(profile, workbench.firmwareSHA256), workbench.firmwareSHA256, workbenchRegistry);
assert.deepEqual(exactVariant, {
  firmwareSHA256:'52f38f562f6e3749357a2ed4834efd72d16870046ea052f2f31691743cb5384d',
  profile:'cores3-wasm-uiflow-workbench-wallclock-candidate', clockDivisor:1,
  readyMarker:UIFLOW_WORKBENCH_READY, fixture:'uiflow-workbench-v1',
  sourceSHA256:'a109d9c11c09b4aa649e1a0a2d0929136fe7083f75bf2452e9c17b57f8b13ab0',
  schedulerCandidate:'qemu-tci-mmio-blocks-v1', oneInsnPerTb:true,
  requiredRuntimePatch:QEMU_ONE_INSN_RUNTIME_PATCH,
});
for (const [field, value] of [['sourceSHA256', '0'.repeat(64)], ['fixture', 'unrelated-fixture-v1'],
  ['readyMarker', 'UNRELATED_READY']]) {
  const copy = structuredClone(cores3);
  copy.firmwareProfiles.find(row => row.firmwareSHA256 === workbench.firmwareSHA256)[field] = value;
  assert.throws(() => resolveWorkbench(copy), /exact workbench source, fixture and ready binding/, `reject workbench ${field} mismatch`);
}
const changedMain = structuredClone(registry);
changedMain.profiles.find(row => row.deviceId === 'cores3').files['main.py'].sha256 = '0'.repeat(64);
assert.throws(() => resolveWorkbench(cores3, changedMain), /exact workbench source, fixture and ready binding/, 'main source registry cannot inherit a prior exact variant');
for (const other of cores3.firmwareProfiles.filter(row => row.firmwareSHA256 !== workbench.firmwareSHA256)) {
  const resolved = resolveQemuFirmwareProfile(cores3, other.firmwareSHA256);
  assert.throws(() => resolveUIFlowWorkbenchProfile(resolved, workbench.firmwareSHA256, registry), /exact workbench/, 'another exact image cannot acquire workbench readiness');
  assert.deepEqual(resolveUIFlowWorkbenchProfile(resolved, other.firmwareSHA256, registry), resolved, 'other images keep their separately bound policy');
  assert.notEqual(resolved.readyMarker, workbench.readyMarker);
}
const unknownCoreS3 = resolveQemuFirmwareProfile(cores3, 'f'.repeat(64));
assert.deepEqual(resolveUIFlowWorkbenchProfile(unknownCoreS3, 'f'.repeat(64), registry), unknownCoreS3);
assert.equal(unknownCoreS3.clockDivisor, 8); assert.equal(unknownCoreS3.oneInsnPerTb, undefined);
assert.equal(unknownCoreS3.firmwareVariant, undefined);
const conservative = resolveUIFlowWorkbenchProfile(cores3, workbench.firmwareSHA256, registry);
assert.equal(conservative.clockDivisor, 8); assert.equal(conservative.oneInsnPerTb, undefined);
const requiredRuntime = {source:{patches:[structuredClone(QEMU_ONE_INSN_RUNTIME_PATCH)]}};
validateQemuRuntimeRequirements(resolveWorkbench(), requiredRuntime);
for (const kind of ['missing', 'wrong', 'duplicate']) {
  const copy = structuredClone(requiredRuntime);
  if (kind === 'missing') copy.source.patches = [];
  if (kind === 'wrong') copy.source.patches[0].sha256 = '0'.repeat(64);
  if (kind === 'duplicate') copy.source.patches.push(structuredClone(QEMU_ONE_INSN_RUNTIME_PATCH));
  assert.throws(() => validateQemuRuntimeRequirements(resolveWorkbench(), copy), /required source patch/, `reject ${kind} runtime patch`);
}
for (const change of [variant => delete variant.requiredRuntimePatch, variant => variant.requiredRuntimePatch.sha256 = '0'.repeat(64),
  variant => variant.requiredRuntimePatch.path = 'patches/qemu-wasm-probe/unrelated.patch']) {
  const copy = structuredClone(cores3);
  change(copy.firmwareProfiles.find(row => row.firmwareSHA256 === workbench.firmwareSHA256));
  assert.throws(() => resolveWorkbench(copy), /runtime patch|one-instruction/, 'invalid patch identity fails before execution');
}
const stamplc=qemu.profiles.find(profile=>profile.deviceId==='stamplc');
const stamplcWorkbench=registry.profiles.find(row=>row.deviceId==='stamplc');
const stamplcVariant=stamplc.firmwareProfiles.find(row=>row.firmwareSHA256===stamplcWorkbench.firmwareSHA256);
const resolveStamPLC=(profile=stamplc,workbenchRegistry=registry)=>resolveUIFlowWorkbenchProfile(
  resolveQemuFirmwareProfile(profile,stamplcWorkbench.firmwareSHA256),stamplcWorkbench.firmwareSHA256,workbenchRegistry);
assert.deepEqual(stamplcVariant,{
  firmwareSHA256:'0b2b9b4f69dba03a7f764499555bdbf5d2e608c9c1c6496369e8d520186fcb5d',
  profile:'stamplc-wasm-uiflow-workbench-wallclock-oneinsn-candidate',clockDivisor:1,
  readyMarker:UIFLOW_WORKBENCH_READY,fixture:'uiflow-workbench-v1',
  sourceSHA256:'a109d9c11c09b4aa649e1a0a2d0929136fe7083f75bf2452e9c17b57f8b13ab0',
  schedulerCandidate:'qemu-tci-mmio-blocks-v1',oneInsnPerTb:true,requiredRuntimePatch:QEMU_ONE_INSN_RUNTIME_PATCH,
});
for(const [field,value] of [['sourceSHA256','0'.repeat(64)],['fixture','unrelated-fixture-v1'],['readyMarker','UNRELATED_READY']]){
  const copy=structuredClone(stamplc);
  copy.firmwareProfiles.find(row=>row.firmwareSHA256===stamplcWorkbench.firmwareSHA256)[field]=value;
  assert.throws(()=>resolveStamPLC(copy),/exact workbench source, fixture and ready binding/,`StamPLC rejects ${field} mismatch`);
}
const changedStamPLCMain=structuredClone(registry);
changedStamPLCMain.profiles.find(row=>row.deviceId==='stamplc').files['main.py'].sha256='0'.repeat(64);
assert.throws(()=>resolveStamPLC(stamplc,changedStamPLCMain),/exact workbench source, fixture and ready binding/);
const unknownStamPLC=resolveQemuFirmwareProfile(stamplc,'f'.repeat(64));
assert.deepEqual(resolveUIFlowWorkbenchProfile(unknownStamPLC,'f'.repeat(64),registry),unknownStamPLC);
assert.equal(unknownStamPLC.clockDivisor,1);assert.equal(unknownStamPLC.oneInsnPerTb,undefined);
assert.equal(unknownStamPLC.firmwareVariant,undefined);
const conservativeStamPLC=resolveUIFlowWorkbenchProfile(stamplc,stamplcWorkbench.firmwareSHA256,registry);
assert.equal(conservativeStamPLC.clockDivisor,1);assert.equal(conservativeStamPLC.oneInsnPerTb,undefined);
validateQemuRuntimeRequirements(resolveStamPLC(),requiredRuntime);
for(const kind of ['missing','wrong','duplicate']){
  const copy=structuredClone(requiredRuntime);
  if(kind==='missing')copy.source.patches=[];
  if(kind==='wrong')copy.source.patches[0].sha256='0'.repeat(64);
  if(kind==='duplicate')copy.source.patches.push(structuredClone(QEMU_ONE_INSN_RUNTIME_PATCH));
  assert.throws(()=>validateQemuRuntimeRequirements(resolveStamPLC(),copy),/required source patch/,`StamPLC rejects ${kind} runtime patch`);
}
for(const change of [variant=>delete variant.requiredRuntimePatch,variant=>variant.requiredRuntimePatch.sha256='0'.repeat(64),
  variant=>variant.requiredRuntimePatch.path='patches/qemu-wasm-probe/unrelated.patch']){
  const copy=structuredClone(stamplc);change(copy.firmwareProfiles.find(row=>row.firmwareSHA256===stamplcWorkbench.firmwareSHA256));
  assert.throws(()=>resolveStamPLC(copy),/runtime patch|one-instruction/);
}
assert.deepEqual(qemu, originalQemu, 'resolving exact, unknown or invalid firmware must not mutate the registry');
const candidate = qemu.profiles.find(row => row.admission === 'candidate');
if (candidate) assert.deepEqual(resolveUIFlowWorkbenchProfile(candidate, 'f'.repeat(64), registry), candidate, 'programming registry must not admit candidate boards');
for (const change of [copy => copy.profiles.push(copy.profiles[0]), copy => copy.profiles[0].files['main.py'].path = '../main.py',
  copy => copy.profiles[0].files['main.py'].bytes++, copy => copy.profiles[0].vfsSize = copy.profiles[0].flashBytes,
  copy => copy.readyMarker = 'unrelated']) {
  const copy = structuredClone(registry); change(copy); assert.throws(() => validateUIFlowWorkbenchRegistry(copy));
}

// Planning contracts execute no browser or firmware. The actual gate remains
// fail-fast and must collect an independent guest report for every planned row.
const publicRegistry={...qemu,profiles:qemu.profiles.filter(row=>row.admission==='public')};
const gateInputs={manifest:{publication_eligible:true,candidate_profiles:[]},
  config:{publication_eligible:true,browser_candidate_profiles:[],browser_wallclock_example:true},
  registry:publicRegistry,runtime:{compiled_profiles:publicRegistry.profiles.map(row=>row.deviceId)},workbenchRegistry:registry};
const plan=planPublicQemuGate(gateInputs),publicCount=publicRegistry.profiles.length;
const bodyCount=publicRegistry.profiles.some(row=>row.deviceId==='stackchan')?1:0;
const keyboardCount=publicRegistry.profiles.some(row=>row.deviceId==='cardputer-adv')?1:0;
assert.equal(plan.publication_eligible,true);assert.equal(plan.cases.length,publicCount*3+1+bodyCount+keyboardCount);
assert.deepEqual(plan.cases.slice(0,9).map(row=>[row.lane,row.device]),[
  ['uiflow-editor','atom-matrix'],['uiflow-buttons','atom-matrix'],
  ['uiflow-editor','stickc-plus'],['uiflow-buttons','stickc-plus'],
  ['uiflow-editor','cardputer-adv'],['uiflow-buttons','cardputer-adv'],
  ['cardputer-keyboard','cardputer-adv'],
  ['uiflow-editor','cores3'],['uiflow-buttons','cores3'],
]);
assert.ok(plan.cases.slice(0,publicCount*2+bodyCount+keyboardCount).every(row=>row.lane!=='fixed'));
assert.ok(plan.cases.slice(publicCount*2+bodyCount+keyboardCount).every(row=>row.lane==='fixed'));
assert.deepEqual(plan.cases.filter(row=>row.lane==='stackchan-body-touch').map(row=>[row.device,row.script]),
  [['stackchan','test_public_stackchan_body_touch_guest.mjs']]);
assert.deepEqual(plan.cases.filter(row=>row.lane==='cardputer-keyboard').map(row=>[row.device,row.script]),
  [['cardputer-adv','test_public_uiflow_cardputer_keyboard_guest.mjs']]);
assert.equal(new Set(plan.cases.map(row=>[row.lane,row.device,row.example||''].join('/'))).size,plan.cases.length);
for(const row of publicRegistry.profiles){
  const board=plan.cases.filter(item=>item.device===row.deviceId);
  assert.equal(board[0].lane,'uiflow-editor');assert.equal(board[1].lane,'uiflow-buttons');
}
for(const phase of PUBLIC_QEMU_GATE_PHASES.filter(phase=>phase!=='all')){
  const diagnostic=planPublicQemuGate({...gateInputs,phase});assert.equal(diagnostic.publication_eligible,false);
  assert.equal(diagnostic.cases.length,phase==='uiflow'?publicCount*2+bodyCount+keyboardCount:phase==='fixed'?publicCount+1:phase==='buttons'?publicCount+bodyCount+keyboardCount:publicCount);
  assert.throws(()=>planPublicQemuGate({...gateInputs,phase,requireAll:true}),/Publication requires/);
}
const subset=planPublicQemuGate({...gateInputs,phase:'uiflow',devices:['cores3','atom-matrix']});
assert.equal(subset.publication_eligible,false);assert.equal(subset.cases.length,4);
assert.throws(()=>planPublicQemuGate({...gateInputs,devices:['cores3'],requireAll:true}),/Publication requires/);
assert.throws(()=>planPublicQemuGate({...gateInputs,phase:'silent-subset'}),/Unknown/);
assert.throws(()=>planPublicQemuGate({...gateInputs,devices:['not-public']}),/Unadmitted/);
assert.throws(()=>planPublicQemuGate({...gateInputs,devices:['cores3','cores3']}),/Duplicate/);
for(const change of [
  copy=>copy.manifest.publication_eligible=false,
  copy=>copy.config.browser_candidate_profiles=['cores3'],
  copy=>copy.config.browser_wallclock_example=false,
  copy=>copy.registry.profiles[0].admission='candidate',
  copy=>copy.runtime.compiled_profiles=[],
  copy=>copy.workbenchRegistry.profiles.pop(),
]){const copy=structuredClone(gateInputs);change(copy);assert.throws(()=>planPublicQemuGate(copy));}
assert.deepEqual(qemu,originalQemu,'gate planning cannot mutate the canonical registry');

// Callback-only scheduler simulations. No browser, firmware or child process.
assert.equal(publicQemuGateWorkers(),1);assert.equal(publicQemuGateWorkers('1'),1);assert.equal(publicQemuGateWorkers('2'),2);
assert.equal(publicQemuGateWorkers(undefined,{ci:true}),1);
assert.throws(()=>publicQemuGateWorkers('2',{ci:true}),/CI requires/);
for(const value of ['',null,'0','3','1.5','2.0','01',' 2','invalid',0,1,2,NaN])
  assert.throws(()=>publicQemuGateWorkers(value),/exactly 1 or 2/);
const caseKey=item=>[item.lane,item.device,item.example||''].join('/');
const sequential=[];
const single=await schedulePublicQemuGate(plan.cases,{runCase:async item=>{sequential.push(caseKey(item));return {status:'PASS'};}});
assert.equal(single.workers,1);assert.equal(single.max_active_children,1);assert.equal(single.all_passed,true);
assert.equal(single.first_failure,null);assert.deepEqual(sequential,plan.cases.map(caseKey),'default1 retains the existing complete order');
const liveDevices=new Set(),parallelOrder=[],uiCount=plan.cases.filter(item=>item.lane!=='fixed').length;
let live=0,maxLive=0,uiComplete=0;
const dual=await schedulePublicQemuGate(plan.cases,{workers:2,runCase:async item=>{
  assert.ok(!liveDevices.has(item.device),'same device cannot run two cases concurrently');
  if(item.lane==='fixed')assert.equal(uiComplete,uiCount,'all UIFlow groups must finish before fixed examples');
  liveDevices.add(item.device);live++;maxLive=Math.max(maxLive,live);parallelOrder.push(caseKey(item));
  await new Promise(resolve=>setImmediate(resolve));
  if(item.lane!=='fixed')uiComplete++;
  liveDevices.delete(item.device);live--;return {status:'PASS'};
}});
assert.equal(dual.all_passed,true);assert.equal(dual.max_active_children,2);assert.equal(maxLive,2);assert.equal(live,0);
assert.equal(dual.cases.length,plan.cases.length);assert.ok(dual.cases.every(row=>row.status==='PASS'));
for(const profile of publicRegistry.profiles)assert.deepEqual(
  parallelOrder.filter(key=>key.split('/')[1]===profile.deviceId),
  plan.cases.filter(item=>item.device===profile.deviceId).map(caseKey),'editor/buttons/extra and fixed-example order stays local to each device');
for(const workers of [0,3,1.5,'2'])await assert.rejects(schedulePublicQemuGate(plan.cases,{workers,runCase:async()=>({status:'PASS'})}),/workers must be/);
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {resolve,promise};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const failureCases=[
  {device:'first',lane:'uiflow-editor'}, {device:'first',lane:'uiflow-buttons'},
  {device:'second',lane:'uiflow-editor'}, {device:'second',lane:'uiflow-buttons'},
  {device:'third',lane:'uiflow-editor'}, {device:'first',lane:'fixed'},
];
const firstChild=deferred(),otherChild=deferred(),failureStarts=[];let failureSettled=false;
const draining=schedulePublicQemuGate(failureCases,{workers:2,runCase:async item=>{
  failureStarts.push(caseKey(item));return item.device==='first'?firstChild.promise:otherChild.promise;
}}).then(value=>{failureSettled=true;return value;});
await tick();assert.deepEqual(failureStarts,['uiflow-editor/first/','uiflow-editor/second/']);
firstChild.resolve({status:'FAIL',error:'first actual failure'});await tick();
assert.equal(failureSettled,false,'one FAIL cannot finish the parent while another child still owns its cleanup');
assert.equal(failureStarts.length,2,'no queued same-board or new-device case can start after FAIL');
otherChild.resolve({status:'FAIL',error:'later failure'});
const failed=await draining;
assert.equal(failed.all_passed,false);assert.equal(failed.first_failure.error,'first actual failure');
assert.equal(failed.cases.filter(row=>row.status==='FAIL').length,2);
assert.equal(failed.cases.filter(row=>row.status==='NOT RUN').length,4);
assert.ok(failed.cases.filter(row=>row.status==='NOT RUN').every(row=>row.not_run_reason));
// A known nonzero child exit stops dispatch before its report is read, while
// both callbacks are still awaited for report/cleanup finalization.
const reportFence=deferred(),peerFence=deferred();let announceFailure,earlySettled=false,earlyStarts=0;
const early=schedulePublicQemuGate(failureCases,{workers:2,runCase:async (item,{noteFailure})=>{
  earlyStarts++;
  if(item.device==='first'){
    announceFailure=()=>noteFailure(new Error('child nonzero exit'));await reportFence.promise;
    return {status:'FAIL',error:'child report retained'};
  }
  await peerFence.promise;return {status:'PASS'};
}}).then(value=>{earlySettled=true;return value;});
await tick();assert.equal(earlyStarts,2);announceFailure();peerFence.resolve();await tick();
assert.equal(earlySettled,false);assert.equal(earlyStarts,2,'a known exit failure stops dispatch while its report is retained');
reportFence.resolve();const earlyResult=await early;
assert.equal(earlyResult.first_failure.error,'child nonzero exit');assert.equal(earlyResult.cases[0].error,'child report retained');
assert.equal(earlyResult.cases.filter(row=>row.status==='NOT RUN').length,4);
const launchFence=deferred();let launchStarts=0,launchSettled=false;
const launch=schedulePublicQemuGate(failureCases,{workers:2,runCase:(item,{noteFailure})=>{
  launchStarts++;noteFailure(new Error('synchronous launch failure'));return launchFence.promise;
}}).then(value=>{launchSettled=true;return value;});
await tick();assert.equal(launchStarts,1,'a synchronous failure announcement blocks even the second initial dispatch');
assert.equal(launchSettled,false,'launch/close handling remains awaited');
launchFence.resolve({status:'FAIL',error:'synchronous launch failure'});
assert.equal((await launch).first_failure.error,'synchronous launch failure');
const thrown=await schedulePublicQemuGate(failureCases,{runCase:async()=>{throw new Error('callback rejected');}});
assert.equal(thrown.all_passed,false);assert.equal(thrown.first_failure.error,'callback rejected');
assert.equal(thrown.cases.filter(row=>row.status==='NOT RUN').length,5);

const inherited={M5_QEMU_DEVICE:'not-selected',M5_QEMU_EXAMPLE:'wallclock-candidate',M5_UIFLOW_SMOKE_ONLY:'1',
  M5_PUBLIC_URL:'https://example.test/other-export/',M5_QEMU_UPLOAD:'other-firmware.bin',M5_QEMU_CLOCK_DIVISOR:'8',
  M5_QEMU_FRAME_DIAGNOSTIC:'1',M5_QEMU_BUTTON_HOLD_MS:'1000',M5_CARDPUTER_KEYBOARD_IRQ:'0',M5_WASM_CHROME:'/explicit/chrome',M5_CHROME:'/different/chrome',
  M5_WASM_NODE_MODULES:'/test/node_modules',M5_PUBLIC_BASE_PATH:'/showcase/',M5_QEMU_READY_TIMEOUT_MS:'600000',M5_WASM_GPU:'hardware'};
for(const item of plan.cases){
  const env=publicQemuGateChildEnvironment(inherited,item,{site:'/review/site',output:'/review/output'});
  for(const key of ['M5_UIFLOW_SMOKE_ONLY','M5_PUBLIC_URL','M5_QEMU_UPLOAD','M5_QEMU_CLOCK_DIVISOR','M5_QEMU_FRAME_DIAGNOSTIC'])
    assert.equal(env[key],'',`${item.lane} must not inherit ${key}`);
  assert.equal(env.M5_QEMU_DEVICE,item.device);assert.equal(env.M5_QEMU_EXAMPLE,item.example||'');
  assert.equal(env.M5_QEMU_BUTTON_HOLD_MS,'250','a longer inherited pulse cannot weaken gate input coverage');
  assert.equal(env.M5_CARDPUTER_KEYBOARD_IRQ,item.lane==='cardputer-keyboard'?'1':'','the real IRQ observer must not be skipped or inherited by another lane');
  assert.equal(env.M5_WASM_CHROME,'/explicit/chrome');assert.equal(env.M5_CHROME,'/explicit/chrome');
  assert.equal(env.M5_PUBLIC_SITE,'/review/site');assert.equal(env.M5_PUBLIC_QEMU_OUT,'/review/output');
  for(const key of ['M5_WASM_NODE_MODULES','M5_PUBLIC_BASE_PATH','M5_QEMU_READY_TIMEOUT_MS','M5_WASM_GPU'])assert.equal(env[key],inherited[key]);
}
assert.equal(inherited.M5_QEMU_BUTTON_HOLD_MS,'1000','child environment normalization cannot mutate its caller');
const chromeFallback=publicQemuGateChildEnvironment({M5_CHROME:'/fallback/chrome'},plan.cases[0],{site:'/site',output:'/out'});
assert.equal(chromeFallback.M5_WASM_CHROME,'/fallback/chrome');assert.equal(chromeFallback.M5_CHROME,'/fallback/chrome');

// Source/export receipt contracts use each runner's actual report layout.
// These synthetic metadata fixtures execute no guest or input controller.
const binding={workbenchRegistry:registry,wasmSHA256:'a'.repeat(64),siteManifestSHA256:'b'.repeat(64),testScriptSHA256:'c'.repeat(64)};
for(const item of plan.cases){
  const expected=registry.profiles.find(row=>row.deviceId===item.device);
  const receipt={deviceId:item.device,firmwareSha256:expected.firmwareSHA256,wasmSha256:binding.wasmSHA256};
  const result={provenance:{site_manifest_sha256:binding.siteManifestSHA256,
    test_script:{path:'platform/tests/'+item.script,sha256:binding.testScriptSHA256},
    runtime_assets:{'qemu-system-xtensa.wasm':{sha256:binding.wasmSHA256}}},smoke_only:false};
  if(item.lane==='cardputer-keyboard')result.initial={evidence:{receipt}};
  else if(item.lane==='uiflow-buttons')result.running={receipt};
  else if(item.lane!=='fixed')result.initial={receipt};
  validatePublicQemuGateResult(item,result,binding);
  for(const change of [copy=>copy.provenance.site_manifest_sha256='0'.repeat(64),
    copy=>copy.provenance.test_script.sha256='0'.repeat(64),copy=>copy.provenance.test_script.path='platform/tests/other.mjs',
    copy=>copy.provenance.runtime_assets['qemu-system-xtensa.wasm'].sha256='0'.repeat(64)]){
    const copy=structuredClone(result);change(copy);assert.throws(()=>validatePublicQemuGateResult(item,copy,binding));
  }
  if(item.lane!=='fixed')for(const field of ['deviceId','firmwareSha256','wasmSha256']){
    const copy=structuredClone(result),actual=item.lane==='cardputer-keyboard'?copy.initial.evidence.receipt
      :item.lane==='uiflow-buttons'?copy.running.receipt:copy.initial.receipt;
    actual[field]=field==='deviceId'?'another-device':'0'.repeat(64);
    assert.throws(()=>validatePublicQemuGateResult(item,copy,binding));
  }
  if(item.lane==='cardputer-keyboard'){
    const wrongLayout=structuredClone(result);wrongLayout.initial={receipt};
    assert.throws(()=>validatePublicQemuGateResult(item,wrongLayout,binding),'keyboard must use its actual initial.evidence.receipt');
  }
  if(item.lane==='uiflow-editor'){
    const smoke=structuredClone(result);smoke.smoke_only=true;
    assert.throws(()=>validatePublicQemuGateResult(item,smoke,binding),/full editor/);
  }
}

const args = new Map(); for (let i = 2; i < process.argv.length; i += 2) args.set(process.argv[i], process.argv[i + 1]);
if (args.get('--runtime') && args.get('--firmware-cache')) {
  const runtime = path.resolve(args.get('--runtime')), cache = path.resolve(args.get('--firmware-cache'));
  const manifest = JSON.parse(await fs.readFile(path.join(runtime, 'manifest.json')));
  const {default:factory} = await import(pathToFileURL(path.join(runtime, manifest.assets.module.path)).href);
  const engine = await factory({wasmBinary:await fs.readFile(path.join(runtime, manifest.assets.wasm.path)), print(){}, printErr(){}});
  for (const device of (args.get('--devices') || 'cores3,stickc-plus,atom-matrix').split(',')) {
    const row = registry.profiles.find(row => row.deviceId === device), profile = qemu.profiles.find(row => row.deviceId === device);
    assert.ok(row && profile);
    const base = await fs.readFile(path.join(cache, row.baseSHA256 + '.bin'));
    const result = await composeUIFlowWorkbenchImage({profile, registry, baseBytes:base, engine});
    assert.equal(result.sha256, row.firmwareSHA256); assert.equal(result.provenance.source_readback_verified, true);
    assert.deepEqual(result.bytes.slice(0, row.vfsOffset), new Uint8Array(base.subarray(0, row.vfsOffset)));
    assert.deepEqual(result.bytes.slice(row.vfsOffset + row.vfsSize, base.length), new Uint8Array(base.subarray(row.vfsOffset + row.vfsSize)));
    assert.ok(result.bytes.slice(base.length).every(byte => byte === 255), 'Flash padding must remain erased');
    const bad = Buffer.from(base); bad[0] ^= 1;
    await assert.rejects(composeUIFlowWorkbenchImage({profile, registry, baseBytes:bad, engine}), /official base SHA256/);
    const changed = structuredClone(registry); changed.profiles.find(row => row.deviceId === device).files['main.py'].text = 'print("altered")\n';
    changed.profiles.find(row => row.deviceId === device).files['main.py'].bytes = new TextEncoder().encode('print("altered")\n').length;
    await assert.rejects(composeUIFlowWorkbenchImage({profile, registry:changed, baseBytes:base, engine}), /startup source SHA256/);
    const abort = new AbortController(); abort.abort();
    await assert.rejects(composeUIFlowWorkbenchImage({profile, registry, baseBytes:base, engine, signal:abort.signal}), /abort/i);
    console.log(`${device}: real LittleFS WASM composition and negative controls PASS; guest execution NOT RUN`);
  }
}
console.log('UIFlow programming firmware contracts PASS. Firmware guest execution: NOT RUN.');
