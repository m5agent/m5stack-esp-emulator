import * as THREE from 'three';
import {Device,Module,Button,Led,Component,materials} from '../../core/index.js';
import {mesh,slab,grove} from '../../modeling/parts.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {spec,KEYS,KEYMAP} from './dimensions.js';

function annulus(parent,{outer,inner,depth,position,material,name}){
 const s=new THREE.Shape();s.absarc(0,0,outer,0,Math.PI*2,false);const hole=new THREE.Path();hole.absarc(0,0,inner,0,Math.PI*2,true);s.holes.push(hole);
 return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:32}),material,position,name);
}

function board(host){
 const holes=[{w:5,h:5,r:2.5,cx:-37,cy:22},...Array.from({length:6},(_,i)=>({w:1.1,h:1.1,r:.55,cx:-35.5+i*2.54,cy:-25.5}))];
 const pcb=slab(host.body,84,54,.9,5,[0,0,-3.1],materials.plastic(0x647960,{roughness:.93}),holes,0);pcb.name='CardKB FR4 PCB';pcb.userData={source:'official-drawing-reconstruction',dimensionSource:'U035-B cardkeyboard_v1_1 drawing; mounting aperture from official front/back photos'};
 slab(host.body,84,54,.05,5,[0,0,-3.15],materials.plastic(0xd8e1d7,{roughness:.86}),holes,0).name='CardKB rear solder mask';
 slab(host.body,84,54,.05,5,[0,0,-2.2],materials.plastic(0xe3e9df,{roughness:.83}),holes,0).name='CardKB front solder mask';
 host.parts={pcb};
 const gold=materials.metal(0xb3a564,{roughness:.62});
 for(let i=0;i<6;i++)for(const z of [-3.151,-2.149])annulus(host.body,{outer:.88,inner:.55,depth:.035,position:[-35.5+i*2.54,-25.5,z],material:gold,name:'CardKB ISP plated through-hole pad'});
}

function key(host,key){
 const [x,y,z]=key.position,base=new THREE.Group();base.name='CardKB fixed switch '+key.id;base.position.set(x,y,0);host.body.add(base);
 const solder=materials.metal(0xa8b3a5,{roughness:.57});
 slab(base,4.65,4.65,.92,.45,[0,0,-2.15],materials.plastic(0x5d6860,{roughness:.87}),[],.025).name='CardKB switch fixed body';
 for(const a of [-1,1])for(const b of [-1,1]){
  mesh(base,new THREE.BoxGeometry(.72,1.0,.12),materials.metal(0xa2aa8f,{roughness:.75}),[a*2.52,b*1.65,-2.09],'CardKB switch PCB pad');
  mesh(base,new THREE.BoxGeometry(.5,.65,.55),solder,[a*2.48,b*1.65,-1.87],'CardKB switch solder leg');
 }
 const shape=new THREE.Shape(),a=2.35,cut=.62;shape.moveTo(-a+cut,-a);shape.lineTo(a-cut,-a);shape.lineTo(a,-a+cut);shape.lineTo(a,a-cut);shape.lineTo(a-cut,a);shape.lineTo(-a+cut,a);shape.lineTo(-a,a-cut);shape.lineTo(-a,-a+cut);shape.closePath();
 const bore=new THREE.Path();bore.absarc(0,0,1.25,0,Math.PI*2,true);shape.holes.push(bore);
 mesh(base,new THREE.ExtrudeGeometry(shape,{depth:.2,bevelEnabled:false}),materials.metal(0xb9c0b3,{roughness:.52}),[0,0,-1.2],'CardKB stamped switch cover');
 annulus(base,{outer:1.5,inner:1.08,depth:.2,position:[0,0,-1.0],material:materials.plastic(0xe0e7d6,{roughness:.71}),name:'CardKB actuator guide collar'});
 const profile=[[0,0],[.9,0],[1.05,.08],[1.05,.28],[.92,.4],[0,.4]].map(p=>new THREE.Vector2(...p));
 const cap=new THREE.Mesh(new THREE.LatheGeometry(profile,24).rotateX(Math.PI/2),materials.metal(0xc4b56c,{roughness:.65}));cap.name='CardKB moving cap '+key.id;
 host.add(new Button({id:key.id,label:key.label,mesh:cap,position:[x,y,z],travel:.2,meta:{role:'visual-key',keyLabel:key.label,row:key.row,column:key.col,travelSource:'Photo-derived visual travel; no matrix scan or character translation'}}));
}

