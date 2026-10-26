// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import { Component } from '../Component.js';

let sharedCtx = null;
function audioContext() {
  if (!sharedCtx) sharedCtx = new (globalThis.AudioContext || globalThis.webkitAudioContext)();
  if (sharedCtx.state === 'suspended') sharedCtx.resume();
  return sharedCtx;
}

/**
 * Speaker backed by WebAudio. Silent until `enabled` (browsers require a user
 * gesture before audio can start; the viewer resumes the context on first click).
 *
 *   speaker.tone(2000, 100, { wave: 'sine', volume: 0.5 })  // Hz, ms
 *   speaker.playPCM(int16, 16000)     // mono samples
 */
export class Speaker extends Component {
  static kind = 'speaker';

  constructor({ volume = 0.4, enabled = true, ...rest }) {
    super(rest);
    this.volume = volume;
    this.enabled = enabled;
    this.playing = 0;
  }

  setVolume(v) {
    this.volume = Math.max(0, Math.min(1, v));
  }

  #out(ctx) {
    const gain = ctx.createGain();
    gain.gain.value = this.volume * 0.25;
    gain.connect(ctx.destination);
    return gain;
  }

  #track(node, ms) {
    this.playing++;
    this.emit('sound', { playing: true });
    const done = () => {
      this.playing = Math.max(0, this.playing - 1);
      if (!this.playing) this.emit('sound', { playing: false });
    };
    node.onended = done;
    return ms;
  }

  tone(frequency = 1000, durationMs = 100, { wave = 'square', volume } = {}) {
    if (!this.enabled || typeof AudioContext === 'undefined') return;
    const ctx = audioContext();
    const osc = ctx.createOscillator();
    osc.type = wave;
    osc.frequency.value = frequency;
    const out = this.#out(ctx);
    if (volume != null) out.gain.value = volume * 0.25;
    const t = ctx.currentTime;
    out.gain.setTargetAtTime(0, t + durationMs / 1000 - 0.005, 0.003);
    osc.connect(out);
    osc.start(t);
    osc.stop(t + durationMs / 1000 + 0.02);
    this.#track(osc, durationMs);
  }

  /** Play mono PCM (Int16Array or Float32Array in [-1, 1]). */
  playPCM(samples, sampleRate = 16000) {
    if (!this.enabled || typeof AudioContext === 'undefined') return;
    const ctx = audioContext();
    const buf = ctx.createBuffer(1, samples.length, sampleRate);
    const ch = buf.getChannelData(0);
    if (samples instanceof Int16Array) for (let i = 0; i < samples.length; i++) ch[i] = samples[i] / 32768;
    else ch.set(samples);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.#out(ctx));
    src.start();
    this.#track(src, (samples.length / sampleRate) * 1000);
  }

  handle(cmd) {
    if (cmd.type === 'tone') return this.tone(cmd.frequency ?? cmd.freq, cmd.duration ?? cmd.ms, { wave: cmd.wave, volume: cmd.volume });
    if (cmd.type === 'pcm') return this.playPCM(cmd.data, cmd.sampleRate);
    if (cmd.type === 'volume') return this.setVolume(cmd.value);
    return super.handle(cmd);
  }

  getState() {
    return { volume: this.volume, enabled: this.enabled, playing: this.playing > 0 };
  }

  /** Call from a user-gesture handler to unlock audio. */
  static unlock() {
    if (typeof AudioContext !== 'undefined' && sharedCtx) sharedCtx.resume();
  }
}
