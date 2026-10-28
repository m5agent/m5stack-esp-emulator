import * as THREE from 'three';
import {mesh,FACE,portQuaternion} from '../../modeling/parts.js';
import {materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
export {THREE,mesh,FACE,portQuaternion,materials,roundedRect};
export function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:32}),material,position,name);}
export function hole(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(h);}
export function annulus(outer,inner,depth){const s=new THREE.Shape();s.absarc(0,0,outer,0,Math.PI*2,false);hole(s,0,0,inner);return new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:40});}
export function cylinder(parent,r,depth,p,m,n,segments=40){return mesh(parent,new THREE.CylinderGeometry(r,r,depth,segments).rotateX(Math.PI/2),m,p,n);}
/** Individually capped positive material loft; section vertices remain identical at cap/side seams. */
export function loft(parent,sections,zs,material,name){
 const s=sections.map(a=>a.map(p=>new THREE.Vector2(...p))),N=s[0].length;if(!s.every(a=>a.length===N)||s.length!==zs.length)throw new Error('Invalid own ENV-IV loft sections');
 if(THREE.ShapeUtils.isClockWise(s[0]))for(const a of s)a.reverse();
 const p=[];for(let k=0;k<s.length;k++)for(const v of s[k])p.push(v.x,v.y,zs[k]);const ix=[];
 for(let k=0;k<s.length-1;k++)for(let i=0;i<N;i++){const j=(i+1)%N,a=k*N+i,b=k*N+j,c=(k+1)*N+j,d=(k+1)*N+i;ix.push(a,b,c,a,c,d);}
 for(const[k,up]of[[0,false],[s.length-1,true]])for(const f of THREE.ShapeUtils.triangulateShape(s[k],[])){let[a,b,c]=f;const ab=s[k][b].clone().sub(s[k][a]),ac=s[k][c].clone().sub(s[k][a]);if((ab.cross(ac)>0)!==up)[b,c]=[c,b];ix.push(k*N+a,k*N+b,k*N+c);}
 const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(p,3));g.setIndex(ix);g.computeVertexNormals();return mesh(parent,g,material,[0,0,0],name);
}
export function stroke(parent,points,width,depth,z,material,name){const out=[];for(let i=1;i<points.length;i++){const a=new THREE.Vector2(...points[i-1]),b=new THREE.Vector2(...points[i]),d=b.clone().sub(a),n=new THREE.Vector2(-d.y,d.x).normalize().multiplyScalar(width/2),s=new THREE.Shape();s.moveTo(a.x+n.x,a.y+n.y);s.lineTo(a.x-n.x,a.y-n.y);s.lineTo(b.x-n.x,b.y-n.y);s.lineTo(b.x+n.x,b.y+n.y);s.closePath();out.push(solid(parent,s,depth,[0,0,z],material,name));}return out;}
