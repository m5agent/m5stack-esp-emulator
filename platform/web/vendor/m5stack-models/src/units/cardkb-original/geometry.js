import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
export {THREE,materials,roundedRect};
export function mesh(parent,g,m,p=[0,0,0],name=''){const o=new THREE.Mesh(g,m);o.position.fromArray(p);o.name='Original U035 '+name;parent.add(o);return o;}
export const box=(p,s,pos,m,n)=>mesh(p,new THREE.BoxGeometry(...s),m,pos,n);
export function hole(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,true);s.holes.push(h);return s;}
export function solid(s,d){return new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:24});}
export function annulus(p,{outer,inner,depth,position,material,name}){const s=new THREE.Shape();s.absarc(0,0,outer,0,Math.PI*2,false);hole(s,0,0,inner);return mesh(p,solid(s,depth),material,position,name);}
export function cutSquare(w=4.9,corner=.5){const a=w/2,s=new THREE.Shape();s.moveTo(-a+corner,-a);s.lineTo(a-corner,-a);s.lineTo(a,-a+corner);s.lineTo(a,a-corner);s.lineTo(a-corner,a);s.lineTo(-a+corner,a);s.lineTo(-a,a-corner);s.lineTo(-a,-a+corner);s.closePath();return s;}
