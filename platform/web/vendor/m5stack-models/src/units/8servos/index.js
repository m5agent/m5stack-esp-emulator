import {addStickers} from './stickers.js';
import * as THREE from 'three';
import {Device,Module,Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {mesh,slab,grove,screw,portQuaternion} from '../../modeling/parts.js';
import {spec,CHANNELS} from './dimensions.js';
import data from './geometry-data.js';
import {TerminalPlug} from './TerminalPlug.js';

function board(host){
 const s=new THREE.Shape(),x=9.9,y=25.4,r=2.6,n=5.3,bore=4.1,dy=Math.sqrt(bore*bore-(x-8)**2),angle=Math.acos((x-8)/bore);
 s.moveTo(-x+r,-y);s.lineTo(-n,-y);s.lineTo(-n,-21.1);s.lineTo(n,-21.1);s.lineTo(n,-y);s.lineTo(x-r,-y);
 s.absarc(x-r,-y+r,r,-Math.PI/2,0);s.lineTo(x,spec.mountY-dy);
 s.absarc(8,spec.mountY,bore,-angle,angle-Math.PI*2,true);
 s.lineTo(x,y-r);s.absarc(x-r,y-r,r,0,Math.PI/2);s.lineTo(-x+r,y);s.absarc(-x+r,y-r,r,Math.PI/2,Math.PI);
 s.lineTo(-x,spec.mountY+dy);s.absarc(-8,spec.mountY,bore,Math.PI-angle,-Math.PI+angle,true);
 s.lineTo(-x,-y+r);s.absarc(-x+r,-y+r,r,Math.PI,Math.PI*1.5);s.closePath();
 const center=new THREE.Path();center.absarc(0,spec.mountY,3.1,0,Math.PI*2,true);s.holes.push(center);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:20}),materials.plastic(0x284b38,{roughness:.91}),[0,0,-1.8],'8Servos PCB with mounting-pillar and Grove clearances');
 host.parts.pcb=pcb;
 // Recessed solid components occupy the real interior. They are neither a
 // hole-covering plane nor a simulation of the controller's electrical state.
 slab(host.body,5.8,4.5,.7,.25,[-5,1.5,-2.5],materials.plastic(0x1b231f,{roughness:.86}),[],.035).name='8Servos concealed MCU package';
}

function moldedHeaderShape(){
 const p=spec.header.pitch,half=p/2,c=.38,s=new THREE.Shape();
 s.moveTo(-half+c,-p);
 for(let i=0;i<3;i++){
  const a=i*p-half,b=i*p+half;
  if(i)s.lineTo(a+c,-p);s.lineTo(b-c,-p);s.lineTo(b,-p+c);
  if(i<2)s.lineTo(b+c,-p);
 }
 s.lineTo(2*p+half,p-c);s.lineTo(2*p+half-c,p);
 for(let i=2;i>=0;i--){const a=i*p-half;if(i<2)s.lineTo(i*p+half-c,p);s.lineTo(a+c,p);s.lineTo(a,p-c);if(i>0)s.lineTo(a-c,p);}
 s.lineTo(-half,-p+c);s.closePath();return s;
}

function servoHeaders(host){
 const group=new THREE.Group();group.name='8Servos four physical 3x2 male headers';host.body.add(group);
 const yellow=materials.plastic(0xeab71b,{roughness:.66}),gold=materials.metal(0xc6ab52,{roughness:.34});
 for(let pair=0;pair<4;pair++){
  const y=spec.header.firstY-spec.header.pitch/2-pair*spec.header.pairPitch;
  mesh(group,new THREE.ExtrudeGeometry(moldedHeaderShape(),{depth:spec.header.baseDepth,bevelEnabled:false}),yellow,[spec.header.firstX,y,spec.header.baseZ],`8Servos P${pair+1} molded yellow 3x2 header base`);
 }
 for(const channel of CHANNELS){
  for(let col=0;col<3;col++){
   const x=spec.header.firstX+col*spec.header.pitch;
   mesh(group,new THREE.BoxGeometry(.64,.64,8.95),gold,[x,channel.y,2.775],`8Servos CH${channel.number} ${['GND','VM','signal'][col]} square pin`);
   const tip=new THREE.CylinderGeometry(.22,.64/Math.SQRT2,.25,4).rotateX(Math.PI/2).rotateZ(Math.PI/4);
   mesh(group,tip,gold,[x,channel.y,7.375],`8Servos CH${channel.number} tapered male-pin tip`);
  }
  host.add(new Port({id:channel.id,label:`CH${channel.number} · GND / VM / signal`,connector:'servo-2.54-3p',position:[spec.header.firstX+spec.header.pitch,channel.y,spec.header.pinTopZ],quaternion:portQuaternion('front'),hitSize:[7.5,.8,2.4],pins:[{n:1,name:'GND'},{n:2,name:'VM'},{n:3,name:'IO'+channel.number}],pinGrid:{cols:3,rows:1,pitch:2.54,center:[0,0],order:col=>col+1},meta:{role:'visual-connector',face:'front',scope:'Physical mating frame only; no PWM, servo movement, voltage or electrical behavior'}}));
 }
 host.servoHeaders=group;
}

