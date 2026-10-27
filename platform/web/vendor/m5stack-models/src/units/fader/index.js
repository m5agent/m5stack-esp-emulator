import {addStickers} from './stickers.js';
import * as THREE from 'three';
import {Device,Module,Component,Led,VisualSlide,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {mesh,slab,grove,screw} from '../../modeling/parts.js';
import data from './geometry-data.js';
import {spec,LEDS} from './dimensions.js';

function board(host){
 const s=new THREE.Shape(),w=9.9,h=29.9,r=2.8,relief=3.8,dy=Math.sqrt(relief**2-(w-8)**2),a=Math.acos((w-8)/relief);
 s.moveTo(-w+r,-h);s.lineTo(-5.3,-h);s.lineTo(-5.3,-25.1);s.lineTo(5.3,-25.1);s.lineTo(5.3,-h);s.lineTo(w-r,-h);s.absarc(w-r,-h+r,r,-Math.PI/2,0);
 s.lineTo(w,spec.mountY-dy);s.absarc(8,spec.mountY,relief,-a,a-Math.PI*2,true);s.lineTo(w,h-r);s.absarc(w-r,h-r,r,0,Math.PI/2);s.lineTo(-w+r,h);s.absarc(-w+r,h-r,r,Math.PI/2,Math.PI);
 s.lineTo(-w,spec.mountY+dy);s.absarc(-8,spec.mountY,relief,Math.PI-a,-Math.PI+a,true);s.lineTo(-w,-h+r);s.absarc(-w+r,-h+r,r,Math.PI,Math.PI*1.5);s.closePath();
 const bore=new THREE.Path();bore.absarc(0,spec.mountY,2.35,0,Math.PI*2,true);s.holes.push(bore);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:24}),materials.plastic(0x28543e,{roughness:.86}),[0,0,-2.2],'Fader solid PCB with real mount and Grove reliefs');host.parts.pcb=pcb;
 for(const [x,y,w,h]of [[-5.4,-11.5,2,3],[5.1,-11.5,2.8,1.6]])slab(host.body,w,h,.65,.12,[x,y,-1.4],materials.plastic(0x242a27),[],.025).name='Fader fixed circuit package';
}

function potentiometer(host){
 const group=new THREE.Group();group.name='Fader fixed 35 mm slide potentiometer assembly';group.position.set(spec.slider.origin[0],spec.slider.origin[1],0);host.body.add(group);
 const black=materials.plastic(0x1b211e,{roughness:.8}),metal=materials.metal(0x727b75,{roughness:.56});
 slab(group,8.8,43.4,2.2,.3,[0,0,-1.2],black,[],.05).name='Fader fixed potentiometer solid lower case';
 for(const x of [-3.4,3.4])slab(group,2,43.4,3,.16,[x,0,1],black,[],.04).name='Fader fixed potentiometer side wall';
 for(const y of [-21.1,21.1])slab(group,6.8,1.2,3,.12,[0,y,1],black,[],.03).name='Fader fixed potentiometer end stop';
 slab(group,8.6,43,.35,.25,[0,0,3.7],metal,[{w:1.95,h:37.3,r:.47,cx:0,cy:0}],.025).name='Fader fixed metal guide with real slider slit';
 for(const x of [-.55,.55])slab(group,.25,37.7,.18,.03,[x,0,1.1],materials.plastic(0x4a4134,{roughness:.92}),[],0).name='Fader fixed resistive track';
 return group;
}

