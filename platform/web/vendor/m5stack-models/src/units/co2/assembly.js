import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';

function bore(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(h);}
function extrude(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:32}),material,position,name);}
function board(host){
 // The exterior opens around both native bosses and the Grove connector:
 // no circular hole crosses the outside edge of this PCB.
 const s=new THREE.Shape();s.moveTo(-6.4,21.8);s.lineTo(6.4,21.8);s.lineTo(10.4,17.8);s.lineTo(10.4,-7.65);s.lineTo(8,-7.65);
 s.absarc(8,-12,4.35,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-16.35);s.lineTo(10.4,-17.8);s.lineTo(6.4,-21.8);
 s.lineTo(5.6,-21.8);s.lineTo(5.6,-16.5);s.lineTo(-5.6,-16.5);s.lineTo(-5.6,-21.8);s.lineTo(-6.4,-21.8);
 s.lineTo(-10.4,-17.8);s.lineTo(-10.4,-16.35);s.lineTo(-8,-16.35);s.absarc(-8,-12,4.35,Math.PI*1.5,Math.PI*2.5,false);
 s.lineTo(-10.4,-7.65);s.lineTo(-10.4,17.8);s.closePath();bore(s,0,-12,2.1);
 for(const x of [-3,-1,1,3])bore(s,x,-16.9,.32);
 const pcb=extrude(host.body,s,.8,[0,0,-4.6],materials.plastic(0x284b3d,{roughness:.88}),'CO2 physical PCB with open mounting-boss and Grove relief');
 pcb.userData={role:'physical-pcb',scope:'Visual reconstruction, not trace-level electrical or production assembly geometry'};return pcb;
}
function sensor(host){
 const group=new THREE.Group();group.name='SCD40 physical sensor package';group.position.set(0,8,-3.78);host.body.add(group);
 const substrate=mesh(group,new THREE.BoxGeometry(10.1,10.1,.8),materials.plastic(0x313b30,{roughness:.75}),[0,0,.4],'SCD40 ceramic package substrate');
 const gold=materials.metal(0xb0a579,{roughness:.48});
 const lower=extrude(group,roundedRect(8.5,8.5,1.1),2.8,[0,0,.8],gold,'SCD40 rounded lower metal can');
 const upper=extrude(group,roundedRect(7.8,7.8,.95),2.62,[0,0,3.6],gold,'SCD40 rounded upper metal can');
 // Physical white gas-permeable membrane, including its polarity notch.
 const s=new THREE.Shape();s.moveTo(-2.9,1.6);s.lineTo(-1.6,2.9);s.lineTo(2.9,2.9);s.lineTo(2.9,-2.9);s.lineTo(-2.9,-2.9);s.closePath();
 const membrane=extrude(group,s,.08,[0,0,6.22],materials.plastic(0xe1e1d5,{roughness:1}),'SCD40 physical white protection membrane');
 const pads=[];for(let side=0;side<4;side++)for(let i=0;i<5;i++){
  const x=(i-2)*1.25,y=4.8;const p=mesh(group,new THREE.BoxGeometry(.7,.5,.16),gold,[side===0?x:side===1?y:side===2?-x:-y,side===0?y:side===1?-x:side===2?-y:x,.1],'SCD40 package perimeter contact');p.rotation.z=side*Math.PI/2;pads.push(p);
 }
 group.userData={role:'physical-sensor-package',part:'SCD40',scope:'Passive visual enclosure and membrane; no gas, temperature, humidity, protocol or electrical simulation',inferred:spec.source.inferred};
 return {group,substrate,lower,upper,membrane,pads};
}
function powerParts(host){
 const black=materials.plastic(0x202723,{roughness:.8}),metal=materials.metal(0xb7b4a7,{roughness:.6}),ceramic=materials.plastic(0xa99a73,{roughness:.9});
 const parts=[mesh(host.body,new THREE.BoxGeometry(3,3,1.5),materials.plastic(0x4a4a40),[6.5,-2,-3.03],'CO2 L1 3015 inductor'),mesh(host.body,new THREE.BoxGeometry(1.7,1.5,.65),black,[2,-2,-3.455],'CO2 buck regulator package')];
 for(const [x,y]of [[-6.5,-1],[-6.5,-4],[6.5,-6],[3.6,-5],[-3.6,-5]]){parts.push(mesh(host.body,new THREE.BoxGeometry(1.5,.8,.55),ceramic,[x,y,-3.505],'CO2 ceramic capacitor'));for(const dx of [-.6,.6])parts.push(mesh(host.body,new THREE.BoxGeometry(.3,.8,.57),metal,[x+dx,y,-3.495],'CO2 capacitor termination'));}
 for(const[x,y]of[[-7,17],[7,17],[-7,1],[7,1],[-2,-7],[2,-7]])parts.push(mesh(host.body,new THREE.BoxGeometry(1.1,.65,.4),black,[x,y,-3.58],'CO2 small protection or resistor package'));
 return parts;
}
export function buildCO2(host){
 addCadParts(host,data,{shell:materials.plastic(0xe6e7e2,{roughness:.8})});
 const pcb=board(host),scd40=sensor(host),power=powerParts(host);
 const socket=connector(host.body,48,false,{height:5.2});socket.position.z=-4;socket.name='CO2 red open-top HY2.0-4P';socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],
  pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],
  meta:{role:'visual-connector',face:'bottom',protocol:'I2C',scope:'Physical connector, attachment and cable pose only; no bus or electrical behavior'}}));
 screw(host.body,[0,-12,-7.97],'back',1.4);
 const shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,2.4,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,-12,-5.5],'CO2 concealed fastening screw shank');
 host.add(new Component({id:'sensor',label:'SCD40 visual package anchor',position:[0,8,2.52],meta:{role:'visual-anchor',part:'SCD40',scope:'No commands, sensor values, gas physics, I2C, electrical or automatic light behavior'}}));
 addStickers(host);
 host.co2Assembly={pcb,scd40,power,socket,port,shank};
}
