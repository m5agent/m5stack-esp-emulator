import * as THREE from 'three';
import {Module,Component,Port,VisualJoint,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {roundedRect} from '../../core/geometry.js';
import {mesh,slab,grove,screw,portQuaternion} from '../../modeling/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';

const orange=()=>materials.plastic(0xee8b21,{roughness:.65});
const contact=()=>materials.metal(0xb8b5a5,{roughness:.4});
const physical=(parent,geometry,material,position,name)=>mesh(parent,geometry,material,position,'Relay '+name);

function pcb(host){
 const x=9.2,y=21.2,r=3.1,n=5.4,bore=3.65,edge=x-8,dy=Math.sqrt(bore*bore-edge*edge),theta=Math.acos(edge/bore),s=new THREE.Shape();
 s.moveTo(-x+r,-y);s.lineTo(-n,-y);s.lineTo(-n,-16.8);s.lineTo(n,-16.8);s.lineTo(n,-y);s.lineTo(x-r,-y);
 s.absarc(x-r,-y+r,r,-Math.PI/2,0);s.lineTo(x,spec.mountY-dy);s.absarc(8,spec.mountY,bore,-theta,theta-Math.PI*2,true);
 s.lineTo(x,y-r);s.absarc(x-r,y-r,r,0,Math.PI/2);s.lineTo(-x+r,y);s.absarc(-x+r,y-r,r,Math.PI/2,Math.PI);
 s.lineTo(-x,spec.mountY+dy);s.absarc(-8,spec.mountY,bore,Math.PI-theta,-Math.PI+theta,true);s.lineTo(-x,-y+r);s.absarc(-x+r,-y+r,r,Math.PI,Math.PI*1.5);
 s.holes.push(roundedRect(6,6,3,{cx:0,cy:spec.mountY,path:new THREE.Path(),clockwise:true}));
 const board=physical(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:24}),materials.plastic(0x264736,{roughness:.92}),[0,0,-2.1],'PCB with open boss and Grove clearances');
 host.relayAssembly={pcb:board};
}

function relayPackage(host){
 const [x,y,z]=spec.relay.position,[w,h,d]=spec.relay.size;
 const base=slab(host.body,w,h,.3,.24,[x,y,z],materials.plastic(0xb8751c,{roughness:.8}),[],.06);base.name='Relay sealed HK4100F bottom seam';
 const can=slab(host.body,w,h,d-.3,.24,[x,y,z+.3],orange(),[],.16);can.name='Relay sealed HK4100F housing';
 can.userData={part:'HK4100F-DC5V-SHG',dimensionsMm:[w,h,d],source:'Official linked HK4100F p7 and U023 assembled drawing; sealed outer package only'};
 // Mounted leads are shortened inside the real rear cover. No internal
 // moving contact, energized armature, coil state or electrical response.
 const metal=contact();
 for(const [px,py]of [[-5.08,-3.78],[-5.08,-1.24],[-5.08,3.78],[5.08,-3.78],[5.08,3.78]])physical(host.body,new THREE.BoxGeometry(.45,.4,1.45),metal,[px,y+py,-1.975],'short concealed HK4100F lead');
 host.relayAssembly.package=can;host.relayAssembly.packageBase=base;
}

function input(host){
 const socket=grove(host,{position:spec.grove.position,face:'bottom',h:5.2,color:spec.grove.color});socket.name='Relay black HY2.0-4P socket';
 // The official U023 front photograph shows the open upper channel and
 // short locking bridge, rather than a continuous plate across the top.
 const cover=socket.children.find(o=>o.geometry?.parameters?.height===.8&&o.position.y>0),plastic=cover.material;
 cover.removeFromParent();cover.geometry.dispose();
 for(const x of [-3.85,3.85])physical(socket,new THREE.BoxGeometry(.9,.8,5.8),plastic,[x,2.2,-2.9],'Grove open-top rail');
 physical(socket,new THREE.BoxGeometry(3.4,.65,1.05),plastic,[0,1.2,-3.9],'Grove short latch bridge');
 host.relayAssembly.grove=socket;
}

