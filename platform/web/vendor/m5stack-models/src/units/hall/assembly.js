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
 // Scallops clear the native mounting bosses; the Grove notch is an open contour.
 const s=new THREE.Shape();s.moveTo(-7,14.4);s.lineTo(7,14.4);s.lineTo(10.4,11.0);s.lineTo(10.4,-.6);s.lineTo(8,-.6);
 s.absarc(8,-4,3.4,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-7.4);s.lineTo(10.4,-11);s.lineTo(7,-14.4);s.lineTo(5.3,-14.4);s.lineTo(5.3,-8.5);s.lineTo(-5.3,-8.5);s.lineTo(-5.3,-14.4);s.lineTo(-7,-14.4);s.lineTo(-10.4,-11);s.lineTo(-10.4,-7.4);s.lineTo(-8,-7.4);
 s.absarc(-8,-4,3.4,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.4,-.6);s.lineTo(-10.4,11);s.closePath();
 bore(s,0,-4,1.9);for(const x of[-3,-1,1,3])bore(s,x,-8.15,.32);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:48}),materials.plastic(0x176d45,{roughness:.93}),[0,0,-.4],'Hall physical PCB with true fastening and solder bores');
 pcb.userData={role:'physical-pcb',scope:'Visual board reconstruction inside native shell; silhouette, thickness and installed plane inferred'};
 const pads=[],metal=materials.metal(0xb5b9b0,{roughness:.45});for(const x of[-3,-1,1,3]){
  const p=new THREE.Shape();p.absarc(x,-8.15,.57,0,Math.PI*2,false);bore(p,x,-8.15,.32);
  pads.push(mesh(host.body,new THREE.ExtrudeGeometry(p,{depth:.05,bevelEnabled:false,curveSegments:32}),metal,[0,0,-.45],'Hall rear Grove solder annulus'));
 }return{pcb,pads};
}
function electronics(host){
 const dark=materials.plastic(0x292c27,{roughness:.84}),metal=materials.metal(0xb7b9ad,{roughness:.5}),ceramic=materials.plastic(0xb09e75,{roughness:.9}),sensors=[],parts=[];
 for(const [i,x]of[-6,0,6].entries()){
  const frame=new THREE.Group();frame.name=`Hall A3144E U${i+1} physical sensor package`;frame.position.set(x,10.0,.4);host.body.add(frame);
  // Faceted UA molded envelope with flat sensing face. Exact installed datum is unknown.
  const body=new THREE.Shape();body.moveTo(-1.7,-1.45);body.lineTo(1.7,-1.45);body.lineTo(2.04,-1.05);body.lineTo(2.04,1.05);body.lineTo(1.7,1.45);body.lineTo(-1.7,1.45);body.lineTo(-2.04,1.05);body.lineTo(-2.04,-1.05);body.closePath();
  const chip=mesh(frame,new THREE.ExtrudeGeometry(body,{depth:1.5,bevelEnabled:false}),dark,[0,0,.04],`Hall U${i+1} A3144E molded UA body`);const leads=[];
  for(const dx of[-1.27,0,1.27])leads.push(mesh(frame,new THREE.BoxGeometry(.38,2.0,.18),metal,[dx,-2.2,.09],`Hall U${i+1} A3144E fixed metal lead`));
  frame.userData={role:'physical-sensor-package',part:'A3144E',scope:'Concealed visual package only; envelope and installed XYZ inferred; no magnetic sensing, polarity or digital logic'};sensors.push({frame,chip,leads});
 }
 const logic=mesh(host.body,new THREE.BoxGeometry(3.9,8.65,1.55),dark,[4.3,1.6,1.225],'Hall U4 74HC08D SO14 body');
 const logicLeads=[];for(const side of[-1,1])for(let j=0;j<7;j++)logicLeads.push(mesh(host.body,new THREE.BoxGeometry(.85,.4,.22),metal,[4.3+side*2.22,1.6+(j-3)*1.27,.51],'Hall U4 74HC08D fixed solder lead'));
 const regulator=mesh(host.body,new THREE.BoxGeometry(4.5,2.5,1.45),dark,[-4.2,1.5,1.175],'Hall U5 HT7533 SOT89 body');for(const dx of[-1.5,0,1.5])parts.push(mesh(host.body,new THREE.BoxGeometry(.45,1.05,.18),metal,[-4.2+dx,-.12,.49],'Hall U5 HT7533 solder lead'));
 mesh(host.body,new THREE.BoxGeometry(2.7,.7,.18),metal,[-4.2,3.1,.49],'Hall U5 HT7533 heat tab');
 const passiveDefs=[['R1',-7.8,6.4,'resistor'],['R2',-1.8,6.4,'resistor'],['R3',4.2,6.4,'resistor'],['R4',7.6,4.8,'resistor'],['C1',-7.8,4.5,'capacitor'],['C2',-1.8,4.5,'capacitor'],['C3',1.5,4.5,'capacitor'],['C4',-7.8,1.8,'capacitor'],['C5',-6.6,-1.5,'capacitor'],['C6',-2.6,-1.5,'capacitor'],['C7',7.8,-1.6,'capacitor']];
 for(const [id,x,y,kind]of passiveDefs){parts.push(mesh(host.body,new THREE.BoxGeometry(1.2,.7,.5),kind==='resistor'?dark:ceramic,[x,y,.65],`Hall ${id} ${kind} package`));for(const dx of[-.48,.48])parts.push(mesh(host.body,new THREE.BoxGeometry(.25,.72,.52),metal,[x+dx,y,.65],`Hall ${id} metal termination`));}
 // D1 is confirmed red 0603, but exact exterior photos and source CAD do not
 // establish an exposed light path. Keep the physical hidden package, no Led API.
 const led=mesh(host.body,new THREE.BoxGeometry(1.6,.8,.6),materials.plastic(0x8b2622,{roughness:.5}),[7.8,3.1,.7],'Hall concealed D1 fixed red 0603 package');led.userData={role:'concealed-led-package',part:'D1 red 0603',scope:'Physical hidden package only; installed XYZ inferred and no proven exterior optical path'};
 for(const dx of[-.65,.65])parts.push(mesh(host.body,new THREE.BoxGeometry(.3,.82,.24),metal,[7.8+dx,3.1,.52],'Hall D1 solder termination'));
 return{sensors,logic,logicLeads,regulator,parts,led};
}
export function buildHall(host){
 addCadParts(host,data,{shell:materials.plastic(0xe8eae5,{roughness:.77})});const pcb=board(host),physicalElectronics=electronics(host);
 const socket=connector(host.body,32,true,{height:5.2});socket.name='Hall black open-top HY2.0-4P';
 const port=host.add(new Port({id:'grove',label:'PORT.B · Digital Output',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'NC',color:'yellow'},{n:4,name:'OUT',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'GPIO',scope:'Physical connector, attachment and cable pose only; no GPIO, magnetic sensing, digital logic, electrical state or firmware'}}));
 const fixing=screw(host.body,[0,-4,-3.97],'back',1.4),shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,2.2,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,-4,-2.8],'Hall fastening screw shank');
 host.add(new Component({id:'sensor',label:'Three A3144E visual package anchor',position:[0,10,1.94],meta:{role:'visual-anchor',part:'A3144E × 3',scope:'Passive visual anchor only; no magnetic field, polarity, threshold, digital output, LED linkage, sensor acquisition, GPIO or firmware'}}));
 addStickers(host);host.hallAssembly={pcb,electronics:physicalElectronics,socket,port,fixing,shank};
}
