import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function hole(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,tau,false);s.holes.push(p);}
function extrude(parent,s,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:64}),material,position,name);}
function board(host){
 const s=new THREE.Shape();s.moveTo(-10.4,-12);s.lineTo(-8.8,-14);s.lineTo(-5.5,-14);s.lineTo(-5.5,-8.2);s.lineTo(5.5,-8.2);s.lineTo(5.5,-14);s.lineTo(8.8,-14);s.lineTo(10.4,-12);s.lineTo(10.4,-7.6);s.lineTo(8,-7.6);s.absarc(8,-4,3.6,-Math.PI/2,-Math.PI*1.5,true);s.lineTo(10.4,-.4);s.lineTo(10.4,12.2);s.lineTo(8.4,14.2);s.lineTo(-8.4,14.2);s.lineTo(-10.4,12.2);s.lineTo(-10.4,-.4);s.lineTo(-8,-.4);s.absarc(-8,-4,3.6,Math.PI/2,-Math.PI/2,true);s.lineTo(-10.4,-7.6);s.closePath();hole(s,0,-4,2.8);
 for(const x of[-4.1,4.1])for(let i=0;i<4;i++)hole(s,x,12-(i*2.54),.45);
 const pcb=extrude(host.body,s,.8,[0,0,1.35],materials.plastic(0xe4e6dd,{roughness:.91}),'DLight fixed white PCB with open mounting edge reliefs and true central and fabrication holes');pcb.userData={role:'physical-pcb',inferred:true};
 const metal=materials.metal(0xb7bbb0,{roughness:.48}),dark=materials.plastic(0x1d211b,{roughness:.87}),ceramic=materials.plastic(0x9a9b76,{roughness:.85}),pads=[];
 for(const x of[-4.1,4.1])for(let i=0;i<4;i++){const y=12-i*2.54,p=new THREE.Shape();p.absarc(0,0,.76,0,tau,false);hole(p,0,0,.45);pads.push(extrude(host.body,p,.035,[x,y,2.15],metal,`DLight concealed unpopulated ${x<0?'P1':'P2'} pad${i+1}`));}
 const regulator=slab(host.body,1.6,2.9,.7,.1,[8.0,8.3,2.15],dark,[],.015);regulator.name='DLight U2 HT7533 fixed three-lead regulator package';
 for(const[dx,dy]of[[-1,-.8],[-1,.8],[1,0]])mesh(host.body,new THREE.BoxGeometry(.8,.4,.18),metal,[8+dx,8.3+dy,2.24],'DLight HT7533 physical lead');
 const resistors=[],capacitors=[];
 for(let i=0;i<3;i++){const x=-8,y=12-i*2.54;resistors.push(mesh(host.body,new THREE.BoxGeometry(1.8,.95,.5),dark,[x,y,2.4],'DLight fixed R1-R3 resistor body'));for(const side of[-1,1])mesh(host.body,new THREE.BoxGeometry(.3,.95,.52),metal,[x+side*.75,y,2.4],'DLight resistor solder termination');}
 for(const y of[12.3,10.2,5.7,3.7]){capacitors.push(mesh(host.body,new THREE.BoxGeometry(1.8,.95,.7),ceramic,[8,y,2.5],'DLight fixed C1-C4 capacitor body'));for(const side of[-1,1])mesh(host.body,new THREE.BoxGeometry(.3,.95,.72),metal,[8+side*.75,y,2.5],'DLight capacitor solder termination');}
 return{pcb,pads,regulator,resistors,capacitors};
}
function sensingPackage(host){
 const group=new THREE.Group();group.name='DLight fixed BH1750FVI-TR WSOF6I optical sensing package';group.position.fromArray(spec.opticalWindow.sensorPosition);host.body.add(group);
 const metal=materials.metal(0xb8b9a9,{roughness:.49}),base=slab(group,1.55,2.8,.14,.06,[0,0,0],materials.plastic(0x202b20,{roughness:.86}),[],.01);base.name='DLight actual BH1750FVI opaque package substrate';
 const die=mesh(group,new THREE.BoxGeometry(1.1,2.22,.1),materials.plastic(0x293b23,{roughness:.47}),[0,0,.2],'DLight passive dark photodiode die beneath clear resin');
 const resin=slab(group,1.6,3,.61,.08,[0,0,.14],materials.plastic(0xc5d3b7,{roughness:.22,transparent:true,opacity:.38,depthWrite:false}),[],.015);resin.name='DLight non-emissive transparent BH1750FVI optical resin';
 const leads=[];for(const side of[-1,1])for(let i=0;i<3;i++){const x=(i-1)*.5;leads.push(mesh(group,new THREE.BoxGeometry(.22,.4,.15),metal,[x,side*1.4,.075],'DLight BH1750FVI physical package lead'));}
 return{group,base,die,resin,leads};
}
function grove(host){
 const g=new THREE.Group();g.name='DLight open red HY2.0-4P socket';g.position.fromArray(spec.grove.position);g.quaternion.copy(FACE.bottom);host.body.add(g);
 const plastic=materials.plastic(spec.grove.color,{roughness:.71}),metal=materials.metal(0xbcb8a0,{roughness:.43}),box=(s,p,n,m=plastic)=>mesh(g,new THREE.BoxGeometry(...s),m,p,'DLight Grove '+n),depth=6.3;
 for(const sign of[-1,1]){box([.65,5.2,depth],[sign*4.675,0,-depth/2],'side wall');box([.7,.6,3.2],[sign*3.85,2.3,-4.7],'guide rail');box([.6,.45,1.2],[sign*3.65,2.375,-1.8],'latch shoulder');}
 box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');box([8.7,4.55,.65],[0,.325,-depth+.325],'rear wall');box([4.8,.45,2.3],[0,2.375,-4.5],'locking bridge');
 const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4.5],[(i-1.5)*2,.2,-3.6],`contact ${i+1}`,metal));box([.42,1.4,.42],[(i-1.5)*2,-2.7,-5.8],`solder tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',scope:'Physical attachment, four contacts, documented pin labels and cable pose only; no light, lux, optical, ADC, I2C, voltage, electrical or firmware simulation'}}));return{group:g,contacts,port};
}
export function buildDLight(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe8e9e3,{roughness:.79})}),pcb=board(host),sensor=sensingPackage(host),input=grove(host);
 const fixing=screw(host.body,[0,-4,-3.79],'back',1.4);fixing.name='DLight recessed central fixed hex retaining screw';fixing.traverse(o=>{if(o.isMesh)o.name='DLight fixed hex retaining screw face';});mesh(host.body,new THREE.CylinderGeometry(.65,.65,4.8,32).rotateX(Math.PI/2),materials.metal(0x9c9e95),[0,-4,-.4],'DLight concealed fixed screw shank');
 const anchor=host.add(new Component({id:'sensor',label:'BH1750FVI appearance anchor',position:[0,8,2.5],meta:{role:'visual-anchor',scope:'Passive fixed visual anchor only; no light emission, optical ray, illuminance/lux/ADC, sensor value, threshold, calibration, I2C, electrical or firmware commands'}}));
 host.dlightAssembly={parts,pcb,sensor,input,fixing,anchor};host.unitStickers=addStickers(host);
}
