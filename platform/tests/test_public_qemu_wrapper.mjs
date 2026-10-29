// Host-only iframe/engine ownership contracts. No QEMU factory or guest runs.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const source=await readFile(new URL('../web/public-qemu-instance.js',import.meta.url),'utf8');
const origin='https://example.test',scriptURL=origin+'/showcase/platform/web/public-qemu-instance.js';
const executable=source.replaceAll('import.meta.url',JSON.stringify(scriptURL));
const parent={};
function fixture({constructorError,transferError}={}){
  const listeners=new Map(),workers=[],timers=new Map();let nextTimer=0;
  class MockWorker {
    constructor(url,options){if(constructorError)throw new Error(constructorError);this.url=String(url);this.options=options;this.messages=[];this.events=new Map();this.terminations=0;workers.push(this);}
    addEventListener(type,callback){if(!this.events.has(type))this.events.set(type,[]);this.events.get(type).push(callback);}
    removeEventListener(type,callback){this.events.set(type,(this.events.get(type)||[]).filter(item=>item!==callback));}
    postMessage(value,transfer=[]){if(transferError)throw new Error(transferError);this.messages.push({value,transfer});}
    terminate(){this.terminations++;}
    emit(type,data){const event=type==='message'?{data}:data;this['on'+type]?.(event);for(const callback of this.events.get(type)||[])callback(event);}
  }
  const context=vm.createContext({Worker:MockWorker,parent,location:{origin,href:scriptURL},URL,
    Set,Map,ArrayBuffer,Uint8Array,Number,JSON,Error,Object,Promise,console,
    addEventListener:(type,callback)=>{if(!listeners.has(type))listeners.set(type,[]);listeners.get(type).push(callback);},
    setTimeout:(callback,ms)=>{const id=++nextTimer;timers.set(id,{callback,ms});return id;},
    clearTimeout:id=>timers.delete(id)});
  vm.runInContext(executable,context,{filename:'public-qemu-instance.js'});
  const dispatch=(type,event)=>{for(const callback of listeners.get(type)||[])callback(event);};
  const ownership=()=>JSON.parse(vm.runInContext('JSON.stringify(globalThis.m5QemuEngineOwnership)',context));
  const port=()=>({messages:[],closed:false,started:false,
    postMessage(value,transfer=[]){this.messages.push({value,transfer});},start(){this.started=true;},close(){this.closed=true;}});
  const connect=(privatePort,overrides={})=>dispatch('message',{source:parent,origin,data:{type:'m5-qemu-connect'},ports:[privatePort],...overrides});
  return {context,workers,timers,dispatch,ownership,port,connect};
}

assert.ok(source.includes('m5QemuEngineOwnership'),'the private engine wrapper must expose read-only lifecycle evidence');
const initial=fixture();
assert.deepEqual(initial.ownership(),{engineWorkersCreated:0,engineOwnerLive:false,
  engineCloseNotificationReceived:false,engineSelfCloseNotifications:0,engineNormalTerminations:0,engineFallbackTerminations:0,enginePortTransferred:false});
const invalidPort=initial.port();
for(const overrides of [
  {source:{}},{origin:'https://other.test'},{data:{type:'other'}},{ports:[]},{ports:null},{ports:[invalidPort,initial.port()]},
])initial.connect(invalidPort,overrides);
assert.equal(initial.workers.length,0,'only parent/same-origin/exact-one-port may create the engine');
assert.equal(invalidPort.messages.length,0,'untrusted connection events receive no data');

