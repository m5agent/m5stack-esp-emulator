// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import * as THREE from 'three';
import { EventEmitter } from './EventEmitter.js';
import { disposeObject } from './geometry.js';

/**
 * Base class for every interactive / simulated part of a device: buttons,
 * displays, LEDs, ports, sensors…
 *
 * A component owns an `object3d` (its local frame, positioned on the device
 * body), knows its `host` (the Device or Module it belongs to) and talks to the
 * outside world through two channels only:
 *
 *   - **input**   component → simulator   `this.input(action, payload)`
 *   - **commands** simulator → component  `handle(cmd)`
 *
 * Subclasses override the pointer hooks to become interactive. Any mesh that
 * should receive pointer events must be registered with `this.hit(mesh)`.
 */
export class Component extends EventEmitter {
  /** Short type name used in input events and `host.get(id, kind)`. */
  static kind = 'component';

  constructor({ id, label, position, rotation, quaternion, meta = {} } = {}) {
    super();
    if (!id) throw new Error(`${this.constructor.name}: "id" is required`);
    this.id = id;
    this.label = label ?? id;
    /** Free-form hardware metadata (gpio, part number…) surfaced in hover info. */
    this.meta = meta;
    this.host = null;
    this.object3d = new THREE.Group();
    this.object3d.name = `${this.constructor.kind}:${id}`;
    if (position) this.object3d.position.fromArray(position);
    if (quaternion) this.object3d.quaternion.copy(quaternion);
    else if (rotation) this.object3d.rotation.fromArray(rotation);
    this.hovered = false;
  }

  get kind() {
    return this.constructor.kind;
  }

  /** Fully-qualified address, e.g. `lcd` or `hat/matrix` for module parts. */
  get path() {
    const prefix = this.host?.pathPrefix ?? '';
    return prefix ? `${prefix}/${this.id}` : this.id;
  }

  /** Whether the pointer currently interacts with this component (vs. rotating the device). */
  get interactive() {
    return false;
  }

  /** Cursor shown on hover when interactive. */
  get cursor() {
    return 'pointer';
  }

  /** Register a mesh as a pointer target for this component. */
  hit(mesh) {
    mesh.userData.component = this;
    return mesh;
  }

  /** Called by the host when added. */
  mount(host, parent) {
    this.host = host;
    (parent ?? host.body).add(this.object3d);
    this.onMount?.();
  }

  unmount() {
    this.object3d.removeFromParent();
    this.host = null;
  }

  requestRender() {
    this.host?.requestRender();
  }

  /** Report an input event (button press, touch…) to the simulator. */
  input(action, payload = {}) {
    const evt = { kind: this.kind, id: this.path, action, time: performance.now(), ...payload };
    this.emit(action, evt);
    this.host?.dispatchInput(evt);
    return evt;
  }

  /** Execute a command addressed to this component. Return value is forwarded to the caller. */
  handle(cmd) {
    throw new Error(`${this.kind} "${this.path}" cannot handle command "${cmd.type}"`);
  }

  /**
   * Per-frame tick. Return `true` while an animation is running so the viewer
   * keeps rendering; the viewer otherwise renders on demand only.
   */
  update(/* dt, time */) {
    return false;
  }

  /** Serializable snapshot of the component state. */
  getState() {
    return {};
  }

  /** Information shown when hovering the component. */
  describe(/* intersection */) {
    return { kind: this.kind, path: this.path, label: this.label, meta: this.meta };
  }

  setHover(on) {
    if (this.hovered === on) return;
    this.hovered = on;
    this.onHover?.(on);
    this.requestRender();
  }

  // Pointer hooks (overridden by interactive components). `info` is
  // { pointerId, intersection|null, uv|null, localPoint|null, event }.
  onPointerDown(/* info */) {}
  onPointerMove(/* info */) {}
  onPointerUp(/* info */) {}
  onPointerCancel(info) {
    this.onPointerUp(info);
  }

  dispose() {
    this.unmount();
    disposeObject(this.object3d);
    this.removeAllListeners();
  }
}
