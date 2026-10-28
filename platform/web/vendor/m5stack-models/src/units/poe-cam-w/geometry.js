/** MIT. Product-local exact-original U121-B reconstruction, millimetres. */
import * as THREE from 'three';
import {roundedRect} from '../../core/geometry.js';
import {mesh,FACE,portQuaternion} from '../../modeling/parts.js';
export {THREE,roundedRect,FACE,portQuaternion};
export function solid(p,s,d,q,m,n){return mesh(p,new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:24}),m,q,'U121-B '+n);}
export function box(p,s,q,m,n){return mesh(p,new THREE.BoxGeometry(...s),m,q,'U121-B '+n);}
export function hole(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(p);}
export function rectHole(s,w,h,r,x=0,y=0){s.holes.push(roundedRect(w,h,r,{cx:x,cy:y,path:new THREE.Path(),clockwise:true}));}
export function ring(ro,ri){const s=new THREE.Shape();s.absarc(0,0,ro,0,Math.PI*2,false);hole(s,0,0,ri);return s;}
export function frame(p,n,q=[0,0,0],face='front'){const g=new THREE.Group();g.name='U121-B '+n;g.position.fromArray(q);g.quaternion.copy(FACE[face]);p.add(g);return g;}
export function tubeRect(w,h,iw,ih,r=.1){const s=roundedRect(w,h,r);rectHole(s,iw,ih,.08);return s;}
export function cylinder(p,r,h,q,m,n){return mesh(p,new THREE.CylinderGeometry(r,r,h,40).rotateX(Math.PI/2),m,q,'U121-B '+n);}
export function bar(p,a,b,w,m,n){const v=new THREE.Vector3(...a),u=new THREE.Vector3(...b),d=u.clone().sub(v),o=box(p,[w,d.length(),w],v.add(u).multiplyScalar(.5).toArray(),m,n);o.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.normalize());return o;}
