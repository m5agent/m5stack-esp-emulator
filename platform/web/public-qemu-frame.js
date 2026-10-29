// Copy only stable, real QEMU display updates from the shared snapshot ABI.
// No guest pixels, clocks or frame counters are synthesized here.
export function readSharedQemuFrame(module, previousSequence, display) {
  if (typeof module._m5_wasm_frame_state !== 'function') throw new Error('QEMU framebuffer ABI is unavailable');
  const pointer = module._m5_wasm_frame_state() >>> 0, heap = module.HEAPU8;
  if (!(heap.buffer instanceof SharedArrayBuffer) || pointer % 4 || pointer + 32 > heap.length)
    throw new Error('Invalid shared QEMU framebuffer metadata');
  const words = new Uint32Array(heap.buffer, pointer, 8);
  if (Atomics.load(words, 0) !== 0x4d354642) return null;
  const before = Atomics.load(words, 1);
  if (!before || before & 1 || before === previousSequence) return null;
  const width = words[2], height = words[3], stride = words[4], start = words[5], updates = words[6];
  // A concurrent surface resize can temporarily expose incomplete metadata.
  // Drop that snapshot before treating stable invalid bounds as an ABI error.
  if (Atomics.load(words, 1) !== before) return null;
  if (!width || !height || width > 1024 || height > 1024 || stride < width * 2 || stride > 2048 || start + stride * height > heap.length)
    throw new Error('Invalid QEMU framebuffer bounds');
  const pixels = new Uint8Array(width * height * 2);
  for (let y = 0; y < height; y++) pixels.set(heap.subarray(start + y * stride, start + y * stride + width * 2), y * width * 2);
  if (Atomics.load(words, 1) !== before) return null;
  if (width !== display.width || height !== display.height) throw new Error('QEMU framebuffer does not match the selected board');
  return {width, height, pixels, format:'rgb565le', source:'qemu-display-surface-shared', sourceSequence:before, sourceUpdates:updates};
}
