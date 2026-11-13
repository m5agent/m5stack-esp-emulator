import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import vm from 'node:vm';
import {ensurePublicIsolation,COI_SOURCE_COMMIT,COI_SOURCE_SHA256} from '../web/public-coi.js';

const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve,reject; const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject}; }
class ServiceWorkers extends EventTarget {
  constructor() { super(); this.activation=deferred();this.ready=this.activation.promise;this.calls=[];this.messages=[];this.listenerCount=0; }
  register(url,options) { this.calls.push({url,options});return Promise.resolve({scope:options.scope}); }
  addEventListener(...args) { this.listenerCount++;super.addEventListener(...args); }
  removeEventListener(...args) { this.listenerCount--;super.removeEventListener(...args); }
  control(url=this.calls[0].url) { this.controller={scriptURL:url,postMessage:message=>this.messages.push(message)};this.dispatchEvent(new Event('controllerchange')); }
}
function environment() {
  const values=new Map(),sw=new ServiceWorkers();
  return {location:{href:'https://example.test/showcase/?device=cores3#screen'},isSecureContext:true,crossOriginIsolated:false,SharedArrayBuffer,
    navigator:{serviceWorker:sw},sessionStorage:{getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)},values,sw};
}
const root='https://example.test/showcase/';
const first=environment();let reloads=0;
const one=ensurePublicIsolation({root,environment:first,reload:()=>reloads++});
const two=ensurePublicIsolation({root,environment:first,reload:()=>reloads++});
await tick();assert.equal(first.sw.calls.length,1);assert.equal(reloads,0);
assert.deepEqual(first.sw.calls[0],{url:root+'coi-serviceworker.js',options:{scope:root,updateViaCache:'none'}});
first.sw.control();await tick();assert.equal(reloads,0,'controllerchange alone must not reload before ready');
first.sw.activation.resolve();const results=await Promise.all([one,two]);
assert.equal(reloads,1);assert.ok(results.every(result=>!result.isolated&&result.reloading));
assert.deepEqual(first.sw.messages,[{type:'coepCredentialless',value:false}]);assert.equal(first.sw.listenerCount,0);
await assert.rejects(ensurePublicIsolation({root,environment:first,reload:()=>reloads++}),{code:'coi_isolation_failed'});
assert.equal(reloads,1,'a failed post-reload isolation must not loop');
first.crossOriginIsolated=true;
assert.equal((await ensurePublicIsolation({root,environment:first})).isolated,true);assert.equal(first.values.size,0);
assert.equal(first.sw.calls.length,1,'already isolated pages do not register or reload');

const readyFirst=environment();let readyReloads=0;readyFirst.sw.activation.resolve();
const preparation=ensurePublicIsolation({root,environment:readyFirst,reload:()=>readyReloads++});await tick();
readyFirst.sw.control('https://example.test/unrelated-worker.js');await tick();assert.equal(readyReloads,0);
readyFirst.sw.control();await preparation;assert.equal(readyReloads,1);

const insecure=environment();insecure.isSecureContext=false;
await assert.rejects(ensurePublicIsolation({root,environment:insecure}),{code:'coi_insecure_context'});assert.equal(insecure.sw.calls.length,0);
const unavailable=environment();unavailable.navigator={};
await assert.rejects(ensurePublicIsolation({root,environment:unavailable}),{code:'coi_unavailable'});
for (const invalid of ['https://other.test/showcase/','https://example.test/other/','https://example.test/showcase','https://example.test/showcase/?scope=1']) {
  await assert.rejects(ensurePublicIsolation({root:invalid,environment:environment()}),{code:'coi_invalid_scope'});
}
const storageBlocked=environment();Object.defineProperty(storageBlocked,'sessionStorage',{get(){throw new Error('blocked');}});
await assert.rejects(ensurePublicIsolation({root,environment:storageBlocked}),{code:'coi_storage_unavailable'});
storageBlocked.crossOriginIsolated=true;
assert.equal((await ensurePublicIsolation({root,environment:storageBlocked})).isolated,true,'server isolation must work without session storage');
const wrongScope=environment();wrongScope.sw.register=async()=>({scope:'https://example.test/'});
await assert.rejects(ensurePublicIsolation({root,environment:wrongScope}),{code:'coi_invalid_scope'});
const rejected=environment();rejected.sw.register=async()=>{throw new Error('404');};
await assert.rejects(ensurePublicIsolation({root,environment:rejected}),{code:'coi_registration_failed'});
const slowRegistration=environment();slowRegistration.sw.register=()=>new Promise(()=>{});
await assert.rejects(ensurePublicIsolation({root,environment:slowRegistration,timeoutMs:10}),{code:'coi_registration_timeout'});
const slowControl=environment();slowControl.sw.activation.resolve();
await assert.rejects(ensurePublicIsolation({root,environment:slowControl,timeoutMs:10}),{code:'coi_control_timeout'});assert.equal(slowControl.sw.listenerCount,0);

