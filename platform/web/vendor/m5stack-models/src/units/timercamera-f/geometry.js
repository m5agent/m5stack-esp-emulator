import * as THREE from 'three';import {mesh,slab,FACE,portQuaternion} from '../../modeling/parts.js';import {materials} from '../../core/index.js';import {roundedRect,capsule} from '../../core/geometry.js';export{THREE,mesh,slab,FACE,portQuaternion,materials,roundedRect,capsule};
export const tau=Math.PI*2;
export function hole(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);s.holes.push(h);}
export function solid(p,s,d,at,m,n){return mesh(p,new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:40}),m,at,n);}
export function annulus(r,i,d){const s=new THREE.Shape();s.absarc(0,0,r,0,tau,false);hole(s,0,0,i);return new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:48});}
export function cylinder(p,r,d,at,m,n){return mesh(p,new THREE.CylinderGeometry(r,r,d,48).rotateX(Math.PI/2),m,at,n);}
export function dome(r,h){const top=new THREE.SphereGeometry(r,64,24,0,tau,0,Math.PI/2).rotateX(Math.PI/2).scale(1,1,h/r).toNonIndexed(),base=new THREE.CircleGeometry(r,64).rotateY(Math.PI).toNonIndexed(),g=new THREE.BufferGeometry();for(const name of['position','normal'])g.setAttribute(name,new THREE.Float32BufferAttribute([...top.attributes[name].array,...base.attributes[name].array],3));top.dispose();base.dispose();return g;}
