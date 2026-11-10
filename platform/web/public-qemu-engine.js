import {readQemuServoOutputs} from './public-qemu-servo.js';
import {validateQemuProfile,validateQemuRuntimeRequirements,buildQemuArguments,buildQemuEfuse,qemuInputCommand} from './public-qemu-profiles.js';
import {readSharedQemuFrame,readQemuOnboardOutputs} from './public-qemu-frame.js';
// The engine owns Emscripten and MEMFS. The top page owns its native pthread Workers.
// The iframe transfers one private port; no window control channel is used.
// workersCreated/workersRemaining count Emscripten pthread handles, excluding this engine.
let port, module, started = false, closed = false, disposeRequested = false, serial = '', qmpLine = '';
let nextId = 0, boardProfile, frameTransport, sourceSequence = 0;
let previousOutputs;
let encoderInputs = Promise.resolve();
let resetEpoch = 0;
let panelPath;
let workersCreated = 0;
let relocatedGlueSha256;
let runtimeArguments,qemuExit,awaitingOwnerFinalization=false;
const pending = new Map(), qmpInput = [], uartInput = [], workers = new Set(), urls = [];
const encoder = new TextEncoder(), decoder = new TextDecoder();
// Emscripten allocates a Worker-shaped handle synchronously. Its actual
// dedicated Worker is started by the top owner, using the verified blob URL.
globalThis.Worker = class extends EventTarget {
  constructor(url, options) {
    super();
    if(options?.type!=='module')throw new TypeError('QEMU pthread requires a module Worker');
    const relay=new MessageChannel();
    this.relay=relay.port1;
    this.pthreadId=workersCreated+1;
    this.onmessage=null;this.onerror=null;
    this.relay.onmessage=({data})=>{
      if(data?.type==='message'){
        const event=new MessageEvent('message',{data:data.payload,ports:data.ports||[]});
        this.dispatchEvent(event);this.onmessage?.(event);
      }else if(data?.type==='error'){
        const event=new ErrorEvent('error',data.detail);
        this.dispatchEvent(event);this.onerror?.(event);
      }
    };
    this.relay.onmessageerror=()=>fail('Could not receive the QEMU pthread relay message');
    this.addEventListener('error',event=>fail(event.message||'QEMU pthread failed'));
    this.relay.start();
    try{self.postMessage({type:'m5-qemu-pthread-spawn',id:this.pthreadId,url:String(url)},[relay.port2]);}
    catch(error){relay.port1.close();relay.port2.close();throw error;}
    workersCreated++;workers.add(this);
  }
  postMessage(payload, transferOrOptions=[]) {
    const transfer=Array.isArray(transferOrOptions)?transferOrOptions:transferOrOptions?.transfer||[];
    this.relay?.postMessage({type:'message',payload,transfer},transfer);
  }
  terminate() {
    if(!this.relay)return;
    // Spawn, terminate and engine drained notifications share the same
    // ordered Worker channel. A closed relay cannot lose the termination.
    self.postMessage({type:'m5-qemu-pthread-terminate',id:this.pthreadId});
    this.relay.onmessage=null;this.relay.onmessageerror=null;
    this.relay.close();this.relay=null;
    workers.delete(this);
  }
};
function emit(type, value, transfer = []) { if (!closed && !disposeRequested) port?.postMessage({type, value}, transfer); }
const qmpTraceLimit=512;
let qmpOrderingMode, qmpTraceCount=0, qmpQueuedBytes=0, qmpReadBytes=0;
const qmpTraceRows=[], qmpTraceUnread=[];
const epochNow=()=>performance.timeOrigin+performance.now();
function readQmpByte() {
  const byte=qmpInput.shift();
  if(byte===undefined||!qmpOrderingMode)return byte;
  const row=qmpTraceUnread[0];
  if(qmpReadBytes===row.first_byte_index)row.stdin_first_epoch_ms=epochNow();
  if(++qmpReadBytes===row.end_byte_index){
    row.stdin_last_epoch_ms=epochNow();
    qmpTraceUnread.shift();
  }
  return byte;
}
function qmp(execute, args = {}, timeout = 15000) {
  if (!module) return Promise.reject(new Error('QEMU is not initialized'));
  const id = ++nextId;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`QMP ${execute} timed out`)); }, timeout);
    const bytes=encoder.encode(JSON.stringify({execute, arguments:args, id}) + '\n');
    let trace;
    if(qmpOrderingMode){
      trace={id,execute,queued_epoch_ms:epochNow(),queued_behind_bytes:qmpInput.length,
        first_byte_index:qmpQueuedBytes,end_byte_index:qmpQueuedBytes+bytes.length};
      if(execute==='qom-get')trace.property=args.property;
      if(execute==='input-send-event')trace.events=args.events;
      qmpQueuedBytes+=bytes.length;
      qmpTraceRows[qmpTraceCount++%qmpTraceLimit]=trace;
      qmpTraceUnread.push(trace);
    }
    pending.set(id, {resolve, reject, timer, trace});
    qmpInput.push(...bytes);
  });
}
function output(text) {
  qmpLine += text;
  if (qmpLine.length > 1048576) throw new Error('QMP output limit exceeded');
  let at;
  while ((at = qmpLine.indexOf('\n')) >= 0) {
    const line = qmpLine.slice(0, at); qmpLine = qmpLine.slice(at + 1);
    let message;
    try { message = JSON.parse(line); } catch { emit('diagnostic', line); continue; }
    if (message.QMP) {
      (async()=>{
        await qmp('qmp_capabilities');
        // QMP is offered during machine construction. Do not queue a display
        // coroutine until QEMU has actually transitioned to a running VM.
        const deadline=performance.now()+120000;
        while (!closed) {
          const status=await qmp('query-status',{},90000);
          if (status.running) break;
          if (performance.now()>deadline) throw new Error('QEMU machine initialization timed out');
          await new Promise(resolve=>setTimeout(resolve,100));
        }
        if (!closed) emit('ready', {shared:module.HEAPU8.buffer instanceof SharedArrayBuffer,
          memoryBytes:module.HEAPU8.buffer.byteLength, crossOriginIsolated, relocatedGlueSha256,arguments:runtimeArguments.slice()});
      })().catch(fail);
    }
    if (['RESET','SHUTDOWN','STOP','RESUME','POWERDOWN','SUSPEND','WAKEUP'].includes(message.event)) {
      if (message.event==='RESET') {resetEpoch++;uartInput.length=0;previousOutputs=undefined;sourceSequence=0;}
      emit('machine-event', {event:message.event,reason:typeof message.data?.reason === 'string'?message.data.reason:null,guest:message.data?.guest === true,
        ...(message.event==='RESET'?{consoleEpoch:resetEpoch}:{})});
    }
    const item = pending.get(message.id);
    if (item) {
      clearTimeout(item.timer); pending.delete(message.id);
      if(item.trace)item.trace.reply_epoch_ms=epochNow();
      if (message.error) item.reject(new Error(`${message.error.class}: ${message.error.desc}`));
      else item.resolve(message.return);
    }
  }
}
function fail(error) { emit('error', String(error?.message || error)); }
function cleanup() {
  uartInput.length=0;
  for (const worker of workers) worker.terminate();
  workers.clear();
  for (const url of urls) URL.revokeObjectURL(url);
  urls.length = 0;
  for (const item of pending.values()) { clearTimeout(item.timer); item.reject(new Error('Instance disposed')); }
  pending.clear();
}
function blob(bytes, type) { const url = URL.createObjectURL(new Blob([bytes], {type})); urls.push(url); return url; }
function ppm(bytes) {
  // QEMU P6 has a 4-byte aligned row stride. Parse only ASCII header bytes.
  let offset = 0;
  function token() {
    while (offset < bytes.length && bytes[offset] <= 32) offset++;
    if (bytes[offset] === 35) { while (offset < bytes.length && bytes[offset++] !== 10) {} return token(); }
    const begin = offset;
    while (offset < bytes.length && bytes[offset] > 32) offset++;
    return decoder.decode(bytes.subarray(begin, offset));
  }
  if (token() !== 'P6') throw new Error('QEMU did not return a P6 framebuffer');
  const width = Number(token()), height = Number(token()), max = Number(token());
  if (width !== boardProfile.display.width || height !== boardProfile.display.height || max !== 255) throw new Error('QEMU framebuffer profile mismatch');
  if (bytes[offset] === 13 && bytes[offset + 1] === 10) offset += 2; else offset++;
  const stride = (width * 3 + 3) & ~3;
  if (bytes.length - offset !== stride * height) throw new Error('QEMU framebuffer length mismatch');
  const pixels = new Uint8Array(width * height * 2);
  for (let y = 0, p = 0; y < height; y++) for (let x = 0; x < width; x++, p += 2) {
    const i = offset + y * stride + x * 3, value = (bytes[i] >> 3) << 11 | (bytes[i+1] >> 2) << 5 | bytes[i+2] >> 3;
    pixels[p] = value & 255; pixels[p+1] = value >> 8;
  }
  return {width, height, pixels, format:'rgb565le', source:'qemu-screendump'};
}
async function start(config) {
  if (started) throw new Error('Instance already initialized');
  started = true;
  if (!crossOriginIsolated || typeof SharedArrayBuffer === 'undefined') throw new Error('Cross-origin isolation is required');
  // Emscripten pthread copies do not inherit locateFile. A blob module cannot
  // resolve their relative new URL(..., import.meta.url). Relocate that host
  // glue base to the original verified asset URL; the C/WASM bytes are intact.
  const assetBase = new URL(config.javascriptURL);
  if (assetBase.origin !== location.origin) throw new Error('QEMU asset base must be same origin');
  const relocated = new TextDecoder('utf-8',{fatal:true}).decode(config.javascript).replaceAll('import.meta.url',JSON.stringify(assetBase.href));
  relocatedGlueSha256 = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',encoder.encode(relocated))),n=>n.toString(16).padStart(2,'0')).join('');
  const script = blob(relocated, 'text/javascript'), worker = blob(config.worker, 'text/javascript');
  self.postMessage({type:'m5-qemu-pthread-source',url:worker});
  const {default:createQemu} = await import(script);
  if (disposeRequested) throw new Error('Instance disposed during start');
  boardProfile=validateQemuProfile(config.profile);
  if(boardProfile.deviceId==='cardputer-adv'&&['baseline','no-orientation'].includes(config.qmpOrderingMode))
    qmpOrderingMode=config.qmpOrderingMode;
  validateQemuRuntimeRequirements(boardProfile,{source:{patches:config.runtimePatches}});
  frameTransport=config.frameTransport;
  const options = {
    arguments:buildQemuArguments(boardProfile),
    wasmBinary:config.wasm, mainScriptUrlOrBlob:script,
    locateFile:(name) => name.endsWith('.worker.js') ? worker : name,
    print:(text) => output(String(text) + '\n'),
    printErr:(text) => emit('diagnostic', String(text)),
    stdin:readQmpByte,
    onAbort:fail,
    onExit:(code) => {
      qemuExit={code,workersCreated,workersRemaining:workers.size};
      emit('exit',qemuExit);
    },
    preRun:[(m) => {
      if (disposeRequested) throw new Error('Instance disposed during start');
      module = m;
      m.FS.mkdirTree('/rom'); m.FS.mkdirTree('/bridge');
      m.FS.writeFile('/flash.bin', new Uint8Array(config.firmware));
      if(!Array.isArray(config.roms)||config.roms.length!==boardProfile.roms.length)throw new Error('QEMU ROM set mismatch');
      for(const [index,rom] of config.roms.entries()){
        const expected=boardProfile.roms[index];
        if(rom.name!==expected.name||rom.sha256!==expected.sha256||rom.bytes.byteLength!==expected.bytes)throw new Error('QEMU ROM identity mismatch');
        m.FS.writeFile('/rom/'+rom.name,new Uint8Array(rom.bytes));
      }
      const efuse=buildQemuEfuse(boardProfile);if(efuse)m.FS.writeFile('/efuse.bin',efuse);
      m.FS.writeFile('/units.json',JSON.stringify(boardProfile.units));
      if (!m.ENV) throw new Error('QEMU build must export ENV');
      Object.assign(m.ENV, {M5_WASM_VM_CLOCK_DIVISOR:String(boardProfile.clockDivisor), M5_WASM_FRAMEBUFFER:boardProfile.display&&frameTransport==='shared-rgb565-v1'?'1':'0', M5_UNIT_CONFIG:'/units.json'});
      if (boardProfile.accelerator?.icountMaxPerCpuNs !== undefined)
        m.ENV.M5SW_ICOUNT_MAX_PERCPU_NS=String(boardProfile.accelerator.icountMaxPerCpuNs);
      const consoleBase = boardProfile.target==='riscv32-softmmu' ? '/bridge/usb' : '/bridge/uart';
      const consoleInput = consoleBase+'.in', consoleOutput = consoleBase+'.out';
      const chardevPaths = [...new Set([consoleInput,consoleOutput,'/bridge/uart.out','/bridge/serial1'])];
      for (const [index,path] of chardevPaths.entries()) {
        const dev = m.FS.makedev(64,index);
        const serialDecoder = new TextDecoder();
        m.FS.registerDevice(dev, {
          open:stream => { stream.seekable = false; }, close:() => {},
          read:(stream,buffer,offset,length) => {
            if (path!==consoleInput||!uartInput.length) throw new m.FS.ErrnoError(6);
            const count = Math.min(uartInput.length,length);
            for (let i=0;i<count;i++) buffer[offset+i] = uartInput.shift();
            return count;
          },
          write:(stream,buffer,offset,length) => {
            // StackChan UART1 is the internal SCS bus, not the user's console.
            // Its parsed register output is read separately from scs_servo QOM.
            if(path==='/bridge/serial1'&&boardProfile.deviceId==='stackchan')return length;
            // Chromium rejects SharedArrayBuffer-backed TextDecoder input.
            // FS buffers can be the shared WASM heap: copy before decoding.
            const bytes=Uint8Array.from(buffer.subarray(offset,offset+length));
            if(path===consoleOutput)emit('uart-bytes',bytes);
            const text = serialDecoder.decode(bytes, {stream:true});
            serial = (serial + text).slice(-65536); emit('serial', text); return length;
          },
          poll:() => 4 | (path===consoleInput&&uartInput.length ? 1 : 0),
          llseek:() => { throw new m.FS.ErrnoError(70); },
        });
        m.FS.mkdev(path,0o666,dev);
      }
    }],
    onRuntimeInitialized:() => {
      if (disposeRequested) return;
      const stream = module.FS.getStream(0);
      stream.stream_ops = {...stream.stream_ops,poll:() => 4 | (qmpInput.length ? 1 : 0)};
    },
  };
  if (config.wasmModule) {
    if (!(config.wasmModule instanceof WebAssembly.Module)) throw new Error('Invalid compiled QEMU module');
    // Emscripten must receive the Module as well as its fresh Instance: it
    // forwards the compiled code to every pthread with the new guest memory.
    options.instantiateWasm=(imports,receiveInstance)=>{
      return receiveInstance(new WebAssembly.Instance(config.wasmModule,imports),config.wasmModule);
    };
  }
  // Retain the very array handed to the factory; ready reports a copy rather
  // than reconstructing arguments from the profile after startup.
  runtimeArguments=options.arguments;
  module = await createQemu(options);
  if (disposeRequested) { cleanup(); throw new Error('Instance disposed during start'); }
}
async function request(op, value) {
  if (op === 'start') return start(value);
  if (op === 'qmp-ordering-diagnostic'&&qmpOrderingMode) {
    const offset=Math.max(0,qmpTraceCount-qmpTraceLimit);
    return {mode:qmpOrderingMode,records_dropped:offset,
      rows:Array.from({length:qmpTraceCount-offset},(_,i)=>qmpTraceRows[(offset+i)%qmpTraceLimit])};
  }
  if (op === 'dispose') {
    disposeRequested=true;
    const workersTerminatedByDispose=workers.size;cleanup();
    const normalExit=qemuExit?.code===0&&qemuExit.workersRemaining===0&&workersTerminatedByDispose===0;
    return {workersRemaining:workers.size,workersTerminatedByDispose,workerCountScope:'engine-pthreads',
      enginePlacement:'dedicated-worker-v1',engineWorkersAtAcknowledgement:1,
      ownerTerminatesAfterAcknowledgement:normalExit,engineSelfClosesAfterAcknowledgement:!normalExit};
  }
  if (op === 'frame') {
    const epoch=resetEpoch;
    if (!boardProfile.display) throw new Error('This headless QEMU device has no framebuffer');
    // Explicit same-guest diagnostic control; never an automatic fallback.
    if(frameTransport==='shared-rgb565-v1'&&value?.diagnosticTransport!=='qmp-screendump'){
      const frame=readSharedQemuFrame(module,sourceSequence,boardProfile.display);
      if(!frame)return {unchanged:true,sourceSequence};
      sourceSequence=frame.sourceSequence;emit('frame',frame,[frame.pixels.buffer]);return {sourceSequence};
    }
    await qmp('screendump',{filename:'/frame.ppm'});
    if(epoch!==resetEpoch||closed)return {unchanged:true,reset:true};
    const frame = ppm(module.FS.readFile('/frame.ppm')); module.FS.unlink('/frame.ppm');
    frame.source='qmp-screendump';
    emit('frame', frame, [frame.pixels.buffer]); return;
  }
  if (op === 'outputs') {
    const epoch=resetEpoch;
    if (value && Object.keys(value).length) throw new Error('QEMU output reads accept no caller path, property or value');
    const state = await (boardProfile.outputs?.kind === 'stackchan-scs-qom-v1'
      ? readQemuServoOutputs(boardProfile,qmp) : readQemuOnboardOutputs(boardProfile, qmp));
    if (!state||epoch!==resetEpoch||closed) return {unchanged:true};
    const identity = JSON.stringify(state);
    if (identity === previousOutputs) return {unchanged:true};
    previousOutputs = identity;
    emit('device-state', state); return {observed:true};
  }
  if (op === 'display') {
    // Only Cardputer's admitted native-glass presentation uses this QOM
    // contract. E-paper and other panel types need no SPI-panel lookup.
    if (boardProfile?.deviceId !== 'cardputer-adv') return null;
    if (!panelPath) {
      const children = await qmp('qom-list', {path:'/machine/unattached'});
      const panel = children.find(row => row.type === 'child<m5.spi-panel>');
      if (!panel) throw new Error('QEMU display panel is unavailable');
      panelPath = `/machine/unattached/${panel.name}`;
    }
    const orientation = await qmp('qom-get', {path:panelPath, property:'logical-orientation'});
    if (!['landscape','portrait','unknown'].includes(orientation))
      throw new Error('QEMU display panel returned an invalid orientation');
    return {orientation, deviceRotationDeg:orientation === 'portrait' ? -90 : 0};
  }
  if (op === 'pause') return qmp('stop');
  if (op === 'resume') return qmp('cont');
  if (op === 'quit') return qmp('quit');
  if (op === 'input' || op === 'touch' || op === 'pir') {
    const event=op==='input'?value:{...value,type:op};
    const command=qemuInputCommand(boardProfile,event);
    if (command.bitInput) {
      const target=command.bitInput;
      const operation=encoderInputs.then(async()=>{
        if(closed||disposeRequested)throw new Error('QEMU touch input was disposed');
        const current=await qmp('qom-get',{path:target.path,property:target.property});
        if(!Number.isInteger(current)||current<0||current>255)throw new Error('Invalid controller touch state');
        const value=target.down?current|target.mask:current&~target.mask;
        await qmp('qom-set',{path:target.path,property:target.property,value});
        const observed=await qmp('qom-get',{path:target.path,property:target.property});
        if(observed!==value)throw new Error('QEMU touch target readback mismatch');
        return {touch_bits:observed,source:'qemu-qom-readback'};
      });
      encoderInputs=operation.catch(()=>{});return operation;
    }
    if (command.readbackResult === 'detents') {
      // Serialize the fixed write/readback pair so a later pointer target
      // cannot overtake the readback for an earlier physical target.
      const operation = encoderInputs.then(async () => {
        if (closed || disposeRequested) throw new Error('QEMU encoder input was disposed');
        await qmp(command.execute, command.arguments);
        const target = await qmp(command.readback.execute, command.readback.arguments);
        if (!Number.isInteger(target) || target !== command.arguments.value) throw new Error('QEMU encoder target readback mismatch');
        return {detents:target, source:'qemu-qom-readback'};
      });
      encoderInputs = operation.catch(() => {});
      return operation;
    }
    const result=await qmp(command.execute,command.arguments);
    if(command.readback)return {motion:await qmp(command.readback.execute,command.readback.arguments)};
    return result;
  }
  if (op === 'uart') {
    if(!boardProfile?.inputs.uart)throw new Error('UART input is not admitted');
    if(!Number.isSafeInteger(value?.consoleEpoch)||value.consoleEpoch!==resetEpoch)throw new Error('UART console was reset');
    const bytes=value?.bytes;
    if(!Array.isArray(bytes)||bytes.length<1||bytes.length>1024
      ||bytes.some(byte=>!Number.isInteger(byte)||byte<0||byte>255))throw new Error('Invalid UART bytes');
    if(uartInput.length+bytes.length>65536)throw new Error('UART input queue is full');
    uartInput.push(...bytes);
    return {queued:bytes.length,transport:'esp-uart0'};
  }
  throw new Error('Unsupported instance operation');
}
addEventListener('message', event => {
  if (awaitingOwnerFinalization && event.data?.type === 'm5-qemu-engine-finalize'
      && typeof event.data.token === 'string' && event.data.token && !event.ports?.length) {
    awaitingOwnerFinalization=false;
    self.postMessage({type:'m5-qemu-engine-finalized',token:event.data.token});
    return;
  }
  if (port || closed || event.data?.type !== 'm5-qemu-engine-connect' || event.ports?.length !== 1) return;
  port = event.ports[0];
  port.onmessage = async ({data}) => {
    if (closed || !Number.isSafeInteger(data?.id)) return;
    try {
      const value = await request(data.op, data.value);
      if (closed || disposeRequested && data.op!=='dispose') return;
      port.postMessage({id:data.id,value});
      if (data.op === 'dispose') {
        closed=true;port.close();
        if (value.ownerTerminatesAfterAcknowledgement) {
          // The owner's finalization request runs in a new Worker task after
          // the private port is closed and the dispose handler has returned.
          port.onmessage=null;port=null;
          awaitingOwnerFinalization=true;
          self.postMessage({type:'m5-qemu-engine-drained'});
        } else {
          self.postMessage({type:'m5-qemu-engine-closing'});
          self.close();
        }
      }
    } catch(error) {
      if (!closed && !disposeRequested) port.postMessage({id:data.id,error:String(error?.message||error)});
    }
  };
  port.start(); emit('connected',{});
});
self.postMessage({type:'m5-qemu-engine-listening'});
