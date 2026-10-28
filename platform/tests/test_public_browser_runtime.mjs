import assert from 'node:assert/strict';
import {PublicBrowserRuntime,getBrowserProfile,validateBrowserFirmware,decodeBrowserFrame,ESP32SIM_SOURCE_COMMIT} from '../web/public-browser-runtime.js';

const romSha = 'c0ce0f338d1de1bdc6efbef1591779a2a42c1ab7d759d3c6ae8ae63a7dd34cfd';
const manifest = {schema_version:1,source:{commit:ESP32SIM_SOURCE_COMMIT},profiles:['papers3','stopwatch'],build:{kind:'source-build'},wasm:{path:'esp32sim.wasm',sha256:'0'.repeat(64)},rom:{path:'esp32s3_rev0_rom.elf',sha256:romSha}};
function firmware() {
  const data = new Uint8Array(0x10100), view = new DataView(data.buffer);
  for (const at of [0,0x10000]) { data[at]=0xe9; data[at+1]=1; view.setUint16(at+12,9,true); view.setUint32(at+28,4,true); }
  view.setUint16(0x8000,0x50aa,true); view.setUint32(0x8004,0x10000,true); view.setUint32(0x8008,0x1000,true);
  return data.buffer;
}
const profile = getBrowserProfile('m5papers3');
assert.equal(profile.board,'papers3');
assert.equal(getBrowserProfile('stopwatch').jit,false);
assert.equal(getBrowserProfile('cores3'),null);
profile.display.width=1;
assert.equal(getBrowserProfile('papers3').display.width,540);
assert.equal(validateBrowserFirmware(firmware(),getBrowserProfile('papers3')),true);
assert.throws(()=>validateBrowserFirmware(new ArrayBuffer(10),getBrowserProfile('papers3')),{code:'merged_firmware_required'});
const mismatch = firmware(); new DataView(mismatch).setUint16(12,13,true);
assert.throws(()=>validateBrowserFirmware(mismatch,getBrowserProfile('papers3')),{code:'firmware_chip_mismatch'});
const corrupt = firmware(); new DataView(corrupt).setUint32(0x10000+28,0xfffffff,true);
assert.throws(()=>validateBrowserFirmware(corrupt,getBrowserProfile('papers3')),{code:'truncated_firmware'});
assert.throws(()=>decodeBrowserFrame(new Uint8Array([1,1,0,1,0,0]).buffer,1),{code:'invalid_frame'});
assert.deepEqual(decodeBrowserFrame(new Uint8Array([1,1,0,1,0,0x34,0x12]).buffer,2).pixels,new Uint8Array([0x34,0x12]));

class WorkerFixture {
  constructor({boot=true,replyInit=true}={}) {this.calls=[];this.terminated=false;this.boot=boot;this.replyInit=replyInit;}
  emit(data) {this.onmessage?.({data});}
  postMessage(message) {
    this.calls.push(message);
    queueMicrotask(()=>{
      if(this.terminated)return;
      const result = message.op==='init' ? (this.replyInit ? {ready:true}:null)
        :message.op==='create'?{created:true}:message.op==='load'?{loaded:message.kind,ok:true}
        :message.op==='start'?{started:this.boot}:message.op==='stop'?{stopped:0}
        :message.op==='resume'?{resumed:true}:message.op==='text'?{inputQueued:message.inputId,time:9}:null;
      if(result)this.emit(result);
    });
  }
  terminate(){this.terminated=true;}
}
function options(overrides={}) {
  return {root:'https://example.test/repo/', fetchImpl:async function(){assert.equal(this,undefined,'fetch must not receive the runtime as its native browser receiver');return new Response(JSON.stringify(manifest));},
    downloadImpl:async(url,{expectedSha256})=>({bytes:new ArrayBuffer(8),sha256:expectedSha256}),...overrides};
}
const worker = new WorkerFixture(), states=[],serial=[],frames=[];
const runtime = new PublicBrowserRuntime(options({workerFactory:url=>{assert.equal(url,'https://example.test/repo/platform/web/vendor/esp32sim/worker.js');return worker;},onState:state=>states.push(state.status),onSerial:data=>serial.push(data),onFrame:frame=>frames.push(frame)}));
await runtime.start({device:'papers3',firmware:firmware()});
assert.equal(runtime.observe().status,'running');
assert.deepEqual(worker.calls.slice(0,5).map(call=>call.op),['init','create','load','load','start']);
assert.equal(worker.calls[1].board,'papers3');
const pixels = new Uint8Array(5+540*960*2); pixels.set([1,28,2,192,3]);
worker.emit({bin:pixels.buffer,ack:true});
assert.equal(frames[0].source,'emulator');
assert.equal(frames[0].width,540);
assert.equal(worker.calls.at(-1).op,'frame-ack');
worker.emit({text:JSON.stringify({t:'serial',data:'real guest serial'})});
assert.deepEqual(serial,['real guest serial']);
worker.emit({text:JSON.stringify({t:'stat',time:8.25,insns:500})});
worker.emit({pace:{speed:0.5}});
assert.equal(runtime.observe().stats.time,8.25);
assert.equal(runtime.observe().stats.speed,0.5);
assert.equal(runtime.observe().persistentStorage,false);
assert.equal((await runtime.input({type:'touch',x:10,y:20,down:true})).delivery,'queued');
assert.equal(JSON.parse(worker.calls.at(-1).data).down,1);
await assert.rejects(runtime.input({type:'button',id:'power',down:true}),{code:'unsupported_control'});
await runtime.pause();
assert.equal(runtime.observe().status,'paused');
await assert.rejects(runtime.input({type:'touch',x:10,y:20,down:true}),{code:'not_running'});
await runtime.input({type:'touch',x:10,y:20,down:false});
await runtime.resume();
assert.equal(runtime.observe().status,'running');
runtime.stop();
assert.equal(worker.terminated,true);
assert.equal(runtime.pending.size,0);
assert.equal(runtime.observe().status,'stopped');

const badWorker = new WorkerFixture({boot:false});
const broken = new PublicBrowserRuntime(options({workerFactory:()=>badWorker}));
await assert.rejects(broken.start({device:'papers3',firmware:firmware()}),{code:'browser_boot_failed'});
assert.equal(badWorker.terminated,true);
assert.equal(broken.observe().status,'error');
const noInit = new WorkerFixture({replyInit:false}), cancel = new AbortController();
const pending = new PublicBrowserRuntime(options({workerFactory:()=>noInit}));
const run = pending.start({device:'papers3',firmware:firmware(),signal:cancel.signal});
await new Promise(resolve=>setImmediate(resolve)); cancel.abort();
await assert.rejects(run,{name:'AbortError'});
assert.equal(noInit.terminated,true);
assert.equal(pending.pending.size,0);
assert.equal(pending.observe().status,'stopped');
const missing = new PublicBrowserRuntime(options({fetchImpl:async()=>new Response('',{status:404})}));
await assert.rejects(missing.start({device:'stopwatch',firmware:firmware()}),{code:'browser_runtime_missing'});
assert.equal(missing.observe().status,'error');
console.log('browser adapter image admission, worker lifecycle, native-frame, input and cancellation contracts passed');
