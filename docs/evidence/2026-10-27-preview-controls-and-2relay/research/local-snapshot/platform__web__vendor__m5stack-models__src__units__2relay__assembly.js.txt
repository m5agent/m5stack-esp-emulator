import * as THREE from 'three';
import {Component,Led,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
import data from './geometry-data.js';

class FixedBlueLed extends Led{
 set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:0x247cff});}
}
function hole(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(h);}
function board(host){
 const s=new THREE.Shape(),x=10.5,y=-16,r=3.55,dx=x-8,dy=Math.sqrt(r*r-dx*dx),theta=Math.acos(dx/r);
 // The two mounting-boss reliefs are open edge scallops, never invalid closed holes.
 s.moveTo(-5.5,-26.4);s.lineTo(-6.8,-26.4);s.lineTo(-x,-23.2);s.lineTo(-x,y-dy);s.absarc(-8,y,r,Math.PI+theta,Math.PI-theta,false);s.lineTo(-x,26.3);s.lineTo(x,26.3);s.lineTo(x,y+dy);s.absarc(8,y,r,theta,Math.PI*2-theta,false);s.lineTo(x,-23.2);s.lineTo(6.8,-26.4);s.lineTo(5.5,-26.4);s.lineTo(5.5,-20.3);s.lineTo(-5.5,-20.3);s.closePath();hole(s,0,-16,2.1);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:40}),materials.plastic(0x23613b,{roughness:.85}),[0,0,1],'2Relay physical PCB with two open LEGO boss reliefs, screw bore and Grove cutout');
 pcb.userData={role:'physical-pcb',scope:'Photo-derived board appearance; no copper routing or electronics behavior'};return pcb;
}
function grove(host){
 const group=new THREE.Group();group.name='2Relay black open-top HY2.0-4P';group.position.fromArray(spec.grove.position);group.quaternion.copy(FACE.bottom);host.body.add(group);
 const black=materials.plastic(0x1e2422,{roughness:.65}),metal=materials.metal(0xb9ad86,{roughness:.4}),box=(size,p,name,mat=black)=>mesh(group,new THREE.BoxGeometry(...size),mat,p,'2Relay Grove '+name);
 for(const sign of[-1,1]){box([.65,5.2,6.5],[sign*4.675,0,-3.25],'side wall');box([.7,.6,3.0],[sign*3.85,2.3,-4.9],'guide rail');box([.65,.6,1.1],[sign*3.7,2.3,-1.2],'latch shoulder');}
 box([8.7,.65,6.5],[0,-2.275,-3.25],'floor');box([8.7,4.55,.65],[0,.325,-6.175],'rear wall');box([4.8,.45,2.1],[0,2.375,-4.65],'locking bridge');
 for(let i=0;i<4;i++){box([.42,.42,4.6],[(i-1.5)*2,.2,-3.6],`contact ${i+1}`,metal);box([.42,1.2,.42],[(i-1.5)*2,-2.65,-5.7],`PCB tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT · GPIO 1 / 2',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'RELAY-2',color:'yellow'},{n:4,name:'RELAY-1',color:'white'}],pinGrid:{cols:4,rows:1,pitch:2,center:[0,.2],order:col=>col+1},meta:{role:'visual-connector',face:'bottom',protocol:'GPIO',scope:'Physical connector only; no switching, load, voltage or firmware model'}}));return{group,port};
}
function terminal(host,item){
 const frame=new THREE.Group();frame.name=`2Relay channel ${item.number} fixed four-pole terminal socket`;frame.position.fromArray(item.terminal);frame.quaternion.copy(portQuaternion('front'));host.body.add(frame);
 const orange=materials.plastic(0xf39331,{roughness:.67}),metal=materials.metal(0xb5b6a1,{roughness:.42}),box=(size,p,name,mat=orange)=>mesh(frame,new THREE.BoxGeometry(...size),mat,p,`2Relay ${item.number} fixed terminal ${name}`);
 const floor=box([16.0,.7,7.0],[0,-7.15,0],'rear floor');
 for(const side of[-1,1])box([.65,6.8,7.0],[side*7.675,-3.4,0],'side cheek');
 // Complete shroud side walls and short retention lips, with real empty insertion cavity.
 for(const side of[-1,1])box([14.7,6.8,.55],[0,-3.4,side*3.225],side>0?'retention wall':'low outer wall');
 for(const x of[-3.96,0,3.96])box([.35,2.4,.35],[x,-5.6,-3.0],'short rear channel divider');
 for(const x of spec.terminal.pinX){box([.62,5.1,.62],[x,-3.7,-.4],'contact pin',metal);box([.62,.62,2.9],[x,-7.15,-1.5],'PCB tail',metal);}
 const port=host.add(new Port({id:`terminal-${item.number}`,label:`Relay ${item.number} · HT/VH3.96-4P`,connector:'ht3.96-4p',position:item.terminal,quaternion:portQuaternion('front'),hitSize:[16.0,1,7.0],pins:spec.terminal.names.map((name,i)=>({n:i+1,name})),pinGrid:{cols:4,rows:1,pitch:3.96,center:[0,-.4],order:col=>col+1},meta:{role:'visual-connector',face:'front',channel:item.number,terminalOrderEvidence:'Official schematic P1/P2 C/A/B/C; order is visible shell-front left-to-right',scope:'Physical detachable connector only; no contact continuity, NO/NC or voltage/load behavior'}}));return{frame,floor,port};
}
function relay(host,item){
 const dark=materials.plastic(0x1e2222,{roughness:.76});
 const body=slab(host.body,18.1,10.3,13.2,.15,item.relay,dark,[],.055);body.name=`2Relay channel ${item.number} sealed relay package`;
 body.userData={role:'sealed-relay-package',scope:'Fixed opaque exterior; internal armature and switching behavior are intentionally external to this visual library'};
 const seam=slab(host.body,18.0,10.2,.18,.12,[item.relay[0],item.relay[1],1.8],materials.plastic(0x131a18,{roughness:.88}),[],.025);seam.name=`2Relay channel ${item.number} lower molded relay seam`;
 for(const sign of[-1,1])for(const dx of[-5.5,0,5.5])mesh(host.body,new THREE.BoxGeometry(.45,.45,.6),materials.metal(0xaeb39a,{roughness:.45}),[item.relay[0]+dx,item.relay[1]+sign*3.2,1.55],`2Relay channel ${item.number} relay PCB lead`);
 return body;
}
function indicator(host,item){
 const[x,y,z]=item.led,green=materials.plastic(0x1d5131,{roughness:.88}),steel=materials.metal(0xc1c3ad,{roughness:.4});
 slab(host.body,2.7,3.0,.3,.05,[x,y,1.8],green,[],.015).name=`2Relay channel ${item.number} indicator PCB seat`;
 for(const sign of[-1,1])mesh(host.body,new THREE.BoxGeometry(1.0,.45,.4),steel,[x,y+sign*.8,z+.15],`2Relay channel ${item.number} blue LED pad`);
 const lens=slab(new THREE.Group(),1.15,1.7,.45,.1,[0,0,0],materials.plastic(0xd9decb,{roughness:.35}),[],.035);lens.name=`2Relay channel ${item.number} recessed blue 0603 LED package`;
 const led=host.add(new FixedBlueLed({id:`led-${item.number}`,label:`Relay ${item.number} blue indicator`,mesh:lens,position:[x,y,z],radius:.4,glowSize:2.5,color:0x247cff,meta:{role:'externally-driven-visual',colorMode:'fixed-blue',channel:item.number,scope:'Defaults off; explicit external on/brightness only. No automatic response to ports, plug presence, GPIO, supply, sealed relay or other channel'}}));return led;
}
export function build2Relay(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe6e8e0,{roughness:.77})}),pcb=board(host),relays=spec.channels.map(item=>relay(host,item)),terminals=spec.channels.map(item=>terminal(host,item)),leds=spec.channels.map(item=>indicator(host,item)),input=grove(host);
 const dark=materials.plastic(0x1c2722,{roughness:.8});for(const x of[-7,7]){slab(host.body,2.6,1.6,.9,.12,[x,-23,1.8],dark,[],.025).name='2Relay discrete GPIO driver package';for(const y of[-21.8,-24.3])slab(host.body,1.4,.65,.4,.05,[x,y,1.8],dark,[],.015).name='2Relay discrete driver passive';}
 screw(host.body,[0,-16,-4.025],'back',1.25);
 host.add(new Component({id:'sensor',label:'2Relay visual anchor',meta:{role:'visual-anchor',scope:'No relay state, contact truth table, GPIO, ratings, power or firmware behavior'}}));
 addStickers(host,{relays});
 host.twoRelayAssembly={parts,pcb,relays,terminals,leds,input};
}
