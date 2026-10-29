// Engine Worker/port/disposal contracts only. No C runtime or guest is run.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {validateQemuProfile,buildQemuArguments,buildQemuEfuse,qemuInputCommand,getQemuBrowserProfile} from '../web/public-qemu-profiles.js';
import {readSharedQemuFrame} from '../web/public-qemu-frame.js';

const registry=JSON.parse(await readFile(new URL('../web/qemu-browser-profiles.json',import.meta.url),'utf8'));
const profile=getQemuBrowserProfile('cores3',registry);

const callbacks=new Map(),origin='https://example.test',lifecycle=[];
class Worker {terminate(){}}
// Node's decoder accepts shared views; Chromium's Web API rejects them.
class BrowserTextDecoder extends TextDecoder {
  decode(input,options){
    if(input instanceof SharedArrayBuffer||input?.buffer instanceof SharedArrayBuffer)throw new TypeError('ArrayBufferView must not be shared');
    return super.decode(input,options);
  }
}
class TestBlob {constructor(parts){this.parts=parts;}}
class TestURL extends URL {
  static createObjectURL(blob){return 'data:text/javascript;base64,'+Buffer.concat(blob.parts.map(part=>Buffer.from(part))).toString('base64');}
  static revokeObjectURL(){}
}
const source=await readFile(new URL('../web/public-qemu-engine.js',import.meta.url),'utf8');
const executableSource=source.replace(/^import .+;\r?\n/gm,'');
const context=vm.createContext({Worker,TextEncoder,TextDecoder:BrowserTextDecoder,Uint8Array,Map,Set,URL:TestURL,Blob:TestBlob,ArrayBuffer,Number,JSON,Error,Promise,setTimeout,clearTimeout,location:{origin},crossOriginIsolated:true,SharedArrayBuffer,crypto:globalThis.crypto,performance:globalThis.performance,
  validateQemuProfile,buildQemuArguments,buildQemuEfuse,qemuInputCommand,readSharedQemuFrame,
  self:{postMessage:value=>lifecycle.push(value.type),close:()=>lifecycle.push('engine-closed')},
  addEventListener:(name,handler)=>callbacks.set(name,handler)});
vm.runInContext(executableSource,context,{importModuleDynamically:vm.constants.USE_MAIN_CONTEXT_DEFAULT_LOADER});
const port=()=>({messages:[],closed:false,start(){this.started=true;},close(){this.closed=true;lifecycle.push('port-closed');},postMessage(value){this.messages.push(value);if(value.id===2)lifecycle.push('dispose-ack');}});
const connect=callbacks.get('message'),one=port();
assert.deepEqual(lifecycle,['m5-qemu-engine-listening']);
for(const event of [{data:{type:'other'},ports:[one]},
  {data:{type:'m5-qemu-engine-connect'},ports:[]},
  {data:{type:'m5-qemu-engine-connect'},ports:[one,port()]},
  {data:{type:'m5-qemu-engine-connect'}}])connect(event);
