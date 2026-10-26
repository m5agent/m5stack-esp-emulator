let emu = null;
let running = false;
let uartAcc = '';
let shared = 0;
let lastSeq = -1;
let lastStateAt = 0;
let displayProtocol = 'none';
const BATCH = 50000;

function u32(bytes, offset) {
  return (bytes[offset] | (bytes[offset + 1] << 8) | (bytes[offset + 2] << 16) | (bytes[offset + 3] << 24)) >>> 0;
}

function readBig(address, length) {
  const out = new Uint8Array(length);
  for (let offset = 0; offset < length; offset += 4096) {
    out.set(emu.read_memory(address + offset, Math.min(4096, length - offset)), offset);
  }
  return out;
}

function emit(kind, payload = {}) {
  postMessage({ type: kind, ...payload });
}

function onUart(text) {
  if (!text) return;
  emit('uart', { data: text });
  uartAcc = (uartAcc + text).slice(-8192);
  const match = /M5EMU:SHARED=0x([0-9a-fA-F]{8})/.exec(uartAcc);
  if (match) {
    shared = parseInt(match[1], 16);
    lastSeq = -1;
    uartAcc = '';
    emit('shared', { address: shared });
  }
}

function pollShared() {
  if (!emu || !shared || displayProtocol !== 'm5emu-shared-v1') return;
  const header = emu.read_memory(shared, 52);
  if (u32(header, 0) !== 0x4D354555) return;
  const width = u32(header, 8);
  const height = u32(header, 12);
  const framebuffer = u32(header, 16);
  const sequence = u32(header, 20);
  const bytes = width * height * 2;
  if (!width || !height || width > 4096 || height > 4096 || bytes > 0x800000) return;
  if (sequence !== lastSeq) {
    lastSeq = sequence;
    const pixels = readBig(framebuffer, bytes);
    emit('frame', { width, height, sequence, pixels }, [pixels.buffer]);
  }
  const now = performance.now();
  if (now - lastStateAt > 200) {
    lastStateAt = now;
    emit('state', {
      cycles: emu.cycles(),
      gpio: Array.from(emu.gpio_state()),
      vibration: u32(header, 40),
      speakerEnable: u32(header, 44),
      brightness: u32(header, 48)
    });
  }
}

function loop() {
  if (!running) return;
  const started = performance.now();
  let delay = 0;
  while (running) {
    try {
      const output = emu.run_batch(BATCH);
      if (output) onUart(output);
      if (emu.needs_restart()) {
        emu.restart();
        shared = 0;
        lastSeq = -1;
        onUart('\r\n[restart]\r\n');
        break;
      }
      delay = emu.throttle_delay_ms(performance.now());
      if (delay > 0) break;
      if (performance.now() - started > 30) break;
    } catch (error) {
      running = false;
      emit('fatal', { message: error.message || String(error) });
      return;
    }
  }
  pollShared();
  setTimeout(loop, delay);
}

onmessage = async event => {
  const message = event.data;
  if (message.type === 'init') {
    try {
      const module = await import('/platform/runtime/wasm/esp_emu.js?v=20261020b');
      await module.default();
      emu = new module.WasmEmulator(message.chip);
      emu.load_default_rom();
      emu.set_boot_from_rom(true);
      emu.load_firmware(new Uint8Array(message.firmware));
      displayProtocol = message.displayProtocol || 'none';
      shared = 0;
      lastSeq = -1;
      uartAcc = '';
      running = true;
      emit('started', { chip: message.chip });
      loop();
    } catch (error) {
      emit('fatal', { message: error.message || String(error) });
    }
    return;
  }
  if (!emu) return;
  if (message.type === 'gpio') emu.gpio_set_input(message.pin, message.high);
  else if (message.type === 'uart_text') emu.uart_input(new TextEncoder().encode(message.data));
  else if (message.type === 'uart_bytes') emu.uart_input(new Uint8Array(message.data));
  else if (message.type === 'reset') {
    emu.restart();
    shared = 0;
    lastSeq = -1;
  } else if (message.type === 'pause') running = false;
  else if (message.type === 'resume') {
    if (!running) {
      running = true;
      loop();
    }
  }
};
