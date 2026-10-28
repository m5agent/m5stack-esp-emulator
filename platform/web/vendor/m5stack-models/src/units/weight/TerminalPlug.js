import * as THREE from 'three';
import {Module,VisualJoint,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {mesh,slab} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
/** Product-specific appearance estimate from the exact U030 package photograph. */
export class TerminalPlug extends Module{
 static meta={id:'m5stack.unit.weight.terminal-plug',name:'Unit Weight U030 supplied four-screw terminal',sku:'U030 accessory',connector:'ht3.96-4p'};
 build(){
  const frame=new THREE.Group();frame.name='Weight own U030 supplied removable HT3.96-4P terminal';this.body.add(frame);const orange=materials.plastic(0xf59045,{roughness:.7}),metal=materials.metal(0xb9b8a7,{roughness:.45}),dark=materials.metal(0x737b70,{roughness:.6}),s=spec.plug;
  const profile=({w,h,y,z,depth,holes,name})=>{const o=slab(frame,w,h,depth,.18,[0,y,z],orange,holes,0);o.rotation.x=Math.PI/2;o.name='Weight plug '+name;return o;};
  const bores=spec.terminal.pinX.map(cx=>({w:s.pinBoreMm[0],h:s.pinBoreMm[1],r:.1,cx,cy:-1.175}));
  const tongue=profile({w:14,h:5.15,y:0,z:1.175,depth:s.insertionDepthMm,holes:bores,name:'mating tongue with four true pin bores'});
  const shoulder=profile({w:16.4,h:6.55,y:.9,z:1.325,depth:.8,holes:spec.terminal.pinX.map(cx=>({w:1.25,h:1.25,r:.1,cx,cy:-1.325})),name:'rear shoulder with four true pin bores'});
  const floor=slab(frame,16.4,9.2,.55,.18,[0,5.5,-1.95],orange,[],0);floor.name='Weight plug actual channel floor';
  const deck=slab(frame,16.4,9.2,.65,.18,[0,5.5,4.6],orange,spec.terminal.pinX.map(cx=>({w:2.65,h:2.65,r:1.325,cx,cy:s.screwY-5.5})),0);deck.name='Weight plug actual four through screw-access deck';
  const partitions=[];for(const x of[-7.95,-3.96,0,3.96,7.95]){const o=slab(frame,Math.abs(x)>7?.5:.42,9.2,6,.07,[x,5.5,-1.4],orange,[],0);o.name='Weight plug real separating wall';partitions.push(o);}
  const entry=profile({w:16.4,h:7.2,y:10.8,z:1.65,depth:.7,holes:spec.terminal.pinX.map(cx=>({w:3.1,h:3.1,r:1.55,cx,cy:.2-1.65})),name:'front face with four true wire-entry bores'}),springs=[],cages=[],shanks=[],heads=[],joints=[];
  for(const[i,x]of spec.terminal.pinX.entries()){
   for(const side of[-1,1])springs.push(mesh(frame,new THREE.BoxGeometry(.13,8.4,.68),metal,[x+side*.5,-3.2,0],'Weight plug recessed actual mating spring'));
   cages.push(mesh(frame,new THREE.BoxGeometry(2.75,.2,4.25),metal,[x,2.1,.975],'Weight plug fixed clamp rear web'));cages.push(mesh(frame,new THREE.BoxGeometry(2.75,7.55,.2),metal,[x,6.025,-1.25],'Weight plug fixed lower clamp plate'));
   for(const side of[-1,1])cages.push(mesh(frame,new THREE.BoxGeometry(.15,7.55,4.25),metal,[x+side*1.3,6.025,.975],'Weight plug fixed clamp cage side'));
   cages.push(mesh(frame,new THREE.BoxGeometry(2.55,7,.2),metal,[x,6,2.9],'Weight plug fixed pressure plate,no simulated clamping'));
   shanks.push(mesh(frame,new THREE.CylinderGeometry(.4,.4,1.65,32).rotateX(Math.PI/2),metal,[x,s.screwY,3.825],'Weight plug retained fixed screw shank'));
   const joint=this.add(new VisualJoint({id:'screw-'+(i+1),label:spec.terminal.names[i]+' terminal screw head visual angle',axis:[0,0,1],position:[x,s.screwY,4.65],meta:{visualRangeDeg:[-180,180],rangeEvidence:'Viewer interval only; actual thread pitch,tightening limits,axial travel and clamp force are unconfirmed.',source:'Exact U030 official package photograph proves four recessed screw heads and separate removable plug.',scope:'External head angle/interpolation only; fixed shank,cage,socket and labels remain fixed. No mechanical clamp,electrical,calibration or firmware model.'}}),frame);
   const head=new THREE.Group();head.name='Weight plug '+spec.terminal.names[i]+' actual slotted screw head';joint.object3d.add(head);
   mesh(head,new THREE.CylinderGeometry(1.05,1.05,.12,48).rotateX(Math.PI/2),dark,[0,0,.06],'Weight plug actual recessed screw slot floor');const shape=new THREE.Shape();shape.absarc(0,0,1.05,0,Math.PI*2,false);shape.holes.push(roundedRect(1.75,.28,.04,{path:new THREE.Path()}));mesh(head,new THREE.ExtrudeGeometry(shape,{depth:.33,bevelEnabled:false,curveSegments:32}),metal,[0,0,.12],'Weight plug real slotted screw head rim');joint.object3d.quaternion.setFromAxisAngle(new THREE.Vector3(0,0,1),s.headRestRadians[i]);joint.restQuaternion.copy(joint.object3d.quaternion);heads.push(head);joints.push(joint);
  }
  this.terminalPlugAssembly={frame,tongue,shoulder,floor,deck,partitions,entry,springs,cages,shanks,heads,joints};
 }
}
