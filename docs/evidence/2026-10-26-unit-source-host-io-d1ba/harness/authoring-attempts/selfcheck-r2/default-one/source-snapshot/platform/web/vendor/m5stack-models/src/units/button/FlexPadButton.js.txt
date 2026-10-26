import {Button} from '../../core/components/Button.js';

/**
 * An integral plastic tab: the molded hinge remains fixed while its free edge
 * bends inwards. This is a normalized visual profile, not material physics.
 */
export class FlexPadButton extends Button {
  constructor({mesh, hingeY, freeY, ...options}) {
    if (!Number.isFinite(hingeY) || !Number.isFinite(freeY) || freeY <= hingeY) throw new RangeError('Flex pad needs an ordered local hinge and free edge');
    super({mesh, ...options});
    this.hingeY = hingeY;
    this.freeY = freeY;
    this.bindMesh(mesh);
    this.lastDepth = 0;
  }

  setMesh(mesh) {
    super.setMesh(mesh);
    // Button's constructor invokes this before product-local dimensions exist.
    if (!Number.isFinite(this.hingeY) || !Number.isFinite(this.freeY)) return;
    this.bindMesh(mesh);
    this.lastDepth = NaN;
    this.requestRender();
  }

  bindMesh(mesh) {
    this.bindings = [];
    mesh.traverse(object => {
      if (!object.isMesh) return;
      const attribute = object.geometry.attributes.position;
      const rest = attribute.array.slice();
      const normal = object.geometry.attributes.normal;
      const restNormals = normal.array.slice();
      const slopes = [];
      const weights = Array.from({length: attribute.count}, (_, i) => {
        const fraction = (attribute.getY(i) - this.hingeY) / (this.freeY - this.hingeY);
        const t = Math.max(0, Math.min(1, fraction));
        slopes.push(fraction>0&&fraction<1?(3 * t - 1.5 * t * t) / (this.freeY - this.hingeY):0);
        return t * t * (3 - t) / 2;
      });
      this.bindings.push({geometry: object.geometry, attribute, rest, normal, restNormals, weights, slopes});
    });
  }

  update(dt) {
    const changed = super.update(dt);
    const {depthMm} = this.getActuationState();
    if (depthMm === this.lastDepth) return changed;
    for (const {geometry, attribute, rest, normal, restNormals, weights, slopes} of this.bindings) {
      for (let i = 0; i < attribute.count; i++) {
        // Cancel the cap Group's full translation at the fixed hinge; retain
        // all of it at the free edge, and smoothly vary between the two.
        const correction = depthMm * (weights[i] - 1);
        attribute.setXYZ(i, rest[i * 3] + this.axis.x * correction, rest[i * 3 + 1] + this.axis.y * correction, rest[i * 3 + 2] + this.axis.z * correction);
        // Inverse-transpose of I + axis * depth * slope * eY^T keeps the
        // original smooth CAD normals while bending. Restore them bit-exactly
        // at rest; recomputing non-indexed normals would harden every triangle.
        const nx=restNormals[i*3],ny=restNormals[i*3+1],nz=restNormals[i*3+2];
        const derivative=depthMm*slopes[i],dot=this.axis.x*nx+this.axis.y*ny+this.axis.z*nz;
        const transformedY=ny-derivative*dot/(1+derivative*this.axis.y),length=Math.hypot(nx,transformedY,nz);
        if(depthMm===0)normal.setXYZ(i,nx,ny,nz);
        else normal.setXYZ(i,nx/length,transformedY/length,nz/length);
      }
      attribute.needsUpdate = true;
      normal.needsUpdate = true;
      geometry.computeBoundingBox();
      geometry.computeBoundingSphere();
    }
    this.lastDepth = depthMm;
    return true;
  }

  dispose() {
    super.dispose();
    this.bindings = [];
  }
}