const active=fixture(),privatePort=active.port();active.connect(privatePort);
assert.equal(active.workers.length,1,'accepted connect creates exactly one engine owner');
const engine=active.workers[0];
assert.equal(engine.url,origin+'/showcase/platform/web/public-qemu-engine.js');
assert.equal(engine.options?.type,'module','the QEMU owner is a dedicated module Worker');
assert.equal(active.ownership().engineWorkersCreated,1);
assert.equal(active.ownership().engineOwnerLive,true);
assert.equal(active.ownership().enginePortTransferred,false);
assert.equal(engine.messages.length,0,'do not transfer until engine confirms its listener');
const replacementPort=active.port();active.connect(replacementPort);
assert.equal(active.workers.length,1,'second parent connect cannot replace the first owner or port');
engine.emit('message',{type:'unrelated'});assert.equal(engine.messages.length,0);
engine.emit('message',{type:'m5-qemu-engine-closing'});
assert.equal(active.ownership().engineCloseNotificationReceived,false,'an unconnected engine cannot announce accepted closure');
assert.equal(active.ownership().engineOwnerLive,true);
engine.emit('message',{type:'m5-qemu-engine-listening'});
assert.equal(engine.messages.length,1);assert.equal(engine.messages[0].value.type,'m5-qemu-engine-connect');
assert.equal(engine.messages[0].transfer.length,1);assert.equal(engine.messages[0].transfer[0],privatePort);
assert.equal(active.ownership().enginePortTransferred,true);
assert.equal(active.timers.size,0,'successful port transfer cancels initialization timeout');
engine.emit('message',{type:'m5-qemu-engine-listening'});
assert.equal(engine.messages.length,1,'duplicate listening cannot transfer or connect twice');
assert.equal(replacementPort.messages.length,0);
// Ownership is observational. External writes must not alter internal state.
vm.runInContext('try { globalThis.m5QemuEngineOwnership.engineWorkersCreated=99; } catch {}',active.context);
assert.equal(active.ownership().engineWorkersCreated,1);
engine.emit('message',{type:'m5-qemu-engine-closing'});
assert.equal(active.ownership().engineCloseNotificationReceived,true);
assert.equal(active.ownership().engineSelfCloseNotifications,1);
assert.equal(active.ownership().engineNormalTerminations,0,'a cooperative notification is not an owner terminate call');
assert.equal(active.ownership().engineFallbackTerminations,0);
assert.equal(engine.terminations,0,'cooperative self.close must not race an immediate owner terminate');
engine.emit('message',{type:'m5-qemu-engine-closing'});
assert.equal(active.ownership().engineSelfCloseNotifications,1,'duplicate notifications cannot invent another close');
active.dispatch('pagehide',{});active.dispatch('pagehide',{});
assert.equal(engine.terminations,0,'normal pagehide must let the announced self.close finish');
assert.equal(active.ownership().engineFallbackTerminations,0);
assert.equal(active.ownership().engineOwnerLive,false);

// A later explicit worker error is still a failure, even after normal close
// intent. Its forced termination remains separate from cooperative intent.
const closeFailure=fixture(),closeFailurePort=closeFailure.port();closeFailure.connect(closeFailurePort);
const closeFailureWorker=closeFailure.workers[0];
closeFailureWorker.emit('message',{type:'m5-qemu-engine-listening'});
closeFailureWorker.emit('message',{type:'m5-qemu-engine-closing'});
closeFailureWorker.emit('error',{message:'synthetic error after close notification'});
closeFailureWorker.emit('error',{message:'duplicate error'});
closeFailure.dispatch('pagehide',{});
assert.equal(closeFailure.ownership().engineSelfCloseNotifications,1);
assert.equal(closeFailure.ownership().engineNormalTerminations,0);
assert.equal(closeFailure.ownership().engineFallbackTerminations,1);
assert.equal(closeFailureWorker.terminations,1,'an explicit error still forces teardown exactly once');

