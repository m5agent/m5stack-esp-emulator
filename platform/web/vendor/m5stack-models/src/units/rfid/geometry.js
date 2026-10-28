import * as THREE from 'three';
import {roundedRect} from '../../core/geometry.js';
import {mesh} from '../../modeling/parts.js';
export {THREE,roundedRect,mesh};
export function hole(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(p);return s;}
// Keep outer and hole directions explicit so FrontSide bore walls face air.
export function solid(s,depth){const p=s.extractPoints(32);if(!THREE.ShapeUtils.isClockWise(p.shape))p.shape.reverse();const shape=new THREE.Shape(p.shape);for(const h of p.holes){if(THREE.ShapeUtils.isClockWise(h))h.reverse();shape.holes.push(new THREE.Path(h));}return new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false});}
export function ring(ro,ri,depth){const s=new THREE.Shape();s.absarc(0,0,ro,0,Math.PI*2,false);hole(s,0,0,ri);return solid(s,depth);}
export function box(parent,size,p,mat,name){return mesh(parent,new THREE.BoxGeometry(...size),mat,p,name);}
export function cylinder(r,depth){return new THREE.CylinderGeometry(r,r,depth,32).rotateX(Math.PI/2);}
