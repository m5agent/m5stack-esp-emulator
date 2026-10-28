import * as THREE from 'three';
import {roundedRect} from '../../core/geometry.js';
import {mesh} from '../../modeling/parts.js';
export {THREE,roundedRect,mesh};
export function circleHole(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(p);return s;}
// Normalize both contours independently;hole winding must remain correct even
// when a concave shell/PCB outer path is already clockwise.
export function extrude(s,depth){const p=s.extractPoints(32),v=p.shape;if(!THREE.ShapeUtils.isClockWise(v))v.reverse();const shape=new THREE.Shape(v);for(const h of p.holes){if(THREE.ShapeUtils.isClockWise(h))h.reverse();shape.holes.push(new THREE.Path(h));}return new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false});}
export function annulus(ro,ri,depth){const s=new THREE.Shape();s.absarc(0,0,ro,0,Math.PI*2,false);circleHole(s,0,0,ri);return extrude(s,depth);}
export function box(parent,size,pos,mat,name){return mesh(parent,new THREE.BoxGeometry(...size),mat,pos,name);}
export function plate(parent,w,h,r,depth,pos,mat,name){return mesh(parent,extrude(roundedRect(w,h,r),depth),mat,pos,name);}
