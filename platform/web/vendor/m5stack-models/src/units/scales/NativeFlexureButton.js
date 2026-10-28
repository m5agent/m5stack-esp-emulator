import * as THREE from 'three';
import {Button} from '../../core/index.js';
import {spec} from './dimensions.js';

// Deform the original closed CAD tongue with zero travel at its hinge.
// No duplicate visible cap and no removed source triangles.
export class NativeFlexureButton extends Button{
 constructor(shell){
  const hit=new THREE.Mesh(new THREE.PlaneGeometry(6.2,8.6),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false}));
  hit.name='Scales native U-slot tare input surface';hit.position.z=.02;
  super({id:'tare',label:'Scales tare input intent',mesh:hit,position:spec.tare.position,axis:[0,0,-1],travel:spec.tare.travelMm,meta:{role:'visual-control',visualMotion:'native-flexure',surfaceCenter:spec.tare.position,surfaceFace:'front',travelSource:'0.20mm appearance estimate;actual native round U-cut pad flexes from retained-Y stem;no rated switch travel or material physics',scope:'input intent only; no automatic tare,zeroing,weight,RGB,power or firmware behavior'}});
  // The target is input geometry, not the visible tongue. Keep it 0.02 mm
  // outside the neutral surface for the entire press, so the native CAD face
  // cannot win a coplanar pick or occlude the target while the tongue flexes.
  this.object3d.add(hit);this.meta.inputTargetOffsetMm=.02;
  this.shell=shell;this.restPositions=shell.geometry.attributes.position.array.slice();this.restNormals=shell.geometry.attributes.normal.array.slice();this.weights=new Float32Array(this.restPositions.length/3);this.lastDepth=0;
  for(let i=0;i<this.weights.length;i++){const x=this.restPositions[i*3],y=this.restPositions[i*3+1],z=this.restPositions[i*3+2];if(z>=-15.101&&y>=spec.tare.hingeY&&y<=spec.tare.freeY&&((x+16)**2+(y+12)**2<=2.65**2||(Math.abs(x+16)<=1.7&&y<=-12)))this.weights[i]=THREE.MathUtils.clamp((y-spec.tare.hingeY)/(spec.tare.freeY-spec.tare.hingeY),0,1);}
  const index=shell.geometry.index.array,affected=new Set();
  for(let f=0;f<index.length;f+=3)if(this.weights[index[f]]||this.weights[index[f+1]]||this.weights[index[f+2]])for(let k=0;k<3;k++)affected.add(index[f+k]);
  this.normalVertices=Uint32Array.from(affected);this.normalMask=new Uint8Array(this.weights.length);for(const i of this.normalVertices)this.normalMask[i]=1;
  // Include unchanged incident faces when deriving the local rotation, while
  // retaining the original indexed crease groups. Never recalculate the rest
  // of the shell's CAD normals as an incidental effect of pressing the controller button.
  this.normalTriangles=[];for(let f=0;f<index.length;f+=3)if(this.normalMask[index[f]]||this.normalMask[index[f+1]]||this.normalMask[index[f+2]])this.normalTriangles.push(f);
  this.restNormalSums=new Float64Array(this.restPositions.length);this.currentNormalSums=new Float64Array(this.restPositions.length);this.normalScratch={from:new THREE.Vector3(),to:new THREE.Vector3(),normal:new THREE.Vector3(),rotation:new THREE.Quaternion()};
  this.sumLocalFaceNormals(this.restPositions,this.restNormalSums);
  this.meta.deformedNativeVertices=this.weights.filter(w=>w>0).length;
  this.meta.localNormalVertices=this.normalVertices.length;
 }
 sumLocalFaceNormals(positions,target){
  target.fill(0);const index=this.shell.geometry.index.array;
  for(const f of this.normalTriangles){const a=index[f]*3,b=index[f+1]*3,c=index[f+2]*3,ux=positions[c]-positions[b],uy=positions[c+1]-positions[b+1],uz=positions[c+2]-positions[b+2],vx=positions[a]-positions[b],vy=positions[a+1]-positions[b+1],vz=positions[a+2]-positions[b+2],nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx,length=Math.hypot(nx,ny,nz);if(!length)continue;for(let k=0;k<3;k++){const i=index[f+k];if(!this.normalMask[i])continue;target[i*3]+=nx/length;target[i*3+1]+=ny/length;target[i*3+2]+=nz/length;}}
 }
 syncLocalNormals(){
  this.sumLocalFaceNormals(this.shell.geometry.attributes.position.array,this.currentNormalSums);const attribute=this.shell.geometry.attributes.normal,{from,to,normal,rotation}=this.normalScratch;
  for(const i of this.normalVertices){const offset=i*3;from.fromArray(this.restNormalSums,offset);to.fromArray(this.currentNormalSums,offset);normal.fromArray(this.restNormals,offset);if(from.lengthSq()>1e-20&&to.lengthSq()>1e-20){from.normalize();to.normalize();if(from.distanceToSquared(to)>1e-24)normal.applyQuaternion(rotation.setFromUnitVectors(from,to));}attribute.setXYZ(i,normal.x,normal.y,normal.z);}attribute.needsUpdate=true;
 }
 update(dt){const changed=super.update(dt),depth=this.getActuationState().depthMm;if(depth!==this.lastDepth){const a=this.shell.geometry.attributes.position;for(let i=0;i<this.weights.length;i++)if(this.weights[i])a.setZ(i,this.restPositions[i*3+2]-depth*this.weights[i]);a.needsUpdate=true;if(depth===0){this.shell.geometry.attributes.normal.array.set(this.restNormals);this.shell.geometry.attributes.normal.needsUpdate=true;}else this.syncLocalNormals();this.shell.geometry.computeBoundingBox();this.shell.geometry.computeBoundingSphere();this.lastDepth=depth;}return changed;}
 dispose(){this.shell=null;this.restPositions=null;this.restNormals=null;this.weights=null;this.normalVertices=null;this.normalMask=null;this.normalTriangles=null;this.restNormalSums=null;this.currentNormalSums=null;this.normalScratch=null;super.dispose();}
}

