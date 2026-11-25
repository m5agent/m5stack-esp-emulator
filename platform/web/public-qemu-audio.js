const AUDIO_PATCHES = ['cores3-i2s-tx-descriptor-pacing.patch', 'cores3-i2s-web-pcm-stream.patch'];
export const CORES3_WAV_SHA = '22eb0ffce846a6175de97e2c2f82c02bbef092724874b317297cf5c95751bff5';
export const CORES3_WAV_SD_SHA = '93a9550a6d325ec8be0d9710eb7c079af24ba7d5ffb8c5c2db423c26e6fb1233';
export const CORES3_MIC_FIRMWARE_SHA = 'b9fe8334023c1b1f95e7c51b3a63724e621a6789812083848ed3ea7eaa332d49';
export const CORES3_MIC_SOURCE_SHA = 'dc6979cf1209ead19085bb97450c91e644bbf45ae28d0d2faa702f189d7e0a8e';
export const QEMU_AUDIO_RATE = 48000;
export const QEMU_AUDIO_FRAMES = 8192;
const READ = 0, WRITE = 1, ACTIVE = 2, EPOCH = 3, DROPPED = 4, RENDERED = 5, STARVED = 6, NONZERO = 7;
const HEADER_BYTES = 8 * Int32Array.BYTES_PER_ELEMENT;
const MASK = QEMU_AUDIO_FRAMES - 1;

export function hasQemuAudioPatches(patches) {
  return Array.isArray(patches) && AUDIO_PATCHES.every(name => patches.some(
    row => /^patches\/qemu-wasm-probe\/\d{4}-/.test(row?.path)
      && row.path.slice('patches/qemu-wasm-probe/0000-'.length) === name && /^[0-9a-f]{64}$/.test(row.sha256)));
}

export function qemuAudioExample(request, {deviceId, inputSHA256, firmwareSHA256, sdSHA256, patches}) {
  if (deviceId !== 'cores3' || !hasQemuAudioPatches(patches)) return null;
  if (request === 'wav' && inputSHA256 === CORES3_WAV_SHA && firmwareSHA256 === CORES3_WAV_SHA && sdSHA256 === CORES3_WAV_SD_SHA) return 'wav';
  if (request === 'mic' && inputSHA256 === CORES3_MIC_FIRMWARE_SHA && firmwareSHA256 === CORES3_MIC_FIRMWARE_SHA) return 'mic';
  return null;
}

export function qemuAudioRing(buffer = new SharedArrayBuffer(HEADER_BYTES + QEMU_AUDIO_FRAMES * 2)) {
  if (!(buffer instanceof SharedArrayBuffer) || buffer.byteLength !== HEADER_BYTES + QEMU_AUDIO_FRAMES * 2)
    throw new Error('QEMU audio ring layout mismatch');
  const control = new Int32Array(buffer, 0, HEADER_BYTES / 4);
  const samples = new Int16Array(buffer, HEADER_BYTES);
  return {buffer, control, samples};
}

export function setQemuAudioActive({control}, active) {
  Atomics.store(control, ACTIVE, 0);
  Atomics.add(control, EPOCH, 1);
  if (active) Atomics.store(control, ACTIVE, 1);
}

export function qemuAudioStats({control}) {
  return {dropped:Atomics.load(control, DROPPED) >>> 0, rendered:Atomics.load(control, RENDERED) >>> 0,
    nonzero:Atomics.load(control, NONZERO) >>> 0, starved:Atomics.load(control, STARVED) >>> 0};
}

export function writeQemuAudio({control, samples}, bytes, offset, length) {
  const epoch = Atomics.load(control, EPOCH);
  if (!Atomics.load(control, ACTIVE) || length % 2) return length;
  const write = Atomics.load(control, WRITE);
  const used = (write - Atomics.load(control, READ)) >>> 0;
  const count = Math.min(length / 2, QEMU_AUDIO_FRAMES - used);
  for (let i = 0; i < count; i++) {
    const index = offset + i * 2;
    // Emscripten fd_write passes signed HEAP8 into the FS device callback.
    samples[(write + i) & MASK] = (bytes[index] & 0xff) | ((bytes[index + 1] & 0xff) << 8);
  }
  if (epoch === Atomics.load(control, EPOCH)) {
    Atomics.store(control, WRITE, write + count);
    Atomics.add(control, DROPPED, length / 2 - count);
  }
  return length;
}

export function qemuAudioReader({control, samples}) {
  let epoch = Atomics.load(control, EPOCH), buffering = true;
  return output => {
    output.fill(0);
    const read = Atomics.load(control, READ);
    const write = Atomics.load(control, WRITE);
    const current = Atomics.load(control, EPOCH);
    if (epoch !== current || !Atomics.load(control, ACTIVE)) {
      Atomics.store(control, READ, write);
      epoch = current;
      buffering = true;
      return;
    }
    const available = (write - read) >>> 0;
    if (buffering && available < 1024) return;
    buffering = false;
    const count = Math.min(output.length, available);
    let nonzero = 0;
    for (let i = 0; i < count; i++) {
      const sample = samples[(read + i) & MASK];
      output[i] = sample / 32768;
      if (sample) nonzero++;
    }
    Atomics.store(control, READ, read + count);
    if (current !== Atomics.load(control, EPOCH)) output.fill(0);
    else {
      Atomics.add(control, RENDERED, count);
      Atomics.add(control, NONZERO, nonzero);
    }
    if (count < output.length) {
      buffering = true;
      Atomics.add(control, STARVED, output.length - count);
    }
  };
}

export function qemuVirtualMic() {
  const buffer = new ArrayBuffer(32000);
  const pcm = new DataView(buffer);
  for (let i = 0; i < 16000; i++) pcm.setInt16(i * 2, Math.round(12000 * Math.sin(i * 2 * Math.PI * 440 / 16000)), true);
  return new Uint8Array(buffer);
}
