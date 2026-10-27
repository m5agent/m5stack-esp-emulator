import*as THREE from'three';import{Button,Component,Port,materials}from'../../core/index.js';import{roundedRect}from'../../core/geometry.js';import{addCadParts}from'../../modeling/cad.js';import{mesh,slab,screw,FACE,portQuaternion}from'../../modeling/parts.js';import{spec}from'./dimensions.js';import data from'./geometry-data.js';import{Antenna}from'./Antenna.js';import{addStickers}from'./stickers.js';
const tau=Math.PI*2;const hole=(s,x,y,r)=>{const p=new THREE.Path();p.absarc(x,y,r,0,tau,false);s.holes.push(p);};
const solid=(p,s,d,v,m,n)=>mesh(p,new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:64}),m,v,n);
function annulus(p,outer,inner,depth,pos,mat,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,tau,false);hole(s,0,0,inner);return solid(p,s,depth,pos,mat,name);}
function electronics(host){
 const s=new THREE.Shape();s.moveTo(-10.2,21.5);s.lineTo(10.2,21.5);s.lineTo(10.2,-16.6);s.lineTo(8,-16.6);s.absarc(8,-20,3.4,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.2,-23.4);s.lineTo(10.2,-29);s.lineTo(5.7,-29);s.lineTo(5.7,-24.8);s.lineTo(-5.7,-24.8);s.lineTo(-5.7,-29);s.lineTo(-10.2,-29);s.lineTo(-10.2,-23.4);s.lineTo(-8,-23.4);s.absarc(-8,-20,3.4,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.2,-16.6);s.closePath();hole(s,0,-20,1.8);
 const green=materials.plastic(0x214e36,{roughness:.9}),metal=materials.metal(0xc5b36c,{roughness:.53}),tin=materials.metal(0xb8b9ac,{roughness:.4});
 const pcb=solid(host.body,s,.8,[0,0,-1.8],materials.plastic(0x17281f,{roughness:.91}),'LoRaE220-920 fixed carrier PCB with actual mounting and Grove clearances');pcb.userData={role:'physical-pcb',inferred:true};
 const substrate=slab(host.body,18.4,29,.65,.1,[0,-2.4,-1],green,[],.015);substrate.name='LoRaE220-920 fixed E220-900T22S JP module substrate';
 const shield=slab(host.body,17.1,26.7,1.85,.28,[0,-2.5,-.35],materials.metal(0xc3c5a5,{roughness:.74}),[],.07);shield.name='LoRaE220-920 actual E220-900T22S JP opaque shielding can';shield.userData={role:'physical-rf-module-shield',part:'E220-900T22S(JP)',inferred:true};
 const terminals=[];for(const sign of[-1,1])for(let i=0;i<11;i++){terminals.push(mesh(host.body,new THREE.BoxGeometry(.8,.72,.25),metal,[sign*9.1,-15.1+i*2.54,-.22],'LoRaE220-920 module castellated physical contact'));mesh(host.body,new THREE.BoxGeometry(.36,.62,.16),tin,[sign*9.55,-15.1+i*2.54,-.85],'LoRaE220-920 castellated solder joint');}
 for(const[x,y]of[[-.2,18.3],[6.9,18.3]]){const c=slab(host.body,2.9,1.55,1.2,.1,[x,y,-1],materials.plastic(0x8f8b70,{roughness:.88}),[],.015);c.name='LoRaE220-920 schematic C1 C2 physical capacitor';for(const dx of[-1.2,1.2])mesh(host.body,new THREE.BoxGeometry(.45,1.55,.15),tin,[x+dx,y,-.94],'LoRaE220-920 capacitor solder termination');}
 return{pcb,substrate,shield,terminals};
}
function modeSwitch(host){
 const plastic=materials.plastic(0x171d18,{roughness:.8}),ivory=materials.plastic(0xe1e4cf,{roughness:.8}),metal=materials.metal(0xb3b7a6,{roughness:.43});
 const base=slab(host.body,5.2,6.2,2.4,.08,[-4.5,15,-.1],plastic,[],.015);base.name='LoRaE220-920 S1 fixed SW DIP-2 molded base';
 const top=roundedRect(5.2,6.2,.08);for(const x of[-1.25,1.25])top.holes.push(roundedRect(1.2,3.1,.08,{cx:x,cy:0,path:new THREE.Path(),clockwise:true}));
 const deck=solid(host.body,top,1.25,[-4.5,15,2.3],plastic,'LoRaE220-920 S1 fixed deck with two genuine slider slots');
 const switches=[];for(const[i,x]of spec.dip.pinX.entries()){
  for(const sign of[-1,1])mesh(host.body,new THREE.BoxGeometry(.55,1.0,.3),metal,[x,15+sign*3.4,-.6],'LoRaE220-920 S1 fixed electrical terminal shape');
  const cap=new THREE.Group();cap.name=`LoRaE220-920 S1 real retained mode-${i} slider`;
  mesh(cap,new THREE.BoxGeometry(1.02,1.35,1.2),ivory,[0,0,-.35],`LoRaE220-920 S1 mode-${i} moving white thumb`);
  for(const y of[-.38,0,.38])mesh(cap,new THREE.BoxGeometry(.99,.09,.12),materials.plastic(0xc4c9b8,{roughness:.84}),[0,y,.31],`LoRaE220-920 S1 mode-${i} moving grip rib`);
  switches.push(host.add(new Button({id:`mode-${i}`,label:`S1 M${i} physical DIP slider`,mesh:cap,position:[x,spec.dip.offY,3.5],axis:spec.dip.axis,travel:spec.dip.travelMm,latching:true,meta:{role:'visual-control',mechanism:'retained-DIP-slider',positions:['lower','upper / ON print'],detentsMm:[0,1.2],travelSource:'Photo/native-aperture visual reconstruction, not measured switch travel',scope:'Stable physical detent, pointer/keyboard input intent and external position only; no M0/M1 logic, mode decoding, transmit/receive, RF, UART or electrical behavior'}})));
 }
 return{base,deck,switches};
}
function sma(host){
 const g=new THREE.Group();g.name='LoRaE220-920 true SMA female connector';g.position.fromArray(spec.sma.position);g.quaternion.copy(FACE.top);host.body.add(g);const gold=materials.metal(0xd1b85c,{roughness:.36}),white=materials.plastic(0xdcd9ba,{roughness:.75}),dark=materials.plastic(0x252b22,{roughness:.8});
 const barrel=annulus(g,2.78,2.1,10.3,[0,0,-10.3],gold,'LoRaE220-920 SMA continuous annular female outer barrel');
 const lip=annulus(g,2.78,2.1,.45,[0,0,-.45],gold,'LoRaE220-920 SMA open annular mating lip');
 class ThreadCurve extends THREE.Curve{getPoint(t,target=new THREE.Vector3()){const a=t*tau*9;return target.set(Math.cos(a)*2.94,Math.sin(a)*2.94,-7.2+t*6.3);}}
 const thread=mesh(g,new THREE.TubeGeometry(new ThreadCurve(),648,.16,8,false),gold,[0,0,0],'LoRaE220-920 SMA real continuous helical external thread');
 const hex=new THREE.Shape();for(let i=0;i<6;i++){const a=tau*i/6+Math.PI/6;const x=Math.cos(a)*3.13,y=Math.sin(a)*3.13;i?hex.lineTo(x,y):hex.moveTo(x,y);}hex.closePath();hole(hex,0,0,1.05);const nut=solid(g,hex,4,[0,0,-13.4],gold,'LoRaE220-920 SMA retained internal hex body visible through both native windows');
 const dielectric=annulus(g,2.095,.6,4.35,[0,0,-4.55],white,'LoRaE220-920 SMA recessed PTFE insulator with genuine centre bore');
 const contact=annulus(g,.58,.25,4,[0,0,-4.4],gold,'LoRaE220-920 SMA female hollow recessed centre contact sleeve');
 const stop=mesh(g,new THREE.CylinderGeometry(.25,.25,.12,32).rotateX(Math.PI/2),gold,[0,0,-4.56],'LoRaE220-920 SMA recessed centre contact blind end');
 const shoulder=annulus(g,1.04,.55,1.2,[0,0,-14.4],white,'LoRaE220-920 SMA rear feed-through dielectric');const rearPin=mesh(g,new THREE.CylinderGeometry(.24,.24,1.6,24).rotateX(Math.PI/2),gold,[0,0,-14.4],'LoRaE220-920 SMA rear centre terminal');
 const rear=annulus(g,1.45,.62,1.2,[0,0,-15],gold,'LoRaE220-920 SMA rear coax termination sleeve');
 const cablePath=new THREE.CatmullRomCurve3([new THREE.Vector3(0,24.3,0),new THREE.Vector3(0,22.2,.1),new THREE.Vector3(5.5,20,.4),new THREE.Vector3(8,15.8,.3),new THREE.Vector3(7.5,10.5,.05)]);const coax=mesh(host.body,new THREE.TubeGeometry(cablePath,48,.5,10,false),materials.plastic(0x171e1a,{roughness:.86}),[0,0,0],'LoRaE220-920 concealed actual SMA to IPEX coax');
 const ipg=new THREE.Group();ipg.name='LoRaE220-920 fixed IPEX board antenna receptacle';ipg.position.set(7.5,10.5,-.25);host.body.add(ipg);const socket=annulus(ipg,1.1,.55,.6,[0,0,0],gold,'LoRaE220-920 actual annular IPEX socket');mesh(ipg,new THREE.CylinderGeometry(.23,.23,.5,20).rotateX(Math.PI/2),gold,[0,0,.25],'LoRaE220-920 IPEX central terminal');
 const port=host.add(new Port({id:'sma',label:'SMA female · antenna connector',connector:'sma-female',position:spec.sma.position,quaternion:portQuaternion('top'),hitSize:[6.2,1,6.2],pins:[{n:1,name:'centre ANT'},{n:2,name:'outer shield'}],meta:{role:'visual-connector',face:'top',signalRole:'antenna',scope:'Female connector shape, external thread, real recessed centre socket, pose and matching connector type only; no RF field, frequency, signal, receive/transmit, power or electrical simulation'}}));return{group:g,barrel,lip,thread,nut,dielectric,contact,stop,shoulder,rearPin,rear,coax,ipex:ipg,socket,port};
}
function grove(host){const g=new THREE.Group();g.name='LoRaE220-920 open red HY2.0-4P socket';g.position.fromArray(spec.grove.position);g.quaternion.copy(FACE.bottom);host.body.add(g);const plastic=materials.plastic(spec.grove.color,{roughness:.66}),metal=materials.metal(0xc0b797,{roughness:.42}),box=(s,p,n,m=plastic)=>mesh(g,new THREE.BoxGeometry(...s),m,p,'LoRaE220-920 Grove '+n),depth=6.6;
 for(const sign of[-1,1]){box([.65,5.2,depth],[sign*4.675,0,-depth/2],'side wall');box([.7,.6,3.2],[sign*3.85,2.3,-4.9],'guide rail');box([.6,.45,1.2],[sign*3.65,2.375,-1.8],'latch shoulder');}box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');box([8.7,4.55,.65],[0,.325,-depth+.325],'rear wall');box([4.8,.45,2.3],[0,2.375,-4.6],'locking bridge');const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4.7],[(i-1.5)*2,.2,-3.7],`contact ${i+1}`,metal));box([.42,1.4,.42],[(i-1.5)*2,-2.7,-6],`solder tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.C · UART',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'RXD',color:'yellow'},{n:4,name:'TXD',color:'white'}],meta:{role:'visual-connector',face:'bottom',scope:'Physical attachment, four contacts, pin labels and cable pose only; no UART transaction, RF, packet, signal, supply or electrical behavior'}}));return{group:g,contacts,port};}
