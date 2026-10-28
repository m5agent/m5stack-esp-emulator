import * as THREE from 'three';
import {Component} from '../../core/index.js';
const STEP=Math.PI/8,TAU=Math.PI*2,wrap=n=>(n%16+16)%16;
function position(n){if(!Number.isInteger(n)||n<0||n>15)throw new RangeError('selector position must be an integer from 0 to 15');return n;}
/** Physical 16-detent switch only. Commands never synthesize input intent. */
export class RotarySelector extends Component{
 static kind='rotary-selector';
 constructor({rotor,hitMeshes=[],position:pose,initialPosition=0,...rest}={}){super({...rest,position:pose});if(!rotor?.isObject3D)throw new TypeError('selector requires its own physical rotor');this.rotor=rotor;this.object3d.add(rotor);this._position=position(initialPosition);this._drag=null;for(const m of hitMeshes)this.hit(m);this._apply();}
 get interactive(){return true;}
 get cursor(){return 'grab';}
 _apply(){this.rotor.rotation.z=-this._position*STEP;this.requestRender();}
 setPosition(n){position(n);this._drag=null;this._position=n;this._apply();return this;}
 getState(){return{position:this._position,positions:16};}
 handle(cmd){if(cmd.type==='selector'){this.setPosition(cmd.position);return this.getState();}return super.handle(cmd);}
 _angle(info){this.object3d.updateWorldMatrix(true,false);let p;if(typeof info?.ray?.intersectPlane==='function'){const origin=this.object3d.getWorldPosition(new THREE.Vector3()),normal=new THREE.Vector3(0,0,1).transformDirection(this.object3d.matrixWorld),plane=new THREE.Plane().setFromNormalAndCoplanarPoint(normal,origin);p=info.ray.intersectPlane(plane,new THREE.Vector3());}else if(info?.point?.isVector3)p=info.point.clone();if(!p)return null;this.object3d.worldToLocal(p);if(!Number.isFinite(p.x)||!Number.isFinite(p.y)||p.x*p.x+p.y*p.y<.04)return null;return Math.atan2(p.y,p.x);}
 onPointerDown(info){if(this._drag)return;const angle=this._angle(info);if(angle==null)return;this._drag={pointerId:info.pointerId,angle,total:0,start:this._position};}
 onPointerMove(info){const d=this._drag;if(!d||d.pointerId!==info.pointerId)return;const a=this._angle(info);if(a==null)return;let delta=a-d.angle;while(delta>Math.PI)delta-=TAU;while(delta<-Math.PI)delta+=TAU;d.angle=a;d.total-=delta;const offset=Math.round(d.total/STEP),next=wrap(d.start+offset);if(next===this._position)return;const previousPosition=this._position;let step=next-previousPosition;if(step>8)step-=16;if(step<-8)step+=16;this._position=next;this._apply();this.input('change',{position:next,previousPosition,delta:step,source:'pointer'});}
 onPointerUp(info){if(this._drag&&this._drag.pointerId===info?.pointerId)this._drag=null;}
 onPointerCancel(info){this.onPointerUp(info);}
 dispose(){this._drag=null;super.dispose();}
}
