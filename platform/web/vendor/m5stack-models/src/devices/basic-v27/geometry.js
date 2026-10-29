/** MIT. Original closed K001-V27 reconstruction primitives. */
import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {mesh,slab,FACE,portQuaternion,header,grove} from '../../modeling/parts.js';
export {THREE,materials,mesh,slab,FACE,portQuaternion,header,grove,roundedRect};
export const box=(p,s,a,m,n)=>mesh(p,new THREE.BoxGeometry(...s),m,a,n);
export const cylinder=(p,r,d,a,m,n)=>mesh(p,new THREE.CylinderGeometry(r,r,d,64).rotateX(Math.PI/2),m,a,n);
export function ring(p,w,h,d,r,innerW,innerH,a,m,n){const s=roundedRect(w,h,r);s.holes.push(roundedRect(innerW,innerH,Math.max(.1,r-(w-innerW)/2),{path:new THREE.Path(),clockwise:true}));return mesh(p,new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:24}),m,a,n);}
export function tube(p,r,ri,d,a,m,n){const s=new THREE.Shape().absarc(0,0,r,0,Math.PI*2,false),h=new THREE.Path().absarc(0,0,ri,0,Math.PI*2,true);s.holes.push(h);return mesh(p,new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:48}),m,a,n);}
export function frame(p,position,face,name){const g=new THREE.Group();g.position.fromArray(position);g.quaternion.copy(FACE[face]);g.name=name;p.add(g);return g;}
