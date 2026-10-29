import {readQemuServoOutputs} from './public-qemu-servo.js';
import {validateQemuProfile,buildQemuArguments,buildQemuEfuse,qemuInputCommand} from './public-qemu-profiles.js';
import {readSharedQemuFrame,readQemuOnboardOutputs} from './public-qemu-frame.js';
// One dedicated engine Worker owns the Emscripten module, MEMFS and pthreads.
// The iframe transfers one private port; no window control channel is used.
// workersCreated/workersRemaining count nested pthreads, excluding this engine.
let port, module, started = false, closed = false, disposeRequested = false, serial = '', qmpLine = '';
let nextId = 0, boardProfile, frameTransport, sourceSequence = 0;
let previousOutputs;
let encoderInputs = Promise.resolve();
let resetEpoch = 0;
let workersCreated = 0;
let relocatedGlueSha256;
const pending = new Map(), qmpInput = [], uartInput = [], workers = new Set(), urls = [];
const encoder = new TextEncoder(), decoder = new TextDecoder();
const NativeWorker = globalThis.Worker;
globalThis.Worker = class extends NativeWorker {
  constructor(...args) { super(...args);workersCreated++;workers.add(this);this.addEventListener('error',event=>fail(event.message||'QEMU pthread failed')); }
  terminate() { workers.delete(this); return super.terminate(); }
};
function emit(type, value, transfer = []) { if (!closed && !disposeRequested) port?.postMessage({type, value}, transfer); }
function qmp(execute, args = {}, timeout = 15000) {
  if (!module) return Promise.reject(new Error('QEMU is not initialized'));
  const id = ++nextId;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`QMP ${execute} timed out`)); }, timeout);
    pending.set(id, {resolve, reject, timer});
    qmpInput.push(...encoder.encode(JSON.stringify({execute, arguments:args, id}) + '\n'));
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
          memoryBytes:module.HEAPU8.buffer.byteLength, crossOriginIsolated, relocatedGlueSha256});
      })().catch(fail);
    }
    if (['RESET','SHUTDOWN','STOP','RESUME','POWERDOWN'].includes(message.event)) {
      emit('machine-event', {event:message.event,reason:typeof message.data?.reason === 'string'?message.data.reason:null,guest:message.data?.guest === true});
      if (message.event==='RESET') {resetEpoch++;previousOutputs=undefined;sourceSequence=0;}
    }
    const item = pending.get(message.id);
    if (item) {
      clearTimeout(item.timer); pending.delete(message.id);
      if (message.error) item.reject(new Error(`${message.error.class}: ${message.error.desc}`));
      else item.resolve(message.return);
    }
  }
}
function fail(error) { emit('error', String(error?.message || error)); }
function cleanup() {
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
  const {default:createQemu} = await import(script);
  if (disposeRequested) throw new Error('Instance disposed during start');
  boardProfile=validateQemuProfile(config.profile);
  frameTransport=config.frameTransport;
  const options = {
    arguments:buildQemuArguments(boardProfile),
    wasmBinary:config.wasm, mainScriptUrlOrBlob:script,
    locateFile:(name) => name.endsWith('.worker.js') ? worker : name,
    print:(text) => output(String(text) + '\n'),
    printErr:(text) => emit('diagnostic', String(text)),
    stdin:() => qmpInput.shift(),
    onAbort:fail,
    onExit:(code) => { emit('exit', {code,workersCreated,workersRemaining:workers.size}); },
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
      for (const [index,path] of ['/bridge/uart.in','/bridge/uart.out','/bridge/serial1'].entries()) {
        const dev = m.FS.makedev(64,index);
        const serialDecoder = new TextDecoder();
        m.FS.registerDevice(dev, {
          open:stream => { stream.seekable = false; }, close:() => {},
          read:(stream,buffer,offset,length) => {
            if (!uartInput.length) throw new m.FS.ErrnoError(6);
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
            const text = serialDecoder.decode(buffer.slice(offset,offset+length), {stream:true});
            serial = (serial + text).slice(-65536); emit('serial', text); return length;
          },
          poll:() => 4 | (uartInput.length ? 1 : 0),
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
  module = await createQemu(options);
  if (disposeRequested) { cleanup(); throw new Error('Instance disposed during start'); }
}
async function request(op, value) {
  if (op === 'start') return start(value);
  if (op === 'dispose') {
    disposeRequested=true;
    const workersTerminatedByDispose=workers.size;cleanup();
    return {workersRemaining:workers.size,workersTerminatedByDispose,workerCountScope:'nested-pthreads',
      enginePlacement:'dedicated-worker-v1',engineWorkersAtAcknowledgement:1,selfCloseAfterAcknowledgement:true};
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
  if (op === 'uart') throw new Error('This offline profile supports UART output only');
  throw new Error('Unsupported instance operation');
}
addEventListener('message', event => {
  if (port || closed || event.data?.type !== 'm5-qemu-engine-connect' || event.ports?.length !== 1) return;
  port = event.ports[0];
  port.onmessage = async ({data}) => {
    if (closed || !Number.isSafeInteger(data?.id)) return;
    try {
      const value = await request(data.op, data.value);
      if (closed || disposeRequested && data.op!=='dispose') return;
      port.postMessage({id:data.id,value});
      if (data.op === 'dispose') {
        // The private acknowledgement must precede port close and self.close.
        // The owner notification records intent, never proof of actual exit.
        closed=true;port.close();
        self.postMessage({type:'m5-qemu-engine-closing'});
        self.close();
      }
    } catch(error) {
      if (!closed && !disposeRequested) port.postMessage({id:data.id,error:String(error?.message||error)});
    }
  };
  port.start(); emit('connected',{});
});
self.postMessage({type:'m5-qemu-engine-listening'});
