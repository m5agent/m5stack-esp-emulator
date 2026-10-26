import * as THREE from 'three';
import {Component} from '../Component.js';

const finite=(value,name)=>{if(!Number.isFinite(value))throw new TypeError(`${name} must be finite`);return value;};

/** Externally driven geometry only. No motor, encoder, sensor or firmware model. */
export class VisualJoint extends Component {
  static kind='joint';

  constructor({axis=[0,0,1],limitsDeg=null,continuous=false,angleDeg=0,...rest}={}){
    super(rest);
    if(!Array.isArray(axis)||axis.length!==3||axis.some(v=>!Number.isFinite(v))||Math.hypot(...axis)===0)throw new TypeError('axis must be a finite nonzero vector');
    this.axis=new THREE.Vector3(...axis).normalize();
    if(limitsDeg!==null&&(!Array.isArray(limitsDeg)||limitsDeg.length!==2||limitsDeg.some(v=>!Number.isFinite(v))||limitsDeg[0]>limitsDeg[1]))throw new TypeError('limitsDeg must be [minimum, maximum] or null');
    if(continuous&&limitsDeg!==null)throw new TypeError('continuous rotation cannot have finite angle limits');
    this.limitsDeg=limitsDeg===null?null:[...limitsDeg];
    this.continuous=continuous;
    this.restQuaternion=this.object3d.quaternion.clone();
    this.angleDeg=0;this.rpm=0;this.transition=null;
    this.meta={...this.meta,role:'externally-driven-visual-joint',axis:this.axis.toArray(),angleUnit:'degree',continuous,limitsDeg:this.limitsDeg};
    this.set({angleDeg});
  }

  /** Mount first, then adopt neutral-pose objects while retaining their pose. */
  adopt(...objects){
    for(const object of objects){
      if(!object?.isObject3D)throw new TypeError('VisualJoint.adopt needs Object3D objects');
      for(let p=this.object3d;p;p=p.parent)if(p===object)throw new Error('A visual joint cannot adopt its own ancestor');
      this.object3d.attach(object);
    }
    this.requestRender();return this;
  }

  set({angleDeg,rpm,durationMs=0}={}){
    finite(durationMs,'durationMs');if(durationMs<0)throw new RangeError('durationMs must be >= 0');
    if(durationMs>0&&angleDeg===undefined)throw new TypeError('durationMs requires angleDeg');
    if(angleDeg!==undefined){finite(angleDeg,'angleDeg');if(this.limitsDeg&&(angleDeg<this.limitsDeg[0]||angleDeg>this.limitsDeg[1]))throw new RangeError(`angleDeg must be within ${this.limitsDeg.join('…')}`);}
    if(rpm!==undefined){finite(rpm,'rpm');if(rpm!==0&&!this.continuous)throw new RangeError('rpm is available only on explicitly continuous visual joints');}
    if(durationMs>0&&rpm!==undefined&&rpm!==0)throw new TypeError('An angle transition and continuous rpm cannot run together');
    if(angleDeg!==undefined){
      this.rpm=0;
      this.transition=durationMs>0&&angleDeg!==this.angleDeg?{from:this.angleDeg,to:angleDeg,duration:durationMs/1000,elapsed:0}:null;
      if(!this.transition){this.angleDeg=angleDeg;this.#apply();}
    }
    if(rpm!==undefined){this.rpm=rpm;if(angleDeg===undefined)this.transition=null;}
    this.requestRender();return this.getState();
  }

  setAngle(angleDeg,durationMs=0){return this.set({angleDeg,durationMs});}
  setRPM(rpm){return this.set({rpm});}

  #apply(){
    const turn=new THREE.Quaternion().setFromAxisAngle(this.axis,THREE.MathUtils.degToRad(this.angleDeg%360));
    this.object3d.quaternion.copy(this.restQuaternion).multiply(turn);
  }

  update(dt=0){
    finite(dt,'dt');if(dt<0)throw new RangeError('dt must be >= 0');
    if(this.transition){
      const t=this.transition;t.elapsed=Math.min(t.duration,t.elapsed+dt);
      this.angleDeg=t.from+(t.to-t.from)*(t.elapsed/t.duration);this.#apply();
      if(t.elapsed>=t.duration)this.transition=null;
      // The terminal frame still changed geometry. Return true once so an
      // on-demand viewer renders the exact destination before going idle.
      return true;
    }
    if(this.rpm!==0){
      const next=this.angleDeg+this.rpm*6*dt;finite(next,'integrated visual angle');
      this.angleDeg=next;this.#apply();return true;
    }
    return false;
  }

  handle(cmd){
    if(cmd.type==='joint')return this.set(cmd);
    if(cmd.type==='state')return this.getState();
    return super.handle(cmd);
  }

  getState(){return {angleDeg:this.angleDeg,targetAngleDeg:this.transition?.to??this.angleDeg,rpm:this.rpm,transitioning:this.transition!==null,mode:this.continuous?'continuous':'position',continuous:this.continuous,rangeDeg:this.limitsDeg===null?null:[...this.limitsDeg],visualRangeDeg:this.meta.visualRangeDeg??null,demoRpmMax:this.continuous?(this.meta.demoRpmMax??60):0};}
}
