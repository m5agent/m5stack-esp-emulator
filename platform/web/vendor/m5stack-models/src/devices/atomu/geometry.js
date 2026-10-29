/** MIT. Closed own reconstructed physical primitives;dimensions inferred unless native. */
import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {mesh as partMesh,FACE,portQuaternion} from '../../modeling/parts.js';
import {roundedRect} from '../../core/geometry.js';
export {THREE,materials,FACE,portQuaternion,roundedRect};
// Per-mesh ownership:repeated receiver walls/floors never share disposable materials.
export const mesh=(p,g,m,a,n)=>partMesh(p,g,Array.isArray(m)?m.map(x=>x.clone()):m.clone(),a,n);
export const box=(p,s,a,m,n)=>mesh(p,new THREE.BoxGeometry(...s),m,a,n);
export function polygon(points){const s=new THREE.Shape();points.forEach(([x,y],i)=>i?s.lineTo(x,y):s.moveTo(x,y));s.closePath();return s;}
export function circleHole(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,true);s.holes.push(h);return s;}
export function solid(p,shape,depth,position,material,name){return mesh(p,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:32}),material,position,name);}
export function plate(p,w,h,d,r,at,m,name,holes=[]){const s=r<=0?polygon([[-w/2,-h/2],[w/2,-h/2],[w/2,h/2],[-w/2,h/2]]):roundedRect(w,h,r);for(const hole of holes){if(hole.r)circleHole(s,hole.x??0,hole.y??0,hole.r);else{const x=hole.x??0,y=hole.y??0,w=hole.w/2,h=hole.h/2,p=new THREE.Path();p.moveTo(x-w,y-h);p.lineTo(x-w,y+h);p.lineTo(x+w,y+h);p.lineTo(x+w,y-h);p.closePath();s.holes.push(p);}}return solid(p,s,d,at,m,name);}
export function ring(p,r,inner,d,at,m,name){const s=new THREE.Shape();s.absarc(0,0,r,0,Math.PI*2,false);circleHole(s,0,0,inner);return solid(p,s,d,at,m,name);}
export const cylinder=(p,r,d,at,m,n)=>mesh(p,new THREE.CylinderGeometry(r,r,d,48).rotateX(Math.PI/2),m,at,n);
