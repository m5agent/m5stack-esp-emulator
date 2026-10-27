import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,FACE,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function board(host){
 const s=new THREE.Shape(),x=10.35,r=3.6,a=Math.acos((x-8)/r),dy=Math.sqrt(r*r-(x-8)**2),row=-4;
 s.moveTo(-5.5,-14.4);s.lineTo(-8.7,-14.4);s.lineTo(-x,-12.8);s.lineTo(-x,row-dy);s.absarc(-8,row,r,Math.PI+a,Math.PI-a,false);s.lineTo(-x,12.8);s.lineTo(-8.8,14.4);s.lineTo(8.8,14.4);s.lineTo(x,12.8);s.lineTo(x,row+dy);s.absarc(8,row,r,a,tau-a,false);s.lineTo(x,-12.8);s.lineTo(8.7,-14.4);s.lineTo(5.5,-14.4);s.lineTo(5.5,-9.5);s.lineTo(-5.5,-9.5);s.closePath();
 const bore=new THREE.Path();bore.absarc(0,row,1.8,0,tau,false);s.holes.push(bore);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:48}),materials.plastic(0x4f6445,{roughness:.9}),[0,0,-1.2],'Accel fixed PCB with real retaining bore and mounting-boss reliefs');pcb.userData={role:'physical-pcb',inferred:true};
 const dark=materials.plastic(0x242820,{roughness:.8}),metal=materials.metal(0xadae9e,{roughness:.5}),ceramic=materials.plastic(0xb8a87e,{roughness:.88});
 const regulator=slab(host.body,1.3,2.9,.9,.09,[-5.6,7.5,-.4],dark,[],.01);regulator.name='Accel U2 HT7533 fixed three-pin regulator';const regulatorLeads=[];
 for(const[dx,dy]of[[-.85,-.95],[-.85,.95],[.85,0]])regulatorLeads.push(mesh(host.body,new THREE.BoxGeometry(.65,.35,.16),metal,[-5.6+dx,7.5+dy,-.3],'Accel HT7533 physical solder terminal'));
 const mosfets=[];for(const[x,y]of[[5.7,10.7],[5.7,6.4]]){const body=slab(host.body,1.3,2.9,.9,.08,[x,y,-.4],dark,[],.01);body.name='Accel Q'+(mosfets.length+1)+' AO3400A fixed three-terminal level-shifter package';const leads=[];for(const[dx,dy]of[[-.85,-.95],[-.85,.95],[.85,0]])leads.push(mesh(host.body,new THREE.BoxGeometry(.65,.35,.16),metal,[x+dx,y+dy,-.3],'Accel AO3400A fixed solder terminal'));mosfets.push({body,leads});}
 const passives=[];for(const[n,x,y,w,h]of[['C1 100nF',-5.8,11.1,1.2,.7],['C2 100nF',-2.6,11.1,1.2,.7],['C3 10uF',-5.8,3.8,1.6,.9],['C4 10uF',-2.6,3.8,1.6,.9],['R1 4.7K',3,11.3,1.2,.7],['R2 4.7K',3,9.2,1.2,.7],['R5 4.7K',3,5.7,1.2,.7],['R6 4.7K',3,3.7,1.2,.7]]){const p=slab(host.body,w,h,.5,.05,[x,y,-.4],n.startsWith('C')?ceramic:dark,[],.01);p.name='Accel fixed '+n;passives.push(p);for(const sign of[-1,1])mesh(host.body,new THREE.BoxGeometry(.2,h,.2),metal,[x+sign*(w/2-.07),y,-.27],'Accel passive physical metal termination');}
 return{pcb,regulator,regulatorLeads,mosfets,passives};
}
function accelerometer(host){
 const frame=new THREE.Group();frame.name='Accel fixed ADXL345 14-terminal LGA installation';frame.position.fromArray(spec.sensor.position);host.body.add(frame);
 const body=slab(frame,3,5,.85,.035,[0,0,-.375],materials.plastic(0x252825,{roughness:.81}),[],.005);body.name='Accel real ADXL345 3×5mm closed LGA package';body.userData={role:'physical-accelerometer-package',part:'ADXL345',packageMm:[3,5,.95],heightNominalMm:.95,internalPlacementInferred:true};
 const pads=[],gold=materials.metal(0xb6a16e,{roughness:.52});for(const x of[-1.01,1.01])for(let n=0;n<6;n++)pads.push(mesh(frame,new THREE.BoxGeometry(.813,.5,.1),gold,[x,2.01-n*.8,-.425],'Accel ADXL345 fixed LGA underside land '+(pads.length+1)));for(const y of[-2.01,2.01])pads.push(mesh(frame,new THREE.BoxGeometry(.5,.813,.1),gold,[0,y,-.425],'Accel ADXL345 fixed LGA end land '+(pads.length+1)));
 return{frame,body,pads};
}
function grove(host){
 const frame=new THREE.Group();frame.name='Accel physical red HY2.0-4P socket';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(FACE.bottom);host.body.add(frame);
 const red=materials.plastic(spec.grove.color,{roughness:.74}),metal=materials.metal(0xb7b6a3,{roughness:.42}),box=(s,p,n,m=red)=>mesh(frame,new THREE.BoxGeometry(...s),m,p,'Accel Grove '+n),depth=6.1;
 for(const sign of[-1,1]){box([.65,5.2,depth],[sign*4.675,0,-depth/2],'side rail');box([.7,.6,3.2],[sign*3.85,2.3,-4.5],'inner guide');box([.6,.45,1.2],[sign*3.65,2.375,-1.8],'locking shoulder');}box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');box([8.7,4.55,.65],[0,.325,-depth+.325],'deep dielectric rear wall');box([4.8,.45,2.3],[0,2.375,-4.3],'locking bridge');
 const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4.3],[(i-1.5)*2,.2,-3.5],'real contact '+(i+1),metal));box([.42,1.3,.42],[(i-1.5)*2,-2.65,-5.6],'solder tail '+(i+1),metal);}
 const port=host.add(new Port({id:'grove',label:'I2C · HY2.0-4P',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',scope:'Four physical contacts and cable attachment/pose only; no I2C,acceleration,power,electrical or firmware behavior'}}));return{frame,contacts,port};
}
function retaining(host){const metal=materials.metal(0xa1a597,{roughness:.5}),head=mesh(host.body,new THREE.CylinderGeometry(1.22,1.22,.5,48).rotateX(Math.PI/2),metal,[0,-4,-3.35],'Accel recessed physical retaining screw head'),shank=mesh(host.body,new THREE.CylinderGeometry(.6,.6,6,32).rotateX(Math.PI/2),metal,[0,-4,-.1],'Accel concealed fixed retaining shank');mesh(host.body,new THREE.CircleGeometry(.5,6).rotateY(Math.PI),materials.cavity(),[0,-4,-3.61],'Accel recessed screw drive');return{head,shank};}
export function buildAccel(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe7e8e1,{roughness:.8})}),pcb=board(host),sensor=accelerometer(host),input=grove(host),fixing=retaining(host),film=materials.plastic(0xdfdfd7,{roughness:.87}),front=slab(host.body,...spec.labels.front.size,.04,.65,spec.labels.front.position,film,[],0),back=slab(host.body,...spec.labels.back.size,.04,.08,spec.labels.back.position,film,[],0);front.name='Accel physical front adhesive film seated on native label recess';back.name='Accel physical back adhesive film seated on native label recess';front.userData={role:'physical-label-substrate',face:'front'};back.userData={role:'physical-label-substrate',face:'back'};
 const anchor=host.add(new Component({id:'sensor',label:'ADXL345 fixed package appearance anchor',position:spec.sensor.position,meta:{role:'visual-anchor',part:'ADXL345',scope:'Passive fixed package anchor only; no acceleration,orientation,gravity,fall,tap,shake,value,register,I2C,electrical or firmware commands'}}));host.accelAssembly={parts,pcb,sensor,input,fixing,labels:{front,back},anchor};host.unitStickers=addStickers(host);
}
