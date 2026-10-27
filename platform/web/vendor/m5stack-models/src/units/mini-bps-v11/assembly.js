import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
function circularHole(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(p);}
function extrude(parent,s,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:64}),material,position,name);}
function board(host){
 const s=new THREE.Shape();s.moveTo(-10.4,-8.8);s.lineTo(-8.8,-10.4);s.lineTo(-5.5,-10.4);s.lineTo(-5.5,-4.2);s.lineTo(5.5,-4.2);s.lineTo(5.5,-10.4);s.lineTo(8.8,-10.4);s.lineTo(10.4,-8.8);s.lineTo(10.4,-3.6);s.lineTo(8,-3.6);s.absarc(8,0,3.6,-Math.PI/2,-Math.PI*1.5,true);s.lineTo(10.4,3.6);s.lineTo(10.4,8.8);s.lineTo(8.8,10.4);s.lineTo(-8.8,10.4);s.lineTo(-10.4,8.8);s.lineTo(-10.4,3.6);s.lineTo(-8,3.6);s.absarc(-8,0,3.6,Math.PI/2,-Math.PI/2,true);s.lineTo(-10.4,-3.6);s.closePath();circularHole(s,0,0,2.8);
 const pcb=extrude(host.body,s,.8,[0,0,.85],materials.plastic(0x202422,{roughness:.92}),'Mini BPS v1.1 physical dark PCB with true mounting reliefs and central hole');pcb.userData={role:'physical-pcb',inferred:true};
 const dark=materials.plastic(0x202321,{roughness:.85}),metal=materials.metal(0xb6b8b0,{roughness:.47}),ceramic=materials.plastic(0xb6a483,{roughness:.86});
 const regulator=slab(host.body,1.7,3,.9,.12,[6.1,6.7,1.65],dark,[],.02);regulator.name='Mini BPS v1.1 concealed HT7533 SOT89 regulator body';
 const regulatorLeads=[];for(const x of[-.95,0,.95])regulatorLeads.push(mesh(host.body,new THREE.BoxGeometry(.42,1.1,.18),metal,[6.1+x,4.9,1.74],'Mini BPS v1.1 HT7533 fixed lead'));mesh(host.body,new THREE.BoxGeometry(1.4,.55,.18),metal,[6.1,8.4,1.74],'Mini BPS v1.1 HT7533 fixed thermal tab');
 const levelShifters=[];for(const y of[4.1,7.2]){const q=slab(host.body,1.3,2,.7,.08,[-6.2,y,1.65],dark,[],.015);q.name='Mini BPS v1.1 concealed BSS138 level shifter';levelShifters.push(q);for(const[x,dy]of[[-.88,-.5],[-.88,.5],[.88,0]])mesh(host.body,new THREE.BoxGeometry(.65,.4,.16),metal,[-6.2+x,y+dy,1.73],'Mini BPS v1.1 fixed BSS138 lead');}
 const resistors=[],capacitors=[];for(const[x,y]of[[-3.4,4.4],[-3.4,6.4],[3.2,4.3],[3.2,6.3]]){resistors.push(mesh(host.body,new THREE.BoxGeometry(1.6,.8,.45),dark,[x,y,1.875],'Mini BPS v1.1 fixed 4.7k pull-up resistor'));for(const sign of[-1,1])mesh(host.body,new THREE.BoxGeometry(.28,.8,.47),metal,[x+sign*.68,y,1.875],'Mini BPS v1.1 resistor solder termination');}
 for(const[x,y]of[[-8,8.9],[8.1,9.3],[3.5,9]]){capacitors.push(mesh(host.body,new THREE.BoxGeometry(1.6,.8,.65),ceramic,[x,y,1.975],'Mini BPS v1.1 fixed decoupling capacitor'));for(const sign of[-1,1])mesh(host.body,new THREE.BoxGeometry(.28,.8,.67),metal,[x+sign*.68,y,1.975],'Mini BPS v1.1 capacitor solder termination');}
 return{pcb,regulator,regulatorLeads,levelShifters,resistors,capacitors};
}
function sensingPackage(host){
 const group=new THREE.Group();group.name='Mini BPS v1.1 passive QMP6988 vented LGA9 package';group.position.fromArray(spec.airSlots.sensorPositionMm);group.rotation.z=spec.airSlots.packageRotationZ;host.body.add(group);
 const dark=materials.plastic(0x2b2c29,{roughness:.83}),metal=materials.metal(0xb5b9b1,{roughness:.48}),gold=materials.metal(0xb2a46b,{roughness:.45});
 const base=extrude(group,roundedRect(2,2.5,.035),.13,[0,0,0],dark,'Mini BPS v1.1 QMP6988 physical LGA substrate');
 const skirtShape=roundedRect(1.82,2.32,.14);skirtShape.holes.push(roundedRect(1.62,2.12,.09,{path:new THREE.Path(),clockwise:true}));const rim=extrude(group,skirtShape,.62,[0,0,.13],metal,'Mini BPS v1.1 QMP6988 metal skirt enclosing real cavity');
 const lidShape=roundedRect(1.82,2.32,.14);circularHole(lidShape,-.46,.71,.1);const lid=extrude(group,lidShape,.1,[0,0,.75],metal,'Mini BPS v1.1 QMP6988 metal lid with true 0.20mm pressure vent');
 const die=mesh(group,new THREE.BoxGeometry(1.35,1.65,.12),materials.plastic(0x242c2b,{roughness:.66}),[0,0,.30],'Mini BPS v1.1 recessed passive sensor die below air vent');
 const contacts=[];for(const sign of[-1,1])for(let i=0;i<4;i++)contacts.push(mesh(group,new THREE.BoxGeometry(.35,.35,.08),gold,[sign*.725,(i-1.5)*.65,.04],'Mini BPS v1.1 QMP6988 underside gold land'));contacts.push(mesh(group,new THREE.BoxGeometry(.35,.35,.08),gold,[0,.975,.04],'Mini BPS v1.1 QMP6988 ninth underside gold land'));
 return{group,base,rim,lid,die,contacts};
}
function grove(host){
 const g=new THREE.Group();g.name='Mini BPS v1.1 open red HY2.0-4P socket';g.position.fromArray(spec.grove.position);g.quaternion.copy(FACE.bottom);host.body.add(g);
 const plastic=materials.plastic(spec.grove.color,{roughness:.71}),metal=materials.metal(0xbcb8a0,{roughness:.43}),box=(s,p,n,m=plastic)=>mesh(g,new THREE.BoxGeometry(...s),m,p,'Mini BPS v1.1 Grove '+n),depth=6.3;
 for(const sign of[-1,1]){box([.65,5.2,depth],[sign*4.675,0,-depth/2],'side wall');box([.7,.6,3.2],[sign*3.85,2.3,-4.7],'guide rail');box([.6,.45,1.2],[sign*3.65,2.375,-1.8],'latch shoulder');}
 box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');box([8.7,4.55,.65],[0,.325,-depth+.325],'rear wall');box([4.8,.45,2.3],[0,2.375,-4.5],'locking bridge');
 const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4.5],[(i-1.5)*2,.2,-3.6],`contact ${i+1}`,metal));box([.42,1.4,.42],[(i-1.5)*2,-2.7,-5.8],`solder tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',scope:'Physical attachment,four contacts,documented pin labels and cable pose only;no pressure,temperature,altitude,airflow,register,I2C,voltage,electrical or firmware simulation'}}));return{group:g,contacts,port};
}
function adhesiveFilms(host){
 const filmMaterial=materials.plastic(0xf8f8f5,{roughness:.9});const front=mesh(host.body,new THREE.CylinderGeometry(2.9,2.9,.04,96).rotateX(Math.PI/2),filmMaterial,[0,0,4.02],'Mini BPS v1.1 independent round front adhesive film');const back=mesh(host.body,new THREE.BoxGeometry(16,4,.04),filmMaterial,[0,7,-3.815],'Mini BPS v1.1 independent rear adhesive film');for(const o of[front,back])o.userData={role:'physical-label-film',inferred:true};return{front,back};
}
export function buildMiniBPSV11(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe9eae5,{roughness:.8})}),pcb=board(host),sensor=sensingPackage(host),input=grove(host),films=adhesiveFilms(host);
 const fixing=screw(host.body,[0,0,-3.79],'back',1.4);fixing.name='Mini BPS v1.1 recessed central fixed hex retaining screw';fixing.traverse(o=>{if(o.isMesh)o.name='Mini BPS v1.1 fixed hex retaining screw face';});mesh(host.body,new THREE.CylinderGeometry(.65,.65,4.8,32).rotateX(Math.PI/2),materials.metal(0x9c9e95),[0,0,-.4],'Mini BPS v1.1 concealed fixed screw shank');
 const anchor=host.add(new Component({id:'sensor',label:'QMP6988 passive appearance anchor',position:spec.airSlots.sensorPositionMm,meta:{role:'visual-anchor',scope:'Passive fixed appearance anchor only;no pressure,temperature,altitude,airflow,sensor values,threshold,calibration,register,I2C,electrical or firmware commands'}}));
 host.miniBPSV11Assembly={parts,pcb,sensor,input,films,fixing,anchor};host.unitStickers=addStickers(host);
}
