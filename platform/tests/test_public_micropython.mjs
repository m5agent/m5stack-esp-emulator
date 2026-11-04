import assert from 'node:assert/strict';
import {PublicMicroPythonRunner} from '../web/public-micropython.js';

const encode=value=>new TextEncoder().encode(value);
function guest({paste=true,legacy=false,output='hello 世界\r\n',stderr='',forever=false,silent=false}={}){
  const listeners=new Set(),writes=[],sources=[];
  let phase='connect';
  const runtime={generation:1,sessionId:'guest-1',status:'running',
    subscribeUart(fn){listeners.add(fn);return()=>listeners.delete(fn);},
    feed(value){for(const fn of listeners)fn(typeof value==='string'?encode(value):Uint8Array.from(value));},
    async writeUart(bytes){
      writes.push(Array.from(bytes));
      const equal=values=>bytes.length===values.length&&values.every((v,i)=>bytes[i]===v);
      if(phase==='execute'&&equal([3,3])){runtime.feed('\x04KeyboardInterrupt\r\n\x04>');phase='done';return;}
      if(equal([13,1])){if(!silent)runtime.feed('raw REPL; CTRL-B to exit\r\n>');phase='negotiate';return;}
      if(equal([5,65,1])){
        if(legacy)runtime.feed('raw REPL; CTRL-B to exit\r\n>');
        else runtime.feed(paste?[82,1,5,0]:[82,0]);
        phase='source';return;
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
    },writes,sources,listeners};
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
  const runtime=guest(),runner=new PublicMicroPythonRunner(runtime);let rejection;
  await runner.run('print(1)',{onPhase:phase=>{
    if(phase==='uploading')rejection=assert.rejects(runner.interrupt(),/代码正在传输/);
  }});
  await rejection;
  assert.equal(runtime.writes.some(bytes=>bytes.length===2&&bytes.every(byte=>byte===3)),false,
    'interrupt cannot corrupt raw-paste source transfer');
}
{
  const runtime=guest({forever:true}),runner=new PublicMicroPythonRunner(runtime);
  await assert.rejects(runner.run('print(1)',{timeoutMs:150,onPhase:phase=>{
    if(phase==='running')runtime.feed('\x04');
  }}),/超时/);
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
  await assert.rejects(runner.run('print(1)',{timeoutMs:150}),/超时/);assert.equal(runtime.listeners.size,0);
  await assert.rejects(runner.run(''),/请输入/);await assert.rejects(runner.run('x'.repeat(65537)),/64 KiB/);
  assert.equal(runtime.writes.filter(row=>row.length===1&&row[0]===4).length,0,'failed handshake never soft-resets the guest');
}
console.log('MicroPython raw-paste / legacy / UTF-8 / exception / interrupt / cancellation contracts passed');
