import * as THREE from 'three';
import{materials}from'../../core/index.js';import{mesh,FACE,portQuaternion}from'../../modeling/parts.js';import{roundedRect}from'../../core/geometry.js';
export{THREE,materials,FACE,portQuaternion,roundedRect};
export const box=(p,s,a,m,n)=>mesh(p,new THREE.BoxGeometry(...s),m,a,n);
export function polygon(points){const s=new THREE.Shape();points.forEach(([x,y],i)=>i?s.lineTo(x,y):s.moveTo(x,y));s.closePath();return s;}
export function hole(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(h);return s;}
export function solid(p,input,d,a,m,n){const raw=input.extractPoints(32),outer=THREE.ShapeUtils.isClockWise(raw.shape)?raw.shape:raw.shape.reverse(),s=polygon(outer.map(v=>[v.x,v.y]));for(const path of raw.holes){const h=THREE.ShapeUtils.isClockWise(path)?path.reverse():path;s.holes.push(polygon(h.map(v=>[v.x,v.y])));}return mesh(p,new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:32}),m,a,n);}
export function ring(p,r,inner,d,a,m,n){const s=new THREE.Shape();s.absarc(0,0,r,0,Math.PI*2,false);hole(s,0,0,inner);return solid(p,s,d,a,m,n);}
export const cylinder=(p,r,d,a,m,n)=>mesh(p,new THREE.CylinderGeometry(r,r,d,64).rotateX(Math.PI/2),m,a,n);
