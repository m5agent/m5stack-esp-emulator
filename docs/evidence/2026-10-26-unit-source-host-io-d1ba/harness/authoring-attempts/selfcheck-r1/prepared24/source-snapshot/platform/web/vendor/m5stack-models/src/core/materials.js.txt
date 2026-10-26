// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import * as THREE from 'three';

/** Material presets tuned for small consumer-electronics enclosures. */
export const materials = {
  /** Matte injection-moulded plastic (the usual M5Stack case finish). */
  plastic(color, { roughness = 0.72, clearcoat = 0.08, ...rest } = {}) {
    return new THREE.MeshPhysicalMaterial({
      color, roughness, metalness: 0, clearcoat, clearcoatRoughness: 0.6, ...rest,
    });
  },
  /** Glossy plastic for keycaps / light pipes. */
  glossy(color, { roughness = 0.32, ...rest } = {}) {
    return new THREE.MeshPhysicalMaterial({
      color, roughness, metalness: 0, clearcoat: 0.5, clearcoatRoughness: 0.25, ...rest,
    });
  },
  metal(color = 0xc8c8cc, { roughness = 0.35, ...rest } = {}) {
    return new THREE.MeshStandardMaterial({ color, roughness, metalness: 1, ...rest });
  },
  /** Flat dark material for holes and cavities. */
  cavity(color = 0x050506) {
    return new THREE.MeshStandardMaterial({ color, roughness: 1, metalness: 0 });
  },
  /**
   * Reflection-only glass: adds reflections (environment + light highlights)
   * on top of whatever is below. `intensity` scales both.
   */
  coverGlass({ roughness = 0.06, intensity = 1 } = {}) {
    return new THREE.MeshPhysicalMaterial({
      color: 0x000000, roughness, metalness: 0, specularIntensity: intensity,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
  },
};
