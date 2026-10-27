import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';

function circularHole(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(h);}
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:40}),material,position,name);}
function rectangle(w,h){const s=new THREE.Shape();s.moveTo(-w/2,-h/2);s.lineTo(-w/2,h/2);s.lineTo(w/2,h/2);s.lineTo(w/2,-h/2);s.closePath();return s;}
function cylinder(parent,r,depth,position,material,name){return mesh(parent,new THREE.CylinderGeometry(r,r,depth,48).rotateX(Math.PI/2),material,position,name);}

function board(host){
 // Open contours clear the two native mounting bosses and the Grove body.
 // This clockwise exterior uses explicitly counter-clockwise bore paths.
 const s=new THREE.Shape();
 s.moveTo(-6.4,13.8);s.lineTo(6.4,13.8);s.lineTo(10.4,9.8);s.lineTo(10.4,.35);s.lineTo(8,.35);
 s.absarc(8,-4,4.35,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-8.35);s.lineTo(10.4,-9.8);s.lineTo(6.4,-13.8);
 s.lineTo(5.6,-13.8);s.lineTo(5.6,-8.5);s.lineTo(-5.6,-8.5);s.lineTo(-5.6,-13.8);s.lineTo(-6.4,-13.8);
 s.lineTo(-10.4,-9.8);s.lineTo(-10.4,-8.35);s.lineTo(-8,-8.35);s.absarc(-8,-4,4.35,Math.PI*1.5,Math.PI*2.5,false);
 s.lineTo(-10.4,.35);s.lineTo(-10.4,9.8);s.closePath();circularHole(s,0,-4,2.1);
 for(const x of [-3,-1,1,3])circularHole(s,x,-8.1,.32);
 const pcb=solid(host.body,s,.8,[0,0,-.3],materials.plastic(0x274a3c,{roughness:.9}),'Gesture PCB with open boss and Grove relief');
 pcb.userData={role:'physical-pcb',scope:'Reconstructed visible board and concealed support; no trace-level or electrical model'};
 return pcb;
}

function opticalPackage(host){
 const bodyMaterial=materials.plastic(0x263b32,{roughness:.65});
 const substrate=mesh(host.body,new THREE.BoxGeometry(5.2,3,.32),materials.plastic(0x303831,{roughness:.85}),[0,8,.66],'Gesture PAJ7620U2 package substrate');
 // A volumetric enclosure with two shallow optical wells. Their floors,
 // receiver lens and IR emitter close the package, rather than a window image.
 const profile=rectangle(5.2,3),left=new THREE.Path();
 left.moveTo(-2.08,-.94);left.lineTo(-.54,-.94);left.lineTo(-.54,.94);left.lineTo(-2.08,.94);left.closePath();profile.holes.push(left);
 circularHole(profile,1.12,0,.38);
 const body=solid(host.body,profile,1.88,[0,8,.82],bodyMaterial,'Gesture PAJ7620U2 molded optical enclosure');
 const emitterFloor=mesh(host.body,new THREE.BoxGeometry(1.54,1.88,1.45),materials.plastic(0x171e19,{roughness:.8}),[-1.31,8,1.545],'Gesture recessed IR emitter well floor');
 const receiverFloor=cylinder(host.body,.38,1.49,[1.12,8,1.565],materials.plastic(0x111b18),'Gesture receiver well floor');
 const emitter=mesh(host.body,new THREE.BoxGeometry(.58,.72,.16),materials.plastic(0xb1a34b,{roughness:.48}),[-1.31,8,2.35],'Gesture passive IR LED package');
 mesh(host.body,new THREE.BoxGeometry(.20,.23,.07),materials.glossy(0x625c2d,{roughness:.28}),[-1.31,8,2.465],'Gesture IR emitter optical centre');
 const lens=cylinder(host.body,.27,.14,[1.12,8,2.40],materials.glossy(0x132720,{roughness:.2}),'Gesture recessed receiver lens');
 // Fine physical edge contacts provide package depth and remain fully inside
 // the optical aperture; their dimensions are visual, not solder tolerances.
 const contacts=[];
 for(const sign of [-1,1])for(let i=0;i<5;i++)contacts.push(mesh(host.body,new THREE.BoxGeometry(.42,.14,.14),materials.metal(0xb4ab87,{roughness:.45}),[-1.94+i*.97,8+sign*1.49,.90],'Gesture package edge contact'));
 const packageInfo={part:'PAJ7620U2',footprintMm:[5.2,3],bodyHeightMm:1.88,substrateHeightMm:.32,scope:'Passive optical appearance; no IR light, gesture, proximity, image, sensor value or protocol simulation',inferred:spec.source.inferred};
 body.userData=packageInfo;substrate.userData=packageInfo;
 return {body,substrate,emitterFloor,receiverFloor,emitter,lens,contacts};
}

export function buildGesture(host){
 addCadParts(host,data,{shell:materials.plastic(0xe4e6df,{roughness:.8})});
 const pcb=board(host),optics=opticalPackage(host);
 const socket=connector(host.body,32,false,{height:5.2});socket.name='Gesture red open-top HY2.0-4P';socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],
  pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],
  meta:{role:'visual-connector',face:'bottom',protocol:'I2C',scope:'Physical connector, attachment and cable pose only; no bus or electrical behavior'}}));
 screw(host.body,[0,-4,-3.97],'back',1.4);
 const shank=cylinder(host.body,.65,1.6,[0,-4,-2.65],materials.metal(0x919997,{roughness:.5}),'Gesture concealed mounting screw shank');
 host.add(new Component({id:'sensor',label:'PAJ7620U2 appearance anchor',position:[0,8,2.7],meta:{role:'visual-anchor',part:'PAJ7620U2',scope:'No commands, hand gestures, image, proximity, sensor values, I2C or automatic light behavior'}}));
 addStickers(host);
 host.gestureAssembly={pcb,optics,socket,port,shank};
}
