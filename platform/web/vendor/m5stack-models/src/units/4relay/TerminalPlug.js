import * as THREE from 'three';
import {Module,VisualJoint,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {mesh,slab} from '../../modeling/parts.js';
import {spec} from './dimensions.js';

/** U097 supplied front-inserted 4P accessory; appearance and screw angle only. */
export class TerminalPlug extends Module{
 static meta={id:'m5stack.unit.4relay.terminal-plug',name:'U097 removable 4P screw terminal',sku:'U097 accessory',connector:'ht3.96-4p'};
 build(){
  const frame=new THREE.Group();frame.name='4Relay removable terminal plug';this.body.add(frame);
  const plastic=materials.plastic(0xf38c37,{roughness:.65}),metal=materials.metal(0xb7baae,{roughness:.44}),inside=materials.metal(0x667064,{roughness:.6});
  // Port +Y follows the actual socket's front normal (+Z of the Unit).
  // Local +Z points toward the Unit's lower end and the wire entry mouths.
  // Walls, clamp details and insertion depth are exact-product photo estimates.
  const layer=(w,h,depth,y,z,holes,name)=>{const part=slab(frame,w,h,depth,.2,[0,y,z],plastic,holes,.025);part.rotation.x=-Math.PI/2;part.name='4Relay plug '+name;return part;};
  const bores=spec.terminal.pinX.map(cx=>({w:1.3,h:1.3,r:.35,cx,cy:0}));
  const tongue=layer(14.5,5.8,3.65,-3.7,0,bores,'four bored mating channels');
  const shoulder=layer(16.3,7.7,.6,0,0,bores,'shoulder with pin bores');
  const screwHoles=spec.terminal.pinX.map(cx=>({w:2.7,h:2.7,r:1.35,cx,cy:-.55}));
  const deck=layer(16.3,7.7,.65,4.6,0,screwHoles,'four screw access bores');
  for(const x of[-7.9,-3.96,0,3.96,7.9])mesh(frame,new THREE.BoxGeometry(Math.abs(x)>7?.5:.42,4.05,7.7),plastic,[x,2.625,0],'4Relay plug channel partition');
  mesh(frame,new THREE.BoxGeometry(15.3,4.05,.55),plastic,[0,2.625,-3.575],'4Relay plug rear wall');
  const entries=spec.terminal.pinX.map(cx=>({w:2.9,h:2.65,r:.5,cx,cy:2.5}));
  const entry=slab(frame,16.3,4.65,.55,.2,[0,2.625,3.575],plastic,entries.map(h=>({...h,cy:h.cy-2.625})),.025);entry.name='4Relay plug four open wire entries';
  for(const[i,x]of spec.terminal.pinX.entries()){
   for(const sign of[-1,1])mesh(frame,new THREE.BoxGeometry(.15,3.4,.65),metal,[x+sign*.48,-1.65,0],'4Relay plug recessed mating spring');
   mesh(frame,new THREE.BoxGeometry(2.8,.18,5.8),metal,[x,.93,.3],'4Relay plug clamp floor');
   for(const sign of[-1,1])mesh(frame,new THREE.BoxGeometry(.14,2.9,5.8),metal,[x+sign*1.33,2.3,.3],'4Relay plug clamp side');
   mesh(frame,new THREE.BoxGeometry(2.8,2.9,.18),metal,[x,2.3,-2.5],'4Relay plug clamp rear');
   mesh(frame,new THREE.BoxGeometry(2.65,.18,5.45),metal,[x,3.72,.3],'4Relay plug pressure plate');
   mesh(frame,new THREE.CylinderGeometry(.4,.4,.55,24),metal,[x,4.08,.55],'4Relay plug screw shank');
   const head=new THREE.Group();head.name=`4Relay plug screw ${i+1}`;
   mesh(head,new THREE.CylinderGeometry(1.08,1.08,.1,40),inside,[0,.05,0],'4Relay plug slot floor');
   const shape=new THREE.Shape();shape.absarc(0,0,1.08,0,Math.PI*2,false);shape.holes.push(roundedRect(1.75,.28,.04,{path:new THREE.Path(),clockwise:true}));
   mesh(head,new THREE.ExtrudeGeometry(shape,{depth:.32,bevelEnabled:false,curveSegments:32}).rotateX(-Math.PI/2),metal,[0,.1,0],'4Relay plug slotted screw head');
   const joint=this.add(new VisualJoint({id:`screw-${i+1}`,label:`Terminal screw ${i+1} visual angle`,position:[x,4.35,.55],axis:[0,1,0],meta:{role:'externally-driven-visual',visualRangeDeg:[-180,180],rangeEvidence:'Visible head angle only; thread, torque and clamp displacement are unconfirmed',scope:'External head rotation only; no tightening, axial displacement, wiring, force or electrical response'}}),frame);joint.object3d.add(head);joint.object3d.rotation.y=[.22,-.31,.53,-.14][i];joint.restQuaternion.copy(joint.object3d.quaternion);
  }
  this.terminalPlugAssembly={frame,tongue,shoulder,deck,entry};
 }
}
