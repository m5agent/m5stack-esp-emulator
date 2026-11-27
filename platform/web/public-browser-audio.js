// The esp32sim protocol carries mono little-endian PCM directly from the
// guest I2S model. AudioBufferSourceNodes work without shared memory.
export function createBrowserAudioPlayer() {
  const context = new AudioContext({latencyHint:'interactive'});
  let next = 0, closed = false, active = true;
  const playing = new Set();
  void context.resume().catch(() => {});
  return {
    push(packet) {
      if (closed || !active || context.state !== 'running' || packet.byteLength < 7 || !(packet.byteLength % 2)) return;
      const pcm = new DataView(packet);
      const rate = pcm.getUint32(1, true), samples = (packet.byteLength - 5) / 2;
      if (rate < 3000 || rate > 192000 || samples > rate) return;
      const now = context.currentTime;
      if (next - now > 0.25) return;
      const buffer = context.createBuffer(1, samples, rate), channel = buffer.getChannelData(0);
      for (let i = 0; i < samples; ++i) channel[i] = pcm.getInt16(5 + 2 * i, true) / 32768;
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);
      source.onended = () => { playing.delete(source); source.disconnect(); };
      playing.add(source);
      const start = Math.max(next, now + 0.02);
      source.start(start);
      next = start + buffer.duration;
    },
    setActive(value) {
      active = value;
      if (!active) {
        for (const source of playing) source.stop();
        playing.clear();
        next = 0;
      }
    },
    close() {
      if (closed) return;
      this.setActive(false);
      closed = true;
      void context.close().catch(() => {});
    },
  };
}