export function buildLoRaE220920(host,{antenna=host.options.antenna??false,antennaAngleDeg=host.options.antennaAngleDeg??0}={}){
 if(typeof antenna!=='boolean')throw new TypeError('antenna must be true or false');
 const parts=addCadParts(host,data,{shell:materials.plastic(0x555956,{roughness:.85})}),board=electronics(host),output=sma(host),input=grove(host),dip=modeSwitch(host);const fixings=[];
 for(const[x,y]of[[0,-20],[-8.2,27.4],[8.2,27.4]]){fixings.push(screw(host.body,[x,y,-3.97],'back',1.35));mesh(host.body,new THREE.CylinderGeometry(.6,.6,1.8,24).rotateX(Math.PI/2),materials.metal(0xa1a797),[x,y,-2.7],'LoRaE220-920 concealed fixed shell retaining shank');}
 const anchor=host.add(new Component({id:'sensor',label:'E220-900T22S JP passive appearance anchor',position:[0,-2.4,1.5],meta:{role:'visual-anchor',scope:'Passive fixed visual anchor only; no RF field, scan, carrier, RSSI, packets, WOR, frequency, UART, mode decoding, sensor values, firmware or electrical commands'}}));
 host.loraE220Assembly={parts,board,output,input,dip,fixings,anchor};host.unitStickers=addStickers(host);
 if(antenna)output.port.attach(new Antenna({angleDeg:antennaAngleDeg}));
}