assert.equal(one.started,undefined);
connect({data:{type:'m5-qemu-engine-connect'},ports:[one]});assert.equal(one.started,true);assert.equal(one.messages[0].type,'connected');
const two=port();connect({data:{type:'m5-qemu-engine-connect'},ports:[two]});assert.equal(two.started,undefined,'a second connection cannot replace the private port');
await one.onmessage({data:{id:1,op:'uart',value:{text:'contract'}}});assert.match(one.messages.at(-1).error,/UART output only/);
// A JS-only factory exposes the actual preRun FS devices without importing
// Emscripten or any guest. Exercise the real UART write and PPM parser together.
const fakeFactory=`export default async function(options){
  const devices=[];const stream={stream_ops:{}};
  const files=new Map();const module={ENV:{},arguments:options.arguments,HEAPU8:new Uint8Array(new SharedArrayBuffer(65536)),FS:{devices,files,mkdirTree(){},writeFile:(name,value)=>files.set(name,value),makedev:(a,b)=>b,
    registerDevice:(id,ops)=>devices[id]=ops,mkdev(){},getStream:()=>stream,
    ErrnoError:class extends Error{}}};
  for(const callback of options.preRun)callback(module);
  options.onRuntimeInitialized();return module;
}`;
await one.onmessage({data:{id:4,op:'start',value:{javascript:new TextEncoder().encode(fakeFactory),javascriptURL:origin+'/showcase/runtime/qemu.js',worker:new Uint8Array(),profile,frameTransport:'qmp-screendump',roms:profile.roms.map(rom=>({name:rom.name,sha256:rom.sha256,bytes:new ArrayBuffer(rom.bytes)})),firmware:new ArrayBuffer(0)}}});
assert.equal(one.messages.at(-1).id,4);assert.equal(one.messages.at(-1).error,undefined);
await one.onmessage({data:{id:5,op:'start',value:{}}});assert.match(one.messages.at(-1).error,/already initialized/);
assert.deepEqual(JSON.parse(vm.runInContext('JSON.stringify(module.arguments)',context)),buildQemuArguments(profile));
assert.equal(vm.runInContext('module.ENV.M5_WASM_VM_CLOCK_DIVISOR',context),'8');
assert.equal(vm.runInContext('module.ENV.M5_WASM_FRAMEBUFFER',context),'0');
assert.equal(vm.runInContext(`module.FS.files.get('/rom/${profile.roms[0].name}').byteLength`,context),profile.roms[0].bytes);
assert.equal(vm.runInContext("module.FS.files.get('/efuse.bin').byteLength",context),4096);
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const commands=()=>JSON.parse(vm.runInContext("JSON.stringify(new TextDecoder().decode(new Uint8Array(qmpInput.splice(0))).trim().split('\\n').filter(Boolean).map(line=>JSON.parse(line)))",context));
const respond=(command,value)=>vm.runInContext(`output(${JSON.stringify(JSON.stringify({return:value,id:command.id})+'\n')})`,context);
vm.runInContext(`output('${JSON.stringify({QMP:{version:{},capabilities:[]}})}\\n')`,context);
assert.equal(one.messages.some(item=>item.type==='ready'),false,'QMP greeting alone does not mean machine initialization is finished');
const capability=commands();assert.equal(capability.length,1);assert.equal(capability[0].execute,'qmp_capabilities');respond(capability[0],{});await tick();
const constructing=commands();assert.equal(constructing.length,1);assert.equal(constructing[0].execute,'query-status');respond(constructing[0],{running:false,status:'prelaunch'});await tick();
assert.equal(one.messages.some(item=>item.type==='ready'),false,'a nonrunning machine cannot authorize frame polling');
await new Promise(resolve=>setTimeout(resolve,120));
const running=commands();assert.equal(running.length,1);assert.equal(running[0].execute,'query-status');respond(running[0],{running:true,status:'running'});await tick();
const ready=one.messages.filter(item=>item.type==='ready');assert.equal(ready.length,1);assert.equal(ready[0].value.shared,true);assert.equal(ready[0].value.memoryBytes,65536);
vm.runInContext(`
  const serialBytes=new Uint8Array(new SharedArrayBuffer(3));serialBytes.set([0xe4,0xb8,0xad]);
  module.FS.devices[0].write(null,serialBytes,0,2);
  const header=new TextEncoder().encode('P6\\n320 240\\n255\\n');
  const frame=new Uint8Array(header.length+320*240*3);frame.set(header);
  ppm(frame);
  module.FS.devices[0].write(null,serialBytes,2,1);
`,context);
assert.equal(one.messages.filter(item=>item.type==='serial').map(item=>item.value).join(''),'中','frame parsing cannot consume a pending UART UTF-8 sequence');
await one.onmessage({data:{id:10,op:'input',value:{type:'uart',text:'unadmitted'}}});assert.match(one.messages.at(-1).error,/not admitted/);assert.equal(commands().length,0,'UART rejection cannot enqueue a QMP command');
const touch=one.onmessage({data:{id:11,op:'input',value:{type:'touch',x:319,y:239,down:true}}});
const touchCommands=commands();assert.equal(touchCommands.length,1);assert.equal(touchCommands[0].execute,'input-send-event');
assert.equal(touchCommands[0].arguments.events[0].data.value,32767);assert.equal(touchCommands[0].arguments.events[1].data.value,32767);respond(touchCommands[0],{});await touch;
const pir=one.onmessage({data:{id:12,op:'input',value:{type:'pir',motion:true}}});
const pirSet=commands();assert.equal(pirSet.length,1);assert.equal(pirSet[0].execute,'qom-set');assert.equal(pirSet[0].arguments.path,'/machine/units/pir');respond(pirSet[0],{});await tick();
const pirGet=commands();assert.equal(pirGet.length,1);assert.equal(pirGet[0].execute,'qom-get');respond(pirGet[0],true);await pir;assert.equal(one.messages.at(-1).value.motion,true);
const display=one.onmessage({data:{id:13,op:'display'}});
const panelList=commands();assert.equal(panelList.length,1);assert.equal(panelList[0].execute,'qom-list');
assert.equal(panelList[0].arguments.path,'/machine/unattached');
respond(panelList[0],[{name:'device[13]',type:'child<m5.spi-panel>'}]);
await tick();
const panelOrientation=commands();assert.equal(panelOrientation.length,1);assert.equal(panelOrientation[0].execute,'qom-get');
assert.equal(panelOrientation[0].arguments.path,'/machine/unattached/device[13]');
assert.equal(panelOrientation[0].arguments.property,'logical-orientation');
respond(panelOrientation[0],'portrait');await display;
assert.equal(one.messages.at(-1).value.orientation,'portrait');
assert.equal(one.messages.at(-1).value.deviceRotationDeg,-90);
// A synthetic host-side ABI buffer exercises the imported real shared-frame
// reader through the instance port. It is not firmware/display validation.
vm.runInContext(`
  frameTransport='shared-rgb565-v1';module.HEAPU8=new Uint8Array(new SharedArrayBuffer(196608));
  module._m5_wasm_frame_state=()=>32;
  const words=new Uint32Array(module.HEAPU8.buffer,32,8);words.set([0x4d354642,2,320,240,640,64,1,0]);
  module.HEAPU8[64]=0x34;module.HEAPU8[65]=0x12;
`,context);
await one.onmessage({data:{id:20,op:'frame'}});
const sharedFrames=one.messages.filter(item=>item.type==='frame');assert.equal(sharedFrames.length,1);assert.equal(sharedFrames[0].value.source,'qemu-display-surface-shared');assert.equal(sharedFrames[0].value.sourceSequence,2);assert.equal(sharedFrames[0].value.pixels[0],0x34);
await one.onmessage({data:{id:21,op:'frame'}});assert.equal(one.messages.at(-1).value.unchanged,true);assert.equal(one.messages.filter(item=>item.type==='frame').length,1);assert.equal(commands().length,0,'shared frames must not fall back to screendump QMP');
const lateInput=one.onmessage({data:{id:22,op:'input',value:{type:'touch',x:1,y:1,down:false}}});
assert.equal(commands().length,1);
await one.onmessage({data:{id:2,op:'dispose'}});await lateInput;assert.equal(one.messages.at(-1).id,2);assert.equal(one.messages.at(-1).value.workersRemaining,0);assert.equal(one.closed,true);
assert.equal(one.messages.at(-1).value.workerCountScope,'nested-pthreads');
assert.equal(one.messages.at(-1).value.enginePlacement,'dedicated-worker-v1');
assert.equal(one.messages.at(-1).value.engineWorkersAtAcknowledgement,1,'acknowledgement does not claim the owning Worker already exited');
assert.deepEqual(lifecycle,['m5-qemu-engine-listening','dispose-ack','port-closed','m5-qemu-engine-closing','engine-closed']);
assert.equal(vm.runInContext('pending.size',context),0);
assert.equal(one.messages.some(item=>item.id===22),false,'in-flight operations cannot reply after disposal');
const count=one.messages.length;await one.onmessage({data:{id:3,op:'uart',value:{text:'late'}}});assert.equal(one.messages.length,count,'disposed instances reject queued late operations');
// Independent actual-source engine fixture: disposal while initialization is
// awaiting query-status must not emit a late error/ready or reopen the port.
const raceCallbacks=new Map(),raceLifecycle=[],raceUnhandled=[];
const onRaceUnhandled=error=>raceUnhandled.push(error);
process.on('unhandledRejection',onRaceUnhandled);
try {
  const raceContext=vm.createContext({Worker,TextEncoder,TextDecoder:BrowserTextDecoder,Uint8Array,Map,Set,URL:TestURL,Blob:TestBlob,ArrayBuffer,Number,JSON,Error,Promise,setTimeout,clearTimeout,
    location:{origin},crossOriginIsolated:true,SharedArrayBuffer,crypto:globalThis.crypto,performance:globalThis.performance,
    validateQemuProfile,buildQemuArguments,buildQemuEfuse,qemuInputCommand,readSharedQemuFrame,
    self:{postMessage:value=>raceLifecycle.push(value.type),close:()=>raceLifecycle.push('engine-closed')},
    addEventListener:(name,handler)=>raceCallbacks.set(name,handler)});
  vm.runInContext(executableSource,raceContext,{importModuleDynamically:vm.constants.USE_MAIN_CONTEXT_DEFAULT_LOADER});
  const racePort={messages:[],closed:false,start(){this.started=true;},close(){this.closed=true;raceLifecycle.push('port-closed');},
    postMessage(value){this.messages.push(value);if(value.id===302)raceLifecycle.push('dispose-ack');}};
  raceCallbacks.get('message')({data:{type:'m5-qemu-engine-connect'},ports:[racePort]});
  await racePort.onmessage({data:{id:300,op:'start',value:{javascript:new TextEncoder().encode(fakeFactory),
    javascriptURL:origin+'/showcase/runtime/qemu.js',worker:new Uint8Array(),profile,frameTransport:'qmp-screendump',
    roms:profile.roms.map(rom=>({name:rom.name,sha256:rom.sha256,bytes:new ArrayBuffer(rom.bytes)})),firmware:new ArrayBuffer(0)}}});
  assert.equal(racePort.messages.at(-1).id,300);assert.equal(racePort.messages.at(-1).error,undefined);
  const raceCommands=()=>JSON.parse(vm.runInContext("JSON.stringify(new TextDecoder().decode(new Uint8Array(qmpInput.splice(0))).trim().split('\\n').filter(Boolean).map(line=>JSON.parse(line)))",raceContext));
  const raceRespond=(command,value)=>vm.runInContext(`output(${JSON.stringify(JSON.stringify({return:value,id:command.id})+'\n')})`,raceContext);
  vm.runInContext(`output(${JSON.stringify(JSON.stringify({QMP:{version:{},capabilities:[]}})+'\n')})`,raceContext);
  const raceCapability=raceCommands();assert.equal(raceCapability.length,1);assert.equal(raceCapability[0].execute,'qmp_capabilities');
  raceRespond(raceCapability[0],{});await tick();
  const raceStatus=raceCommands();assert.equal(raceStatus.length,1);assert.equal(raceStatus[0].execute,'query-status');
  assert.equal(vm.runInContext('pending.size',raceContext),1,'initialization query must still be in flight');
  assert.equal(racePort.messages.some(message=>message.type==='ready'),false);
  await racePort.onmessage({data:{id:302,op:'dispose'}});await tick();await tick();
  assert.equal(racePort.messages.at(-1).id,302,'disposal acknowledgement remains the final port message');
  assert.equal(racePort.closed,true);assert.equal(vm.runInContext('pending.size',raceContext),0);
  assert.deepEqual(raceLifecycle,['m5-qemu-engine-listening','dispose-ack','port-closed','m5-qemu-engine-closing','engine-closed']);
  assert.equal(racePort.messages.some(message=>message.type==='error'||message.type==='ready'),false,
    'rejecting initialization QMP during dispose cannot emit late error/ready');
  const raceMessageCount=racePort.messages.length;
  raceRespond(raceStatus[0],{running:true,status:'running'});await tick();
  assert.equal(racePort.messages.length,raceMessageCount,'a delayed query-status response cannot resurrect readiness');
  assert.equal(vm.runInContext('pending.size',raceContext),0);
  assert.deepEqual(raceUnhandled,[],'disposed initialization cannot leave an unhandled rejection');
} finally {
  process.removeListener('unhandledRejection',onRaceUnhandled);
}
console.log('public QEMU dedicated engine one-port, FS/frame, pending-QMP disposal and ack-before-self-close contracts passed; no guest executed');
