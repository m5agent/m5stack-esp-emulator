/** MIT. Preserve all C008-B-V11 source faces/attributes at rest;only its connected reset tongue flexes. */
import {Button} from '../../core/index.js';
import {THREE,FACE} from './geometry.js';
import {spec} from './dimensions.js';
import {weightedInputHit} from '../../modeling/weighted-input.js';
export class NativeReset extends Button{
 constructor(shell){
  const hit=new THREE.Mesh(new THREE.PlaneGeometry(3.9,3.3),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false}));hit.name='Matrix v1.1 reset-only input proxy;native tongue is physical';
  super({id:'reset',label:'Side Reset physical input',mesh:hit,position:spec.reset.position,quaternion:FACE.left,travel:spec.reset.travelMm,longPressMs:0,meta:{role:'visual-control',motion:'own native flexure',noFirmwareAction:true,travelAndFlexure:'inferred appearance,not measured threshold'}});
  this.shell=shell;this.rest=shell.geometry.attributes.position.array.slice();this.restNormal=shell.geometry.attributes.normal.array.slice();this.lastDepth=0;this.weights=new Float32Array(this.rest.length/3);this.slopes=new Float32Array(this.weights.length);
  // The own-source U-slot isolates this graph after its fixed root at raw Z=1.7 is removed.
  // In particular the inner wall and the raised free end are part of the same tongue.
  const nodes=new Map(),keys=[],source=shell.geometry.attributes.sourceFaceIndex,dx=shell.position.x;
  for(let i=0;i<this.weights.length;i++){const k=i*3,key=[this.rest[k],this.rest[k+1],this.rest[k+2]].map(x=>Math.round(x*1e5)).join(',');keys.push(key);let node=nodes.get(key);if(!node)nodes.set(key,node={x:this.rest[k]+dx,z:this.rest[k+2],indices:[],near:new Set()});node.indices.push(i);}
  const eligible=n=>n.x< -9.9&&n.z>spec.reset.sourceHingeZ+1e-5;
  for(let i=0;i<this.weights.length;i+=3)for(let j=0;j<3;j++)for(let l=0;l<3;l++){const a=nodes.get(keys[i+j]),b=nodes.get(keys[i+l]);if(eligible(a)&&eligible(b))a.near.add(keys[i+l]);}
  const seed=Array.from(source.array).findIndex(face=>face===2701),seen=new Set(),queue=[keys[seed]],span=spec.reset.sourceFreeZ-spec.reset.sourceHingeZ;
  for(let j=0;j<queue.length;j++){const key=queue[j];if(seen.has(key))continue;seen.add(key);const node=nodes.get(key),t=THREE.MathUtils.clamp((node.z-spec.reset.sourceHingeZ)/span,0,1);for(const i of node.indices){this.weights[i]=t*t*(3-2*t);this.slopes[i]=6*t*(1-t)/span;}queue.push(...node.near);}
  this.meta.movingNativeVertices=this.weights.filter(x=>x>0).length;this.meta.connectedTongueUniqueVertices=seen.size;this.meta.fixedRootRawZ=spec.reset.sourceHingeZ;
  this.hit(shell,intersection=>weightedInputHit(this,shell,intersection));
 }
 bindFollower(follower){
  // Interpolate the actual own inner-wall source triangle at the follower height.
  const p=this.shell.geometry.attributes.position,sf=this.shell.geometry.attributes.sourceFaceIndex,origin=new THREE.Vector3(-this.shell.position.x,follower.position.y-this.shell.position.y,follower.position.z-this.shell.position.z),ray=new THREE.Ray(origin,new THREE.Vector3(-1,0,0));let nearest=null;
  for(let i=0;i<p.count;i+=3){const a=new THREE.Vector3().fromBufferAttribute(p,i),b=new THREE.Vector3().fromBufferAttribute(p,i+1),c=new THREE.Vector3().fromBufferAttribute(p,i+2),point=ray.intersectTriangle(a,b,c,true,new THREE.Vector3());if(!point)continue;const distance=origin.distanceTo(point);if(nearest&&distance>=nearest.distance)continue;const bary=THREE.Triangle.getBarycoord(point,a,b,c,new THREE.Vector3());nearest={distance,point:point.clone().add(this.shell.position).toArray(),sourceFace:sf.getX(i),indices:[i,i+1,i+2],barycentric:bary.toArray(),weight:bary.x*this.weights[i]+bary.y*this.weights[i+1]+bary.z*this.weights[i+2]};}
  if(!nearest||nearest.weight<=0)throw new Error('Matrix v1.1 follower must track its own moving inner wall');
  this.follower=follower;this.followerRest=follower.position.x;this.followerWeight=nearest.weight;this.followerNativeAnchor=nearest;
 }
 update(dt){const changed=super.update(dt),depth=this.getActuationState().depthMm;if(depth===this.lastDepth)return changed;const p=this.shell.geometry.attributes.position,n=this.shell.geometry.attributes.normal;for(let i=0;i<this.weights.length;i++){if(!this.weights[i])continue;const k=i*3;if(depth===0){p.setXYZ(i,this.rest[k],this.rest[k+1],this.rest[k+2]);n.setXYZ(i,this.restNormal[k],this.restNormal[k+1],this.restNormal[k+2]);continue;}p.setXYZ(i,this.rest[k]+depth*this.weights[i],this.rest[k+1],this.rest[k+2]);let nx=this.restNormal[k],ny=this.restNormal[k+1],nz=this.restNormal[k+2]-depth*this.slopes[i]*nx,l=Math.hypot(nx,ny,nz);n.setXYZ(i,nx/l,ny/l,nz/l);}p.needsUpdate=true;n.needsUpdate=true;this.shell.geometry.computeBoundingBox();this.shell.geometry.computeBoundingSphere();if(this.follower)this.follower.position.x=this.followerRest+depth*this.followerWeight;this.lastDepth=depth;return true;}
 dispose(){super.dispose();this.shell=null;this.rest=null;this.restNormal=null;this.weights=null;this.slopes=null;this.follower=null;this.followerNativeAnchor=null;}
}
