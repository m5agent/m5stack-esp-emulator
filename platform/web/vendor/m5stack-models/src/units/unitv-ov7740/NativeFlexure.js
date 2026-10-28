import * as THREE from 'three';
import {Button} from '../../core/index.js';
/** A real native rear-shell side tongue; two disjoint masks may deform one mesh. */
export class NativeFlexure extends Button{
 constructor({id,sign,shell,follower}){
  const hit=new THREE.Mesh(new THREE.PlaneGeometry(3.1,1.65).rotateY(sign*Math.PI/2),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false}));hit.name='UnitV-OV7740 '+id+' real side-tongue surface input proxy';
  super({id,label:'UnitV-OV7740 '+id+' native side tongue',mesh:hit,position:[sign*12.14,-14.45,-1.05],axis:[-sign,0,0],travel:.22,longPressMs:0,meta:{role:'visual-control',surfaceFace:sign>0?'right':'left',visualMotion:'native-flexure',scope:'Momentary physical side-tongue press/release/cancel intent only;no boot,power,camera,AI,storage or firmware behavior.',travelSource:'Own native molded tongue/hinge and own side photos;0.22mm visual flexure is inferred,not material simulation or certified stop.'}});
  this.shell=shell;this.sign=sign;this.follower=follower;this.followerRest=follower.position.x;this.rest=shell.geometry.attributes.position.array.slice();this.norm=shell.geometry.attributes.normal.array.slice();this.weights=new Float32Array(this.rest.length/3);this.slopes=new Float32Array(this.weights.length);this.affectedIndices=[];this.lastDepth=0;
  for(let i=0;i<this.weights.length;i++){const k=i*3,x=this.rest[k],y=this.rest[k+1],rawZ=this.rest[k+2]+3.15;if(sign*x<10.19||y< -16.51||y> -12.39||rawZ<= -1.5||rawZ>3.296)continue;const t=THREE.MathUtils.clamp((rawZ+1.5)/4.795615,0,1);this.weights[i]=t*t*(3-2*t);this.slopes[i]=6*t*(1-t)/4.795615;if(this.weights[i]>0)this.affectedIndices.push(i);}
  this.meta.deformedNativeVertices=this.affectedIndices.length;
 }
 update(dt){const changed=super.update(dt),depth=this.getActuationState().depthMm;if(depth===this.lastDepth)return changed;const p=this.shell.geometry.attributes.position,n=this.shell.geometry.attributes.normal;for(const i of this.affectedIndices){const k=i*3;p.setXYZ(i,this.rest[k]-this.sign*depth*this.weights[i],this.rest[k+1],this.rest[k+2]);let nx=this.norm[k],ny=this.norm[k+1],nz=this.norm[k+2];if(depth){nz+=this.sign*depth*this.slopes[i]*nx;const length=Math.hypot(nx,ny,nz);nx/=length;ny/=length;nz/=length;}n.setXYZ(i,nx,ny,nz);}p.needsUpdate=true;n.needsUpdate=true;this.shell.geometry.computeBoundingBox();this.shell.geometry.computeBoundingSphere();this.follower.position.x=this.followerRest-this.sign*depth*.93;this.lastDepth=depth;return true;}
 dispose(){super.dispose();this.shell=null;this.follower=null;this.rest=null;this.norm=null;this.weights=null;this.slopes=null;this.affectedIndices=null;}
}
