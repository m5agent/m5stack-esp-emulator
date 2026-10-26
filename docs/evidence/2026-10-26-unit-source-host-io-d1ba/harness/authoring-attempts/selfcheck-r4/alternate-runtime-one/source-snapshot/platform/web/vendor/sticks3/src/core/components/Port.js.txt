import * as THREE from 'three';
import { Component } from '../Component.js';
import { createModule } from '../registry.js';

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
   */
  attach(module, options = {}) {
    if (typeof module === 'string') module = createModule(module, options);
    else if (typeof module === 'function') module = new module(options);
    if (!this.accepts(module)) {
      throw new Error(`${module.meta.name} (${module.meta.connector}) does not fit port "${this.path}" (${this.connector})`);
    }
    if (this.module) this.detach();
    module.parentHost = this.host;
    module.attachedTo = this;
    this.module = module;
    this.object3d.add(module.root);
    // Picking a module's plain geometry resolves to this port (hover info,
    // click-to-unplug); the module's own components are found first.
    module.root.userData.component = this;
    this.highlightMesh.visible = false;
    module.onAttach(this);
    this.input('attach', { module: module.meta.id, name: module.meta.name });
    this.host?.emit('module:attach', { port: this, module });
    this.requestRender();
    return module;
  }

  /** Unplug and dispose the current module (pass `{ dispose: false }` to keep it). */
  detach({ dispose = true } = {}) {
    const module = this.module;
    if (!module) return null;
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
