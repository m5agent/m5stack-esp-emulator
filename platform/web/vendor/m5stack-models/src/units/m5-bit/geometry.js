/** MIT; closed product-local solids. */
import * as THREE from 'three';import{mesh}from'../../modeling/parts.js';
export function hole(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(p);}
export function solid(parent,s,d,p,m,n){return mesh(parent,new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:24}),m,p,n);}
export function ring(parent,x,y,outer,inner,z,d,m,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,Math.PI*2,false);hole(s,0,0,inner);return solid(parent,s,d,[x,y,z],m,name);}
export function pcbContour(){const s=new THREE.Shape();s.moveTo(-28.2,-10.5);s.lineTo(28.2,-10.5);s.lineTo(28.5,-10.2);s.lineTo(28.5,.5);s.lineTo(27.6,.5);s.absarc(27.6,1.3,.8,-Math.PI/2,-Math.PI*1.5,true);s.lineTo(28.5,2.1);s.lineTo(28.5,10.2);s.lineTo(28.2,10.5);s.lineTo(-28.2,10.5);s.lineTo(-28.5,10.2);s.lineTo(-28.5,2.1);s.lineTo(-27.6,2.1);s.absarc(-27.6,1.3,.8,Math.PI/2,-Math.PI/2,true);s.lineTo(-28.5,.5);s.lineTo(-28.5,-10.2);s.closePath();return s;}
