/** MIT; closed product-local contours;all dimensions mm. */
import * as THREE from'three';import{roundedRect}from'../../core/geometry.js';import{mesh}from'../../modeling/parts.js';
export function hole(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(p);}
export function solid(parent,s,depth,p,m,n){return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:32}),m,p,n);}
export function ring(ro,ri){const s=new THREE.Shape();s.absarc(0,0,ro,0,Math.PI*2,false);hole(s,0,0,ri);return s;}
export function rectangleRing(w,h,r,iw,ih,ir){const s=roundedRect(w,h,r);s.holes.push(roundedRect(iw,ih,ir,{path:new THREE.Path(),clockwise:true}));return s;}
export function corner(cx,cy,a){const s=new THREE.Shape();s.absarc(cx,cy,4,a,a+Math.PI/2,false);s.lineTo(cx+2.8*Math.cos(a+Math.PI/2),cy+2.8*Math.sin(a+Math.PI/2));s.absarc(cx,cy,2.8,a+Math.PI/2,a,true);s.closePath();return s;}
export function rearFrame(){const s=new THREE.Shape();s.moveTo(-8,-24);s.lineTo(-5.5,-24);s.lineTo(-5.5,-16);s.lineTo(5.5,-16);s.lineTo(5.5,-24);s.lineTo(8,-24);s.absarc(8,-20,4,-Math.PI/2,0,false);s.lineTo(12,20);s.absarc(8,20,4,0,Math.PI/2,false);s.lineTo(-8,24);s.absarc(-8,20,4,Math.PI/2,Math.PI,false);s.lineTo(-12,-20);s.absarc(-8,-20,4,Math.PI,Math.PI*1.5,false);s.closePath();s.holes.push(roundedRect(19.4,36.5,1.6,{cy:3,path:new THREE.Path(),clockwise:true}));for(const x of[-8,8])hole(s,x,-19.5,1.35);return s;}
