import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
function bore(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(h);}
function board(host){
 // Top notch accommodates the edge-facing receiver; the bottom contour is
 // open for the Grove, while scallops retain both original mounting bores.
 const s=new THREE.Shape();s.moveTo(-7,14.4);s.lineTo(-2.4,14.4);s.lineTo(-2.4,8.7);s.lineTo(2.4,8.7);s.lineTo(2.4,14.4);s.lineTo(7,14.4);s.lineTo(10.4,11);s.lineTo(10.4,-.6);s.lineTo(8,-.6);
 s.absarc(8,-4,3.4,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-7.4);s.lineTo(10.4,-11);s.lineTo(7,-14.4);s.lineTo(5.3,-14.4);s.lineTo(5.3,-8.5);s.lineTo(-5.3,-8.5);s.lineTo(-5.3,-14.4);s.lineTo(-7,-14.4);s.lineTo(-10.4,-11);s.lineTo(-10.4,-7.4);s.lineTo(-8,-7.4);s.absarc(-8,-4,3.4,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.4,-.6);s.lineTo(-10.4,11);s.closePath();
 bore(s,0,-4,1.9);for(const x of[-3,-1,1,3])bore(s,x,-8.15,.32);for(const x of[-.9,0,.9])bore(s,x,8.2,.23);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:48}),materials.plastic(0x176d45,{roughness:.93}),[0,0,-.4],'Laser RX physical PCB with true fastening, receiver and Grove solder bores');
 pcb.userData={role:'physical-pcb',scope:'Visual reconstruction only; outline, thickness and installed datum inferred'};
 const pads=[],metal=materials.metal(0xb5b9b0,{roughness:.45});for(const [x,y,r]of[...[-3,-1,1,3].map(x=>[x,-8.15,.32]),...[-.9,0,.9].map(x=>[x,8.2,.23])]){const p=new THREE.Shape();p.absarc(x,y,r+.23,0,Math.PI*2,false);bore(p,x,y,r);pads.push(mesh(host.body,new THREE.ExtrudeGeometry(p,{depth:.05,bevelEnabled:false,curveSegments:32}),metal,[0,0,-.45],'Laser RX rear through-hole solder annulus'));}
 return{pcb,pads};
}
function receiver(host){
 const frame=new THREE.Group();frame.name='Laser RX ISO103 physical optical receiver';host.body.add(frame);
 const dark=materials.plastic(0x1d201c,{roughness:.63}),metal=materials.metal(0xaeb3a6,{roughness:.46});
 const body=mesh(frame,new THREE.CylinderGeometry(1.4,1.4,3.2,64),dark,[0,12.6,0],'Laser RX ISO103 fixed dark cylindrical body');
 const dome=mesh(frame,new THREE.SphereGeometry(1.4,64,24,0,Math.PI*2,0,Math.PI/2),materials.plastic(0x34261c,{roughness:.27,clearcoat:.22}),[0,14.2,0],'Laser RX recessed dark non-emissive receiver dome');
 // A physical back cap closes the body. The lens is an absorber, never a Led.
 const cap=mesh(frame,new THREE.CylinderGeometry(1.41,1.41,.35,64),dark,[0,11,0],'Laser RX ISO103 fixed package rear seal');const leads=[];
 for(const x of[-.9,0,.9]){
  leads.push(mesh(frame,new THREE.BoxGeometry(.24,2.8,.24),metal,[x,9.5,0],'Laser RX ISO103 metal lead to PCB'));
  leads.push(mesh(frame,new THREE.BoxGeometry(.24,.24,.8),metal,[x,8.2,-.28],'Laser RX ISO103 through-hole lead bend'));
 }
 frame.userData={role:'physical-receiver-package',part:'ISO103',scope:'Exact product identity; concealed package profile, material tint and installed depth inferred from the 3 mm native optical aperture and same-SKU exterior photos. No light source, ray, sensitivity or digital output'};
 dome.userData={role:'physical-optical-window',part:'ISO103 receiving surface',emitsLight:false};return{frame,body,dome,cap,leads};
}
function electronics(host){
 const dark=materials.plastic(0x292c27,{roughness:.84}),ceramic=materials.plastic(0xb09e75,{roughness:.9}),metal=materials.metal(0xb7b9ad,{roughness:.5}),parts=[];
 for(const[id,x,y,kind]of[['R1',-4,6,'resistor'],['R2',4,6,'resistor'],['C2',4,3.6,'capacitor']]){
  parts.push(mesh(host.body,new THREE.BoxGeometry(1.6,.8,.55),kind==='resistor'?dark:ceramic,[x,y,.675],`Laser RX ${id} physical ${kind}`));for(const dx of[-.64,.64])parts.push(mesh(host.body,new THREE.BoxGeometry(.32,.82,.57),metal,[x+dx,y,.675],`Laser RX ${id} metal termination`));
 }
 return{parts};
}
export function buildLaserRx(host){
 addCadParts(host,data,{shell:materials.plastic(0xe8eae5,{roughness:.77})});const pcb=board(host),physicalReceiver=receiver(host),physicalElectronics=electronics(host),socket=connector(host.body,32,true,{height:5.2});socket.name='Laser RX black open-top HY2.0-4P';
 const port=host.add(new Port({id:'grove',label:'PORT.B · DOUT',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'NC',color:'yellow'},{n:4,name:'DOUT',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'GPIO',scope:'Physical connector, attachment and cable pose only; no light transport, acquisition, signal processing, digital output, GPIO or electrical state'}}));
 const fixing=screw(host.body,[0,-4,-3.97],'back',1.4),shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,2.2,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,-4,-2.8],'Laser RX fastening screw shank');
 host.add(new Component({id:'sensor',label:'ISO103 receiver visual anchor',position:spec.receiver.position,quaternion:portQuaternion('top'),meta:{role:'visual-anchor',part:'ISO103',scope:'Passive visual anchor only; no light, beam, optical coupling, illumination, reception, sampling, communication, waveform, digital output, GPIO or firmware'}}));
 addStickers(host);host.laserRxAssembly={pcb,receiver:physicalReceiver,electronics:physicalElectronics,socket,port,fixing,shank};
}
