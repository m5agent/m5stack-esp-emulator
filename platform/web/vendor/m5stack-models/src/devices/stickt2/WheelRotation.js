import * as THREE from 'three';
import {VisualJoint} from '../../core/index.js';
/** Own T2 encoder wheel rim input plus external visual command. No pulse/electrical model. */
export class WheelRotation extends VisualJoint{
 constructor({meshes,...options}){super({continuous:true,axis:[0,0,1],...options});this.drag=null;for(const mesh of meshes)this.hit(mesh);this.meta={...this.meta,role:'visual-rotary-input',scope:'Signed continuous angle intent; encoder pulses and firmware external'};}
 get interactive(){return true;}
 get cursor(){return 'grab';}
 angle(info){this.object3d.updateWorldMatrix(true,false);const origin=this.object3d.getWorldPosition(new THREE.Vector3()),normal=new THREE.Vector3(0,0,1).transformDirection(this.object3d.matrixWorld);let point=info.ray?.intersectPlane(new THREE.Plane().setFromNormalAndCoplanarPoint(normal,origin),new THREE.Vector3())??info.point?.clone();if(!point)return null;point=this.object3d.worldToLocal(point);if(Math.hypot(point.x,point.y)<1)return null;return Math.atan2(point.y,point.x)+THREE.MathUtils.degToRad(this.angleDeg);}
 onPointerDown(info){if(this.drag)return;const angle=this.angle(info);if(angle==null)return;this.set({rpm:0});this.drag={id:info.pointerId,angle};}
 onPointerMove(info){if(!this.drag||this.drag.id!==info.pointerId)return;const angle=this.angle(info);if(angle==null)return;let delta=angle-this.drag.angle;while(delta>Math.PI)delta-=2*Math.PI;while(delta<-Math.PI)delta+=2*Math.PI;this.drag.angle=angle;const deltaDeg=THREE.MathUtils.radToDeg(delta);if(Math.abs(deltaDeg)<1e-7)return;this.set({angleDeg:this.angleDeg+deltaDeg});this.input('rotate',{angleDeg:this.angleDeg,deltaDeg,source:'pointer'});}
 onPointerUp(info){if(this.drag?.id===info.pointerId)this.drag=null;}
 onPointerCancel(info){this.onPointerUp(info);}
 dispose(){this.drag=null;super.dispose();}
}
