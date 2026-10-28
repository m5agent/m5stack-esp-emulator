import * as THREE from 'three';import{roundedRect}from'../../core/geometry.js';import{mesh}from'../../modeling/parts.js';
export{THREE,roundedRect,mesh};
export function circleHole(shape,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,-Math.PI*2,true);shape.holes.push(p);return shape;}
export function annulus(ro,ri,depth){const s=new THREE.Shape();s.absarc(0,0,ro,0,Math.PI*2,false);circleHole(s,0,0,ri);return extrude(s,depth);}
export function extrude(s,depth){return new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:32});}
export function box(parent,size,position,material,name){return mesh(parent,new THREE.BoxGeometry(...size),material,position,name);}
export function receiverGeometry(w,h,r,wall,depth){const s=roundedRect(w,h,r);s.holes.push(roundedRect(w-wall*2,h-wall*2,Math.max(.02,r-wall),{path:new THREE.Path(),clockwise:true}));return extrude(s,depth).rotateX(Math.PI/2);}
