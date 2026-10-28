import * as THREE from 'three';
import {Button} from '../../core/index.js';
import {FACE} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
/** Exact native U-cut tongue retains every source face and its fixed upper hinge. */
export class NativeButton extends Button{
 constructor(shell,follower){
  const hit=new THREE.Mesh(new THREE.PlaneGeometry(5.45,6.7),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false}));hit.name='U078-USB actual native tongue hit surface';
  super({id:'user',label:'Top-end native User actuator',mesh:hit,position:spec.user.position,quaternion:FACE.top,travel:spec.user.travelMm,axis:[0,0,-1],meta:{role:'visual-control',visualMotion:'native-flexure',surfaceFace:'top',scope:'Actual U-cut shell actuator and its internal follower only;input intent,no boot,AI,power,USB or firmware linkage.',travelSource:'Own native tongue/photo appearance estimate,not a material or rated-stop model.'}});
  this.shell=shell;this.follower=follower;this.followerRest=follower.position.y;this.restPositions=shell.geometry.attributes.position.array.slice();this.restNormals=shell.geometry.attributes.normal.array.slice();this.weights=new Float32Array(this.restPositions.length/3);this.changedTriangles=[];this.lastDepth=0;
  for(let i=0;i<this.weights.length;i++){const[x,y,z]=this.restPositions.slice(i*3,i*3+3);if(Math.abs(x)>2.867||y<22.0||z<spec.user.freeZ-.001||z>spec.user.hingeZ+.001)continue;const t=THREE.MathUtils.clamp((spec.user.hingeZ-z)/(spec.user.hingeZ-spec.user.freeZ),0,1);this.weights[i]=t*t*(3-2*t);}
  for(let i=0;i<this.weights.length;i+=3)if(this.weights[i]||this.weights[i+1]||this.weights[i+2])this.changedTriangles.push(i);
  this.meta.deformedNativeVertices=this.weights.filter(w=>w>0).length;
 }
 update(dt){const changed=super.update(dt),depth=this.getActuationState().depthMm;if(depth===this.lastDepth)return changed;const p=this.shell.geometry.attributes.position,n=this.shell.geometry.attributes.normal;
  for(let i=0;i<this.weights.length;i++)if(this.weights[i])p.setY(i,this.restPositions[i*3+1]-depth*this.weights[i]);
  if(depth===0)n.array.set(this.restNormals);else{const a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3();for(const i of this.changedTriangles){a.fromBufferAttribute(p,i);b.fromBufferAttribute(p,i+1).sub(a);c.fromBufferAttribute(p,i+2).sub(a);b.cross(c).normalize();for(let j=0;j<3;j++)n.setXYZ(i+j,b.x,b.y,b.z);}}
  p.needsUpdate=true;n.needsUpdate=true;this.shell.geometry.computeBoundingBox();this.shell.geometry.computeBoundingSphere();this.follower.position.y=this.followerRest-depth;this.lastDepth=depth;return true;
 }
 dispose(){super.dispose();this.shell=null;this.follower=null;this.restPositions=null;this.restNormals=null;this.weights=null;this.changedTriangles=null;}
}
