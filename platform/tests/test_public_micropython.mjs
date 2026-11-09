import assert from 'node:assert/strict';
import {PublicMicroPythonRunner} from '../web/public-micropython.js';
import {PublicQemuRuntime} from '../web/public-qemu-runtime.js';

const encode=value=>new TextEncoder().encode(value);
function guest({paste=true,legacy=false,output='hello 世界\r\n',stderr='',forever=false,silent=false,onInterrupt}={}){
  const writes=[],sources=[];
  let phase='connect';
  // Use the actual runtime UART lease and epoch implementation. Only the
  // guest protocol transport is mocked; this does not execute firmware.
  const runtime=new PublicQemuRuntime({root:'https://example.test/'});
  Object.assign(runtime,{generation:1,sessionId:'guest-1',status:'running',profile:{inputs:{uart:true}},
    waiters:new Map(),machineEvents:[],serial:'',writes,sources,listeners:runtime.uartListeners});
  runtime.feed=value=>{for(const fn of runtime.uartListeners)fn(typeof value==='string'?encode(value):Uint8Array.from(value));};
  runtime.ask=async(op,value)=>{
      assert.equal(op,'uart');assert.equal(value.consoleEpoch,runtime.consoleEpoch);
      const bytes=Uint8Array.from(value.bytes);
      writes.push(Array.from(bytes));
      const equal=values=>bytes.length===values.length&&values.every((v,i)=>bytes[i]===v);
      if(phase==='execute'&&bytes.includes(3)){
        if(onInterrupt)return onInterrupt({bytes,feed:runtime.feed,finish:()=>{phase='done';}});
        assert.deepEqual(Array.from(bytes),[3],'running interruption sends exactly one Ctrl-C');
        runtime.feed('\x04KeyboardInterrupt\r\n\x04>');phase='done';return;
      }
      if(equal([13,1])){if(!silent)runtime.feed('raw REPL; CTRL-B to exit\r\n>');phase='negotiate';return;}
      if(equal([5,65,1])){
        if(legacy)runtime.feed('raw REPL; CTRL-B to exit\r\n>');
        else runtime.feed(paste?[82,1,5,0]:[82,0]);
        phase='source';runtime.source=[];return;
      }
      if(phase==='source'){
        if(equal([4])){
          sources.push(new TextDecoder().decode(Uint8Array.from(runtime.source||[])));
          phase='execute';runtime.feed(paste&&!legacy?[4]:[79,75]);
          if(!forever){
            // Deliberately split a UTF-8 character and coalesce all EOF markers.
            const body=encode(output);runtime.feed(body.subarray(0,8));runtime.feed(body.subarray(8));
            runtime.feed(`\x04${stderr}\x04>`);phase='done';
          }
        }else{runtime.source=[...(runtime.source||[]),...bytes];if(paste&&!legacy)runtime.feed([1]);}
      }
    };
  return runtime;
}
{
  const runtime=guest(),runner=new PublicMicroPythonRunner(runtime),phases=[],output=[];
  const source='print("hello 世界")\n';
  const result=await runner.run(source,{onPhase:value=>phases.push(value),onOutput:(text,channel)=>output.push({text,channel})});
  assert.equal(result.stdout,'hello 世界\r\n');assert.equal(result.stderr,'');assert.equal(result.transfer,'raw-paste');
  assert.deepEqual(runtime.sources,[source]);assert.deepEqual(phases,['connecting','uploading','running','complete']);
  assert.equal(output.map(row=>row.text).join(''),result.stdout);assert.equal(runtime.listeners.size,0);
  assert.equal(runner.busy,false);assert.deepEqual(runtime.writes.at(-1),[2],'exit raw mode without Ctrl-D soft reset');
}
for(const legacy of [false,true]){
  const runtime=guest({paste:false,legacy,stderr:'ValueError: expected\r\n'}),runner=new PublicMicroPythonRunner(runtime);
  const result=await runner.run('raise ValueError("expected")');
  assert.equal(result.transfer,'raw-repl');assert.match(result.stderr,/ValueError/);assert.equal(runner.busy,false);
}
{
  const runtime=guest({forever:true}),runner=new PublicMicroPythonRunner(runtime);
  let running;const started=new Promise(resolve=>running=resolve);
  const execution=runner.run('while True: pass',{onPhase:phase=>{if(phase==='running')running();}});
  await started;await assert.rejects(runner.run('print(2)'),/仍在运行/);await runner.interrupt();
  const result=await execution;assert.equal(result.interrupted,true);assert.match(result.stderr,/KeyboardInterrupt/);
  assert.deepEqual(runtime.writes[0],[13,3,3],'initial connection retains its separate REPL synchronization handshake');
  assert.equal(runtime.writes.filter(bytes=>bytes.length===1&&bytes[0]===3).length,1);
}
function finallyGuest(){
  let controls=0,ack,complete,entered;
  const finallyEntered=new Promise(resolve=>entered=resolve),acknowledgement=new Promise(resolve=>ack=resolve);
  const runtime=guest({forever:true,onInterrupt:({bytes,feed,finish})=>{
    // Deliberately process every byte. The old coalesced-EOF fake could not
    // distinguish a second exception interrupting an unfinished finally.
    assert.ok(Array.from(bytes).every(byte=>byte===3));controls+=bytes.length;
    if(!complete){
      feed('FINALLY_BEGIN\r\n');entered();
      complete=()=>{feed(controls===1?'DEINIT_DONE\r\n\x04KeyboardInterrupt\r\n\x04>'
        :'\x04KeyboardInterrupt in finally\r\n\x04>');finish();};
    }
    return acknowledgement;
  }});
  return {runtime,finallyEntered,ack:()=>ack(),complete:()=>complete(),controls:()=>controls};
}
{
  const fixture=finallyGuest(),runner=new PublicMicroPythonRunner(fixture.runtime);
  let running;const started=new Promise(resolve=>running=resolve);
  const execution=runner.run('try:\n while True: pass\nfinally:\n driver.deinit()',{
    onPhase:phase=>{if(phase==='running')running();}});
  await started;
  const first=runner.interrupt(),second=runner.interrupt();
  await fixture.finallyEntered;
  const deadline=runner.current.interruptDeadline;
  assert.equal(fixture.controls(),1,'concurrent interruption requests inject one exception before UART ACK');
  await new Promise(resolve=>setTimeout(resolve,15));fixture.ack();await Promise.all([first,second]);
  await runner.interrupt();
  assert.equal(fixture.controls(),1,'a repeat after ACK cannot interrupt the guest finally');
  assert.equal(runner.current.interruptDeadline,deadline,'repeated interruption cannot extend its deadline');
  fixture.complete();const result=await execution;
  assert.match(result.stdout,/FINALLY_BEGIN\r\nDEINIT_DONE/);assert.equal(result.stderr,'KeyboardInterrupt\r\n');
  assert.equal(result.interrupted,true);assert.equal(fixture.runtime.uartOwner,null);
  await runner.interrupt();assert.equal(fixture.controls(),1,'a completed run is an interruption no-op');
}
{
  const fixture=finallyGuest(),runtime=fixture.runtime,runner=new PublicMicroPythonRunner(runtime);
  let running;const started=new Promise(resolve=>running=resolve);
  const execution=runner.run('while True: pass',{onPhase:phase=>{if(phase==='running')running();}});
  await started;const first=runner.interrupt();await fixture.finallyEntered;
  runtime.status='paused';await assert.rejects(runner.interrupt(),/设备已暂停/);runtime.status='running';
  runner.current.phase='uploading';await assert.rejects(runner.interrupt(),/代码正在传输/);runner.current.phase='running';
  runtime.stopping=true;await assert.rejects(runner.interrupt(),error=>error.name==='AbortError');runtime.stopping=false;
  assert.equal(fixture.controls(),1,'pause, transfer and stop guards still run before the interruption latch');
  fixture.ack();await first;fixture.complete();assert.equal((await execution).interrupted,true);
}
for(const reset of [false,true]){
  const fixture=finallyGuest(),runtime=fixture.runtime,runner=new PublicMicroPythonRunner(runtime);
  let running;const started=new Promise(resolve=>running=resolve);
  const execution=runner.run('while True: pass',{onPhase:phase=>{if(phase==='running')running();}});
  await started;const first=runner.interrupt(),oldAck=assert.rejects(first,error=>error.name==='AbortError');
  await fixture.finallyEntered;const writes=runtime.writes.length;
  if(reset)runtime.receive({type:'machine-event',value:{event:'RESET',consoleEpoch:1}},runtime.generation);
  else runtime.releaseUart(runner.current.owner);
  const nextOwner=runtime.acquireUart();
  await assert.rejects(runner.interrupt(),error=>error.name==='AbortError');
  fixture.ack();await oldAck;await assert.rejects(execution,error=>error.name==='AbortError');
  assert.equal(runtime.writes.length,writes,'a latched stale run cannot send another interruption');
  assert.equal(runtime.uartOwner,nextOwner,'the old run cannot release the replacement UART owner');
  runtime.releaseUart(nextOwner);
}
{
  const fixture=finallyGuest(),runner=new PublicMicroPythonRunner(fixture.runtime);
  let running;const started=new Promise(resolve=>running=resolve);
  const execution=runner.run('try:\n while True: pass\nfinally:\n driver.deinit()',{
    onPhase:phase=>{if(phase==='running')running();}});
  await started;
  // Negative control of the transport oracle, preserving the old two-byte
  // request. It must not be mistaken for completed guest cleanup.
  const oldTransport=fixture.runtime.writeUart(new Uint8Array([3,3]),runner.current.owner);
  await fixture.finallyEntered;fixture.ack();await oldTransport;fixture.complete();
  const result=await execution;
  assert.equal(fixture.controls(),2);assert.doesNotMatch(result.stdout,/DEINIT_DONE/);
  assert.match(result.stderr,/KeyboardInterrupt in finally/);
}
{
  const runtime=guest({forever:true}),runner=new PublicMicroPythonRunner(runtime);
  for(let index=0;index<2;index++){
    let running;const started=new Promise(resolve=>running=resolve);
    const execution=runner.run('while True: pass',{onPhase:phase=>{if(phase==='running')running();}});
    await started;await runner.interrupt();assert.equal((await execution).interrupted,true);
  }
  assert.equal(runtime.writes.filter(bytes=>bytes.length===1&&bytes[0]===3).length,2,
    'the interruption latch belongs to one run and is fresh for the next program');
}
{
  const runtime=guest({forever:true}),runner=new PublicMicroPythonRunner(runtime);
  const execution=runner.run('while True: pass',{onPhase:phase=>{if(phase==='running')runtime.generation++;}});
  await assert.rejects(execution,error=>error.name==='AbortError');assert.equal(runtime.listeners.size,0);assert.equal(runner.busy,false);
}
{
  const runtime=guest({forever:true}),runner=new PublicMicroPythonRunner(runtime);
  let running;const started=new Promise(resolve=>running=resolve);
  const execution=runner.run('while True: pass',{onPhase:phase=>{if(phase==='running')running();}});
  await started;runtime.generation++;runtime.sessionId='guest-2';const count=runtime.writes.length;
  await assert.rejects(runner.interrupt(),error=>error.name==='AbortError');
  await assert.rejects(execution,error=>error.name==='AbortError');
  assert.equal(runtime.writes.length,count,'a stale runner cannot inject Ctrl-C into a new guest');
}
{
  const runtime=guest(),runner=new PublicMicroPythonRunner(runtime);let rejection,writesBefore,writesAfter;
  await runner.run('print(1)',{onPhase:phase=>{
    if(phase==='uploading'){
      writesBefore=runtime.writes.length;rejection=assert.rejects(runner.interrupt(),/代码正在传输/);
      writesAfter=runtime.writes.length;
    }
  }});
  await rejection;
  assert.equal(writesAfter,writesBefore,
    'interrupt cannot corrupt raw-paste source transfer');
}
{
  const runtime=guest({forever:true}),runner=new PublicMicroPythonRunner(runtime);
  await assert.rejects(runner.run('print(1)',{timeoutMs:150,onPhase:phase=>{
    if(phase==='running')runtime.feed('\x04');
  }}),error=>/超时/.test(error.message)&&error.code!=='micropython_repl_timeout');
  assert.equal(runner.busy,false,'missing stderr EOF has a finite completion deadline');
}
{
  // A streaming program without stdout EOF is still running, not completed.
  // Its owner must be able to cancel after the finite transfer budget expires.
  const runtime=guest({forever:true}),runner=new PublicMicroPythonRunner(runtime),controller=new AbortController(),output=[];
  let cancel;
  const execution=runner.run('while True: pass',{timeoutMs:150,signal:controller.signal,
    onOutput:text=>output.push(text),onPhase:phase=>{
      if(phase==='running'){
        runtime.feed('stream without stdout EOF\r\n');
        cancel=setTimeout(()=>controller.abort(),200);
      }
    }});
  try{await assert.rejects(execution,error=>error.name==='AbortError');}finally{clearTimeout(cancel);}
  assert.equal(output.join(''),'stream without stdout EOF\r\n');
  assert.equal(runtime.listeners.size,0);assert.equal(runner.busy,false);
  assert.equal(runtime.writes.filter(bytes=>bytes.length===1&&bytes[0]===4).length,1,'cancellation sends no extra Ctrl-D soft reset');
  assert.notDeepEqual(runtime.writes.at(-1),[2],'an incomplete output protocol cannot be mistaken for a returned raw prompt');
}
{
  const runtime=guest({forever:true}),runner=new PublicMicroPythonRunner(runtime);
  await assert.rejects(runner.run('print(1)',{timeoutMs:150,onPhase:phase=>{
    if(phase==='running')runtime.feed('\x04\x04');
  }}),/超时/);
  assert.equal(runtime.listeners.size,0);assert.equal(runner.busy,false);
  assert.notDeepEqual(runtime.writes.at(-1),[2],'missing final raw prompt has a finite deadline and no successful mode-exit claim');
}
{
  const runtime=guest({forever:true}),runner=new PublicMicroPythonRunner(runtime);
  let resume,observed;
  try{
    const result=await runner.run('print("paused")',{timeoutMs:150,onPhase:phase=>{
      if(phase==='running'){
        runtime.status='paused';runtime.feed('paused output\r\n\x04');
        const writes=runtime.writes.length;
        resume=setTimeout(()=>{
          observed={busy:runner.busy,listeners:runtime.listeners.size,writesBefore:writes,writesAfter:runtime.writes.length};
          runtime.status='running';runtime.feed('\x04>');
        },350);
      }
    }});
    assert.equal(result.stdout,'paused output\r\n');assert.equal(result.stderr,'');
    assert.equal(observed.busy,true);assert.equal(observed.listeners,1,
      'paused time longer than the completion budget retains the same execution and UART subscription');
    assert.equal(observed.writesAfter,observed.writesBefore,'paused execution sends no UART writes');
    assert.equal(result.sessionId,'guest-1');assert.equal(runtime.generation,1);assert.equal(runtime.listeners.size,0);
  }finally{clearTimeout(resume);}
}
{
  const runtime=guest(),runner=new PublicMicroPythonRunner(runtime);let resume,pausedWrites;
  try{
    const result=await runner.run('print("resume transfer")',{timeoutMs:150,onPhase:phase=>{
      if(phase==='uploading'){
        runtime.status='paused';const count=runtime.writes.length;
        resume=setTimeout(()=>{pausedWrites={before:count,after:runtime.writes.length};runtime.status='running';},250);
      }
    }});
    assert.equal(result.transfer,'raw-paste');assert.deepEqual(pausedWrites,{before:2,after:2},
      'source transfer waits for resume and never writes to a paused guest');
    assert.deepEqual(runtime.sources,['print("resume transfer")']);assert.equal(runtime.listeners.size,0);
  }finally{clearTimeout(resume);}
}
{
  const runtime=guest({forever:true}),runner=new PublicMicroPythonRunner(runtime);
  await assert.rejects(runner.run('while True: pass',{onPhase:phase=>{
    if(phase==='running')runtime.feed(new Uint8Array(131073));
  }}),/缓冲区上限/);
  assert.equal(runtime.listeners.size,0);assert.equal(runner.busy,false,'output overflow releases UART ownership');
}
{
  const runtime=guest({silent:true}),runner=new PublicMicroPythonRunner(runtime);
  await assert.rejects(runner.run('print(1)',{timeoutMs:150}),{code:'micropython_repl_timeout'});assert.equal(runtime.listeners.size,0);
  await assert.rejects(runner.run(''),/请输入/);await assert.rejects(runner.run('x'.repeat(65537)),/64 KiB/);
  assert.equal(runtime.writes.filter(row=>row.length===1&&row[0]===4).length,0,'failed handshake never soft-resets the guest');
}
{
  const runtime=guest({forever:true}),first=new PublicMicroPythonRunner(runtime),second=new PublicMicroPythonRunner(runtime);
  let running;const started=new Promise(resolve=>running=resolve);
  const execution=first.run('while True: pass',{onPhase:phase=>{if(phase==='running')running();}});
  await started;const writes=runtime.writes.length,owner=runtime.uartOwner;
  await assert.rejects(second.run('print("competing")'),/串口正由另一项操作/);
  await assert.rejects(runtime.writeUart(encode('ordinary serial')),/串口正由另一项操作/);
  assert.equal(second.busy,false);assert.equal(runtime.writes.length,writes);assert.equal(runtime.uartOwner,owner);
  await first.interrupt();await execution;assert.equal(runtime.uartOwner,null);
}
{
  const runtime=guest(),runner=new PublicMicroPythonRunner(runtime),owner=runtime.acquireUart();
  await runtime.writeUart(encode('ordinary serial'),owner);const writes=runtime.writes.length;
  await assert.rejects(runner.run('print("competing")'),/串口正由另一项操作/);
  assert.equal(runtime.writes.length,writes);runtime.releaseUart(owner);
  await runner.run('print("after serial")');assert.deepEqual(runtime.sources,['print("after serial")']);
  assert.equal(runtime.uartOwner,null);
}
{
  const runtime=guest({forever:true}),runner=new PublicMicroPythonRunner(runtime);
  let running;const started=new Promise(resolve=>running=resolve);
  const execution=runner.run('while True: pass',{onPhase:phase=>{if(phase==='running')running();}});
  await started;const oldOwner=runtime.uartOwner,writes=runtime.writes.length,generation=runtime.generation;
  runtime.receive({type:'machine-event',value:{event:'RESET',consoleEpoch:1}},generation);
  const nextOwner=runtime.acquireUart();
  await assert.rejects(runner.interrupt(),error=>error.name==='AbortError');
  await assert.rejects(execution,error=>error.name==='AbortError');
  await assert.rejects(runtime.writeUart(new Uint8Array([3]),oldOwner),error=>error.name==='AbortError');
  assert.equal(runtime.generation,generation,'hardware reset changes console epoch without requiring a new browser session');
  assert.equal(runtime.consoleEpoch,1);assert.equal(runtime.writes.length,writes);
  assert.equal(runtime.uartOwner,nextOwner,'old runner finally cannot release the new boot owner');
  assert.equal(runtime.listeners.size,0);runtime.releaseUart(nextOwner);
}
{
  const runtime=guest(),runner=new PublicMicroPythonRunner(runtime);let acknowledge;
  runtime.ask=()=>new Promise(resolve=>acknowledge=resolve);
  const execution=runner.run('print("old boot")');await Promise.resolve();
  runtime.receive({type:'machine-event',value:{event:'RESET',consoleEpoch:1}},runtime.generation);
  const nextOwner=runtime.acquireUart();acknowledge({queued:3});
  await assert.rejects(execution,error=>error.name==='AbortError');
  assert.equal(runtime.uartOwner,nextOwner,'late old UART ACK cannot complete or release a new console lease');
  runtime.releaseUart(nextOwner);
}
for(const control of [0,1,2,3,4,5,6,7,8,11,14,27,31,127]){
  const runtime=guest(),runner=new PublicMicroPythonRunner(runtime);
  await assert.rejects(runner.run('print("prefix")\n'+String.fromCharCode(control)+'print("tail")\n'),/原始串口控制字符/);
  assert.equal(runtime.writes.length,0);assert.equal(runtime.uartOwner,null);assert.equal(runner.busy,false,
    'raw control characters are rejected before acquiring UART or executing any prefix');
}
{
  const runtime=guest(),runner=new PublicMicroPythonRunner(runtime),source='\f# whitespace\nprint("\\x04")\t\r\n';
  await runner.run(source);assert.deepEqual(runtime.sources,[source],
    'ordinary source whitespace and backslash escapes remain untouched; this does not claim binary stdout transparency');
}
console.log('MicroPython raw-paste / legacy / UTF-8 / exception / interrupt / cancellation contracts passed');
