// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import * as THREE from 'three';
import { ComponentHost } from './ComponentHost.js';

/**
 * A top-level piece of hardware mounted in a `DeviceViewer`.
 *
 * Subclass it, describe it with `static meta`, and model it in `build()`:
 *
 *   class MyBoard extends Device {
 *     static meta = { id: 'acme.board', name: 'ACME Board', size: [30, 50, 12],
 *                     keymap: { Space: 'btnA' } };
 *     build() {
 *       this.body.add(myCaseMesh);
 *       this.add(new Display({ id: 'lcd', width: 240, height: 135, size: [26.4, 14.9], position: [0, 5, 6] }));
 *       this.add(new Button({ id: 'btnA', ... }));
 *     }
 *   }
 *
 * Simulator ↔ device traffic:
 *   device.on('input', evt => …)   // buttons, touch, port attach/detach
 *   device.handle({ type, target, … })  // display writes, LEDs, vibration…
 */
export class Device extends ComponentHost {
  static meta = { id: 'device', name: 'Device', size: [20, 40, 10], keymap: {} };

  #vibration = null;
  #rng = 1;

  constructor(options = {}) {
    super(options);
    this.viewer = null;
    /** Keyboard code → button path. Copied so instances can be customised. */
    this.keymap = { ...(this.constructor.meta.keymap ?? {}), ...(options.keymap ?? {}) };
  }

  /** World orientation of the device (what an IMU would see). */
  get orientation() {
    return this.root.getWorldQuaternion(new THREE.Quaternion());
  }

  /**
   * Haptic feedback. `pattern` is a duration in ms or a [on, off, on, …] list,
   * like `navigator.vibrate`. Visualised as a high-frequency shake of the body.
   */
  vibrate(pattern = 200, { intensity = 1, frequency = 170 } = {}) {
    const steps = Array.isArray(pattern) ? pattern : [pattern];
    if (!steps.length || steps.every((s) => !s)) return this.stopVibration();
    this.#vibration = { steps, intensity: Math.max(0, Math.min(1, intensity)), frequency, t: 0 };
    this.emit('vibrate', { pattern: steps, intensity });
    this.requestRender();
  }

  stopVibration() {
    this.#vibration = null;
    this.shaker.position.set(0, 0, 0);
    this.shaker.rotation.set(0, 0, 0);
    this.requestRender();
  }

  get vibrating() {
    return !!this.#vibration;
  }

  handle(cmd) {
    if (!Array.isArray(cmd) && cmd.type === 'vibrate' && cmd.target == null) {
      if (cmd.stop) return this.stopVibration();
      return this.vibrate(cmd.pattern ?? cmd.duration ?? 200, cmd);
    }
    return super.handle(cmd);
  }

  update(dt, time) {
    let animating = super.update(dt, time);
    if (this.#vibration && this.#tickVibration(dt)) animating = true;
    return animating;
  }

  #rand() {
    // xorshift: deterministic, allocation-free jitter
    let x = this.#rng;
    x ^= x << 13; x ^= x >>> 17; x ^= x << 5;
    this.#rng = x >>> 0 || 1;
    return (this.#rng / 0xffffffff) * 2 - 1;
  }

  #tickVibration(dt) {
    const v = this.#vibration;
    v.t += dt * 1000;
    let acc = 0, on = false, done = true;
    for (let i = 0; i < v.steps.length; i++) {
      acc += v.steps[i];
      if (v.t < acc) { on = i % 2 === 0; done = false; break; }
    }
    if (done) {
      this.stopVibration();
      return false;
    }
    const amp = on ? 0.28 * v.intensity : 0;
    // Eccentric-mass motor: rotation in the face plane + small translation jitter.
    const phase = (v.t / 1000) * v.frequency * Math.PI * 2;
    this.shaker.position.set(Math.sin(phase) * amp + this.#rand() * amp * 0.35,
      Math.cos(phase) * amp * 0.6 + this.#rand() * amp * 0.35, this.#rand() * amp * 0.2);
    this.shaker.rotation.set(0, 0, Math.sin(phase * 0.5) * amp * 0.012);
    return true;
  }
}
