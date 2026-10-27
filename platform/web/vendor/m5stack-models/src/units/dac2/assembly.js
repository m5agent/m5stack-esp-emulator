import *as THREE from 'three';
import{Component,Port,materials}from'../../core/index.js';
import{addCadParts}from'../../modeling/cad.js';
import{mesh,slab,screw,FACE,portQuaternion}from'../../modeling/parts.js';
import{spec}from'./dimensions.js';import data from'./geometry-data.js';import{addStickers}from'./stickers.js';

function board(host){
 const x=10.5,y=-4,r=3.25,dx=x-8,dy=Math.sqrt(r*r-dx*dx),a=Math.acos(dx/r),s=new THREE.Shape();
 // Native mounting bosses are outside-boundary scallops, not crossing holes.
 s.moveTo(-5.35,-14.8);s.lineTo(-7,-14.8);s.lineTo(-x,-11.5);s.lineTo(-x,y-dy);s.absarc(-8,y,r,Math.PI+a,Math.PI-a,false);s.lineTo(-x,12.5);s.lineTo(-8.3,14.8);s.lineTo(8.3,14.8);s.lineTo(x,12.5);s.lineTo(x,y+dy);s.absarc(8,y,r,a,Math.PI*2-a,false);s.lineTo(x,-11.5);s.lineTo(7,-14.8);s.lineTo(5.35,-14.8);s.lineTo(5.35,-8.75);s.lineTo(-5.35,-8.75);s.closePath();
 const hole=new THREE.Path();hole.absarc(0,-4,1.9,0,Math.PI*2,false);s.holes.push(hole);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:36}),materials.plastic(0x285e43,{roughness:.88}),[0,0,-.9],'DAC2 physical PCB with clear mounting scallops and Grove notch');pcb.userData={role:'physical-pcb',scope:'Reconstructed board envelope; no copper routes, values or electrical behavior'};
 const dark=materials.plastic(0x222624,{roughness:.8}),metal=materials.metal(0xb9b7a6,{roughness:.46}),ceramic=materials.plastic(0xad8960,{roughness:.8}),parts=[];
 const part=(name,w,h,d,pos,mat=dark)=>{const p=slab(host.body,w,h,d,.12,pos,mat,[],.025);p.name='DAC2 '+name;parts.push(p);return p;};
 const gp8413=part('U1 GP8413 physical ten-lead DAC package',3,4.8,.85,[-2.5,2.1,-.1]);
 for(const side of[-1,1])for(let i=0;i<5;i++)parts.push(mesh(host.body,new THREE.BoxGeometry(.75,.34,.18),metal,[-2.5+side*1.8,2.1+(i-2)*.9,.05],'DAC2 GP8413 gull-wing lead'));
 part('U2 TPS61040DBVR boost package',1.7,2.9,.9,[5.7,1.7,-.1]);
 part('U3 HX6306P332MR regulator package',1.6,2.9,.8,[-6.9,2,-.1]);
 part('L1 2520 inductor',2.5,2,1.1,[5.8,5,-.1]);part('D3 rectifier package',2.4,1.4,.75,[2.2,5,-.1]);
 for(const[x,y]of[[-5.7,8.8],[-1.7,8.8]])part('D1/D2 output TVS package',1.7,2.3,.7,[x,y,-1.6]);
 for(const[x,y,w,h]of[[2,2.4,1.1,1.8],[2,-.2,1.1,1.8],[-7,5,1,1.5],[7,-1.2,1,1.5]])part('decoupling capacitor',w,h,.5,[x,y,-.1],ceramic);
 const straps=[];for(let i=0;i<3;i++){
  const x=-2.7+i*2.2,y=-1.6;
  for(const dy of[-.43,.43])parts.push(mesh(host.body,new THREE.BoxGeometry(.7,.48,.08),metal,[x,y+dy,-.05],`DAC2 JP${i+1} address solder pad`));
  if(i===0)straps.push(part('JP1 A0 populated 0R hardware strap',.65,1.1,.38,[x,y,-.04]));
 }
 return{pcb,parts,gp8413,straps};
}
function grove(host){
 const frame=new THREE.Group();frame.name='DAC2 burgundy open-top HY2.0-4P';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(FACE.bottom);host.body.add(frame);
 const plastic=materials.plastic(spec.grove.color,{roughness:.62}),metal=materials.metal(0xb9ad82,{roughness:.43}),box=(size,p,name,mat=plastic)=>mesh(frame,new THREE.BoxGeometry(...size),mat,p,'DAC2 Grove '+name);
 for(const x of[-4.65,4.65]){box([.7,5.2,6.5],[x,0,-3.25],'side wall');box([.85,.75,6.5],[Math.sign(x)*3.85,2.2,-3.25],'guide rail');box([.7,.9,.6],[x,2.05,0],'mouth ear');}
 box([8.6,.7,6.5],[0,-2.25,-3.25],'floor');box([8.6,5.2,.6],[0,0,-6.2],'recessed rear wall');box([8.6,2.65,3.6],[0,-1.25,-4.7],'recessed contact carrier');box([3.4,.65,2.7],[0,1.2,-5.1],'short locking tongue');
 const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4],[(i-1.5)*2,-.15,-3.2],`contact ${i+1}`,metal));box([.42,1.2,.42],[(i-1.5)*2,-1.4,-5.7],`PCB tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],pinGrid:{cols:4,rows:1,pitch:2,center:[0,-.15],order:col=>4-col},meta:{role:'visual-connector',face:'bottom',protocol:'I2C',i2cAddress:'0x59',scope:'Connector and physical cable pose only; no bus, DAC conversion, voltage, current, short-circuit or firmware behavior'}}));return{frame,contacts,port};
}
function terminal(host){
 const frame=new THREE.Group();frame.name='DAC2 fixed orange HT3.96-4P socket';host.body.add(frame);
 const orange=materials.plastic(0xf29a47,{roughness:.65}),metal=materials.metal(0xb9b8a8,{roughness:.43}),parts=[];
 const solid=(name,w,h,d,p,holes=[])=>{const m=slab(frame,w,h,d,.18,p,orange,holes,.035);m.name='DAC2 fixed terminal '+name;parts.push(m);return m;};
 const floor=solid('floor',15.8,9.8,.6,[0,11.1,-.7]);
 for(const x of[-7.55,7.55])solid('side cheek',.7,9.8,5.65,[x,11.1,-.1]);
 const rear=solid('recessed rear wall',14.4,.7,5.65,[0,6.35,-.1]);
 const windows=spec.terminal.pinX.map(cx=>({w:2.6,h:1.1,r:.08,cx,cy:-3.65}));
 const roof=solid('roof with four real inspection windows',15.8,9.8,.65,[0,11.1,5.55],windows);
 for(const x of[-3.96,0,3.96])solid('lower channel rib',.4,8.2,.55,[x,11.8,-.1]);
 const contacts=[];for(const[i,x]of spec.terminal.pinX.entries()){
  const pin=mesh(frame,new THREE.BoxGeometry(.65,8.3,.65),metal,[x,10.9,1.2],`DAC2 fixed terminal ${spec.terminal.names[i]} contact pin`);pin.userData={schematicPin:spec.terminal.pinNumbers[i],signal:spec.terminal.names[i]};contacts.push(pin);
  mesh(frame,new THREE.BoxGeometry(.65,1.7,.65),metal,[x,5.9,1.2],'DAC2 fixed terminal bent lead');mesh(frame,new THREE.BoxGeometry(.65,.65,1.9),metal,[x,5.1,.25],'DAC2 fixed terminal PCB tail');
 }
 const port=host.add(new Port({id:'terminal',label:'Dual DAC output · HT3.96-4P',connector:'ht3.96-4p',position:spec.terminal.position,hitSize:[15.8,1,6.9],pins:spec.terminal.names.map((name,i)=>({n:spec.terminal.pinNumbers[i],name})),pinGrid:{cols:4,rows:1,pitch:3.96,center:[0,-1.4],order:col=>4-col},meta:{role:'visual-connector',face:'top',signalRole:'dual-analog-output',scope:'Physical connector and detachable plug only; no continuity, voltage, current, DAC conversion or short-circuit behavior',terminalOrderEvidence:'Exact own front print V0/G/V1/G corresponds to schematic P1 pins4/3/2/1'}}));return{frame,floor,rear,roof,contacts,parts,port};
}
export function buildDAC2(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe8e9e1,{roughness:.77})}),pcb=board(host),input=grove(host),output=terminal(host);
 screw(host.body,[0,-4,-3.98],'back',1.3);
 host.add(new Component({id:'sensor',label:'DAC2 visual anchor',meta:{role:'visual-anchor',scope:'Appearance anchor only; no DAC codes, conversion, voltage/current, power, short-circuit, electrical or firmware behavior'}}));
 const artwork=addStickers(host);host.dac2Assembly={parts,pcb,input,terminal:output,artwork};
}
