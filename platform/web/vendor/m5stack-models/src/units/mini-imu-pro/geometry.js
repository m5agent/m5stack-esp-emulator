import * as THREE from 'three';
import {mesh,slab,FACE,portQuaternion} from '../../modeling/parts.js';
import {materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
export {THREE,mesh,slab,FACE,portQuaternion,materials,roundedRect};
const tau=Math.PI*2;
export function hole(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);s.holes.push(h);}
export function solid(parent,s,depth,p,m,name){return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:40}),m,p,name);}
export function annulus(r,i,depth){const s=new THREE.Shape();s.absarc(0,0,r,0,tau,false);hole(s,0,0,i);return new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:48});}
/** Independently traced own U171 outline with real open Grove notch and depressed mounting shelves. */
export function outline({edge=12,radius=4,notch=false,notchTop=-5.05,relief=0}={}){
 const s=new THREE.Shape(),c=edge-radius;s.moveTo(-c,-edge);
 if(notch){s.lineTo(-5.1,-edge);s.lineTo(-5.1,notchTop);s.lineTo(5.1,notchTop);s.lineTo(5.1,-edge);}
 s.lineTo(c,-edge);s.absarc(c,-c,radius,-Math.PI/2,0,false);
 if(relief){s.lineTo(edge,-relief);s.lineTo(8,-relief);s.absarc(8,0,relief,-Math.PI/2,-Math.PI*1.5,true);s.lineTo(edge,relief);}
 s.lineTo(edge,c);s.absarc(c,c,radius,0,Math.PI/2,false);s.lineTo(-c,edge);s.absarc(-c,c,radius,Math.PI/2,Math.PI,false);
 if(relief){s.lineTo(-edge,relief);s.lineTo(-8,relief);s.absarc(-8,0,relief,Math.PI/2,-Math.PI/2,true);s.lineTo(-edge,-relief);}
 s.lineTo(-edge,-c);s.absarc(-c,-c,radius,Math.PI,Math.PI*1.5,false);s.closePath();return s;
}
export function corner(parent,cx,cy,a,b,z,depth,m,name){const s=new THREE.Shape();s.absarc(cx,cy,4,a,b,false);s.lineTo(cx+Math.cos(b)*2.8,cy+Math.sin(b)*2.8);s.absarc(cx,cy,2.8,b,a,true);s.closePath();return solid(parent,s,depth,[0,0,z],m,name);}
