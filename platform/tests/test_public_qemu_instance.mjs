// Window/port/disposal contracts only. The C runtime is never imported or run.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const callbacks=new Map(),parent={},origin='https://example.test';
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
const source=await readFile(new URL('../web/public-qemu-instance.js',import.meta.url),'utf8');
const context=vm.createContext({Worker,TextEncoder,TextDecoder:BrowserTextDecoder,Uint8Array,Map,Set,URL:TestURL,Blob:TestBlob,ArrayBuffer,Number,JSON,Error,Promise,setTimeout,clearTimeout,parent,location:{origin},crossOriginIsolated:true,SharedArrayBuffer,crypto:globalThis.crypto,performance:globalThis.performance,
  addEventListener:(name,handler)=>callbacks.set(name,handler)});
vm.runInContext(source,context,{importModuleDynamically:vm.constants.USE_MAIN_CONTEXT_DEFAULT_LOADER});
const port=()=>({messages:[],closed:false,start(){this.started=true;},close(){this.closed=true;},postMessage(value){this.messages.push(value);}});
const connect=callbacks.get('message'),one=port();
for(const event of [{source:{},origin,data:{type:'m5-qemu-connect'},ports:[one]},
  {source:parent,origin:'https://other.test',data:{type:'m5-qemu-connect'},ports:[one]},
  {source:parent,origin,data:{type:'other'},ports:[one]},
  {source:parent,origin,data:{type:'m5-qemu-connect'},ports:[]}])connect(event);
assert.equal(one.started,undefined);
connect({source:parent,origin,data:{type:'m5-qemu-connect'},ports:[one]});assert.equal(one.started,true);assert.equal(one.messages[0].type,'connected');
const two=port();connect({source:parent,origin,data:{type:'m5-qemu-connect'},ports:[two]});assert.equal(two.started,undefined,'a second connection cannot replace the private port');
await one.onmessage({data:{id:1,op:'uart',value:{text:'contract'}}});assert.match(one.messages.at(-1).error,/UART output only/);
// A JS-only factory exposes the actual preRun FS devices without importing
// Emscripten or any guest. Exercise the real UART write and PPM parser together.
const fakeFactory=`export default async function(options){
  const devices=[];const stream={stream_ops:{}};
  const module={ENV:{},HEAPU8:new Uint8Array(new SharedArrayBuffer(65536)),FS:{devices,mkdirTree(){},writeFile(){},makedev:(a,b)=>b,
    registerDevice:(id,ops)=>devices[id]=ops,mkdev(){},getStream:()=>stream,
    ErrnoError:class extends Error{}}};
  for(const callback of options.preRun)callback(module);
  options.onRuntimeInitialized();return module;
}`;
await one.onmessage({data:{id:4,op:'start',value:{javascript:new TextEncoder().encode(fakeFactory),javascriptURL:origin+'/showcase/runtime/qemu.js',worker:new Uint8Array(),rom:new ArrayBuffer(0),firmware:new ArrayBuffer(0)}}});
assert.equal(one.messages.at(-1).id,4);assert.equal(one.messages.at(-1).error,undefined);
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
await one.onmessage({data:{id:2,op:'dispose'}});assert.equal(one.messages.at(-1).id,2);assert.equal(one.messages.at(-1).value.workersRemaining,0);assert.equal(one.closed,true);
const count=one.messages.length;await one.onmessage({data:{id:3,op:'uart',value:{text:'late'}}});assert.equal(one.messages.length,count,'disposed instances reject queued late operations');
console.log('public QEMU instance parent/origin/one-port ownership and disposal fencing contracts passed; no guest executed');
