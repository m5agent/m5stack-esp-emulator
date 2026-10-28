import*as THREE from'three';export{THREE};export{materials}from'../../core/index.js';export{mesh,slab,FACE,portQuaternion}from'../../modeling/parts.js';export{roundedRect}from'../../core/geometry.js';import{mesh}from'../../modeling/parts.js';export const tau=Math.PI*2;
export function solid(p,s,d,at,m,n){return mesh(p,new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:32}),m,at,n);}
export function hole(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,tau,false);s.holes.push(p);}
export function ring(p,outer,inner,d,at,m,n){const s=new THREE.Shape();s.absarc(0,0,outer,0,tau,false);hole(s,0,0,inner);return solid(p,s,d,at,m,n);}
