import { createJitHost } from './jit.mjs';
import { createPacing } from './pacing.mjs';
import { applyExperiments } from './experiments.mjs';
let pacing = createPacing();
// Optional host-stage diagnostics. Run entry is not controller consumption;
// framebuffer output is not physical panel scanout. Epoch times match the page.
let traceEnabled = false, pendingInputTrace = [];
const traceNow = () => performance.timeOrigin + performance.now();
// esp32sim in a Web Worker: owns the wasm instance, paces it to wall time, and relays the UI
// protocol (docs/web-ui.md) to the page as postMessage — text as strings, binary as ArrayBuffers.
let CPU_HZ = 240e6;   // replaced from the module once an emulator exists: the C3 runs at 160 MHz
let wasm = null, emu = 0, running = false, t0 = 0, resyncs = 0, lastStat = { wall: 0, insns: 0, cycles: 0 };
let loopGeneration = 0, booted = false, catchupTurns = 0;
let flashShadow = null, flashWatchId = null, flashScanAt = 0;
const FLASH_PAGE = 4096;
let sdShadow=null,sdWatchId=null,sdScanAt=0;
function sdBytes() {if(!emu||!wasm.esp32sim_sd_len)throw new Error('SD images unsupported by this WASM');return mem().subarray(wasm.esp32sim_sd_ptr(emu),wasm.esp32sim_sd_ptr(emu)+wasm.esp32sim_sd_len(emu));}
function collectSd(force=false) {
  if(!sdShadow||!force&&performance.now()-sdScanAt<1500)return;sdScanAt=performance.now();
  const bytes=sdBytes(),words=new Uint32Array(bytes.buffer,bytes.byteOffset,bytes.length/4),old=new Uint32Array(sdShadow.buffer),pages=[];
  for(let offset=0;offset<bytes.length;offset+=FLASH_PAGE){let changed=false;for(let i=offset/4;i<(offset+FLASH_PAGE)/4;i++)if(words[i]!==old[i]){changed=true;break;}
    if(changed){const data=bytes.slice(offset,offset+FLASH_PAGE).buffer;sdShadow.set(new Uint8Array(data),offset);pages.push({offset,data});}}
  if(pages.length)postMessage({sdDelta:{watchId:sdWatchId,pages}},pages.map(p=>p.data));
}
function flashBytes() {
  if (!emu || !wasm.esp32sim_flash_ptr || !wasm.esp32sim_flash_len) throw new Error('Flash snapshots are unsupported by this WASM build');
  return mem().subarray(wasm.esp32sim_flash_ptr(emu), wasm.esp32sim_flash_ptr(emu) + wasm.esp32sim_flash_len(emu));
}
function collectFlash(force = false) {
  if (!flashShadow || !force && performance.now() - flashScanAt < 500) return;
  flashScanAt = performance.now();
  const bytes = flashBytes(), words = new Uint32Array(bytes.buffer, bytes.byteOffset, bytes.length / 4), old = new Uint32Array(flashShadow.buffer);
  const pages = [];
  for (let offset = 0; offset < bytes.length; offset += FLASH_PAGE) {
    let changed = false;
    for (let i = offset / 4; i < (offset + FLASH_PAGE) / 4; i++) if (words[i] !== old[i]) { changed = true; break; }
    if (changed) { const data = bytes.slice(offset, offset + FLASH_PAGE).buffer; flashShadow.set(new Uint8Array(data), offset); pages.push({offset, data}); }
  }
  if (pages.length) postMessage({flashDelta: {watchId: flashWatchId, pages}}, pages.map(page => page.data));
}
let net = 0, netNodes = 0, netT0 = 0;   // a network of motes: several emulators on one medium
const enc = new TextEncoder(), dec = new TextDecoder();
const mem = () => new Uint8Array(wasm.memory.buffer);
function put(bytes) { const p = wasm.esp32sim_alloc(bytes.length); mem().set(bytes, p); return p; }
function withBytes(bytes, f) { const p = put(bytes); try { return f(p, bytes.length); } finally { wasm.esp32sim_free(p, bytes.length); } }
const blockJit = createJitHost(() => wasm);
let experiments = [], setupError = null, smoothDisplay = false;
let frameAck = false, framesInFlight = 0, pendingFrame = null;
const imports = { env: { ...blockJit.imports, host_log: (p, n) => postMessage({ log: dec.decode(mem().subarray(p, p + n)) }) } };

