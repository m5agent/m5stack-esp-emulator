import*as THREE from'three';
import{Component,Port,materials}from'../../core/index.js';
import{addCadParts}from'../../modeling/cad.js';
import{mesh,portQuaternion,screw}from'../../modeling/parts.js';
import{connector}from'../shared/parts.js';
import data from'./geometry-data.js';
import{spec}from'./dimensions.js';
import{addStickers}from'./stickers.js';
const hole=(s,x,y,r)=>{const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,true);s.holes.push(p);};
function pcb(host){
 const s=new THREE.Shape();s.moveTo(-7.4,-21.7);s.lineTo(-5.3,-21.7);s.lineTo(-5.3,-17.1);s.lineTo(5.3,-17.1);s.lineTo(5.3,-21.7);s.lineTo(7.4,-21.7);s.quadraticCurveTo(10.4,-21.7,10.4,-18.7);s.lineTo(10.4,-15.2);s.lineTo(8,-15.2);s.absarc(8,-12,3.2,-Math.PI/2,Math.PI/2,true);s.lineTo(10.4,-8.8);s.lineTo(10.4,19);s.quadraticCurveTo(10.4,22,7.4,22);s.lineTo(-7.4,22);s.quadraticCurveTo(-10.4,22,-10.4,19);s.lineTo(-10.4,-8.8);s.lineTo(-8,-8.8);s.absarc(-8,-12,3.2,Math.PI/2,-Math.PI/2,true);s.lineTo(-10.4,-15.2);s.lineTo(-10.4,-18.7);s.quadraticCurveTo(-10.4,-21.7,-7.4,-21.7);s.closePath();hole(s,0,-12,2.1);
 for(const x of[-3,-1,1,3])hole(s,x,-16.85,.3);
 const board=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:48}),materials.plastic(0x1c6545,{roughness:.91}),[0,0,-.7],'NFC U216 physical scalloped PCB');board.userData={role:'physical-pcb',scope:'Own assembled shell constrains outline/clearances; concealed PCB outline/thickness/installed plane inferred'};
 const pads=[];for(const x of[-3,-1,1,3]){const p=new THREE.Shape();p.absarc(x,-16.85,.55,0,Math.PI*2,false);hole(p,x,-16.85,.3);pads.push(mesh(host.body,new THREE.ExtrudeGeometry(p,{depth:.045,bevelEnabled:false,curveSegments:32}),materials.metal(0xc0b48d,{roughness:.48}),[0,0,-.745],'NFC U216 Grove solder annulus'));}
 return{board,pads};
}
function physicalAntenna(host){
 // This is solid copper on the concealed PCB, NOT an animated RF scan overlay.
 // ANT1 existence is schematic-confirmed; route, turns and dimensions are
 // deliberately recorded as reconstruction because no PCB artwork was supplied.
 const g=new THREE.Group();g.name='NFC U216 physical ANT1 planar copper winding';host.body.add(g);g.userData={role:'physical-antenna',part:'ANT1',scope:'Planar antenna type from own schematic; concealed route, three turns, trace widths and position are inferred, not measured RF layout or an emitted field'};
 const points=[[-1.3,-7],[-9.3,-7],[-9.3,21],[9.3,21],[9.3,-6.1],[-8.4,-6.1],[-8.4,20.1],[8.4,20.1],[8.4,-5.2],[-7.5,-5.2],[-7.5,19.2],[7.5,19.2],[7.5,-4.3],[1.3,-4.3]],traces=[],copper=materials.metal(0xa5874f,{roughness:.7,metalness:.65});
 const trace=(a,b,z)=>{const dx=b[0]-a[0],dy=b[1]-a[1],o=mesh(g,new THREE.BoxGeometry(Math.hypot(dx,dy)+.4,.4,.035),copper,[(a[0]+b[0])/2,(a[1]+b[1])/2,z],'NFC U216 solid ANT1 PCB copper trace');o.rotation.z=Math.atan2(dy,dx);traces.push(o);return o;};
 for(let i=1;i<points.length;i++)trace(points[i-1],points[i],.123);
 // The inner end returns on the reverse layer via a plated physical via.
 trace([1.3,-4.3],[1.3,-7],-.722);const vias=[];for(const y of[-4.3,-7])vias.push(mesh(g,new THREE.CylinderGeometry(.29,.29,.85,24).rotateX(Math.PI/2),materials.metal(0x9f8857,{roughness:.68}),[1.3,y,-.3],'NFC U216 antenna feed plated via'));
 return{group:g,traces,vias};
}
function electronics(host){
 const group=new THREE.Group();group.name='NFC U216 ST25R3916 and RF matching physical assembly';host.body.add(group);group.userData={role:'physical-electronics',scope:'Own schematic population, concealed package XYZ and envelopes visually reconstructed; no electrical/NFC/reader/card/firmware behavior'};
 const dark=materials.plastic(0x282c29,{roughness:.83}),metal=materials.metal(0xb9bbb1,{roughness:.5}),ceramic=materials.plastic(0x998963,{roughness:.85}),parts=[];
 const chip=mesh(group,new THREE.BoxGeometry(5,5,.9),dark,[0,1.8,-1.23],'NFC U216 U1 ST25R3916-AQWT QFN32 body');chip.userData={role:'physical-sensor-package',part:'ST25R3916-AQWT',package:'QFN32',scope:'Correct own U216 chip; package size/installation envelope inferred'};
 const leads=[];for(const side of[-1,1])for(let i=0;i<8;i++){const v=(i-3.5)*.5;leads.push(mesh(group,new THREE.BoxGeometry(.28,.55,.14),metal,[v,1.8+side*2.38,-.77],'NFC U216 QFN32 solder terminal'));leads.push(mesh(group,new THREE.BoxGeometry(.55,.28,.14),metal,[side*2.38,1.8+v,-.77],'NFC U216 QFN32 solder terminal'));}
 mesh(group,new THREE.CylinderGeometry(.17,.17,.02,24).rotateX(Math.PI/2),materials.plastic(0x6d726c),[-1.8,3.6,-1.69],'NFC U216 QFN pin-one dot');
 const ldo=mesh(group,new THREE.BoxGeometry(2,2,.7),dark,[-5.2,-4.6,-1.1],'NFC U216 U3 TPAP7343D-33FS4 body');for(const dx of[-1,1])for(const dy of[-.55,.55])parts.push(mesh(group,new THREE.BoxGeometry(.4,.35,.12),metal,[-5.2+dx,-4.6+dy,-.76],'NFC U216 LDO solder terminal'));
 const crystal=mesh(group,new THREE.BoxGeometry(3.2,2.5,.8),materials.metal(0xabaea6,{roughness:.5}),[5.3,-3.5,-1.15],'NFC U216 X1 27.12 MHz metal crystal');
 const passive=(ref,x,y,w=1.1,h=.65,color=ceramic)=>{const p=mesh(group,new THREE.BoxGeometry(w,h,.5),color,[x,y,-1],`NFC U216 ${ref} physical passive`);parts.push(p);for(const dx of[-(w-.25)/2,(w-.25)/2])parts.push(mesh(group,new THREE.BoxGeometry(.27,h+.03,.52),metal,[x+dx,y,-1],`NFC U216 ${ref} passive termination`));return p;};
 for(const[ref,x,y,w,h]of[['L1',-3.5,-3.4,1.6,.8],['L2',3.1,-3.4,1.6,.8],['R1',-1.5,-7.1],['R2',1.7,-7.1],['C1',-3.9,-5],['C2',-2.4,-5],['C4',-.8,-5],['C5',.8,-5],['C6',2.4,-5],['C7',-3.9,-6.4],['C8',-2.4,-6.4],['C9',3.9,-5],['C11',4,-6.4],['C13',2.7,-6.4]])passive(ref,x,y,w,h);
 // C3 and C10 are NC on the own schematic; keep only empty solder pads.
 const unpopulated=[];for(const[x,y]of[[-5.2,-7],[5.1,-7]])for(const dx of[-.42,.42])unpopulated.push(mesh(group,new THREE.BoxGeometry(.3,.65,.035),metal,[x+dx,y,-.723],'NFC U216 NC C3/C10 unpopulated solder land'));
 for(let i=0;i<18;i++){const x=i<9?-4.5:4.5,y=8.5-(i%9)*1.3;passive(`decoupling ${i+1}`,x,y);}
 for(const[ref,x,y]of[['R3',-4.2,-9],['R4',4.2,-9],['R5',-6.5,2],['C29',-6.7,-2.5],['C30',-6.7,-5.8],['C12',4.3,-1.5],['C14',6.1,-1.5]])passive(ref,x,y);
 return{group,chip,leads,ldo,crystal,parts,unpopulated};
}
export function buildNfc(host){
 addCadParts(host,data,{shell:materials.plastic(0xe7e9e4,{roughness:.77})});const board=pcb(host),antenna=physicalAntenna(host),physicalElectronics=electronics(host);
 const socket=connector(host.body,48,false,{height:5.2});socket.name='NFC U216 red open-top HY2.0-4P';const contacts=socket.children.filter(o=>o.name==='Grove contact pin');
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'I2C',documentedAddress:'0x50',scope:'Physical connector/cable attachment only; no I2C transaction, RF field, NFC/RFID scanning, tag reading/writing, card emulation, protocol, state or firmware'}}));
 const fixing=screw(host.body,[0,-12,-3.97],'back',1.35),shank=mesh(host.body,new THREE.CylinderGeometry(.6,.6,2.25,32).rotateX(Math.PI/2),materials.metal(0x949a96),[0,-12,-2.8],'NFC U216 fastening screw shank');
 host.add(new Component({id:'sensor',label:'ST25R3916 visual package anchor',position:[0,1.8,-1.7],meta:{role:'visual-anchor',part:'ST25R3916-AQWT',scope:'Passive physical package anchor only; no read, write, tag, field, card emulation, scan, recognition, NFC, RFID, I2C or firmware behavior'}}));
 const artwork=addStickers(host);host.nfcAssembly={pcb:board,antenna,electronics:physicalElectronics,socket,contacts,port,fixing,shank,artwork};
}
