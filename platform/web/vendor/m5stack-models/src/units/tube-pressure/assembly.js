import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function hole(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,tau,false);s.holes.push(p);}
function extrude(parent,s,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:64}),material,position,name);}
function ring(parent,outer,inner,depth,position,material,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,tau,false);hole(s,0,0,inner);return extrude(parent,s,depth,position,material,name);}
function board(host){
 const s=new THREE.Shape();s.moveTo(-10.4,-12);s.lineTo(-8.8,-14);s.lineTo(-5.6,-14);s.lineTo(-5.6,-8.5);s.lineTo(5.6,-8.5);s.lineTo(5.6,-14);s.lineTo(8.8,-14);s.lineTo(10.4,-12);s.lineTo(10.4,-7.6);s.lineTo(8,-7.6);s.absarc(8,-4,3.6,-Math.PI/2,-Math.PI*1.5,true);s.lineTo(10.4,-.4);s.lineTo(10.4,12.2);s.lineTo(8.4,14.2);s.lineTo(-8.4,14.2);s.lineTo(-10.4,12.2);s.lineTo(-10.4,-.4);s.lineTo(-8,-.4);s.absarc(-8,-4,3.6,Math.PI/2,-Math.PI/2,true);s.lineTo(-10.4,-7.6);s.closePath();hole(s,0,-4,1.65);
 const pcb=extrude(host.body,s,.8,[0,0,-1.6],materials.plastic(0x167147,{roughness:.9}),'Tube Pressure fixed PCB with open mounting edge reliefs and true central screw hole');pcb.userData={role:'physical-pcb',inferred:true};
 const dark=materials.plastic(0x191d1b,{roughness:.85}),metal=materials.metal(0xb7b7a6,{roughness:.42}),ceramic=materials.plastic(0x969273,{roughness:.85});
 const regulator=slab(host.body,2.9,1.5,1,.1,[-7.7,-10.6,-.8],dark,[],.015);regulator.name='Tube Pressure U1 HT7533 fixed three-lead regulator package';
 for(const[dx,dy]of[[-.8,-1],[.8,-1],[0,1]])mesh(host.body,new THREE.BoxGeometry(.4,.8,.18),metal,[-7.7+dx,-10.6+dy,-.55],'Tube Pressure HT7533 physical lead');
 const capacitors=[];for(const[x,y,w,h]of[[-7.7,-13,1.1,1.5],[-7.7,-8.1,1.1,1.5],[-6.2,5.6,1.4,.9],[6.2,6.2,1.4,.9],[6.2,9.7,1.4,.9]]){const c=mesh(host.body,new THREE.BoxGeometry(w,h,.7),ceramic,[x,y,-.45],'Tube Pressure fixed C1-C5 capacitor body');capacitors.push(c);for(const sign of[-1,1])mesh(host.body,new THREE.BoxGeometry(.25,h,.72),metal,[x+sign*(w/2-.12),y,-.45],'Tube Pressure capacitor solder termination');}
 return{pcb,regulator,capacitors};
}
function sensor(host){
 const g=new THREE.Group();g.name='Tube Pressure MCP-H10-B200KPPN fixed single-nozzle sensing package';g.position.set(spec.tube.position[0],spec.tube.position[1],0);host.body.add(g);
 const black=materials.plastic(0x151918,{roughness:.84}),metal=materials.metal(0xb2a66a,{roughness:.47}),deep=materials.plastic(0x0b0e0c,{roughness:.94});
 const lower=roundedRect(7.4,7.6,.35);hole(lower,0,0,.65);const base=extrude(g,lower,3.6,[0,0,-.8],black,'Tube Pressure sensor package base with genuine central tube channel');
 const top=roundedRect(7.5,7.6,.3);hole(top,0,0,.65);const recesses=[];for(const x of[-2.45,2.45])for(const y of[-2.05,0,2.05])hole(top,x,y,.38);
 const cap=extrude(g,top,1.15,[0,0,2.8],black,'Tube Pressure sensor upper carrier closes native shell aperture with six real molded recesses');
 for(const x of[-2.45,2.45])for(const y of[-2.05,0,2.05])recesses.push(mesh(g,new THREE.CylinderGeometry(.38,.38,.1,32).rotateX(Math.PI/2),deep,[x,y,3.23],'Tube Pressure recessed molding pocket floor'));
 const nozzle=ring(g,1.5,.65,4.65,[0,0,3.85],black,'Tube Pressure single Ø3mm open nozzle with continuous physical lumen');
 const diaphragm=mesh(g,new THREE.CylinderGeometry(.65,.65,.12,48).rotateX(Math.PI/2),deep,[0,0,.34],'Tube Pressure recessed fixed sensing diaphragm at blind end of tube');
 const leads=[];for(const side of[-1,1])for(let i=0;i<3;i++){const y=(i-1)*2.05;leads.push(mesh(g,new THREE.BoxGeometry(1.4,.48,.2),metal,[side*4.1,y,-.65],'Tube Pressure MCP-H10 physical package terminal'));mesh(g,new THREE.BoxGeometry(.46,.48,.6),metal,[side*3.55,y,-.25],'Tube Pressure MCP-H10 lead shoulder');}
 const port=host.add(new Port({id:'tube',label:'Single Ø3mm tube nozzle',connector:spec.tube.connector,position:spec.tube.position,quaternion:portQuaternion('front'),hitSize:[3.1,.7,3.1],pins:[],meta:{role:'visual-connector',face:'front',mechanical:true,outerDiameterMm:3,scope:'Mechanical single-nozzle shape and attachment frame only; no pressure, gas, flow, pipe network, electrical or firmware behavior'}}));
 return{group:g,base,cap,nozzle,diaphragm,recesses,leads,port};
}
function grove(host){
 const g=new THREE.Group();g.name='Tube Pressure open black HY2.0-4P socket';g.position.fromArray(spec.grove.position);g.quaternion.copy(FACE.bottom);host.body.add(g);
 const plastic=materials.plastic(spec.grove.color,{roughness:.71}),metal=materials.metal(0xbcb8a0,{roughness:.43}),box=(s,p,n,m=plastic)=>mesh(g,new THREE.BoxGeometry(...s),m,p,'Tube Pressure Grove '+n),depth=6.3;
 for(const sign of[-1,1]){box([.65,5.2,depth],[sign*4.675,0,-depth/2],'side wall');box([.7,.6,3.2],[sign*3.85,2.3,-4.7],'guide rail');box([.6,.45,1.2],[sign*3.65,2.375,-1.8],'latch shoulder');}
 box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');box([8.7,4.55,.65],[0,.325,-depth+.325],'rear wall');box([4.8,.45,2.3],[0,2.375,-4.5],'locking bridge');
 const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4.5],[(i-1.5)*2,.2,-3.6],`contact ${i+1}`,metal));box([.42,1.4,.42],[(i-1.5)*2,-2.7,-5.8],`solder tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.B · analog signal',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'NC',color:'yellow'},{n:4,name:'Analog Output',color:'white'}],meta:{role:'visual-connector',face:'bottom',scope:'Physical attachment, four contacts, documented pin labels and cable pose only; no pressure conversion, voltage, I2C or electrical behavior'}}));return{group:g,contacts,port};
}
export function buildTubePressure(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe8e9e3,{roughness:.79})}),pcb=board(host),sensing=sensor(host),input=grove(host);
 const fixing=screw(host.body,[0,-4,-3.79],'back',1.65);fixing.name='Tube Pressure recessed central fixed hex retaining screw';fixing.traverse(o=>{if(o.isMesh)o.name='Tube Pressure fixed hex retaining screw face';});mesh(host.body,new THREE.CylinderGeometry(.7,.7,3.8,32).rotateX(Math.PI/2),materials.metal(0x9c9e95),[0,-4,-1.6],'Tube Pressure concealed fixed screw shank');
 const anchor=host.add(new Component({id:'sensor',label:'MCP-H10-B200KPPN appearance anchor',position:[spec.tube.position[0],spec.tube.position[1],1],meta:{role:'visual-anchor',scope:'Passive fixed visual anchor only; no pressure, gas, flow, voltage, conversion, values, calibration, I2C or electrical/firmware commands'}}));
 host.tubePressureAssembly={parts,pcb,sensing,input,fixing,anchor};host.unitStickers=addStickers(host);
}
