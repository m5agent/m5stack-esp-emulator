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
 // A single outside contour follows the open boss reliefs and bottom Grove
 // notch. No intersecting "hole" cuts fake the actual PCB boundary.
 const s=new THREE.Shape();s.moveTo(-6.5,14.6);s.lineTo(6.5,14.6);s.lineTo(10.5,11.7);s.lineTo(10.5,-.6);s.lineTo(8,-.6);
 s.absarc(8,-4,3.4,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.5,-7.4);s.lineTo(10.5,-11.7);s.lineTo(6.5,-14.6);s.lineTo(5.6,-14.6);s.lineTo(5.6,-9.3);s.lineTo(-5.6,-9.3);s.lineTo(-5.6,-14.6);s.lineTo(-6.5,-14.6);s.lineTo(-10.5,-11.7);s.lineTo(-10.5,-7.4);s.lineTo(-8,-7.4);
 s.absarc(-8,-4,3.4,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.5,-.6);s.lineTo(-10.5,11.7);s.closePath();bore(s,0,-4,1.9);
 for(const x of[-3,-1,1,3])bore(s,x,-8.85,.32);
 for(const x of spec.io.columnX)for(const y of[9.25,6.71])bore(s,x,y,.5);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:40}),materials.plastic(0x1c2922,{roughness:.92}),[0,0,-1.2],'EXT.IO2 physical PCB with open mounting and Grove relief');
 pcb.userData={role:'physical-pcb',scope:'Installed plane, thickness and concealed outline inferred from exact shell and photos; not fabrication data'};return pcb;
}
function stm32(host){
 const group=new THREE.Group();group.name='EXT.IO2 physical STM32F030F4P6 20-lead assembly';group.position.set(0,3,-.4);host.body.add(group);
 const metal=materials.metal(0xb3b7ad,{roughness:.48}),black=materials.plastic(0x1b211c,{roughness:.85}),leads=[];
 const body=mesh(group,new THREE.BoxGeometry(4.4,6.5,1),black,[0,0,.7],'STM32F030F4P6 TSSOP20 molded body');
 for(let i=0;i<10;i++)for(const side of[-1,1]){
  const y=(i-4.5)*.65;
  leads.push(mesh(group,new THREE.BoxGeometry(.75,.3,.12),metal,[side*2.88,y,.06],'STM32 TSSOP20 solder foot'));
  leads.push(mesh(group,new THREE.BoxGeometry(.16,.3,.51),metal,[side*2.55,y,.3],'STM32 TSSOP20 gull-wing riser'));
  leads.push(mesh(group,new THREE.BoxGeometry(.55,.3,.12),metal,[side*2.35,y,.55],'STM32 TSSOP20 shoulder'));
 }
 const marker=mesh(group,new THREE.CylinderGeometry(.17,.17,.02,20).rotateX(Math.PI/2),materials.plastic(0x5b6258,{roughness:.9}),[-1.57,-2.64,1.21],'STM32 physical pin-one indentation');
 group.userData={role:'physical-sensor-package',part:'STM32F030F4P6',scope:'Package outline and installed XYZ are photo reconstruction; no GPIO, ADC, servo, PWM, RGB, bus or firmware logic'};return{group,body,leads,marker};
}
function ioHeader(host){
 const group=new THREE.Group();group.name='EXT.IO2 physical P2 right-angle male 2×5 header';host.body.add(group);
 const black=materials.plastic(0x131914,{roughness:.8}),metal=materials.metal(0xbcb8a1,{roughness:.47});
 const carrier=mesh(group,new THREE.BoxGeometry(12.7,2.4,5.08),black,[0,10.8,2.31],'P2 complete 2×5 molded pin carrier'),contacts=[],legs=[];
 // Real squared male contact tips and bent PCB legs. The two rows occupy
 // different bend depths; the mating envelope stays inside the native mouth.
 for(let col=0;col<5;col++)for(let row=0;row<2;row++){
  const x=spec.io.columnX[col],z=spec.io.rowZ[row],bendY=9.25-row*2.54;
  const tip=mesh(group,new THREE.BoxGeometry(.64,15.7-bendY,.64),metal,[x,(15.7+bendY)/2,z],`P2 metal male contact row ${row+1} column ${col+1}`);
  tip.userData={row:row+1,column:col+1,pin:col*2+row+1};contacts.push(tip);
  legs.push(mesh(group,new THREE.BoxGeometry(.64,.64,z+1.45),metal,[x,bendY,(z-1.45)/2],`P2 right-angle pin vertical solder leg ${row+1}/${col+1}`));
  const pad=new THREE.Shape();pad.absarc(0,0,.72,0,Math.PI*2,false);const hole=new THREE.Path();hole.absarc(0,0,.49,0,Math.PI*2,true);pad.holes.push(hole);
  legs.push(mesh(group,new THREE.ExtrudeGeometry(pad,{depth:.1,bevelEnabled:false,curveSegments:24}),metal,[x,bendY,-1.3],`P2 annular solder pad ${row+1}/${col+1}`));
 }
 // Rear-label pin map is explicit: when looking at the rear label, its columns
 // left-to-right are VCC/IO6/IO4/IO2/IO0. Front-axis +X is label-view left.
 const names=['IO0','IO1','IO2','IO3','IO4','IO5','IO6','IO7','VCC','GND'];
 const port=host.add(new Port({id:'io',label:'P2 · 2×5 / 2.54 mm male IO',connector:spec.io.connector,position:spec.io.position,quaternion:portQuaternion('top'),hitSize:[12.8,.8,5.2],pins:names.map((name,i)=>({n:i+1,name})),
  pinGrid:{cols:5,rows:2,pitch:2.54,center:[0,0],order:(col,row)=>col*2+(row===0?2:1)},meta:{role:'visual-connector',face:'top',part:'P2',scope:'Physical 10-pin attachment and pin legend only; connector type does not accept Grove; no GPIO/electrical behavior',pinMapping:'Schematic P2 pins 1–8=IO0–IO7, 9=VCC, 10=GND; front-axis columns -X to +X are IO0/1, IO2/3, IO4/5, IO6/7, VCC/GND; rear-near row GND/odd, front-near row VCC/even'}}));
 group.userData={role:'physical-connector',part:'P2',inferred:'Bend path, carrier and datum reconstructed from exact U011-B photo; not mechanical-mating tolerances'};
 return{group,carrier,contacts,legs,port};
}
function electronics(host){
 const dark=materials.plastic(0x252b23,{roughness:.84}),metal=materials.metal(0xb8b9af,{roughness:.54}),ceramic=materials.plastic(0xa69d7b,{roughness:.9}),parts=[];
 const regulator=mesh(host.body,new THREE.BoxGeometry(3,1.7,1.1),dark,[-6.7,3.7,.2],'EXT.IO2 HT7533 physical regulator');parts.push(regulator);
 for(const x of[-7.65,-6.7,-5.75])parts.push(mesh(host.body,new THREE.BoxGeometry(.4,.75,.13),metal,[x,2.7,-.32],'HT7533 physical solder lead'));
 for(const[x,y]of[[8.3,9.8],[8.3,7.5],[8.3,5.2],[8.3,2.9],[-6.8,6.3],[-6.8,.9],[5,3],[5,.8],[8.3,.6]]){
  parts.push(mesh(host.body,new THREE.BoxGeometry(1.35,.85,.5),ceramic,[x,y,-.15],'EXT.IO2 passive resistor/capacitor body'));
  for(const sign of[-1,1])parts.push(mesh(host.body,new THREE.BoxGeometry(.27,.85,.52),metal,[x+sign*.55,y,-.15],'EXT.IO2 passive termination'));
 }
 // P1 is documented as a five-node SWD connection, but the assembled product
 // photos do not establish an exposed socket or populated pin strip. Fixed,
 // concealed pads record that connection without inventing an outside Port.
 const swdPads=[];for(let i=0;i<5;i++)swdPads.push(mesh(host.body,new THREE.CylinderGeometry(.43,.43,.08,24).rotateX(Math.PI/2),metal,[-4.8+i*2.4,.5,-1.25],'EXT.IO2 inferred concealed P1 SWD pad'));
 return{regulator,parts,swdPads};
}
export function buildEXTIO2(host){
 const native=addCadParts(host,data,{shell:materials.plastic(0xe8eae5,{roughness:.77})});
 const pcb=board(host),chip=stm32(host),io=ioHeader(host),supportElectronics=electronics(host);
 const socket=connector(host.body,32,false,{height:5.2});socket.position.z=-1.1;socket.name='EXT.IO2 red physical open-top HY2.0-4P';socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'I2C',scope:'Physical mating/cable pose only; no bus, address, GPIO, ADC, servo, PWM or RGB state'}}));
 const fixing=screw(host.body,[0,-4,-4.91],'back',1.4),shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,1.6,32).rotateX(Math.PI/2),materials.metal(0xa2aaa2),[0,-4,-3.6],'EXT.IO2 physical fastening shank');
 host.add(new Component({id:'sensor',label:'STM32F030F4P6 visual package anchor',position:[0,3,.8],meta:{role:'visual-anchor',part:'STM32F030F4P6',scope:'Passive geometry anchor only; no sensor values, GPIO, ADC, PWM, servo, RGB, I2C or firmware behavior'}}));
 const stickers=addStickers(host);host.extio2Assembly={native,pcb,chip,io,supportElectronics,socket,port,fixing,shank,stickers};
}
