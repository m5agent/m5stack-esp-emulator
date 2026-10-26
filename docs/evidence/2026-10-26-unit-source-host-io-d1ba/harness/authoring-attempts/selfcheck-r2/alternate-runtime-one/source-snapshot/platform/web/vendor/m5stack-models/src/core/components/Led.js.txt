// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import * as THREE from 'three';
import { Component } from '../Component.js';

let glowTexture = null;
function getGlowTexture() {
  if (glowTexture) return glowTexture;
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.25, 'rgba(255,255,255,0.45)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  glowTexture = new THREE.CanvasTexture(c);
  return glowTexture;
}

/**
 * Indicator LED (single colour or RGB). Pass the lens mesh or let it create a
 * small dome. `set({ on, color, brightness })` or `set('#ff0000')`.
 * `invisible: true` renders the light the way a phone camera sees an IR LED.
 */
export class Led extends Component {
  static kind = 'led';

  constructor({ mesh, color = 0xff2020, radius = 0.6, glowSize = 4, lensColor = 0xdddddd, ...rest }) {
    super(rest);
    this.color = new THREE.Color(color);
    this.brightness = 0;
    if (!mesh) {
      mesh = new THREE.Mesh(
        new THREE.SphereGeometry(radius, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2).rotateX(Math.PI / 2),
        new THREE.MeshPhysicalMaterial({ color: lensColor, roughness: 0.15, transmission: 0, clearcoat: 1 }),
      );
    }
    this.lens = this.hit(mesh);
    this.object3d.add(mesh);
    this.lensMaterial = mesh.material;
    this.lensMaterial.emissive ??= new THREE.Color();
    this.glow = new THREE.Sprite(new THREE.SpriteMaterial({
      map: getGlowTexture(), color: this.color, transparent: true, opacity: 0,
      blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false,
    }));
    this.glow.scale.setScalar(glowSize);
    this.glow.raycast = () => {};
    this.glow.position.z = radius * 0.5;
    this.glow.visible = false;
    this.object3d.add(this.glow);
  }

  /** `set(true|false)`, `set('#00ff00')`, `set({ on, color, brightness })` */
  set(state) {
    if (typeof state === 'boolean') state = { on: state };
    else if (typeof state === 'string' || typeof state === 'number') state = { color: state, on: true };
    if (state.color != null) this.color.set(state.color);
    if (state.brightness != null) this.brightness = Math.max(0, Math.min(1, state.brightness));
    else if (state.on != null) this.brightness = state.on ? 1 : 0;
    if (this.color.getHex() === 0) this.brightness = 0;
    this.#sync();
  }

  #sync() {
    const b = this.brightness;
    this.lensMaterial.emissive.copy(this.color).multiplyScalar(b * 2.2);
    this.glow.material.color.copy(this.color);
    this.glow.material.opacity = b * 0.85;
    this.glow.visible = b > 0;
    this.requestRender();
  }

  handle(cmd) {
    if (cmd.type !== 'led') return super.handle(cmd);
    this.set(cmd);
  }

  getState() {
    return { color: `#${this.color.getHexString()}`, brightness: this.brightness };
  }
}
