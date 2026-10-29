// MIT. Own C126-CAM connected native side tongue, with exact rest arrays and stable source-face IDs.
import {Button} from '../../core/index.js';
import {THREE,FACE} from './geometry.js';
import {weightedInputHit} from '../../modeling/weighted-input.js';
import {spec} from './dimensions.js';
export class NativeReset extends Button{
 constructor(shell){
  // Input comes from the actual native surface, including its raised free end.
  super({id:'reset',label:'C126-CAM side Reset',position:[-11,4.5,-2],quaternion:FACE.left,travel:spec.travelMm.reset,longPressMs:0,meta:{role:'visual-control',actuation:'native-flexure',gpio:'RESET',surfaceCenter:[-11,4.5,-2],surfaceFace:'left',travelSource:'C126-CAM own native/photo inferred visual travel;not a rated threshold',scope:'Input intent only;no reboot/download/LED side effect'}});
  this.shell=shell;this.rest=shell.geometry.attributes.position.array.slice();this.restNormal=shell.geometry.attributes.normal.array.slice();this.weights=new Float32Array(this.rest.length/3);this.lastDepth=0;this.followers=[];
  const nodes=new Map(),keys=[],sf=shell.geometry.attributes.sourceFaceIndex;
  for(let i=0;i<this.weights.length;i++){const k=i*3,key=[this.rest[k],this.rest[k+1],this.rest[k+2]].map(x=>Math.round(x*1e5)).join(',');keys.push(key);let node=nodes.get(key);if(!node)nodes.set(key,node={p:new THREE.Vector3(this.rest[k],this.rest[k+1],this.rest[k+2]).add(shell.position),indices:[],near:new Set()});node.indices.push(i);}
  const eligible=n=>n.p.x< -9.9&&n.p.z>spec.reset.rootZ+1e-5;
  for(let i=0;i<this.weights.length;i+=3)for(let j=0;j<3;j++)for(let k=0;k<3;k++){const a=nodes.get(keys[i+j]),b=nodes.get(keys[i+k]);if(eligible(a)&&eligible(b))a.near.add(keys[i+k]);}
  const seed=Array.from(sf.array).map((face,i)=>({face,i,node:nodes.get(keys[i])})).filter(q=>q.face===spec.reset.seedSourceFace&&eligible(q.node)).sort((a,b)=>b.node.p.z-a.node.p.z)[0]?.i??-1;if(seed<0)throw new Error('C126-CAM own reset source face missing');
  const seen=new Set(),queue=[keys[seed]],span=spec.reset.freeZ-spec.reset.rootZ;
  for(let j=0;j<queue.length;j++){const key=queue[j];if(seen.has(key))continue;seen.add(key);const n=nodes.get(key),w=THREE.MathUtils.clamp((n.p.z-spec.reset.rootZ)/span,0,1);for(const i of n.indices)this.weights[i]=w;queue.push(...n.near);}
  this.meta.movingNativeVertices=this.weights.filter(w=>w>0).length;this.meta.connectedTongueVertices=seen.size;this.hit(shell,h=>weightedInputHit(this,shell,h));
 }
 follow(object){
  this.shell.updateWorldMatrix(true,false);const p=this.shell.geometry.attributes.position,sf=this.shell.geometry.attributes.sourceFaceIndex,anchor=object.getWorldPosition(new THREE.Vector3()),localAnchor=this.shell.parent.worldToLocal(anchor),origin=new THREE.Vector3(0,localAnchor.y,localAnchor.z).sub(this.shell.position),ray=new THREE.Ray(origin,new THREE.Vector3(-1,0,0));let best=null;
  for(let i=0;i<p.count;i+=3){const v=[0,1,2].map(k=>new THREE.Vector3().fromBufferAttribute(p,i+k)),hit=ray.intersectTriangle(...v,true,new THREE.Vector3());if(!hit)continue;const distance=origin.distanceTo(hit);if(best&&distance>=best.distance)continue;const bary=THREE.Triangle.getBarycoord(hit,...v,new THREE.Vector3()),weight=bary.x*this.weights[i]+bary.y*this.weights[i+1]+bary.z*this.weights[i+2];best={distance,weight,sourceFace:sf.getX(i)};}
  if(!best||best.weight<=0)throw new Error('C126-CAM Reset follower must track own moving inner wall');this.followers.push({object,rest:object.position.x,weight:best.weight});this.followerAnchor=best;
 }
 update(dt){const changed=super.update(dt),d=this.getActuationState().depthMm;if(d===this.lastDepth)return changed;const p=this.shell.geometry.attributes.position,n=this.shell.geometry.attributes.normal,span=spec.reset.freeZ-spec.reset.rootZ;
  for(let i=0;i<this.weights.length;i++){const w=this.weights[i];if(!w)continue;const k=i*3;p.setXYZ(i,this.rest[k]+d*w,this.rest[k+1],this.rest[k+2]);let nx=this.restNormal[k],ny=this.restNormal[k+1],nz=this.restNormal[k+2];if(d){nz-=d/span*nx;const len=Math.hypot(nx,ny,nz);nx/=len;ny/=len;nz/=len;}n.setXYZ(i,nx,ny,nz);}
  p.needsUpdate=true;n.needsUpdate=true;this.shell.geometry.computeBoundingBox();this.shell.geometry.computeBoundingSphere();for(const f of this.followers)f.object.position.x=f.rest+d*f.weight;this.lastDepth=d;return true;
 }
 dispose(){if(this.shell){const p=this.shell.geometry.attributes.position,n=this.shell.geometry.attributes.normal;p.array.set(this.rest);n.array.set(this.restNormal);p.needsUpdate=true;n.needsUpdate=true;this.shell.geometry.computeBoundingBox();this.shell.geometry.computeBoundingSphere();for(const f of this.followers)f.object.position.x=f.rest;}super.dispose();this.shell=null;this.rest=null;this.restNormal=null;this.weights=null;this.followers=[];}
}
