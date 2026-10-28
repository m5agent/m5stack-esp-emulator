import * as THREE from 'three';
import {mesh,slab,FACE,portQuaternion} from '../../modeling/parts.js';
import {materials} from '../../core/index.js';
import {roundedRect,capsule} from '../../core/geometry.js';
export {THREE,mesh,slab,FACE,portQuaternion,materials,roundedRect,capsule};
export function hole(shape,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(p);}
export function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:40}),material,position,name);}
export function ring(outer,inner,depth){const s=new THREE.Shape();s.absarc(0,0,outer,0,Math.PI*2,false);hole(s,0,0,inner);return new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:40});}
export function cylinder(parent,r,depth,position,material,name){return mesh(parent,new THREE.CylinderGeometry(r,r,depth,48).rotateX(Math.PI/2),material,position,name);}
export function glassDome(r,height){const top=new THREE.SphereGeometry(r,48,18,0,Math.PI*2,0,Math.PI/2).rotateX(Math.PI/2).scale(1,1,height/r).toNonIndexed(),bottom=new THREE.CircleGeometry(r,48).rotateY(Math.PI).toNonIndexed(),g=new THREE.BufferGeometry();for(const key of['position','normal'])g.setAttribute(key,new THREE.Float32BufferAttribute([...top.attributes[key].array,...bottom.attributes[key].array],3));top.dispose();bottom.dispose();return g;}