function electronics(host){
 const chip=slab(host.body,7,7,.85,.2,[-35.2,-2.6,-2.15],materials.plastic(0x273c31,{roughness:.85}),[],.04);chip.name='CardKB ATMega8A package';
 const solder=materials.metal(0xb3bdac,{roughness:.58});
 for(const side of [-1,1])for(let i=0;i<8;i++){
  mesh(host.body,new THREE.BoxGeometry(1.25,.3,.2),solder,[-35.2+side*3.92,-2.6+(i-3.5)*.8,-2.0],'CardKB MCU side lead');
  mesh(host.body,new THREE.BoxGeometry(.3,1.25,.2),solder,[-35.2+(i-3.5)*.8,-2.6+side*3.92,-2.0],'CardKB MCU upper lower lead');
 }
 for(const [x,y,w,h]of [[-39,3.2,1.4,.8],[-36.5,3.2,1.4,.8],[-34.2,3.2,1.4,.8],[-29.7,-.6,.8,1.5],[-29.7,-2.7,.8,1.5],[-31.6,5.8,.8,1.5]]){
  slab(host.body,w,h,.45,.08,[x,y,-2.15],materials.plastic(0x586551,{roughness:.84}),[],.015).name='CardKB passive package';
  for(const s of [-1,1])mesh(host.body,new THREE.BoxGeometry(w*.22,h,.14),solder,[x+s*w*.38,y,-2.06],'CardKB passive solder end');
 }
 slab(host.body,2.8,2.8,.8,.16,[-26.5,-5,-2.15],materials.plastic(0xd8e0cf,{roughness:.79}),[],.025).name='CardKB RGB package';
 host.add(new Led({id:'rgb',label:'CardKB RGB',radius:.65,glowSize:2.5,position:spec.rgb,lensColor:0xdde6d4,meta:{role:'externally-driven-visual',positionSource:'Official U035-B front photograph; no key-to-LED behavior'}}));
}

function build(host){
 board(host);for(const item of KEYS)key(host,item);electronics(host);
 const socket=grove(host,{...spec.grove,color:0xe1e6d6});socket.name='CardKB left Grove socket';
 const solder=materials.metal(0xb0baa8,{roughness:.52});
 for(const y of [9,11,13,15]){
  mesh(host.body,new THREE.BoxGeometry(.9,.42,.42),solder,[-34.55,y,.35],'CardKB Grove contact elbow');
  mesh(host.body,new THREE.BoxGeometry(.42,.42,2.65),solder,[-34.2,y,-.975],'CardKB Grove PCB tail');
 }
 host.add(new Component({id:'sensor',label:'CardKB geometry anchor',meta:{role:'visual-anchor',scope:'no-keyboard-firmware'}}));
}

export class Model extends Device{
 static meta={id:'m5stack.unit.cardkb',name:'CardKB v1.1',sku:'U035-B',vendor:'M5Stack',size:spec.nominalMm,keymap:KEYMAP,drawingEnvelopeMm:spec.drawingEnvelopeMm};
 build(){build(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.cardkb.grove',name:'CardKB v1.1',sku:'U035-B',connector:'grove',keymap:KEYMAP};
 build(options={}){
  const {unitFrame}=buildGroveModuleAssembly(this,build,options);
  // This Unit has a left-facing input. Keep its large board beyond the host
  // port in the initial assembly, with the actual input mouth facing back.
  if(!options.unitPose){unitFrame.setPose({rotation:[0,0,Math.PI/2]});unitFrame.setDistance(options.cableLength??35);}
 }
}
export {KEYS,spec,KEYMAP};
export default Model;