function powerTerminal(host){
 const group=new THREE.Group();group.name='8Servos fixed HT3.96-4P power socket';host.body.add(group);
 const orange=materials.plastic(0xf2a04a,{roughness:.64}),metal=materials.metal(0xb9b9a1,{roughness:.43});
 slab(group,15.8,9.8,.6,.3,[0,22.6,-1],orange,[],.045).name='8Servos power socket solid floor';
 for(const x of [-7.55,7.55])slab(group,.7,9.8,6.2,.12,[x,22.6,-.4],orange,[],.035).name='8Servos power socket side wall';
 slab(group,14.4,.7,5.9,.12,[0,17.85,-.4],orange,[],.03).name='8Servos power socket recessed rear wall';
 const windows=spec.terminal.pinX.map(cx=>({w:2.6,h:1.25,r:.12,cx,cy:-3.65}));
 slab(group,15.8,9.8,.65,.3,[0,22.6,5.8],orange,windows,.045).name='8Servos power socket roof with four real inspection windows';
 for(const x of [-3.96,0,3.96])slab(group,.4,8.5,.7,.08,[x,23.2,-.4],orange,[],.025).name='8Servos power socket channel rib';
 for(const [i,x]of spec.terminal.pinX.entries()){
  mesh(group,new THREE.BoxGeometry(.68,8.4,.68),metal,[x,22.4,1.55],`8Servos ${spec.terminal.names[i]} recessed power contact`);
  mesh(group,new THREE.BoxGeometry(.68,1.9,.68),metal,[x,17.35,1.55],'8Servos power socket bent lead');
  mesh(group,new THREE.BoxGeometry(.68,.68,2.6),metal,[x,16.4,.2],'8Servos power socket PCB tail');
 }
 host.add(new Port({id:'terminal',label:'HT3.96-4P · HPWR / GND / GND / 5V',connector:'ht3.96-4p',position:spec.terminal.position,hitSize:[15.8,1,7],pins:spec.terminal.names.map((name,i)=>({n:i+1,name})),pinGrid:{cols:4,rows:1,pitch:3.96,center:[0,-1.1],order:col=>col+1},meta:{role:'visual-connector',face:'top',scope:'Physical fixed socket only; no power-path, current sensing or electrical behavior'}}));
 host.powerSocket=group;
}

function groveConnector(host){
 const socket=grove(host,spec.grove);socket.name='8Servos red open-top HY2.0-4P socket';
 const cover=socket.children.find(o=>o.geometry?.parameters?.height===.8&&o.position.y>0);
 if(!cover)throw new Error('8Servos Grove roof was not found');
 const plastic=cover.material;cover.removeFromParent();cover.geometry.dispose();
 for(const x of [-3.85,3.85])mesh(socket,new THREE.BoxGeometry(.9,.8,6.5),plastic,[x,2.2,-3.25],'8Servos Grove open upper rail');
 mesh(socket,new THREE.BoxGeometry(3.4,.65,2),plastic,[0,1.2,-5.1],'8Servos Grove short latch tongue');
 const port=host.port('grove');port.pins=[{n:1,name:'GND'},{n:2,name:'5V'},{n:3,name:'SDA'},{n:4,name:'SCL'}];
 for(const x of [-3,-1,1,3])mesh(host.body,new THREE.BoxGeometry(.42,1.2,1.2),materials.metal(0xabae91,{roughness:.47}),[x,-21.3,-.8],'8Servos Grove solder tail');
}

function build(host){
 addCadParts(host,data,{shell:materials.plastic(0xe7eae3,{roughness:.77})});
 board(host);servoHeaders(host);powerTerminal(host);groveConnector(host);
 screw(host.body,[0,spec.mountY,-4.015],'back',1.35);
 host.add(new Component({id:'sensor',label:'Unit 8Servos visual anchor',meta:{role:'visual-anchor',scope:'no-PWM-registers-power-state-current-sensor-or-servo-physics'}}));
 host.unitStickers=addStickers(host);
}
export class Model extends Device{
 static meta={id:'m5stack.unit.8servos',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};
 build(options={}){build(this);if(options.terminalPlug===true)this.port('terminal').attach(new TerminalPlug());}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.8servos.grove',name:spec.name,sku:spec.sku,connector:'grove',keymap:{}};
 build(options={}){buildGroveModuleAssembly(this,build,options);if(options.terminalPlug===true)this.port('terminal').attach(new TerminalPlug());}
}
export {spec,CHANNELS,TerminalPlug};
export default Model;
