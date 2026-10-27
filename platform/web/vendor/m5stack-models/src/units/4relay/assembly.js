import * as THREE from 'three';
import {Led,Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {FACE,mesh,slab,portQuaternion} from '../../modeling/parts.js';
import {spec,CHANNELS} from './dimensions.js';

class GreenIndicator extends Led{
 set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:0x38d653});}
}

export function addBoard(host){
 const x=11.4,y=55.2,r=3.7,n=5.3,s=new THREE.Shape();
 s.moveTo(-x+r,-y);s.lineTo(-n,-y);s.lineTo(-n,-48.7);s.lineTo(n,-48.7);s.lineTo(n,-y);s.lineTo(x-r,-y);
 s.absarc(x-r,-y+r,r,-Math.PI/2,0);s.lineTo(x,y-r);s.absarc(x-r,y-r,r,0,Math.PI/2);s.lineTo(-x+r,y);s.absarc(-x+r,y-r,r,Math.PI/2,Math.PI);s.lineTo(-x,-y+r);s.absarc(-x+r,-y+r,r,Math.PI,Math.PI*1.5);s.closePath();
 for(const[cx,cy]of spec.mountingHolesMm)s.holes.push(roundedRect(6.2,6.2,3.1,{cx,cy,path:new THREE.Path(),clockwise:true}));
 for(const cy of[-44,52])s.holes.push(roundedRect(3.8,3.8,1.9,{cx:0,cy,path:new THREE.Path(),clockwise:true}));
 const board=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:24}),materials.plastic(0x244c37,{roughness:.9}),[0,0,.1],'4Relay PCB with four mounting and two screw bores');
 const chip=materials.plastic(0x202424,{roughness:.8}),tin=materials.metal(0xbcc3bc,{roughness:.5});
 slab(host.body,5.5,6.4,.9,.15,[3.8,-36.9,.9],chip,[],.025).name='4Relay STM32F030 controller';
 for(const sign of[-1,1])for(let i=0;i<10;i++)mesh(host.body,new THREE.BoxGeometry(.7,.26,.16),tin,[3.8+sign*3.05,-36.9+(i-4.5)*.5,1.03],'4Relay controller lead');
 for(const cy of[-33.7,-36.2,-39])for(const cx of[-5.2,-2.4])slab(host.body,1.5,1,.5,.1,[cx,cy,.9],chip,[],.02).name='4Relay hidden passive';
 host.fourRelayAssembly={board,relays:[],indicators:[],terminals:[]};return board;
}

export function addGrove(host){
 const p=spec.grove,group=new THREE.Group();group.name='4Relay open-top HY2.0-4P';group.position.fromArray(p.position);group.quaternion.copy(FACE.bottom);host.body.add(group);
 const plastic=materials.plastic(p.color,{roughness:.62}),metal=materials.metal(0xbaaf89,{roughness:.43}),box=(size,pos,name,mat=plastic)=>mesh(group,new THREE.BoxGeometry(...size),mat,pos,'4Relay Grove '+name);
 for(const x of[-4.65,4.65])box([.7,5.2,6.5],[x,0,-3.25],'side wall');
 for(const x of[-3.85,3.85])box([.9,.8,6.5],[x,2.2,-3.25],'upper guide');
 box([8.6,.7,6.5],[0,-2.25,-3.25],'floor');box([8.6,5.2,.6],[0,0,-6.2],'rear wall');box([8.6,2.7,4.65],[0,-1.25,-4.175],'contact support');box([3.4,.65,3],[0,1.2,-4.95],'locking tongue');
 for(const x of[-4.65,4.65])box([.7,1.1,.6],[x,2.05,0],'mouth ear');
 for(let i=0;i<4;i++){const pin=box([.42,.42,1.2],[(i-1.5)*2,-.15,-1.25],'contact '+(i+1),metal);pin.userData.pin=4-i;}
 host.add(new Port({id:'grove',label:'HY2.0-4P · PORT.A I2C',connector:'grove',position:p.position,quaternion:portQuaternion('bottom'),hitSize:[10,.6,5.2],pins:['GND','5V','SDA','SCL'].map((name,i)=>({n:i+1,name})),pinGrid:{cols:4,rows:1,pitch:2,center:[0,-.15],order:col=>col+1},meta:{role:'visual-connector',face:'bottom',scope:'Physical connection only; no power, relay, I2C or protocol behavior'}}));
 host.fourRelayAssembly.grove=group;
}

export function addChannels(host){
 const black=materials.plastic(0x242829,{roughness:.72}),orange=materials.plastic(0xf38c37,{roughness:.65}),metal=materials.metal(0xb5b8a9,{roughness:.4});
 for(const c of CHANNELS){
  const relay=slab(host.body,18.55,10.15,13.5,.45,[.95,c.relayY,.9],black,[],.15);relay.name=`4Relay sealed relay ${c.number}`;host.fourRelayAssembly.relays.push(relay);
  const lens=new THREE.Mesh(new THREE.BoxGeometry(1.65,2.9,1.35),materials.glossy(0x658d48,{roughness:.25}));
  const led=host.add(new GreenIndicator({id:`led-${c.number}`,label:`Relay ${c.number} green indicator`,position:[-9.5,c.ledY,3.35],mesh:lens,color:0x38d653,radius:.3,glowSize:2.8,meta:{role:'externally-driven-visual',colorMode:'fixed-green',scope:'Independent external on/brightness only; default off. No automatic relay, screw, supply, register or electrical response.'}}));host.fourRelayAssembly.indicators.push(led);
  const group=new THREE.Group();group.name=`4Relay fixed front-facing HT3.96 socket ${c.number}`;group.position.set(spec.terminal.positionX,c.terminalY,0);host.body.add(group);
  const box=(size,pos,name,mat=orange)=>mesh(group,new THREE.BoxGeometry(...size),mat,pos,`4Relay terminal ${c.number} ${name}`);
  box([16.3,7.7,.7],[0,0,1.25],'floor');
  for(const x of[-7.8,7.8])box([.7,7.7,6.25],[x,0,4.725],'side wall');
  box([14.9,.7,6.25],[0,3.5,4.725],'rear wall');
  box([14.9,.7,5.1],[0,-3.5,4.15],'front lip');
  for(const x of spec.terminal.pinX){box([.66,.66,6.5],[x,0,4.8],'vertical contact pin',metal);box([.66,.66,1.1],[x,0,.35],'PCB solder tail',metal);}
  for(const x of[-3.96,0,3.96])box([.35,5.8,.8],[x,0,2],'lower channel rib');
  const port=host.add(new Port({id:`terminal-${c.number}`,label:`Relay ${c.number} removable 4P terminal`,connector:spec.terminal.connector,position:[spec.terminal.positionX,c.terminalY,spec.terminal.matingZ],quaternion:portQuaternion('front'),hitSize:[16.3,.5,7.7],pins:[1,2,3,4].map(n=>({n,name:`Contact ${n}`})),pinGrid:{cols:4,rows:1,pitch:3.96,center:[0,0],order:col=>col+1},meta:{role:'visual-connector',face:'front',channel:c.number,pinoutConfirmed:false,scope:'Physical attachment only. Signal/COM/NO/NC order unconfirmed; no switching, isolation, mains wiring or electrical simulation.'}}));
  host.fourRelayAssembly.terminals.push({group,port});
 }
}
