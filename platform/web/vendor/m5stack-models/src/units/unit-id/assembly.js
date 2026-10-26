import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,FACE,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function board(host){
 const s=new THREE.Shape(),x=10.35,r=3.6,a=Math.acos((x-8)/r),dy=Math.sqrt(r*r-(x-8)**2);
 s.moveTo(-5.5,-10.35);s.lineTo(-8.7,-10.35);s.lineTo(-x,-8.7);s.lineTo(-x,-dy);s.absarc(-8,0,r,Math.PI+a,Math.PI-a,false);s.lineTo(-x,8.7);s.lineTo(-8.7,10.35);s.lineTo(8.7,10.35);s.lineTo(x,8.7);s.lineTo(x,dy);s.absarc(8,0,r,a,tau-a,false);s.lineTo(x,-8.7);s.lineTo(8.7,-10.35);s.lineTo(5.5,-10.35);s.lineTo(5.5,-5.4);s.lineTo(-5.5,-5.4);s.closePath();
 const bore=new THREE.Path();bore.absarc(0,0,1.8,0,tau,false);s.holes.push(bore);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:48}),materials.plastic(0x375244,{roughness:.92}),[0,0,-1.2],'Unit ID fixed PCB with actual retaining bore and mounting-boss reliefs');pcb.userData={role:'physical-pcb',inferred:true};
 const dark=materials.plastic(0x252825,{roughness:.82}),metal=materials.metal(0xb4b8a7,{roughness:.5}),ceramic=materials.plastic(0xb7aa7f,{roughness:.88});
 const regulator=slab(host.body,1.3,2.9,.9,.08,[5.4,6.5,-.4],dark,[],.01);regulator.name='Unit ID U1 HT7533 fixed three-terminal regulator';const regulatorLeads=[];for(const[dx,dy]of[[-.85,-.95],[-.85,.95],[.85,0]])regulatorLeads.push(mesh(host.body,new THREE.BoxGeometry(.65,.35,.16),metal,[5.4+dx,6.5+dy,-.3],'Unit ID HT7533 fixed physical terminal'));
 const passives=[];for(const[n,x,y,w,h]of[['C1 10uF',-5.6,7.8,1.6,.9],['C2 10uF',-5.6,4.9,1.6,.9],['C3 100nF',2.9,8.8,1.2,.7],['R1 4.7K',-2.8,3.6,1.2,.7],['R2 4.7K',2.8,3.6,1.2,.7]]){const p=slab(host.body,w,h,.5,.05,[x,y,-.4],n.startsWith('C')?ceramic:dark,[],.01);p.name='Unit ID fixed '+n;passives.push(p);for(const sign of[-1,1])mesh(host.body,new THREE.BoxGeometry(.2,h,.2),metal,[x+sign*(w/2-.07),y,-.27],'Unit ID passive physical metal termination');}
 return{pcb,regulator,regulatorLeads,passives};
}
function secureElement(host){
 const frame=new THREE.Group();frame.name='Unit ID fixed ATECC608B eight-pad UDFN installation';frame.position.fromArray(spec.secureElement.position);host.body.add(frame);
 const body=slab(frame,3,2,.398,.025,[0,0,.152],materials.plastic(0x242624,{roughness:.86}),[],0);body.name='Unit ID U2 ATECC608B-TNGTLSU-G closed UDFN package';body.userData={role:'physical-secure-element-package',part:'ATECC608B-TNGTLSU-G',package:'8-pad UDFN',modelPackageMm:[3,2,.55],internalPlacementInferred:true};
 const pads=[],metal=materials.metal(0xb6b29b,{roughness:.5});for(const x of[-1.3,1.3])for(let n=0;n<4;n++)pads.push(mesh(frame,new THREE.BoxGeometry(.4,.25,.152),metal,[x,.75-n*.5,.076],'Unit ID ATECC608B fixed UDFN underside terminal '+(pads.length+1)));
 const thermalPad=mesh(frame,new THREE.BoxGeometry(1.3,1.5,.152),metal,[0,0,.076],'Unit ID ATECC608B fixed underside exposed paddle');return{frame,body,pads,thermalPad};
}
function grove(host){
 const frame=new THREE.Group();frame.name='Unit ID physical red HY2.0-4P socket';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(FACE.bottom);host.body.add(frame);
 const red=materials.plastic(spec.grove.color,{roughness:.73}),metal=materials.metal(0xb7b6a3,{roughness:.42}),box=(s,p,n,m=red)=>mesh(frame,new THREE.BoxGeometry(...s),m,p,'Unit ID Grove '+n),depth=6.1;
 for(const sign of[-1,1]){box([.65,5.2,depth],[sign*4.675,0,-depth/2],'side rail');box([.7,.6,3.2],[sign*3.85,2.3,-4.5],'inner guide');box([.6,.45,1.2],[sign*3.65,2.375,-1.8],'locking shoulder');}box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');box([8.7,4.55,.65],[0,.325,-depth+.325],'deep dielectric rear wall');box([4.8,.45,2.3],[0,2.375,-4.3],'locking bridge');
 const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4.3],[(i-1.5)*2,.2,-3.5],'real contact '+(i+1),metal));box([.42,1.3,.42],[(i-1.5)*2,-2.65,-5.6],'solder tail '+(i+1),metal);}
 const port=host.add(new Port({id:'grove',label:'I2C · HY2.0-4P',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',scope:'Four physical contacts and cable attachment/pose only;no keys,certificates,serial number,identity,cryptography,I2C,power,electrical or firmware behavior'}}));return{frame,contacts,port};
}
function retaining(host){const metal=materials.metal(0xa1a597,{roughness:.5}),head=mesh(host.body,new THREE.CylinderGeometry(1.22,1.22,.5,48).rotateX(Math.PI/2),metal,[0,0,-3.35],'Unit ID recessed physical retaining screw head'),shank=mesh(host.body,new THREE.CylinderGeometry(.6,.6,6,32).rotateX(Math.PI/2),metal,[0,0,-.1],'Unit ID concealed fixed retaining shank');mesh(host.body,new THREE.CircleGeometry(.5,6).rotateY(Math.PI),materials.cavity(),[0,0,-3.61],'Unit ID recessed screw drive');return{head,shank};}
export function buildId(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe8e9e3,{roughness:.8})}),pcb=board(host),chip=secureElement(host),input=grove(host),fixing=retaining(host),film=materials.plastic(0xdfdfd7,{roughness:.87}),front=slab(host.body,...spec.labels.front.size,.04,.6,spec.labels.front.position,film,[],0),back=slab(host.body,...spec.labels.back.size,.04,.06,spec.labels.back.position,film,[],0);front.name='Unit ID physical front adhesive film seated on native label recess';back.name='Unit ID physical back adhesive film seated on native label recess';front.userData={role:'physical-label-substrate',face:'front'};back.userData={role:'physical-label-substrate',face:'back'};
 host.idAssembly={parts,pcb,secureElement:chip,input,fixing,labels:{front,back}};host.unitStickers=addStickers(host);
}
