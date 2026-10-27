import {Button} from '../../core/components/Button.js';

/** A stable toggle lever. Reuses Button sources/events and converts its
 * interpolation to rigid rotation around the switch pivot, without translation. */
export class ToggleButton extends Button{
 constructor({anglesDeg=[-22.5,22.5],leverRadiusMm=6.9,...options}){
  super({...options,latching:true,axis:[0,0,1],travel:leverRadiusMm*Math.abs(anglesDeg[1]-anglesDeg[0])*Math.PI/180});
  this.anglesDeg=[...anglesDeg];this.applyPose();
 }
 applyPose(){
  const amount=this.getActuationState().depthMm/this.travel;
  this.leverAngleDeg=this.anglesDeg[0]+(this.anglesDeg[1]-this.anglesDeg[0])*amount;
  this.cap.position.set(0,0,0);this.cap.rotation.y=this.leverAngleDeg*Math.PI/180;
 }
 setPosition(position,options={}){super.setPosition(position,options);if(options.immediate)this.applyPose();return this.getState();}
 update(dt){const changed=super.update(dt);this.applyPose();return changed;}
 getState(){return {...super.getState(),leverAngleDeg:this.leverAngleDeg,scope:'visual-only'};}
}
