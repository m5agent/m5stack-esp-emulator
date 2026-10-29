// Host adapter contracts only. Mock downloads/messages never execute a guest.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PublicQemuRuntime,browserQemuHistory} from '../web/public-qemu-runtime.js';
import {getQemuBrowserProfile,validateQemuFirmware} from '../web/public-qemu-profiles.js';
import {sha256Bytes} from '../web/sha256.js';

const root='https://example.test/showcase/';
const profiles=JSON.parse(await readFile(new URL('../web/qemu-browser-profiles.json',import.meta.url),'utf8'));
const coreProfile=getQemuBrowserProfile('cores3',profiles);
const roms=new Map(profiles.profiles.flatMap(profile=>profile.roms).map(rom=>[rom.url,rom]));
const romSha='b5c7090cc22efce51c1323cef31ca96fcd673a5b1d1b1017e219d393f2659913';
const manifest={schema_version:1,engine:'qemu-wasm',source:{commit:'40edccac415693c5130f91c01d84176ae6008566'},profiles:['cores3'],compiled_profiles:profiles.profiles.map(profile=>profile.deviceId),execution_profile:{id:'cores3-wasm-vm-div8'},build:{kind:'contract-fixture'},
  assets:{javascript:{path:'qemu-system-xtensa.js',sha256:'1'.repeat(64),bytes:8},wasm:{path:'qemu-system-xtensa.wasm',sha256:'2'.repeat(64),bytes:8},worker:{path:'qemu-system-xtensa.worker.js',sha256:'3'.repeat(64),bytes:8}},
  required_rom:{url:'https://example.test/rom.bin',sha256:romSha,bytes:393216}};
