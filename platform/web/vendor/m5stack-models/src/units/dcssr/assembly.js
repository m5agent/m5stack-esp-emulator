import * as THREE from 'three';
import {Component,Led,Port,VisualJoint,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,FACE,portQuaternion,header} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import {NativeFlexureButton} from './NativeFlexureButton.js';
import {addStickers} from './stickers.js';
import data from './geometry-data.js';

class FixedRedLed extends Led{
 set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:0xff2820});}
}
function hole(shape,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(p);}
function board(host){
 const y=spec.controller.y,green=materials.plastic(0x316441,{roughness:.86}),dark=materials.plastic(0x202720,{roughness:.8}),metal=materials.metal(0xb4b8a4,{roughness:.44});
 const outline=new THREE.Shape();outline.moveTo(-21.05,y-7.5);outline.lineTo(-5.3,y-7.5);outline.lineTo(-5.3,-33.0);outline.lineTo(5.3,-33.0);outline.lineTo(5.3,y-7.5);outline.lineTo(21.05,y-7.5);outline.lineTo(21.05,y+7.5);outline.lineTo(-21.05,y+7.5);outline.closePath();
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(outline,{depth:.8,bevelEnabled:false}),green,[0,0,5.35]);pcb.name='DCSSR physical controller PCB';pcb.userData={role:'physical-pcb',scope:'Reconstructed board/installed packages, no circuits or firmware'};
 const chips=[];for(const [name,x,dy,w,h,d]of[['ESP32-C3 inferred body',-4,1.9,5,5,.9],['RS485 transceiver appearance envelope',10,1.8,4,5,1.3],['power converter appearance envelope',-9,-3,3,3,1.1],['regulator appearance envelope',7,-2.7,3,3,1]]){
  const chip=slab(host.body,w,h,d,.16,[x,y+dy,6.15],dark,[],.03);chip.name=`DCSSR concealed ${name} package`;chips.push(chip);
  for(const sign of[-1,1])for(let j=0;j<4;j++)mesh(host.body,new THREE.BoxGeometry(.5,.35,.3),metal,[x+sign*(w/2+.15),y+dy+(j-1.5)*h/5,6.2],`DCSSR ${name} physical lead`);
 }
 for(const [x,dy]of[[-12,-1.8],[8,4]])slab(host.body,3.6,3.4,1.6,.25,[x,y+dy,6.15],dark,[],.04).name='DCSSR concealed buck inductor';
 for(const [x,dy]of[[-8,4],[-4,-4],[5,5],[12,-4],[-13,4]])slab(host.body,1.8,1.0,.65,.09,[x,y+dy,6.15],materials.plastic(0xc3ad82),[],.02).name='DCSSR concealed passive package';
 const tactile=slab(host.body,5.2,5.2,2.25,.3,[0,-28.65,6.15],metal,[],.045);tactile.name='DCSSR inferred installed tactile switch body below native tongue';
 mesh(host.body,new THREE.CylinderGeometry(.95,.95,1.3,32).rotateX(Math.PI/2),dark,[0,-28.65,8.9],'DCSSR inferred fixed tactile-switch plunger envelope');
 // The exact U140 rear photograph labels concealed six-pad download positions. It is not
 // advertised as an exposed Port through the closed rear enclosure.
 const download=header(host.body,{position:[-6,y-4.1,6.1],face:'back',cols:6,rows:1,pitch:1.27});download.name='DCSSR internal J1 six-pin download socket';
 const forks=[];for(const x of spec.ssr.screwX){
  const s=new THREE.Shape(),w=8.5,r=2.65,bottom=-23.1,top=-9.3;
  // U-shaped end is an open contour, never an intersecting closed hole.
  s.moveTo(x-w/2,bottom);s.lineTo(x+w/2,bottom);s.lineTo(x+w/2,top);s.lineTo(x+r,top);s.lineTo(x+r,-12.1);s.absarc(x,-12.1,r,0,-Math.PI,true);s.lineTo(x-r,top);s.lineTo(x-w/2,top);s.closePath();
  const fork=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.9,bevelEnabled:false,curveSegments:32}),materials.metal(0xbac6aa,{roughness:.47}),[0,0,6.55],'DCSSR control-input fork lug with real open U-slot');forks.push(fork);
  slab(host.body,8.5,2.7,.8,.15,[x,-22.0,6.5],green,[],.025).name='DCSSR reinforced fork PCB root';
 }
 return{pcb,chips,tactile,download,forks};
}
function grove(host){
 const group=new THREE.Group();group.position.fromArray(spec.grove.position);group.quaternion.copy(FACE.bottom);group.name='DCSSR open-top red HY2.0-4P Grove';host.body.add(group);
 const red=materials.plastic(0xca3024,{roughness:.65}),metal=materials.metal(0xb5ac84,{roughness:.44}),box=(size,p,name,mat=red)=>mesh(group,new THREE.BoxGeometry(...size),mat,p,'DCSSR Grove '+name);
 for(const side of[-1,1]){box([.65,5.2,6.5],[side*4.675,0,-3.25],'side wall');box([.7,.6,3],[side*3.85,2.3,-4.9],'upper guide');box([.65,.6,1.1],[side*3.7,2.3,-1.2],'latch shoulder');}
 box([8.7,.65,6.5],[0,-2.275,-3.25],'floor');box([8.7,4.55,.65],[0,.325,-6.175],'recessed physical rear wall');box([4.8,.45,2.1],[0,2.375,-4.65],'latch bridge');
 for(let i=0;i<4;i++){box([.42,.42,4.6],[(i-1.5)*2,.2,-3.6],`contact ${i+1}`,metal);box([.42,1.2,.42],[(i-1.5)*2,-2.65,-5.7],`PCB tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:['GND','5V','SDA','SCL'].map((name,i)=>({n:i+1,name,color:['black','red','yellow','white'][i]})),pinGrid:{cols:4,rows:1,pitch:2,center:[0,.2],order:col=>col+1},meta:{role:'visual-connector',face:'bottom',scope:'Physical four-pin socket only; no I2C, supply, firmware or AC/DC behavior'}}));return{group,port};
}
function terminal(host,i){
 const face=i===0?'left':'right',position=spec.terminal.positions[i],frame=new THREE.Group();frame.position.fromArray(position);frame.quaternion.copy(portQuaternion(face));frame.name=`DCSSR fixed RS485PWR ${i+1} HT3.96 socket`;host.body.add(frame);
 const orange=materials.plastic(0xf2912c,{roughness:.67}),metal=materials.metal(0xb7baa8,{roughness:.44}),box=(size,p,name,mat=orange)=>mesh(frame,new THREE.BoxGeometry(...size),mat,p,`DCSSR terminal-${i+1} fixed ${name}`);
 box([16,.7,7],[0,-6.0,0],'rear support');
 for(const side of[-1,1]){box([.65,5.65,7],[side*7.675,-2.825,0],'side cheek');box([14.7,5.65,.55],[0,-2.825,side*3.225],'retention wall');}
 for(const x of spec.terminal.pinX){box([.62,4.8,.62],[x,-3.1,-.4],'male contact pin',metal);box([.62,.62,2.5],[x,-6,-1.4],'PCB tail',metal);}
 const port=host.add(new Port({id:`terminal-${i+1}`,label:`RS485PWR ${i+1} · HT3.96-4P`,connector:'ht3.96-4p',position,quaternion:portQuaternion(face),hitSize:[16,1,7],pins:spec.terminal.names.map((name,j)=>({n:j+1,name})),pinGrid:{cols:4,rows:1,pitch:3.96,center:[0,-.4],order:col=>col+1},meta:{role:'visual-connector',face,insetSocket:true,pinOrderEvidence:'Exact U140 rear label; local row order B/A/VIN/GND on both opposing mating frames. No bus continuity is implemented.',scope:'Detachable physical connector only; no voltage, supply, RS485/Modbus or electrical state'}}));return{frame,port};
}
function screwHead(host,x,y,id,label){
 const steel=materials.metal(0x696f69,{roughness:.45}),dark=materials.metal(0x303733,{roughness:.64}),head=new THREE.Group();head.name=`DCSSR ${label} cross-head terminal screw`;
 const shape=new THREE.Shape();shape.absarc(0,0,2.55,0,Math.PI*2,false);const recess=new THREE.Path(),l=1.85,t=.35,points=[[-t,-l],[t,-l],[t,-t],[l,-t],[l,t],[t,t],[t,l],[-t,l],[-t,t],[-l,t],[-l,-t],[-t,-t]].reverse();points.forEach(([a,b],i)=>i?recess.lineTo(a,b):recess.moveTo(a,b));recess.closePath();shape.holes.push(recess);
 mesh(head,new THREE.CylinderGeometry(2.55,2.55,.15,64).rotateX(Math.PI/2),dark,[0,0,-.05],'DCSSR terminal screw recess floor');
 mesh(head,new THREE.ExtrudeGeometry(shape,{depth:.85,bevelEnabled:false,curveSegments:40}),steel,[0,0,0],'DCSSR physical cross-recess SSR terminal screw head');
 const joint=host.add(new VisualJoint({id,label:`${label} screw visual angle`,position:[x,y,12.05],axis:[0,0,1],meta:{visualRangeDeg:[-180,180],rangeEvidence:'Visual screw-head angle only. Thread pitch, tightening limits, clamp travel and cover removal unconfirmed.',scope:'External visible head angle only; no tightening, electrical switching, force or load simulation'}}));joint.object3d.add(head);return{joint,head};
}
function ssr(host){
 const dark=materials.plastic(0x262c29,{roughness:.78}),white=materials.plastic(0xe6e8e2,{roughness:.74}),metal=materials.metal(0xadb3b1,{roughness:.53}),clampMetal=materials.metal(0x9a9e90,{roughness:.49}),{yMin,yMax,screwX,screwY,mountY,mountRadius}=spec.ssr;
 const length=yMax-yMin,center=(yMin+yMax)/2;
 const base=slab(host.body,44.0,length,1.2,.4,[0,center,-15.5],metal,mountY.map(cy=>({w:mountRadius*2,h:mountRadius*2,r:mountRadius,cx:0,cy:cy-center})),.04);base.name='DCSSR SSR aluminum thermal base plate with two real mounting bores';
 const main=slab(host.body,44.0,length-27.0,27.5,.65,[0,center,-14.3],dark,[],.09);main.name='DCSSR sealed DELIXI solid-state relay package';main.userData={role:'sealed-ssr-package',scope:'Opaque semiconductor relay exterior only; no moving armature or electrical behavior'};
 const covers=[],clamps=[],screws=[];
 for(const [row,y]of screwY.entries()){
  const end=row===0?1:-1,insideY=y-end*5.6,outerY=y+end*6.2;
  // Each end has a central open mounting channel, two separate terminal wells,
  // recessed metal clamp cages and a white screw-access guard.
  for(const x of screwX){
   slab(host.body,16.25,13.5,18.6,.25,[x,y,-14.3],dark,[],.05).name='DCSSR SSR terminal lower supporting leg';
   for(const dx of[-8.0,8.0])slab(host.body,.7,13.5,8.3,.1,[x+dx,y,4.3],dark,[],.03).name='DCSSR SSR open terminal well side wall';
   slab(host.body,15.8,.65,8.3,.1,[x,insideY,4.3],dark,[],.025).name='DCSSR SSR terminal well recessed rear wall';
   const cage=new THREE.Group();cage.name='DCSSR SSR physical recessed screw clamp cage';host.body.add(cage);
   mesh(cage,new THREE.BoxGeometry(10.4,10.8,.7),clampMetal,[x,y,4.8],'DCSSR SSR contact cage lower plate');
   for(const dx of[-4.85,4.85])mesh(cage,new THREE.BoxGeometry(.6,10.8,3.5),clampMetal,[x+dx,y,6.6],'DCSSR SSR contact cage side web');
   mesh(cage,new THREE.BoxGeometry(9.3,10.2,.65),clampMetal,[x,y,8.3],'DCSSR SSR clamp pressure plate');
   mesh(cage,new THREE.CylinderGeometry(1.15,1.15,3.9,40).rotateX(Math.PI/2),metal,[x,y,10.2],'DCSSR SSR terminal screw fixed shank envelope');clamps.push(cage);
   const n=row*2+(x<0?1:2);screws.push(screwHead(host,x,y,`ssr-screw-${n}`,`${row===0?'DC output':'DC input'} ${x<0?'left':'right'}`));
   slab(host.body,3.5,1.0,2.9,.25,[x,outerY,10.6],white,[],.045).name='DCSSR white terminal-guard end retention tongue';
  }
  const cover=slab(host.body,45,13.5,2.3,.7,[0,y,13.2],white,screwX.map(cx=>({w:6.5,h:6.5,r:3.25,cx,cy:0})),.08);cover.name=`DCSSR SSR fixed white ${row===0?'DC output':'DC input'} terminal guard with two true screw bores`;covers.push(cover);
 }
 const panel=slab(host.body,43,29.0,.18,.15,[0,9.4,13.22],materials.plastic(0x4d5350,{roughness:.83}),[{w:3.8,h:3.8,r:1.9,cx:spec.ssr.indicator[0],cy:spec.ssr.indicator[1]-9.4}],.025);panel.name='DCSSR SSR physical dark nameplate support with independent indicator aperture';
 for(const x of[-22.2,22.2])slab(host.body,.6,5.4,4.5,.12,[x,9.4,7.3],dark,[],.025).name='DCSSR SSR molded side retention tab';
 return{base,main,covers,clamps,screws,panel};
}
function indicators(host){
 const lens=new THREE.Mesh(new THREE.BoxGeometry(3.0,.7,.48),materials.plastic(0xe6e6d8,{roughness:.45}));lens.name='DCSSR SK6812 physical lens behind native button slit';
 const rgb=host.add(new Led({id:'rgb',label:'Controller SK6812 RGB',mesh:lens,position:spec.rgb.position,radius:.25,glowSize:3.0,meta:{role:'externally-driven-visual',part:'SK6812; official U140 specifications',scope:'Defaults off. External RGB/on/brightness only; no automatic button, configuration, bus or relay response'}}));rgb.glow.position.z=.25;
 const redMesh=new THREE.Mesh(new THREE.SphereGeometry(.53,28,16),materials.plastic(0x812a21,{roughness:.4}));redMesh.scale.z=.22;redMesh.name='DCSSR D4 red 0603 power indicator light-guide face';
 const power=host.add(new FixedRedLed({id:'power-led',label:'Controller red PWR indicator',mesh:redMesh,position:spec.power.position,quaternion:FACE.back,radius:.3,glowSize:2.4,color:0xff2820,meta:{role:'externally-driven-visual',colorMode:'fixed-red',part:'Red PWR indicator shown in exact U140 rear label; package envelope inferred',positionEvidence:'Rear PWR icon location from exact U140 photograph; optical route through rear molding/film inferred. Source CAD remains complete.',scope:'Defaults off. External on/brightness only; no supply or other-indicator linkage'}}));
 const [x,y,z]=spec.ssr.indicator;const bezel=slab(host.body,4.4,4.4,.4,2.15,[x,y,z-.35],materials.plastic(0x202623,{roughness:.75}),[{w:3.3,h:3.3,r:1.65,cx:0,cy:0}],.035);bezel.name='DCSSR SSR independent circular red indicator bezel';
 const ssrMesh=new THREE.Mesh(new THREE.SphereGeometry(1.55,40,24),materials.plastic(0x4c201d,{roughness:.35}));ssrMesh.scale.z=.25;ssrMesh.name='DCSSR SSR physical red indicator lens';
 const ssrLed=host.add(new FixedRedLed({id:'ssr-led',label:'SSR red indicator',mesh:ssrMesh,position:[x,y,z-.22],radius:1.1,glowSize:4,color:0xff2820,meta:{role:'externally-driven-visual',colorMode:'fixed-red',part:'Bundled DELIXI CDG1-1DD/10A indicator',scope:'Defaults off. External on/brightness only; no relay continuity, actual load, button, voltage or switching state'}}));return{rgb,power,ssrLed};
}
export function buildDCSSR(host){
 const native=addCadParts(host,data,{shell:materials.plastic(0xe7e8e3,{roughness:.78})}),circuit=board(host),input=grove(host),terminals=[terminal(host,0),terminal(host,1)],relay=ssr(host),leds=indicators(host),button=host.add(new NativeFlexureButton(Object.values(native)[0]));
 host.add(new Component({id:'sensor',label:'DCSSR visual anchor',meta:{role:'visual-anchor',scope:'No DC switching, relay state, Modbus/I2C, WiFi, firmware, registers or actual hardware connection'}}));
 const stickers=addStickers(host,{native:Object.values(native)[0],panel:relay.panel});host.dcssrAssembly={native,circuit,input,terminals,relay,leds,button,stickers};
}
