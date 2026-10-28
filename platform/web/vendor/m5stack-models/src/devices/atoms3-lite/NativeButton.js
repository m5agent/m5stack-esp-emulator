// MIT. C124 native U-tongues deform locally. Original face/index/attribute arrays are never partitioned.
import {Button} from '../../core/index.js';
import {THREE,FACE} from './geometry.js';
import {weightedInputHit} from '../../modeling/weighted-input.js';
const smooth=t=>{t=THREE.MathUtils.clamp(t,0,1);return t*t*(3-2*t);};
// The own C124 side U-slot opens upward; its continuous root is the -3.05357mm ledge.
// A linear hinge field keeps each coarse native inner/outer cross-section together.
const resetRoot=-3.053569793701172,resetTip=4.753570556640625;
const resetWeight=z=>THREE.MathUtils.clamp((z-resetRoot)/(resetTip-resetRoot),0,1);
export class NativeButton extends Button{
 constructor(shell,{id,label,face,position,travel,gpio}){
  const target=new THREE.Mesh(new THREE.PlaneGeometry(id==='button'?10.8:3.8,id==='button'?10:3.2),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false}));target.name='C124 '+id+' input-only native surface target';
  super({id,label,position,quaternion:FACE[face],mesh:target,travel,longPressMs:0,meta:{gpio,role:'visual-control',actuation:'native-flexure',surfaceFace:face,surfaceCenter:position,scope:'Input intention and inferred native cap flexure only;no reset/bootloader/electrical/firmware effect.',travelSource:'Own native/photo appearance estimate;not a rated mechanical travel.'}});
  this.shell=shell;this.rest=shell.geometry.attributes.position.array.slice();this.norm=shell.geometry.attributes.normal.array.slice();this.weights=new Float32Array(this.rest.length/3);this.lastDepth=0;this.followers=[];
  const shift=shell.position;
  for(let i=0;i<this.weights.length;i++){const x=this.rest[i*3]+shift.x,y=this.rest[i*3+1]+shift.y,z=this.rest[i*3+2]+shift.z;let w=0;if(id==='button'&&Math.abs(x)<5.8&&y>-4.8&&y<7.3&&z>3.25)w=smooth((7.3-y)/11.7);if(id==='reset'&&x<-9.35&&x>-12.01&&y>2.15&&y<6.85&&z>resetRoot&&z<=resetTip)w=resetWeight(z);this.weights[i]=w;}
  this.meta.movingNativeVertices=this.weights.filter(w=>w>0).length;
  this.hit(shell,intersection=>weightedInputHit(this,shell,intersection));
 }
 follow(object,axis,weight){this.followers.push({object,axis:new THREE.Vector3(...axis),rest:object.position.clone(),weight});return object;}
 weightAt(y,z){return this.id==='button'?smooth((7.3-y)/11.7):resetWeight(z);}
 update(dt){const changed=super.update(dt),d=this.getActuationState().depthMm;if(d===this.lastDepth)return changed;const p=this.shell.geometry.attributes.position,n=this.shell.geometry.attributes.normal;
  for(let i=0;i<this.weights.length;i++){const w=this.weights[i];if(!w)continue;const k=i*3;let x=this.rest[k],y=this.rest[k+1],z=this.rest[k+2],nx=this.norm[k],ny=this.norm[k+1],nz=this.norm[k+2];
   if(this.id==='button'){z-=d*w;const t=THREE.MathUtils.clamp((7.3-(y+this.shell.position.y))/11.7,0,1),slope=-6*t*(1-t)/11.7;ny+=d*slope*nz;}
   else{x+=d*w;nz-=d/(resetTip-resetRoot)*nx;}
   if(d){const length=Math.hypot(nx,ny,nz);nx/=length;ny/=length;nz/=length;}else{nx=this.norm[k];ny=this.norm[k+1];nz=this.norm[k+2];}
   p.setXYZ(i,x,y,z);n.setXYZ(i,nx,ny,nz);
  }
  p.needsUpdate=true;n.needsUpdate=true;this.shell.geometry.computeBoundingBox();this.shell.geometry.computeBoundingSphere();for(const f of this.followers)f.object.position.copy(f.rest).addScaledVector(f.axis,d*f.weight);this.lastDepth=d;return true;
 }
 dispose(){super.dispose();this.shell=null;this.rest=null;this.norm=null;this.weights=null;this.followers=[];}
}
