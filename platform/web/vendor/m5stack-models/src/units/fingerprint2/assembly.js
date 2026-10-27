import * as THREE from 'three';
import {Component,Led,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function bore(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);shape.holes.push(h);}
function solid(parent,shape,depth,p,mat,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:64}),mat,p,name);}
function cylinder(parent,r,depth,p,mat,name){return mesh(parent,new THREE.CylinderGeometry(r,r,depth,80).rotateX(Math.PI/2),mat,p,name);}
function annulus(parent,outer,inner,depth,p,mat,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,tau,true);bore(s,0,0,inner);return solid(parent,s,depth,p,mat,name);}
class BluePowerIndicator extends Led{
 set(state){if(typeof state==='string'||typeof state==='number')state={on:true};else if(state&&typeof state==='object')state={...state,color:0x267bff};super.set(state);}
}
class RingIndicator extends Led{
 set(state){super.set(state);this.glow.visible=false;}
}
function board(host){
 // The outer edge opens around both native mounting bosses and the connector;
 // separate clockwise exterior and CCW bores preserve inward bore-wall hits.
 const s=new THREE.Shape();s.moveTo(-10.3,8);s.absarc(0,8,10.3,Math.PI,0,true);s.lineTo(10.3,-3.65);s.lineTo(8,-3.65);s.absarc(8,-8,4.35,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.3,-12.35);s.lineTo(10.3,-17.4);s.lineTo(8.8,-18.4);s.lineTo(5.6,-18.4);s.lineTo(5.6,-12.5);s.lineTo(-5.6,-12.5);s.lineTo(-5.6,-18.4);s.lineTo(-8.8,-18.4);s.lineTo(-10.3,-17.4);s.lineTo(-10.3,-12.35);s.lineTo(-8,-12.35);s.absarc(-8,-8,4.35,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.3,-3.65);s.closePath();bore(s,0,-8,1.8);
 for(const x of[-3,-1,1,3])bore(s,x,-12.1,.32);
 const pcb=solid(host.body,s,.8,[0,0,-1.0],materials.plastic(0x28372e,{roughness:.92}),'Fingerprint2 physical main PCB with open boss and Grove relief');
 pcb.userData={role:'physical-pcb',scope:'Appearance reconstruction; no traces or electrical state'};return pcb;
}
function fingerprintModule(host){
 const group=new THREE.Group();group.name='Fingerprint2 A-K323CP physical capacitive module';group.position.set(0,8,0);host.body.add(group);
 const dark=materials.plastic(0x202320,{roughness:.79}),matte=materials.plastic(0x151715,{roughness:.92});
 const carrier=cylinder(group,9.65,1.0,[0,0,.35],dark,'A-K323CP molded carrier');
 const substrate=cylinder(group,9.25,.6,[0,0,-.45],materials.plastic(0x25362a,{roughness:.91}),'A-K323CP circular sensor substrate');
 const backing=cylinder(group,8.8,2.4,[0,0,1.95],dark,'A-K323CP solid capacitive package support');
 const bezel=annulus(group,8.8,8.15,.55,[0,0,3.35],dark,'A-K323CP black annular bezel');
 const face=cylinder(group,8.15,.48,[0,0,3.69],matte,'A-K323CP solid matte capacitive sensing surface');
 const ringMesh=annulus(new THREE.Group(),9.64,8.80,.55,[0,0,0],materials.glossy(0x9da9a4,{roughness:.35}),'A-K323CP solid annular RGB diffuser');
 const ring=host.add(new RingIndicator({id:'ring-led',label:'A-K323CP RGB light ring',mesh:ringMesh,position:[0,8,3.35],color:0x00bfff,radius:.1,glowSize:0,
  meta:{role:'externally-driven-visual',colorMode:'rgb',hardwareColors:['blue','green','cyan','red','purple','yellow','white'],scope:'External colour/on/brightness only; default off. No autonomous breathing, recognition status, biometric capture, enrollment or UART commands.'}}));
 // The underlying LED package is a physical part; its installed form is inferred.
 const emitter=mesh(group,new THREE.BoxGeometry(1.6,.8,.6),materials.plastic(0xd7dbd4,{roughness:.6}),[0,-9.0,1.15],'A-K323CP recessed RGB emitter package');
 group.userData={role:'physical-sensor-package',part:'A-K323CP',type:'capacitive semiconductor',inferred:spec.source.inferred,scope:'Stationary sensing surface and carrier only; no fingerprint image, template, database, identity or sensor data'};
 return{group,carrier,substrate,backing,bezel,face,ring,emitter};
}
function electronics(host){
 const dark=materials.plastic(0x282b26,{roughness:.87}),parts=[];
 // All component locations below are concealed assembly estimates, not a BOM fit.
 parts.push(mesh(host.body,new THREE.BoxGeometry(4,4,.65),dark,[0,-1,-1.325],'Fingerprint2 STM32G031G8U6 package'));
 for(const[x,y]of[[-3.8,-2.8],[3.8,-2.8]])parts.push(mesh(host.body,new THREE.BoxGeometry(2.2,1.3,.7),dark,[x,y,-1.35],'Fingerprint2 TPAP7343D-33FS4 regulator'));
 for(const[x,y]of[[-5.5,0],[5.5,0],[-4.2,-5.1],[4.2,-5.1]])parts.push(mesh(host.body,new THREE.BoxGeometry(1.4,.8,.5),materials.plastic(0xb5a37a,{roughness:.9}),[x,y,-1.25],'Fingerprint2 decoupling capacitor'));
 const interconnect=mesh(host.body,new THREE.BoxGeometry(5.8,1.8,1.2),dark,[0,1,-1.6],'Fingerprint2 concealed J2 six-way module socket');parts.push(interconnect);
 for(let i=0;i<6;i++)parts.push(mesh(host.body,new THREE.BoxGeometry(.35,2.0,.35),materials.metal(0xa49b77),[-2.5+i,1,-1.6],'Fingerprint2 J2 contact'));
 const ledPackage=mesh(host.body,new THREE.BoxGeometry(1.6,.8,.6),materials.plastic(0xc5d0d7,{roughness:.6}),[7.9,-15.4,.1],'Fingerprint2 blue power LED package');parts.push(ledPackage);
 return{parts,ledPackage};
}
export function buildFingerprint2(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe8e9e4,{roughness:.83}),lens:materials.glossy(0xc5d0d7,{roughness:.3})});
 const pcb=board(host),sensorModule=fingerprintModule(host),support=electronics(host);
 const socket=connector(host.body,40,false,{height:5.2});socket.name='Fingerprint2 cyan open-top HY2.0-4P';socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.C · UART',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'UART_RX',color:'yellow'},{n:4,name:'UART_TX',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'UART',scope:'Attachment and four-wire cable pose only; no UART, electrical or biometric behavior'}}));
 // Use the complete native light-guide mesh with a reversible local translation.
 const lightGuide=parts['Fingerprint2 native blue power light guide'],p=[7.9,-16,3.6];lightGuide.geometry.translate(-p[0],-p[1],-p[2]);
 const power=host.add(new BluePowerIndicator({id:'power-led',label:'Blue power indicator',mesh:lightGuide,position:p,color:0x267bff,radius:.2,glowSize:2,meta:{role:'externally-driven-visual',colorMode:'fixed-blue',evidence:'Official U203 schematic LED1 BLUE; exact native light-guide triangles retained',scope:'Independent external on/brightness only; default off. Cable, ring and finger surface cause no automatic feedback.'}}));
 screw(host.body,[0,-8,-3.97],'back',1.4);const shank=cylinder(host.body,.65,1.6,[0,-8,-2.65],materials.metal(0x929997),'Fingerprint2 concealed fastening screw shank');
 const sensor=host.add(new Component({id:'sensor',label:'A-K323CP capacitive surface anchor',position:[0,8,3.93],meta:{role:'visual-anchor',part:'A-K323CP',sensorType:'capacitive',scope:'Stationary appearance only; no mechanical button, unconfirmed touch API, sensing, biometric capture, enrollment, recognition or database'}}));
 addStickers(host);
 host.fingerprint2Assembly={pcb,sensorModule,support,socket,port,power,sensor,shank};
}
