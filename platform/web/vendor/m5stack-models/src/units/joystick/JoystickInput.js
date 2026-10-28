/** MIT; originalU024 physicalXY input andvisualpose only. */
import * as THREE from'three';import{Component,Button}from'../../core/index.js';
export class JoystickTilt extends Component{
 static kind='joystick';
 constructor(){super({id:'stick',label:'OriginalU024 XY stick',position:[0,8,10.4],meta:{role:'physical-XY-input-and-external-visual-pose',visualRangeDeg:[-16,16],pivotMm:[0,8,10.4],rangeEvidence:'Ownphoto reconstruction/viewerbound,notratedhardstop',scope:'Angles/inputintent only;noADC/I2C/potentiometer/firmware'}});this.xDeg=0;this.yDeg=0;this.transition=null;this.sources=new Map();this.drags=new Map();}
 validate(x,y){if(!Number.isFinite(x)||!Number.isFinite(y)||Math.abs(x)>16||Math.abs(y)>16)throw new RangeError('xDeg/yDeg must be finite within[-16,16]');}
 apply(){this.object3d.rotation.set(THREE.MathUtils.degToRad(this.xDeg),THREE.MathUtils.degToRad(this.yDeg),0,'XYZ');this.requestRender();}
 set({xDeg=this.xDeg,yDeg=this.yDeg,durationMs=0}={}){this.validate(xDeg,yDeg);if(!Number.isFinite(durationMs)||durationMs<0)throw new RangeError('durationMs must be finite>=0');this.transition=durationMs>0&&(xDeg!==this.xDeg||yDeg!==this.yDeg)?{x:this.xDeg,y:this.yDeg,toX:xDeg,toY:yDeg,duration:durationMs/1000,elapsed:0}:null;if(!this.transition){this.xDeg=xDeg;this.yDeg=yDeg;this.apply();}this.requestRender();return this.getState();}
 move(source='sim',xDeg=0,yDeg=0){this.validate(xDeg,yDeg);if(typeof source!=='string'||!source)throw new TypeError('source must be nonemptystring');const first=!this.sources.has(source);this.sources.delete(source);this.sources.set(source,{xDeg,yDeg});if(first)this.input('start',{source});this.set({xDeg,yDeg});this.input('change',{source,xDeg,yDeg});return this.getState();}
 release(source='sim',cancelled=false){if(!this.sources.delete(source))return this.getState();const last=[...this.sources.values()].at(-1)??{xDeg:0,yDeg:0};this.set({...last,durationMs:100});this.input('end',{source,cancelled,targetXDeg:last.xDeg,targetYDeg:last.yDeg});return this.getState();}
 point(info){const frame=this.object3d.parent;frame.updateWorldMatrix(true,false);const inverse=frame.matrixWorld.clone().invert();if(info.ray){const ray=info.ray.clone().applyMatrix4(inverse),p=new THREE.Vector3();return ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0,0,1),-27),p);}if(info.point)return info.point.clone().applyMatrix4(inverse);return null;}
 pointerDown(info){const source=`pointer:${info.pointerId}`,p=this.point(info);this.drags.set(info.pointerId,{point:p,xDeg:this.xDeg,yDeg:this.yDeg});this.move(source,this.xDeg,this.yDeg);}
 pointerMove(info){const d=this.drags.get(info.pointerId),p=this.point(info);if(!d||!p||!d.point)return;const clamp=x=>Math.max(-16,Math.min(16,x));this.move(`pointer:${info.pointerId}`,clamp(d.xDeg-THREE.MathUtils.radToDeg(Math.atan((p.y-d.point.y)/17))),clamp(d.yDeg+THREE.MathUtils.radToDeg(Math.atan((p.x-d.point.x)/17))));}
 pointerUp(info,cancelled=false){this.drags.delete(info.pointerId);return this.release(`pointer:${info.pointerId}`,cancelled);}
 update(dt=0){if(!Number.isFinite(dt)||dt<0)throw new RangeError('dt must be finite>=0');if(!this.transition)return false;const t=this.transition;t.elapsed=Math.min(t.duration,t.elapsed+dt);const f=t.elapsed/t.duration;this.xDeg=t.x+(t.toX-t.x)*f;this.yDeg=t.y+(t.toY-t.y)*f;this.apply();if(t.elapsed>=t.duration)this.transition=null;return true;}
 handle(cmd){if(cmd.type!=='joystick')return super.handle(cmd);const action=cmd.action??'set';if(action==='set')return this.set(cmd);if(action==='center')return this.set({xDeg:0,yDeg:0,durationMs:cmd.durationMs??100});if(action==='move')return this.move(cmd.source??'sim',cmd.xDeg,cmd.yDeg);if(action==='release'||action==='cancel')return this.release(cmd.source??'sim',action==='cancel');if(action==='state')return this.getState();throw new Error('Unknownjoystickaction');}
 getState(){return{xDeg:this.xDeg,yDeg:this.yDeg,targetXDeg:this.transition?.toX??this.xDeg,targetYDeg:this.transition?.toY??this.yDeg,transitioning:this.transition!==null,activeSources:[...this.sources.keys()],visualRangeDeg:[-16,16]};}
 dispose(){this.sources.clear();this.drags.clear();super.dispose();}
}
/** Actualthumbsurface belongs toZButton;normalpointerXY,ShiftaddsindependentZ. */
export class JoystickPress extends Button{
 constructor(tilt,options){super(options);this.tilt=tilt;}
 onPointerDown(info){this.tilt.pointerDown(info);if(info.event?.shiftKey)super.onPointerDown(info);}
 onPointerMove(info){this.tilt.pointerMove(info);}
 onPointerUp(info){super.onPointerUp(info);this.tilt.pointerUp(info,false);}
 onPointerCancel(info){super.onPointerCancel(info);this.tilt.pointerUp(info,true);}
}
