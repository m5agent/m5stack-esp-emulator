import * as THREE from 'three';
import {Device,Module,Component,Button,Led,Port,materials} from '../../core/index.js';
import {VisualJoint} from '../../core/components/VisualJoint.js';
import {addCadParts} from '../../modeling/cad.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {slab,mesh,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {roundedRect} from '../../core/geometry.js';
import {spec,CHANNELS} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';

function cylinder(parent,r,depth,position,material,name){
 return mesh(parent,new THREE.CylinderGeometry(r,r,depth,48).rotateX(Math.PI/2),material,position,name);
}
function board(host){
 const shape=new THREE.Shape(),x=9.9,top=60,bottom=60,r=2.2,notch=5.6,bore=4.2,offset=x-8,dy=Math.sqrt(bore*bore-offset*offset),theta=Math.acos(offset/bore);
 shape.moveTo(-x+r,-bottom);shape.lineTo(-notch,-bottom);shape.lineTo(-notch,-55.1);shape.lineTo(notch,-55.1);shape.lineTo(notch,-bottom);shape.lineTo(x-r,-bottom);
 shape.absarc(x-r,-bottom+r,r,-Math.PI/2,0);shape.lineTo(x,spec.mountY-dy);shape.absarc(8,spec.mountY,bore,-theta,theta-Math.PI*2,true);
 shape.lineTo(x,top-r);shape.absarc(x-r,top-r,r,0,Math.PI/2);shape.lineTo(-x+r,top);shape.absarc(-x+r,top-r,r,Math.PI/2,Math.PI);
 shape.lineTo(-x,spec.mountY+dy);shape.absarc(-8,spec.mountY,bore,Math.PI-theta,-Math.PI+theta,true);shape.lineTo(-x,-bottom+r);shape.absarc(-x+r,-bottom+r,r,Math.PI,Math.PI*1.5);shape.closePath();
 shape.holes.push(roundedRect(6.6,6.6,3.3,{cx:0,cy:spec.mountY,path:new THREE.Path(),clockwise:true}));
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(shape,{depth:.8,bevelEnabled:false,curveSegments:24}),materials.plastic(0x233e31,{roughness:.92}),[0,0,-2.6],'8Angle PCB with mounting-pillar and Grove relief');
 slab(host.body,7,7,.95,.35,[0,-24,-3.55],materials.plastic(0x1c2420,{roughness:.9}),[],.04).name='8Angle recessed rear MCU package';
 return pcb;
}
function capGeometry(number){
 const cap=new THREE.Group();cap.name=`CH${number} moving potentiometer cap and shaft`;
 const black=materials.plastic(0x151a19,{roughness:.68}),cyan=materials.plastic(0x05a8cd,{roughness:.48});
 // Closed molded body with a blind bore, not a solid cylinder over a shaft.
 const profile=[[1.7,0],[4.85,0],[5,.3],[4.82,.85],[4.6,11.7],[4.3,12.3],[0,12.3],[0,6],[1.7,6],[1.7,0]].map(p=>new THREE.Vector2(...p));
 mesh(cap,new THREE.LatheGeometry(profile,80).rotateX(Math.PI/2),black,[0,0,0],`CH${number} bored knob body`);
 const ridge=new THREE.Shape(),a=.034;ridge.moveTo(4.48*Math.cos(-a),4.48*Math.sin(-a));ridge.lineTo(4.94*Math.cos(-a),4.94*Math.sin(-a));ridge.absarc(0,0,4.94,-a,a,false);ridge.lineTo(4.48*Math.cos(a),4.48*Math.sin(a));ridge.absarc(0,0,4.48,a,-a,true);ridge.closePath();
 for(let i=0;i<20;i++){
  const geometry=new THREE.ExtrudeGeometry(ridge,{depth:10.5,bevelEnabled:false,curveSegments:3});
  const rib=mesh(cap,geometry,black,[0,0,1],`CH${number} grip rib ${i+1}`);rib.rotation.z=i*Math.PI/10;
 }
 const radius=3.9,half=.5,delta=Math.asin(half/radius),insert=new THREE.Shape();
 insert.moveTo(half,-Math.sqrt(radius*radius-half*half));insert.absarc(0,0,radius,-Math.PI/2+delta,Math.PI*1.5-delta,false);insert.lineTo(-half,-2.8);insert.lineTo(half,-2.8);insert.closePath();
 mesh(cap,new THREE.ExtrudeGeometry(insert,{depth:.3,bevelEnabled:false,curveSegments:32}),cyan,[0,0,12.3],`CH${number} solid cyan insert with open index notch`);
 cylinder(cap,1.5,8,[0,0,1.8],materials.metal(0x9ca7a2,{roughness:.48}),`CH${number} moving potentiometer shaft`);
 cap.userData={role:'physical-actuator-cap',channel:number,boreRadiusMm:1.7,boreDepthMm:6,scope:'rotary-only; no push switch'};
 return cap;
}
function channel(host,item){
 const {number,y}=item;
 slab(host.body,10.8,11,4.8,.45,[0,y,-1.8],materials.plastic(0x167b9d,{roughness:.78}),[],.05).name=`CH${number} fixed potentiometer package`;
 slab(host.body,10.6,10.8,.55,.4,[0,y,3.02],materials.metal(0x9ca7a2,{roughness:.48}),[{w:3.5,h:3.5,r:1.75}],.03).name=`CH${number} fixed metal retaining cover`;
 const ring=new THREE.Shape();ring.absarc(0,0,3.1,0,Math.PI*2,false);const hole=new THREE.Path();hole.absarc(0,0,1.75,0,Math.PI*2,true);ring.holes.push(hole);
 mesh(host.body,new THREE.ExtrudeGeometry(ring,{depth:1.5,bevelEnabled:false,curveSegments:24}),materials.metal(0xaab3af,{roughness:.48}),[0,y,3.6],`CH${number} fixed annular shaft bushing`);
 const cap=capGeometry(number);cap.position.set(0,y,spec.knob.baseZ);host.body.add(cap);
 const rotation=host.add(new VisualJoint({id:item.rotation,label:`CH${number} potentiometer position`,position:[0,y,spec.knob.baseZ],axis:[0,0,1],limitsDeg:[...spec.knob.limitsDeg],meta:{channel:number,rangeEvidence:spec.source.rotation,scope:'Externally driven cap and shaft only; no ADC, resistance, bus or firmware state'}}));
 rotation.adopt(cap);return {rotation,cap};
}
function light(host,number,y){
 const pipe=new THREE.Mesh(new THREE.BoxGeometry(spec.led.w,spec.led.h,spec.led.depth),materials.plastic(0x8f9b91,{roughness:.62}));pipe.position.z=-spec.led.depth/2;pipe.name=`RGB${number} recessed physical light pipe`;
 return host.add(new Led({id:'rgb-'+number,label:number<9?`CH${number} external RGB`:'Switch external RGB',mesh:pipe,position:[spec.led.x,y,spec.led.z],radius:.45,glowSize:3,lensColor:0x8f9b91,meta:{role:'externally-driven-visual',visualLocation:number<9?'CH'+number:'switch',mapping:'Physical location only; not schematic U1-U9 chain order',scope:'No automatic response to angle, switch or power'}}));
}
function slide(host){
 const dark=materials.plastic(0x111713,{roughness:.84});
 slab(host.body,7,4,5,.4,[0,59,-1.5],dark,[],.05).name='8Angle fixed slide-switch package';
 slab(host.body,5.9,2.9,.6,.2,[0,59,4.3],dark,[{w:4.5,h:1.6,r:.12}],.025).name='8Angle slotted slide-switch carrier';
 mesh(host.body,new THREE.BoxGeometry(4.5,1.6,.2),dark,[0,59,4.15],'8Angle recessed slide-switch floor');
 const cap=new THREE.Group();cap.name='8Angle stable slide-switch thumb';
 slab(cap,1.2,1.1,1.5,.12,[0,0,0],materials.plastic(0x151c18,{roughness:.7}),[],.035);
 for(const x of [-.3,0,.3])mesh(cap,new THREE.BoxGeometry(.09,1,.12),materials.plastic(0x354139,{roughness:.9}),[x,0,1.51],'Slide-switch grip ridge');
 return host.add(new Button({id:'switch',label:'8Angle stable slide switch',mesh:cap,position:[-1.1,59,4.45],axis:[1,0,0],travel:spec.slide.travel,latching:true,meta:{role:'visual-control',mechanism:'slide',detents:[0,1],positionEvidence:'Official U154 front photograph and SS12D07L4B schematic; 2.2 mm detent separation is a visual estimate',scope:'No electrical truth table or automatic LED behavior'}}));
}
function connector(host){
 const g=new THREE.Group();g.name='8Angle red open-top HY2.0-4P socket';g.position.fromArray(spec.grove.position);g.quaternion.copy(FACE.bottom);host.body.add(g);
 const d=spec.grove,plastic=materials.plastic(0xa92323,{roughness:.62}),metal=materials.metal(0xbaad83,{roughness:.42});
 const box=(size,p,name,material=plastic)=>mesh(g,new THREE.BoxGeometry(...size),material,p,'8Angle Grove '+name);
 for(const sign of [-1,1]){box([.7,5.2,d.depth],[sign*4.65,0,-d.depth/2],'side rail');box([.9,.8,d.depth],[sign*3.85,2.2,-d.depth/2],'upper lip');}
 box([8.6,.7,d.depth],[0,-2.25,-d.depth/2],'floor');box([8.6,5.2,.6],[0,0,-d.depth+.3],'rear wall');box([8.6,2.7,4.75],[0,-1.25,-4.225],'recessed contact support');box([3.4,.65,3],[0,1.2,-4.95],'locking tongue');
 for(let i=0;i<4;i++)box([.42,.42,1.2],[(i-1.5)*2,-.15,-1.25],`contact ${i+1}`,metal);
 host.add(new Port({id:'grove',label:'HY2.0-4P PORT.A',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND'},{n:2,name:'5V'},{n:3,name:'SDA'},{n:4,name:'SCL'}],meta:{role:'visual-connector',face:'bottom',pinOrder:'Official U154 Grove table: black GND, red 5V, yellow SDA, white SCL'}}));
 return g;
}
function build(host){
 addCadParts(host,data,{shell:materials.plastic(0x50544f,{roughness:.8})});
 host.angleBoard=board(host);host.groveSocket=connector(host);
 host.angleMechanisms=CHANNELS.map(item=>channel(host,item));
 host.rgbLights=CHANNELS.map(item=>light(host,item.number,item.y));host.rgbLights.push(light(host,9,59));
 host.stableSwitch=slide(host);screw(host.body,[0,spec.mountY,-4.98],'back',1.4);
 addStickers(host);
 host.add(new Component({id:'sensor',label:'8Angle geometry anchor',meta:{role:'visual-anchor',scope:'No ADC, resistance, I2C, registers or firmware'}}));
}
export class Model extends Device{
 static meta={id:'m5stack.unit.8angle',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{Space:'switch'}};
 build(){build(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.8angle.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,build,options);}
}
export {spec,CHANNELS};
export default Model;
