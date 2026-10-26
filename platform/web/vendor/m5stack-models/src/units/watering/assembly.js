import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import {Hose} from './Hose.js';
import {addStickers} from './stickers.js';
import data from './geometry-data.js';
const tau=Math.PI*2;
function bore(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,tau,false);s.holes.push(p);}
function extrude(parent,s,d,p,m,n){return mesh(parent,new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:56}),m,p,n);}
function circle(r){const s=new THREE.Shape();s.absarc(0,0,r,0,tau,false);return s;}
function ring(r,inner){const s=circle(r);bore(s,0,0,inner);return s;}
function probeShape(inset=0){const s=new THREE.Shape(),w=10.3-inset;s.moveTo(-w,55.5);s.lineTo(w,55.5);s.lineTo(w,116.5);s.quadraticCurveTo(w,121,w-2.1,125);s.lineTo(.65,136.15-inset);s.lineTo(0,136.8-inset);s.lineTo(-.65,136.15-inset);s.lineTo(-w+2.1,125);s.quadraticCurveTo(-w,121,-w,116.5);s.closePath();return s;}
function circuitry(host){
 const green=materials.plastic(0x163f31,{roughness:.94}),dark=materials.plastic(0x202420,{roughness:.85}),metal=materials.metal(0xb8b9a8,{roughness:.5}),ceramic=materials.plastic(0xab9872,{roughness:.85}),copper=materials.metal(0x8e623d,{roughness:.72});
 const boardShape=roundedRect(22.2,110,.3,{cy:.2});for(const[x,y]of spec.mountingHolesMm)bore(boardShape,x,y,2.7);bore(boardShape,0,-44,1.55);bore(boardShape,-6.8,43,1.35);bore(boardShape,6.8,43,1.35);
 const pcb=extrude(host.body,boardShape,1.0,[0,0,-2.6],green,'Watering physical fixed pump-drive PCB with four genuine mounting bores');pcb.userData.role='physical-pcb';
 const sensorBoard=extrude(host.body,roundedRect(16.4,20,1),.8,[0,39,-1.4],green,'Watering concealed capacitive sensor electronics PCB');
 const substrate=extrude(host.body,probeShape(),1.52,[0,0,-1.26],materials.plastic(0x252827,{roughness:.88}),'Watering real1.6mm single capacitive probe laminate substrate');substrate.userData.role='physical-probe-pcb';
 const electrodes=[],mask=[];for(const z of[-1.285,.26]){
  const e=extrude(host.body,probeShape(.7),.025,[0,0,z],copper,'Watering buried capacitive PAD electrode conductor');e.userData.role='physical-capacitive-electrode';electrodes.push(e);
  const outer=z<0?z-.015:z+.025;mask.push(extrude(host.body,probeShape(),.015,[0,0,outer],materials.plastic(0x101412,{roughness:.79}),'Watering black corrosion-resistant electrode soldermask'));
 }
 const parts=[];const chip=(name,x,y,w,h,d,z=-1.05)=>{const g=mesh(host.body,new THREE.BoxGeometry(w,h,d),dark,[x,y,z],name);parts.push(g);return g;};
 const tlc555=chip('Watering U1 TLC555I fixed8-lead timer package',0,39,4.9,3.9,1.2,-.8);for(const sign of[-1,1])for(let i=0;i<4;i++)parts.push(mesh(host.body,new THREE.BoxGeometry(.42,1,.18),metal,[(i-1.5)*1.27,39+sign*2.3,-1.28],'Watering TLC555I real solder lead'));
 const regulator=chip('Watering U2 XC6206 fixed LDO package',-5.2,46,2.9,1.5,.95);const mosfet=chip('Watering Q1 SI2302 fixed pump-drive MOSFET',-5.8,-37,2.9,1.5,.95);for(const[x,y]of[[-5.2,46],[-5.8,-37]])for(const[dx,dy]of[[-.9,-1],[.9,-1],[0,1]])parts.push(mesh(host.body,new THREE.BoxGeometry(.4,.7,.16),metal,[x+dx,y+dy,-1.28],'Watering SOT-23 fixed solder lead'));
 for(const[x,y]of[[4.8,46],[-4.8,34],[4.9,34],[-4.7,41],[4.9,41],[-4.2,49],[4.2,49],[-5.8,-41],[5,-39],[5,-35]]){parts.push(mesh(host.body,new THREE.BoxGeometry(1.6,.85,.6),ceramic,[x,y,-1.26],'Watering fixed sensing/driver resistor or capacitor'));for(const dx of[-.65,.65])parts.push(mesh(host.body,new THREE.BoxGeometry(.3,.88,.62),metal,[x+dx,y,-1.26],'Watering passive package termination'));}
 const cap=mesh(host.body,new THREE.CylinderGeometry(1.55,1.55,2.2,32).rotateX(Math.PI/2),dark,[3.5,-40,-.5],'Watering pump-board C1 fixed22uF output filter capacitor');
 for(const[x,y]of[[0,47.5],[0,-34]])parts.push(mesh(host.body,new THREE.BoxGeometry(3.1,1.2,1),dark,[x,y,-1.1],'Watering fixed4148 or ZMM3V3 diode package'));
 const link=[];for(const x of[-2,0,2]){link.push(mesh(host.body,new THREE.BoxGeometry(.5,8,.5),metal,[x,31,-.9],'Watering concealed3-wire sensor-board physical interconnect'));}
 return{pcb,sensorBoard,substrate,electrodes,mask,parts,tlc555,regulator,mosfet,cap,link};
}
function pump(host){
 const g=new THREE.Group();g.name='Watering fixed motor and diaphragm pump assembly';g.position.z=spec.pump.centerZ;host.body.add(g);const metal=materials.metal(0xb8bebc,{roughness:.41}),white=materials.plastic(0xe9e9e1,{roughness:.65}),dark=materials.plastic(0x333937,{roughness:.85}),deep=materials.plastic(0x101412,{roughness:.98});
 const motor=mesh(g,new THREE.CylinderGeometry(11.55,11.55,30,64),metal,[0,-22.5,0],'Watering physical stationary EDLP600-D12B motor can');
 const rear=mesh(g,new THREE.CylinderGeometry(11.3,11.3,3,64),dark,[0,-39,0],'Watering fixed rear motor end-cap with stationary electrical terminals');
 for(const side of[-1,1]){mesh(g,new THREE.BoxGeometry(1.15,3.2,2.2),metal,[side*5.5,-41.8,2.7],'Watering stationary motor solder lug');mesh(g,new THREE.BoxGeometry(2.5,1.4,1.1),dark,[side*5.5,-40.4,3.3],'Watering motor brush terminal insulator');}
 const shaft=mesh(g,new THREE.CylinderGeometry(1.2,1.2,5,24),metal,[0,-7.2,0],'Watering hidden fixed motor shaft, no exposed rotor or invented rotation');
 const canGeometry=new THREE.ExtrudeGeometry(ring(12.25,10.45),{depth:35,bevelEnabled:false,curveSegments:64}).rotateX(-Math.PI/2);const barrel=mesh(g,canGeometry,white,[0,-6.5,0],'Watering real hollow fixed diaphragm pump housing');
 mesh(g,new THREE.CylinderGeometry(10.5,10.5,1.4,64),white,[0,-5.8,0],'Watering fixed pump rear partition');
 const backing=mesh(g,new THREE.CylinderGeometry(10.45,10.45,.8,64),deep,[0,22.9,0],'Watering recessed concealed diaphragm backing beyond both open pipe lumens');
 const frontShape=circle(12.25);for(const z of[-5.4,5.4])bore(frontShape,0,-z,1.35);const frontGeo=new THREE.ExtrudeGeometry(frontShape,{depth:3.2,bevelEnabled:false,curveSegments:64}).rotateX(-Math.PI/2),front=mesh(g,frontGeo,white,[0,27.3,0],'Watering pump front cap with two real separate open water channels');
 const nozzles=[],ports={};for(const[id,z]of[['inlet',5.4],['outlet',-5.4]]){
  const nozzleGeo=new THREE.ExtrudeGeometry(ring(2.1,1.35),{depth:7.7,bevelEnabled:false,curveSegments:56}).rotateX(-Math.PI/2);const nozzle=mesh(g,nozzleGeo,white,[0,30.5,z],`Watering ${id} real bored pump nipple`);nozzles.push(nozzle);
  const raised=mesh(g,new THREE.ExtrudeGeometry(ring(2.25,1.35),{depth:.7,bevelEnabled:false,curveSegments:56}).rotateX(-Math.PI/2),white,[0,35.1,z],`Watering ${id} integral hose-retaining collar`);nozzles.push(raised);
  const pos=[0,38.2,spec.pump.centerZ+z];ports[id]=host.add(new Port({id,label:`Water pump ${id} tube nipple`,connector:spec.pump.connector,position:pos,quaternion:portQuaternion('top'),hitSize:[4.5,1,4.5],pins:[],meta:{role:'visual-connector',face:'top',mechanical:true,dimensionsInferred:true,outerDiameterMm:4.2,boreDiameterMm:2.7,scope:'Mechanical tube attachment and appearance only; no water, direction-dependent behavior, pump, flow, pressure, humidity, firmware or electrical function'}}));
 }
 const fasteners=[];for(const x of[-8.6,8.6]){const f=screw(g,[x,30.52,0],'top',1.45);f.name='Watering fixed pump-cap retaining screw';fasteners.push(f);}
 const wires=[];for(const[x,color]of[[-5.5,0x171a17],[5.5,0xa71a13]]){const c=new THREE.CatmullRomCurve3([new THREE.Vector3(x,-41,2.5),new THREE.Vector3(x,-43,1),new THREE.Vector3(x,-43,-9),new THREE.Vector3(x,-39,-15.4)]);wires.push(mesh(g,new THREE.TubeGeometry(c,16,.45,8,false),materials.plastic(color),[0,0,0],'Watering fixed concealed motor lead'))}
 return{group:g,motor,rear,shaft,barrel,backing,front,nozzles,ports,fasteners,wires};
}
function ties(host){
 const parts=[],black=materials.plastic(0x171b19,{roughness:.65});for(const y of[3.5,23]){
  const s=new THREE.Shape();s.moveTo(-11.7,-4.0);s.lineTo(11.7,-4.0);s.lineTo(13.25,15.75);s.absarc(0,15.75,13.25,0,Math.PI,false);s.lineTo(-11.7,-4.0);s.closePath();const inner=new THREE.Path();inner.moveTo(-11.05,-3.3);inner.lineTo(11.05,-3.3);inner.lineTo(12.55,15.75);inner.absarc(0,15.75,12.55,0,Math.PI,false);inner.lineTo(-11.05,-3.3);inner.closePath();s.holes.push(inner);
  const geo=new THREE.ExtrudeGeometry(s,{depth:2.35,bevelEnabled:false,curveSegments:64}).rotateX(Math.PI/2);const tie=mesh(host.body,geo,black,[0,y+1.175,0],'Watering real fixed black retaining tie encircling pump and shell');parts.push(tie);parts.push(mesh(host.body,new THREE.BoxGeometry(1.4,3.2,2.8),black,[12.55,y,13.7],'Watering black retaining-tie latch'));
 }return parts;
}
function grove(host){
 const g=new THREE.Group();g.name='Watering real open black HY2.0-4P socket';g.position.fromArray(spec.grove.position);g.quaternion.copy(FACE.bottom);host.body.add(g);const dark=materials.plastic(0x151a17,{roughness:.77}),metal=materials.metal(0xb7b195,{roughness:.48}),box=(size,pos,name,m=dark)=>mesh(g,new THREE.BoxGeometry(...size),m,pos,'Watering Grove '+name),depth=6.1;
 for(const side of[-1,1]){box([.65,5.2,depth],[side*4.675,0,-depth/2],'socket side wall');box([.7,.7,3],[side*3.85,2.25,-4.6],'guide rail');}
 box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');box([8.7,4.55,.65],[0,.325,-depth+.325],'rear dielectric backing');box([4.8,.45,2.3],[0,2.375,-4.5],'locking bridge');const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4.3],[(i-1.5)*2,.2,-3.5],`contact${i+1}`,metal));box([.42,1.3,.42],[(i-1.5)*2,-2.65,-5.7],`solder tail${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.B · Watering analog/control connector',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'PUMP_EN',color:'yellow'},{n:4,name:'Analog Output',color:'white'}],meta:{role:'visual-connector',face:'bottom',scope:'Physical frame,4contacts, pin labels and four-core cable pose only; no electrical power, pump enable, voltage/ADC, moisture or firmware behavior'}}));return{group:g,contacts,port};
}
export function buildWatering(host,{hoses=false}={}){
 const native=addCadParts(host,data,{shell:materials.plastic(0x4c514d,{roughness:.8})}),circuit=circuitry(host),pumpAssembly=pump(host),retainingTies=ties(host),input=grove(host),fixings=[];
 for(const[x,y]of[[0,-44],[-6.8,43],[6.8,43]]){const f=screw(host.body,[x,y,-3.96],'back',1.25);f.name='Watering fixed rear retaining screw';fixings.push(f);}
 const sensor=host.add(new Component({id:'sensor',label:'Watering capacitive probe and fixed pump visual anchor',position:[0,95,-.5],meta:{role:'visual-anchor',scope:'Passive appearance anchor only; no pump state, water, moisture, ADC, timing, sensor values, firmware or electrical behavior'}}));
 const assembly={native,circuit,pump:pumpAssembly,retainingTies,input,fixings,sensor,hoses:[]};host.wateringAssembly=assembly;
 if(hoses)for(const id of['inlet','outlet']){const points=spec.hose.points.map(([x,y,z])=>[id==='inlet'?-x:x,y,id==='inlet'?-z:z]);const hose=pumpAssembly.ports[id].attach(new Hose({points}));assembly.hoses.push(hose);}
 assembly.stickers=addStickers(host,assembly);host.unitStickers=assembly.stickers;
}
