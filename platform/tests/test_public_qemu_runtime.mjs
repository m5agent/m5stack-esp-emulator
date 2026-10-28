// Host adapter contracts only. Mock downloads/messages never execute a guest.
import assert from 'node:assert/strict';
import {PublicQemuRuntime,browserQemuHistory} from '../web/public-qemu-runtime.js';

const root='https://example.test/showcase/';
const romSha='b5c7090cc22efce51c1323cef31ca96fcd673a5b1d1b1017e219d393f2659913';
const manifest={schema_version:1,engine:'qemu-wasm',source:{commit:'40edccac415693c5130f91c01d84176ae6008566'},profiles:['cores3'],execution_profile:{id:'cores3-wasm-vm-div8'},build:{kind:'contract-fixture'},
  assets:{javascript:{path:'qemu-system-xtensa.js',sha256:'1'.repeat(64),bytes:8},wasm:{path:'qemu-system-xtensa.wasm',sha256:'2'.repeat(64),bytes:8},worker:{path:'qemu-system-xtensa.worker.js',sha256:'3'.repeat(64),bytes:8}},
  required_rom:{url:'https://example.test/rom.bin',sha256:romSha,bytes:393216}};
function firmware(){const bytes=new Uint8Array(0x10100),view=new DataView(bytes.buffer);for(const at of [0,0x10000]){bytes[at]=0xe9;bytes[at+1]=1;view.setUint16(at+12,9,true);view.setUint32(at+28,4,true);}view.setUint16(0x8000,0x50aa,true);view.setUint32(0x8004,0x10000,true);view.setUint32(0x8008,0x1000,true);return bytes.buffer;}
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
      frame.calls.push(data.op);
      if(config.ignore?.includes(data.op))return;
      if(data.op==='start'&&config.rejectStart){port.postMessage({id:data.id,error:'contract start rejection'});return;}
      port.postMessage({id:data.id,value:data.op==='pir'?{motion:data.value.motion}:data.op==='dispose'?{workersRemaining:0}:undefined});
      if(data.op==='start')queueMicrotask(()=>port.postMessage({type:'ready',value:{shared:true,crossOriginIsolated:true,memoryBytes:268435456}}));
      if(data.op==='quit')queueMicrotask(()=>port.postMessage({type:'exit',value:{code:config.exitCode??0}}));
      if(data.op==='frame')port.postMessage({type:'frame',value:{width:320,height:240,pixels:new Uint8Array(320*240*2),format:'rgb565le',source:'contract-fixture'}});
    };
    port.start();if(!config.ignoreConnect)port.postMessage({type:'connected',value:{}});
  }}};frames.push(frame);return frame;},
  body:{append(frame){if(!options.ignoreLoad)queueMicrotask(()=>frame.onload?.());}},
};
const oldDocument=Object.getOwnPropertyDescriptor(globalThis,'document'),oldIsolation=Object.getOwnPropertyDescriptor(globalThis,'crossOriginIsolated');
Object.defineProperty(globalThis,'document',{value:mockDocument,configurable:true});Object.defineProperty(globalThis,'crossOriginIsolated',{value:true,configurable:true});
const unhandled=[];const unhandledListener=error=>unhandled.push(error);process.on('unhandledRejection',unhandledListener);
const runtimes=[];
function create(overrides={}){
  const downloads=[],states=[],errors=[];
  const runtime=new PublicQemuRuntime({root,storage:storage(),requestTimeout:100,onState:value=>states.push(value.status),onError:error=>errors.push(error.message),
    fetchImpl:async function(url){assert.equal(this,undefined,'native fetch receiver must stay unbound');assert.equal(url,root+'platform/runtime/qemu/runtime.json');return new Response(JSON.stringify(manifest));},
    downloadImpl:async(url,config)=>{downloads.push({url,...config});const size=url.endsWith('/rom.bin')?393216:8;return {bytes:new ArrayBuffer(size),size,sha256:config.expectedSha256};},...overrides});
  runtimes.push(runtime);return {runtime,downloads,states,errors};
}
try {
  const normal=create();await normal.runtime.start({device:'cores3',firmware:firmware()});await until(()=>normal.runtime.lastFrame);
  assert.equal(normal.runtime.observe().status,'running');assert.equal(normal.runtime.observe().persistentStorage,false);
  assert.equal(normal.runtime.receipt.clockDivisor,8);assert.equal(normal.downloads.length,4);assert.equal(normal.downloads[3].expectedSha256,romSha);
  assert.ok(normal.downloads.every(row=>row.signal instanceof AbortSignal&&typeof row.fetchImpl==='function'));
  assert.equal((await normal.runtime.input({type:'pir',motion:true})).result.motion,true);
  await normal.runtime.input({type:'touch',x:160,y:184,down:true});await normal.runtime.input({type:'uart',text:'hello\n'});
  await assert.rejects(normal.runtime.input({type:'touch',x:320,y:1,down:true}));await assert.rejects(normal.runtime.input({type:'uart',text:'a'.repeat(129)}));
  await normal.runtime.pause();assert.equal(normal.runtime.status,'paused');await normal.runtime.input({type:'touch',x:160,y:184,down:false});
  await assert.rejects(normal.runtime.input({type:'pir',motion:false}));await normal.runtime.resume();assert.equal(normal.runtime.status,'running');
  const generation=normal.runtime.generation,frameCount=normal.runtime.sequence;
  normal.runtime.receive({type:'frame',value:{width:1,height:1,pixels:new Uint8Array(2)}},generation-1);assert.equal(normal.runtime.sequence,frameCount);
  await normal.runtime.stop();assert.equal(normal.runtime.pending.size,0);assert.equal(normal.runtime.waiters.size,0);assert.equal(normal.runtime.iframe,null);assert.equal(normal.runtime.port,null);
  assert.equal(normal.runtime.cleanupResult.exitCode,0);assert.equal(normal.runtime.cleanupResult.explicitWorkerDisposal,true);assert.equal(browserQemuHistory(normal.runtime.storage).length,1);assert.ok(normal.runtime.evidence().last_frame.sha256);

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
