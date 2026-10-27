import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
function bore(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(h);}
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:40}),material,position,name);}
function board(host){
 // Mounting-boss relief is open to the exterior rather than intersecting holes.
 const s=new THREE.Shape();s.moveTo(-6.4,22.4);s.lineTo(6.4,22.4);s.lineTo(10.4,18.4);s.lineTo(10.4,-8.6);s.lineTo(8,-8.6);
 s.absarc(8,-12,3.4,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-15.4);s.lineTo(10.4,-18.4);s.lineTo(6.4,-22.4);
 s.lineTo(5.6,-22.4);s.lineTo(5.6,-16.5);s.lineTo(-5.6,-16.5);s.lineTo(-5.6,-22.4);s.lineTo(-6.4,-22.4);s.lineTo(-10.4,-18.4);s.lineTo(-10.4,-15.4);s.lineTo(-8,-15.4);
 s.absarc(-8,-12,3.4,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.4,-8.6);s.lineTo(-10.4,18.4);s.closePath();bore(s,0,-12,1.9);
 for(const x of[-3,-1,1,3])bore(s,x,-16.1,.32);
 const pcb=solid(host.body,s,.8,[0,0,-.4],materials.plastic(0x22362b,{roughness:.94}),'RTC physical PCB with open mounting and Grove relief');
 pcb.userData={role:'physical-pcb',scope:'Concealed outline and installed plane reconstructed from shell clearance; not a production PCB'};return pcb;
}
function rtc(host){
 const group=new THREE.Group();group.name='RTC HYM8563 physical 8-lead package';group.position.set(0,-.8,.4);host.body.add(group);
 const packageBody=mesh(group,new THREE.BoxGeometry(4.9,3.9,1.2),materials.plastic(0x242724,{roughness:.83}),[0,0,.8],'HYM8563 8-lead molded body');
 const metal=materials.metal(0xa9aca4,{roughness:.52}),leads=[];
 for(const x of[-1.905,-.635,.635,1.905])for(const side of[-1,1]){
  leads.push(mesh(group,new THREE.BoxGeometry(.42,.8,.15),metal,[x,side*2.55,.075],'HYM8563 gull-wing solder foot'));
  leads.push(mesh(group,new THREE.BoxGeometry(.42,.2,.65),metal,[x,side*2.2,.4],'HYM8563 gull-wing riser'));
  leads.push(mesh(group,new THREE.BoxGeometry(.42,.6,.15),metal,[x,side*1.95,.725],'HYM8563 gull-wing shoulder'));
 }
 const marker=mesh(group,new THREE.CylinderGeometry(.22,.22,.025,24).rotateX(Math.PI/2),materials.plastic(0x777a70,{roughness:.95}),[-1.8,-1.28,1.413],'HYM8563 molded pin-one indentation');
 group.userData={role:'physical-sensor-package',part:'HYM8563',scope:'Single concealed 8-lead package visual reconstruction; package alternative and installed XYZ inferred; no RTC or bus behavior'};
 return{group,packageBody,leads,marker};
}
function battery(host){
 const group=new THREE.Group();group.name='RTC concealed built-in button-cell assembly';group.position.set(0,12,0);host.body.add(group);
 const metal=materials.metal(0xb6bbb2,{roughness:.4}),dark=materials.plastic(0x3b4037,{roughness:.85}),tabs=[];
 // The source confirms a built-in button cell but gives no production holder
 // or battery dimensions. These fixed unmarked supports are expressly inferred.
 const support=mesh(group,new THREE.CylinderGeometry(6.6,6.6,.2,64).rotateX(Math.PI/2),dark,[0,0,.5],'RTC inferred concealed cell insulating support');
 const negative=mesh(group,new THREE.CylinderGeometry(5.7,5.7,.22,64).rotateX(Math.PI/2),metal,[0,0,.71],'RTC unmarked button-cell negative cap');
 const gasket=mesh(group,new THREE.CylinderGeometry(6.21,6.21,.18,64).rotateX(Math.PI/2),dark,[0,0,.91],'RTC button-cell insulating gasket');
 const can=mesh(group,new THREE.CylinderGeometry(6.25,6.25,1.8,80).rotateX(Math.PI/2),metal,[0,0,1.7],'RTC unmarked built-in button-cell positive can');
 // Real metal solids give the concealed battery conductive support. Their tab
 // arrangement is illustrative; the model does not assert a replaceable holder.
 tabs.push(mesh(group,new THREE.BoxGeometry(2.2,3.5,.18),metal,[0,-6.25,.52],'RTC inferred fixed battery negative contact tongue'));
 tabs.push(mesh(group,new THREE.BoxGeometry(2.2,.18,2),metal,[0,6.5,1.5],'RTC inferred fixed battery positive side tab'));
 tabs.push(mesh(group,new THREE.BoxGeometry(2.2,3,.18),metal,[0,5.1,2.63],'RTC inferred fixed battery positive top contact'));
 tabs.push(mesh(group,new THREE.BoxGeometry(2.2,1.5,.18),metal,[0,7.15,.5],'RTC inferred fixed battery solder foot'));
 group.userData={role:'physical-battery-assembly',model:null,removable:false,inferred:true,scope:'Unmarked built-in coin-cell and metal support visual estimate; no confirmed battery BOM, removable holder, charge, voltage or capacity model'};
 return{group,support,negative,gasket,can,tabs};
}
function electronics(host){
 const parts=[],dark=materials.plastic(0x252824,{roughness:.85}),metal=materials.metal(0xb6b9b0,{roughness:.58}),ceramic=materials.plastic(0xafa17c,{roughness:.9});
 const crystal=mesh(host.body,new THREE.CylinderGeometry(1,1,5,40),metal,[-6.6,0,1.4],'RTC 32.768 kHz cylindrical metal crystal');parts.push(crystal);
 for(const y of[-3.1,3.1])parts.push(mesh(host.body,new THREE.BoxGeometry(.22,1.4,.22),metal,[-6.6,y,.65],'RTC crystal lead'));
 parts.push(mesh(host.body,new THREE.BoxGeometry(3,1.7,.95),dark,[5.8,-5,1.075],'RTC HT7533 regulator body'));
 for(const x of[4.85,5.8,6.75])parts.push(mesh(host.body,new THREE.BoxGeometry(.4,.8,.12),metal,[x,-6.1,.46],'RTC regulator solder lead'));
 parts.push(mesh(host.body,new THREE.BoxGeometry(2.1,1.2,.8),dark,[-5.6,-5,1],'RTC BAV74 dual-diode body'));
 for(const[x,y]of[[-2.4,3.2],[0,3.2],[2.4,3.2],[-2.8,-5],[0,-5],[2.8,-5],[7.6,0],[7.6,2.2]]){
  parts.push(mesh(host.body,new THREE.BoxGeometry(1.3,.8,.5),ceramic,[x,y,.65],'RTC concealed resistor or capacitor body'));
  for(const dx of[-.52,.52])parts.push(mesh(host.body,new THREE.BoxGeometry(.27,.8,.52),metal,[x+dx,y,.65],'RTC passive metal termination'));
 }
 return{crystal,parts};
}
export function buildRTC(host){
 addCadParts(host,data,{shell:materials.plastic(0xe8eae5,{roughness:.76})});
 const pcb=board(host),chip=rtc(host),cell=battery(host),supportElectronics=electronics(host);
 const socket=connector(host.body,48,false,{height:5.2});socket.name='RTC red open-top HY2.0-4P';socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],
 pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'I2C',scope:'Physical connector, attachment and cable pose only; no time/calendar, alarm, battery or electrical behavior'}}));
 const fixing=screw(host.body,[0,-12,-3.97],'back',1.4),shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,1.6,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,-12,-2.65],'RTC concealed fastening screw shank');
 host.add(new Component({id:'sensor',label:'HYM8563 visual package anchor',position:[0,-.8,1.8],meta:{role:'visual-anchor',part:'HYM8563',scope:'Passive anchor only; no time, date, alarm, oscillator, battery state, I2C or autonomous behavior'}}));
 addStickers(host);
 host.rtcAssembly={pcb,chip,cell,supportElectronics,socket,port,fixing,shank};
}
