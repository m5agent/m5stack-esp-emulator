import * as THREE from 'three';
import {Component} from '../Component.js';

const finite=(value,name)=>{if(!Number.isFinite(value))throw new TypeError(`${name} must be finite`);return value;};

/** A physical cap translated in millimetres. No ADC, sensor or firmware state. */
export class VisualSlide extends Component {
 static kind='slider';

 constructor({mesh,axis=[0,1,0],rangeMm=[0,35],positionMm=0,...rest}={}){
  super(rest);
  if(!Array.isArray(axis)||axis.length!==3||axis.some(v=>!Number.isFinite(v))||Math.hypot(...axis)===0)throw new TypeError('axis must be a finite nonzero vector');
  if(!Array.isArray(rangeMm)||rangeMm.length!==2||rangeMm.some(v=>!Number.isFinite(v))||rangeMm[0]>=rangeMm[1])throw new TypeError('rangeMm must be [minimum, maximum] with positive travel');
  this.axis=new THREE.Vector3(...axis).normalize();this.rangeMm=[...rangeMm];
  this.cap=new THREE.Group();this.cap.name='Sliding physical cap';this.object3d.add(this.cap);
  if(mesh){this.cap.add(mesh);mesh.traverse(o=>{if(o.isMesh)this.hit(o);});}
  this.positionMm=0;this.transition=null;this.drag=null;
  this.meta={...this.meta,role:'externally-driven-visual-slide',axis:this.axis.toArray(),positionUnit:'mm',rangeMm:[...this.rangeMm]};
  this.set({positionMm});
 }

 get interactive(){return true;}
 get cursor(){return 'grab';}

 /** External commands update geometry without emitting input intent. */
 set({positionMm,durationMs=0}={}){
  finite(durationMs,'durationMs');if(durationMs<0)throw new RangeError('durationMs must be >= 0');
  if(durationMs>0&&positionMm===undefined)throw new TypeError('durationMs requires positionMm');
  if(positionMm!==undefined){
   finite(positionMm,'positionMm');
   if(positionMm<this.rangeMm[0]||positionMm>this.rangeMm[1])throw new RangeError(`positionMm must be within ${this.rangeMm.join('…')}`);
   this.transition=durationMs>0&&positionMm!==this.positionMm?{from:this.positionMm,to:positionMm,duration:durationMs/1000,elapsed:0}:null;
   if(!this.transition){this.positionMm=positionMm;this.#apply();}
   this.requestRender();
  }
  return this.getState();
 }

 #apply(){this.cap.position.copy(this.axis).multiplyScalar(this.positionMm);}

 update(dt=0){
  finite(dt,'dt');if(dt<0)throw new RangeError('dt must be >= 0');
  if(!this.transition)return false;
  const t=this.transition;t.elapsed=Math.min(t.duration,t.elapsed+dt);
  this.positionMm=t.from+(t.to-t.from)*(t.elapsed/t.duration);this.#apply();
  if(t.elapsed>=t.duration)this.transition=null;
  return true;
 }

 #localRay(ray){
  if(!(ray instanceof THREE.Ray))return null;
  this.object3d.updateWorldMatrix(true,false);
  return ray.clone().applyMatrix4(this.object3d.matrixWorld.clone().invert());
 }

 onPointerDown({pointerId,point,intersection,ray}={}){
  if(this.drag)return;
  const localRay=this.#localRay(ray),worldPoint=point??intersection?.point;
  if(!localRay||!worldPoint?.isVector3)return;
  const normal=localRay.direction.clone().addScaledVector(this.axis,-localRay.direction.dot(this.axis));
  if(normal.lengthSq()<1e-10)return; // Looking straight along the slide cannot resolve its travel.
  const localPoint=this.object3d.worldToLocal(worldPoint.clone());
  const plane=new THREE.Plane().setFromNormalAndCoplanarPoint(normal.normalize(),localPoint);
  this.transition=null;
  this.drag={pointerId,plane,offset:localPoint.dot(this.axis)-this.positionMm};
  this.input('start',{pointerId,positionMm:this.positionMm});this.requestRender();
 }

 onPointerMove({pointerId,ray}={}){
  if(!this.drag||pointerId!==this.drag.pointerId)return;
  const localRay=this.#localRay(ray),point=localRay?.intersectPlane(this.drag.plane,new THREE.Vector3());
  if(!point)return;
  const positionMm=THREE.MathUtils.clamp(point.dot(this.axis)-this.drag.offset,...this.rangeMm);
  if(positionMm===this.positionMm)return;
  this.set({positionMm});this.input('position',{pointerId,positionMm});
 }

 #finish(pointerId,cancelled){
  if(!this.drag||pointerId!==this.drag.pointerId)return;
  this.drag=null;this.input('end',{pointerId,positionMm:this.positionMm,...(cancelled?{cancelled:true}:{})});this.requestRender();
 }
 onPointerUp({pointerId}={}){this.#finish(pointerId,false);}
 onPointerCancel({pointerId}={}){this.#finish(pointerId,true);}

 handle(cmd){
  if(cmd.type==='slider')return this.set(cmd);
  if(cmd.type==='state')return this.getState();
  return super.handle(cmd);
 }

 getState(){return {positionMm:this.positionMm,targetPositionMm:this.transition?.to??this.positionMm,rangeMm:[...this.rangeMm],transitioning:this.transition!==null,dragging:this.drag!==null};}
 dispose(){if(this.drag)this.#finish(this.drag.pointerId,true);super.dispose();}
}
