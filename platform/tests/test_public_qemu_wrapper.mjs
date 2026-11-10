// Host-only iframe/engine ownership contracts. No QEMU factory or guest runs.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const iframeSource=await readFile(new URL('../web/public-qemu-instance.js',import.meta.url),'utf8');
const ownerSource=await readFile(new URL('../web/public-qemu-engine-owner.js',import.meta.url),'utf8');
const origin='https://example.test',engineURL=origin+'/showcase/platform/web/public-qemu-engine.js';
const makePort=()=>({messages:[],closed:false,started:false,
  postMessage(value,transfer=[]){this.messages.push({value,transfer});},start(){this.started=true;},close(){this.closed=true;}});

function iframeFixture({replyError=false}={}) {
  let receive;
  const sent=[],parent={postMessage(...args){if(replyError)throw new Error('reply failed');sent.push(args);}};
  vm.runInNewContext(iframeSource,{parent,location:{origin},addEventListener(type,callback){assert.equal(type,'message');receive=callback;}});
  const connect=(port,overrides={})=>receive({source:parent,origin,data:{type:'m5-qemu-connect',sessionId:'session'},ports:[port],...overrides});
  return {sent,connect};
}
const wrapper=iframeFixture(),port=makePort(),extraPort=makePort();
for(const overrides of [
  {source:{}},{origin:'https://other.test'},{data:{type:'other'}},{data:{type:'m5-qemu-connect'}},
  {ports:[]},{ports:null},{ports:[port,extraPort]},
])wrapper.connect(port,overrides);
assert.equal(wrapper.sent.length,0,'iframe rejects invalid source, origin, session and port count');
wrapper.connect(port);wrapper.connect(extraPort);
assert.equal(wrapper.sent.length,1,'iframe admits a single parent request');
assert.equal(wrapper.sent[0][0].type,'m5-qemu-admitted');assert.equal(wrapper.sent[0][0].sessionId,'session');
assert.equal(wrapper.sent[0][1],origin);assert.equal(wrapper.sent[0][2][0],port);
const failedReply=iframeFixture({replyError:true}),failedReplyPort=makePort();
failedReply.connect(failedReplyPort);assert.equal(failedReplyPort.closed,true);

function fixture({constructorError,transferError}={}){
  const listeners=new Map(),workers=[],timers=new Map(),errors=[];let nextTimer=0,owner;
  class MockWorker {
    constructor(url,options){if(constructorError)throw new Error(constructorError);this.url=String(url);this.options=options;this.messages=[];this.events=new Map();this.terminations=0;workers.push(this);}
    addEventListener(type,callback){if(!this.events.has(type))this.events.set(type,new Set());this.events.get(type).add(callback);}
    removeEventListener(type,callback){this.events.get(type)?.delete(callback);}
    postMessage(value,transfer=[]){if(transferError)throw new Error(transferError);this.messages.push({value,transfer});}
    terminate(){this.terminations++;}
    emit(type,data){const event=type==='message'?{data}:data;for(const callback of this.events.get(type)||[])callback({...event,currentTarget:this});}
  }
  const context=vm.createContext({Worker:MockWorker,DOMException,
    addEventListener:(type,callback)=>{if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(callback);},
    removeEventListener:(type,callback)=>listeners.get(type)?.delete(callback),
    setTimeout:(callback,ms)=>{const id=++nextTimer;timers.set(id,{callback,ms});return id;},
    clearTimeout:id=>timers.delete(id)});
  vm.runInContext(ownerSource.replace(/^export /gm,''),context,{filename:'public-qemu-engine-owner.js'});
  const dispatch=(type,event)=>{for(const callback of listeners.get(type)||[])callback(event);};
  const create=vm.runInContext('createQemuEngineOwner',context);
  const admit=vm.runInContext('admitQemuEnginePort',context);
  const connect=port=>{owner=create(engineURL,port,()=>errors.push('engine failed'));};
  const ownership=()=>owner.observe(),release=()=>owner.release();
  return {workers,timers,listeners,errors,dispatch,ownership,port:makePort,connect,release,admit};
}

const admission=fixture(),admissionPort=makePort(),returnedPort=makePort(),requests=[];
const iframe={contentWindow:{postMessage(...args){requests.push(args);}}};
const admitted=admission.admit(iframe,origin,'session',admissionPort,new AbortController().signal);
assert.equal(requests.length,1);assert.equal(requests[0][0].sessionId,'session');assert.equal(requests[0][1],origin);
assert.equal(requests[0][2][0],admissionPort);
const response={source:iframe.contentWindow,origin,data:{type:'m5-qemu-admitted',sessionId:'session'},ports:[returnedPort]};
for(const overrides of [
  {source:{}},{origin:'https://other.test'},{data:{type:'m5-qemu-connect',sessionId:'session'}},
  {data:{type:'m5-qemu-admitted',sessionId:'old-session'}},{ports:[]},{ports:[port,extraPort]},
])admission.dispatch('message',{...response,...overrides});
assert.equal(admission.timers.size,1,'foreign or stale events cannot resolve admission');
assert.equal(admission.workers.length,0,'the iframe admission phase does not own a Worker');
admission.dispatch('message',response);
assert.equal(await admitted,returnedPort);assert.equal(admission.timers.size,0);assert.equal(admission.listeners.get('message').size,0);
admission.dispatch('message',{...response,ports:[extraPort]});

