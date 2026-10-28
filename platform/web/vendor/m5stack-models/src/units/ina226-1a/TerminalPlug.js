import * as THREE from 'three';
import {Module,VisualJoint,materials} from '../../core/index.js';
import {mesh,slab} from '../../modeling/parts.js';
import {spec} from './dimensions.js';


const physical=(parent,geometry,material,position,name)=>mesh(parent,geometry,material,position,`INA226-1A plug ${name}`);

// An X/Z profile extruded towards -Y. Its bores remain real empty channels.
function crossSection(parent,{w,h,depth,y,z=0,holes=[],name,material}){
 const part=slab(parent,w,h,depth,.22,[0,y,z],material,holes.map(hole=>({...hole,cy:hole.cy-z})),.025);
 part.rotation.x=Math.PI/2;part.name=`INA226-1A plug ${name}`;return part;
}

/** Supplied U200-1A HT3.96-4P accessory; physical appearance only. */
export class TerminalPlug extends Module{
 static meta={id:'m5stack.unit.ina226-1a.terminal-plug',name:'U200-1A removable 4P screw terminal',sku:'U200-1A accessory',connector:'ht3.96-4p'};
 build(options={}){
  const frame=new THREE.Group();frame.name='INA226-1A removable terminal plug assembly';this.body.add(frame);
  const plastic=materials.plastic(0xf29a47,{roughness:.67}),metal=materials.metal(0xb9bcb3,{roughness:.42}),inside=materials.metal(0x666e65,{roughness:.62});
  // U200-1A's own package photograph confirms the orange four-pole plug,
  // round wire entries and recessed cross-recess screws. Its local dimensions
  // remain own-model photo estimates. This U200-1A-specific accessory is not a universal HT3.96 plug asset.
  // Mating tongue remains above the native front shell and within the
  // exact model's inferred exposed socket channel. Socket/plug insertion
  // depths are appearance reconstruction, not production connector CAD.
  // These are not rated fit tolerances.
  const bores=spec.terminal.pinX.map(cx=>({w:1.5,h:1,r:.12,cx,cy:-.5}));
  const tongue=crossSection(frame,{w:14.1,h:2.9,depth:7.6,y:0,z:.225,holes:bores,name:'bored mating tongue',material:plastic});
  const rear=crossSection(frame,{w:16.3,h:5.75,depth:.8,y:.8,z:.875,holes:bores,name:'bored rear shoulder',material:plastic});
  const floor=slab(frame,16.3,10.5,.6,.22,[0,5.25,-2.6],plastic,[],.035);floor.name='INA226-1A plug channel floor';
  const deck=slab(frame,16.3,9.7,.65,.22,[0,5.65,3.75],plastic,spec.terminal.pinX.map(cx=>({w:2.7,h:2.7,r:1.35,cx,cy:5.2-5.65})),.035);deck.name='INA226-1A plug screw-access deck';
  for(const x of [-7.9,-3.96,0,3.96,7.9]){
   const width=Math.abs(x)>7?.5:.45;
   slab(frame,width,9.7,5.75,.09,[x,5.65,-2],plastic,[],.025).name='INA226-1A plug channel partition';
  }
  const entry=crossSection(frame,{w:16.3,h:7,depth:.7,y:11.2,z:.9,holes:spec.terminal.pinX.map(cx=>({w:3.1,h:3.1,r:1.55,cx,cy:.35})),name:'four open wire entries',material:plastic});
  for(const [i,x]of spec.terminal.pinX.entries()){
   for(const side of [-1,1])physical(frame,new THREE.BoxGeometry(.14,9.44,.68),metal,[x+side*.55,-2.08,-.5],'recessed mating spring');
   physical(frame,new THREE.BoxGeometry(2.9,.22,5.05),metal,[x,2.75,.745],'clamp rear web');
   physical(frame,new THREE.BoxGeometry(2.9,7.44,.22),metal,[x,6.58,-1.67],'clamp lower plate');
   for(const side of [-1,1])physical(frame,new THREE.BoxGeometry(.15,7.44,5.05),metal,[x+side*1.375,6.58,.745],'clamp cage side');
   physical(frame,new THREE.BoxGeometry(2.6,7.2,.2),metal,[x,6.58,2.95],'pressure plate');
   physical(frame,new THREE.CylinderGeometry(.4,.4,.75,32).rotateX(Math.PI/2),metal,[x,5.2,3.425],'screw shank');
   const head=new THREE.Group();head.name=`INA226-1A ${spec.terminal.names[i]} cross-recess terminal screw`;
   physical(head,new THREE.CylinderGeometry(1.1,1.1,.1,48).rotateX(Math.PI/2),inside,[0,0,.05],'screw slot floor');
   const shape=new THREE.Shape();shape.absarc(0,0,1.1,0,Math.PI*2,false);const recess=new THREE.Path(),l=.83,t=.15,points=[[-t,-l],[t,-l],[t,-t],[l,-t],[l,t],[t,t],[t,l],[-t,l],[-t,t],[-l,t],[-l,-t],[-t,-t]].reverse();points.forEach(([a,b],i)=>i?recess.lineTo(a,b):recess.moveTo(a,b));recess.closePath();shape.holes.push(recess);
   physical(head,new THREE.ExtrudeGeometry(shape,{depth:.35,bevelEnabled:false,curveSegments:32}),metal,[0,0,.1],'cross-recess screw head');
   const joint=this.add(new VisualJoint({id:`screw-${i+1}`,label:`${spec.terminal.names[i]} screw visual angle`,position:[x,5.2,3.8],axis:[0,0,1],meta:{visualRangeDeg:[-180,180],rangeEvidence:'Viewer angle only; thread pitch, tightening limits and clamp displacement are unconfirmed',source:'Exact official U200-1A package photograph shows the supplied four screw-access holes and four wire entries',scope:'External visible screw-head angle only; no tightening, axial travel, clamp force, wiring, electrical,  voltage, current, power, calibration, metering or firmware behavior'}}),frame);
   joint.object3d.add(head);joint.object3d.quaternion.setFromAxisAngle(new THREE.Vector3(0,0,1),[.29,-.43,.62,-.18][i]);joint.restQuaternion.copy(joint.object3d.quaternion);
  }
  this.terminalPlugAssembly={frame,tongue,rear,floor,deck,entry};
 }
}
