import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {FACE,mesh,portQuaternion} from '../../modeling/parts.js';
import {unitPcb} from '../shared/parts.js';
import {spec} from './dimensions.js';

/** Real open-top housings and contact tips; no photograph or cavity-cover plane. */
function addSocket(host,{id,position,face,turn=0,color,channel}){
 const d={...spec.socket,depth:face==='front'?spec.socket.uprightDepth:spec.socket.depth},group=new THREE.Group(),rotation=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),turn);
 group.name=`PbHUB ${id} socket`;group.position.fromArray(position);group.quaternion.copy(FACE[face]).premultiply(rotation);host.body.add(group);
 group.userData={visualFamily:'open-top-grove',connectorId:id};
 const box=(size,pos,name,metal=false)=>mesh(group,new THREE.BoxGeometry(...size),metal?materials.metal(0xb9ae84,{roughness:.42}):materials.plastic(color,{roughness:.65}),pos,`PbHUB ${id} ${name}`);
 for(const sign of [-1,1])box([d.wall,d.height,d.depth],[sign*(d.width-d.wall)/2,0,-d.depth/2],`side wall ${sign}`);
 box([d.width-2*d.wall,d.wall,d.depth],[0,-(d.height-d.wall)/2,-d.depth/2],'floor');
 box([d.width-2*d.wall,d.height,.6],[0,0,-d.depth+.3],'rear wall');
 for(const sign of [-1,1]){
  box([.9,.8,d.depth],[sign*3.85,(d.height-.8)/2,-d.depth/2],`upper guide ${sign}`);
  box([d.wall,1.1,.6],[sign*(d.width-d.wall)/2,d.height/2-.55,0],`front ear ${sign}`);
 }
 const rear=d.tipDepth+d.contactLength;
 box([d.width-2*d.wall,2.7,d.depth-rear],[0,-1.25,-rear-(d.depth-rear)/2],'contact support');
 box([3.4,.65,3],[0,1.2,-d.depth+1.55],'locking tongue');
 for(let i=0;i<4;i++){
  const pinNumber=face==='bottom'?4-i:i+1;
  const pin=box([.42,.42,d.contactLength],[(i-1.5)*2,-.15,-d.tipDepth-d.contactLength/2],`pin ${pinNumber}`,true);
  pin.userData.pin=pinNumber;pin.userData.connectorId=id;
 }
 const isInput=channel==null,names=isInput?['SCL','SDA','5V','GND']:[`IN${channel}`,`OUT${channel}`,'5V','GND'];
 const q=portQuaternion(face).premultiply(rotation);
 const port=host.add(new Port({id,label:isInput?'PbHUB upstream · PORT.A I2C':`PbHUB CH${channel} · PORT.B`,connector:'grove',position,quaternion:q,hitSize:[10,.6,5.2],pins:names.map((name,i)=>({n:i+1,name})),pinGrid:{cols:4,rows:1,pitch:2,center:[0,isInput?-.15:.15],order:col=>col+1},meta:{role:'visual-connector',face,channel:isInput?null:channel,scope:'Physical connection and pin metadata only; no GPIO, PWM, ADC, servo, I2C or power behavior'}}));
 return {group,port};
}

export function addBoard(host){
 const board=unitPcb(host.body,{h:48});board.name='PbHUB black PCB';board.material.color.setHex(0x181c1d);
 const add=(size,position,name,color=0x282b2a,metal=false)=>mesh(host.body,new THREE.BoxGeometry(...size),metal?materials.metal(color,{roughness:.48}):materials.plastic(color,{roughness:.82}),position,`PbHUB ${name}`);
 // The same-version front photo shows a TSSOP20 package, three upper passives,
 // regulator and surrounding capacitors. Hidden pad/tail dimensions are inferred.
 add([4.4,6.5,.95],[0,2,1.375],'STM32F030 package');
 for(const sign of [-1,1])for(let i=0;i<10;i++)add([.8,.27,.2],[sign*2.5,2+(i-4.5)*.65,1.06],`MCU lead ${sign} ${i}`,0xaeb3af,true);
 const passive=(x,y,w,h,name,color=0x928b62)=>{
  add([w,h,.5],[x,y,1.15],name,color);
  for(const sign of [-1,1])add([w,.28,.52],[x,y+sign*(h-.24)/2,1.16],`${name} terminal ${sign}`,0xaeb4b0,true);
 };
 for(const x of [-1.8,0,1.8])passive(x,8.5,1.05,2.35,`upper resistor ${x}`,0x343b36);
 passive(0,14.3,1.15,1.9,'upper capacitor');
 for(const x of [-4.3,4.3])passive(x,11.4,1.25,2.1,`side capacitor ${x}`);
 passive(0,-4.1,2.1,1.15,'lower capacitor 1');
 passive(0,-6.3,2.1,1.15,'lower capacitor 2');
 for(const x of [-3.4,3.4])passive(x,-6.4,1.05,2.1,`lower passive ${x}`);
 add([1.8,2.8,.85],[0,-8.1,1.325],'HT7533 regulator');
 for(let i=0;i<5;i++)add([.65,.9,.08],[(i-2)*1.2,-8.15,.94],`debug pad ${i+1}`,0xbcad76,true);
 return board;
}

export function addGroveSockets(host){
 host.groveSockets=[addSocket(host,{...spec.input})];
 for(const output of spec.outputs)host.groveSockets.push(addSocket(host,{...output,face:'front',color:0x171b1c}));
 return host.groveSockets;
}
