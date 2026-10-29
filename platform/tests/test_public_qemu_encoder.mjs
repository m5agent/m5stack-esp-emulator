// Actual shell/page routing methods with host doubles; no QEMU guest is run.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {getQemuBrowserProfile,advanceQemuEncoderTarget,qemuInputCommand} from '../web/public-qemu-profiles.js';
const registry=JSON.parse(await readFile(new URL('../web/qemu-browser-profiles.json',import.meta.url),'utf8'));
const dial=getQemuBrowserProfile('dial',registry,{allowCandidateProfiles:true});
const shellSource=await readFile(new URL('../web/model-shell.js',import.meta.url),'utf8');
const method=shellSource.slice(shellSource.indexOf('  handleInput(event) {'),shellSource.indexOf('\n  setViewMode(',shellSource.indexOf('  handleInput(event) {')));
assert.ok(method.startsWith('  handleInput(event) {') && method.endsWith('\n  }\n'));
const route=vm.runInNewContext(`(class {${method}}).prototype.handleInput`);
const events=[];
const shell={device:{id:'dial'},model:{find:()=>({meta:{role:'visual-rotary-input',detentsPerTurn:16}})},
 emit:(type,value)=>events.push({type,value})};
const gesture={kind:'joint',id:'rotation',action:'rotate',deltaDeg:22.5,source:'pointer'};
route.call(shell,gesture);
assert.deepEqual(JSON.parse(JSON.stringify(events)),[{type:'model-input',value:gesture},{type:'encoder',value:{deltaDegrees:22.5,source:'pointer'}}]);
for(const [patch,expected] of [[{deltaDeg:-45},1],[{deltaDeg:Infinity},0],[{deltaDeg:181},0],[{id:'unknown'},0],
 [{kind:'component'},0],[{action:'set'},0],[{source:'runtime-readback'},0]]) {
 events.length=0;route.call(shell,{...gesture,...patch});assert.equal(events.filter(row=>row.type==='encoder').length,expected);
}
events.length=0;shell.device.visual_only=true;route.call(shell,gesture);assert.equal(events.filter(row=>row.type==='encoder').length,0);
shell.device.visual_only=false;shell.model.find=()=>({meta:{role:'visual-rotary-input',detentsPerTurn:20}});
events.length=0;route.call(shell,gesture);assert.equal(events.filter(row=>row.type==='encoder').length,0);
const pageSource=await readFile(new URL('../web/public.js',import.meta.url),'utf8');
assert.match(pageSource,/shell\.on\?\.\('encoder', event => void deliverEncoderInput\(event\)\)/);
const start=pageSource.indexOf('async function deliverEncoderInput(event) {');
const handler=pageSource.slice(start,pageSource.indexOf('\nasync function stopRun()',start));
assert.ok(start>0 && handler.endsWith('\n}'));
const commands=[],errors=[];
class PublicQemuRuntime {constructor(profile){this.profile=profile;}async input(command){qemuInputCommand(this.profile,command);commands.push(command);return {detents:command.detents,source:'host-double-no-guest'};}}
const state={busy:false,run:{kind:'browser',controller:new PublicQemuRuntime(dial)}};
const deliver=vm.runInNewContext(`(${handler})`,{state,PublicQemuRuntime,advanceQemuEncoderTarget,
 active:run=>run===state.run&&!run.stopping,error:err=>errors.push(err.message)});
await deliver({deltaDegrees:11.25});assert.equal(commands.length,0);
await deliver({deltaDegrees:11.25});assert.deepEqual(JSON.parse(JSON.stringify(commands)),[{type:'encoder',detents:1}]);
await deliver({deltaDegrees:-45});assert.equal(commands.at(-1).detents,-1);
assert.deepEqual(JSON.parse(JSON.stringify(state.run.encoderGesture)),{target:-1,remainderDegrees:0});
assert.equal(Object.hasOwn(state.run,'guestCount'),false,'gesture state must never pose as guest count');
state.run={kind:'browser',controller:new PublicQemuRuntime(dial)};
await deliver({deltaDegrees:22.5});assert.equal(commands.at(-1).detents,1,'new run starts a fresh physical target');
for(const change of [run=>run.stopping=true,run=>run.kind='service',run=>run.controller.profile=getQemuBrowserProfile('stickc-plus2',registry,{allowCandidateProfiles:true})]) {
 state.run={kind:'browser',controller:new PublicQemuRuntime(dial)};change(state.run);const n=commands.length;await deliver({deltaDegrees:22.5});assert.equal(commands.length,n);
}
assert.deepEqual(errors,[]);
console.log('Dial actual shell/page rotary routing, fresh-run target, signed fractional gesture and feedback/inactive guards passed; no guest executed');
