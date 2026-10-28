import * as THREE from 'three';
import{mesh,portQuaternion}from'../../modeling/parts.js';
import{materials}from'../../core/index.js';
import{roundedRect}from'../../core/geometry.js';
import{spec,mountingCenters}from'./dimensions.js';
export{THREE,mesh,portQuaternion,materials,roundedRect};
export const TAU=Math.PI*2;
export function hole(shape,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,TAU,false);shape.holes.push(p);}
export function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:32}),material,position,name);}
export function ring(parent,outer,inner,depth,position,material,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,TAU,false);hole(s,0,0,inner);return solid(parent,s,depth,position,material,name);}
export function hexShape(){const s=new THREE.Shape();for(let i=0;i<6;i++){const a=i*Math.PI/3,x=spec.bodyRadiusMm*Math.cos(a),y=spec.bodyRadiusMm*Math.sin(a);i?s.lineTo(x,y):s.moveTo(x,y);}s.closePath();return s;}
export function boardShape(drills=[]){
 const s=new THREE.Shape();s.moveTo(spec.bodyRadiusMm,0);
 for(let i=0;i<6;i++){
  const a=(30+i*60)*Math.PI/180,n=[Math.cos(a),Math.sin(a)],t=[-Math.sin(a),Math.cos(a)],c=[18*n[0],18*n[1]];
  s.lineTo(15.5*n[0]-2*t[0],15.5*n[1]-2*t[1]);s.lineTo(c[0]-2*t[0],c[1]-2*t[1]);
  s.absarc(c[0],c[1],2,a-Math.PI/2,a+Math.PI/2,false);
  s.lineTo(15.5*n[0]+2*t[0],15.5*n[1]+2*t[1]);
  const next=(i+1)*Math.PI/3;s.lineTo(spec.bodyRadiusMm*Math.cos(next),spec.bodyRadiusMm*Math.sin(next));hole(s,c[0],c[1],1.06);
  const points=roundedRect(2.2,.35,.175).getPoints(32).map(p=>new THREE.Vector2(15.7*n[0]+p.x*t[0]+p.y*n[0],15.7*n[1]+p.x*t[1]+p.y*n[1]));
  s.holes.push(new THREE.Path(points));
 }
 s.closePath();for(const[x,y]of drills)hole(s,x,y,.36);return s;
}
export function box(parent,size,position,material,name){return mesh(parent,new THREE.BoxGeometry(...size),material,position,name);}
export{mountingCenters};
