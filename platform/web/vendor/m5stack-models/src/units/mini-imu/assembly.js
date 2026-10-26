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
 // Real exterior scallops clear native mounting bosses; no intersecting holes.
 const s=new THREE.Shape();s.moveTo(-7,10.4);s.lineTo(7,10.4);s.lineTo(10.4,7);s.lineTo(10.4,3.4);s.lineTo(8,3.4);
 s.absarc(8,0,3.4,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-3.4);s.lineTo(10.4,-7);s.lineTo(7,-10.4);s.lineTo(-7,-10.4);s.lineTo(-10.4,-7);s.lineTo(-10.4,-3.4);s.lineTo(-8,-3.4);
 s.absarc(-8,0,3.4,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.4,3.4);s.lineTo(-10.4,7);s.closePath();bore(s,0,0,1.9);
 for(const x of[-3,-1,1,3])bore(s,x,-4.85,.32);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:48}),materials.plastic(0x147548,{roughness:.93}),[0,0,-.4],'Mini IMU physical scalloped PCB with true mounting and solder holes');
 pcb.userData={role:'physical-pcb',scope:'Board silhouette constrained by exact official U095 rear photo; installed plane/thickness inferred'};
 const pads=[],metal=materials.metal(0xb5b9b0,{roughness:.45});
 for(const x of[-3,-1,1,3]){
  const p=new THREE.Shape();p.absarc(x,-4.85,.57,0,Math.PI*2,false);bore(p,x,-4.85,.32);
  pads.push(mesh(host.body,new THREE.ExtrudeGeometry(p,{depth:.05,bevelEnabled:false,curveSegments:32}),metal,[0,0,-.45],'Mini IMU rear Grove solder annulus'));
 }
 return{pcb,pads};
}
function electronics(host){
 const dark=materials.plastic(0x292c27,{roughness:.84}),metal=materials.metal(0xb7b9ad,{roughness:.5}),ceramic=materials.plastic(0xb09e75,{roughness:.9}),parts=[];
 const sensorGroup=new THREE.Group();sensorGroup.position.set(0,6,.4);sensorGroup.name='Mini IMU MPU6886 physical sensor package';host.body.add(sensorGroup);
 const chip=mesh(sensorGroup,new THREE.BoxGeometry(3,3,.9),dark,[0,0,.53],'MPU6886 molded QFN body');
 const leads=[];
 for(const side of[-1,1])for(const a of[-1,-.6,-.2,.2,.6,1]){
  leads.push(mesh(sensorGroup,new THREE.BoxGeometry(.2,.28,.12),metal,[a,side*1.46,.06],'MPU6886 QFN exposed solder terminal'));
  leads.push(mesh(sensorGroup,new THREE.BoxGeometry(.28,.2,.12),metal,[side*1.46,a,.06],'MPU6886 QFN exposed solder terminal'));
 }
 const pinOne=mesh(sensorGroup,new THREE.CylinderGeometry(.15,.15,.02,24).rotateX(Math.PI/2),materials.plastic(0x636960),[-1,1,.991],'MPU6886 molded pin-one marker');
 sensorGroup.userData={role:'physical-sensor-package',part:'MPU6886',scope:'Concealed visual package; package envelope and installed XYZ inferred; no sensor data or motion processing'};
 parts.push(mesh(host.body,new THREE.BoxGeometry(2.9,1.6,1.05),dark,[-5.8,6,.975],'Mini IMU HT7533 regulator body'));
 for(const x of[-6.75,-5.8,-4.85])parts.push(mesh(host.body,new THREE.BoxGeometry(.4,.8,.13),metal,[x,4.9,.465],'Mini IMU regulator solder lead'));
 for(const[x,y]of[[-4.8,-6.1],[4.8,-6.1]]){
  parts.push(mesh(host.body,new THREE.BoxGeometry(1.3,2.2,.85),dark,[x,y,.825],'Mini IMU BSS138 level-shifter package'));
  for(const[dx,dy]of[[-.8,-.65],[-.8,.65],[.8,0]])parts.push(mesh(host.body,new THREE.BoxGeometry(.6,.35,.12),metal,[x+dx,y+dy,.46],'Mini IMU BSS138 solder lead'));
 }
 for(const[x,y]of[[-3.3,8.4],[-3.3,4],[3.3,8.4],[3.3,4],[5.9,6],[5.9,8.5],[-6.8,-8.1],[6.8,-8.1]]){
  parts.push(mesh(host.body,new THREE.BoxGeometry(1.2,.7,.5),ceramic,[x,y,.65],'Mini IMU resistor or capacitor body'));
  for(const dx of[-.48,.48])parts.push(mesh(host.body,new THREE.BoxGeometry(.25,.72,.52),metal,[x+dx,y,.65],'Mini IMU passive metal termination'));
 }
 return{sensorGroup,chip,leads,pinOne,parts};
}
export function buildMiniIMU(host){
 addCadParts(host,data,{shell:materials.plastic(0xe8eae5,{roughness:.77})});
 const pcb=board(host),physicalElectronics=electronics(host);
 const socket=connector(host.body,24,false,{height:5.2});socket.name='Mini IMU red open-top HY2.0-4P';
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'I2C',scope:'Physical connector, attachment and cable pose only; no I2C, inertial measurements, calibration, fusion or electrical behavior'}}));
 const fixing=screw(host.body,[0,0,-3.97],'back',1.4),shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,2.2,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,0,-2.8],'Mini IMU fastening screw shank');
 host.add(new Component({id:'sensor',label:'MPU6886 visual package anchor',position:[0,6,1.4],meta:{role:'visual-anchor',part:'MPU6886',scope:'Passive visual anchor only; no acceleration, gyroscope, temperature, tilt, motion, calibration, I2C or firmware behavior'}}));
 addStickers(host);host.miniImuAssembly={pcb,electronics:physicalElectronics,socket,port,fixing,shank};
}
