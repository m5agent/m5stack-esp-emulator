// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import * as THREE from 'three';
import { EventEmitter } from './EventEmitter.js';
import { disposeObject } from './geometry.js';

/**
 * Shared base of `Device` and `Module`: something with a 3D body and a set of
 * addressable components.
 *
 * Subclasses implement `build()`, which creates the enclosure meshes under
 * `this.body` and registers components with `this.add(component)`. `build()`
 * runs lazily on first access, so subclass fields are initialised by then.
 *
 * Scene graph:
 *   root      ← orientation (the viewer rotates this for devices)
 *    └ shaker ← vibration offsets
 *       └ body ← modelled geometry + components (+ attached modules via ports)
 */
export class ComponentHost extends EventEmitter {
  /** Override in subclasses: { id, name, vendor, ... } */
  static meta = { id: 'host', name: 'Host' };

  #built = false;
  #root = new THREE.Group();

  constructor(options = {}) {
    super();
    this.options = options;
    this.components = new Map();
    /** Parent host when this is a module plugged into a port. */
    this.parentHost = null;
    /** Port this host is plugged into (modules only). */
    this.attachedTo = null;
    this.shaker = new THREE.Group();
    this.body = new THREE.Group();
    this.#root.add(this.shaker);
    this.shaker.add(this.body);
    this.#root.name = this.constructor.meta.id;
  }

  get meta() {
    return this.constructor.meta;
  }

  /** Root Object3D; triggers the lazy build. */
  get root() {
    this.ensureBuilt();
    return this.#root;
  }

  ensureBuilt() {
    if (this.#built) return this;
    this.#built = true;
    this.build(this.options);
    return this;
  }

  /** Override: model the enclosure and register components. */
  build(/* options */) {}

  /** Prefix used to address this host's components from the top-level device. */
  get pathPrefix() {
    if (!this.parentHost) return '';
    const parent = this.parentHost.pathPrefix;
    return parent ? `${parent}/${this.attachedTo.id}` : this.attachedTo.id;
  }

  /** Register a component. `parent` defaults to `this.body`. */
  add(component, parent) {
    if (this.components.has(component.id)) throw new Error(`Duplicate component id "${component.id}"`);
    this.components.set(component.id, component);
    component.mount(this, parent);
    this.requestRender();
    return component;
  }

  remove(id) {
    const c = this.components.get(id);
    if (!c) return;
    this.components.delete(id);
    c.dispose();
    this.requestRender();
  }

  /**
   * Resolve a component by path. Paths walk through ports into attached
   * modules: `get('hat/matrix')` → the `matrix` component of the module
   * plugged into port `hat`. Optionally assert the component kind.
   */
  get(path, kind) {
    this.ensureBuilt();
    const [head, ...rest] = String(path).split('/');
    let c = this.components.get(head);
    if (c && rest.length) {
      const mod = c.module;
      if (!mod) throw new Error(`Nothing attached at "${head}" (resolving "${path}")`);
      return mod.get(rest.join('/'), kind);
    }
    if (!c) throw new Error(`No component "${path}" on ${this.meta.name}`);
    if (kind && c.kind !== kind) throw new Error(`Component "${path}" is a ${c.kind}, not a ${kind}`);
    return c;
  }

  /** Non-throwing lookup. */
  find(path, kind) {
    try { return this.get(path, kind); } catch { return null; }
  }

  // Typed accessors — sugar over get().
  display(id = 'lcd') { return this.get(id, 'display'); }
  button(id) { return this.get(id, 'button'); }
  port(id) { return this.get(id, 'port'); }
  led(id) { return this.get(id, 'led'); }
  speaker(id = 'speaker') { return this.get(id, 'speaker'); }
  imu(id = 'imu') { return this.get(id, 'imu'); }

  /** All components (optionally of a kind), including those of attached modules. */
  list(kind) {
    this.ensureBuilt();
    const out = [];
    for (const c of this.components.values()) {
      if (!kind || c.kind === kind) out.push(c);
      if (c.module) out.push(...c.module.list(kind));
    }
    return out;
  }

  /** Bubble an input event up to the top-level device. */
  dispatchInput(evt) {
    this.emit('input', evt);
    this.parentHost?.dispatchInput(evt);
  }

  requestRender() {
    if (this.parentHost) this.parentHost.requestRender();
    else this.viewer?.requestRender();
  }

  /**
   * Execute a command (or an array of commands). Commands addressed with
   * `target` are routed to that component's `handle()`.
   */
  handle(cmd) {
    if (Array.isArray(cmd)) return cmd.map((c) => this.handle(c));
    if (cmd.target != null) return this.get(cmd.target).handle(cmd);
    throw new Error(`Unhandled command "${cmd.type}" (missing "target"?)`);
  }

  /** Tick components and attached modules. Returns true while animating. */
  update(dt, time) {
    let animating = false;
    for (const c of this.components.values()) {
      if (c.update(dt, time)) animating = true;
      if (c.module?.update(dt, time)) animating = true;
    }
    return animating;
  }

  getState() {
    const state = {};
    for (const c of this.components.values()) {
      state[c.id] = c.getState();
      if (c.module) state[c.id].module = { id: c.module.meta.id, state: c.module.getState() };
    }
    return state;
  }

  dispose() {
    for (const c of [...this.components.values()]) c.dispose();
    this.components.clear();
    disposeObject(this.#root);
    this.#root.removeFromParent();
    this.removeAllListeners();
  }
}
