import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {capsule} from '../../core/geometry.js';
import {mesh,slab,disc,grove,header,FACE,portQuaternion} from '../../modeling/parts.js';

function ring(parent,{outer,inner,depth,z,material,name}){
 const shape=new THREE.Shape();shape.absarc(0,0,outer,0,Math.PI*2,false);const bore=new THREE.Path();bore.absarc(0,0,inner,0,Math.PI*2,true);shape.holes.push(bore);
 return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:48}),material,[0,0,z],name);
}

/** Product-local USB geometry: the socket has a full interior, tongue and surface contacts. */
function usbC(host){
 const position=[0,-24.02,5.8],g=new THREE.Group();g.position.fromArray(position);g.quaternion.copy(FACE.bottom);g.name='Nesso USB-C assembly';host.body.add(g);
 const shell=capsule(8.7,3.1);shell.holes.push(capsule(8.1,2.5,{path:new THREE.Path(),clockwise:true}));
 mesh(g,new THREE.ExtrudeGeometry(shell,{depth:5.4,bevelEnabled:false,curveSegments:24}),materials.metal(0xa1aaa9,{roughness:.33}),[0,0,-5.4],'USB-C metal shell');
 slab(g,8.1,2.5,.5,1.25,[0,0,-5.7],materials.plastic(0x171c1c),[],.025).name='USB-C recessed back';
 mesh(g,new THREE.BoxGeometry(6.6,.65,4.5),materials.plastic(0x202725),[0,0,-3.1],'USB-C tongue');
 for(const side of [-1,1])for(let i=0;i<12;i++)mesh(g,new THREE.BoxGeometry(.22,.045,1.65),materials.metal(0xc9bb8b,{roughness:.43}),[(i-5.5)*.48,side*.348,-1.8],'USB-C contact');
 const silver=materials.metal(0x9da5a1,{roughness:.45}),pad=materials.metal(0xb3a76d,{roughness:.58});
 for(const x of [-4.1,4.1]){mesh(host.body,new THREE.BoxGeometry(.65,2.8,.26),silver,[x,-20.6,4.18],'USB shell solder tab');mesh(host.body,new THREE.BoxGeometry(1.1,3.1,.08),pad,[x,-20.6,4.12],'USB shell PCB pad');}
 host.add(new Port({id:'usb',label:'USB-C',connector:'usb-c',position,quaternion:portQuaternion('bottom'),hitSize:[8.7,1,3.1],meta:{role:'visual-connector',face:'bottom'}}));
}

function qwiic(host){
 const position=[-12.02,0,5.6],g=new THREE.Group();g.position.fromArray(position);g.quaternion.copy(FACE.left);g.name='Qwiic connector';host.body.add(g);const white=materials.plastic(0xd2d7cf,{roughness:.65});
 for(const x of [-2.85,2.85])mesh(g,new THREE.BoxGeometry(.6,3.5,3.2),white,[x,0,-1.6],'Qwiic side wall');
 for(const y of [-1.5,1.5])mesh(g,new THREE.BoxGeometry(5.1,.5,3.2),white,[0,y,-1.6],'Qwiic retaining rail');
 mesh(g,new THREE.BoxGeometry(5.1,2.5,.4),white,[0,0,-3],'Qwiic socket back');
 for(let i=0;i<4;i++)mesh(g,new THREE.BoxGeometry(.24,.3,2.4),materials.metal(0xa9b1a3,{roughness:.5}),[(i-1.5),-.2,-1.7],'Qwiic contact');
 host.add(new Port({id:'qwiic',label:'Qwiic · 4 pin',connector:'qwiic',position,quaternion:portQuaternion('left'),hitSize:[6.3,1,3.5],meta:{role:'visual-connector',face:'left',pitchMm:1}}));
}

