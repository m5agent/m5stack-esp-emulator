import * as THREE from 'three';
import {Module,VisualJoint,materials} from '../../core/index.js';
import {mesh,slab} from '../../modeling/parts.js';
import {spec} from './dimensions.js';

function section(parent,{w,h,depth,y,z=0,holes=[],name,material}){
 const m=slab(parent,w,h,depth,.15,[0,y,z],material,holes.map(h=>({...h,cy:h.cy-z})),.02);m.rotation.x=Math.PI/2;m.name='ExtEncoder plug '+name;return m;
}
/** Supplied green U161 five-pole screw plug, independently detachable. */
export class TerminalPlug extends Module{
 static meta={id:'m5stack.unit.extencoder.terminal-plug',name:'U161 supplied VH2.54-5P screw plug',sku:'U161 accessory',connector:'vh2.54-5p'};
 build(){
  const frame=new THREE.Group();frame.name='ExtEncoder supplied green five-pole plug';this.body.add(frame);
  const green=materials.plastic(0x4d9c68,{roughness:.68}),metal=materials.metal(0xb7b9ab,{roughness:.45}),inside=materials.metal(0x667268,{roughness:.66});
  const box=(name,size,p,m=green)=>mesh(frame,new THREE.BoxGeometry(...size),m,p,'ExtEncoder plug '+name);
  // The own U161 package photograph explicitly shows five slotted screws and
  // five round wire entries. Dimensions/clearance are photo-derived estimates.
  // Local origin is the fixed socket face, global Z2.4; the bore centre -1.2
  // aligns the real fixed contacts at chassis Z1.2, without moving the socket.
  const bores=spec.encoder.pinX.map(cx=>({w:1.04,h:1.04,r:.11,cx,cy:-1.2}));
  const tongue=section(frame,{w:12.8,h:3.6,depth:6.3,y:-.3,z:0,holes:bores,name:'five bored mating channels',material:green});
  const shoulder=section(frame,{w:14.5,h:5.5,depth:.7,y:.75,z:.75,holes:bores,name:'bored shoulder',material:green});
  const floor=slab(frame,14.5,7.7,.55,.2,[0,4.45,-2.05],green,[],.025);floor.name='ExtEncoder plug wire-channel floor';
  const deck=slab(frame,14.5,7.6,.65,.2,[0,4.5,3.9],green,spec.encoder.pinX.map(cx=>({w:1.85,h:1.85,r:.925,cx,cy:3.9-4.5})),.025);deck.name='ExtEncoder five actual screw-access bores';
  for(const x of[-7,-3.81,-1.27,1.27,3.81,7])box('wire channel partition',[Math.abs(x)>6?.5:.35,7.7,5.95],[x,4.45,.925]);
  const entry=section(frame,{w:14.5,h:6.5,depth:.65,y:8.95,z:1.2,holes:spec.encoder.pinX.map(cx=>({w:1.9,h:1.9,r:.95,cx,cy:.2})),name:'five true round wire entries',material:green});
  const springs=[],screws=[];
  for(const[i,x]of spec.encoder.pinX.entries()){
   for(const side of[-1,1])springs.push(box('recessed mating spring',[.12,7.0,.7],[x+side*.45,-2.0,-1.2],metal));
   box('clamp rear web',[1.8,.2,4.9],[x,1.25,.95],metal);
   box('clamp bottom plate',[1.8,6.7,.16],[x,4.6,-1.47],metal);
   for(const side of[-1,1])box('clamp cage side',[.12,6.7,4.9],[x+side*.84,4.6,.95],metal);
   box('pressure plate',[1.5,6.3,.16],[x,4.6,3.12],metal);
   mesh(frame,new THREE.CylinderGeometry(.29,.29,.8,28).rotateX(Math.PI/2),metal,[x,3.9,3.6],'ExtEncoder screw shank');
   const head=new THREE.Group();head.name=`ExtEncoder ${spec.encoder.names[i]} slotted screw head`;
   mesh(head,new THREE.CylinderGeometry(.75,.75,.08,48).rotateX(Math.PI/2),inside,[0,0,.04],'ExtEncoder slot physical floor');
   // Two circular segments create a real transverse slot with visible walls.
   for(const sign of[-1,1]){
    const shape=new THREE.Shape(),r=.75,t=.12,a=Math.asin(t/r);const start=sign>0?a:Math.PI+a,end=sign>0?Math.PI-a:Math.PI*2-a;
    shape.absarc(0,0,r,start,end,false);shape.closePath();
    mesh(head,new THREE.ExtrudeGeometry(shape,{depth:.28,bevelEnabled:false,curveSegments:28}),metal,[0,0,.08],'ExtEncoder slotted screw metal cheek');
   }
   const joint=this.add(new VisualJoint({id:`screw-${i+1}`,label:`${spec.encoder.names[i]} screw visual angle`,axis:[0,0,1],position:[x,3.9,4.12],meta:{visualRangeDeg:[-180,180],rangeEvidence:'Illustrative head angle only; thread pitch, torque and axial/clamp movement are unconfirmed',source:'Exact U161 official package photo shows a supplied five-screw plug with five round wire entries',scope:'External screw-head orientation only. No tightening, axial motion, clamp force, electrical continuity, excitation, AB/ABZ decoding, position, counting, speed or firmware behavior'}}),frame);
   joint.object3d.add(head);joint.object3d.quaternion.setFromAxisAngle(new THREE.Vector3(0,0,1),[.3,-.4,.15,-.25,.52][i]);joint.restQuaternion.copy(joint.object3d.quaternion);screws.push(joint);
  }
  frame.userData={role:'physical-connector-accessory',source:'Own U161 product/package photo',inferred:'Plug envelope, bores, contacts, cages, screw depth and installation clearance are visual estimates, not manufacturing fit.'};
  this.terminalPlugAssembly={frame,tongue,shoulder,floor,deck,entry,springs,screws};
 }
}
