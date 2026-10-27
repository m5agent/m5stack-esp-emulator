import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function hole(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,tau,false);s.holes.push(p);}
function rectHole(s,x,y,w,h){const p=new THREE.Path();p.moveTo(x-w/2,y-h/2);p.lineTo(x+w/2,y-h/2);p.lineTo(x+w/2,y+h/2);p.lineTo(x-w/2,y+h/2);p.closePath();s.holes.push(p);}
function rect(w,h){const s=new THREE.Shape();s.moveTo(-w/2,-h/2);s.lineTo(w/2,-h/2);s.lineTo(w/2,h/2);s.lineTo(-w/2,h/2);s.closePath();return s;}
function extrude(parent,s,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:64}),material,position,name);}
function board(host){
 const s=new THREE.Shape();s.moveTo(-10.4,-12);s.lineTo(-8.8,-14);s.lineTo(-5.5,-14);s.lineTo(-5.5,-8.2);s.lineTo(5.5,-8.2);s.lineTo(5.5,-14);s.lineTo(8.8,-14);s.lineTo(10.4,-12);s.lineTo(10.4,-7.6);s.lineTo(8,-7.6);s.absarc(8,-4,3.6,-Math.PI/2,-Math.PI*1.5,true);s.lineTo(10.4,-.4);s.lineTo(10.4,12.2);s.lineTo(8.4,14.2);s.lineTo(-8.4,14.2);s.lineTo(-10.4,12.2);s.lineTo(-10.4,-.4);s.lineTo(-8,-.4);s.absarc(-8,-4,3.6,Math.PI/2,-Math.PI/2,true);s.lineTo(-10.4,-7.6);s.closePath();hole(s,0,-4,2.8);
 const pcb=extrude(host.body,s,.8,[0,0,.85],materials.plastic(0x202422,{roughness:.92}),'TMOS PIR physical dark PCB with true mounting reliefs and central hole');pcb.userData={role:'physical-pcb',inferred:true};
 const dark=materials.plastic(0x202321,{roughness:.86}),metal=materials.metal(0xb6b8b0,{roughness:.47}),ceramic=materials.plastic(0xb6a483,{roughness:.86});
 const regulator=slab(host.body,2.2,2.8,.8,.12,[7,9,1.65],dark,[],.02);regulator.name='TMOS PIR concealed U2 XC6228 regulator package';
 const protection=slab(host.body,1.7,2.8,.6,.1,[-6,1.5,1.65],dark,[],.02);protection.name='TMOS PIR concealed U3 SRV05-4 interface protection package';
 for(const[x,y,w,h,n]of[[7,9,2.2,2.8,5],[-6,1.5,1.7,2.8,6]])for(let i=0;i<n;i++){const sign=i%2?-1:1;mesh(host.body,new THREE.BoxGeometry(.6,.35,.15),metal,[x+sign*(w/2+.1),y+(Math.floor(i/2)-1)*.8,1.75],'TMOS PIR concealed fixed IC lead');}
 const resistors=[],capacitors=[];
 for(const y of[5,2.5]){resistors.push(mesh(host.body,new THREE.BoxGeometry(1.6,.8,.45),dark,[-6,y,1.875],'TMOS PIR fixed I2C pull-up resistor'));for(const side of[-1,1])mesh(host.body,new THREE.BoxGeometry(.28,.8,.47),metal,[-6+side*.68,y,1.875],'TMOS PIR resistor solder termination');}
 for(const[x,y]of[[6,12],[7,5],[6,2.5],[-6,11.5],[-6,9]]){capacitors.push(mesh(host.body,new THREE.BoxGeometry(1.6,.8,.65),ceramic,[x,y,1.975],'TMOS PIR fixed capacitor'));for(const side of[-1,1])mesh(host.body,new THREE.BoxGeometry(.28,.8,.67),metal,[x+side*.68,y,1.975],'TMOS PIR capacitor solder termination');}
 return{pcb,regulator,protection,resistors,capacitors};
}
function sensingPackage(host){
 const group=new THREE.Group();group.name='TMOS PIR passive STHS34PF80 OLGA-10L sensing assembly';group.position.fromArray(spec.opticalWindow.sensorPosition);host.body.add(group);
 const dark=materials.plastic(0x292c29,{roughness:.76}),metal=materials.metal(0xa9afaa,{roughness:.5}),base=slab(group,4.2,3.2,1.265,.06,[0,0,0],dark,[],.015);base.name='TMOS PIR STHS34PF80 organic LGA package substrate';
 const outer=rect(4.2,3.2);rectHole(outer,0,0,4.02,3.02);const rim=extrude(group,outer,.19,[0,0,1.265],metal,'TMOS PIR STHS34PF80 thin metal package edge');
 const lidShape=rect(4.02,3.02);rectHole(lidShape,-.7,-.28,1.65,1.65);const lid=extrude(group,lidShape,.18,[0,0,1.265],dark,'TMOS PIR actual top lid with square silicon-filter aperture');
 const die=mesh(group,new THREE.BoxGeometry(1.49,1.49,.08),materials.plastic(0x243a35,{roughness:.64}),[-.7,-.28,1.23],'TMOS PIR passive internal filter support below silicon window');
 const filter=mesh(group,new THREE.BoxGeometry(1.55,1.55,.12),materials.plastic(0x9ab3ae,{roughness:.31,metalness:.25}),[-.7,-.28,1.35],'TMOS PIR non-emissive integrated silicon infrared filter');
 const contacts=[];for(const sign of[-1,1])for(let i=0;i<5;i++)contacts.push(mesh(group,new THREE.BoxGeometry(.45,.35,.12),metal,[(i-2)*.75,sign*1.4,.06],'TMOS PIR OLGA-10L underside land'));
 const pin1=mesh(group,new THREE.CircleGeometry(.11,24),materials.plastic(0xc6ccc5,{roughness:.66}),[-1.7,-1.2,1.447],'TMOS PIR fixed package orientation dot');
 return{group,base,rim,lid,die,filter,contacts,pin1};
}
function grove(host){
 const g=new THREE.Group();g.name='TMOS PIR open red HY2.0-4P socket';g.position.fromArray(spec.grove.position);g.quaternion.copy(FACE.bottom);host.body.add(g);
 const plastic=materials.plastic(spec.grove.color,{roughness:.71}),metal=materials.metal(0xbcb8a0,{roughness:.43}),box=(s,p,n,m=plastic)=>mesh(g,new THREE.BoxGeometry(...s),m,p,'TMOS PIR Grove '+n),depth=6.3;
 for(const sign of[-1,1]){box([.65,5.2,depth],[sign*4.675,0,-depth/2],'side wall');box([.7,.6,3.2],[sign*3.85,2.3,-4.7],'guide rail');box([.6,.45,1.2],[sign*3.65,2.375,-1.8],'latch shoulder');}
 box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');box([8.7,4.55,.65],[0,.325,-depth+.325],'rear wall');box([4.8,.45,2.3],[0,2.375,-4.5],'locking bridge');
 const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4.5],[(i-1.5)*2,.2,-3.6],`contact ${i+1}`,metal));box([.42,1.4,.42],[(i-1.5)*2,-2.7,-5.8],`solder tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',scope:'Physical attachment, four contacts, documented pin labels and cable pose only; no presence,motion,temperature,infrared ray,I2C,voltage,electrical or firmware simulation'}}));return{group:g,contacts,port};
}
export function buildTMOSPIR(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe9eae5,{roughness:.8})}),pcb=board(host),sensor=sensingPackage(host),input=grove(host);
 const fixing=screw(host.body,[0,-4,-3.79],'back',1.4);fixing.name='TMOS PIR recessed central fixed hex retaining screw';fixing.traverse(o=>{if(o.isMesh)o.name='TMOS PIR fixed hex retaining screw face';});mesh(host.body,new THREE.CylinderGeometry(.65,.65,4.8,32).rotateX(Math.PI/2),materials.metal(0x9c9e95),[0,-4,-.4],'TMOS PIR concealed fixed screw shank');
 const anchor=host.add(new Component({id:'sensor',label:'STHS34PF80 passive appearance anchor',position:[0,8,2.4],meta:{role:'visual-anchor',scope:'Passive fixed appearance anchor only; no presence,motion,temperature,infrared emission,visible beam,detection cone,sensor values,threshold,calibration,register,I2C,electrical or firmware commands'}}));
 host.tmosPIRAssembly={parts,pcb,sensor,input,fixing,anchor};host.unitStickers=addStickers(host);
}
