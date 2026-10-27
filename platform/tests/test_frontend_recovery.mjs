// Deterministic orchestration faults only; no browser, HTTP, firmware or QEMU.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const sourceRoot=resolve(process.argv[2] || '.');
const output=process.argv[3];
const sessionSource=await readFile(resolve(sourceRoot,'platform/web/sessions.js'),'utf8');
const panelSource=await readFile(resolve(sourceRoot,'platform/web/unit-panel.js'),'utf8');
const mappingSource=await readFile(resolve(sourceRoot,'platform/web/unit-visual-mappings.js'),'utf8');
const {arrayLedFeedback}=await import(pathToFileURL(resolve(sourceRoot,'platform/web/unit-visual-mappings.js')).href);
const sessionClass=sessionSource.slice(sessionSource.indexOf('class SessionVisual {'),sessionSource.indexOf('\nfunction createSessionCard'));
const panelClass=panelSource.slice(panelSource.indexOf('class UnitPanel {'),panelSource.indexOf('\nexport async function createUnitPanel'));
const deferred=()=>{let resolve,reject;const promise=new Promise((r,j)=>{resolve=r;reject=j;});return {promise,resolve,reject};};
function visualFixture({frame=true,lateMount=true,container=null,failImage=false}={}) {
  const requests=[],trace=[];
  const state={deviceProfiles:new Map([['fixture',{}]]),devicePaths:new Map([['fixture','fixture']])};
  const create=host=>{const gate=deferred();gate.mount=host;requests.push(gate);return gate.promise.then(()=>{if(lateMount)host.content='late-shell';return {dispose(){trace.push('dispose-stale');if(host.content==='late-shell')host.content='';},setViewMode(){},on(){},setImage:async()=>{if(failImage)throw Error('fixture image decode failed');return true;}};});};
  const node=()=>({style:{},_content:'',children:[],get content(){return this.children.length?this.children.map(child=>child.content).join(''):this._content;},set content(value){this._content=value;this.children=[];},replaceChildren(...children){this._content='';this.children=children;},classList:{add(){},remove(){}}});
  const Visual=new Function('document','state','createDeviceShell','CONTROL_RELEASE_TIMEOUT_MS','api','framePlaceholder',sessionClass+'\nreturn SessionVisual;')({createElement:node},state,create,5000,async()=>{},()=> 'waiting');
  const visual=Object.create(Visual.prototype);
  Object.assign(visual,{container:container || node(),session:{device_id:'fixture',state:'running'},allowThree:true,threeAttempted:false,shellLoading:false,shellGeneration:0,destroyed:false,shell:null,unitPanel:null,frameBlob:frame?{}:null,activeControls:new Set(),controlReleaseTimers:new Map(),frameApply:Promise.resolve()});
  visual.setGenericFrame=()=>{visual.container.content='generic-frame';trace.push('frame');};
  visual.setMessage=()=>{visual.container.content='placeholder';trace.push('placeholder');};
  return {visual,requests,trace};
}
const Panel=new Function('window','document','copy','ACTIVE','clearTimeout','setTimeout','arrayLedFeedback',panelClass+'\nreturn UnitPanel;')({addEventListener(){},removeEventListener(){}},{hidden:false},structuredClone,new Set(['booting','running']),()=>{},()=>1,arrayLedFeedback);
function panelFixture({array=false,failUps=0,appliedBeforeFailure=false}={}) {
  let failures=failUps,guest=array?[false,true,false]:false,available=true;
  const posts=[],notes=[],field=array?'keys':'pressed';
  let getGate=null;
  const payload=()=>({source:'live',units:[{id:'u',unit_id:array?'cardkb':'button',available,errors:{},properties:{[field]:structuredClone(guest)}}]});
  const api=async(path,options)=>{
    if(options?.method==='POST') {
      const values=JSON.parse(options.body).values;posts.push(structuredClone(values));
      const next=values[field];const up=array?guest[0]===true&&next[0]===false:guest===true&&next===false;
      if(up&&failures>0){failures--;if(appliedBeforeFailure)guest=structuredClone(next);throw Error('fixture release request lost');}
      guest=structuredClone(next);return payload();
    }
    if(getGate){const gate=getGate;getGate=null;return gate.promise;}
    return payload();
  };
  const panel=new Panel({replaceChildren(){}},{session:{session_id:'offline-recovery-fixture',state:'running',units:[{id:'u',unit_id:array?'cardkb':'button'}]},shell:null,api});
  panel.note=(id,message)=>notes.push(message);panel.states.set('u',payload().units[0]);
  return {panel,posts,notes,field,setAvailable(value){available=value;},get guest(){return guest;},hold(down,index=array?0:undefined){panel.setHeld('u',field,index,'form:pointer:1',down);},blockGet(){getGate=deferred();return getGate;},payload,async drain(){for(let i=0;i<5;i++){const next=panel.queues.get('u');await next;if(next===panel.queues.get('u'))return;}throw Error('unexpected queue churn');}};
}
const cases=[];
async function test(name,run){try{await run();cases.push({name,status:'PASS'});}catch(error){cases.push({name,status:'FAIL',error:error.message});}}
await test('late-shell-demotion-restores-saved-frame',async()=>{const f=visualFixture();const p=f.visual.init();f.visual.setThreeAllowed(false);f.requests[0].resolve();await p;assert.equal(f.visual.container.content,'generic-frame');assert.equal(f.visual.shell,null);});
await test('late-shell-without-frame-restores-placeholder',async()=>{const f=visualFixture({frame:false});const p=f.visual.init();f.visual.setThreeAllowed(false);f.requests[0].resolve();await p;assert.equal(f.visual.container.content,'placeholder');});
await test('destroyed-visual-is-not-restored',async()=>{const f=visualFixture();const p=f.visual.init();f.visual.destroyed=true;f.requests[0].resolve();await p;assert.deepEqual(f.trace,['dispose-stale']);});
await test('stale-cleanup-does-not-replace-current-owner',async()=>{const f=visualFixture();const p=f.visual.init();f.visual.shellGeneration++;const owner={};f.visual.shell=owner;f.visual.container.content='new-owner';f.requests[0].resolve();await p;assert.equal(f.visual.shell,owner);assert.equal(f.visual.container.content,'new-owner');assert.deepEqual(f.trace,['dispose-stale']);});
await test('destroyed-load-cannot-clear-reused-host-owner',async()=>{const f=visualFixture();const p=f.visual.init();f.visual.destroyed=true;const next=visualFixture({container:f.visual.container});next.visual.container.content='new-session-owner';f.requests[0].resolve();await p;assert.equal(next.visual.container.content,'new-session-owner');assert.notEqual(f.requests[0].mount,next.visual.container);});
await test('reallow-three-retries-only-latest-generation',async()=>{const f=visualFixture();const p=f.visual.init();f.visual.setThreeAllowed(false);f.visual.setThreeAllowed(true);f.requests[0].resolve();await p;assert.equal(f.requests.length,2);f.requests[1].resolve();await new Promise(r=>setImmediate(r));assert.ok(f.visual.shell);assert.equal(f.visual.container.content,'late-shell');});
await test('late-shell-rejection-after-demotion-preserves-frame',async()=>{const f=visualFixture();const p=f.visual.init();f.visual.setThreeAllowed(false);f.requests[0].reject(Error('fixture late load rejected'));await p;assert.equal(f.visual.container.content,'generic-frame');});
await test('late-rejection-cannot-clear-reused-host-after-destroy',async()=>{const f=visualFixture();const p=f.visual.init();f.visual.destroyed=true;const next=visualFixture({container:f.visual.container});next.visual.container.content='new-session-owner';f.requests[0].reject(Error('fixture late load rejected'));await p;assert.equal(next.visual.container.content,'new-session-owner');});
await test('late-rejection-preserves-new-shell-owner',async()=>{const f=visualFixture();const p=f.visual.init();f.visual.shellGeneration++;const owner={};f.visual.shell=owner;f.visual.container.content='new-owner';f.requests[0].reject(Error('fixture late load rejected'));await p;assert.equal(f.visual.shell,owner);assert.equal(f.visual.container.content,'new-owner');});
await test('committed-image-failure-detaches-and-disposes-owned-shell',async()=>{const f=visualFixture({failImage:true});const bindings=[];f.visual.unitPanel={setShell(shell){bindings.push(shell);}};const p=f.visual.init();f.requests[0].resolve();await p;assert.equal(f.visual.shell,null);assert.equal(f.visual.container.content,'generic-frame');assert.equal(bindings.length,2);assert.equal(bindings[1],null);assert.ok(f.trace.includes('dispose-stale'));});
await test('normal-release-adds-no-extra-post',async()=>{const f=panelFixture();f.hold(true);await f.drain();f.hold(false);await f.drain();await f.panel.refresh();await f.drain();assert.equal(f.posts.length,2);assert.equal(f.guest,false);assert.equal((f.panel.releaseIntents?.size || 0),0);});
await test('lost-release-recovers-on-new-get-once',async()=>{const f=panelFixture({failUps:1});f.hold(true);await f.drain();f.hold(false);await f.drain();assert.equal(f.guest,true);await f.panel.refresh();await f.drain();assert.equal(f.guest,false);assert.equal(f.posts.length,3);assert.equal((f.panel.releaseIntents?.size || 0),0);});
await test('array-recovery-preserves-unowned-held-index',async()=>{const f=panelFixture({array:true,failUps:1});f.hold(true);await f.drain();f.hold(false);await f.drain();await f.panel.refresh();await f.drain();assert.deepEqual(f.guest,[false,true,false]);assert.deepEqual(f.posts.at(-1).keys,[false,true,false]);});
await test('repress-cancels-previous-release-intent',async()=>{const f=panelFixture({failUps:1});f.hold(true);await f.drain();f.hold(false);await f.drain();f.hold(true);await f.drain();await f.panel.refresh();await f.drain();assert.equal(f.guest,true);assert.equal(f.posts.length,3);assert.equal((f.panel.releaseIntents?.size || 0),0);});
await test('stale-get-started-before-release-failure-is-not-recovery',async()=>{const f=panelFixture({failUps:1});f.hold(true);await f.drain();const gate=f.blockGet();const stale=f.panel.refresh();f.hold(false);await f.drain();gate.resolve(f.payload());await stale;await f.drain();assert.equal(f.posts.length,2);assert.equal(f.guest,true);await f.panel.refresh();await f.drain();assert.equal(f.posts.length,3);assert.equal(f.guest,false);});
await test('already-applied-release-is-confirmed-without-retry',async()=>{const f=panelFixture({failUps:1,appliedBeforeFailure:true});f.hold(true);await f.drain();f.hold(false);await f.drain();await f.panel.refresh();await f.drain();assert.equal(f.posts.length,2);assert.equal(f.guest,false);assert.equal((f.panel.releaseIntents?.size || 0),0);});
await test('permanent-failure-is-bounded-and-keeps-intent',async()=>{const f=panelFixture({failUps:100});f.hold(true);await f.drain();f.hold(false);await f.drain();for(let i=0;i<8;i++){await f.panel.refresh();await f.drain();}assert.equal(f.posts.length,3);assert.equal((f.panel.releaseIntents?.size || 0),1);assert.ok(f.notes.some(n=>n.includes('松开')));});
for(const terminal of ['stopped','failed'])await test(`${terminal}-cancels-pending-compensation`,async()=>{const f=panelFixture({failUps:1});f.hold(true);await f.drain();f.hold(false);await f.drain();const gate=deferred();f.panel.queues.set('u',gate.promise);await f.panel.refresh();f.panel.updateSession({...f.panel.session,state:terminal});gate.resolve();await f.drain();assert.equal(f.posts.length,2);assert.equal((f.panel.releaseIntents?.size || 0),0);});
await test('dispose-cancels-pending-compensation',async()=>{const f=panelFixture({failUps:1});f.hold(true);await f.drain();f.hold(false);await f.drain();const gate=deferred();f.panel.queues.set('u',gate.promise);await f.panel.refresh();f.panel.dispose();gate.resolve();await f.drain();assert.equal(f.posts.length,2);assert.equal((f.panel.releaseIntents?.size || 0),0);});
await test('queued-unavailable-does-not-consume-compensation-budget',async()=>{const f=panelFixture({failUps:1});f.hold(true);await f.drain();f.hold(false);await f.drain();const gate=deferred();f.panel.queues.set('u',gate.promise);await f.panel.refresh();f.setAvailable(false);f.panel.states.set('u',f.payload().units[0]);gate.resolve();await f.drain();assert.equal(f.posts.length,2);const intent=[...f.panel.releaseIntents.values()][0];assert.equal(intent.retried,false);assert.equal(intent.queued,false);f.setAvailable(true);await f.panel.refresh();await f.drain();assert.equal(f.posts.length,3);assert.equal(f.guest,false);});
await test('repress-while-compensation-is-queued-cancels-old-release',async()=>{const f=panelFixture({failUps:1});f.hold(true);await f.drain();f.hold(false);await f.drain();const gate=deferred();f.panel.queues.set('u',gate.promise);await f.panel.refresh();f.hold(true);gate.resolve();await f.drain();assert.equal(f.posts.length,3);assert.equal(f.guest,true);assert.equal((f.panel.releaseIntents?.size || 0),0);});
await test('unowned-direct-input-does-not-create-recovery-or-echo',async()=>{const f=panelFixture({failUps:1});await f.panel.send('u',{pressed:true});await f.panel.send('u',{pressed:false});await f.panel.refresh();await f.drain();assert.equal(f.posts.length,2);assert.equal(f.guest,true);assert.equal((f.panel.releaseIntents?.size || 0),0);});
const report={category:'frontend-orchestration-fault-contract',status:cases.every(c=>c.status==='PASS')?'PASS':'FAIL',browser_execution:'NOT RUN',firmware_execution:'NOT RUN',hardware_execution:'NOT RUN',source_sha256:{'platform/web/unit-visual-mappings.js':createHash('sha256').update(mappingSource).digest('hex'),'platform/web/sessions.js':createHash('sha256').update(sessionSource).digest('hex'),'platform/web/unit-panel.js':createHash('sha256').update(panelSource).digest('hex')},cases};
if(output)await writeFile(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
process.exitCode=report.status==='PASS'?0:1;
