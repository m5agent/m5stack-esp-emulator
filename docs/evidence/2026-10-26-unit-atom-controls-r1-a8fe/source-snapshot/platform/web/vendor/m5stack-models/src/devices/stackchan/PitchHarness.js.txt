import * as THREE from 'three';
import {Component,materials} from '../../core/index.js';

/** Product-local visual loom. Both real terminal frames constrain its endpoints;
 * an inferred slack S-bend keeps visual wire length stable across head pitch. */
export class PitchHarness extends Component{
 static kind='visual-harness';
 constructor({upper,lower,pitch,...rest}){
  super(rest);this.upper=upper;this.lower=lower;this.pitch=pitch;this.wires=[];this.previous='';this.targetLengths=[];
  for(let i=0;i<7;i++){const wire=new THREE.Mesh(new THREE.BufferGeometry(),materials.plastic(0x111b16,{roughness:.76}));wire.name=`Rear harness wire ${i+1}`;wire.userData.role='cross-pitch-harness';this.object3d.add(wire);this.wires.push(wire);}
 }
 curve(i,start,end,back,amplitude){
  const theta=THREE.MathUtils.degToRad(this.pitch.angleDeg),offset=(i-3)*.28;
  const p1=start.clone().addScaledVector(back,2.5),p4=end.clone().add(new THREE.Vector3(0,0,-.65));
  const p2=p1.clone().lerp(p4,.34).add(new THREE.Vector3(amplitude+offset,2.3*Math.cos(theta),0));
  const p3=p1.clone().lerp(p4,.72).add(new THREE.Vector3(-amplitude+offset,.8*Math.cos(theta),-.5));
  return new THREE.CatmullRomCurve3([start,p1,p2,p3,p4,end],false,'centripetal');
 }
 update(){
  this.host.root.updateMatrixWorld(true);
  const start=this.upper.contacts.map(o=>this.object3d.worldToLocal(o.getWorldPosition(new THREE.Vector3()))),end=this.lower.contacts.map(o=>this.object3d.worldToLocal(o.getWorldPosition(new THREE.Vector3())));
  const back=new THREE.Vector3(0,0,1).transformDirection(this.upper.matrixWorld).transformDirection(this.object3d.matrixWorld.clone().invert());
  const signature=[...start.flatMap(p=>p.toArray()),...end.flatMap(p=>p.toArray()),...back.toArray()].map(v=>v.toFixed(6)).join(',');if(signature===this.previous)return false;this.previous=signature;
  for(let i=0;i<7;i++){
   if(this.targetLengths[i]===undefined)this.targetLengths[i]=this.curve(i,start[i],end[i],back,1.8).getLength()+.3;
   let lo=0,hi=15,curve;for(let j=0;j<18;j++){const mid=(lo+hi)/2;curve=this.curve(i,start[i],end[i],back,mid);curve.getLength()<this.targetLengths[i]?lo=mid:hi=mid;}
   curve=this.curve(i,start[i],end[i],back,(lo+hi)/2);const geometry=new THREE.TubeGeometry(curve,64,.21,8,false);this.wires[i].geometry.dispose();this.wires[i].geometry=geometry;
   this.wires[i].userData.lengthMm=curve.getLength();this.wires[i].userData.targetLengthMm=this.targetLengths[i];
  }
  return true;
 }
 getState(){return {wireCount:7,lengthsMm:this.wires.map(w=>w.userData.lengthMm??null),targetLengthsMm:[...this.targetLengths],scope:'externally posed visual harness; slack route inferred, no cable physics or electrical behavior'};}
}
