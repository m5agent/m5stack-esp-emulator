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
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:36}),materials.plastic(0x285e43,{roughness:.88}),[0,0,-.9],'ADC v1.1 physical PCB with clear mounting scallops and Grove notch');pcb.userData={role:'physical-pcb',scope:'Reconstructed board envelope; no copper routes, values or electrical behavior'};
 const dark=materials.plastic(0x222624,{roughness:.8}),metal=materials.metal(0xb9b7a6,{roughness:.46}),ceramic=materials.plastic(0xad8960,{roughness:.8}),parts=[];
 const part=(name,w,h,d,pos,mat=dark)=>{const p=slab(host.body,w,h,d,.10,pos,mat,[],.025);p.name='ADC v1.1 '+name;parts.push(p);return p;};
 const ads1110=part('U2 ADS1110 six-lead ADC package',1.65,2.9,.9,[1.9,2.3,-.1]);
 for(const side of[-1,1])for(let i=0;i<3;i++)parts.push(mesh(host.body,new THREE.BoxGeometry(.65,.3,.18),metal,[1.9+side*1.1,2.3+(i-1)*.95,.05],'ADC v1.1 ADS1110 gull-wing lead'));
 const lm358=part('U1 LM358DR2G eight-lead buffer package',3.9,4.9,1.3,[-3.3,4,-.1]);
 for(const side of[-1,1])for(let i=0;i<4;i++)parts.push(mesh(host.body,new THREE.BoxGeometry(.9,.37,.18),metal,[-3.3+side*2.35,4+(i-1.5)*1.27,.05],'ADC v1.1 LM358 gull-wing lead'));
 const regulators=[];
 for(const[x,y]of[[-6.5,8.7],[5.5,6.2]]){
  regulators.push(part('HT7533 regulator package',1.6,2.9,.9,[x,y,-.1]));
  for(const dx of[-.95,.95])parts.push(mesh(host.body,new THREE.BoxGeometry(.55,.32,.14),metal,[x+dx,y,.05],'ADC v1.1 HT7533 lead'));
 }
 for(const[x,y,w,h]of[[6,1.1,1.1,1.8],[-7,1.2,1,1.5],[-6.5,5.8,1,1.6],[5.7,9.6,1,1.6],[1.8,6.1,1,1.6]])part('C1-C5 capacitor envelope',w,h,.5,[x,y,-.1],ceramic);
 for(const[x,y,w,h]of[[-2.2,8.4,1,1.5],[-.3,8.4,1,1.5],[4.6,3.5,.8,1.5],[4.6,1.6,.8,1.5],[-1,1.6,.8,1.5],[-2,-.9,.8,1.5]])part('R1-R6 fixed resistor envelope',w,h,.4,[x,y,-.1]);
 return{pcb,parts,ads1110,lm358,regulators};
}
function grove(host){
 const frame=new THREE.Group();frame.name='ADC v1.1 burgundy open-top HY2.0-4P';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(FACE.bottom);host.body.add(frame);
 const plastic=materials.plastic(spec.grove.color,{roughness:.62}),metal=materials.metal(0xb9ad82,{roughness:.43}),box=(size,p,name,mat=plastic)=>mesh(frame,new THREE.BoxGeometry(...size),mat,p,'ADC v1.1 Grove '+name);
 for(const x of[-4.65,4.65]){box([.7,5.2,6.5],[x,0,-3.25],'side wall');box([.85,.75,6.5],[Math.sign(x)*3.85,2.2,-3.25],'guide rail');box([.7,.9,.6],[x,2.05,0],'mouth ear');}
 box([8.6,.7,6.5],[0,-2.25,-3.25],'floor');box([8.6,5.2,.6],[0,0,-6.2],'recessed rear wall');box([8.6,2.65,3.6],[0,-1.25,-4.7],'recessed contact carrier');box([3.4,.65,2.7],[0,1.2,-5.1],'short locking tongue');
 const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4],[(i-1.5)*2,-.15,-3.2],`contact ${i+1}`,metal));box([.42,1.2,.42],[(i-1.5)*2,-1.4,-5.7],`PCB tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],pinGrid:{cols:4,rows:1,pitch:2,center:[0,-.15],order:col=>4-col},meta:{role:'visual-connector',face:'bottom',protocol:'I2C',i2cAddress:'0x48',scope:'Connector and physical cable pose only; no bus, ADC conversion, voltage, current, short-circuit or firmware behavior'}}));return{frame,contacts,port};
}
function terminal(host){
 const frame=new THREE.Group();frame.name='ADC v1.1 fixed orange HT3.96-2P socket';host.body.add(frame);
 const orange=materials.plastic(0xf29a47,{roughness:.65}),metal=materials.metal(0xb9b8a8,{roughness:.43}),parts=[];
 const solid=(name,w,h,d,p,holes=[])=>{const m=slab(frame,w,h,d,.18,p,orange,holes,.035);m.name='ADC v1.1 fixed terminal '+name;parts.push(m);return m;};
 const floor=solid('floor',7.92,9.8,.6,[0,11.1,-.7]);
 for(const x of[-3.61,3.61])solid('side cheek',.7,9.8,5.65,[x,11.1,-.1]);
 const rear=solid('recessed rear wall',6.52,.7,5.65,[0,6.35,-.1]);
 const roof=solid('roof with physical positive/negative print support',7.92,9.8,.65,[0,11.1,5.55]);
 for(const x of[0])solid('lower channel rib',.4,8.2,.55,[x,11.8,-.1]);
 const contacts=[];for(const[i,x]of spec.terminal.pinX.entries()){
  const pin=mesh(frame,new THREE.BoxGeometry(.65,8.3,.65),metal,[x,10.9,1.2],`ADC v1.1 fixed terminal ${spec.terminal.names[i]} contact pin`);pin.userData={schematicPin:spec.terminal.pinNumbers[i],signal:spec.terminal.names[i]};contacts.push(pin);
  mesh(frame,new THREE.BoxGeometry(.65,1.7,.65),metal,[x,5.9,1.2],'ADC v1.1 fixed terminal bent lead');mesh(frame,new THREE.BoxGeometry(.65,.65,1.9),metal,[x,5.1,.25],'ADC v1.1 fixed terminal PCB tail');
 }
 const port=host.add(new Port({id:'terminal',label:'Analog input · HT3.96-2P',connector:'ht3.96-2p',position:spec.terminal.position,hitSize:[7.92,1,6.9],pins:spec.terminal.names.map((name,i)=>({n:spec.terminal.pinNumbers[i],name})),pinGrid:{cols:2,rows:1,pitch:3.96,center:[0,-1.4],order:col=>col+1},meta:{role:'visual-connector',face:'top',signalRole:'analog-input',scope:'Physical connector and detachable plug only; no continuity, voltage, current, ADC conversion or short-circuit behavior',terminalOrderEvidence:'Exact own front print + / − corresponds to own schematic P1 pins1 / 2'}}));return{frame,floor,rear,roof,contacts,parts,port};
}
export function buildADCv11(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe8e9e1,{roughness:.77})}),pcb=board(host),input=grove(host),output=terminal(host);
 screw(host.body,[0,-4,-3.98],'back',1.3);
 host.add(new Component({id:'sensor',label:'ADC v1.1 visual anchor',meta:{role:'visual-anchor',scope:'Appearance anchor only; no ADC codes, conversion, voltage/current, power, short-circuit, electrical or firmware behavior'}}));
 host.adcV11Assembly={parts,pcb,input,terminal:output};host.adcV11Assembly.artwork=addStickers(host);
}
