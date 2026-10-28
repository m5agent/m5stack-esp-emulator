import * as THREE from 'three';
import {mesh,slab,FACE,portQuaternion} from '../../modeling/parts.js';
import {materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
const tau=Math.PI*2;
export {THREE,mesh,slab,FACE,portQuaternion,materials,roundedRect};
export function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:32}),material,position,name);}
export function hole(shape,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,tau,false);shape.holes.push(p);}
export function annulus(outer,inner,depth){const s=new THREE.Shape();s.absarc(0,0,outer,0,tau,false);hole(s,0,0,inner);return new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:40});}
export function ringY(parent,outer,inner,depth,y,material,name){const g=annulus(outer,inner,depth);g.rotateX(-Math.PI/2);return mesh(parent,g,material,[0,y,0],name);}
/** Closed material sweep. Caps use original Float32 ring coordinates and directed end normals. */
export function cappedSweep(curve,radius,segments=64,radial=10){const tube=new THREE.TubeGeometry(curve,segments,radius,radial,false),base=tube.toNonIndexed(),positions=[...base.attributes.position.array],normals=[...base.attributes.normal.array],p=tube.attributes.position;
 for(const[end,normal]of[[0,curve.getTangent(0).negate()],[segments,curve.getTangent(1)]]){const center=curve.getPoint(end/segments);for(let j=0;j<radial;j++){let a=new THREE.Vector3().fromBufferAttribute(p,end*(radial+1)+j),b=new THREE.Vector3().fromBufferAttribute(p,end*(radial+1)+j+1);if(a.clone().sub(center).cross(b.clone().sub(center)).dot(normal)<0)[a,b]=[b,a];for(const v of[center,a,b]){positions.push(...v);normals.push(...normal);}}}tube.dispose();base.dispose();const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));g.setAttribute('normal',new THREE.Float32BufferAttribute(normals,3));return g;}
export function closedDome(radius){const shell=new THREE.SphereGeometry(radius,40,20,0,tau,0,Math.PI/2).toNonIndexed(),floor=new THREE.CircleGeometry(radius,40).rotateX(Math.PI/2).toNonIndexed(),g=new THREE.BufferGeometry();for(const name of['position','normal'])g.setAttribute(name,new THREE.Float32BufferAttribute([...shell.attributes[name].array,...floor.attributes[name].array],3));shell.dispose();floor.dispose();return g;}