const abortedAdmission=fixture(),controller=new AbortController(),abortedPort=makePort();
const aborted=abortedAdmission.admit(iframe,origin,'session',abortedPort,controller.signal);
controller.abort();await assert.rejects(aborted,{name:'AbortError'});
abortedAdmission.dispatch('message',response);
assert.equal(abortedPort.closed,true);assert.equal(abortedAdmission.timers.size,0);
assert.equal(abortedAdmission.listeners.get('message').size,0,'abort releases the admission listener');
assert.equal(abortedAdmission.workers.length,0);

const active=fixture(),privatePort=active.port();active.connect(privatePort);
assert.equal(active.workers.length,1,'admitted port creates exactly one engine owner');
const engine=active.workers[0];
assert.equal(engine.url,engineURL);
assert.equal(engine.options?.type,'module','the QEMU owner is a dedicated module Worker');
assert.equal(active.ownership().engineWorkersCreated,1);
assert.equal(active.ownership().engineOwnerLive,true);
assert.equal(active.ownership().enginePortTransferred,false);
assert.equal(engine.messages.length,0,'do not transfer until engine confirms its listener');
const staleReceive=[...engine.events.get('message')][0];
staleReceive({currentTarget:{},data:{type:'m5-qemu-engine-listening'}});
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
active.ownership().engineWorkersCreated=99;
assert.equal(active.ownership().engineWorkersCreated,1);
engine.emit('message',{type:'m5-qemu-engine-closing'});
assert.equal(active.ownership().engineCloseNotificationReceived,true);
assert.equal(active.ownership().engineCloseNotifications,1);
assert.equal(active.ownership().engineSelfCloseNotifications,1,'the legacy receipt key preserves the notification count');
assert.equal(active.ownership().engineNormalTerminations,0,'the owner acknowledges cooperative self-close');
assert.equal(active.ownership().engineFallbackTerminations,0);
assert.equal(engine.terminations,0,'the owner does not terminate after the notification');
assert.equal(engine.events.get('message').size,0);assert.equal(engine.events.get('error').size,0);
assert.equal(active.listeners.get('pagehide').size,0,'normal close detaches all owner callbacks');
staleReceive({currentTarget:engine,data:{type:'m5-qemu-engine-closing'}});
assert.equal(active.timers.size,0,'acknowledged finalization cannot schedule another termination');
engine.emit('message',{type:'m5-qemu-engine-closing'});
assert.equal(active.ownership().engineCloseNotifications,1,'duplicate notifications cannot invent another close');
active.dispatch('pagehide',{});active.dispatch('pagehide',{});
active.release();
assert.equal(engine.terminations,0,'pagehide cannot force termination after acknowledgement');
assert.equal(active.ownership().engineFallbackTerminations,0);
assert.equal(active.ownership().engineOwnerLive,false);

// Late events do not rewrite an acknowledged self-close as a forced fallback.
const closeFailure=fixture(),closeFailurePort=closeFailure.port();closeFailure.connect(closeFailurePort);
const closeFailureWorker=closeFailure.workers[0];
closeFailureWorker.emit('message',{type:'m5-qemu-engine-listening'});
closeFailureWorker.emit('message',{type:'m5-qemu-engine-closing'});
closeFailureWorker.emit('error',{message:'synthetic error after close notification'});
closeFailureWorker.emit('error',{message:'duplicate error'});
closeFailure.dispatch('pagehide',{});
assert.equal(closeFailure.ownership().engineCloseNotifications,1);
assert.equal(closeFailure.ownership().engineNormalTerminations,0);
assert.equal(closeFailure.ownership().engineFallbackTerminations,0);
assert.equal(closeFailureWorker.terminations,0,'late errors cannot force termination after acknowledgement');
assert.equal(closeFailure.timers.size,0,'late worker errors and pagehide cannot schedule another termination');

for(const transferred of [false,true]){
  const abandoned=fixture(),port=abandoned.port();abandoned.connect(port);
  const worker=abandoned.workers[0];
  if(transferred)worker.emit('message',{type:'m5-qemu-engine-listening'});
  abandoned.release();abandoned.dispatch('pagehide',{});
  assert.equal(worker.terminations,1,'pagehide terminates an unclosed engine exactly once');
  assert.equal(worker.events.get('message').size,0);assert.equal(worker.events.get('error').size,0);
  assert.equal(abandoned.ownership().engineFallbackTerminations,1);
  assert.equal(abandoned.ownership().engineCloseNotifications,0);
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
// A transferred MessagePort cannot carry an owner-side error. Report it to
// the current runtime callback after releasing the failed Worker.
const transferredFailure=fixture(),transferredPort=transferredFailure.port();transferredFailure.connect(transferredPort);
const failedEngine=transferredFailure.workers[0];failedEngine.emit('message',{type:'m5-qemu-engine-listening'});
failedEngine.emit('error',{message:'synthetic post-transfer worker failure'});
assert.equal(transferredFailure.ownership().engineOwnerLive,false,'post-transfer worker error must reclaim the owner');
assert.equal(transferredFailure.ownership().engineFallbackTerminations,1);
assert.equal(failedEngine.terminations,1);assert.equal(transferredFailure.timers.size,0);
assert.deepEqual(transferredFailure.errors,['engine failed']);
transferredFailure.dispatch('pagehide',{});assert.equal(failedEngine.terminations,1);

console.log('private QEMU iframe ownership/origin/one-port/transfer, acknowledged cooperative finalization without fallback, startup/error/timeout/pagehide contracts passed; no guest executed');
