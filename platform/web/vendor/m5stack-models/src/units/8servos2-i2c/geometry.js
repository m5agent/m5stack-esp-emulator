import * as THREE from 'three';
import {mesh,slab,FACE,portQuaternion} from '../../modeling/parts.js';
import {materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
export {THREE,mesh,slab,FACE,portQuaternion,materials,roundedRect};
export function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:32}),material,position,name);}
export function hole(shape,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(p);}
export function rectHole(s,w,h,x=0,y=0,r=.06){s.holes.push(roundedRect(w,h,Math.max(.06,r),{cx:x,cy:y,path:new THREE.Path(),clockwise:false}));}
export function annulus(outer,inner,depth){const s=new THREE.Shape();s.absarc(0,0,outer,0,Math.PI*2,false);hole(s,0,0,inner);return new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:40});}
export function cylinder(parent,r,depth,position,material,name,segments=40){return mesh(parent,new THREE.CylinderGeometry(r,r,depth,segments).rotateX(Math.PI/2),material,position,name);}