function drain() {
  const n = wasm.esp32sim_out_take(emu);
  for (let i = 0; i < n; i++) {
    const kind = wasm.esp32sim_out_kind(emu, i), p = wasm.esp32sim_out_ptr(emu, i), len = wasm.esp32sim_out_len(emu, i);
    if (kind === 1) postMessage({ text: dec.decode(mem().subarray(p, p + len)) });
    else {
      const display = mem()[p] === 1;
      // Backpressure is opt-in: legacy consumers need not acknowledge frames. A page
      // that has not handled its last two frames gets only the newest retained frame.
      const frameTrace = traceEnabled && display
        ? { stage: 'worker-frame', atMs: traceNow(), cycles: wasm.esp32sim_cycles(emu) } : undefined;
      if (frameAck && display && framesInFlight >= 2) { pendingFrame = { bin: mem().slice(p, p + len).buffer, frameTrace, ack: true }; continue; }
      const buf = new ArrayBuffer(len);
      new Uint8Array(buf).set(mem().subarray(p, p + len));
      if (frameAck && display) { framesInFlight++; pendingFrame = null; }
      postMessage({ bin: buf, frameTrace, ack: frameAck && display }, [buf]);
    }
  }
}

function loop(generation = loopGeneration) {
  if (!running || generation !== loopGeneration) return;
  const now = performance.now();
  let cur = wasm.esp32sim_cycles(emu);
  let target = (now - t0) / 1000 * CPU_HZ;
  if (target - cur > CPU_HZ * 0.5) { t0 = now - cur / CPU_HZ * 1000; target = cur + CPU_HZ * 0.02; resyncs++; }   // hopelessly behind: skip, don't burst
  const turnMs = pacing.turnMs(now);
  while (cur < target) {
    const before = performance.now();
    const remaining = pacing.sliceCycles(target - cur, turnMs - (before - now), now);
    const previous = cur;
    const inputTraceIds = pendingInputTrace;
    if (inputTraceIds.length) { postMessage({ touchTrace: { stage: 'run-entry', ids: inputTraceIds, atMs: traceNow(), cycles: cur } }); pendingInputTrace = []; }
    const rc = wasm.esp32sim_run(emu, remaining, Date.now());
    cur = wasm.esp32sim_cycles(emu);
    if (inputTraceIds.length) postMessage({ touchTrace: { stage: 'run-exit', ids: inputTraceIds, atMs: traceNow(), cycles: cur } });
    pacing.observe(cur - previous, performance.now() - before);
    drain();
    collectFlash();collectSd();
    if (rc !== 0) { running = false; postMessage({ stopped: rc }); return; }
    if (performance.now() - now >= turnMs) break;                       // let messages flow, come back
  }
  const aheadMs = cur / CPU_HZ * 1000 - (performance.now() - t0);
  const wall = performance.now();
  if (wall - lastStat.wall > 1000) {
    const insns = wasm.esp32sim_insns(emu);
    // Emulated seconds per wall second over the window. Unlike `behind`, a resync does not reset it.
    const speed = Math.max(0, cur - lastStat.cycles) / CPU_HZ / ((wall - lastStat.wall) / 1000);
    postMessage({ pace: { behind: Math.max(0, -aheadMs / 1000), resyncs, speed, mips: Math.max(0, (insns - lastStat.insns)) / (wall - lastStat.wall) / 1000 } });
    lastStat = { wall, insns, cycles: cur };
  }
  // Only yield immediately when this turn left catch-up work unfinished. Once we reach
  // its target, sleep even if running the guest has put us slightly behind wall time.
  // MessageChannel avoids the nested timer clamp during expensive interactive turns.
  // A self-posting MessagePort can keep draining on some hosts before another
  // port (including stop/input commands) gets serviced. Bound that chain without
  // reintroducing a clamped timer on every interactive turn (EX117).
  if (cur < target && ++catchupTurns < 8) yieldPort.postMessage(generation);
  else {
    catchupTurns = 0;
    setTimeout(() => loop(generation), Math.max(1, Math.min(20, aheadMs)));
  }
}
const yieldChannel = typeof MessageChannel === 'function' ? new MessageChannel() : null;
const yieldPort = yieldChannel ? yieldChannel.port2 : { postMessage: generation => setTimeout(() => loop(generation), 0) };
if (yieldChannel) yieldChannel.port1.onmessage = event => loop(event.data);

