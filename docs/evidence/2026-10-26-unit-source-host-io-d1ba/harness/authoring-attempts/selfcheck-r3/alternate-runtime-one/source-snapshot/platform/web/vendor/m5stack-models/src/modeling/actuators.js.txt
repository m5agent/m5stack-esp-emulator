import * as THREE from 'three';
import {Button} from '../core/index.js';
import {roundedRect} from '../core/geometry.js';
import {FACE} from './parts.js';

const EPS=1e-5;
function clipped(poly,plane,positive=true){
 const result=[];for(let i=0;i<poly.length;i++){
  const a=poly[i],b=poly[(i+1)%poly.length],da=plane.normal.dot(a.p)-plane.constant,db=plane.normal.dot(b.p)-plane.constant,ina=positive?da>=-EPS:da< -EPS,inb=positive?db>=-EPS:db< -EPS;
  if(ina)result.push(a);if(ina!==inb){const t=da/(da-db);result.push({p:a.p.clone().lerp(b.p,t),n:a.n.clone().lerp(b.n,t).normalize()});}
 }return result;
}
function triangleFan(poly,positions,normals,transform){
 for(let i=1;i+1<poly.length;i++)for(const v of [poly[0],poly[i],poly[i+1]]){const p=transform?v.p.clone().applyMatrix4(transform):v.p,n=transform?v.n.clone().transformDirection(transform):v.n;positions.push(p.x,p.y,p.z);normals.push(n.x,n.y,n.z);}
}
function geometry(positions,normals){const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));g.setAttribute('normal',new THREE.Float32BufferAttribute(normals,3));g.computeBoundingBox();return g;}
function key(p){return [p.x,p.y,p.z].map(x=>Math.round(x/EPS)).join(',');}

// Close only the newly cut boundaries, never an original acoustic/optical hole.
function closeCuts(positions,normals,planes){
 const edges=new Map(),point=i=>new THREE.Vector3(...positions.slice(i,i+3));
 for(let i=0;i<positions.length;i+=9)for(const [a,b]of [[i,i+3],[i+3,i+6],[i+6,i]]){const p=point(a),q=point(b),kp=key(p),kq=key(q);if(kp===kq)continue;const k=[kp,kq].sort().join('|'),e=edges.get(k);if(e)e.count++;else edges.set(k,{p,q,count:1});}
 let closures=0;
 for(const plane of planes){
  const pending=[...edges.values()].filter(e=>e.count===1&&Math.abs(plane.normal.dot(e.p)-plane.constant)<EPS*4&&Math.abs(plane.normal.dot(e.q)-plane.constant)<EPS*4);
  while(pending.length){const first=pending.pop(),loop=[first.p,first.q];let closed=false;
   while(pending.length){const end=loop.at(-1);if(end.distanceTo(loop[0])<EPS*4){closed=true;break;}const at=pending.findIndex(e=>e.p.distanceTo(end)<EPS*4||e.q.distanceTo(end)<EPS*4);if(at<0)break;const edge=pending.splice(at,1)[0];loop.push(edge.p.distanceTo(end)<EPS*4?edge.q:edge.p);}
   if(loop.at(-1).distanceTo(loop[0])<EPS*4)closed=true;if(!closed||loop.length<4)continue;loop.pop();
   const normal=plane.normal.clone().negate(),u=new THREE.Vector3(Math.abs(normal.y)<.9?0:1,Math.abs(normal.y)<.9?1:0,0).cross(normal).normalize(),v=normal.clone().cross(u),flat=loop.map(p=>new THREE.Vector2(p.dot(u),p.dot(v)));
   for(const tri of THREE.ShapeUtils.triangulateShape(flat,[])){const a=loop[tri[0]],b=loop[tri[1]],c=loop[tri[2]],cross=b.clone().sub(a).cross(c.clone().sub(a));const order=cross.dot(normal)>=0?[a,b,c]:[a,c,b];for(const p of order){positions.push(p.x,p.y,p.z);normals.push(normal.x,normal.y,normal.z);}}closures++;
  }
 }return closures;
}

/**
 * Separate an actual native CAD face/sidewall from a continuous molded part.
 * Every original triangle is partitioned: the fixed duplicate of the cap is
 * removed from the source. Newly cut closed contours receive a backing face;
 * open native flex-molding surfaces remain surface patches, not fit-ready CAD.
 * Origin/footprint are in the product frame; local +Z points out of the case.
 */