function cap(){
 const group=new THREE.Group();group.name='Fader movable cap, stem and carriage';
 const black=materials.plastic(0x202423,{roughness:.75}),metal=materials.metal(0xa7aaa2,{roughness:.5});
 slab(group,3.8,3.8,1.4,.25,[0,0,2.2],black,[],.035).name='Fader moving internal carriage';
 mesh(group,new THREE.BoxGeometry(1.45,.7,6.4),metal,[0,0,6.1],'Fader moving metal stem through real track slot');
 // The own U123 drawing gives a 7.2 x 11.2 mm cap and 22.8 mm overall
 // height. Grip curvature and ridge sizes are reconstructed from its photo.
 const profile=[[-5.6,8.4],[5.6,8.4],[5.4,10],[4.9,12.1],[4.2,14.4],[3.4,16.3],[1.3,17.55],[-1.3,17.55],[-3.4,16.3],[-4.2,14.4],[-4.9,12.1],[-5.4,10]];
 const shape=new THREE.Shape();shape.moveTo(...profile[0]);for(const p of profile.slice(1))shape.lineTo(...p);shape.closePath();
 // Transform (profileY, profileZ, extrusionX) into device (X,Y,Z).
 const g=new THREE.ExtrudeGeometry(shape,{depth:7.2,bevelEnabled:false});
 g.applyMatrix4(new THREE.Matrix4().set(0,0,1,-3.6,1,0,0,0,0,1,0,0,0,0,0,1));
 mesh(group,g,black,[0,0,0],'Fader solid sculpted grip cap');
 const stripe=new THREE.ExtrudeGeometry(shape,{depth:.8,bevelEnabled:false});stripe.applyMatrix4(new THREE.Matrix4().set(0,0,1,-.4,1,0,0,0,0,1,0,.045,0,0,0,1));
 mesh(group,stripe,materials.plastic(0xe5e7dc,{roughness:.58}),[0,0,0],'Fader raised white centre index insert');
 for(const sign of [-1,1])for(const [y,z]of [[2.6,16.9],[3.8,15.4],[4.5,13.35],[5.1,11.15]]){
  const rib=slab(group,7.21,.22,.18,.03,[0,sign*y,z],black,[],0);rib.name='Fader molded grip ridge';rib.rotation.x=sign*.35;
 }
 return group;
}

function lights(host){
 const group=new THREE.Group();group.name='Fader 14 independent physical RGB emitters';host.body.add(group);
 for(const d of LEDS){
  slab(group,3.5,3.5,.8,.15,[d.x,d.y,-1.4],materials.plastic(0xe8e6d9,{roughness:.6}),[],.025).name=`Fader LED${d.number} SMD package`;
  const lens=new THREE.Mesh(new THREE.BoxGeometry(.88,5.65,.12),materials.plastic(0xe3e8d9,{roughness:.53}));lens.name=`Fader LED${d.number} diffused light-guide segment`;
  const led=host.add(new Led({id:d.id,label:`Fader RGB ${d.number}`,mesh:lens,position:[d.x,d.y,3.8],glowSize:6,meta:{role:'externally-driven-visual',part:'SK6812',source:'U123 product states 14 individually controlled LEDs; numbering follows its own rear photograph',scope:'No ADC mapping, automatic level meter, data chain, voltage or firmware behavior'}}));led.glow.position.z=1.15;
 }
}

function connector(host){
 const socket=grove(host,spec.grove);socket.name='Fader black HY2.0-4P socket';
 const port=host.port('grove');port.pins=[{n:1,name:'GND'},{n:2,name:'5V'},{n:3,name:'RGB'},{n:4,name:'Analog Input'}];
 for(const x of [-3,-1,1,3])mesh(host.body,new THREE.BoxGeometry(.42,.42,1.8),materials.metal(0xb9ae8f),[x,-25.3,-.5],'Fader fixed Grove solder lead');
}

function build(host){
 addCadParts(host,data,{shell:materials.plastic(0xe8ebe5,{roughness:.75}),guide:materials.plastic(0xe6ecdf,{roughness:.58,transparent:true,opacity:.72})});
 board(host);const rail=potentiometer(host);const movingCap=cap();
 const slider=host.add(new VisualSlide({id:'slider',label:'Fader 35 mm slide',mesh:movingCap,position:spec.slider.origin,axis:spec.slider.axis,rangeMm:spec.slider.rangeMm,positionMm:0,meta:{travelEvidence:'Official U123 product specifies 35 mm travel and centre detent',neutralEvidence:'Centre of own CAD slot at original Y26.837; default is the documented centre detent',capEvidence:'Own U123 drawing: 7.2 mm width, 11.2 mm length, 22.8 mm overall; concealed carriage and fixed pot are reconstructed appearance',scope:'Only physical cap, stem and carriage move. No resistance, ADC or LED level mapping'}}));
 lights(host);connector(host);screw(host.body,[0,spec.mountY,-5.215],'back',1.3);
 host.add(new Component({id:'sensor',label:'Fader visual anchor',meta:{role:'visual-anchor',scope:'No resistance, ADC, sensor-value or firmware behavior'}}));
 host.faderAssembly={slider,rail,cap:movingCap};
 host.unitStickers=addStickers(host);
}
export class Model extends Device{static meta={id:'m5stack.unit.fader',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(){build(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.fader.grove',name:spec.name,sku:spec.sku,connector:'grove',keymap:{}};build(options={}){buildGroveModuleAssembly(this,build,options);}}
export {spec,LEDS};
export default Model;
