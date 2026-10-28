import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {mesh,FACE,portQuaternion} from '../../modeling/parts.js';
import {roundedRect} from '../../core/geometry.js';
export {THREE,materials,FACE,portQuaternion,roundedRect};
export const box=(p,size,position,material,name)=>mesh(p,new THREE.BoxGeometry(...size),material,position,name);
export function polygon(points){const s=new THREE.Shape();points.forEach(([x,y],i)=>i?s.lineTo(x,y):s.moveTo(x,y));s.closePath();return s;}
export function hole(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(h);return s;}
/** Explicit opposite contour winding keeps all material and bore walls outward FrontSide. */
export function solid(parent,input,depth,position,material,name){const raw=input.extractPoints(40),outer=THREE.ShapeUtils.isClockWise(raw.shape)?raw.shape:raw.shape.reverse(),s=polygon(outer.map(v=>[v.x,v.y]));for(const path of raw.holes){const h=THREE.ShapeUtils.isClockWise(path)?path.reverse():path;s.holes.push(polygon(h.map(v=>[v.x,v.y])));}return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:40}),material,position,name);}
export function ring(p,r,inner,d,at,m,n){const s=new THREE.Shape();s.absarc(0,0,r,0,Math.PI*2,false);hole(s,0,0,inner);return solid(p,s,d,at,m,n);}
export const cylinder=(p,r,d,at,m,n)=>mesh(p,new THREE.CylinderGeometry(r,r,d,64).rotateX(Math.PI/2),m,at,n);
