/** MIT; own U082 closed contour construction in mm. */
import * as THREE from 'three';import{mesh}from'../../modeling/parts.js';import{roundedRect}from'../../core/geometry.js';
export function hole(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(p);}
export function solid(parent,s,depth,p,m,n){return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:32}),m,p,n);}
export function ring(ro,ri){const s=new THREE.Shape();s.absarc(0,0,ro,0,Math.PI*2,false);hole(s,0,0,ri);return s;}
export function rectangleRing(w,h,r,iw,ih,ir){const s=roundedRect(w,h,r);s.holes.push(roundedRect(iw,ih,ir,{path:new THREE.Path(),clockwise:true}));return s;}
export function pcbShape(){const p=[[-8.9,22.5],[8.9,22.5],[9.7,21.7],[9.7,20.3],[8.7,19.5],[8.7,18.1],[9.7,17.3],[9.7,-3.3],[8.8,-4.1],[8.8,-6.1],[9.7,-6.9],[9.7,-18.7],[8.8,-19.8],[5.8,-19.8],[5.8,-22.5],[-5.8,-22.5],[-5.8,-19.8],[-8.8,-19.8],[-9.7,-18.7],[-9.7,-7.1],[-8.8,-6.3],[-8.8,-4.8],[-9.7,-4],[-9.7,21.7]];const s=new THREE.Shape();for(const[i,q]of p.entries())i?s.lineTo(...q):s.moveTo(...q);s.closePath();return s;}