export function extractCadCap(source,{name='Native CAD actuator cap',position,face='front',w,h,r=0,depth=1,outward=1}){
 if(!source?.isMesh)throw new Error('CAD actuator requires its source mesh');
 source.updateMatrix();const pose=new THREE.Matrix4().compose(new THREE.Vector3(...position),FACE[face],new THREE.Vector3(1,1,1)),toCap=pose.clone().invert().multiply(source.matrix),toSource=toCap.clone().invert(),normalMatrix=new THREE.Matrix3().getNormalMatrix(toCap);
 let contour=roundedRect(w,h,r).getPoints(8);contour=contour.filter((p,i)=>i===0||p.distanceTo(contour[i-1])>EPS);if(contour[0].distanceTo(contour.at(-1))<EPS)contour.pop();if(THREE.ShapeUtils.area(contour)<0)contour.reverse();
 const planes=contour.map((a,i)=>{const b=contour[(i+1)%contour.length],n=new THREE.Vector3(a.y-b.y,b.x-a.x,0).normalize();return {normal:n,constant:n.x*a.x+n.y*a.y};});planes.push({normal:new THREE.Vector3(0,0,1),constant:-depth},{normal:new THREE.Vector3(0,0,-1),constant:-outward});
 const src=source.geometry,ps=src.attributes.position,ns=src.attributes.normal,index=src.index,keepP=[],keepN=[],capP=[],capN=[];let selected=0;
 for(let i=0;i<(index?.count??ps.count);i+=3){let poly=Array.from({length:3},(_,k)=>{const at=index?index.getX(i+k):i+k;return {p:new THREE.Vector3().fromBufferAttribute(ps,at).applyMatrix4(toCap),n:new THREE.Vector3().fromBufferAttribute(ns,at).applyMatrix3(normalMatrix).normalize()};});
  if(Math.max(...poly.map(v=>v.p.x))< -w/2-EPS||Math.min(...poly.map(v=>v.p.x))>w/2+EPS||Math.max(...poly.map(v=>v.p.y))< -h/2-EPS||Math.min(...poly.map(v=>v.p.y))>h/2+EPS||Math.max(...poly.map(v=>v.p.z))< -depth-EPS||Math.min(...poly.map(v=>v.p.z))>outward+EPS){triangleFan(poly,keepP,keepN,toSource);continue;}
  for(const plane of planes){const outside=clipped(poly,plane,false);if(outside.length>=3)triangleFan(outside,keepP,keepN,toSource);poly=clipped(poly,plane,true);if(poly.length<3)break;}
  if(poly.length>=3){triangleFan(poly,capP,capN);selected++;}
 }
 if(!selected||!capP.length)throw new Error(`${name}: selected no native CAD surface`);
 const closures=closeCuts(capP,capN,planes),old=source.geometry;source.geometry=geometry(keepP,keepN);old.dispose();
 const material=Array.isArray(source.material)?source.material.map(m=>m.clone()):source.material.clone(),cap=new THREE.Mesh(geometry(capP,capN),material);cap.name=name;cap.userData={source:'official-structure',role:'physical-actuator-cap',sourcePart:source.name,selectedTriangles:selected,cutClosures:closures};
 return {cap,position,face};
}

export function cadButton(host,{source,position,face='front',w,h,r=0,depth=1,outward=1,id,label,travel=.18,axis=[0,0,-1],meta={}}){
 const {cap}=extractCadCap(source,{name:`Physical ${id} native CAD cap`,position,face,w,h,r,depth,outward});
 return host.add(new Button({id,label,mesh:cap,position,quaternion:FACE[face],axis,travel,meta:{...meta,role:meta.role??'visual-control',actuation:'momentary',surfaceCenter:position,surfaceFace:face}}));
}

/** Bind separately modeled geometry without leaving a stationary copy behind. */
export function physicalButton(host,{id,label,mesh,position,quaternion,axis=[0,0,-1],travel=.2,latching=false,meta={}}){
 mesh.userData.role='physical-actuator-cap';
 return host.add(new Button({id,label,mesh,position,quaternion,axis,travel,latching,meta:{...meta,actuation:latching?'latching':'momentary'}}));
}
