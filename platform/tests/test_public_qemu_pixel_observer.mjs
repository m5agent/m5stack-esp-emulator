// Host-only contracts. Fake page values do not establish guest or browser PASS.
import assert from 'node:assert/strict';
import {isMatchingCanvasObservation,waitForCanvasPixels} from './public_qemu_pixel_observer.mjs';

const regions=[
  {name:'primary',x:10,y:10,width:2,height:2,expected:'a'.repeat(64)},
  {name:'secondary',x:50,y:20,width:2,height:2,expected:'b'.repeat(64)},
];
const boundary={minimumSequence:10,notBeforeMs:100};
const options={regions,boundary};
const observation=(change={})=>({frame_sequence:11,captured_ms:101,width:320,height:240,
  regions:regions.map(r=>({name:r.name,rgba_sha256:r.expected})),...change});
let assertions=0;
function rejected(value,name){
  assert.equal(isMatchingCanvasObservation(value,options),false,name);assertions++;
}
for(const value of [false,true,null,undefined,0,1,'matched',[],Promise.resolve(observation()),new Boolean(true),new Date()])rejected(value,'Only a real matching plain observation can succeed');
class Observation {constructor(){Object.assign(this,observation());}}
rejected(new Observation(),'Class instances are not observation records');
rejected({...observation(),then(){}},'Thenables cannot masquerade as resolved observations');
rejected({matched:true},'A claimed match is not pixel evidence');
rejected({...observation(),matched:true,regions:[{name:'primary',rgba_sha256:'c'.repeat(64)},{name:'secondary',rgba_sha256:'b'.repeat(64)}]},'A claimed match cannot override actual hash mismatch');
for(const sequence of [10,9,-1,11.5,NaN,Infinity,Number.MAX_SAFE_INTEGER+1,'11'])rejected(observation({frame_sequence:sequence}),'Frame sequence must be a fresh finite safe integer');
for(const time of [99.999,NaN,Infinity,'101',undefined])rejected(observation({captured_ms:time}),'Capture time must satisfy the actual boundary');
for(const value of [
  observation({regions:[]}),
  observation({regions:[{name:'primary',rgba_sha256:'a'.repeat(64)}]}),
  observation({regions:[{name:'primary',rgba_sha256:'a'.repeat(64)},{name:'primary',rgba_sha256:'b'.repeat(64)}]}),
  observation({regions:[{name:'other',rgba_sha256:'a'.repeat(64)},{name:'secondary',rgba_sha256:'b'.repeat(64)}]}),
  observation({regions:[{name:'primary',rgba_sha256:'short'},{name:'secondary',rgba_sha256:'b'.repeat(64)}]}),
  observation({regions:[{name:'primary',rgba_sha256:'a'.repeat(64)},{name:'secondary',rgba_sha256:'c'.repeat(64)}]}),
  observation({regions:[{name:'primary',rgba_sha256:'a'.repeat(64)},{name:'secondary',rgba_sha256:'b'.repeat(64)},{name:'extra',rgba_sha256:'c'.repeat(64)}]}),
  observation({width:319}),observation({height:239}),
])rejected(value,'Both uniquely named actual ROI hashes are required');
assert.equal(isMatchingCanvasObservation(observation(),options),true);
assert.equal(isMatchingCanvasObservation(observation({captured_ms:100}),options),true,'The timestamp boundary is inclusive');
assert.equal(isMatchingCanvasObservation({frame_sequence:0,captured_ms:0,regions:observation().regions},{regions,boundary:{minimumSequence:-1,notBeforeMs:0}}),true,'The cold boundary can admit actual frame0');
assertions+=3;

class FakePage {
  constructor(values){this.values=values;this.calls=[];this.pending=0;this.maxPending=0;}
  waitForFunction(){throw new Error('Pixel polling must not delegate an async predicate to Playwright waitForFunction');}
  async evaluate(fn,arg){
    this.pending++;this.maxPending=Math.max(this.maxPending,this.pending);this.calls.push({fn,arg});
    try{const next=this.values.length>1?this.values.shift():this.values[0];return typeof next==='function'?await next():await next;}
    finally{this.pending--;}
  }
}
const firstValid=observation(),secondValid=observation({frame_sequence:12,captured_ms:102});
const page=new FakePage([Promise.resolve(false),observation({frame_sequence:10}),observation({captured_ms:99}),firstValid,secondValid]);
const found=await waitForCanvasPixels(page,{...options,timeoutMs:100,pollingMs:1});
assert.equal(found,firstValid,'Return the first matching observation object, never false or a later value');
assert.equal(page.calls.length,4,'False, stale sequence and stale time each require another awaited evaluation');
assert.equal(page.maxPending,1,'Each page evaluation must finish before another begins');
for(const call of page.calls){
  const args=JSON.stringify(call.arg);
  assert.ok(!args.includes('a'.repeat(64))&&!args.includes('b'.repeat(64)),'Do not pass expected hashes into the page sampler');
}
const delayed=observation({frame_sequence:13});
const delayedPage=new FakePage([()=>new Promise(done=>setTimeout(()=>done(false),5)),()=>new Promise(done=>setTimeout(()=>done(delayed),5))]);
assert.equal(await waitForCanvasPixels(delayedPage,{...options,timeoutMs:100,pollingMs:1}),delayed);
assert.equal(delayedPage.maxPending,1);
const falsePage=new FakePage([Promise.resolve(false)]);
await assert.rejects(waitForCanvasPixels(falsePage,{...options,timeoutMs:15,pollingMs:1}),error=>{
  assert.match(error.message,/timeout|timed out/i);
  assert.equal(error.lastObservation,false,'Timeout retains the actual false observation');
  return true;
});
const wrong=observation({matched:true,regions:[{name:'primary',rgba_sha256:'f'.repeat(64)},{name:'secondary',rgba_sha256:'b'.repeat(64)}]});
await assert.rejects(waitForCanvasPixels(new FakePage([wrong]),{...options,timeoutMs:15,pollingMs:1}),error=>{
  assert.equal(error.lastObservation,wrong,'Timeout retains actual wrong hashes, not a synthesized match');return true;
});
await assert.rejects(waitForCanvasPixels(new FakePage([()=>new Promise(()=>{})]),{...options,timeoutMs:15,pollingMs:1}),error=>{
  assert.match(error.message,/timeout|timed out/i);
  assert.equal(error.lastObservation,null,'A hung first evaluation cannot invent an observation');return true;
});
console.log(`HOST_CANVAS_PIXEL_OBSERVER_OK: ${assertions} value contracts, explicit await/first-object/single-flight/timeout controls; no browser or guest executed`);
