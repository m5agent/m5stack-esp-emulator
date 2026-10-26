// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import * as THREE from 'three';

/**
 * Geometry helpers. All units are millimetres; one scene unit == 1 mm.
 */

/** Rounded rectangle centred at (cx, cy). Usable as a Shape or as a hole Path. */
export function roundedRect(w, h, r, { cx = 0, cy = 0, path = new THREE.Shape(), clockwise = false } = {}) {
  r = Math.max(0.0001, Math.min(r, w / 2, h / 2));
  const x0 = cx - w / 2, x1 = cx + w / 2, y0 = cy - h / 2, y1 = cy + h / 2;
  if (!clockwise) {
    path.moveTo(x0 + r, y0);
    path.lineTo(x1 - r, y0);
    path.absarc(x1 - r, y0 + r, r, -Math.PI / 2, 0, false);
    path.lineTo(x1, y1 - r);
    path.absarc(x1 - r, y1 - r, r, 0, Math.PI / 2, false);
    path.lineTo(x0 + r, y1);
    path.absarc(x0 + r, y1 - r, r, Math.PI / 2, Math.PI, false);
    path.lineTo(x0, y0 + r);
    path.absarc(x0 + r, y0 + r, r, Math.PI, Math.PI * 1.5, false);
  } else {
    path.moveTo(x0 + r, y0);
    path.absarc(x0 + r, y0 + r, r, Math.PI * 1.5, Math.PI, true);
    path.lineTo(x0, y1 - r);
    path.absarc(x0 + r, y1 - r, r, Math.PI, Math.PI / 2, true);
    path.lineTo(x1 - r, y1);
    path.absarc(x1 - r, y1 - r, r, Math.PI / 2, 0, true);
    path.lineTo(x1, y0 + r);
    path.absarc(x1 - r, y0 + r, r, 0, -Math.PI / 2, true);
    path.lineTo(x0 + r, y0);
  }
  return path;
}

/** Stadium / pill shape (fully rounded short ends). */
export function capsule(w, h, opts = {}) {
  return roundedRect(w, h, Math.min(w, h) / 2, opts);
}

/**
 * Extrude a rounded slab along +Z with a soft bevel on both faces.
 * The *outer* footprint (including bevel) is exactly w × h, the total depth is
 * exactly `depth`, and the slab spans z ∈ [0, depth].
 *
 * `holes` is a list of { w, h, r, cx, cy } openings measured at the face; the
 * bevel rolls into them, so the opening narrows by `bevel` once inside.
 */
export function roundedSlab({ w, h, depth, radius, bevel = 0.8, bevelSegments = 4, curveSegments = 12, holes = [] }) {
  const b = Math.min(bevel, depth / 2 - 0.001);
  const shape = roundedRect(w - 2 * b, h - 2 * b, Math.max(0.01, radius - b));
  for (const hole of holes) {
    shape.holes.push(roundedRect(hole.w, hole.h, hole.r ?? Math.min(hole.w, hole.h) / 2, {
      cx: hole.cx ?? 0, cy: hole.cy ?? 0, path: new THREE.Path(), clockwise: true,
    }));
  }
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: depth - 2 * b,
    bevelEnabled: b > 0,
    bevelThickness: b,
    bevelSize: b,
    bevelSegments,
    curveSegments,
  });
  geo.translate(0, 0, b);
  geo.computeVertexNormals();
  return geo;
}

/** Pick a basis so the plane's local +X/+Y/+Z map to the given model axes. */
export function basisQuaternion(xAxis, yAxis, zAxis) {
  const m = new THREE.Matrix4().makeBasis(
    new THREE.Vector3(...xAxis), new THREE.Vector3(...yAxis), new THREE.Vector3(...zAxis));
  return new THREE.Quaternion().setFromRotationMatrix(m);
}

/**
 * Paint a texture with the 2D canvas API at a given physical size.
 * `draw(ctx, W, H, mm)` receives the canvas size in pixels and a mm→px scale.
 */
export function paintTexture(wMm, hMm, draw, { pxPerMm = 24, anisotropy = 8 } = {}) {
  const W = Math.round(wMm * pxPerMm), H = Math.round(hMm * pxPerMm);
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  draw(ctx, W, H, pxPerMm);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = anisotropy;
  return tex;
}

/** A decal: thin plane with a painted texture. Place it slightly off the surface. */
export function decal(wMm, hMm, draw, { transparent = true, roughness = 0.6, pxPerMm, ...matOpts } = {}) {
  const map = paintTexture(wMm, hMm, draw, { pxPerMm });
  const mat = new THREE.MeshStandardMaterial({
    map, transparent, roughness, metalness: 0,
    polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
    ...matOpts,
  });
  return new THREE.Mesh(new THREE.PlaneGeometry(wMm, hMm), mat);
}

/** Dispose every geometry/material/texture below `root`. */
export function disposeObject(root) {
  root.traverse((o) => {
    o.geometry?.dispose();
    const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
    for (const m of mats) {
      for (const v of Object.values(m)) if (v && v.isTexture) v.dispose();
      m.dispose();
    }
  });
}
