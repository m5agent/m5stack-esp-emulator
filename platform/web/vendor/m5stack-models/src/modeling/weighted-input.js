import * as THREE from 'three';

// Dimensionless native deformation weight. Keep the fixed root and numerical
// barycentric edge noise passive while accepting the actual moving triangle.
const WEIGHT_EPSILON=1e-6;
const BARYCENTRIC_EPSILON=1e-6;

/** Resolve input on the current, unpartitioned native surface without editing it. */
export function weightedInputHit(component,mesh,intersection){
 // A projected child ink mesh has its own face indices. Never interpret those
 // indices using the parent's native positions/weights.
 if(intersection?.object!==mesh||!intersection.point?.isVector3)return false;
 const position=mesh?.geometry?.attributes.position,weights=component?.weights,face=intersection.face;
 if(!position||!weights||weights.length!==position.count||!face)return false;
 const indices=[face.a,face.b,face.c];
 if(!indices.every(index=>Number.isInteger(index)&&index>=0&&index<position.count))return false;
 if(!Number.isInteger(intersection.faceIndex)||intersection.faceIndex<0)return false;
 const offset=intersection.faceIndex*3,index=mesh.geometry.index;
 if(offset+2>=(index?.count??position.count))return false;
 if(indices.some((vertex,i)=>vertex!==(index?index.getX(offset+i):offset+i)))return false;
 const local=mesh.worldToLocal(intersection.point.clone());
 const triangle=indices.map(vertex=>new THREE.Vector3().fromBufferAttribute(position,vertex));
 const barycentric=THREE.Triangle.getBarycoord(local,...triangle,new THREE.Vector3());
 if(!barycentric||!barycentric.toArray().every(value=>Number.isFinite(value)&&value>=-BARYCENTRIC_EPSILON&&value<=1+BARYCENTRIC_EPSILON))return false;
 const weight=indices.reduce((sum,vertex,i)=>sum+weights[vertex]*barycentric.getComponent(i),0);
 return Number.isFinite(weight)&&weight>WEIGHT_EPSILON;
}
