import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {mesh,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import {shapeRect,hole,circleHole,extrude,polygon,mainFront,lowerFront,ring,endCorner,headerCarrier} from './geometry.js';
import {addStickers} from './stickers.js';

function buildCase(host){
 const white=materials.plastic(0xe8eae6,{roughness:.78}),parts=[],add=(geo,pos,name)=>{const m=mesh(host.body,geo,white,pos,'8Servos2-Chain '+name);m.userData={role:'physical-case',installationInferred:true};parts.push(m);return m;};
 const front=add(extrude(mainFront(),1.11),[0,0,4.6],'own stepped main front plate with true 8x30.25 window');
 const lower=add(extrude(lowerFront(),1.2),[0,0,1.65],'own lowered mounting face with two true bores');
 const baseShape=()=>{const s=shapeRect(24,56,3);for(const x of[-8,8])circleHole(s,x,-16,2.425);for(const x of[-10.3,10.3])hole(s,1.25,4.2,.25,x,-23.4);return s;};
 const rear=add(extrude(baseShape(),1.02),[0,0,-5.63],'rear cover structural floor with real mounting and snap apertures');
 const skin=baseShape(),M=[[-4.7,-26],[-4.7,-20.6],[-3.9,-20.6],[-2.6,-22.25],[-1.3,-20.6],[-.5,-20.6],[-.5,-26],[-1.35,-26],[-1.35,-22],[-2.6,-23.55],[-3.85,-22],[-3.85,-26]],five=[[.6,-20.6],[4.8,-20.6],[4.8,-21.4],[1.45,-21.4],[1.45,-22.8],[3.8,-22.8],[4.8,-23.65],[4.8,-25.2],[3.95,-26],[.6,-26],[.6,-25.2],[3.65,-25.2],[3.95,-24.9],[3.95,-24],[3.55,-23.6],[.6,-23.6]];
 for(const points of[M,five.map(([x,y])=>[x,y+.075])]){const p=new THREE.Path();points.slice().reverse().forEach(([x,y],i)=>i?p.lineTo(x,y):p.moveTo(x,y));p.closePath();skin.holes.push(p);}
 const rearSkin=add(extrude(skin,.08),[0,0,-5.71],'rear outer skin with shallow molded M5 recesses');
 const walls=[];
 for(const side of[-1,1]){
  const s=polygon([[-24.9,-4.61],[24.9,-4.61],[24.9,4.6],[-12,4.6],[-12,2.85],[-24.9,2.85]]);
  if(side===1)hole(s,9.4,7.2,.16,-7.19,-.45);
  hole(s,3,2.8,.12,0,-3.15);
  const direct=extrude(s,1.1),mat=new THREE.Matrix4().makeBasis(new THREE.Vector3(0,1,0),new THREE.Vector3(0,0,1),new THREE.Vector3(1,0,0));direct.applyMatrix4(mat);
  walls.push(add(direct,[side===1?10.9:-12,0,0],side===1?'right side wall with actual square jack-face opening':'left stepped side wall'));
  const tongue=add(new THREE.BoxGeometry(.84,2.8,2.56),[side*11.45,0,-3.15],'fixed recessed retaining tongue');tongue.userData.role='physical-snap';
 }
 for(const sx of[-1,1])for(const sy of[-1,1])walls.push(add(endCorner(sx,sy),[0,0,0],'exact R3 end corner and socket-side cheek'));
 for(const sy of[-1,1]){
  add(new THREE.BoxGeometry(10.5,1.1,2.51),[0,sy*27.45,-3.355],'end wall below the real receiving mouth');
  if(sy>0)add(new THREE.BoxGeometry(10.5,1.1,1.8),[0,27.45,3.7],'upper end wall above the real receiving mouth');
  else add(new THREE.BoxGeometry(10.5,1.1,.15),[0,-27.45,2.775],'lower end wall above the real receiving mouth');
 }
 const bores=spec.mountingHolesMm.map(([x,y])=>add(extrude(ring(3.13,2.425),6.26),[x,y,-4.61],'continuous mounting sleeve with outward bore wall'));
 const ledge=add(new THREE.BoxGeometry(22,1.05,1.75),[0,-11.475,3.725],'closed front step riser');
 const snaps=[];for(const x of[-10.3,10.3]){snaps.push(add(new THREE.BoxGeometry(1.05,3.95,.75),[x,-23.4,-4.97],'recessed rear latch head and real backing'));snaps.push(add(new THREE.BoxGeometry(.85,3.6,5.6),[x,-23.4,-1.8],'fixed rear snap stem'));}
 const supports=[];for(const[x,y]of[[-7,22],[7,22],[-7,-10],[.4,-22]])supports.push(add(new THREE.CylinderGeometry(1,1,7.26,24).rotateX(Math.PI/2),[x,y,-.98],'PCB support post terminating at underside'));
 return {parts,front,lower,rear,rearSkin,walls,bores,ledge,snaps,supports};
}

function buildBoard(host){
 const green=materials.plastic(0x1c4637,{roughness:.89}),dark=materials.plastic(0x222723,{roughness:.8}),metal=materials.metal(0xb2b3a4),ceramic=materials.plastic(0xaba285),s=polygon([[-10.8,25.5],[-10.8,-12.2],[-4.5,-12.2],[-4.5,-25.5],[4.5,-25.5],[4.5,-12.2],[10.8,-12.2],[10.8,25.5]]);
 for(const y of spec.headers.y)for(const x of spec.headers.x)circleHole(s,x,y,.39);
 for(const x of[4.35,7.65])circleHole(s,x,14.3,.43);
 for(const y of[-22.5,22.5])for(const x of[-3,-1,1,3])circleHole(s,x,y,.34);
 const pcb=mesh(host.body,extrude(s,.8),green,[0,0,2.65],'8Servos2-Chain own shaped populated PCB with 32 actual connector drills');pcb.userData={role:'physical-pcb',inferred:true};
 const pads=[];for(const y of spec.headers.y)for(const x of spec.headers.x){const p=mesh(host.body,extrude(ring(.63,.39),.07),metal,[x,y,3.45],'U223 physical header annular solder pad');pads.push(p);}
 const packages=[],terminals=[],passives=[];
 // Hidden installation comes from this SKU schematic identity; package placement is an explicit own-photo inference.
 for(const[name,x,y,w,h,t]of[['STM32G031G8U6',-5,5,4,4,.8],['SY8303AIC',-5,15,3,3,.95],['INA199A1DCKR',-5,-8,2.1,1.3,.75],['SSP7615-33',-5,21,2.8,1.3,.85]]){
  const q=mesh(host.body,extrude(shapeRect(w,h,.12),t),dark,[x,y,3.45],'U223 fixed '+name+' package envelope');packages.push(q);
  for(const sy of[-1,1])for(let i=0;i<3;i++)terminals.push(mesh(host.body,new THREE.BoxGeometry(.35,.45,.13),metal,[x+(i-1)*.65,y+sy*(h/2+.12),3.515],'U223 physical package solder termination'));
 }
 const inductor=mesh(host.body,extrude(shapeRect(4.3,4.3,.4),1.5),materials.plastic(0x454b44),[-5.3,10,3.45],'U223 fixed buck inductor envelope');packages.push(inductor);
 for(let i=0;i<14;i++){const x=-7.8+(i%3)*1.8,y=-9+Math.floor(i/3)*5.5;passives.push(mesh(host.body,new THREE.BoxGeometry(.95,.6,.45),i%3?ceramic:dark,[x,y,3.675],'U223 hidden populated passive envelope'));for(const sx of[-1,1])terminals.push(mesh(host.body,new THREE.BoxGeometry(.18,.6,.12),metal,[x+sx*.43,y,3.51],'U223 passive fixed physical terminal'));}
 const indicators=[];for(const [y,color]of[[18.7,0x8c2921],[20.1,0x347443]]){const q=mesh(host.body,new THREE.BoxGeometry(1.6,.85,.6),materials.plastic(color,{roughness:.7}),[-1.5,y,3.75],'U223 internal nonemissive indicator carrier; no confirmed external light path');indicators.push(q);for(const x of[-2.25,-.75])terminals.push(mesh(host.body,new THREE.BoxGeometry(.3,.85,.12),metal,[x,y,3.51],'U223 indicator fixed terminal'));}
 return {pcb,pads,packages,terminals,passives,indicators};
}

function chainSocket(host,id){
 const cfg=spec[id],frame=new THREE.Group();frame.position.fromArray(cfg.position);frame.quaternion.copy(portQuaternion(cfg.face));frame.name='U223 '+cfg.label+' cyan HY2.0-4P actual socket';host.body.add(frame);
 const cyan=materials.plastic(0x1495a6,{roughness:.62}),metal=materials.metal(0xbdbca6),parts=[],b=(size,pos,name,mat=cyan)=>{const q=mesh(frame,new THREE.BoxGeometry(...size),mat,pos,'U223 '+cfg.label+' '+name);parts.push(q);return q;};
 for(const sx of[-1,1]){b([.65,5.9,4.5],[sx*4.675,-2.95,.05],'full side wall');b([.65,5.9,.6],[sx*4.0,-2.95,2.0],'upper keyed rail');b([.75,1.4,.65],[sx*3.8,-1,1.65],'retaining shoulder');}
 const floor=b([8.7,5.9,.6],[0,-2.95,-1.9],'physical socket floor');
 const back=b([8.7,.65,3.9],[0,-5.475,.35],'recessed dielectric contact carrier');
 const bridge=b([4.7,.95,.5],[0,-2.8,2.0],'central top latch retainer');
 const contacts=[],tails=[],returns=[],pads=[];
 for(let i=0;i<4;i++){
  const x=(i-1.5)*2;contacts.push(b([.42,4.1,.42],[x,-2.75,-.05],'retained contact '+(i+1),metal));returns.push(b([.42,.42,3.0],[x,-5.45,1.28],'bent return terminal '+(i+1),metal));tails.push(b([.42,.42,1.2],[x,-5.45,2.9],'physical PCB tail '+(i+1),metal));
  const pad=mesh(host.body,extrude(ring(.55,.34),.07),metal,[0,0,0],'U223 '+cfg.label+' annular PCB termination');const p=new THREE.Vector3(x,-5.45,3.45-cfg.position[2]).applyQuaternion(frame.quaternion).add(frame.position);pad.position.copy(p);pads.push(pad);
 }
 const port=host.add(new Port({id,label:cfg.label,connector:'grove',position:cfg.position,quaternion:portQuaternion(cfg.face),hitSize:[10,1,4.5],pinGrid:{cols:4,rows:1,pitch:2,center:[0,-.05],order:col=>col+1},pins:cfg.pins.map((name,i)=>({n:i+1,name})),meta:{role:'visual-connector',face:cfg.face,physicalFamily:'HY2.0-4P socket',scope:'Mechanical four-contact family and cable pose only; literal printed names, no UART,power,protocol,electrical or firmware routing'}}));
 return {frame,parts,floor,back,bridge,contacts,returns,tails,pads,port};
}

function headers(host){
 const yellow=materials.plastic(0xc9a239,{roughness:.72}),metal=materials.metal(0xb9b9a1,{roughness:.4}),carriers=[],posts=[],tips=[],tails=[],ports=[];
 for(let pair=0;pair<4;pair++){const y=(spec.headers.y[pair*2]+spec.headers.y[pair*2+1])/2;carriers.push(mesh(host.body,extrude(headerCarrier(),1.3),yellow,[6,y,3.45],'U223 actual fixed 3x2 yellow keyed insulator '+(pair+1)));}
 for(let c=0;c<8;c++){
  const y=spec.headers.y[c];for(const x of spec.headers.x){
   posts.push(mesh(host.body,new THREE.BoxGeometry(.5,.5,2.0),metal,[x,y,4.45],'U223 male square post CH'+c));
   tips.push(mesh(host.body,new THREE.CylinderGeometry(.16,.353553,.3,4).rotateY(Math.PI/4).rotateX(Math.PI/2),metal,[x,y,5.6],'U223 tapered male square pin tip CH'+c));
   tails.push(mesh(host.body,new THREE.BoxGeometry(.5,.5,1.13),metal,[x,y,2.885],'U223 through-board header solder tail CH'+c));
  }
  ports.push(host.add(new Port({id:'ch'+c,label:'CH'+c+' · documentary G/V/S',connector:spec.headers.connector,position:[6,y,5.75],quaternion:portQuaternion('front'),hitSize:[7.5,1,1.8],pinGrid:{cols:3,rows:1,pitch:2.54,center:[0,0],order:col=>col+1},pins:spec.headers.labels.map((name,i)=>({n:i+1,name})),meta:{role:'visual-connector',face:'front',physicalFamily:'2.54mm three male square posts',scope:'Mechanical header appearance only; no PWM,servo joint,mode or electrical routing'}})));
 }
 return {carriers,posts,tips,tails,ports};
}

function dcJack(host){
 const frame=new THREE.Group();frame.position.fromArray(spec.dc.position);frame.quaternion.setFromAxisAngle(new THREE.Vector3(0,1,0),Math.PI/2);frame.name='U223 DC5.5x2.1 deep receiving jack';host.body.add(frame);
 const black=materials.plastic(0x252923,{roughness:.76}),metal=materials.metal(0xb5b9b1,{roughness:.43}),parts=[],add=(g,pos,name,m=black)=>{const o=mesh(frame,g,m,pos,'U223 DC '+name);parts.push(o);return o;};
 const shell=shapeRect(6.2,9.4,.16);circleHole(shell,0,0,2.95);const housing=add(extrude(shell,6.6),[0,0,-6.6],'fixed housing with real bore');
 const faceShape=shapeRect(7.2,9.4,.16);circleHole(faceShape,0,0,3);const face=add(extrude(faceShape,.28),[0,0,-.28],'actual square front flange with true Ø6 entrance');
 const sleeve=add(extrude(ring(2.95,2.75),5.8),[0,0,-5.8],'metal outer contact sleeve',metal);
 const back=add(new THREE.CylinderGeometry(2.75,2.75,.7,48).rotateX(Math.PI/2),[0,0,-6.15],'dielectric rear backing');
 const center=add(new THREE.CylinderGeometry(1.05,1.05,5.2,48).rotateX(Math.PI/2),[0,0,-3.2],'retained real 2.1mm centerpost',metal);
 const terminals=[];for(const p of[[-2.5,2.7,-5.6],[2.5,2.7,-5.6],[0,-2.8,-6.2]])terminals.push(add(new THREE.BoxGeometry(.5,1.3,1.3),p,'fixed physical solder terminal',metal));
 const port=host.add(new Port({id:'dc',label:'DC5.5×2.1 mechanical',connector:spec.dc.connector,position:spec.dc.position,quaternion:portQuaternion('right'),hitSize:[6,1,6],pins:[{n:1,name:'center'},{n:2,name:'sleeve'}],meta:{role:'visual-connector',face:'right',physicalFamily:'DC5.5x2.1 receiving jack',scope:'Mechanical cavity and two actual contact bodies only; no voltage,polarity,power or electrical behavior'}}));
 return {frame,parts,housing,face,sleeve,back,center,terminals,port};
}

function capacitor(host){
 const frame=new THREE.Group();frame.position.fromArray(spec.capacitor.position);frame.name='U223 fixed electrolytic capacitor; never a selector';host.body.add(frame);
 const metal=materials.metal(0xbbbdb7,{roughness:.5}),red=materials.plastic(0xa5353b,{roughness:.6}),black=materials.plastic(0x1f241e),parts=[];
 const base=mesh(frame,new THREE.CylinderGeometry(3.4,3.4,.3,48).rotateX(Math.PI/2),black,[0,0,.15],'U223 fixed bulk fixed capacitor seat');parts.push(base);
 const sleeve=mesh(frame,new THREE.CylinderGeometry(3.4,3.4,1.65,48).rotateX(Math.PI/2),red,[0,0,1.125],'U223 fixed bulk fixed red insulated can');parts.push(sleeve);
 const top=mesh(frame,new THREE.CylinderGeometry(3.12,3.12,.15,48).rotateX(Math.PI/2),metal,[0,0,2.025],'U223 fixed bulk actual metal end cap');parts.push(top);
 const terminals=[];for(const x of[-1.65,1.65])terminals.push(mesh(frame,new THREE.BoxGeometry(.48,.6,.8),metal,[x,0,-.2],'U223 fixed capacitor retained terminal'));
 return {frame,parts,base,sleeve,top,terminals};
}

function films(host){
 const plastic=materials.plastic(0xd3d5d2,{roughness:.88}),w=spec.labels.front.size[0],h=spec.labels.front.size[1],xmin=-w/2,xmax=w/2,ymin=-h/2,ymax=h/2,notchX=1.718,notchY=10.555;
 // The L-shaped carrier is a closed outer contour; the open window is never an intersecting hole.
 const frontShape=polygon([[xmin,ymin],[notchX,ymin],[notchX,notchY],[xmax,notchY],[xmax,ymax],[xmin,ymax]]);
 const front=mesh(host.body,extrude(frontShape,.04),plastic,[-.05,7.685,5.71],'U223 independent physical L-shaped front adhesive film');
 const back=mesh(host.body,extrude(shapeRect(...spec.labels.back.size,.3),.04),plastic,[0,7.685,-5.75],'U223 independent physical rear adhesive film');
 for(const q of[front,back])q.userData={role:'physical-label-substrate',thicknessMm:.04,registrationInferred:true};return {front,back};
}

export function buildEightServosChain(host){
 const shell=buildCase(host),board=buildBoard(host),input=chainSocket(host,'grove'),output=chainSocket(host,'out'),header=headers(host),dc=dcJack(host),bulk=capacitor(host),labels=films(host);
 host.eightServosChainAssembly={shell,board,input,output,header,dc,bulk,labels};host.unitStickers=addStickers(host);
}
