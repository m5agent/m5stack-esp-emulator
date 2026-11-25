import {QEMU_AUDIO_RATE,qemuAudioRing,qemuAudioStats,setQemuAudioActive} from './public-qemu-audio.js';

// Construct and request resume in the Start click, before async firmware intake.
export function createQemuAudioPlayer() {
  const context = new AudioContext({sampleRate: QEMU_AUDIO_RATE, latencyHint: 'interactive'});
  const ring = qemuAudioRing();
  let closed = false, node;
  const resumed = context.resume();
  resumed.catch(() => {});
  return {
    ring: ring.buffer,
    async connect() {
      await resumed;
      if (closed) return false;
      if (context.sampleRate !== QEMU_AUDIO_RATE) throw new Error('浏览器无法使用 48 kHz 模拟音频。');
      await context.audioWorklet.addModule(new URL('./public-qemu-audio-worklet.js', import.meta.url));
      if (closed) return false;
      node = new AudioWorkletNode(context, 'qemu-pcm-player', {numberOfInputs: 0, numberOfOutputs: 1,
        outputChannelCount: [1], processorOptions: {ring: ring.buffer}});
      node.connect(context.destination);
      return true;
    },
    setActive(active) { if (!closed) setQemuAudioActive(ring, active); },
    stats() { return qemuAudioStats(ring); },
    close() {
      if (closed) return;
      closed = true;
      setQemuAudioActive(ring, false);
      node?.disconnect();
      void context.close().catch(() => {});
    },
  };
}
