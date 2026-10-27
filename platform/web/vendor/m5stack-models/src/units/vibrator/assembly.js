import * as THREE from 'three';
import {Component,Port,VisualJoint,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
function bore(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(h);}
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:48}),material,position,name);}
function board(host){
 // Open outer contour leaves the installed motor and Grove body clear; real
 // mounting and screw holes continue through the added board layer.
 const s=new THREE.Shape(),x=11.4,y=15.2,r=3.7,n=5.3,upper=5.5;
 s.moveTo(-x+r,-y);s.lineTo(-n,-y);s.lineTo(-n,-9);s.lineTo(n,-9);s.lineTo(n,-y);s.lineTo(x-r,-y);
 s.absarc(x-r,-y+r,r,-Math.PI/2,0);s.lineTo(x,y-r);s.absarc(x-r,y-r,r,0,Math.PI/2);
 s.lineTo(upper,y);s.lineTo(upper,-1.8);s.lineTo(-upper,-1.8);s.lineTo(-upper,y);s.lineTo(-x+r,y);
 s.absarc(-x+r,y-r,r,Math.PI/2,Math.PI);s.lineTo(-x,-y+r);s.absarc(-x+r,-y+r,r,Math.PI,Math.PI*1.5);s.closePath();
 for(const cx of[-8,8])bore(s,cx,-4,3.1);bore(s,0,-4,1.9);
 const pcb=solid(host.body,s,.8,[0,0,.1],materials.plastic(0x2c4639,{roughness:.91}),'Vibrator U-shaped PCB with motor clearance');
 pcb.userData={role:'physical-pcb',scope:'Inferred board support; no electrical simulation or trace-level manufacturing model'};return pcb;
}
function motor(host){
 const silver=materials.metal(0xadb1ab,{roughness:.48}),dark=materials.plastic(0x2c302d,{roughness:.83}),group=new THREE.Group();group.name='Vibrator N20 fixed motor assembly';host.body.add(group);
 // The concealed can is a photo-derived flattened N20 envelope. The original
 // molded cover is retained, and the visible bearing backs its real aperture.
 const can=solid(group,roundedRect(10.5,9.6,3.4),16.8,[0,-1.5,2.2],silver,'N20 flattened stamped metal motor can');can.rotation.x=-Math.PI/2;
 const rear=solid(group,roundedRect(10.3,9.4,3.3),.7,[0,-2.2,2.2],dark,'N20 fixed brush end cap');rear.rotation.x=-Math.PI/2;
 const ring=new THREE.Shape();ring.absarc(0,0,2.45,0,Math.PI*2,false);bore(ring,0,0,.53);
 const bearing=solid(group,ring,.55,[0,15.25,2.2],silver,'N20 fixed front bearing with shaft bore');bearing.rotation.x=-Math.PI/2;
 const rotorGroup=new THREE.Group();rotorGroup.name='Vibrator external shaft and eccentric';rotorGroup.position.set(0,15.65,2.2);host.body.add(rotorGroup);
 const shaft=mesh(rotorGroup,new THREE.CylinderGeometry(.5,.5,5.7,40),silver,[0,2.2,0],'Vibrator motor output shaft');
 const massShape=new THREE.Shape();massShape.absarc(.8,0,3.5,0,Math.PI*2,false);bore(massShape,0,0,.53);
 const mass=solid(rotorGroup,massShape,5,[0,.35,0],materials.metal(0xb99347,{roughness:.42,metalness:.85}),'Vibrator bored brass eccentric mass');mass.rotation.x=-Math.PI/2;
 // The exact U059 photos show the radial retaining screw. Its recess, like
 // the hidden eccentric bore offset, is visual reconstruction, not a BOM.
 const retainingScrew=mesh(rotorGroup,new THREE.CylinderGeometry(.53,.53,.18,32),materials.metal(0x9c7c3c,{roughness:.62}),[-2.68,2.7,0],'Vibrator eccentric radial retaining screw');retainingScrew.rotation.z=Math.PI/2;
 const slot=mesh(rotorGroup,new THREE.BoxGeometry(.025,.65,.12),materials.plastic(0x50452f,{roughness:.9}),[-2.78,2.7,0],'Vibrator radial screw recessed slot');
 const rotor=host.add(new VisualJoint({id:'rotor',label:'Exposed eccentric and shaft',position:spec.shaft.centreMm,axis:spec.shaft.axis,continuous:true,
  meta:{axisEvidence:'Exact U059 photographs and dimension drawing show exposed N20 shaft/eccentric along +Y; model shaft-axis XYZ and offset bore are inferred.',demoRpmMax:240,scope:'External visual angle or RPM only; default stopped. No vibration force, housing shake, PWM-to-RPM mapping, motor physics, GPIO or autonomous motion.'}}));rotor.adopt(rotorGroup);
 return {group,can,rear,bearing,rotorGroup,shaft,mass,retainingScrew,slot,rotor};
}
function electronics(host){
 const parts=[],dark=materials.plastic(0x222a26,{roughness:.83}),metal=materials.metal(0xb3b5ac,{roughness:.57});
 for(const[x,y,w,h]of[[-7.1,-9.2,2.9,1.6],[7.2,-9.2,1.6,.8],[-7.1,-11.7,1,.6],[7.2,-11.7,1,.6]]){
  parts.push(mesh(host.body,new THREE.BoxGeometry(w,h,.55),dark,[x,y,1.175],'Vibrator drive/protection package'));
  for(const dx of[-w*.37,w*.37])parts.push(mesh(host.body,new THREE.BoxGeometry(.3,h*.7,.56),metal,[x+dx,y,1.18],'Vibrator package solder termination'));
 }
 return parts;
}
export function buildVibrator(host){
 addCadParts(host,data,{shell:materials.plastic(0xe0e3dc,{roughness:.8})});
 const pcb=board(host),motorAssembly=motor(host),support=electronics(host),socket=connector(host.body,32,true,{height:5.2});socket.name='Vibrator black open-top HY2.0-4P';
 const port=host.add(new Port({id:'grove',label:'PORT.B · DIN / NC',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],
  pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'DIN',color:'yellow'},{n:4,name:'NC',color:'white'}],
  meta:{role:'visual-connector',face:'bottom',scope:'Physical connector, attachment and cable pose only; no GPIO, PWM or electrical behavior'}}));
 screw(host.body,[0,-4,-3.97],'back',1.4);
 const shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,1.6,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,-4,-2.65],'Vibrator concealed fastening screw shank');
 host.add(new Component({id:'sensor',label:'Vibrator passive visual anchor',position:[0,7,2.2],meta:{role:'visual-anchor',scope:'No sensor readings, motor drive, electrical behavior or autonomous vibration'}}));
 addStickers(host);
 host.vibratorAssembly={pcb,motor:motorAssembly,electronics:support,socket,port,shank};
}
