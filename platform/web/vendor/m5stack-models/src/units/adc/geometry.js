import*as THREE from'three';import{materials}from'../../core/index.js';import{mesh,FACE,portQuaternion}from'../../modeling/parts.js';import{roundedRect}from'../../core/geometry.js';export{THREE,materials,mesh,FACE,portQuaternion,roundedRect};
export const box=(p,s,at,m,n)=>mesh(p,new THREE.BoxGeometry(...s),m,at,n);
export function polygon(points){const s=new THREE.Shape();points.forEach(([x,y],i)=>i?s.lineTo(x,y):s.moveTo(x,y));s.closePath();return s;}
export function circleHole(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(h);return s;}
export function solid(p,s,d,at,m,n){const points=s.extractPoints(48),contour=THREE.ShapeUtils.isClockWise(points.shape)?points.shape:points.shape.reverse(),shape=polygon(contour.map(v=>[v.x,v.y]));for(const raw of points.holes){const h=THREE.ShapeUtils.isClockWise(raw)?raw.reverse():raw;shape.holes.push(polygon(h.map(v=>[v.x,v.y])));}return mesh(p,new THREE.ExtrudeGeometry(shape,{depth:d,bevelEnabled:false,curveSegments:48}),m,at,n);}
export function ring(p,r,inner,d,at,m,n){const s=new THREE.Shape();s.absarc(0,0,r,0,Math.PI*2,false);circleHole(s,0,0,inner);return solid(p,s,d,at,m,n);}
export const cylinder=(p,r,d,at,m,n)=>mesh(p,new THREE.CylinderGeometry(r,r,d,64).rotateX(Math.PI/2),m,at,n);
export function crossProfile(p,s,depth,at,m,n){const o=solid(p,s,depth,at,m,n);o.rotation.x=Math.PI/2;return o;}
export function filmProfile(){return polygon([[-3.8,-2],[3.8,-2],[3.8,1.5],[3.4,2],[.65,2],[0,1.55],[-.65,2],[-3.4,2],[-3.8,1.5]]);}
