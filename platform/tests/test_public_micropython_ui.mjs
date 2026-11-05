// Actual UI handlers with a minimal DOM and a delayed transport. Host contracts
// only: this tests ownership/event scheduling, never firmware execution.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import {PublicQemuRuntime} from '../web/public-qemu-runtime.js';
import {PublicMicroPythonRunner} from '../web/public-micropython.js';

const source=await fs.readFile(new URL('../web/public.js',import.meta.url),'utf8');
const functions=source.slice(source.indexOf('const pythonPhases='),source.indexOf('function updateCapability()'));
const serial=source.slice(source.indexOf("$('serialForm').addEventListener('submit'"),source.indexOf("$('browserPir').addEventListener('change'"));
const keyboard=source.slice(source.indexOf("$('pythonSource').addEventListener('keydown'"),source.indexOf("$('serialForm').addEventListener('submit'"));
assert.ok(functions.startsWith('const pythonPhases=')&&serial&&keyboard,'the production handlers must be exercised');
function fixture(){
  const handlers=new Map(),nodes={},errors=[],writes=[];
  for(const id of ['serialForm','serialInput','serialSendBtn','pythonSource','pythonRunBtn','pythonInterruptBtn','pythonStatus','pythonOutput','pauseBtn'])
    nodes[id]={disabled:false,textContent:'',value:'',addEventListener:(type,handler)=>handlers.set(id+':'+type,handler)};
  nodes.serialInput.value='x'.repeat(2050);nodes.pythonSource.value='print(1)';
  const runtime=new PublicQemuRuntime({root:'https://example.test/'});
  Object.assign(runtime,{generation:1,sessionId:'ui-guest',status:'running',profile:{inputs:{uart:true}},
    waiters:new Map(),machineEvents:[],serial:''});
  let acknowledge;
  runtime.ask=async(op,value)=>{assert.equal(op,'uart');writes.push(value);if(writes.length===1)await new Promise(resolve=>acknowledge=resolve);return {queued:value.bytes.length};};
  const run={kind:'browser',generation:1,controller:runtime};
  const state={run,runGeneration:1};
  const context={state,$:id=>nodes[id],active:value=>value===state.run&&value.generation===state.runGeneration&&!value.stopping,
    PublicQemuRuntime,PublicMicroPythonRunner,TextEncoder,Uint8Array,DOMException,
    error:error=>{if(error.name!=='AbortError')errors.push(error);}};
  vm.createContext(context);vm.runInContext(functions+'\n'+serial+'\n'+keyboard,context);
  context.updatePythonControls();
  return {context,run,runtime,nodes,handlers,errors,writes,ack:()=>acknowledge()};
}
{
  const test=fixture(),send=test.handlers.get('serialForm:submit');
  const sending=send({preventDefault(){}});
  assert.equal(test.run.serialSending,true);assert.equal(test.nodes.pythonRunBtn.disabled,true);assert.equal(test.nodes.serialSendBtn.disabled,true);
  assert.equal(test.nodes.pauseBtn.disabled,true,'pause cannot split an ordinary UART transfer');
  await test.context.runPython();await send({preventDefault(){}});
  assert.equal(test.writes.length,1,'Run and repeated Send cannot interleave with the pending first chunk');
  test.ack();await sending;
  assert.deepEqual(test.writes.map(row=>row.bytes.length),[1024,1024,4]);
  assert.ok(test.writes.every(row=>row.bytes.every(byte=>byte===120||byte===13||byte===10)));
  assert.equal(test.runtime.uartOwner,null);assert.equal(test.run.serialSending,false);
  assert.equal(test.nodes.pythonRunBtn.disabled,false);assert.equal(test.nodes.serialSendBtn.disabled,false);assert.deepEqual(test.errors,[]);
}
{
  const test=fixture(),sending=test.handlers.get('serialForm:submit')({preventDefault(){}});
  test.runtime.receive({type:'machine-event',value:{event:'RESET',consoleEpoch:1}},1);
  const nextOwner=test.runtime.acquireUart();test.ack();await sending;
  assert.equal(test.writes.length,1,'no remaining serial chunks can enter the next hardware boot');
  assert.equal(test.runtime.uartOwner,nextOwner,'old UI cleanup cannot release the new console owner');
  assert.equal(test.run.serialSending,false);assert.deepEqual(test.errors,[]);test.runtime.releaseUart(nextOwner);
}
{
  const test=fixture(),keydown=test.handlers.get('pythonSource:keydown');let prevented=0,ran=0;
  test.context.runPython=()=>ran++;
  for(const shiftKey of [false,true])keydown({key:'Tab',shiftKey,stopPropagation(){},preventDefault(){prevented++;}});
  assert.equal(prevented,0,'Tab and Shift+Tab retain native focus navigation');
  keydown({key:'Enter',ctrlKey:true,stopPropagation(){},preventDefault(){prevented++;}});
  keydown({key:'Enter',metaKey:true,stopPropagation(){},preventDefault(){prevented++;}});
  assert.equal(ran,2,'Ctrl/Cmd+Enter still run code');assert.equal(prevented,2);
  test.nodes.pythonRunBtn.disabled=true;
  keydown({key:'Enter',ctrlKey:true,stopPropagation(){},preventDefault(){}});assert.equal(ran,2,'shortcut respects UART ownership controls');
}
{
  const test=fixture(),pending=[];
  Object.assign(test.run,{kind:'service',controller:{current:{state:'running'}}});
  const native=test.run.python={ready:true,busy:false,canInterrupt:true,canReplace:false,
    run(_source,options){this.busy=true;options.onPhase('running');return new Promise((resolve,reject)=>pending.push({options,resolve,reject}));}};
  const first=test.context.runPython();
  assert.equal(test.nodes.pythonInterruptBtn.disabled,false,'native code keeps its real cancellation available while busy');
  assert.equal(test.nodes.serialSendBtn.disabled,true,'raw UART cannot race a managed native program');
  await test.context.runPython();assert.equal(pending.length,1,'managed Run cannot overlap the current transfer');
  native.canReplace=true;test.context.updatePythonControls();
  assert.equal(test.nodes.pythonRunBtn.disabled,false,'ordinary legacy sessions can explicitly replace running code');
  const second=test.context.runPython();assert.equal(pending.length,2);
  pending[1].options.onOutput('new output');pending[1].options.onPhase('complete');native.busy=false;pending[1].resolve();await second;
  pending[0].options.onOutput('late output');pending[0].reject(new Error('late observer'));await first;
  assert.equal(test.nodes.pythonOutput.textContent,'new output','old execution observations cannot overwrite the replacement editor');
  assert.equal(test.run.pythonPhase,'complete');
  native.canInterrupt=false;native.busy=true;test.run.pythonPhase='running';test.context.updatePythonControls();
  assert.equal(test.nodes.pythonInterruptBtn.disabled,true,'legacy sessions never advertise a missing interrupt API');
}
console.log('MicroPython UI serial ownership, reset cancellation, native programming and replacement generation contracts passed');
