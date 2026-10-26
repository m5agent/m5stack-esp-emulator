import * as THREE from 'three';
import {Component,Port,Led,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,FACE,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';

function extrude(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:40}),material,position,name);}
function bore(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);s.holes.push(h);}
function boards(host){
 // Mount bosses meet the outer PCB contour: their clearances are open scallops,
 // rather than holes that illegally cross the board exterior.
 const s=new THREE.Shape();s.moveTo(-10.8,13.8);s.lineTo(10.8,13.8);s.lineTo(10.8,-19.7);s.lineTo(8,-19.7);s.absarc(8,-24,4.3,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.8,-28.3);s.lineTo(10.8,-31.8);s.lineTo(8.2,-34.0);s.lineTo(5.6,-34.0);s.lineTo(5.6,-28.5);s.lineTo(-5.6,-28.5);s.lineTo(-5.6,-34.0);s.lineTo(-8.2,-34.0);s.lineTo(-10.8,-31.8);s.lineTo(-10.8,-28.3);s.lineTo(-8,-28.3);s.absarc(-8,-24,4.3,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.8,-19.7);s.closePath();bore(s,0,-24,2.1);for(const x of[-3,-1,1,3])bore(s,x,-29.1,.32);
 const green=materials.plastic(0x1e6650,{roughness:.89});
 const base=extrude(host.body,s,.8,[0,0,-7.5],green,'PoESP32 PoE base PCB with boss scallops and open Grove relief');
 const top=roundedRect(21.1,31.8,.6,{cy:-3.6});
 for(let i=0;i<6;i++)bore(top,-9.2,-14.25+i*2.54,.43);
 const logic=extrude(host.body,top,.8,[0,0,.7],green,'PoESP32 ESP32 and IP101G logic PCB with actual six download holes');
 const bridge=[];const black=materials.plastic(0x222620),metal=materials.metal(0xb9b39c,{roughness:.45});
 for(let row=0;row<2;row++)for(let col=0;col<5;col++){
  const x=6.6+row*2.0,y=-15.6+col*2.0;
  bridge.push(mesh(host.body,new THREE.BoxGeometry(.46,.46,6.2),metal,[x,y,-3.1],'PoESP32 P1/P2 interboard pin '+(row*5+col+1)));
 }
 mesh(host.body,new THREE.BoxGeometry(4.2,10.6,1.6),black,[7.6,-11.6,-.1],'PoESP32 P2 5×2 interboard female carrier');
 return{base,logic,bridge};
}
function electronics(host){
 const g=new THREE.Group();g.name='PoESP32 physically populated concealed subassemblies';host.body.add(g);
 const dark=materials.plastic(0x202622,{roughness:.8}),metal=materials.metal(0xbebeb6,{roughness:.48}),gold=materials.metal(0xc8ac66,{roughness:.43}),ceramic=materials.plastic(0xa9956d,{roughness:.86});
 const moduleBoard=mesh(g,new THREE.BoxGeometry(16,15.6,.8),materials.plastic(0x234e45),[0,-10.1,1.9],'PoESP32 U3 ESP32-WROOM-32U visual substrate');
 const shield=mesh(g,new THREE.BoxGeometry(14.8,14.2,2.25),metal,[0,-10.1,3.425],'PoESP32 U3 ESP32-WROOM shield');
 for(const x of[-7.9,7.9])for(let i=0;i<10;i++)mesh(g,new THREE.BoxGeometry(.65,.65,.15),gold,[x,-16.35+i*1.39,2.34],'PoESP32 ESP32 module castellated pad');
 const phy=mesh(g,new THREE.BoxGeometry(6.4,6.4,1),dark,[0,5.7,2],'PoESP32 U2 IP101G PHY package');const leads=[];
 for(let side=0;side<4;side++)for(let i=0;i<8;i++){
  const lead=mesh(g,new THREE.BoxGeometry(.28,.9,.15),metal,[-2.275+i*.65,9.15,1.62],'PoESP32 IP101G lead');lead.position.sub(new THREE.Vector3(0,5.7,0)).applyAxisAngle(new THREE.Vector3(0,0,1),side*Math.PI/2).add(new THREE.Vector3(0,5.7,0));lead.rotation.z=side*Math.PI/2;leads.push(lead);
 }
 const crystal=mesh(g,new THREE.BoxGeometry(3.2,2.5,.8),metal,[-6.8,6.3,1.9],'PoESP32 Y1 25MHz crystal package');
 const regulator=mesh(g,new THREE.BoxGeometry(3.8,6.3,1.4),dark,[-6.5,-.4,2.2],'PoESP32 VR1 AMS1117 SOT-223 body');mesh(g,new THREE.BoxGeometry(3.3,3.5,.25),metal,[-6.5,3.2,1.62],'PoESP32 AMS1117 heat tab');for(const x of[-7.6,-6.5,-5.4])mesh(g,new THREE.BoxGeometry(.65,1.5,.25),metal,[x,-4.1,1.62],'PoESP32 regulator lead');
 // The baseboard power converter occupies the space between the two boards.
 // Envelopes are photo/schematic-derived; no transformer or PoE simulation.
 const powerBoard=mesh(g,new THREE.BoxGeometry(18.0,24.5,.8),materials.plastic(0x214332),[0,-2.4,-6.25],'PoESP32 M2 WC-PD06H050A converter substrate');
 const transformer=mesh(g,new THREE.BoxGeometry(10.2,10.7,4.2),dark,[0,-1.8,-3.75],'PoESP32 M2 ferrite transformer envelope');mesh(g,new THREE.BoxGeometry(8.7,6.8,4.35),materials.plastic(0xbd9c43),[0,-1.8,-3.75],'PoESP32 M2 insulated winding envelope');
 const capacitors=[];for(const[x,y]of[[-6.1,7.2],[6.1,7.2]]){const c=mesh(g,new THREE.CylinderGeometry(2,2,4.7,32).rotateX(Math.PI/2),dark,[x,y,-3.5],'PoESP32 converter electrolytic capacitor');mesh(g,new THREE.CylinderGeometry(1.8,1.8,.2,32).rotateX(Math.PI/2),metal,[x,y,-1.05],'PoESP32 capacitor metal end');capacitors.push(c);}
 for(const[x,y,z]of[[-6,11,1.75],[6,11,1.75],[7,1.5,1.75],[-6,-6.5,1.75],[-7.3,-9,-5.4],[6.5,-8.8,-5.4],[0,-16.5,-5.4],[-2,-17,-5.4]]){
  mesh(g,new THREE.BoxGeometry(1.4,.8,.5),ceramic,[x,y,z],'PoESP32 resistor/capacitor package');for(const dx of[-.55,.55])mesh(g,new THREE.BoxGeometry(.3,.8,.52),metal,[x+dx,y,z],'PoESP32 passive termination');
 }
 return{group:g,moduleBoard,shield,phy,leads,crystal,regulator,powerBoard,transformer,capacitors};
}
function mouthHole(){const p=new THREE.Path();p.moveTo(-6.0,3.2);p.lineTo(6.0,3.2);p.lineTo(6.0,-3.25);p.lineTo(3.25,-3.25);p.lineTo(3.25,-4.35);p.lineTo(2.45,-4.35);p.lineTo(2.45,-5.15);p.lineTo(-2.45,-5.15);p.lineTo(-2.45,-4.35);p.lineTo(-3.25,-4.35);p.lineTo(-3.25,-3.25);p.lineTo(-6,-3.25);p.closePath();return p;}
function jackShape(w,h,r){const s=roundedRect(w,h,r);s.holes.push(mouthHole());for(const x of[-6,6])s.holes.push(roundedRect(3.2,1.7,.08,{cx:x,cy:4.95,path:new THREE.Path()}));return s;}
function wireSegment(parent,a,b,r,material,name){const d=new THREE.Vector3(...b).sub(new THREE.Vector3(...a));const m=mesh(parent,new THREE.CylinderGeometry(r,r,d.length(),10),material,new THREE.Vector3(...a).add(new THREE.Vector3(...b)).multiplyScalar(.5).toArray(),name);m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.normalize());return m;}
class FixedNetworkLed extends Led{
 constructor({fixedColor,...options}){super({...options,color:fixedColor});this.fixedColor=fixedColor;}
 set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:this.fixedColor});}
}
function ethernet(host){
 const g=new THREE.Group();g.name='PoESP32 U1 HBJ-6308ANLF magnetic RJ45';g.position.fromArray(spec.ethernet.position);g.quaternion.copy(FACE.top);host.body.add(g);
 const dark=materials.plastic(0x141a18,{roughness:.73}),steel=materials.metal(0xb6bcb8,{roughness:.37}),gold=materials.metal(0xcab35e,{roughness:.33});
 const carrier=extrude(g,jackShape(15.5,12.65,.2),20.9,[0,0,-21.15],dark,'PoESP32 RJ45 real stepped socket carrier and cavity walls');
 const front=extrude(g,jackShape(15.8,12.9,.15),.25,[0,0,-.25],steel,'PoESP32 RJ45 metal face with actual 8P8C opening and LED windows');
 const stop=mesh(g,new THREE.BoxGeometry(12.6,10.8,.6),dark,[0,-.7,-20.75],'PoESP32 RJ45 recessed insertion stop and magnetic body');
 for(const x of[-7.8,7.8])mesh(g,new THREE.BoxGeometry(.2,12.8,20.8),steel,[x,0,-10.6],'PoESP32 RJ45 metal side wall');for(const y of[-6.35,6.35])mesh(g,new THREE.BoxGeometry(15.5,.2,20.8),steel,[0,y,-10.6],'PoESP32 RJ45 folded shield wall');
 // Separate spring fingers sit above the housing roof; no false second socket.
 const springs=[];for(const x of[-4.7,4.7]){const s=mesh(g,new THREE.BoxGeometry(1.8,.2,6.7),steel,[x,-6.5,-5.5],'PoESP32 RJ45 shield retention spring');s.rotation.x=-.07;springs.push(s);}
 const contacts=[];for(let i=0;i<8;i++){const x=(i-3.5)*1.016,segments=[];segments.push(wireSegment(g,[x,2.65,-2.2],[x,1.65,-8.3],.13,gold,'PoESP32 RJ45 pin '+(i+1)+' spring'));segments.push(wireSegment(g,[x,1.65,-8.3],[x,2.9,-16.9],.13,gold,'PoESP32 RJ45 pin '+(i+1)+' tail'));contacts.push(segments);}
 const leds=[];for(const info of spec.leds){const lens=mesh(g,new THREE.BoxGeometry(2.9,1.45,.7),materials.plastic(info.color,{roughness:.3,transparent:true,opacity:.88}),info.localPosition,'PoESP32 RJ45 '+info.id+' physical lens');lens.removeFromParent();const led=host.add(new FixedNetworkLed({id:info.id,label:info.id==='link-led'?'RJ45 yellow LINK indicator':'RJ45 green ACTIVITY indicator',mesh:lens,fixedColor:info.color,radius:.5,glowSize:3,meta:{role:'externally-driven-indicator',fixedColor:info.id==='link-led'?'yellow':'green',scope:'External on/brightness appearance only; no automatic network/link/activity, PHY, PoE or firmware behavior'}}));g.add(led.object3d);led.glow.position.set(...info.localPosition);leds.push(led);}
 const port=host.add(new Port({id:'ethernet',label:'HBJ-6308ANLF · RJ45 8P8C',connector:'rj45-8p8c',position:spec.ethernet.position,quaternion:portQuaternion('top'),hitSize:[15.8,1,12.9],pins:Array.from({length:8},(_,i)=>({n:i+1,name:'RJ45 '+(i+1)})),meta:{role:'visual-connector',face:'top',scope:'Physical eight-contact jack and mating frame only; no Ethernet, packet, link, PHY, PoE supply or protocol behavior'}}));
 return{group:g,carrier,front,stop,springs,contacts,leds,port};
}
export function buildPoESP32(host){
 const native=addCadParts(host,data,{shell:materials.plastic(0x545b59,{roughness:.81})});
 const pcb=boards(host),circuit=electronics(host),jack=ethernet(host);
 const socket=connector(host.body,72,true,{height:5.2});socket.name='PoESP32 cyan HY2.0-4P physical UART socket';socket.position.z=-6.7;socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.C · UART',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'UART_RX',color:'yellow'},{n:4,name:'UART_TX',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'UART',scope:'Physical Grove connection and cable pose only; no UART/AT commands, Ethernet, PoE, WiFi, BLE, web, electrical or firmware behavior'}}));
 screw(host.body,[0,-24,-9.43],'back',1.4);
 host.add(new Component({id:'sensor',label:'PoESP32 visual assembly anchor',meta:{role:'visual-anchor',scope:'No networking, PoE power, serial, WiFi, BLE, web, protocol, electrical or register commands'}}));
 const stickers=addStickers(host);
 host.poESP32Assembly={native,pcb,circuit,jack,socket,port,stickers};
}
