import {Button} from '../../core/components/Button.js';

/** Product-local articulated lever; keeps Button's input and multi-source semantics. */
export class LeverButton extends Button{
 constructor({lever,plunger,...options}){
  super({...options,axis:[0,-1,0],travel:lever.contactTravelMm});
  this.lever=lever;this.plunger=plunger;
  this.restPlungerY=plunger.position.y;
  this.angleDeg=lever.restAngleDeg;
  this.applyPose(0);
 }
 applyPose(amount){
  this.angleDeg=this.lever.restAngleDeg+(this.lever.pressedAngleDeg-this.lever.restAngleDeg)*amount;
  this.cap.position.set(0,0,0);
  this.cap.rotation.z=this.angleDeg*Math.PI/180;
  const restContact=this.lever.contactX*Math.sin(this.lever.restAngleDeg*Math.PI/180);
  const contact=this.lever.contactX*Math.sin(this.cap.rotation.z);
  this.plunger.position.y=this.restPlungerY+contact-restContact;
 }
 update(dt){
  const changed=super.update(dt);
  // Button interpolates its private travel depth. Convert that depth to a rigid
  // hinge rotation, then clear the temporary translation on the metal lever.
  const amount=this.getActuationState().depthMm/this.travel;
  this.applyPose(amount);
  return changed;
 }
 getState(){return {...super.getState(),leverAngleDeg:this.angleDeg,scope:'visual-only'};}
}
