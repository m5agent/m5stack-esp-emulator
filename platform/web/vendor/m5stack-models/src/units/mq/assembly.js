import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
import data from './geometry-data.js';
const tin=()=>materials.metal(0xb4b6a8,{roughness:.49});
function bore(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(h);}
function pcb(host){
 const s=new THREE.Shape(),edge=10.4,hy=-20,r=3.35,dx=edge-8,a=Math.acos(dx/r),dy=Math.sqrt(r*r-dx*dx);
 s.moveTo(-5.35,-30.5);s.lineTo(-8.1,-30.5);s.lineTo(-edge,-28.2);s.lineTo(-edge,hy-dy);s.absarc(-8,hy,r,Math.PI+a,Math.PI-a,false);s.lineTo(-edge,27.6);s.lineTo(-8,30);s.lineTo(8,30);s.lineTo(edge,27.6);s.lineTo(edge,hy+dy);s.absarc(8,hy,r,a,Math.PI*2-a,false);s.lineTo(edge,-28.2);s.lineTo(8.1,-30.5);s.lineTo(5.35,-30.5);s.lineTo(5.35,-23.6);s.lineTo(-5.35,-23.6);s.closePath();
 bore(s,0,-20,1.85);for(const x of[-7.5,7.5])bore(s,x,15,1.5);for(const x of[-3,-1,1,3])bore(s,x,-24.5,.35);
 const board=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:40}),materials.plastic(0x205c41,{roughness:.94}),[0,0,-1.7],'MQ physical main PCB with open mounting scallops and true fastening bores');
 board.userData={role:'physical-pcb',inferred:'Concealed board contour/Z and drill fit reconstructed within exact shell; no copper/production PCB claim'};return board;
}
function population(host){
 const group=new THREE.Group();group.name='MQ schematic-confirmed concealed electronics';host.body.add(group);const dark=materials.plastic(0x242723,{roughness:.9}),ceramic=materials.plastic(0xbbaa86,{roughness:.94}),metal=tin(),items=[];
 const box=(name,size,p,m=dark)=>{const o=mesh(group,new THREE.BoxGeometry(...size),m,p,'MQ '+name);items.push(o);return o;};
 const mcu=box('U2 STM32G030F6P6 TSSOP20',[6.5,4.4,1.05],[0,-8,-.25]);for(const sy of[-1,1])for(let i=0;i<10;i++)box('U2 physical gull-wing lead',[.27,1,.17],[(i-4.5)*.65,-8+sy*2.65,-.68],metal);
 const ldo=box('U3 XC6228D332VR-G',[2.9,1.6,1.0],[-6.3,-25,-.3]),opamp=box('U4 LMV321M5/NOPB',[2.9,1.6,1.05],[5.3,6,-.25]),mosfet=box('Q1 AO3400',[2.9,1.6,1.05],[-5,5,-.25]);
 for(const [name,x,y]of[['U3',-6.3,-25],['U4',5.3,6],['Q1',-5,5]])for(const sy of[-1,1])for(let i=0,n=sy<0?1:2;i<n;i++)box(name+' metal termination',[.36,.8,.17],[x+(i-(n-1)/2)*1.8,y+sy*1.05,-.68],metal);
 const passives=[];for(const[id,x,y,c]of[['R1',2,6,0],['R8',2,4.4,0],['R10',5.3,10,0],['R11',7.3,6,0],['R12',-5,2.2,0],['R13',-7.1,3.6,0],['R2',-5,8,0],['R14',-7.2,-3,0],['R16',-2,-15,0],['R17',0,-15,0],['C1',4,-8,1],['C2',-8.5,-25,1],['C3',-6.5,-27.2,1],['C4',-4.4,-25,1],['C5',-4.4,-27.2,1],['C6',-4,-12,1],['C7',7.3,8,1],['C8',4,-12,1],['L1',-2,1.4,0]]){passives.push(box(id+' physical passive',[1.25,.7,.5],[x,y,-.6],c?ceramic:dark));for(const sx of[-1,1])box(id+' solder termination',[.25,.72,.51],[x+sx*.5,y,-.6],metal);}
 const ntc=box('R18 KNTC0603/10KF3950 thermistor',[1.6,.8,.5],[-7.2,-.8,-.6],materials.plastic(0x64563c));
 const diodes=[];for(const[id,x]of[['D2',2],['D3',4]]){diodes.push(box(id+' 1N4148WS physical package',[1.7,.9,.7],[x,1.3,-.5]));for(const sx of[-1,1])box(id+' metal end',[.3,.91,.71],[x+sx*.7,1.3,-.5],metal);}
 const led=box('D1 GREEN0603 concealed physical package',[1.6,.8,.6],[6.9,-15,-.55],materials.plastic(0xc7d3a0,{roughness:.6}));led.userData={role:'concealed-physical-led',part:'D1 GREEN0603',scope:'No confirmed exterior light path; no Led component, glow or automatic power response'};
 const pads=[];for(let i=0;i<5;i++)pads.push(mesh(group,new THREE.CylinderGeometry(.54,.54,.06,24).rotateX(Math.PI/2),metal,[-8.8,1+i*2.5,-1.74],'MQ concealed P1 SWD manufacturing pad'));
 group.userData={role:'physical-electronics',scope:'Exact schematic establishes identities; hidden populated locations/package sizes reconstructed for appearance only'};return{group,mcu,ldo,opamp,mosfet,ntc,led,passives,diodes,pads,items};
}
function socket(host){
 const frame=new THREE.Group();frame.name='MQ fixed circular J3 six-hole socket and J2/J4 adapter';host.body.add(frame);const polymer=materials.plastic(0x3a3c35,{roughness:.84}),metal=tin(),green=materials.plastic(0x225b3d,{roughness:.93}),s=new THREE.Shape();s.absarc(0,9,9.65,0,Math.PI*2,false);
 for(const p of spec.mq5.pins)bore(s,p.x,9+p.z,.72);
 const body=mesh(frame,new THREE.ExtrudeGeometry(s,{depth:7.8,bevelEnabled:false,curveSegments:64}).rotateX(Math.PI/2),polymer,[0,32.4,0],'MQ six genuinely open round socket channels');
 const rear=mesh(frame,new THREE.CylinderGeometry(9.5,9.5,.7,96),polymer,[0,24.25,9],'MQ socket physical rear stop');
 const springs=[],rings=[];
 for(const p of spec.mq5.pins){const sh=new THREE.Shape();sh.absarc(0,0,.72,0,Math.PI*2,false);bore(sh,0,0,.57);rings.push(mesh(frame,new THREE.ExtrudeGeometry(sh,{depth:5.5,bevelEnabled:false,curveSegments:24}).rotateX(Math.PI/2),metal,[p.x,31.6,9+p.z],`MQ recessed socket metal sleeve pin${p.n}`));
  for(const sx of[-1,1])springs.push(mesh(frame,new THREE.BoxGeometry(.09,4.5,.54),metal,[p.x+sx*.51,28.5,9+p.z],`MQ socket pin${p.n} inner spring contact`));
 }
 const adapterShape=new THREE.Shape();adapterShape.absarc(0,9,9.2,0,Math.PI*2,false);for(const p of spec.mq5.pins)bore(adapterShape,p.x,9+p.z,.6);
 const adapter=mesh(frame,new THREE.ExtrudeGeometry(adapterShape,{depth:.8,bevelEnabled:false,curveSegments:64}).rotateX(Math.PI/2),green,[0,23.7,0],'MQ fixed circular J3/J4 adapter PCB with six plated holes');
 const tails=[],headerBody=mesh(frame,new THREE.BoxGeometry(8,5.1,2.4),polymer,[0,21.6,2.4],'MQ J4 actual2×3 female-header insulator');
 for(const x of[-2.54,0,2.54])for(const y of[20.33,22.87]){tails.push(mesh(frame,new THREE.BoxGeometry(.64,.64,3.0),metal,[x,y,.55],'MQ J2 actual2×3 board header pin'));tails.push(mesh(frame,new THREE.BoxGeometry(.16,.8,2.7),metal,[x-.4,y,2.0],'MQ J4 recessed female spring'));}
 for(const p of spec.mq5.pins){tails.push(mesh(frame,new THREE.CylinderGeometry(.45,.45,2.1,20),metal,[p.x,23.2,9+p.z],`MQ J3 soldered rear tail${p.n}`));}
 const port=host.add(new Port({id:'mq5',label:'MQ-5 removable six-round-pin sensor socket',connector:spec.mq5.connector,position:spec.mq5.position,hitSize:[19.3,1,19.3],pins:spec.mq5.pins.map(({n,name})=>({n,name})),meta:{role:'visual-connector',face:'top',part:'J3 MQ-series socket',source:'Exact U199 photo08 shows round-pin MQ-5 can detached; J3/J4 adapter remains fixed',scope:'Mechanical appearance/mating only. Rejects Grove. No gas, heater, alarm, ADC, temperature, electrical continuity or firmware behavior. Only the supplied MQ-5 cartridge is modeled.'}}));
 frame.userData={role:'physical-fixed-sensor-socket',scope:'Socket, adapter PCB and J2/J4 stay with Unit on cartridge removal. Contact profile, bore depth and concealed header positions estimated.'};return{frame,body,rear,springs,rings,adapter,tails,headerBody,port};
}
export function buildMq(host){
 const shell=addCadParts(host,data,{shell:materials.plastic(0x353938,{roughness:.77})}),board=pcb(host),electronics=population(host),mqSocket=socket(host),grove=connector(host.body,64,false,{height:5.2});grove.name='MQ burgundy open-top HY2.0-4P with four actual contacts';
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'I2C',documentedAddress:'0x11',scope:'Physical connector, four-wire cable and external pose only. No gas values, I2C, heater, alarm, ADC, temperature or electrical behavior'}}));
 const screws=[screw(host.body,[0,-20,-3.98],'back',1.3),...[-7.5,7.5].map(x=>screw(host.body,[x,15,-3.98],'back',1.3))];
 host.add(new Component({id:'sensor',label:'Unit MQ passive appearance anchor',meta:{role:'visual-anchor',scope:'Passive appearance only. No concentration, gas detection, heater state, alarm, ADC, temperature, electrical, protocol or firmware behavior.'}}));
 host.mqAssembly={shell,board,electronics,mqSocket,grove,port,screws};host.unitStickers=addStickers(host);
}
