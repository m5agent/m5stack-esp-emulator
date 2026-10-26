// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import * as THREE from 'three';
import { Component } from '../Component.js';
import { createModule } from '../registry.js';

// Synchronous callbacks must not reattach a module while it is transferring or
// between unlink and disposal. A transferring attach owns this lock through its
// internal detach; independent detaches retain it until all notifications end.
const moduleTransactions = new WeakSet();

/**
 * An expansion connector that accepts pluggable `Module`s.
 *
 * The component's local frame *is* the mating frame handed to modules:
 * origin at the connector face, +Y pointing out of the host, +Z towards the
 * host's front. `connector` names the standard (`m5.hat2`, `grove`, …).
 *
 * `pins` documents the pinout; with `pinGrid` ({ cols, rows, pitch, center:[x,z], order(col,row)→n })
 * hovering the connector reports which pin is under the cursor.
 *
 * Input events: `attach` / `detach` ({ module: meta.id }).
 */
export class Port extends Component {
  static kind = 'port';

  #attaching = false;
  #detaching = false;

  constructor({ connector, pins = [], pinGrid = null, hitSize = [10, 2, 6], hitOffset = [0, 0, 0], ...rest }) {
    super(rest);
    if (!connector) throw new Error('Port needs a "connector" type');
    this.connector = connector;
    this.pins = pins;
    this.pinGrid = pinGrid;
    this.module = null;
    // Hover / highlight volume around the connector. Kept rendered at
    // opacity 0 (not `visible=false`) so it stays raycastable.
    this.highlightMesh = this.hit(new THREE.Mesh(
      new THREE.BoxGeometry(...hitSize),
      new THREE.MeshBasicMaterial({ color: 0x3aa0ff, transparent: true, opacity: 0, depthWrite: false, toneMapped: false }),
    ));
    this.highlightMesh.position.fromArray(hitOffset);
    this.highlightMesh.renderOrder = 4;
    this.object3d.add(this.highlightMesh);
    this.highlighted = false;
  }

  /** Whether `module` (instance or class) can be plugged in here. */
  accepts(module) {
    const meta = module.meta ?? module.constructor?.meta ?? module;
    const c = meta.connector;
    return Array.isArray(c) ? c.includes(this.connector) : c === this.connector;
  }

  /**
   * Plug a module in. Accepts a Module instance, a Module class, or a
   * registered module id (with `options`). Replaces any existing module.
   * An attached instance is transferred without disposal; attaching it to the
   * same port is a no-op. Validate before changing either existing assembly.
   */
  attach(module, options = {}) {
    if (this.#detaching) throw new Error(`Cannot attach while port "${this.path}" is detaching`);
    if (this.#attaching) throw new Error(`Cannot attach while port "${this.path}" is attaching`);
    if (typeof module === 'string') module = createModule(module, options);
    else if (typeof module === 'function') module = new module(options);
    if (moduleTransactions.has(module)) throw new Error('Cannot reattach a module during its attachment or detaching transaction');
    const root = this.#validateAttachment(module);
    if (this.module === module && module.attachedTo === this) return module;
    this.#attaching = true;
    moduleTransactions.add(module);
    try {
      if (module.attachedTo) module.attachedTo.detach({ dispose: false });
      // A synchronous detach consumer can move this port's host or ancestors.
      // Recheck after each callback phase, before replacing anything or adding.
      this.#validateAttachment(module, root);
      if (module.attachedTo) throw new Error('A transferring module must have no attachment owner');
      if (this.module) this.detach();
      this.#validateAttachment(module, root);
      if (module.attachedTo) throw new Error('A transferring module must have no attachment owner');
      module.parentHost = this.host;
      module.attachedTo = this;
      this.module = module;
      this.object3d.add(root);
      // Picking a module's plain geometry resolves to this port (hover info,
      // click-to-unplug); the module's own components are found first.
      root.userData.component = this;
      this.highlightMesh.visible = false;
      module.onAttach(this);
      this.input('attach', { module: module.meta.id, name: module.meta.name });
      this.host?.emit('module:attach', { port: this, module });
      this.requestRender();
      return module;
    } finally {
      moduleTransactions.delete(module);
      this.#attaching = false;
    }
  }

  #validateAttachment(module, root) {
    if (!this.accepts(module)) {
      throw new Error(`${module.meta.name} (${module.meta.connector}) does not fit port "${this.path}" (${this.connector})`);
    }
    for (let host = this.host; host; host = host.parentHost) {
      if (host === module) throw new Error('A module cannot be attached to itself or one of its descendants');
    }
    root ??= module.root;
    for (let object = this.object3d; object; object = object.parent) {
      if (object === root) throw new Error('A module cannot contain its own attachment port');
    }
    if (module.attachedTo?.#detaching) throw new Error('Cannot transfer a module while its port is detaching');
    return root;
  }

  /** Unplug and dispose the current module (pass `{ dispose: false }` to keep it). */
  detach({ dispose = true } = {}) {
    const module = this.module;
    if (!module) return null;
    if (this.#detaching) return module;
    this.#detaching = true;
    const ownsTransaction = !moduleTransactions.has(module);
    if (ownsTransaction) moduleTransactions.add(module);
    try {
      // A viewer must cancel captured input while both its old address and
      // scene ancestry are intact. This lifecycle event is not input intent.
      const hosts = [];
      for (let host = this.host; host; host = host.parentHost) hosts.push(host);
      for (const host of hosts) host.emit('module:will-detach', { port: this, module });
      module.onDetach(this);
      module.root.removeFromParent();
      delete module.root.userData.component;
      module.parentHost = null;
      module.attachedTo = null;
      this.module = null;
      this.highlightMesh.visible = true;
      this.input('detach', { module: module.meta.id });
      this.host?.emit('module:detach', { port: this, module });
      if (dispose) module.dispose();
      this.requestRender();
      return module;
    } finally {
      if (ownsTransaction) moduleTransactions.delete(module);
      this.#detaching = false;
    }
  }

  setHighlight(on) {
    this.highlighted = on;
    this.highlightMesh.material.opacity = on ? 0.28 : 0;
    this.requestRender();
  }

  onHover(on) {
    if (!this.module) this.highlightMesh.material.opacity = on || this.highlighted ? 0.28 : 0;
  }

  /** Pin under a point given in the port's local frame (requires `pinGrid`). */
  pinAt(localPoint) {
    const g = this.pinGrid;
    if (!g || !localPoint) return null;
    const [cx, cz] = g.center ?? [0, 0];
    const col = Math.round((localPoint.x - cx) / g.pitch + (g.cols - 1) / 2);
    const row = Math.round((localPoint.z - cz) / g.pitch + (g.rows - 1) / 2);
    if (col < 0 || col >= g.cols || row < 0 || row >= g.rows) return null;
    const n = g.order(col, row);
    return this.pins.find((p) => p.n === n) ?? null;
  }

  describe(intersection) {
    const d = super.describe();
    d.connector = this.connector;
    d.module = this.module ? this.module.meta.name : null;
    if (intersection) {
      const local = this.object3d.worldToLocal(intersection.point.clone());
      d.pin = this.pinAt(local);
    }
    return d;
  }

  /** { type:'attach', target:'hat', module:'id', options } / { type:'detach', target:'hat' } */
  handle(cmd) {
    if (cmd.type === 'attach') return this.attach(cmd.module, cmd.options).meta.id;
    if (cmd.type === 'detach') return this.detach()?.meta.id ?? null;
    return super.handle(cmd);
  }

  getState() {
    return { connector: this.connector, module: this.module?.meta.id ?? null };
  }

  dispose() {
    this.detach();
    super.dispose();
  }
}
