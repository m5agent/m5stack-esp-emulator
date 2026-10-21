// Worker: runs esp-emulator WASM, models StopWatch peripherals on top of the public JS API.
let emu = null, running = false, uartAcc = '', shared = 0, lastSeq = -1, spkRd = 0;
const BATCH = 50000;
function u32(b, o) { return (b[o] | (b[o+1] << 8) | (b[o+2] << 16) | (b[o+3] << 24)) >>> 0; }
function readBig(addr, len) {
  const out = new Uint8Array(len);
  for (let o = 0; o < len; o += 4096) out.set(emu.read_memory(addr + o, Math.min(4096, len - o)), o);
  return out;
}
let S = null; // parsed shared header
function pollShared() {
  if (!shared) return;
  const h = emu.read_memory(shared, 52);
  if (u32(h, 0) !== 0x4D354555) return;
  S = { w: u32(h, 8), h: u32(h, 12), fb: u32(h, 16), seq: u32(h, 20), spk: u32(h, 24), spkLen: u32(h, 28),
        spkRate: u32(h, 32), spkWr: u32(h, 36), vib: u32(h, 40), spkEn: u32(h, 44) };
  if (S.seq !== lastSeq) {
    lastSeq = S.seq;
    const px = readBig(S.fb, S.w * S.h * 2);
    postMessage({ type: 'frame', w: S.w, h: S.h, seq: S.seq, px }, [px.buffer]);
  }
  if (S.spkWr !== spkRd) {
    let n = (S.spkWr - spkRd) >>> 0;
    if (n > S.spkLen) { spkRd = (S.spkWr - S.spkLen) >>> 0; n = S.spkLen; }
    const pcm = new Int16Array(n);
    let got = 0;
    while (got < n) {
      const idx = (spkRd + got) % S.spkLen, chunk = Math.min(n - got, S.spkLen - idx, 2048);
      const b = emu.read_memory(S.spk + idx * 2, chunk * 2);
      pcm.set(new Int16Array(b.buffer, b.byteOffset, chunk), got); got += chunk;
    }
    spkRd = S.spkWr;
    postMessage({ type: 'audio', rate: S.spkRate, pcm }, [pcm.buffer]);
  }
  postMessage({ type: 'state', vib: S.vib, gpio: Array.from(emu.gpio_state()), cycles: emu.cycles() });
}
function onUart(s) {
  postMessage({ type: 'uart', data: s });
  uartAcc = (uartAcc + s).slice(-4096);
  const m = /M5EMU:SHARED=0x([0-9a-fA-F]{8})/.exec(uartAcc);
  if (m) { shared = parseInt(m[1], 16); uartAcc = ''; lastSeq = -1; postMessage({ type: 'shared', addr: shared }); }
}
let lastPoll = 0;
function loop() {
  if (!running) return;
  const t0 = performance.now(); let delay = 0;
  while (running) {
    const out = emu.run_batch(BATCH);
    if (out) onUart(out);
    if (emu.needs_restart()) { emu.restart(); shared = 0; spkRd = 0; onUart('\r\n[restart]\r\n'); break; }
    const d = emu.throttle_delay_ms(performance.now());
    if (d > 0) { delay = d; break; }
    if (performance.now() - t0 > 30) break;
  }
  if (performance.now() - lastPoll > 50) { lastPoll = performance.now(); pollShared(); }
  setTimeout(loop, delay);
}
onmessage = async (e) => {
  const m = e.data;
  if (m.type === 'init') {
    const mod = await import('/platform/runtime/wasm/esp_emu.js?v=20261020b'); await mod.default();
    emu = new mod.WasmEmulator('esp32s3'); emu.load_default_rom(); emu.set_boot_from_rom(true);
    emu.load_firmware(new Uint8Array(m.firmware));
    for (const p of [0, 1, 2]) emu.gpio_set_input(p, true); // GPIO0 BOOT high, keys released (pull-ups)
    running = true; postMessage({ type: 'started' }); loop();
  } else if (!emu) return;
  else if (m.type === 'gpio') emu.gpio_set_input(m.pin, m.high);
  else if (m.type === 'uart') emu.uart_input(new TextEncoder().encode(m.data));
  else if (m.type === 'reset') { emu.restart(); shared = 0; spkRd = 0; lastSeq = -1; }
  else if (m.type === 'pause') running = false;
  else if (m.type === 'resume') { if (!running) { running = true; loop(); } }
};
