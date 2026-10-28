import * as THREE from 'three';
import {mesh} from '../../modeling/parts.js';
export {THREE,mesh};
export function outline(points){return new THREE.Shape(points.map(p=>new THREE.Vector2(...p)));}
export function hole(shape,x,y,r){const path=new THREE.Path();path.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(path);return shape;}
// Normalize all extracted contours before extruding; hole walls face empty air.
export function solid(shape,depth){const p=shape.extractPoints(24);if(!THREE.ShapeUtils.isClockWise(p.shape))p.shape.reverse();const s=new THREE.Shape(p.shape);for(const h of p.holes){if(THREE.ShapeUtils.isClockWise(h))h.reverse();s.holes.push(new THREE.Path(h));}return new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false});}
export function ring(ro,ri,depth){const shape=new THREE.Shape();shape.absarc(0,0,ro,0,Math.PI*2,false);hole(shape,0,0,ri);return solid(shape,depth);}
export function box(parent,size,position,material,name){return mesh(parent,new THREE.BoxGeometry(...size),material,position,name);}
export function cylinder(radius,depth){return new THREE.CylinderGeometry(radius,radius,depth,32).rotateX(Math.PI/2);}
