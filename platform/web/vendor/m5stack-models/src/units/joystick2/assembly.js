import {addStickers} from './stickers.js';
import * as THREE from 'three';
import {Button,Component,Led,Port,materials} from '../../core/index.js';
import {VisualJoint} from '../../core/components/VisualJoint.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';

function hole(shape,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(p);}
function cylinder(parent,r,depth,position,material,name){return mesh(parent,new THREE.CylinderGeometry(r,r,depth,48).rotateX(Math.PI/2),material,position,name);}
function board(host){
 // Clockwise exterior plus counter-clockwise bores keeps the FrontSide
 // screw-bore wall facing its empty interior. Mounting bosses use open relief.
 const s=new THREE.Shape();s.moveTo(-6.4,18.8);s.lineTo(6.4,18.8);s.lineTo(10.4,14.8);s.lineTo(10.4,-4.4);s.lineTo(8,-4.4);
 s.absarc(8,-8,3.6,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-11.6);s.lineTo(10.4,-14.8);s.lineTo(6.4,-18.8);
 s.lineTo(5.6,-18.8);s.lineTo(5.6,-12.3);s.lineTo(-5.6,-12.3);s.lineTo(-5.6,-18.8);s.lineTo(-6.4,-18.8);s.lineTo(-10.4,-14.8);
 s.lineTo(-10.4,-11.6);s.lineTo(-8,-11.6);s.absarc(-8,-8,3.6,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.4,-4.4);s.lineTo(-10.4,14.8);s.closePath();
 hole(s,0,-8,2.1);for(const x of[-3,-1,1,3])hole(s,x,-12.1,.32);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:40}),materials.plastic(0x254936,{roughness:.9}),[0,0,-1.2],'Joystick2 physical PCB with open mounting and connector relief');
 pcb.userData={role:'physical-pcb',scope:spec.source.inferred};return pcb;
}

export function buildJoystick2(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe6e7e1,{roughness:.79}),cap:materials.plastic(0xc91940,{roughness:.8}),diffuser:materials.plastic(0xe9e9de,{roughness:.42})});
 const pcb=board(host),fixed=new THREE.Group();fixed.name='Joystick2 fixed JH16 appearance package';host.body.add(fixed);
 mesh(fixed,new THREE.BoxGeometry(17.4,17.4,5.9),materials.plastic(0x20262a,{roughness:.8}),[0,8,2.55],'Joystick2 fixed Hall joystick housing');
 mesh(fixed,new THREE.BoxGeometry(17.8,17.8,.5),materials.metal(0x8e9593,{roughness:.55}),[0,8,-.05],'Joystick2 package metal base');
 // Fixed package encloses the top opening. The visible ball and shaft move
 // with the cap; concealed Hall details and electrical physics are omitted.
 const moving=new THREE.Group();moving.name='Joystick2 moving cap shaft and gimbal';moving.add(parts['Joystick2 native moving thumb cap']);
 const pivot=spec.stick.pivotMm;
 mesh(moving,new THREE.SphereGeometry(3.9,48,28),materials.plastic(0xd1d4cc,{roughness:.55}),pivot,'Joystick2 visible ball gimbal');
 const shaft=cylinder(moving,1.5,6.5,[pivot[0],pivot[1],9.05],materials.plastic(0x20252a,{roughness:.5}),'Joystick2 moving stick shaft');
 moving.position.set(-pivot[0],-pivot[1],-pivot[2]);
 const press=host.add(new Button({id:'press',label:'Stick Z press',mesh:moving,position:pivot,travel:spec.stick.pressTravelMm,
  meta:{role:'visual-control',travelSource:spec.source.motion,scope:'Real cap/shaft/ball press and return; input intent only, no button register or electrical state'}}));
 const meta={visualRangeDeg:spec.stick.visualRangeDeg,rangeEvidence:spec.source.motion,pivotEvidence:spec.source.inferred};
 const x=host.add(new VisualJoint({id:'tilt-x',label:'Stick tilt around X',position:pivot,axis:[1,0,0],limitsDeg:spec.stick.visualRangeDeg,meta}));
 const y=host.add(new VisualJoint({id:'tilt-y',label:'Stick tilt around Y',position:pivot,axis:[0,1,0],limitsDeg:spec.stick.visualRangeDeg,meta}));
 y.adopt(press.object3d);x.adopt(y.object3d);
 const diffuser=parts['Joystick2 native RGB light pipe'];
 const rgb=host.add(new Led({id:'rgb',label:'WS2812C / light pipe',mesh:diffuser,position:[0,0,0],glowSize:3.4,
  meta:{role:'externally-driven-visual-led',scope:'External color/brightness on the real native light pipe; no firmware, sensor state, automatic effects or WS2812 protocol'}}));
 // The component's geometry uses the native translated coordinates. Put its
 // glow at the actual exposed tip instead of the body origin.
 rgb.glow.position.set(7.9,-18.8,4.05);
 mesh(host.body,new THREE.BoxGeometry(2,2,.42),materials.plastic(0xe8e7d9,{roughness:.55}),[7.9,-14.9,.05],'Joystick2 concealed WS2812C package');
 mesh(host.body,new THREE.BoxGeometry(6.4,4.5,.9),materials.plastic(0x20282c,{roughness:.8}),[0,-1.7,.05],'Joystick2 concealed STM32 package');
 for(const xPos of[-2.5,0,2.5])mesh(host.body,new THREE.BoxGeometry(1.2,.7,.45),materials.plastic(0xb1a58c,{roughness:.8}),[xPos,-4.8,-.1],'Joystick2 concealed passive package');
 const socket=connector(host.body,40);socket.name='Joystick2 red open-top HY2.0-4P';
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],
  pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],
  meta:{role:'visual-connector',face:'bottom',protocol:'I2C',scope:'Physical connector and cable attachment only; no electrical or bus behavior'}}));
 screw(host.body,[0,-8,-3.98],'back',1.4);const shank=cylinder(host.body,.65,1.6,[0,-8,-2.65],materials.metal(0x949c98,{roughness:.5}),'Joystick2 concealed mounting screw shank');
 host.add(new Component({id:'sensor',label:'Hall joystick appearance anchor',position:pivot,meta:{role:'visual-anchor',part:'JH16',scope:'No ADC values, Hall sensing, calibration, GPIO, I2C, registers or firmware'}}));
 host.joystick2Assembly={pcb,fixed,moving,shaft,press,x,y,rgb,socket,port,shank};
 host.unitStickers=addStickers(host);
}
