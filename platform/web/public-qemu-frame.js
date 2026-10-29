import {qemuOnboardOutputQueries, validateQemuOnboardState} from './public-qemu-profiles.js';

// Copy only stable, real QEMU display updates from the shared snapshot ABI.
// No guest pixels, clocks or frame counters are synthesized here.
export function readSharedQemuFrame(module, previousSequence, display) {
  if (!display) throw new Error('A headless QEMU profile has no framebuffer');
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

/** Read real RMT-decoded output, dropping snapshots spanning an LED update. */
export async function readQemuOnboardOutputs(profile, qmp) {
  const [rgb, frames, pressed] = qemuOnboardOutputQueries(profile);
  const before = await qmp(frames.execute, frames.arguments);
  if (!Number.isSafeInteger(before) || before < 0) throw new Error('Invalid QEMU RMT frame counter');
  const [color, down] = await Promise.all([qmp(rgb.execute, rgb.arguments), qmp(pressed.execute, pressed.arguments)]);
  const after = await qmp(frames.execute, frames.arguments);
  if (!Number.isSafeInteger(after) || after < 0) throw new Error('Invalid QEMU RMT frame counter');
  if (before !== after) return null;
  return validateQemuOnboardState(profile, {schema_version:1,device_id:profile.deviceId,
    source:'qemu-rmt-qom-readback',path:profile.outputs.path,led_rgb:color,led_frames:after,pressed:down});
}

/** Output-only model commands from a validated same-worker QOM observation. */
export function qemuOnboardVisualCommands(profile, state) {
  validateQemuOnboardState(profile, state);
  if(profile.outputs.kind==='matrix-ws2812-qom-v1') {
    const uniform=state.led_rgb.every(color=>color===state.led_rgb[0]), color=state.led_rgb[0];
    return [...profile.outputs.ledTargets.map(target=>({type:'led',target,known:uniform&&state.led_frames>0,color,brightness:1,on:color!==0})),
      {type:'button-state',target:profile.outputs.buttonTarget,pressed:state.pressed}];
  }
  return [{type:'led',target:profile.outputs.ledTarget,known:state.led_frames > 0,
    color:state.led_rgb,brightness:1,on:state.led_rgb !== 0},
  {type:'button-state',target:profile.outputs.buttonTarget,pressed:state.pressed}];
}