// A network runs on its own clock: network time in nanoseconds paced to the wall clock, with
// each node's console and LED drained per turn. The medium and the stepping are in the module
// (esp32c6::net) — this only says how far to run and relays what came out.
function netLoop(generation = loopGeneration) {
  if (!running || generation !== loopGeneration) return;
  const now = performance.now();
  const targetNs = (now - netT0) * 1e6;
  const curNs = wasm.esp32sim_net_now_ns(net);
  if (targetNs - curNs > 5e8) { netT0 = now - curNs / 1e6; resyncs++; }   // hopelessly behind: skip
  const turnStart = performance.now();
  while (wasm.esp32sim_net_now_ns(net) < targetNs) {
    wasm.esp32sim_net_run(net, Math.min(targetNs, wasm.esp32sim_net_now_ns(net) + 5e6));   // 5 ms of network time
    if (performance.now() - turnStart >= 12) break;
  }
  const stats = [];
  for (let i = 0; i < netNodes; i++) {
    const len = wasm.esp32sim_net_console_take(net, i);
    if (len) { const p = wasm.esp32sim_net_console_ptr(net); postMessage({ netText: { node: i, data: dec.decode(mem().subarray(p, p + len)) } }); }
    stats.push({ tx: wasm.esp32sim_net_stat(net, i, 0), rx: wasm.esp32sim_net_stat(net, i, 1),
                 dropped: wasm.esp32sim_net_stat(net, i, 2), ns: wasm.esp32sim_net_stat(net, i, 3),
                 led: wasm.esp32sim_net_stat(net, i, 4), halted: wasm.esp32sim_net_stat(net, i, 6) !== 0 });
  }
  const wall = performance.now();
  if (wall - lastStat.wall > 500) {
    // `t` is the protocol's message type, so the network clock travels as `sec`
    postMessage({ netStat: { sec: wasm.esp32sim_net_now_ns(net) / 1e9, nodes: stats, resyncs,
                             behind: Math.max(0, (targetNs - wasm.esp32sim_net_now_ns(net)) / 1e9) } });
    lastStat = { wall, insns: 0 };
  }
  setTimeout(() => netLoop(generation), 5);
}

