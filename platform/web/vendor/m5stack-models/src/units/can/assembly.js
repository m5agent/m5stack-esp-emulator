import * as THREE from 'three';
import {Component,Led,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';

class FixedWhiteLed extends Led{
 set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:0xffffff});}
}
function board(host){
 const s=new THREE.Shape(),x=10.5,y=-16,r=3.5,dx=x-8,dy=Math.sqrt(r*r-dx*dx),a=Math.acos(dx/r);
 // Mounting bosses are relieved with open boundary scallops rather than invalid holes.
 s.moveTo(-5.45,-26.4);s.lineTo(-7,-26.4);s.lineTo(-x,-23.1);s.lineTo(-x,y-dy);s.absarc(-8,y,r,Math.PI+a,Math.PI-a,false);s.lineTo(-x,24.6);s.lineTo(-8,26.4);s.lineTo(8,26.4);s.lineTo(x,24.6);s.lineTo(x,y+dy);s.absarc(8,y,r,a,Math.PI*2-a,false);s.lineTo(x,-23.1);s.lineTo(7,-26.4);s.lineTo(5.45,-26.4);s.lineTo(5.45,-20.5);s.lineTo(-5.45,-20.5);s.closePath();
 const bore=new THREE.Path();bore.absarc(0,y,2.1,0,Math.PI*2,false);s.holes.push(bore);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:40}),materials.plastic(0x285a3c,{roughness:.88}),[0,0,-1.5],'CAN physical PCB with boss reliefs, screw bore and Grove notch');pcb.userData={role:'physical-pcb',scope:'Reconstructed board envelope; no copper, circuit or electrical simulation'};
 const dark=materials.plastic(0x222827,{roughness:.8}),metal=materials.metal(0xb3b7a7,{roughness:.48});
 slab(host.body,5.8,7.6,2.25,.2,[-2,2,-.7],dark,[],.035).name='CAN CA-IS3050G isolated transceiver package';
 for(const x of[-5.15,1.15])for(let i=0;i<4;i++)mesh(host.body,new THREE.BoxGeometry(.7,.5,.35),metal,[x,2+(i-1.5)*1.7,-.4],'CAN transceiver gull-wing lead');
 slab(host.body,7.2,9.5,3.4,.25,[4.5,9,-.7],dark,[],.045).name='CAN B0505ST16-W5 isolated DC-DC package';
 slab(host.body,2.4,2.9,1,.15,[-5.5,-8,-.7],dark,[],.025).name='CAN MST5333 regulator package';
 for(const [px,py,w,h]of[[-5,12,2.7,3],[-1,12,2.7,3],[5,-5,2.7,3],[-5,-3,2,1],[6,-10,2,1]])slab(host.body,w,h,.7,.1,[px,py,-.7],dark,[],.02).name='CAN protection or decoupling package';
 return pcb;
}
function grove(host){
 const group=new THREE.Group();group.name='CAN open-top HY2.0-4P';group.position.fromArray(spec.grove.position);group.quaternion.copy(FACE.bottom);host.body.add(group);
 const plastic=materials.plastic(spec.grove.color,{roughness:.65}),metal=materials.metal(0xb6aa82,{roughness:.42}),box=(size,p,name,mat=plastic)=>mesh(group,new THREE.BoxGeometry(...size),mat,p,'CAN Grove '+name);
 for(const sign of[-1,1]){box([.65,5.2,6.5],[sign*4.675,0,-3.25],'side wall');box([.7,.6,3],[sign*3.85,2.3,-4.9],'guide rail');box([.65,.6,1.1],[sign*3.7,2.3,-1.2],'latch shoulder');}
 box([8.7,.65,6.5],[0,-2.275,-3.25],'floor');box([8.7,4.55,.65],[0,.325,-6.175],'rear wall');box([4.8,.45,2.1],[0,2.375,-4.65],'locking bridge');
 for(let i=0;i<4;i++){box([.42,.42,4.6],[(i-1.5)*2,.2,-3.6],`contact ${i+1}`,metal);box([.42,1.2,.42],[(i-1.5)*2,-1.6,-5.7],`PCB tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.C · CAN TX/RX',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'CAN_TX',color:'yellow'},{n:4,name:'CAN_RX',color:'white'}],pinGrid:{cols:4,rows:1,pitch:2,center:[0,.2],order:col=>col+1},meta:{role:'visual-connector',face:'bottom',protocol:'CAN TX/RX',scope:'Physical attachment/cable pose only; no CAN controller, transceiver, bus, supply or firmware behavior'}}));return{group,port};
}
function terminal(host){
 const frame=new THREE.Group();frame.name='CAN fixed four-pole HT3.96 socket';frame.position.fromArray(spec.terminal.position);host.body.add(frame);
 const orange=materials.plastic(0xf38e2e,{roughness:.67}),metal=materials.metal(0xb5b6a1,{roughness:.42}),box=(size,p,name,mat=orange)=>mesh(frame,new THREE.BoxGeometry(...size),mat,p,'CAN fixed terminal '+name);
 const rear=box([16,.7,7],[0,-9.65,0],'rear support');
 for(const side of[-1,1])box([.65,9.3,7],[side*7.675,-4.65,0],'side cheek');
 box([14.7,9.3,.55],[0,-4.65,-3.225],'lower retention wall');
 box([14.7,6.95,.55],[0,-3.475,3.225],'upper forward retention wall');
 box([14.7,.85,.55],[0,-8.875,3.225],'upper rear retention wall');
 for(const x of spec.terminal.pinX){box([.62,7.2,.62],[x,-4.6,-.4],'contact pin',metal);box([.62,.62,3],[x,-9.65,-1.9],'PCB tail',metal);}
 // The visible moulded lip/latch apertures on the upper cover are solids around real slots.
 for(const x of[-7.5,-3.96,0,3.96,7.5])box([.65,1.5,.55],[x,-7.7,3.225],'upper latch partition');
 box([16,.5,.55],[0,-8.45,3.225],'upper latch rear rib');
 const port=host.add(new Port({id:'terminal',label:'CAN · HT/VH3.96-4P',connector:'ht3.96-4p',position:spec.terminal.position,hitSize:[16,1,7],pins:spec.terminal.names.map((name,i)=>({n:i+1,name})),pinGrid:{cols:4,rows:1,pitch:3.96,center:[0,-.4],order:col=>col+1},meta:{role:'visual-connector',face:'top',scope:'Physical connector and attachment frame only; no bus continuity, termination, isolation, electrical or firmware state',terminalOrderEvidence:'Exact U085 front photograph reads H/L/NC/G; schematic JP1 maps pin4 H, pin3 L, pin2 NC, pin1 SHIELD. Port n indexes visual left-to-right positions, not JP1 schematic numbering.'}}));return{frame,rear,port};
}
function indicator(host){
 const lens=slab(new THREE.Group(),.55,2.7,4.3,.23,[0,0,0],materials.plastic(0xd0d5c8,{roughness:.52}),[],.02);lens.name='CAN physical white LED/light-guide behind native indicator slot';
 const led=host.add(new FixedWhiteLed({id:'power-led',label:'White power indicator',mesh:lens,position:spec.led.position,color:0xffffff,radius:.2,glowSize:2,meta:{role:'externally-driven-visual',colorMode:'fixed-white',evidence:'Official schematic LED1 White; slot position from native shell. Light-guide depth is inferred.',scope:'Defaults off; explicit external on/brightness only. No automatic response to power, CAN traffic, cable or terminal attachment'}}));led.glow.position.z=4.35;return led;
}
export function buildCAN(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe5e7df,{roughness:.78})}),pcb=board(host),input=grove(host),terminalAssembly=terminal(host),powerLed=indicator(host);
 screw(host.body,[0,-16,-4.025],'back',1.25);
 host.add(new Component({id:'sensor',label:'CAN visual anchor',meta:{role:'visual-anchor',scope:'No CAN transceiver/controller, termination resistor, frames, registers, voltage, isolation, firmware or sensor behavior'}}));
 addStickers(host);
 host.canAssembly={parts,pcb,input,terminal:terminalAssembly,powerLed};
}