function fixedTerminal(host){
 const t=spec.terminal,group=new THREE.Group();group.name='Relay fixed 3.96 mm three-pole socket';host.body.add(group);
 const plastic=orange(),metal=contact();
 slab(group,12,9.3,1.3,.18,[0,9.05,-1.2],plastic,[],.05).name='Relay fixed terminal floor';
 slab(group,12,.8,8.2,.2,[0,13.3,.1],plastic,[],.06).name='Relay fixed terminal straight retention wall';
 // The photographed relay-side wall has three scalloped wire clearances.
 // They are open parts of the outside contour, not holes cutting an edge.
 const scallop=new THREE.Shape();scallop.moveTo(-6,.1);scallop.lineTo(6,.1);scallop.lineTo(6,8.3);
 for(const x of [...t.pinX].reverse()){scallop.lineTo(x+1.3,8.3);scallop.lineTo(x+1.3,7);scallop.absarc(x,7,1.3,0,-Math.PI,true);scallop.lineTo(x-1.3,8.3);}
 scallop.lineTo(-6,8.3);scallop.closePath();
 physical(group,new THREE.ExtrudeGeometry(scallop,{depth:.8,bevelEnabled:false,curveSegments:24}).rotateX(Math.PI/2),plastic,[0,5.2,0],'fixed terminal scalloped retention wall');
 for(const x of [-5.65,5.65])slab(group,.7,7.8,2.8,.1,[x,9.05,.1],plastic,[],.035).name='Relay fixed terminal low end wall';
 for(const x of t.pinX){
  physical(group,new THREE.BoxGeometry(.7,.7,5.25),metal,[x,9.05,2.725],'fixed terminal contact pin');
  physical(group,new THREE.CylinderGeometry(.16,.35,.3,4).rotateX(Math.PI/2).rotateZ(Math.PI/4),metal,[x,9.05,5.5],'fixed terminal tapered contact tip');
  physical(group,new THREE.BoxGeometry(.7,.7,1.45),metal,[x,9.05,-1.925],'fixed terminal short solder tail');
 }
 const terminal=host.add(new Port({id:'terminal',label:'3.96 mm 3P · COM / NO / NC',connector:'ht3.96-3p',position:t.position,quaternion:portQuaternion('front'),hitSize:[12,1,9.3],pins:t.names.map((name,i)=>({n:i+1,name})),pinGrid:{cols:3,rows:1,pitch:t.pitch,center:[0,0],order:col=>col+1},meta:{role:'visual-connector',face:'front',sku:'U023',source:'Official J2 Socket_3.96x3p and COM / NO / NC front photo',scope:'Physical load connector appearance and removable accessory only; no continuity, switching, voltage or electrical behavior'}}));
 host.relayAssembly.terminal=group;host.relayAssembly.terminalPort=terminal;
}