function firmware(profile=coreProfile){const bytes=new Uint8Array(0x10100),view=new DataView(bytes.buffer);for(const at of [profile.bootloaderOffset,0x10000]){bytes[at]=0xe9;bytes[at+1]=1;view.setUint16(at+12,profile.imageChipId,true);view.setUint32(at+28,4,true);}view.setUint16(0x8000,0x50aa,true);view.setUint32(0x8004,0x10000,true);view.setUint32(0x8008,0x1000,true);return bytes.buffer;}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function until(predicate){for(let i=0;i<100;i++){if(predicate())return;await new Promise(resolve=>setTimeout(resolve,5));}throw new Error('Contract phase did not arrive');}
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
function storage(){const values=new Map();return {getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value)};}
let options={},frames=[];
const mockDocument={
  createElement(tag){assert.equal(tag,'iframe');const config={...options};const frame={removed:false,style:{},attributes:new Map(),setAttribute(name,value){this.attributes.set(name,value);},remove(){this.removed=true;this.channel?.close();},contentWindow:{postMessage(message,origin,ports){
    assert.equal(message.type,'m5-qemu-connect');assert.equal(origin,'https://example.test');assert.equal(ports.length,1);
    if(config.throwConnect)throw new Error('connect clone failure');
    const port=ports[0];frame.channel=port;frame.calls=[];
    port.onmessage=({data})=>{
      frame.calls.push(data);
      if(config.ignore?.includes(data.op))return;
      if(data.op==='start'&&config.rejectStart){port.postMessage({id:data.id,error:'contract start rejection'});return;}
      if(data.op==='dispose'&&config.rejectDispose){
        if(config.failedEngineOnDispose)frame.contentWindow.m5QemuEngineOwnership=config.failedEngineOnDispose;
        port.postMessage({id:data.id,error:'contract dispose rejection'});return;
      }
      if(data.op==='start')frame.profile=data.value.profile;
      port.postMessage({id:data.id,value:data.op==='input'&&data.value.type==='pir'?{motion:data.value.motion}:data.op==='dispose'?{workersRemaining:0,...(config.engineDisposal?{enginePlacement:'dedicated-worker-v1',engineWorkersAtAcknowledgement:1,selfCloseAfterAcknowledgement:true}:{})}:undefined});
      if(data.op==='start')queueMicrotask(()=>port.postMessage({type:'ready',value:{shared:true,crossOriginIsolated:true,memoryBytes:268435456}}));
      if(data.op==='quit')queueMicrotask(()=>port.postMessage({type:'exit',value:{code:config.exitCode??0}}));
      if(data.op==='frame'){const {width,height}=frame.profile.display;port.postMessage({type:'frame',value:{width,height,pixels:new Uint8Array(width*height*2),format:'rgb565le',source:'contract-fixture'}});}
    };
    port.start();if(!config.ignoreConnect)port.postMessage({type:'connected',value:{}});
  }}};
  if(config.engineDisposal)frame.contentWindow.m5QemuEngineOwnership={engineWorkersCreated:1,engineOwnerLive:false,engineCloseNotificationReceived:true,engineFallbackTerminations:0,enginePortTransferred:true};
  frames.push(frame);return frame;},
  body:{append(frame){if(!options.ignoreLoad)queueMicrotask(()=>frame.onload?.());}},
};
const oldDocument=Object.getOwnPropertyDescriptor(globalThis,'document'),oldIsolation=Object.getOwnPropertyDescriptor(globalThis,'crossOriginIsolated');
Object.defineProperty(globalThis,'document',{value:mockDocument,configurable:true});Object.defineProperty(globalThis,'crossOriginIsolated',{value:true,configurable:true});
const unhandled=[];const unhandledListener=error=>unhandled.push(error);process.on('unhandledRejection',unhandledListener);
const runtimes=[];
function create(overrides={}){
  const downloads=[],states=[],errors=[];
  const runtime=new PublicQemuRuntime({root,profiles,storage:storage(),requestTimeout:100,onState:value=>states.push(value.status),onError:error=>errors.push(error.message),
    fetchImpl:async function(url){assert.equal(this,undefined,'native fetch receiver must stay unbound');assert.ok([root+'platform/runtime/qemu/runtime.json',root+'platform/web/qemu-browser-profiles.json'].includes(url));return new Response(JSON.stringify(url.endsWith('qemu-browser-profiles.json')?profiles:manifest));},
    downloadImpl:async(url,config)=>{downloads.push({url,...config});const size=roms.get(url)?.bytes??8;return {bytes:new ArrayBuffer(size),size,sha256:config.expectedSha256};},...overrides});
  runtimes.push(runtime);return {runtime,downloads,states,errors};
}
try {
  const normal=create();await normal.runtime.start({device:'cores3',firmware:firmware()});await until(()=>normal.runtime.lastFrame);
  assert.equal(normal.runtime.observe().status,'running');assert.equal(normal.runtime.observe().persistentStorage,false);
  assert.equal(normal.runtime.receipt.clockDivisor,8);assert.equal(normal.downloads.length,4);assert.equal(normal.downloads[3].expectedSha256,romSha);
  assert.equal(normal.runtime.receipt.firmwareVariant,null,'an unknown complete Flash hash stays on the baseline clock profile');
  const startMessage=frames.at(-1).calls.find(row=>row.op==='start');
  assert.equal(startMessage.value.profile.deviceId,'cores3');assert.deepEqual(startMessage.value.roms.map(({name,sha256})=>({name,sha256})),coreProfile.roms.map(({name,sha256})=>({name,sha256})));
  assert.equal(startMessage.value.roms[0].bytes.byteLength,coreProfile.roms[0].bytes);assert.equal(startMessage.value.rom,undefined,'the old singular-ROM protocol must not leak through');
  assert.ok(normal.downloads.every(row=>row.signal instanceof AbortSignal&&typeof row.fetchImpl==='function'));
  assert.equal((await normal.runtime.input({type:'pir',motion:true})).result.motion,true);
  await normal.runtime.input({type:'touch',x:160,y:184,down:true});
  const beforeUart=frames.at(-1).calls.length;await assert.rejects(normal.runtime.input({type:'uart',text:'hello\n'}),/not admitted/);assert.equal(frames.at(-1).calls.length,beforeUart,'unadmitted UART cannot cross the private port');
  await assert.rejects(normal.runtime.input({type:'touch',x:320,y:1,down:true}));await assert.rejects(normal.runtime.input({type:'uart',text:'a'.repeat(129)}));
  await normal.runtime.pause();assert.equal(normal.runtime.status,'paused');await normal.runtime.input({type:'touch',x:160,y:184,down:false});
  await assert.rejects(normal.runtime.input({type:'pir',motion:false}));await normal.runtime.resume();assert.equal(normal.runtime.status,'running');
  const generation=normal.runtime.generation,frameCount=normal.runtime.sequence;
  normal.runtime.receive({type:'frame',value:{width:1,height:1,pixels:new Uint8Array(2)}},generation-1);assert.equal(normal.runtime.sequence,frameCount);
  await normal.runtime.stop();assert.equal(normal.runtime.pending.size,0);assert.equal(normal.runtime.waiters.size,0);assert.equal(normal.runtime.iframe,null);assert.equal(normal.runtime.port,null);
  assert.equal(normal.runtime.cleanupResult.exitCode,0);assert.equal(normal.runtime.cleanupResult.explicitWorkerDisposal,true);assert.equal(browserQemuHistory(normal.runtime.storage).length,1);assert.ok(normal.runtime.evidence().last_frame.sha256);

  // A caller may collect the private acknowledgement before removing the
  // iframe to observe actual Worker close. stop() reuses that receipt instead
  // of sending a second command to the now-closed engine port.
  options={engineDisposal:true};const dedicated=create();await dedicated.runtime.start({device:'cores3',firmware:firmware()});
  await dedicated.runtime.pause();const dedicatedFrame=frames.at(-1);
  const disposal=await dedicated.runtime.ask('dispose');assert.equal(disposal.engineWorkersAtAcknowledgement,1);
  await dedicated.runtime.stop();
  assert.equal(dedicatedFrame.calls.filter(row=>row.op==='dispose').length,1);
  assert.equal(dedicated.runtime.cleanupResult.disposal.enginePlacement,'dedicated-worker-v1');
  assert.equal(dedicated.runtime.cleanupResult.engineOwnership.engineCloseNotificationReceived,true);
  assert.equal(dedicated.runtime.cleanupResult.engineOwnership.engineFallbackTerminations,0);
  assert.equal(dedicatedFrame.removed,true);

  const failedEngine={engineWorkersCreated:1,engineOwnerLive:false,engineCloseNotificationReceived:false,
    engineFallbackTerminations:1,enginePortTransferred:true};
  options={};const pausedFailure=create();await pausedFailure.runtime.start({device:'cores3',firmware:firmware()});
  await pausedFailure.runtime.pause();const pausedFailureFrame=frames.at(-1),beforeFailureCalls=pausedFailureFrame.calls.length;
  pausedFailureFrame.contentWindow.m5QemuEngineOwnership=failedEngine;
  await until(()=>pausedFailure.runtime.status==='stopped');
  assert.equal(pausedFailure.errors.length,1);assert.match(pausedFailure.errors[0],/执行线程异常停止/);
  assert.ok(pausedFailure.states.includes('error'),'a paused engine failure must immediately enter the error path');
  assert.equal(pausedFailureFrame.calls.length,beforeFailureCalls,'a dead engine cannot receive frame/quit/dispose commands');
  assert.deepEqual(pausedFailure.runtime.cleanupResult.engineOwnership,failedEngine);
  assert.equal(pausedFailure.runtime.cleanupResult.engineOwnershipStage,'before-iframe-removal');
  assert.equal(pausedFailure.runtime.cleanupResult.explicitWorkerDisposal,false);
  assert.equal(pausedFailure.runtime.cleanupResult.disposal,null);
  assert.equal(browserQemuHistory(pausedFailure.runtime.storage)[0].cleanup.engineOwnership.engineFallbackTerminations,1);
  assert.equal(pausedFailureFrame.removed,true);

  options={rejectDispose:true,failedEngineOnDispose:failedEngine};const rejectedDispose=create();
  await rejectedDispose.runtime.start({device:'cores3',firmware:firmware()});await rejectedDispose.runtime.pause();
  const rejectedDisposeFrame=frames.at(-1),beforeRejectedStop=rejectedDisposeFrame.calls.length;
  await rejectedDispose.runtime.stop();
  assert.deepEqual(rejectedDisposeFrame.calls.slice(beforeRejectedStop).map(row=>row.op),['quit','dispose']);
  assert.deepEqual(rejectedDispose.runtime.cleanupResult.engineOwnership,failedEngine,'failed dispose must retain the latest owner failure without an acknowledgement');
  assert.equal(rejectedDispose.runtime.cleanupResult.engineOwnershipStage,'before-iframe-removal');
  assert.equal(rejectedDispose.runtime.cleanupResult.disposal,null);
  assert.equal(rejectedDispose.runtime.cleanupResult.explicitWorkerDisposal,false);
  assert.equal(rejectedDisposeFrame.removed,true);

  options={};const frameSources=create({fetchImpl:async(url)=>{assert.equal(url,root+'platform/runtime/qemu/runtime.json');return new Response(JSON.stringify({...manifest,frame_transport:{kind:'shared-rgb565-v1'}}));}});
  await frameSources.runtime.start({device:'cores3',firmware:firmware()});await until(()=>frameSources.runtime.lastFrame);await frameSources.runtime.pause();
  const sourceGeneration=frameSources.runtime.generation,sourceFrameCount=frameSources.runtime.sequence;
  const sharedPixels=new Uint8Array([0x00,0xf8,0xe0,0x07]);
  frameSources.runtime.receive({type:'frame',value:{width:2,height:1,pixels:sharedPixels,format:'rgb565le',source:'qemu-display-surface-shared',sourceSequence:42,sourceUpdates:7}},sourceGeneration);
  const sharedEvidence=frameSources.runtime.evidence();
  assert.equal(sharedEvidence.receipt.frameTransport,'shared-rgb565-v1');
  assert.deepEqual(sharedEvidence.last_frame,{width:2,height:1,sequence:sourceFrameCount+1,format:'rgb565le',source:'qemu-display-surface-shared',source_sequence:42,source_updates:7,sha256:sha256Bytes(sharedPixels),pixels:Array.from(sharedPixels)},'shared frame evidence must retain the actual source counters as snake_case fields');
  const diagnosticPixels=new Uint8Array([0x1f,0x00,0xff,0xff]);
  frameSources.runtime.receive({type:'frame',value:{width:2,height:1,pixels:diagnosticPixels,format:'rgb565le',source:'qmp-screendump'}},sourceGeneration);
  const diagnosticEvidence=frameSources.runtime.evidence();
  assert.equal(diagnosticEvidence.receipt.frameTransport,'shared-rgb565-v1','the configured transport remains independent of the actual diagnostic frame source');
  assert.deepEqual(diagnosticEvidence.last_frame,{width:2,height:1,sequence:sourceFrameCount+2,format:'rgb565le',source:'qmp-screendump',source_sequence:null,source_updates:null,sha256:sha256Bytes(diagnosticPixels),pixels:Array.from(diagnosticPixels)},'a QMP diagnostic frame must not inherit the previous shared frame source or counters');
  await frameSources.runtime.stop();

  options={};const remoteProfiles=create({profiles:undefined});await remoteProfiles.runtime.start({device:'cores3',firmware:firmware()});assert.equal(remoteProfiles.runtime.profile.board,coreProfile.board);await remoteProfiles.runtime.stop();
  // Bind the real canonical variant metadata to this synthetic host-only Flash.
  // This checks adapter resolution without depending on an ignored firmware cache.
  const variantProfiles=structuredClone(profiles),variantProfile=variantProfiles.profiles.find(profile=>profile.deviceId==='cores3');
  const variant=variantProfile.firmwareProfiles[0];variant.firmwareSHA256=sha256Bytes(validateQemuFirmware(firmware(),coreProfile));
  const matched=create({profiles:variantProfiles});await matched.runtime.start({device:'cores3',firmware:firmware()});
  assert.equal(matched.runtime.receipt.profile,variant.profile);assert.equal(matched.runtime.receipt.clockDivisor,1);
  assert.deepEqual(matched.runtime.receipt.firmwareVariant,variant);assert.deepEqual(frames.at(-1).profile.firmwareVariant,variant);
  assert.equal(frames.at(-1).profile.readyFirmwareSHA256,variant.firmwareSHA256);await matched.runtime.stop();
  const override=create();await assert.rejects(override.runtime.start({device:'cores3',firmware:firmware(),clockDivisor:1}),/候选/);
  assert.equal(override.downloads.length,0,'public callers cannot override the clock for an unknown firmware hash');
  const core2=getQemuBrowserProfile('core2',profiles,{allowCandidateProfiles:true});
  const candidateProfiles=structuredClone(profiles);candidateProfiles.profiles.find(profile=>profile.deviceId==='core2').admission='candidate';
  const candidate=create({profiles:candidateProfiles,allowCandidateProfiles:true});await candidate.runtime.start({device:'core2',firmware:firmware(core2)});
  assert.equal(candidate.runtime.receipt.roms.length,2);assert.equal(candidate.runtime.receipt.deviceId,'core2');
  await candidate.runtime.input({type:'touch',x:160,y:184,down:true});await assert.rejects(candidate.runtime.input({type:'button',id:'a',down:true}),/not admitted/);await assert.rejects(candidate.runtime.input({type:'pir',motion:true}));await candidate.runtime.stop();
  const unadmitted=create({profiles:candidateProfiles});await assert.rejects(unadmitted.runtime.start({device:'core2',firmware:firmware(core2)}),/准入/);assert.equal(unadmitted.downloads.length,0);

  const profileFetch=deferred(),profileCancel=new AbortController();let profileSignal;
  const profileLoading=create({profiles:undefined,fetchImpl:async(url,config)=>{assert.ok(url.endsWith('qemu-browser-profiles.json'));profileSignal=config.signal;return profileFetch.promise;}});
  const profileStart=profileLoading.runtime.start({device:'cores3',firmware:firmware(),signal:profileCancel.signal});profileStart.catch(()=>{});await until(()=>profileSignal);
  profileCancel.abort();await until(()=>profileLoading.runtime.status==='stopped');assert.equal(profileSignal.aborted,true);
  profileFetch.resolve(new Response(JSON.stringify(profiles)));await assert.rejects(profileStart,{name:'AbortError'});assert.equal(profileLoading.downloads.length,0);assert.equal(profileLoading.runtime.profile,null);

  const registryRequests=[];
  const concurrent=create({profiles:undefined,fetchImpl:async(url,config)=>{if(url.endsWith('qemu-browser-profiles.json')){const request=deferred();registryRequests.push({...request,signal:config.signal});return request.promise;}assert.ok(url.endsWith('runtime.json'));return new Response(JSON.stringify(manifest));}});
  const older=concurrent.runtime.start({device:'cores3',firmware:firmware()});older.catch(()=>{});
  const newer=concurrent.runtime.start({device:'cores3',firmware:firmware()});newer.catch(()=>{});await until(()=>registryRequests.length===2);
  registryRequests[1].resolve(new Response(JSON.stringify(profiles)));await newer;const currentSession=concurrent.runtime.sessionId,currentReceipt=concurrent.runtime.receipt;
  registryRequests[0].resolve(new Response(JSON.stringify(profiles)));await assert.rejects(older,{name:'AbortError'});
  assert.equal(concurrent.runtime.status,'running');assert.equal(concurrent.runtime.sessionId,currentSession);assert.equal(concurrent.runtime.receipt,currentReceipt);assert.equal(concurrent.downloads.length,4);await concurrent.runtime.stop();

  options={ignoreLoad:true};const loading=create(),cancel=new AbortController();const load=loading.runtime.start({device:'cores3',firmware:firmware(),signal:cancel.signal});await until(()=>loading.runtime.iframe);cancel.abort();await assert.rejects(load,{name:'AbortError'});await loading.runtime.stop();assert.equal(loading.runtime.iframe,null);assert.equal(loading.runtime.pending.size,0);assert.equal(loading.runtime.waiters.size,0);
  options={};const pending=create();pending.runtime.port={postMessage(){throw new DOMException('bad transfer','DataCloneError');}};
  await assert.rejects(pending.runtime.ask('contract'),{name:'DataCloneError'});assert.equal(pending.runtime.pending.size,0);pending.runtime.port=null;

  const deferredFetch=[];const replacing=create({fetchImpl:()=>{const request=deferred();deferredFetch.push(request);return request.promise;}});
  const oldStart=replacing.runtime.start({device:'cores3',firmware:firmware()});oldStart.catch(()=>{});await until(()=>deferredFetch.length===1);
  const newStart=replacing.runtime.start({device:'cores3',firmware:firmware()});newStart.catch(()=>{});await until(()=>deferredFetch.length===2);
  deferredFetch[0].reject(new Error('late old failure'));await assert.rejects(oldStart,/late old failure/);
  assert.equal(replacing.runtime.status,'loading','old failure must not stop newer startup');assert.equal(replacing.runtime.abort.signal.aborted,false);
  deferredFetch[1].resolve(new Response(JSON.stringify(manifest)));await newStart;await replacing.runtime.stop();

  options={rejectStart:true};const rejected=create();await assert.rejects(rejected.runtime.start({device:'cores3',firmware:firmware()}),/contract start rejection/);await rejected.runtime.stop();await tick();assert.equal(rejected.runtime.pending.size,0);assert.equal(rejected.runtime.waiters.size,0);
  options={throwConnect:true};const connect=create();await assert.rejects(connect.runtime.start({device:'cores3',firmware:firmware()}),/connect clone failure/);await connect.runtime.stop();await tick();assert.equal(connect.runtime.pending.size,0);assert.equal(connect.runtime.waiters.size,0);

  options={};const crashed=create();await crashed.runtime.start({device:'cores3',firmware:firmware()});
  crashed.runtime.receive({type:'exit',value:{code:7}},crashed.runtime.generation);await crashed.runtime.stop();
  assert.equal(crashed.runtime.cleanupResult.exitCode,7);assert.equal(crashed.runtime.cleanupResult.gracefulExit,false,'a nonzero spontaneous exit must not be reported as normal cleanup');
  options={exitCode:9};const failedQuit=create();await failedQuit.runtime.start({device:'cores3',firmware:firmware()});await failedQuit.runtime.stop();
  assert.equal(failedQuit.runtime.cleanupResult.exitCode,9);assert.equal(failedQuit.runtime.cleanupResult.gracefulExit,false,'a nonzero quit exit must not be reported as normal cleanup');

  options={};const reused=create();await reused.runtime.start({device:'cores3',firmware:firmware()});await reused.runtime.stop();
  assert.equal(browserQemuHistory(reused.runtime.storage).length,1);
  reused.runtime.fetchImpl=async()=>{throw new Error('replacement manifest unavailable');};
  await assert.rejects(reused.runtime.start({device:'cores3',firmware:firmware()}),/replacement manifest unavailable/);
  assert.equal(reused.runtime.observe().runtime,null,'failed replacement startup must not retain the previous runtime receipt');
  assert.equal(browserQemuHistory(reused.runtime.storage).length,1,'failed replacement download must not archive the previous firmware under a fresh session');

  const oldStorage=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
  Object.defineProperty(globalThis,'localStorage',{configurable:true,get(){throw new DOMException('Storage disabled','SecurityError');}});
  try {
    assert.deepEqual(browserQemuHistory(),[],'optional history cannot break the page when the localStorage getter is blocked');
    let optional;
    assert.doesNotThrow(()=>{optional=new PublicQemuRuntime({root,storage:undefined});},'optional persistence cannot block runtime construction');
    runtimes.push(optional);
  } finally {
    if(oldStorage)Object.defineProperty(globalThis,'localStorage',oldStorage);else delete globalThis.localStorage;
  }
  assert.deepEqual(unhandled,[],'startup failure and stop must not leave an unobserved waiter rejection');
  assert.ok(frames.every(frame=>frame.removed));
  console.log('public QEMU adapter admission, resource contracts, private-channel lifecycle, cancellation and stale-generation contracts passed; no guest executed');
} finally {
  for(const runtime of runtimes)await runtime.stop();
  process.removeListener('unhandledRejection',unhandledListener);
  if(oldDocument)Object.defineProperty(globalThis,'document',oldDocument);else delete globalThis.document;
  if(oldIsolation)Object.defineProperty(globalThis,'crossOriginIsolated',oldIsolation);else delete globalThis.crossOriginIsolated;
}
