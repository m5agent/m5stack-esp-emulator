// Optional, read-only electrical PWM audition. No physical acoustic model.
const FIELDS = ['frequency-hz', 'duty-pct'];
const own = (value, field) => value != null && Object.hasOwn(value, field);

function outputSchema(schema, duty) {
  return schema && ['number', 'integer'].includes(schema.type) && schema.readOnly === true
    && Number.isFinite(schema.minimum) && schema.minimum >= 0
    && (schema.maximum === undefined || Number.isFinite(schema.maximum) && schema.maximum >= schema.minimum)
    && (!duty || Number.isFinite(schema.maximum) && schema.maximum <= 100)
    && (schema.enum === undefined || Array.isArray(schema.enum) && schema.enum.length > 0
      && schema.enum.every(value => Number.isFinite(value)));
}

export function buzzerReadback(unit, definition, {running, source, frozenDefinitions, attached = true} = {}) {
  if (!attached || running !== true || source !== 'live' || frozenDefinitions !== true
    || unit?.unit_id !== 'buzzer' || definition?.id !== 'buzzer'
    || unit.source !== 'guest-qom' || unit.available !== true
    || unit.errors != null && (typeof unit.errors !== 'object' || Array.isArray(unit.errors) || Object.keys(unit.errors).length)) return null;
  for (const field of FIELDS) {
    const schema = definition.outputs?.[field], value = unit.properties?.[field];
    if (own(definition.inputs, field) || !outputSchema(schema, field === 'duty-pct')
      || !own(unit.properties, field) || !Number.isFinite(value)
      || schema.type === 'integer' && !Number.isInteger(value)
      || value < schema.minimum || schema.maximum !== undefined && value > schema.maximum
      || schema.enum && !schema.enum.includes(value)) return null;
  }
  return {frequency: unit.properties['frequency-hz'], duty: unit.properties['duty-pct']};
}

// Fourier series of a centered unit-height PWM pulse with its DC removed.
// Keep actual duty-dependent harmonics and amplitude; normalization would hide
// their amplitude changes. Truncate at Nyquist and cap work for low frequencies.
export function pwmCoefficients(frequency, duty, sampleRate) {
  if (!Number.isFinite(frequency) || frequency <= 0 || !Number.isFinite(duty) || duty <= 0 || duty >= 100
    || !Number.isFinite(sampleRate) || sampleRate <= 0 || frequency >= sampleRate / 2) return null;
  const count = Math.min(256, Math.ceil(sampleRate / 2 / frequency) - 1);
  const real = new Float32Array(count + 1), imag = new Float32Array(count + 1);
  for (let n = 1; n <= count; n++) real[n] = 2 * Math.sin(Math.PI * n * duty / 100) / (Math.PI * n);
  return {real, imag};
}

export class UnitAudio {
  constructor({createContext = () => new (globalThis.AudioContext || globalThis.webkitAudioContext)(), onChange = () => {}} = {}) {
    Object.assign(this, {createContext, onChange});
    this.epoch = 0;
    this.enabled = this.pending = this.disposed = false;
    this.signal = this.context = this.oscillator = this.gain = null;
    this.message = '默认静音';
  }

  notify() { this.onChange(this); }

  observe(unit, definition, options = {}) {
    if (this.disposed) return;
    if (this.sessionId !== options.sessionId) {
      this.mute();
      this.sessionId = options.sessionId;
    }
    this.signal = typeof options.sessionId === 'string' && options.sessionId
      ? buzzerReadback(unit, definition, options) : null;
    if (!this.signal) {
      this.mute('观测未确认 · 静音');
      return;
    }
    if (this.enabled && !this.pending) this.play();
    else this.notify();
  }

  enable() {
    if (this.disposed || !this.signal) return Promise.resolve(false);
    if (this.enabled) return this.activation || Promise.resolve(true);
    this.enabled = this.pending = true;
    this.message = '正在启用声音…';
    const epoch = ++this.epoch;
    let context;
    try {
      context = this.createContext();
      this.context = context;
      this.stateChanged = () => {
        if (this.context === context && !this.pending && context.state !== 'running') this.mute('声音已中断 · 静音');
      };
      context.addEventListener('statechange', this.stateChanged);
      // Called synchronously inside the user's click, before any await.
      const resumed = context.resume();
      this.notify();
      this.activation = this.finishEnable(resumed, context, epoch);
      return this.activation;
    } catch {
      if (epoch === this.epoch) this.mute('声音未启用 · 请再次点击');
      return Promise.resolve(false);
    }
  }

  async finishEnable(resumed, context, epoch) {
    try {
      await resumed;
      if (this.disposed || epoch !== this.epoch || this.context !== context || !this.enabled || !this.signal) return false;
      if (context.state !== 'running') throw new Error('AudioContext 未运行');
      this.pending = false;
      return this.play();
    } catch {
      if (epoch === this.epoch) this.mute('声音未启用 · 请再次点击');
      return false;
    } finally {
      if (epoch === this.epoch) this.activation = null;
    }
  }

  stopTone() {
    if (this.gain) {
      try { this.gain.gain.cancelScheduledValues(this.context.currentTime); this.gain.gain.setValueAtTime(0, this.context.currentTime); } catch { /* context can already be closed */ }
    }
    if (this.oscillator) {
      try { this.oscillator.stop(); } catch { /* idempotent cleanup */ }
      try { this.oscillator.disconnect(); } catch { /* idempotent cleanup */ }
    }
    try { this.gain?.disconnect(); } catch { /* idempotent cleanup */ }
    this.oscillator = this.gain = null;
  }

  play() {
    if (!this.enabled || this.pending || !this.signal || this.context?.state !== 'running') return false;
    const {frequency, duty} = this.signal, context = this.context;
    const coefficients = pwmCoefficients(frequency, duty, context.sampleRate);
    if (!coefficients) {
      this.stopTone();
      this.message = frequency > 0 && duty > 0 && duty < 100 ? '超出浏览器采样范围 · 静音' : '已启用 · 当前无交流 PWM';
      this.notify();
      return true;
    }
    try {
      const wave = context.createPeriodicWave(coefficients.real, coefficients.imag, {disableNormalization: true});
      if (!this.oscillator) {
        this.oscillator = context.createOscillator();
        this.gain = context.createGain();
        this.gain.gain.setValueAtTime(0.12, context.currentTime);
        this.oscillator.connect(this.gain);
        this.gain.connect(context.destination);
        this.oscillator.setPeriodicWave(wave);
        this.oscillator.frequency.setValueAtTime(frequency, context.currentTime);
        this.oscillator.start();
      } else {
        this.oscillator.setPeriodicWave(wave);
        this.oscillator.frequency.setValueAtTime(frequency, context.currentTime);
      }
      this.message = `试听中 · ${frequency} Hz / ${duty}%`;
      this.notify();
      return true;
    } catch {
      this.mute('声音不可用 · 静音');
      return false;
    }
  }

  mute(message = '已静音') {
    this.epoch += 1;
    this.enabled = this.pending = false;
    this.activation = null;
    this.stopTone();
    const context = this.context;
    this.context = null;
    if (context) {
      try { context.removeEventListener('statechange', this.stateChanged); } catch { /* partial construction */ }
      try { Promise.resolve(context.close()).catch(() => {}); } catch { /* already closed */ }
    }
    this.message = message;
    this.notify();
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.signal = null;
    this.mute();
  }
}