function plugGeometry(host){
 // Public Module frame: local +Y is out of the front mating face. The child
 // frame restores engineering XY/Z axes used in the official front drawing.
 const frame=new THREE.Group();frame.name='Relay removable terminal plug assembly';frame.rotation.x=-Math.PI/2;host.body.add(frame);
 const plastic=orange(),metal=contact(),inside=materials.metal(0x646963,{roughness:.6}),y=0,bottom=-5.1;
 const holes=spec.terminal.pinX.map(cx=>({w:1.7,h:1.8,r:.12,cx,cy:y}));
 slab(frame,11.75,6.4,2.45,.2,[0,y,bottom],plastic,holes,.04).name='Relay plug bored mating foot';
 slab(frame,11.75,.8,2.7,.14,[0,2.8,-2.65],plastic,[],.04).name='Relay plug closed inner wall';
 // The top deck has actual recessed screw-access bores. The three side
 // entries remain empty space between partitions, with real clamp cages.
 slab(frame,11.75,6.4,1.3,.22,[0,y,-.7],plastic,spec.terminal.pinX.map(cx=>({w:2.9,h:2.9,r:1.45,cx,cy:y})),.04).name='Relay plug screw-access deck';
 for(const x of [-5.58,-1.98,1.98,5.58])slab(frame,.55,5.6,2.7,.08,[x,-.4,-2.65],plastic,[],.025).name='Relay plug wire-channel partition';
 for(const [i,x]of spec.terminal.pinX.entries()){
  for(const sign of [-1,1])physical(frame,new THREE.BoxGeometry(.18,1.35,2.2),metal,[x+sign*.6,0,-3.95],'plug mating spring contact');
  physical(frame,new THREE.BoxGeometry(2.9,4.7,.25),metal,[x,-.45,-2.525],'plug clamp lower plate');
  // Inferred concealed metal ends at host z7.51, below the actual molded
  // deck bottom z7.60. This 0.09 mm visual gap is not a rated tolerance.
  for(const sign of [-1,1])physical(frame,new THREE.BoxGeometry(.2,4.7,1.61),metal,[x+sign*1.35,-.45,-1.595],'plug clamp cage side');
  physical(frame,new THREE.BoxGeometry(2.9,.25,1.61),metal,[x,1.8,-1.595],'plug clamp rear web');
  physical(frame,new THREE.BoxGeometry(2.7,3.8,.24),metal,[x,-.45,-.91],'plug pressure plate');
  physical(frame,new THREE.CylinderGeometry(.43,.43,.75,24).rotateX(Math.PI/2),metal,[x,0,-.85],'plug screw shank');
  const head=new THREE.Group();head.name=`Relay ${spec.terminal.names[i]} slotted terminal screw`;
  physical(head,new THREE.CylinderGeometry(1.18,1.18,.12,48).rotateX(Math.PI/2),inside,[0,0,.06],'plug screw slot floor');
  const outline=new THREE.Shape();outline.absarc(0,0,1.18,0,Math.PI*2,false);outline.holes.push(roundedRect(1.95,.32,.05,{path:new THREE.Path(),clockwise:true}));
  physical(head,new THREE.ExtrudeGeometry(outline,{depth:.3,bevelEnabled:false,curveSegments:32}),metal,[0,0,.12],'plug slotted screw head');
  const joint=host.add(new VisualJoint({id:`screw-${i+1}`,label:`${spec.terminal.names[i]} screw visual angle`,position:[x,0,-.42],axis:[0,0,1],meta:{visualRangeDeg:[-180,180],rangeEvidence:'Viewer angle only; thread pitch, tightening limits and clamp displacement are unconfirmed',scope:'External visible screw angle only; no tightening, axial travel, clamp force, wire or electrical behavior'}}),frame);
  joint.object3d.add(head);joint.object3d.quaternion.setFromAxisAngle(new THREE.Vector3(0,0,1),[.27,-.38,.61][i]);joint.restQuaternion.copy(joint.object3d.quaternion);
 }
 host.plugAssembly={frame};
}

/** Supplied U023 detachable 3-pole screw terminal; visual mating geometry only. */
export class TerminalPlug extends Module{
 static meta={id:'m5stack.unit.relay.terminal-plug',name:'U023 removable 3P screw terminal',sku:'U023 accessory',connector:'ht3.96-3p'};
 build(){plugGeometry(this);}
}

export function buildRelay(host,{terminalPlug=false}={}){
 addCadParts(host,data,{shell:materials.plastic(0xe0e3dc,{roughness:.8})});pcb(host);relayPackage(host);input(host);fixedTerminal(host);
 screw(host.body,[0,spec.mountY,-4.035],'back',1.4);
 host.add(new Component({id:'sensor',label:'Relay appearance anchor',meta:{role:'visual-anchor',scope:'No coil, armature, relay output, load, firmware or electrical model'}}));
 if(terminalPlug)host.port('terminal').attach(new TerminalPlug());
}