const vendor=await readFile(new URL('../web/vendor/coi-serviceworker/coi-serviceworker.js',import.meta.url));
assert.equal(createHash('sha256').update(vendor).digest('hex'),COI_SOURCE_SHA256);
assert.match(await readFile(new URL('../web/vendor/coi-serviceworker/NOTICE.md',import.meta.url),'utf8'),new RegExp(COI_SOURCE_COMMIT));
assert.match(await readFile(new URL('../web/vendor/coi-serviceworker/LICENSE',import.meta.url),'utf8'),/MIT License/);
const wrapper=await readFile(new URL('../web/public-coi-serviceworker.js',import.meta.url),'utf8');
const handlers={},lifecycle=[],requests=[];
let nextResponse;
vm.runInNewContext(wrapper,{Headers,Request,Response,fetch:async request=>{requests.push(request);return nextResponse();},
  self:{addEventListener:(type,handler)=>{handlers[type]=handler;},skipWaiting:()=>lifecycle.push('skipWaiting'),
    clients:{claim:async()=>{lifecycle.push('claim');},matchAll:async()=>[{url:'https://example.test/showcase/',navigate:url=>lifecycle.push(['navigate',url])}]},
    registration:{unregister:async()=>{lifecycle.push('unregister');}}}});
handlers.install();let activation;handlers.activate({waitUntil:value=>{activation=value;}});await activation;
assert.deepEqual(lifecycle,['skipWaiting','claim']);
handlers.message({});handlers.message({data:{type:'unknown'}});
const dispatch=request=>{let pending;handlers.fetch({request,respondWith:value=>{pending=value;}});return pending;};
const request=new Request('https://example.test/showcase/frame.png',{cache:'no-store',redirect:'error'});
for (const status of [204,205,304]) {
  nextResponse=()=>({status,statusText:'',headers:{ETag:'"frame"'},body:new ReadableStream()});
  const response=await dispatch(request);
  assert.equal(response.status,status);assert.equal(response.body,null,'null-body HTTP statuses cannot inherit even an empty stream');
  assert.equal(response.headers.get('ETag'),'"frame"');
  assert.equal(response.headers.get('Cross-Origin-Embedder-Policy'),'require-corp');
  assert.equal(response.headers.get('Cross-Origin-Resource-Policy'),'cross-origin');
  assert.equal(response.headers.get('Cross-Origin-Opener-Policy'),'same-origin');
}
nextResponse=()=>new Response('actual bytes',{status:200,headers:{'Content-Type':'image/png','X-Frame-SHA256':'fixture'}});
const ordinary=await dispatch(request);assert.equal(await ordinary.text(),'actual bytes');assert.equal(ordinary.headers.get('X-Frame-SHA256'),'fixture');
const opaque={status:0};nextResponse=()=>opaque;assert.equal(await dispatch(request),opaque);
const beforeGuard=requests.length;assert.equal(dispatch({cache:'only-if-cached',mode:'no-cors'}),undefined);assert.equal(requests.length,beforeGuard);
handlers.message({data:{type:'coepCredentialless',value:true}});
nextResponse=()=>new Response('credentialless');
const credentialless=await dispatch(new Request('https://example.test/image',{mode:'no-cors',credentials:'include'}));
assert.equal(requests.at(-1).credentials,'omit');assert.equal(credentialless.headers.get('Cross-Origin-Embedder-Policy'),'credentialless');
assert.equal(credentialless.headers.get('Cross-Origin-Resource-Policy'),null);assert.equal(credentialless.headers.get('Cross-Origin-Opener-Policy'),'same-origin');
handlers.message({data:{type:'coepCredentialless',value:false}});
nextResponse=()=>{throw new TypeError('fixture network rejection');};await assert.rejects(dispatch(request),/fixture network rejection/);
handlers.message({data:{type:'deregister'}});await new Promise(resolve=>setImmediate(resolve));
assert.deepEqual(lifecycle.slice(-2),['unregister',['navigate','https://example.test/showcase/']]);
console.log('public COI scope, lifecycle, headers, null-body responses, network rejection and pinned original source contracts passed');
