import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import {roundedRect} from '../../core/geometry.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
const metal=()=>materials.metal(0xb6b6a8,{roughness:.43});
function circleBore(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(h);}
function board(host){
 // Board contour follows the exact-version exposed PCB photo: open scallops
 // around the native mounting bores and a real bottom notch for the Grove.
 const s=new THREE.Shape();s.moveTo(-8,26.6);s.lineTo(8,26.6);s.lineTo(10.4,24.2);s.lineTo(10.4,-12.25);s.lineTo(8,-12.25);s.absarc(8,-16,3.75,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-19.75);s.lineTo(10.4,-24.6);s.lineTo(8.2,-26.6);s.lineTo(5.3,-26.6);s.lineTo(5.3,-21.3);s.lineTo(-5.3,-21.3);s.lineTo(-5.3,-26.6);s.lineTo(-8.2,-26.6);s.lineTo(-10.4,-24.6);s.lineTo(-10.4,-19.75);s.lineTo(-8,-19.75);s.absarc(-8,-16,3.75,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.4,-12.25);s.lineTo(-10.4,24.2);s.closePath();circleBore(s,0,-16,2.85);
 for(const x of[-3,-1,1,3])circleBore(s,x,-20.85,.32);
 for(const x of[-4,4])circleBore(s,x,13.55,.48);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:48}),materials.plastic(0x137345,{roughness:.92}),[0,0,-2.2],'KMeter-ISO v1.1 PCB with native bore clearances');
 pcb.userData={role:'physical-pcb',source:'Exact U133-V11 exposed PCB photograph',inferred:'Outline, thickness/Z and drills are appearance estimates. No fabricated traces or electrical isolation simulation.'};
 const pads=[];for(const[x,y,r]of[...[-3,-1,1,3].map(x=>[x,-20.85,.32]),...[-4,4].map(x=>[x,13.55,.48])]){const a=new THREE.Shape();a.absarc(x,y,r+.22,0,Math.PI*2,false);circleBore(a,x,y,r);pads.push(mesh(host.body,new THREE.ExtrudeGeometry(a,{depth:.07,bevelEnabled:false,curveSegments:24}),metal(),[0,0,-2.27],'KMeter-ISO physical annular solder pad'));}
 // Five flat factory SWD pads, entirely inside the assembled cover; no
 // external user port is invented from these concealed production pads.
 for(let i=0;i<5;i++)pads.push(mesh(host.body,new THREE.CylinderGeometry(.62,.62,.06,32).rotateX(Math.PI/2),metal(),[-9.1,-10.5+i*2.5,-1.36],'KMeter-ISO concealed SWD test pad'));
 return{pcb,pads};
}
function packageIc(host,id,name,size,position,pins,pitch){
 const group=new THREE.Group();group.name=`KMeter-ISO ${id} ${name} physical package`;host.body.add(group);const dark=materials.plastic(0x252821,{roughness:.82});
 const body=mesh(group,new THREE.BoxGeometry(...size),dark,position,`${id} ${name} molded body`),leads=[];const side=pins/2;
 for(const sign of[-1,1])for(let i=0,n=pins===3?(sign<0?1:2):side;i<n;i++){const x=position[0]+(i-((pins===3?(sign<0?1:2):side)-1)/2)*pitch,y=position[1]+sign*(size[1]/2+.5),z=position[2]-size[2]/2+.2;leads.push(mesh(group,new THREE.BoxGeometry(.27,1,.18),metal(),[x,y,z],`${id} physical gull-wing lead`));}
 group.userData={role:'physical-component',part:name,reference:id,inferred:'Package dimensions and populated placement follow own PCB photo; concealed geometry is not an assembly drawing.'};return{group,body,leads};
}
function electronics(host){
 const mcu=packageIc(host,'U2','STM32F030F4P6',[6.5,4.4,1.05],[-.8,-9.1,.175],20,.65),isolator=packageIc(host,'U3','CA-IS3641HW',[10.1,7.5,2.5],[3.4,1.1,.9],16,1.27),converter=packageIc(host,'U4','MAX31855KASA+T',[4.9,3.9,1.45],[0,10.1,.4],8,1.27),ldo=packageIc(host,'U1','MD5333',[2.8,1.5,1.1],[7.2,-23.1,.2],3,1.2),passives=[];
 const dark=materials.plastic(0x272a24,{roughness:.85}),ceramic=materials.plastic(0xbda87f,{roughness:.9});
 const list=[['R1',-7.8,-21.4,'R'],['R2',-5.8,-11.8,'R'],['R3',-5.8,-10.3,'R'],['R4',-5.8,-8.8,'R'],['R5',-5.8,-7.3,'R'],['R6',7.5,6.5,'R'],['C1',8.4,-20.4,'C'],['C2',6.7,-20.4,'C'],['C3',6.9,-25.2,'C'],['C4',9,-23.1,'C'],['C6',-4.9,7.5,'C'],['C8',-6.8,7.5,'C'],['C9',-3.4,11.4,'C'],['C10',-4.8,-5.7,'C'],['C11',3.2,11.4,'C'],['C12',5.3,10.1,'C'],['C13',7.4,10.1,'C'],['C14',-.8,13.0,'C'],['C15',-3.7,-5.6,'C'],['C16',7.9,7.9,'C'],['FB1',-3.8,12.7,'R'],['FB2',3.8,12.7,'R'],['FB3',-7,5.3,'R']];
 for(const[id,x,y,type]of list){passives.push(mesh(host.body,new THREE.BoxGeometry(1.25,.7,.5),type==='R'?dark:ceramic,[x,y,-.1],`KMeter-ISO ${id} physical ${type==='R'?'resistor or ferrite':'capacitor'}`));for(const dx of[-.5,.5])passives.push(mesh(host.body,new THREE.BoxGeometry(.25,.72,.51),metal(),[x+dx,y,-.1],`KMeter-ISO ${id} metal termination`));}
 const led=mesh(host.body,new THREE.BoxGeometry(.8,1.4,.55),materials.plastic(0xe4d8be,{roughness:.47}),[-7.5,-22.5,-.075],'KMeter-ISO concealed LED1 red package');
 for(const o of[mcu.group,isolator.group,converter.group,ldo.group,...passives,led])o.position.z-=1.05;
 led.userData={role:'concealed-physical-led',part:'LED1 red',scope:'Exact v1.1 schematic confirms package; no independently verified exterior light path. No Led component, glow or emissive behavior.'};return{mcu,isolator,converter,ldo,passives,led};
}
function kSocket(host){
 const d=spec.thermocouple,group=new THREE.Group();group.name='KMeter-ISO PCC-SMP-K-100-CE K-type socket';host.body.add(group);const white=materials.plastic(0xe4e7db,{roughness:.68}),chrome=metal();
 const shape=roundedRect(17,5.2,.18,{cy:d.bodyCentreZMm});
 for(const slot of d.slots)shape.holes.push(roundedRect(slot.widthMm,slot.heightMm,.08,{cx:slot.x,cy:d.slotCentreZMm,path:new THREE.Path(),clockwise:true}));
 const geometry=new THREE.ExtrudeGeometry(shape,{depth:12.8,bevelEnabled:false,curveSegments:12}).rotateX(Math.PI/2);
 const body=mesh(group,geometry,white,[0,28,0],'KMeter-ISO true unequal flat-slot socket body');
 const caps=[],springs=[],tabs=[];
 // Both actual flat mating cavities run inward from +Y. A physical polymer
 // stop closes each cavity at the rear; the visible metal is recessed spring
 // strip, never four Grove-style round contacts or a fake shadow plane.
 for(const slot of d.slots){
  caps.push(mesh(group,new THREE.BoxGeometry(slot.widthMm+.2,.7,slot.heightMm+.2),white,[slot.x,15.55,d.slotCentreZMm],`KMeter-ISO ${slot.name} cavity rear stop`));
  for(const sign of[-1,1])springs.push(mesh(group,new THREE.BoxGeometry(slot.widthMm-.25,6.8,.09),chrome,[slot.x,23,d.slotCentreZMm+sign*(slot.heightMm/2-.055)],`KMeter-ISO ${slot.name} recessed flat contact spring`));
  tabs.push(mesh(group,new THREE.BoxGeometry(slot.widthMm,2.1,.22),chrome,[slot.x,14.15,.8],`KMeter-ISO ${slot.name} rear folded metal contact`));
  tabs.push(mesh(group,new THREE.BoxGeometry(.55,.55,2.2),chrome,[slot.x,13.55,-.2],`KMeter-ISO ${slot.name} through-PCB socket terminal`));
 }
 // The plated end rim has the same two actual holes. Its body surrounds the
 // bore rather than hiding a single rectangular cutout behind a dark decal.
 const rimShape=roundedRect(17.15,5.32,.16,{cy:1.2});for(const slot of d.slots)rimShape.holes.push(roundedRect(slot.widthMm,slot.heightMm,.08,{cx:slot.x,cy:d.slotCentreZMm,path:new THREE.Path(),clockwise:true}));
 const rim=mesh(group,new THREE.ExtrudeGeometry(rimShape,{depth:.35,bevelEnabled:false,curveSegments:12}).rotateX(Math.PI/2),chrome,[0,28,0],'KMeter-ISO plated socket face with unequal open slots');
 const strap=mesh(group,new THREE.BoxGeometry(17.2,1.25,.15),chrome,[0,24.25,3.875],'KMeter-ISO socket top retaining strap');
 const sides=[];for(const sign of[-1,1])sides.push(mesh(group,new THREE.BoxGeometry(.16,1.25,4.95),chrome,[sign*8.58,24.25,1.25],'KMeter-ISO socket retaining strap fold'));
 const ridges=[];for(const x of[-6.4,-2,2,6.4])ridges.push(mesh(group,new THREE.BoxGeometry(.35,2.6,.1),white,[x,26.2,3.85],'KMeter-ISO socket molded upper rib'));
 group.userData={role:'physical-connector',part:d.part,connector:d.connector,slotDimensionsMm:d.slots,slotDepthMm:d.slotDepthMm,inferred:'Own official v1.1 end/PCB photos scaled to native shell; actual unequal flat slots, spring strips, polymer stops and retaining strap reconstructed. Width/spacing/depth are not manufacturer tolerances.'};
 const port=host.add(new Port({id:'thermocouple',label:'K-type miniature flat thermocouple socket',connector:d.connector,position:d.position,quaternion:portQuaternion('top'),hitSize:[17.2,.8,5.3],pins:[{n:1,name:'T+',material:'Chromel'},{n:2,name:'T-',material:'Alumel'}],meta:{role:'visual-connector',face:'top',part:d.part,scope:'Physical mating anchor only; rejects Grove. No thermoelectric voltage, temperature, sampling, compensation, short/open-circuit, isolation or electrical behavior. No probe module is supplied without matching mechanical evidence.'}}));
 return{group,body,rim,strap,sides,ridges,caps,springs,tabs,port};
}
export function buildKmeterIso(host){
 addCadParts(host,data,{shell:materials.plastic(0xe7eae3,{roughness:.79})});const pcb=board(host),parts=electronics(host),k=kSocket(host),socket=connector(host.body,56,false,{height:5.2});socket.name='KMeter-ISO red open-top HY2.0-4P';
 const groveTails=[];for(const x of[-3,-1,1,3])groveTails.push(mesh(host.body,new THREE.BoxGeometry(.42,.42,3.55),metal(),[x,-20.85,-.675],'KMeter-ISO Grove folded through-PCB contact'));
 const grove=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'I2C',scope:'Physical attachment, four-wire cable and external pose only; no I2C, conversion, temperature values or electrical behavior'}}));
 const fixing=screw(host.body,[0,-16,-3.97],'back',1.4),shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,2.2,32).rotateX(Math.PI/2),metal(),[0,-16,-2.8],'KMeter-ISO fastening screw shank');
 host.add(new Component({id:'sensor',label:'KMeter-ISO visual appearance anchor',meta:{role:'visual-anchor',scope:'Passive appearance anchor. No temperature, compensation, sample rate, I2C, fault detection, isolation, thermoelectric or electrical behavior.'}}));
 host.kmeterIsoAssembly={pcb,electronics:parts,thermocouple:k,socket,grove,groveTails,fixing,shank};host.unitStickers=addStickers(host);
}
