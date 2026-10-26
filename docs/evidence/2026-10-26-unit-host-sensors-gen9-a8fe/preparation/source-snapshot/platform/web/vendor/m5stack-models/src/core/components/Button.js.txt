// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import * as THREE from 'three';
import { Component } from '../Component.js';

/**
 * A momentary push button.
 *
 * Give it the cap mesh (modelled at rest, in the component's local frame) and
 * the travel direction. Presses can come from the pointer, the keyboard or the
 * simulator itself (`press()` / `release()` / `click()`); the button is down
 * while *any* source holds it.
 *
 * Input events: `down`, `up` ({ duration }), `click` ({ duration }), `longpress`.
 */
export class Button extends Component {
  static kind = 'button';

  constructor({ mesh, travel = 0.35, axis = [0, 0, -1], longPressMs = 800, latching = false, position = 0, ...rest }) {
    // `position` is the stable visual detent for latching controls. Keep the
    // existing component-placement option (an array) backwards compatible.
    const placement = Array.isArray(position) ? position : undefined;
    if (placement) rest.position = placement;
    super(rest);
    this.travel = travel;
    this.axis = new THREE.Vector3(...axis).normalize();
    this.longPressMs = longPressMs;
    this.pressed = false;
    this.latching = !!latching;
    this.position = this.latching && !placement && Number(position) >= .5 ? 1 : 0;
    this.cap = new THREE.Group();
    this.object3d.add(this.cap);
    this.#depth = this.position * travel;
    this.#sources = new Set();
    if (mesh) this.setMesh(mesh);
    this.cap.position.copy(this.axis).multiplyScalar(this.#depth);
  }

  #depth;
  #sources;
  #downAt = 0;
  #longTimer = null;
  #materials = [];
  #clickTimers = new Set();
  #clickSequence = 0;
  #cancelled = false;

  get isLatching() { return this.latching; }

  setMesh(mesh) {
    this.cap.clear();
    this.cap.add(mesh);
    this.#materials = [];
    mesh.traverse((o) => {
      if (!o.isMesh) return;
      this.hit(o);
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of mats) if (m.emissive) this.#materials.push({ m, base: m.emissive.clone(), color: m.color.clone() });
    });
  }

  get interactive() {
    return true;
  }

  /** Begin a press from `source` (pointer id, key code, 'sim', …). */
  press(source = 'sim') {
    this.#sources.add(source);
    if (this.pressed) return;
    this.pressed = true;
    this.#cancelled = false;
    if (this.latching) this.position = 1 - this.position;
    this.#downAt = performance.now();
    clearTimeout(this.#longTimer);
    if (this.longPressMs > 0) {
      this.#longTimer = setTimeout(() => this.pressed && this.input('longpress', { source }), this.longPressMs);
    }
    this.input('down', { source });
    this.requestRender();
  }

  /** End the press from `source`. The button rises once no source holds it. */
  release(source = 'sim', { cancelled = false } = {}) {
    if (cancelled && this.#sources.has(source)) this.#cancelled = true;
    this.#sources.delete(source);
    if (!this.pressed || this.#sources.size) return;
    this.pressed = false;
    clearTimeout(this.#longTimer);
    const duration = performance.now() - this.#downAt;
    this.input('up', { source, duration, ...(this.#cancelled ? { cancelled: true } : {}) });
    if (!this.#cancelled && (duration < this.longPressMs || this.longPressMs <= 0)) this.input('click', { source, duration });
    this.requestRender();
  }

  cancel(source = 'sim') { return this.release(source, { cancelled: true }); }

  /** Programmatic tap. */
  click(ms = 90) {
    const source = `click:${++this.#clickSequence}`;
    this.press(source);
    const timer = setTimeout(() => { this.#clickTimers.delete(timer); this.release(source); }, ms);
    this.#clickTimers.add(timer);
  }

  /** Set a latching control's visual detent without changing device power. */
  setPosition(position, { immediate = false } = {}) {
    if (!this.latching) throw new Error(`Button "${this.id}" is not a latching actuator`);
    if (position !== 0 && position !== 1) throw new RangeError('Actuator position must be 0 or 1');
    this.position = position;
    if (immediate) { this.#depth = position * this.travel; this.cap.position.copy(this.axis).multiplyScalar(this.#depth); }
    this.requestRender();
    return this.getState();
  }

  onPointerDown({ pointerId }) {
    this.press(`pointer:${pointerId}`);
  }

  onPointerUp({ pointerId }) {
    this.release(`pointer:${pointerId}`);
  }

  onPointerCancel({ pointerId }) { this.cancel(`pointer:${pointerId}`); }

  onHover(on) {
    for (const { m, base, color } of this.#materials) {
      if (on) m.emissive.copy(color).multiplyScalar(0.18).add(base);
      else m.emissive.copy(base);
    }
  }

  handle(cmd) {
    const action = cmd.action ?? cmd.type;
    if (action === 'press') return this.press(cmd.source ?? 'sim');
    if (action === 'release') return this.release(cmd.source ?? 'sim');
    if (action === 'cancel') return this.cancel(cmd.source ?? 'sim');
    if (action === 'click') return this.click(cmd.ms);
    if (action === 'position' || action === 'setPosition') return this.setPosition(cmd.position ?? cmd.value, cmd);
    if (action === 'state') return this.getState();
    return super.handle(cmd);
  }

  update(dt) {
    const previousDepth = this.#depth;
    const target = this.latching ? this.position * this.travel : this.pressed ? this.travel : 0;
    const k = 1 - Math.exp(-dt * 40);
    this.#depth += (target - this.#depth) * k;
    if (Math.abs(target - this.#depth) < 1e-3) this.#depth = target;
    this.cap.position.copy(this.axis).multiplyScalar(this.#depth);
    // Render the frame which reaches the exact endpoint as well. The following
    // unchanged tick returns false, allowing an on-demand viewer to go idle.
    return this.#depth !== previousDepth;
  }

  getState() {
    return this.latching ? { pressed: this.pressed, position: this.position, latching: true } : { pressed: this.pressed };
  }

  /** Visual travel shared by linear, flexing and lever-shaped actuators. */
  getActuationState() {
    const targetDepthMm = this.latching ? this.position * this.travel : this.pressed ? this.travel : 0;
    return { depthMm: this.#depth, targetDepthMm, settled: this.#depth === targetDepthMm };
  }

  dispose() {
    clearTimeout(this.#longTimer);
    for (const timer of this.#clickTimers) clearTimeout(timer);
    this.#clickTimers.clear();
    super.dispose();
  }
}