for(const transferred of [false,true]){
  const abandoned=fixture(),port=abandoned.port();abandoned.connect(port);
  const worker=abandoned.workers[0];
  if(transferred)worker.emit('message',{type:'m5-qemu-engine-listening'});
  abandoned.dispatch('pagehide',{});abandoned.dispatch('pagehide',{});
  assert.equal(worker.terminations,1,'pagehide terminates an unclosed engine exactly once');
  assert.equal(abandoned.ownership().engineFallbackTerminations,1);
  assert.equal(abandoned.ownership().engineSelfCloseNotifications,0);
  assert.equal(abandoned.ownership().engineOwnerLive,false);
  const sent=worker.messages.length;worker.emit('message',{type:'m5-qemu-engine-listening'});
  assert.equal(worker.messages.length,sent,'late listening after teardown cannot transfer a port');
  worker.emit('message',{type:'m5-qemu-engine-closing'});
  assert.equal(abandoned.ownership().engineCloseNotificationReceived,false,'late closing cannot rewrite a forced fallback as cooperative');
}

function assertBeforeTransferFailure(state,port,expectedMessage,created){
  assert.equal(state.ownership().engineWorkersCreated,created);
  assert.equal(state.ownership().engineOwnerLive,false,'failed startup cannot leave an owned engine alive');
  assert.equal(state.ownership().enginePortTransferred,false,'failed transfer never becomes accepted ownership');
  assert.equal(state.ownership().engineFallbackTerminations,created);
  assert.equal(port.closed,true,'failed startup closes the held parent port');
  assert.equal(port.messages.length,1);assert.equal(port.messages[0].value.type,'error');
  assert.match(port.messages[0].value.value,expectedMessage);
  assert.equal(state.timers.size,0,'failed startup must cancel the initialization timer');
  state.dispatch('pagehide',{});state.dispatch('pagehide',{});
  if(created)assert.equal(state.workers[0].terminations,1,'failure and pagehide cannot double-terminate');
}
const constructorFailure=fixture({constructorError:'synthetic constructor error'}),constructorPort=constructorFailure.port();
constructorFailure.connect(constructorPort);
assertBeforeTransferFailure(constructorFailure,constructorPort,/synthetic constructor error/,0);
const transferFailure=fixture({transferError:'synthetic transfer error'}),transferPort=transferFailure.port();
transferFailure.connect(transferPort);transferFailure.workers[0].emit('message',{type:'m5-qemu-engine-listening'});
assertBeforeTransferFailure(transferFailure,transferPort,/synthetic transfer error/,1);
const workerFailure=fixture(),failurePort=workerFailure.port();workerFailure.connect(failurePort);
workerFailure.workers[0].emit('error',{message:'synthetic worker error'});
assertBeforeTransferFailure(workerFailure,failurePort,/synthetic worker error/,1);
const timeout=fixture(),timeoutPort=timeout.port();timeout.connect(timeoutPort);
assert.equal(timeout.timers.size,1);const [timerId,timer]=[...timeout.timers][0];
assert.equal(timer.ms,30000,'engine listener wait has a bounded initialization timeout');
timeout.timers.delete(timerId);timer.callback();
assertBeforeTransferFailure(timeout,timeoutPort,/initialization timed out/,1);
// A transferred MessagePort cannot be reused by the iframe. Still reclaim the
// failed owner; the parent's request timeout remains its failure signal.
const transferredFailure=fixture(),transferredPort=transferredFailure.port();transferredFailure.connect(transferredPort);
const failedEngine=transferredFailure.workers[0];failedEngine.emit('message',{type:'m5-qemu-engine-listening'});
failedEngine.emit('error',{message:'synthetic post-transfer worker failure'});
assert.equal(transferredFailure.ownership().engineOwnerLive,false,'post-transfer worker error must reclaim the owner');
assert.equal(transferredFailure.ownership().engineFallbackTerminations,1);
assert.equal(failedEngine.terminations,1);assert.equal(transferredFailure.timers.size,0);
transferredFailure.dispatch('pagehide',{});assert.equal(failedEngine.terminations,1);

console.log('private QEMU iframe ownership/origin/one-port/transfer, cooperative self-close without owner terminate, startup/error/timeout/pagehide fallback contracts passed; no guest executed');