onmessage = async (ev) => {
  const m = ev.data;
  try {
    if (m.op === 'frame-ack') {
      if (!frameAck) return;
      framesInFlight = Math.max(0, framesInFlight - 1);
      if (pendingFrame && framesInFlight < 2) { const message = pendingFrame; pendingFrame = null; framesInFlight++; postMessage(message, [message.bin]); }
      return;
    }
    if (m.op === 'init') { frameAck = m.frameAck === true; traceEnabled = !!m.touchTrace; const r = await WebAssembly.instantiate(m.wasm, imports); wasm = r.instance.exports;  postMessage({ ready: true }); }
    else if (m.op === 'create') {
      running = false; loopGeneration++; booted = false;
      flashShadow = null; flashWatchId = null;
      // Keep credits for already posted frames until their ACKs arrive, but never send
      // a retained frame from the emulator being replaced.
      pendingFrame = null;sdShadow=null;sdWatchId=null;
      pacing = createPacing(); catchupTurns = 0;
      pendingInputTrace = [];
      if (emu) { wasm.esp32sim_delete(emu); emu = 0; }
      emu = withBytes(enc.encode(m.board), (p, n) => wasm.esp32sim_new(p, n, m.flash_mb | 0, m.psram_mb | 0));
      if (emu !== 0) wasm.esp32sim_set_jit(emu, m.jit === false ? 0 : 1);
      setupError = null;
      experiments = m.experiments === undefined ? [] : m.experiments;
      smoothDisplay = m.smoothDisplay === true;
      if (emu !== 0 && wasm.esp32sim_cpu_hz) CPU_HZ = wasm.esp32sim_cpu_hz(emu);
      postMessage({ created: emu !== 0, flashStorage: !!wasm.esp32sim_flash_ptr && !!wasm.esp32sim_flash_len });
    }
    else if (m.op === 'sd-attach') {if(booted||running)throw new Error('Attach SD only before boot');if(withBytes(new Uint8Array(m.data),(p,n)=>wasm.esp32sim_load(emu,8,p,n))!==0)throw new Error('SD attach rejected');postMessage({sdReply:m.requestId,ok:true});}
    else if (m.op === 'sd-export') {const data=sdBytes().slice().buffer;postMessage({sdReply:m.requestId,data},[data]);}
    else if (m.op === 'sd-watch') {sdShadow=sdBytes().slice();sdWatchId=m.requestId;sdScanAt=performance.now();postMessage({sdReply:m.requestId,ok:true});}
    else if (m.op === 'sd-flush') {collectSd(true);postMessage({sdReply:m.requestId,ok:true});}
    else if (m.op === 'flash-snapshot') { const data = flashBytes().slice().buffer; postMessage({flashReply: m.requestId, data}, [data]); }
    else if (m.op === 'flash-watch') { flashShadow = flashBytes().slice(); flashWatchId = m.requestId; flashScanAt = performance.now(); postMessage({flashReply: m.requestId, ok: true}); }
    else if (m.op === 'flash-flush') { collectFlash(true); postMessage({flashReply: m.requestId, ok: true}); }
    else if (m.op === 'flash-restore') {
      if (running || booted) throw new Error('Restore Flash only before boot');
      const size = flashBytes().length, seen = new Set();
      if (!Array.isArray(m.pages) || m.pages.length > size / FLASH_PAGE) throw new Error('Invalid Flash restore pages');
      for (const {offset, data} of m.pages) {
        if (!Number.isInteger(offset) || offset < 0 || offset % FLASH_PAGE || offset + FLASH_PAGE > size || seen.has(offset) || !(data instanceof ArrayBuffer) || data.byteLength !== FLASH_PAGE) throw new Error('Invalid Flash restore page');
        seen.add(offset);
      }
      for (const {offset, data} of m.pages) if (withBytes(new Uint8Array(data), (p, n) => wasm.esp32sim_load_at(emu, offset, p, n)) !== 0) throw new Error('Flash restore failed');
      postMessage({flashReply: m.requestId, ok: true});
    }
    else if (m.op === 'load') { const rc = withBytes(new Uint8Array(m.data), (p, n) => m.at !== undefined ? wasm.esp32sim_load_at(emu, m.at >>> 0, p, n) : wasm.esp32sim_load(emu, m.kind, p, n)); postMessage({ loaded: m.at !== undefined ? 'at' + m.at : m.kind, ok: rc === 0 }); }
    else if (m.op === 'stub') { if (withBytes(enc.encode(m.spec), (p, n) => wasm.esp32sim_stub_spec(emu, p, n)) !== 0) setupError ||= 'invalid stub: ' + m.spec; }
    else if (m.op === 'wifi') { if (withBytes(enc.encode(m.spec), (p, n) => wasm.esp32sim_wifi(emu, p, n)) !== 0) setupError ||= 'invalid WiFi configuration (see console)'; }
    else if (m.op === 'start') {
      // Optional timing-model exports (`?timing=hw`), applied after the loads and before the first instruction.
      running = false; loopGeneration++; booted = false;
      if (!emu) throw new Error('no emulator to start');
      if (setupError) throw new Error(setupError);
      applyExperiments(wasm, emu, experiments);
      if (smoothDisplay && (!wasm.esp32sim_set_smooth_display || wasm.esp32sim_set_smooth_display(emu, 1) !== 0)) throw new Error('smooth display publication is unsupported');
      const rc = wasm.esp32sim_boot(emu, m.appDirect ? 1 : 0); if (rc === 0) { running = true; booted = true; t0 = performance.now(); lastStat = { wall: t0, insns: wasm.esp32sim_insns(emu), cycles: wasm.esp32sim_cycles(emu) }; loop(); } postMessage({ started: rc === 0 }); }
    else if (m.op === 'resume') {
      if (!emu || !booted) throw new Error('no booted emulator to resume');
      if (!running) {
        loopGeneration++; pacing = createPacing(); catchupTurns = 0;
        const wall = performance.now(), cycles = wasm.esp32sim_cycles(emu);
        t0 = wall - cycles / CPU_HZ * 1000;
        lastStat = { wall, insns: wasm.esp32sim_insns(emu), cycles };
        running = true; loop();
      }
      postMessage({ resumed: true });
    }
    else if (m.op === 'net-create') {
      flashShadow = null; flashWatchId = null;sdShadow=null;sdWatchId=null;
      setupError = null;
      running = false; loopGeneration++; booted = false;
      pendingFrame = null;
      if (net) { wasm.esp32sim_net_delete(net); net = 0; }
      if (emu) { wasm.esp32sim_delete(emu); emu = 0; }
      net = wasm.esp32sim_net_new(m.slice_ns || 0);
      netNodes = 0;
      for (const node of m.nodes) {
        const mac = (node.mac || '02:00:00:00:00:0' + (netNodes + 1)).split(':').map(h => parseInt(h, 16));
        const added = withBytes(new Uint8Array(mac), (mp) => withBytes(enc.encode(node.board || m.board || 'none'),
          (bp, bn) => wasm.esp32sim_net_add(net, mp, node.flash_mb || m.flash_mb || 2, (node.start_ms || 0) * 1e6, node.x || 0, node.y || 0, bp, bn)));
        if ((added >>> 0) === 0xffffffff) {
          wasm.esp32sim_net_delete(net); net = 0; netNodes = 0;
          break;
        }
        netNodes++;
      }
      postMessage({ created: net !== 0, nodes: netNodes });
    }
    else if (m.op === 'net-load') { const rc = withBytes(new Uint8Array(m.data), (p, n) => wasm.esp32sim_net_load(net, m.node, m.kind, p, n)); postMessage({ loaded: 'n' + m.node + ':' + m.kind, ok: rc === 0 }); }
    else if (m.op === 'net-stub') { if (withBytes(enc.encode(m.spec), (p, n) => wasm.esp32sim_net_stub_spec(net, m.node, p, n)) !== 0) setupError ||= 'invalid stub for node ' + m.node + ': ' + m.spec; }
    else if (m.op === 'net-start') { if (setupError) throw new Error(setupError); const rc = wasm.esp32sim_net_boot(net); if (rc === 0) { running = true; netT0 = performance.now(); netLoop(); } postMessage({ started: rc === 0 }); }
    else if (m.op === 'stop') { running = false; loopGeneration++; collectFlash(true);collectSd(true); postMessage({ stopped: 0 }); }
    else if (m.op === 'imu') {
      const values = [...(m.accelG || []), ...(m.gyroDps || [])];
      const ok = !!emu && values.length === 6 && values.every(Number.isFinite) && !!wasm.esp32sim_set_imu_sample
        && wasm.esp32sim_set_imu_sample(emu, ...values) === 0;
      postMessage({ imuApplied: m.inputId, ok, time: emu ? wasm.esp32sim_cycles(emu) / CPU_HZ : 0 });
    }
    else if (m.op === 'text-batch') {
      // A passive connector unplug changes its bounded child routes before the
      // next guest slice. One receipt anchors recording; no CPU work is skipped.
      if (!Array.isArray(m.data) || m.data.length > 3 || m.data.some(data => typeof data !== 'string' || data.length > 1024)) throw new Error('invalid connector input batch');
      pacing.input(performance.now());
      for (const data of m.data) withBytes(enc.encode(data), (p, n) => wasm.esp32sim_in_text(emu, p, n));
      if (m.inputId !== undefined) postMessage({ inputQueued:m.inputId,time:wasm.esp32sim_cycles(emu)/CPU_HZ });
    }
    else if (m.op === 'lora-read' || m.op === 'lora-receive') {
      let result = {ok:false,code:1};
      if (emu && wasm.esp32sim_lora_snapshot && wasm.esp32sim_lora_receive) {
        if (m.op === 'lora-receive') {
          const code=withBytes(enc.encode(JSON.stringify(m.packet)),(p,n)=>wasm.esp32sim_lora_receive(emu,p,n));
          result={ok:code===0,code};
        } else {
          const capacity=16384,p=wasm.esp32sim_alloc(capacity);
          try {const n=wasm.esp32sim_lora_snapshot(emu,p,capacity);result=n>0&&n<=capacity?{ok:true,state:JSON.parse(dec.decode(mem().subarray(p,p+n)))}:{ok:false,code:1};}
          finally {wasm.esp32sim_free(p,capacity);}
        }
      }
      postMessage({loraResult:m.requestId,...result,time:emu?wasm.esp32sim_cycles(emu)/CPU_HZ:0});
    }
    else if (m.op === 'text') {
      if (traceEnabled && m.touchTrace) {
        postMessage({ touchTrace: { stage: 'worker-receive', ...m.touchTrace, atMs: traceNow(), cycles: wasm.esp32sim_cycles(emu) } });
        if (pendingInputTrace.length < 2048) pendingInputTrace.push(m.touchTrace.id);
      }
      pacing.input(performance.now());
      withBytes(enc.encode(m.data), (p, n) => wasm.esp32sim_in_text(emu, p, n));
      // Opt-in queue receipt: the command is in the emulator inbox, not yet observed
      // by firmware. Its current guest clock anchors paced input on a slow host.
      if (m.inputId !== undefined) postMessage({ inputQueued: m.inputId, time: wasm.esp32sim_cycles(emu) / CPU_HZ });
    }
    else if (m.op === 'bin') {
      pacing.input(performance.now());
      const data = new Uint8Array(m.data);
      if (data.length > 8 * 1024 * 1024) {
        postMessage({ text: JSON.stringify({ t: 'camera-error', message: 'input exceeds 8 MiB' }) });
        return;
      }
      withBytes(data, (p, n) => wasm.esp32sim_in_bin(emu, p, n));
    }
  } catch (err) { postMessage({ log: '[worker] ' + (err && err.stack || err) }); running = false; loopGeneration++; if (m.op === 'start' || m.op === 'net-start') postMessage({ started: false, error: err.message || String(err) }); else if (m.op === 'resume') postMessage({ resumed: false, error: err.message || String(err) }); else if (m.op.startsWith('sd-')) postMessage({sdReply:m.requestId,ok:false,error:err.message||String(err)}); else if (m.op.startsWith('flash-')) postMessage({flashReply: m.requestId, ok: false, error: err.message || String(err)}); else postMessage({ stopped: 1 }); }
};
