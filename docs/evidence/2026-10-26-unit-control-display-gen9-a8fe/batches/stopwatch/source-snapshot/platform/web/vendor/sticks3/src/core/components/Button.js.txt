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

  constructor({ mesh, travel = 0.35, axis = [0, 0, -1], longPressMs = 800, ...rest }) {
    super(rest);
    this.travel = travel;
    this.axis = new THREE.Vector3(...axis).normalize();
    this.longPressMs = longPressMs;
    this.pressed = false;
    this.cap = new THREE.Group();
    this.object3d.add(this.cap);
    this.#depth = 0;
    this.#sources = new Set();
    if (mesh) this.setMesh(mesh);
  }

  #depth;
  #sources;
  #downAt = 0;
  #longTimer = null;
  #materials = [];

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
    this.#downAt = performance.now();
    clearTimeout(this.#longTimer);
    if (this.longPressMs > 0) {
      this.#longTimer = setTimeout(() => this.pressed && this.input('longpress', { source }), this.longPressMs);
    }
    this.input('down', { source });
    this.requestRender();
  }

  /** End the press from `source`. The button rises once no source holds it. */
  release(source = 'sim') {
    this.#sources.delete(source);
    if (!this.pressed || this.#sources.size) return;
    this.pressed = false;
    clearTimeout(this.#longTimer);
    const duration = performance.now() - this.#downAt;
    this.input('up', { source, duration });
    if (duration < this.longPressMs || this.longPressMs <= 0) this.input('click', { source, duration });
    this.requestRender();
  }

  /** Programmatic tap. */
  click(ms = 90) {
    this.press('sim');
    setTimeout(() => this.release('sim'), ms);
  }

  onPointerDown({ pointerId }) {
    this.press(`pointer:${pointerId}`);
  }

  onPointerUp({ pointerId }) {
    this.release(`pointer:${pointerId}`);
  }

  onHover(on) {
    for (const { m, base, color } of this.#materials) {
      if (on) m.emissive.copy(color).multiplyScalar(0.18).add(base);
      else m.emissive.copy(base);
    }
  }

  handle(cmd) {
    const action = cmd.action ?? cmd.type;
    if (action === 'press') return this.press('sim');
    if (action === 'release') return this.release('sim');
    if (action === 'click') return this.click(cmd.ms);
    if (action === 'state') return this.getState();
    return super.handle(cmd);
  }

  update(dt) {
    const target = this.pressed ? this.travel : 0;
    const k = 1 - Math.exp(-dt * 40);
    this.#depth += (target - this.#depth) * k;
    if (Math.abs(target - this.#depth) < 1e-3) this.#depth = target;
    this.cap.position.copy(this.axis).multiplyScalar(this.#depth);
    return this.#depth !== target;
  }

  getState() {
    return { pressed: this.pressed };
  }

  dispose() {
    clearTimeout(this.#longTimer);
    super.dispose();
  }
}
