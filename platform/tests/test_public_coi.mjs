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
for (const project of ['https://example.test/','https://example.test/showcase/']) {
  let imported;
  vm.runInNewContext(wrapper,{URL,self:{location:{href:project+'coi-serviceworker.js'}},importScripts:url=>{imported=url;}});
  assert.equal(imported,project+'platform/web/vendor/coi-serviceworker/coi-serviceworker.js');
}
console.log('public COI scope, activation/control ordering, one-reload guard, timeouts and pinned source contracts passed');
