import * as THREE from 'three';
import {Button, materials} from '../../core/index.js';
import {FACE} from '../../modeling/parts.js';
import {weightedInputHit} from '../../modeling/weighted-input.js';
import {cadTranslation, keys} from './dimensions.js';
import * as data from './geometry-data.js';

function decode(value, Type) {
  return new Type(Uint8Array.from(atob(value), byte => byte.charCodeAt(0)).buffer);
}

function nativeRegions() {
  const positions = decode(data.position, Float32Array);
  const normals = decode(data.normal, Float32Array);
  const faces = decode(data.faces, Uint16Array);
  const regions = [null, ...keys].map(() => ({
    position: [], normal: [], weight: [], slope: [], index: [], sourceFaces: [], vertices: new Map(),
  }));
  const weights = [];
  const slopes = [];
  const owners = new Uint8Array(positions.length / 3);
  for (let i = 0; i < owners.length; i++) {
    const point = cadTranslation.map((translation, axis) => translation + positions[3 * i + axis]);
    const control = keys.findIndex(key => key.nativeRegion(point)
      && (point[key.tangent] - key.hinge) / (key.tip - key.hinge) > 0);
    owners[i] = control + 1;
    if (control < 0) continue;
    const {hinge, tip, tangent} = keys[control];
    const t = (point[tangent] - hinge) / (tip - hinge);
    weights[i] = Math.min(1, t);
    slopes[i] = t < 1 ? 1 / (tip - hinge) : 0;
  }
  // Partition facets only, at the zero-travel boundary. No native face is
  // duplicated or cut. All facets sharing an active vertex move together.
  for (let f = 0; f < faces.length; f += 4) {
    const [a, b, c, normal] = faces.subarray(f, f + 4);
    const owner = owners[a] || owners[b] || owners[c];
    const region = regions[owner];
    region.sourceFaces.push(f / 4);
    for (const v of [a, b, c]) {
      if (owners[v] && owners[v] !== owner) throw new Error('CoreMatrix flex regions overlap');
      const tuple = normal * owners.length + v;
      if (!region.vertices.has(tuple)) {
        region.vertices.set(tuple, region.weight.length);
        region.position.push(...positions.subarray(3 * v, 3 * v + 3));
        region.normal.push(...normals.subarray(3 * normal, 3 * normal + 3));
        region.weight.push(weights[v] ?? 0);
        region.slope.push(slopes[v] ?? 0);
      }
      region.index.push(region.vertices.get(tuple));
    }
  }
  return regions;
}

let regions;

function partMesh(host, region, name) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(region.position, 3));
  geometry.setAttribute('normal', new THREE.Float32BufferAttribute(region.normal, 3));
  geometry.setIndex(new THREE.Uint16BufferAttribute(region.index, 1));
  geometry.userData.sourceFaces = region.sourceFaces;
  geometry.userData.sourceAttributeWord = 0;
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  const part = new THREE.Mesh(geometry, materials.plastic(0x27292a, {roughness: .73}));
  part.position.fromArray(cadTranslation);
  part.name = name;
  part.userData.source = 'official-structure';
  host.body.add(part);
  return part;
}

class NativeKey extends Button {
  constructor(mesh, key, region) {
    super({
      id: key.id, label: key.label, position: key.position, quaternion: FACE[key.face],
      travel: .27, longPressMs: key.id === 'power' ? 800 : 0,
      meta: {
        role: 'visual-control', ...key.controller, actuation: 'native-flexure',
        surfaceFace: key.face, surfaceCenter: key.position,
        travelSource: 'Estimated from the native U-slot and side reference',
      },
    });
    this.mesh = mesh;
    this.key = key;
    this.region = region;
    this.weights = region.weight;
    this.hit(mesh, intersection => {
      if (!weightedInputHit(this, mesh, intersection)) return false;
      const local = mesh.worldToLocal(intersection.point.clone());
      const point = cadTranslation.map((shift, i) => shift + local.getComponent(i));
      return key.nativeRegion(point) && (point[key.tangent] - key.hinge) / (key.tip - key.hinge) > 0;
    });
  }

  update(dt) {
    if (!super.update(dt)) return false;
    const depth = this.getActuationState().depthMm;
    const {inward, tangent} = this.key;
    const {position, normal} = this.mesh.geometry.attributes;
    const {position: rest, normal: restNormals, slope} = this.region;
    const n = new THREE.Vector3();
    for (let i = 0; i < this.weights.length; i++) {
      const travel = depth * this.weights[i];
      if (!this.weights[i]) continue;
      const p = i * 3;
      position.setXYZ(i, rest[p] + inward[0] * travel, rest[p + 1] + inward[1] * travel, rest[p + 2]);
      n.fromArray(restNormals, p);
      if (travel) {
        const projection = n.x * inward[0] + n.y * inward[1];
        n.setComponent(tangent, n.getComponent(tangent) - depth * slope[i] * projection).normalize();
      }
      normal.setXYZ(i, n.x, n.y, n.z);
    }
    position.needsUpdate = true;
    normal.needsUpdate = true;
    this.mesh.geometry.computeBoundingBox();
    this.mesh.geometry.computeBoundingSphere();
    return true;
  }
}

export function addNativeHousing(host) {
  regions ??= nativeRegions();
  const shell = partMesh(host, regions[0], 'CoreMatrix native chassis');
  const buttons = keys.map((key, i) => {
    const region = regions[i + 1];
    const mesh = partMesh(host, region, 'CoreMatrix native ' + key.id + ' flexure');
    return host.add(new NativeKey(mesh, key, region));
  });
  return {shell, buttons};
}
