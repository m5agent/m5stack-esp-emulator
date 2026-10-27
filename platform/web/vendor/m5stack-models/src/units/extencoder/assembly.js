import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {roundedRect} from '../../core/geometry.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
function board(host){
 const x=10.5,y=-4,r=3.25,dx=x-8,dy=Math.sqrt(r*r-dx*dx),a=Math.acos(dx/r),s=new THREE.Shape();
 // Native mounting bosses are outside-boundary scallops, not crossing holes.
 s.moveTo(-5.35,-14.8);s.lineTo(-7,-14.8);s.lineTo(-x,-11.5);s.lineTo(-x,y-dy);s.absarc(-8,y,r,Math.PI+a,Math.PI-a,false);s.lineTo(-x,12.5);s.lineTo(-8.3,14.8);s.lineTo(8.3,14.8);s.lineTo(x,12.5);s.lineTo(x,y+dy);s.absarc(8,y,r,a,Math.PI*2-a,false);s.lineTo(x,-11.5);s.lineTo(7,-14.8);s.lineTo(5.35,-14.8);s.lineTo(5.35,-8.75);s.lineTo(-5.35,-8.75);s.closePath();
 const hole=new THREE.Path();hole.absarc(0,-4,1.9,0,Math.PI*2,false);s.holes.push(hole);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:36}),materials.plastic(0x285e43,{roughness:.88}),[0,0,-.9],'ExtEncoder physical PCB with clear mounting scallops and Grove notch');pcb.userData={role:'physical-pcb',scope:'Reconstructed board envelope; no copper routes, values or electrical behavior'};
 return{pcb};
}
function electronics(host){
 const group=new THREE.Group();group.name='ExtEncoder concealed populated electronics';host.body.add(group);
 const dark=materials.plastic(0x252825,{roughness:.85}),metal=materials.metal(0xbab9aa,{roughness:.45}),ceramic=materials.plastic(0xb7a07b,{roughness:.85}),parts=[];
 const box=(name,size,p,mat=dark)=>{const m=mesh(group,new THREE.BoxGeometry(...size),mat,p,'ExtEncoder '+name);parts.push(m);return m;};
 const mcu=box('U1 STM32F030F4P6 TSSOP20 package',[6.5,4.4,1],[0,.4,.55]);
 for(const sign of[-1,1])for(let i=0;i<10;i++)box('U1 gull-wing metal lead',[.27,1,.17],[(i-4.5)*.65,.4+sign*2.65,.16],metal);
 const regulator=box('U2 HX6306 package',[2.8,1.5,1],[-6.5,-8.3,.55]);
 for(const sign of[-1,1])for(let i=0,n=sign<0?1:2;i<n;i++)box('U2 metal lead',[.35,.75,.17],[-6.5+(i-(n-1)/2)*1.7,-8.3+sign*1.05,.16],metal);
 const tvs=box('D1 TVS5V protection package',[2.6,1.7,.9],[5.8,4.0,.5]);
 for(const sign of[-1,1])box('D1 TVS metal termination',[.5,1.72,.92],[5.8+sign*1.15,4,.5],metal);
 const population=[['R1',-5,4.6],['R2',-3.2,4.6],['R8',-1.4,4.6],['R6',3.4,2.9],['R7',3.4,1.2],['R15',-3,-7.2],['R16',-1.2,-7.2],['C4',-5,6.2],['C6',-3.2,6.2],['C12',-1.4,6.2],['C5',-8.5,-8.3],['C7',-6.5,-10.2],['C8',-4.5,-8.3],['C9',3.4,-.6],['C10',3.4,-2.3],['C11',5.5,-2.3]];
 for(const[id,x,y]of population){box(id+' physical passive package',[1.25,.7,.5],[x,y,.3],id[0]==='C'?ceramic:dark);for(const sign of[-1,1])box(id+' metal termination',[.25,.72,.51],[x+sign*.5,y,.3],metal);}
 const swd=[];for(let i=0;i<5;i++){const pad=mesh(group,new THREE.CylinderGeometry(.53,.53,.06,24).rotateX(Math.PI/2),metal,[-8.8,.8+i*2.4,-.95],'ExtEncoder concealed J2 SWD manufacturing pad');swd.push(pad);}
 group.userData={role:'physical-electronics',scope:'Own schematic identifies components; PCB population placement and package Z are hidden appearance estimates, no electrical behavior. J2 remains concealed and has no user Port.'};return{group,mcu,regulator,tvs,parts,swd};
}
function grove(host){
 const frame=new THREE.Group();frame.name='ExtEncoder burgundy open-top HY2.0-4P';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(FACE.bottom);host.body.add(frame);
 const plastic=materials.plastic(spec.grove.color,{roughness:.62}),metal=materials.metal(0xb9ad82,{roughness:.43}),box=(size,p,name,mat=plastic)=>mesh(frame,new THREE.BoxGeometry(...size),mat,p,'ExtEncoder Grove '+name);
 for(const x of[-4.65,4.65]){box([.7,5.2,6.5],[x,0,-3.25],'side wall');box([.85,.75,6.5],[Math.sign(x)*3.85,2.2,-3.25],'guide rail');box([.7,.9,.6],[x,2.05,0],'mouth ear');}
 box([8.6,.7,6.5],[0,-2.25,-3.25],'floor');box([8.6,5.2,.6],[0,0,-6.2],'recessed rear wall');box([8.6,2.65,3.6],[0,-1.25,-4.7],'recessed contact carrier');box([3.4,.65,2.7],[0,1.2,-5.1],'short locking tongue');
 const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4],[(i-1.5)*2,-.15,-3.2],`contact ${i+1}`,metal));box([.42,1.2,.42],[(i-1.5)*2,-1.4,-5.7],`PCB tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],pinGrid:{cols:4,rows:1,pitch:2,center:[0,-.15],order:col=>4-col},meta:{role:'visual-connector',face:'bottom',protocol:'I2C',i2cAddress:'0x59',scope:'Connector and physical cable pose only; no bus, AB/ABZ decoding, counts, angular position, speed, voltage, current or firmware behavior'}}));return{frame,contacts,port};
}
function encoderSocket(host){
 const frame=new THREE.Group();frame.name='ExtEncoder green fixed VH2.54-5P socket';host.body.add(frame);
 const green=materials.plastic(0x4d9c68,{roughness:.68}),metal=materials.metal(0xb7b5a5,{roughness:.4});
 const solid=(name,size,p)=>mesh(frame,new THREE.BoxGeometry(...size),green,p,'ExtEncoder fixed encoder '+name);
 const floor=solid('floor',[14.5,10.2,.6],[0,10.9,-.3]),rear=solid('recessed rear wall',[13.1,.65,6.7],[0,6.125,3.35]);
 const cheeks=[];for(const sign of[-1,1])cheeks.push(solid('side cheek',[.7,10.2,7.3],[sign*6.9,10.9,3.05]));
 const roof=solid('label roof',[14.5,10.2,.65],[0,10.9,6.375]);
 // T-shaped openings in the end band connect directly into the actual cavity.
 // This is a contoured physical lip, not a dark rectangle pasted on a box.
 const s=new THREE.Shape();s.moveTo(-7.25,4.45);
 for(const x of spec.encoder.pinX){s.lineTo(x-.35,4.45);s.lineTo(x-.35,5.25);s.lineTo(x-.9,5.25);s.lineTo(x-.9,5.95);s.lineTo(x+.9,5.95);s.lineTo(x+.9,5.25);s.lineTo(x+.35,5.25);s.lineTo(x+.35,4.45);}
 s.lineTo(7.25,4.45);s.lineTo(7.25,6.7);s.lineTo(-7.25,6.7);s.closePath();
 const lip=mesh(frame,new THREE.ExtrudeGeometry(s,{depth:.65,bevelEnabled:false}).rotateX(Math.PI/2),green,[0,16,0],'ExtEncoder encoder T-window front lip');
 const rails=[];for(const x of[-5.6,5.6])rails.push(solid('low keyed insertion rail',[.45,7.8,.48],[x,11.75,.24]));
 const contacts=[],tails=[];
 for(const[i,x]of spec.encoder.pinX.entries()){
  const collar=mesh(frame,new THREE.CylinderGeometry(.88,.88,1.0,32),green,[x,6.8,1.2],'ExtEncoder recessed encoder pin carrier collar');
  const pin=mesh(frame,new THREE.BoxGeometry(.64,8.3,.64),metal,[x,10.65,1.2],`ExtEncoder ${spec.encoder.names[i]} P6 contact`);pin.userData={schematicPin:spec.encoder.pinNumbers[i],signal:spec.encoder.names[i]};contacts.push(pin);
  tails.push(mesh(frame,new THREE.BoxGeometry(.64,1.1,.64),metal,[x,6.2,1.2],'ExtEncoder bent encoder contact'));
  tails.push(mesh(frame,new THREE.BoxGeometry(.64,.64,1.4),metal,[x,5.95,.5],'ExtEncoder through-PCB encoder tail'));
 }
 const port=host.add(new Port({id:'encoder',label:'External AB/ABZ encoder · VH2.54-5P',connector:spec.encoder.connector,position:spec.encoder.position,hitSize:[14.5,1,7.3],pins:spec.encoder.names.map((name,i)=>({n:spec.encoder.pinNumbers[i],name})),pinGrid:{cols:5,rows:1,pitch:2.54,center:[0,-1.2],order:col=>5-col},meta:{role:'visual-connector',face:'top',scope:'Physical mating frame only. No AB/ABZ decoding, counting, angular position, speed, excitation, continuity or electrical behavior. Not a Grove socket.',pinOrderEvidence:'Own front print G/5V/Z/B/A and schematic P6 pins5/4/3/2/1'}}));
 frame.userData={role:'physical-connector',connector:spec.encoder.connector,inferred:'Own U161 photos and 14.5×10.2 mm drawing; insertion depth, pin length, T-window and key/rail profile estimated for appearance, not manufacturing clearance.'};
 return{frame,floor,rear,roof,lip,rails,cheeks,contacts,tails,port};
}
export function buildExtEncoder(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe8e9e1,{roughness:.77})}),pcb=board(host),population=electronics(host),input=grove(host),encoder=encoderSocket(host);
 const fixing=screw(host.body,[0,-4,-3.98],'back',1.3);
 host.add(new Component({id:'sensor',label:'External encoder visual appearance anchor',meta:{role:'visual-anchor',scope:'Passive appearance anchor. No AB/ABZ decode, counts, position, angle, speed, I2C, voltage, current, electrical or firmware behavior.'}}));
 host.extEncoderAssembly={parts,pcb,electronics:population,input,encoder,fixing};host.unitStickers=addStickers(host);
}