/** The external RF socket is photo-shaped; the source's MMCX/IPEX4 naming conflict is recorded in the audit. */
function rfSocket(host){
 const position=[11.97,18.75,1.55],g=new THREE.Group();g.position.fromArray(position);g.quaternion.copy(FACE.right);g.name='LoRa RF snap receptacle';host.body.add(g);
 const brass=materials.metal(0xad954d,{roughness:.4}),insulator=materials.plastic(0xc5ba8d,{roughness:.73});
 slab(g,4.1,4.1,.3,.6,[0,0,-.32],brass,[{w:2.3,h:2.3,r:1.15}],.025).name='RF mounting flange';
 ring(g,{outer:1.65,inner:1.15,depth:1.65,z:-1.67,material:brass,name:'RF socket barrel'});
 ring(g,{outer:1.88,inner:1.65,depth:.15,z:-.17,material:brass,name:'RF retaining collar'});
 ring(g,{outer:1.13,inner:.23,depth:.25,z:-.9,material:insulator,name:'RF socket dielectric'});
 ring(g,{outer:.26,inner:.12,depth:1,z:-1.55,material:brass,name:'RF female center contact'});
 disc(g,1.15,[0,0,-1.75],materials.plastic(0x171b17)).name='RF socket bore back';
 mesh(host.body,new THREE.BoxGeometry(.55,2.5,.8),brass,[9.9,18.75,3.1],'RF board mount');
 mesh(host.body,new THREE.BoxGeometry(1.2,2.8,.08),brass,[9.9,18.75,3.3],'RF PCB pad');
 host.add(new Port({id:'lora-antenna',label:'LoRa antenna · coaxial snap',connector:'coax-snap',position,quaternion:portQuaternion('right'),hitSize:[4.1,1,4.1],meta:{role:'visual-connector',face:'right',connectorTypeSource:'M5Stack/Arduino pinout: MMCX; Arduino datasheet: IPEX4; feedback pending'}}));
}

function stowedAntennaPlug(host){
 const g=new THREE.Group();g.position.set(-.05,-19.13,-5);g.name='Stored antenna coaxial plug';g.userData={role:'stowed-antenna-connector',pose:'storage'};host.body.add(g);
 const brass=materials.metal(0xb09a51,{roughness:.4});
 slab(g,3.7,3.7,.22,.25,[0,0,-.1],brass,[{w:1.6,h:1.6,r:.8}],.025).name='Antenna plug mounting flange';
 ring(g,{outer:1.55,inner:.95,depth:2.73,z:.12,material:brass,name:'Antenna plug barrel'});
 for(const z of [.25,.65])ring(g,{outer:1.76,inner:1.52,depth:.15,z,material:brass,name:'Antenna snap collar'});
 ring(g,{outer:.93,inner:.22,depth:.3,z:2.1,material:materials.plastic(0xc6bb8f),name:'Antenna plug dielectric'});
 mesh(g,new THREE.CylinderGeometry(.16,.16,.65,24).rotateX(Math.PI/2),brass,[0,0,2.475],'Antenna plug center pin');
}

function rearFasteners(host){
 const metal=materials.metal(0xa3aba7,{roughness:.4});
 for(const x of [-9,9]){
  const profile=new THREE.Shape();profile.absarc(0,0,1.6,0,Math.PI*2,false);const hex=new THREE.Path();for(let i=0;i<6;i++){const a=-i*Math.PI/3;i?hex.lineTo(.72*Math.cos(a),.72*Math.sin(a)):hex.moveTo(.72*Math.cos(a),.72*Math.sin(a));}hex.closePath();profile.holes.push(hex);
  mesh(host.body,new THREE.ExtrudeGeometry(profile,{depth:1.1,bevelEnabled:true,bevelThickness:.025,bevelSize:.025,bevelSegments:2,curveSegments:32}),metal,[x,-21,-10.55],'Rear M2 socket-head fastener');
  mesh(host.body,new THREE.CylinderGeometry(.7,.7,.1,6).rotateX(Math.PI/2),materials.plastic(0x252b29),[x,-21,-9.5],'Rear screw hex recess floor');
 }
}

export function nessoAssembly(host){
 const pcb=slab(host.body,20.8,45.2,.8,.8,[0,.3,3.3],materials.plastic(0x284637,{roughness:.9}),[],.08);pcb.name='Nesso main PCB';
 usbC(host);grove(host,{position:[0,-23.65,.6],face:'bottom',w:10.2,h:5.2});
 const solder=materials.metal(0xabb2a3,{roughness:.5});
 for(const x of [-3,-1,1,3]){mesh(host.body,new THREE.BoxGeometry(.42,.65,.42),solder,[x,-18.35,.45],'Grove contact elbow');mesh(host.body,new THREE.BoxGeometry(.42,.42,2.95),solder,[x,-18.15,1.925],'Grove PCB contact tail');}
 qwiic(host);rfSocket(host);stowedAntennaPlug(host);rearFasteners(host);
 header(host.body,{position:[0,23.8,-2.35],face:'top',cols:8,rows:1});
 const key=slab(host.body,4,6.4,1.1,.7,[-10.7,-16,3.3],materials.plastic(0x242a2a),[],.07);key.quaternion.copy(FACE.left);key.name='Side power key cap';
}
