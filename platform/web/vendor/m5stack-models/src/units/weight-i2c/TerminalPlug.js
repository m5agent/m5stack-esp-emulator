import * as THREE from 'three';
import {Module,VisualJoint,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {mesh,slab} from '../../modeling/parts.js';
import {spec} from './dimensions.js';

const physical=(parent,geometry,material,position,name)=>mesh(parent,geometry,material,position,`Weight-I2C plug ${name}`);

// An X/Z profile extruded towards -Y. Its bores remain real empty channels.
function crossSection(parent,{w,h,depth,y,z=0,holes=[],name,material}){
 const part=slab(parent,w,h,depth,.22,[0,y,z],material,holes.map(hole=>({...hole,cy:hole.cy-z})),.025);
 part.rotation.x=Math.PI/2;part.name=`Weight-I2C plug ${name}`;return part;
}

/** Supplied U180 HT3.96-4P accessory; physical appearance only. */
export class TerminalPlug extends Module{
 static meta={id:'m5stack.unit.weight-i2c.terminal-plug',name:'U180 removable 4P screw terminal',sku:'U180 accessory',connector:'ht3.96-4p'};
 build(){
  const frame=new THREE.Group();frame.name='Weight-I2C removable terminal plug assembly';this.body.add(frame);
  const plastic=materials.plastic(0xf49b39,{roughness:.67}),metal=materials.metal(0xb9bcb3,{roughness:.42}),inside=materials.metal(0x666e65,{roughness:.62});
  // U180's own package photograph confirms the orange four-pole plug,
  // round wire entries and recessed slotted screws. Its local dimensions
  // remain photo estimates. This is not a universal HT3.96 plug asset.
  // Keep the source fixed socket untouched and leave clearance around its
  // low channel ribs, roof and pins. The existing U180 Port is at Z 3.8,
  // so a local bore centre of -1.4 aligns its pins at chassis Z 2.4.
  // These are not rated fit tolerances.
  const bores=spec.terminal.pinX.map(cx=>({w:1.5,h:1,r:.12,cx,cy:-1.4}));
  const tongue=crossSection(frame,{w:14.1,h:4.55,depth:7.6,y:0,z:.225,holes:bores,name:'bored mating tongue',material:plastic});
  const rear=crossSection(frame,{w:16.3,h:5.75,depth:.8,y:.8,z:.875,holes:bores,name:'bored rear shoulder',material:plastic});
  const floor=slab(frame,16.3,10.5,.6,.22,[0,5.25,-2.6],plastic,[],.035);floor.name='Weight-I2C plug channel floor';
  const deck=slab(frame,16.3,9.7,.65,.22,[0,5.65,3.75],plastic,spec.terminal.pinX.map(cx=>({w:2.7,h:2.7,r:1.35,cx,cy:5.2-5.65})),.035);deck.name='Weight-I2C plug screw-access deck';
  for(const x of [-7.9,-3.96,0,3.96,7.9]){
   const width=Math.abs(x)>7?.5:.45;
   slab(frame,width,9.7,5.75,.09,[x,5.65,-2],plastic,[],.025).name='Weight-I2C plug channel partition';
  }
  const entry=crossSection(frame,{w:16.3,h:7,depth:.7,y:11.2,z:.9,holes:spec.terminal.pinX.map(cx=>({w:3.1,h:3.1,r:1.55,cx,cy:.35})),name:'four open wire entries',material:plastic});
  for(const [i,x]of spec.terminal.pinX.entries()){
   for(const side of [-1,1])physical(frame,new THREE.BoxGeometry(.14,9.44,.68),metal,[x+side*.55,-2.08,-1.4],'recessed mating spring');
   physical(frame,new THREE.BoxGeometry(2.9,.22,5.05),metal,[x,2.75,.745],'clamp rear web');
   physical(frame,new THREE.BoxGeometry(2.9,7.44,.22),metal,[x,6.58,-1.67],'clamp lower plate');
   for(const side of [-1,1])physical(frame,new THREE.BoxGeometry(.15,7.44,5.05),metal,[x+side*1.375,6.58,.745],'clamp cage side');
   physical(frame,new THREE.BoxGeometry(2.6,7.2,.2),metal,[x,6.58,2.95],'pressure plate');
   physical(frame,new THREE.CylinderGeometry(.4,.4,.75,32).rotateX(Math.PI/2),metal,[x,5.2,3.425],'screw shank');
   const head=new THREE.Group();head.name=`Weight-I2C ${spec.terminal.names[i]} slotted terminal screw`;
   physical(head,new THREE.CylinderGeometry(1.1,1.1,.1,48).rotateX(Math.PI/2),inside,[0,0,.05],'screw slot floor');
   const shape=new THREE.Shape();shape.absarc(0,0,1.1,0,Math.PI*2,false);shape.holes.push(roundedRect(1.8,.3,.05,{path:new THREE.Path(),clockwise:true}));
   physical(head,new THREE.ExtrudeGeometry(shape,{depth:.35,bevelEnabled:false,curveSegments:32}),metal,[0,0,.1],'slotted screw head');
   const joint=this.add(new VisualJoint({id:`screw-${i+1}`,label:`${spec.terminal.names[i]} screw visual angle`,position:[x,5.2,3.8],axis:[0,0,1],meta:{visualRangeDeg:[-180,180],rangeEvidence:'Viewer angle only; thread pitch, tightening limits and clamp displacement are unconfirmed',source:'Exact official U180 package photograph shows the supplied four screw-access holes and four wire entries',scope:'External visible screw-head angle only; no tightening, axial travel, clamp force, wiring, excitation, calibration or load-cell behavior'}}),frame);
   joint.object3d.add(head);joint.object3d.quaternion.setFromAxisAngle(new THREE.Vector3(0,0,1),[.29,-.43,.62,-.18][i]);joint.restQuaternion.copy(joint.object3d.quaternion);
  }
  this.terminalPlugAssembly={frame,tongue,rear,floor,deck,entry};
 }
}
